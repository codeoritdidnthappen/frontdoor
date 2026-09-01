import AVFoundation
import Foundation
import UIKit

/// TICK-020 spike. Answers one question on real hardware: does AVFoundation hand us
/// `AVCameraCalibrationData` alongside a full-resolution still from the 1x main lens, and does it
/// hand us depth?
///
/// The whole architecture rests on that (ASM-2), and R-9 is the risk that it is not true on the
/// team's actual phones. The simulator supplies neither true intrinsics nor depth, so simulator
/// results prove nothing — this only means anything run on a device.
///
/// Calibration delivery has preconditions. Apple gates it behind depth or virtual-device
/// constituent delivery, which is why this probes several lens configurations rather than assuming
/// the one D-014 fixes will offer it. If the 1x wide-angle path cannot deliver calibration, that
/// is the finding, and it forces a decision rather than a workaround.
enum CapabilityProbe {

    struct LensReport: Identifiable {
        var id: String { lens }
        var lens: String
        var available: Bool
        var calibrationSupported: Bool
        var depthSupported: Bool
        var maxPhotoDimensions: String
    }

    struct CaptureReport {
        var lens: String
        var pixelDimensions: String
        var calibrationDelivered: Bool
        var intrinsics: String
        var referenceDimensions: String
        var distortionTableEntries: Int?
        var depthDelivered: Bool
        var depthDetail: String
    }

    struct Report {
        var deviceModel: String
        var systemVersion: String
        var lenses: [LensReport]
        var capture: CaptureReport?
        var failure: String?

        /// Plain text, so a result can leave the phone by any route — AirDrop, Notes, a photo of
        /// the screen — and be pasted into the committed note the ticket asks for.
        var plainText: String {
            var lines = [
                "Frontdoor capability probe (TICK-020)",
                "device: \(deviceModel)  iOS \(systemVersion)",
                "",
                "Lens configurations:",
            ]
            for l in lenses {
                lines.append(
                    "  \(l.lens): available=\(l.available) calibration=\(l.calibrationSupported) "
                        + "depth=\(l.depthSupported) maxPhoto=\(l.maxPhotoDimensions)"
                )
            }
            if let c = capture {
                lines += [
                    "",
                    "Capture on \(c.lens):",
                    "  pixels: \(c.pixelDimensions)",
                    "  calibration delivered: \(c.calibrationDelivered)",
                    "  intrinsics: \(c.intrinsics)",
                    "  reference dimensions: \(c.referenceDimensions)",
                    "  distortion table entries: \(c.distortionTableEntries.map(String.init) ?? "none")",
                    "  depth delivered: \(c.depthDelivered) \(c.depthDetail)",
                ]
            }
            if let failure { lines += ["", "FAILED: \(failure)"] }
            return lines.joined(separator: "\n")
        }
    }

    /// Lens configurations worth asking about. The first is the one D-014 fixes; the others exist
    /// to show whether calibration is available at all on this device, which changes what a
    /// fallback would cost.
    private static let candidates: [(String, AVCaptureDevice.DeviceType)] = [
        ("builtInWideAngleCamera (1x, the D-014 path)", .builtInWideAngleCamera),
        ("builtInDualWideCamera", .builtInDualWideCamera),
        ("builtInLiDARDepthCamera", .builtInLiDARDepthCamera),
    ]

    static func run() async -> Report {
        var report = Report(
            deviceModel: hardwareIdentifier(),
            systemVersion: UIDevice.current.systemVersion,
            lenses: [],
            capture: nil,
            failure: nil
        )

        for (label, type) in candidates {
            report.lenses.append(inspect(label: label, type: type))
        }

        do {
            report.capture = try await captureOnWideAngle()
        } catch {
            report.failure = error.localizedDescription
        }
        return report
    }

    // MARK: - Static inspection

    private static func inspect(label: String, type: AVCaptureDevice.DeviceType) -> LensReport {
        guard let device = AVCaptureDevice.default(type, for: .video, position: .back) else {
            return LensReport(
                lens: label, available: false, calibrationSupported: false,
                depthSupported: false, maxPhotoDimensions: "-"
            )
        }
        let session = AVCaptureSession()
        let output = AVCapturePhotoOutput()
        session.beginConfiguration()
        session.sessionPreset = .photo
        defer { session.commitConfiguration() }

        guard
            let input = try? AVCaptureDeviceInput(device: device),
            session.canAddInput(input), session.canAddOutput(output)
        else {
            return LensReport(
                lens: label, available: true, calibrationSupported: false,
                depthSupported: false, maxPhotoDimensions: "could not configure"
            )
        }
        session.addInput(input)
        session.addOutput(output)

        // Depth must be enabled before calibration support is meaningful: Apple gates calibration
        // delivery behind depth or constituent-photo delivery.
        if output.isDepthDataDeliverySupported { output.isDepthDataDeliveryEnabled = true }

        let dims = output.maxPhotoDimensions
        return LensReport(
            lens: label,
            available: true,
            calibrationSupported: output.isCameraCalibrationDataDeliverySupported,
            depthSupported: output.isDepthDataDeliverySupported,
            maxPhotoDimensions: "\(dims.width)x\(dims.height)"
        )
    }

