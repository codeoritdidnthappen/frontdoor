import CryptoKit
import Foundation

/// Writes one capture to disk: the image, the depth map when there is one, and the sidecar.
///
/// The ordering is the requirement, not an implementation detail (TICK-028 AC4). Hashes are taken
/// over the bytes that reached the disk, and the sidecar is renamed into place only after those
/// files are closed -- so a crash mid-capture can leave an orphaned image, which is harmless, but
/// never a sidecar pointing at a file that was never finished, which is a row the dataset would
/// treat as real.
enum CaptureWriter {

    enum Failure: Error, Equatable {
        case incomplete(String)
        case unwritable(String)

        var message: String {
            switch self {
            case .incomplete(let what):
                return "\(what) Nothing was written."
            case .unwritable(let detail):
                return "The capture could not be saved: \(detail). Nothing was written."
            }
        }
    }

    struct Written: Equatable {
        var sidecarURL: URL
        var imageURL: URL
        var depthURL: URL?
        var sidecarBytes: Data
    }

    /// Deterministic bytes for identical content, so `sidecar_sha256` is reproducible (AC6).
    /// `.sortedKeys` rather than a hand-fixed order: an order maintained by hand drifts the first
    /// time a field is added.
    static func encoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        return encoder
    }

    static func sha256(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    /// Assemble the sidecar for a record, or say what is missing.
    ///
    /// Complete-or-nothing is decided here, before anything touches the disk (AC5). A capture
    /// without ROI taps or without a distortion table is not a partial record to be fixed later --
    /// it is unmeasurable, and writing it would put a row in the dataset that nothing can use and
    /// nothing can tell apart from a good one.
    static func sidecar(
        for record: CaptureRecord,
        imagePath: String,
        imageSHA256: String,
        depthPath: String?,
        depthSHA256: String?
    ) -> Result<Sidecar, Failure> {
        guard let roi = record.roi else {
            return .failure(.incomplete("This capture has no ROI taps, so no arm can measure it."))
        }
        guard let table = record.intrinsics.lensDistortionLookupTable, table.count >= 8 else {
            return .failure(.incomplete(
                "This capture carries no lens distortion table, so its taps cannot be undistorted."))
        }
        let depth: Sidecar.FileRef? = {
            guard let depthPath, let depthSHA256 else { return nil }
            return Sidecar.FileRef(
                path: depthPath, sha256: depthSHA256,
                width: record.depth?.width, height: record.depth?.height)
        }()

        return .success(Sidecar(
            captureId: record.captureId,
            entranceId: record.entrance.id,
            capturedAt: record.capturedAt,
            deviceModel: record.deviceModel,
            lens: record.lens,
            captureDevice: record.captureDevice,
            zoomFactor: record.zoomFactor,
            image: Sidecar.FileRef(
                path: imagePath, sha256: imageSHA256,
                width: record.pixelWidth, height: record.pixelHeight),
            depth: depth,
            intrinsics: Sidecar.Intrinsics(
                fx: record.intrinsics.fx,
                fy: record.intrinsics.fy,
                cx: record.intrinsics.cx,
                cy: record.intrinsics.cy,
                distortionTable: unpack(table),
                distortionCenter: Sidecar.Point(
                    x: record.intrinsics.lensDistortionCenterX,
                    y: record.intrinsics.lensDistortionCenterY)),
            gravity: [record.gravity.x, record.gravity.y, record.gravity.z],
            cardPlacement: record.conditions.cardPlacement.rawValue,
            groundTruth: Sidecar.GroundTruth(
                riseIn: record.entrance.riseInches,
                instrument: record.entrance.instrument),
            conditions: Sidecar.Conditions(
                distanceM: record.conditions.distanceM,
                lighting: record.conditions.lighting.rawValue,
                surface: record.conditions.surface.rawValue,
                occlusion: record.conditions.occlusion.rawValue),
            roi: Sidecar.ROI(
                thresholdTop: [roi.thresholdTop.x, roi.thresholdTop.y],
                thresholdBottom: [roi.thresholdBottom.x, roi.thresholdBottom.y],
                cardCorners: roi.cardCorners.map { [$0.x, $0.y] }),
            split: record.entrance.split.rawValue))
    }

    /// AVFoundation hands the table over as packed 32-bit floats.
    static func unpack(_ data: Data) -> [Double] {
        let count = data.count / MemoryLayout<Float>.size
        guard count > 0 else { return [] }
        return data.withUnsafeBytes { raw in
            raw.bindMemory(to: Float.self).prefix(count).map(Double.init)
        }
    }

    /// Write the capture. Image first, then depth, then the sidecar renamed into place.
    static func write(
        _ record: CaptureRecord,
        imageData: Data,
        depthData: Data?,
        into directory: URL
    ) -> Result<Written, Failure> {
        let base = record.captureId
        let imageURL = directory.appendingPathComponent("\(base).jpg")
        let depthURL = depthData.map { _ in directory.appendingPathComponent("\(base).depth") }
        let sidecarURL = directory.appendingPathComponent("\(base).json")

        // Assemble before writing anything, so an unmeasurable capture leaves the disk untouched
        // rather than an image with no sidecar beside it.
        let assembled = sidecar(
            for: record,
            imagePath: imageURL.lastPathComponent,
            imageSHA256: sha256(imageData),
            depthPath: depthURL?.lastPathComponent,
            depthSHA256: depthData.map(sha256))
        guard case .success(let sidecar) = assembled else {
            if case .failure(let failure) = assembled { return .failure(failure) }
            return .failure(.incomplete("This capture could not be described."))
        }

        var written: [URL] = []
        func cleanUp() { for url in written { try? FileManager.default.removeItem(at: url) } }

        do {
            try FileManager.default.createDirectory(
                at: directory, withIntermediateDirectories: true)
            try imageData.write(to: imageURL, options: .atomic)
            written.append(imageURL)

            // Hashed over what is on the disk, not over what we meant to put there: a truncated
            // write would otherwise be recorded with the hash of the full buffer, and the sidecar
            // would vouch for a file that does not match it (AC2).
            guard try Data(contentsOf: imageURL) == imageData else {
                cleanUp()
                return .failure(.unwritable("the image on disk does not match what was captured"))
            }

            if let depthURL, let depthData {
                try depthData.write(to: depthURL, options: .atomic)
                written.append(depthURL)
                guard try Data(contentsOf: depthURL) == depthData else {
                    cleanUp()
                    return .failure(.unwritable("the depth map on disk does not match"))
                }
            }

            // Last, and atomically. Until this rename lands there is no sidecar, so there is no
            // capture -- which is what makes an interrupted write leave an orphan rather than a
            // false row.
            let bytes = try encoder().encode(sidecar)
            try bytes.write(to: sidecarURL, options: .atomic)
            written.append(sidecarURL)

            return .success(Written(
                sidecarURL: sidecarURL, imageURL: imageURL,
                depthURL: depthURL, sidecarBytes: bytes))
        } catch {
            cleanUp()
            return .failure(.unwritable(error.localizedDescription))
        }
    }
}
