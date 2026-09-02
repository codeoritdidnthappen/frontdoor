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
        // Each mode is complete-or-nothing against ITS OWN contract. Screening does not relax
        // metrology's requirements; it has different ones, and the schema enforces the difference
        // in both directions -- a screening capture carrying a caliper reading is refused too.
        var roi: ROITaps?
        if record.captureMode.carriesMetrologyTruth {
            guard let taps = record.roi else {
                return .failure(.incomplete(
                    "This capture has no ROI taps, so no arm can measure it."))
            }
            // Exactly four, because the homography is built from a known rectangle: three corners
            // do not determine it and five are not a rectangle. The schema says minItems 4 and
            // maxItems 4, so anything else wrote an invalid sidecar and left the image behind
            // it -- a partial record, which is what AC5 exists to prevent (QA B03).
            guard taps.cardCorners.count == Sidecar.requiredCardCorners else {
                return .failure(.incomplete(
                    "This capture has \(taps.cardCorners.count) card corners, not "
                    + "\(Sidecar.requiredCardCorners), so its scale cannot be recovered."))
            }
            guard record.entrance.riseInches != nil, record.entrance.instrument != nil else {
                return .failure(.incomplete(
                    "This is a metrology capture with no caliper reading, so it has no truth to "
                    + "be measured against."))
            }
            guard record.conditions.cardPlacement != nil else {
                return .failure(.incomplete(
                    "This is a metrology capture with no card placement, so its scale cannot be "
                    + "interpreted."))
            }
            roi = taps
        }

        // Our camera knows its own optics, whichever mode it is shooting in; an imported photo
        // knows none of them. The schema requires the whole intrinsics block or forbids it
        // outright, so a half-filled one must not be assembled here.
        // Metrology REQUIRES the camera model and refuses without it -- every arm needs it.
        // Screening RECORDS it when the camera offers it and proceeds without it: the phone
        // carrying depth capture has never been through the capability probe (D-032), and a
        // protocol that fails outright on a device delivering no distortion table would lose the
        // entrance rather than record it. Losing a doorway is worse than a sidecar with a gap.
        var intrinsics: Sidecar.Intrinsics?
        var gravity: [Double]?
        if record.captureMode.isOurCamera {
            let table = record.intrinsics?.lensDistortionLookupTable
            let complete = record.intrinsics != nil && record.gravity != nil
                && (table?.count ?? 0) >= 8
            if record.captureMode.carriesMetrologyTruth && !complete {
                return .failure(.incomplete(
                    "This capture carries no lens distortion table, so its taps cannot be "
                    + "undistorted and no arm can measure it."))
            }
            if complete, let model = record.intrinsics, let sample = record.gravity,
               let table {
                intrinsics = Sidecar.Intrinsics(
                    fx: model.fx, fy: model.fy, cx: model.cx, cy: model.cy,
                    distortionTable: unpack(table),
                    distortionCenter: Sidecar.Point(
                        x: model.lensDistortionCenterX,
                        y: model.lensDistortionCenterY))
                gravity = [sample.x, sample.y, sample.z]
            }
        }
        let depth: Sidecar.DepthRef? = {
            guard let depthPath, let depthSHA256 else { return nil }
            return Sidecar.DepthRef(path: depthPath, sha256: depthSHA256)
        }()

        return .success(Sidecar(
            captureId: record.captureId,
            entranceId: record.entrance.id,
            capturedAt: record.capturedAt,
            deviceModel: record.deviceModel,
            lens: record.captureMode.isOurCamera ? record.lens : nil,
            captureDevice: record.captureMode.isOurCamera ? record.captureDevice : nil,
            zoomFactor: record.captureMode.isOurCamera ? record.zoomFactor : nil,
            captureMode: record.captureMode,
            image: Sidecar.FileRef(
                path: imagePath, sha256: imageSHA256,
                width: record.pixelWidth, height: record.pixelHeight),
            depth: depth,
            intrinsics: intrinsics,
            gravity: gravity,
            // Gated on the MODE, never on whether the entrance happens to carry a reading.
            // `EntranceStore.resolveScreening` deliberately returns an entrance already recorded
            // with its caliper reading intact, so a doorway shot in metrology mode in the morning
            // and in screening mode in the afternoon would otherwise write `ground_truth` into a
            // screening sidecar -- a reading nobody took at that shot, and a record the schema
            // refuses. Same for the card placement.
            cardPlacement: record.captureMode.carriesMetrologyTruth
                ? record.conditions.cardPlacement?.rawValue : nil,
            groundTruth: record.captureMode.carriesMetrologyTruth
                ? record.entrance.riseInches.flatMap({ rise in
                    record.entrance.instrument.map {
                        Sidecar.GroundTruth(riseIn: rise, instrument: $0)
                    }
                  })
                : nil,
            conditions: Sidecar.Conditions(
                distanceM: record.conditions.distanceM,
                lighting: record.conditions.lighting.rawValue,
                // Gated on the mode for the same reason as the card placement: the screening
                // protocol never asks an operator for a surface, so any value reaching here came
                // from a default rather than from someone looking at the ground.
                surface: record.captureMode.carriesMetrologyTruth
                    ? record.conditions.surface?.rawValue : nil,
                occlusion: record.conditions.occlusion.rawValue),
            roi: roi.map {
                Sidecar.ROI(
                    thresholdTop: [$0.thresholdTop.x, $0.thresholdTop.y],
                    thresholdBottom: [$0.thresholdBottom.x, $0.thresholdBottom.y],
                    cardCorners: $0.cardCorners.map { [$0.x, $0.y] })
            },
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
        into directory: URL,
        imageExtension: String = "jpg"
    ) -> Result<Written, Failure> {
        let base = record.captureId
        // Our camera emits JPEG; an imported photo is whatever the library handed over, which on
        // an iPhone is usually HEIC and for a screenshot is PNG. Naming those `.jpg` would label
        // a file for a format it does not hold (D-034).
        let imageURL = directory.appendingPathComponent("\(base).\(imageExtension)")
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