    // MARK: - Real capture

    private static func captureOnWideAngle() async throws -> CaptureReport {
        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back)
        else { throw ProbeError.noDevice }

        let session = AVCaptureSession()
        let output = AVCapturePhotoOutput()
        session.beginConfiguration()
        session.sessionPreset = .photo
        let input = try AVCaptureDeviceInput(device: device)
        guard session.canAddInput(input), session.canAddOutput(output) else {
            session.commitConfiguration()
            throw ProbeError.cannotConfigure
        }
        session.addInput(input)
        session.addOutput(output)
        if output.isDepthDataDeliverySupported { output.isDepthDataDeliveryEnabled = true }
        // Ask for the largest still the format offers, so "full resolution" is a measured claim
        // rather than an assumption (D-014 rejects ARKit precisely for frame size).
        output.maxPhotoDimensions = output.maxPhotoDimensions
        session.commitConfiguration()

        session.startRunning()
        defer { session.stopRunning() }

        let settings = AVCapturePhotoSettings()
        settings.maxPhotoDimensions = output.maxPhotoDimensions
        if output.isDepthDataDeliverySupported { settings.isDepthDataDeliveryEnabled = true }
        if output.isCameraCalibrationDataDeliverySupported {
            settings.isCameraCalibrationDataDeliveryEnabled = true
        }

        let photo = try await withCheckedThrowingContinuation { continuation in
            let delegate = ProbeDelegate(continuation: continuation)
            Self.retained = delegate
            output.capturePhoto(with: settings, delegate: delegate)
        }
        Self.retained = nil

        let calibration = photo.cameraCalibrationData
        let matrix = calibration?.intrinsicMatrix
        return CaptureReport(
            lens: "builtInWideAngleCamera",
            pixelDimensions: "\(photo.resolvedSettings.photoDimensions.width)x"
                + "\(photo.resolvedSettings.photoDimensions.height)",
            calibrationDelivered: calibration != nil,
            intrinsics: matrix.map {
                String(
                    format: "fx=%.1f fy=%.1f cx=%.1f cy=%.1f",
                    $0.columns.0.x, $0.columns.1.y, $0.columns.2.x, $0.columns.2.y
                )
            } ?? "not delivered",
            referenceDimensions: calibration.map {
                "\(Int($0.intrinsicMatrixReferenceDimensions.width))x"
                    + "\(Int($0.intrinsicMatrixReferenceDimensions.height))"
            } ?? "-",
            distortionTableEntries: calibration?.lensDistortionLookupTable
                .map { $0.count / MemoryLayout<Float>.size },
            depthDelivered: photo.depthData != nil,
            depthDetail: photo.depthData.map {
                "type=\($0.depthDataType) accuracy=\($0.depthDataAccuracy.rawValue)"
            } ?? ""
        )
    }

    private nonisolated(unsafe) static var retained: ProbeDelegate?

    enum ProbeError: LocalizedError {
        case noDevice
        case cannotConfigure

        var errorDescription: String? {
            switch self {
            case .noDevice: return "no rear wide-angle camera (expected on a simulator)"
            case .cannotConfigure: return "the device rejected the probe configuration"
            }
        }
    }
}

private final class ProbeDelegate: NSObject, AVCapturePhotoCaptureDelegate {
    private let continuation: CheckedContinuation<AVCapturePhoto, Error>

    init(continuation: CheckedContinuation<AVCapturePhoto, Error>) {
        self.continuation = continuation
    }

    func photoOutput(
        _ output: AVCapturePhotoOutput,
        didFinishProcessingPhoto photo: AVCapturePhoto,
        error: Error?
    ) {
        if let error { continuation.resume(throwing: error) } else { continuation.resume(returning: photo) }
    }
}

private func hardwareIdentifier() -> String {
    var info = utsname()
    uname(&info)
    let raw = withUnsafePointer(to: &info.machine) {
        $0.withMemoryRebound(to: CChar.self, capacity: 1) { String(validatingUTF8: $0) }
    }
    return raw ?? UIDevice.current.model
}
