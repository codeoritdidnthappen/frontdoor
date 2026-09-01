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
///
/// Every capability read here happens **after** `commitConfiguration()`. These properties reflect
/// committed session state, and reading them mid-transaction returns false on hardware that does
/// support them — which would make this spike confidently report the answer that triggers the
/// expensive ARKit fallback.
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
        var requestedDimensions: String
        var pixelDimensions: String
        var isFullResolution: Bool
        var calibrationRequested: Bool
        var calibrationDelivered: Bool
        /// Which channel answered. The distinction decides whether the ARKit fallback is warranted.
        var calibrationSource: String
        var intrinsics: String
        var referenceDimensions: String
        var distortionTableEntries: Int?
        var depthRequested: Bool
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
                    "  requested: \(c.requestedDimensions)",
                    "  delivered: \(c.pixelDimensions)  full-resolution=\(c.isFullResolution)",
                    "  calibration requested=\(c.calibrationRequested) delivered=\(c.calibrationDelivered)",
                    "  calibration source=\(c.calibrationSource)",
                    "  intrinsics: \(c.intrinsics)",
                    "  reference dimensions: \(c.referenceDimensions)",
                    "  distortion table entries: \(c.distortionTableEntries.map(String.init) ?? "none")",
                    "  depth requested=\(c.depthRequested) delivered=\(c.depthDelivered) \(c.depthDetail)",
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

    /// Bounds the capture so a denied or wedged camera reports rather than spinning forever.
    private static let captureTimeout = Duration.seconds(15)

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

        // Authorisation is a probe result, not a reason to hang. Without this an unauthorised
        // session starts, delivers no frames, and the capture callback never arrives.
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            break
        case .notDetermined:
            guard await AVCaptureDevice.requestAccess(for: .video) else {
                report.failure = "camera access denied, so no capture was attempted"
                return report
            }
        case .denied, .restricted:
            report.failure = "camera access denied or restricted, so no capture was attempted"
            return report
        @unknown default:
            report.failure = "camera authorisation is in an unknown state"
            return report
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
        guard
            let input = try? AVCaptureDeviceInput(device: device),
            session.canAddInput(input), session.canAddOutput(output)
        else {
            session.commitConfiguration()
            return LensReport(
                lens: label, available: true, calibrationSupported: false,
                depthSupported: false, maxPhotoDimensions: "could not configure"
            )
        }
        session.addInput(input)
        session.addOutput(output)
        session.commitConfiguration()

        // Depth must be enabled before calibration support is meaningful: Apple gates calibration
        // delivery behind depth or constituent-photo delivery. Both reads are post-commit.
        if output.isDepthDataDeliverySupported {
            session.beginConfiguration()
            output.isDepthDataDeliveryEnabled = true
            session.commitConfiguration()
        }

        // The format is the authority on what the sensor can produce; the output's current value
        // is only what has been asked for so far.
        let best = device.activeFormat.supportedMaxPhotoDimensions.last
        return LensReport(
            lens: label,
            available: true,
            calibrationSupported: output.isCameraCalibrationDataDeliverySupported,
            depthSupported: output.isDepthDataDeliverySupported,
            maxPhotoDimensions: best.map { "\($0.width)x\($0.height)" } ?? "unknown"
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
        session.commitConfiguration()

        // Everything below reads or writes committed state. Enabling depth needs its own
        // transaction, and calibration support is only meaningful once depth has been enabled.
        let sensorMax = device.activeFormat.supportedMaxPhotoDimensions.last
        session.beginConfiguration()
        if output.isDepthDataDeliverySupported { output.isDepthDataDeliveryEnabled = true }
        // Ask for the largest still the active format offers, so "full resolution" is a measured
        // claim rather than a default (D-014 rejects ARKit precisely for frame size).
        if let sensorMax { output.maxPhotoDimensions = sensorMax }
        session.commitConfiguration()

        session.startRunning()
        defer { session.stopRunning() }

        let settings = AVCapturePhotoSettings()
        if let sensorMax { settings.maxPhotoDimensions = sensorMax }
        let depthRequested = output.isDepthDataDeliverySupported
        if depthRequested { settings.isDepthDataDeliveryEnabled = true }
        let calibrationRequested = output.isCameraCalibrationDataDeliverySupported
        if calibrationRequested { settings.isCameraCalibrationDataDeliveryEnabled = true }

        let photo = try await capture(with: settings, from: output)

        // Read the channel the SHIPPED capture path reads, not the one that is easiest to ask for
        // (#149). CaptureController takes intrinsics from depthData.cameraCalibrationData, because
        // isCameraCalibrationDataDeliveryEnabled additionally needs two or more constituent devices
        // for virtual-device delivery (AVCapturePhotoOutput.h:1496) and D-014's fixed 1x lens rules
        // that out. Reporting only photo.cameraCalibrationData would print "not delivered" on a
        // device where the app is successfully extracting fx/fy/cx/cy — and this note's own
        // instructions make that reading the trigger for the ARKit fallback.
        //
        // Both channels are reported separately, because "no calibration anywhere" and "none via
        // the direct API, present via depth" are different answers with different consequences, and
        // only the first justifies abandoning D-015.
        let directCalibration = photo.cameraCalibrationData
        let depthCalibration = photo.depthData?.cameraCalibrationData
        let calibration = depthCalibration ?? directCalibration
        let matrix = calibration?.intrinsicMatrix
        let delivered = photo.resolvedSettings.photoDimensions
        return CaptureReport(
            lens: "builtInWideAngleCamera",
            requestedDimensions: sensorMax.map { "\($0.width)x\($0.height)" } ?? "device default",
            pixelDimensions: "\(delivered.width)x\(delivered.height)",
            isFullResolution: sensorMax.map {
                $0.width == delivered.width && $0.height == delivered.height
            } ?? false,
            calibrationRequested: calibrationRequested,
            calibrationDelivered: calibration != nil,
            calibrationSource: depthCalibration != nil
                ? "depthData.cameraCalibrationData (the channel the app uses)"
                : directCalibration != nil
                    ? "photo.cameraCalibrationData (direct; the app does not use this route)"
                    : "neither channel delivered calibration",
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
            depthRequested: depthRequested,
            depthDelivered: photo.depthData != nil,
            depthDetail: photo.depthData.map {
                "type=\($0.depthDataType) accuracy=\($0.depthDataAccuracy.rawValue)"
            } ?? ""
        )
    }

    /// One capture, bounded. The delegate is owned by this call rather than a shared slot, so two
    /// probes cannot deallocate each other's delegate and strand each other's continuation.
    private static func capture(
        with settings: AVCapturePhotoSettings,
        from output: AVCapturePhotoOutput
    ) async throws -> AVCapturePhoto {
        // Three things race to finish this capture: the photo delegate, the 15-second timeout, and
        // cancellation when the operator taps Done. A continuation may be resumed exactly once, and
        // resuming it twice is a crash, so the box settles the winner under a lock.
        //
        // It also holds the continuation itself rather than the delegate. onCancel can run before —
        // or during — the operation body, so a box keyed on the delegate has a window where
        // cancellation consumes the right to resume and then finds nothing to resume, leaving the
        // continuation permanently stranded. Recording the outcome and replaying it on attach
        // closes that window.
        //
        // The earlier shape raced the capture inside withThrowingTaskGroup. A task group does not
        // return until every child finishes, and cancelling a child suspended on a continuation
        // does not resume it, so the timeout fired on schedule and could never propagate (#150).
        let box = CaptureBox()
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                box.attach(continuation)
                let delegate = ProbeDelegate(box: box)
                box.retain(delegate)
                box.deadline = Task {
                    try? await Task.sleep(for: captureTimeout)
                    box.finish(.failure(ProbeError.timedOut))
                }
                output.capturePhoto(with: settings, delegate: delegate)
            }
        } onCancel: {
            box.finish(.failure(CancellationError()))
        }
    }

    /// AVCapturePhotoOutput holds its delegate weakly, so it has to be retained for the duration
    /// of one capture — but per call, never in a shared static.
    /// Owns the continuation, the delegate's lifetime and the timeout, and guarantees exactly one
    /// resume. AVCapturePhotoOutput holds its delegate weakly, so the box keeps it alive.
    final class CaptureBox: @unchecked Sendable {
        private let lock = NSLock()
        private var continuation: CheckedContinuation<AVCapturePhoto, Error>?
        private var pending: Result<AVCapturePhoto, Error>?
        private var finished = false
        private var delegate: AnyObject?
        private var _deadline: Task<Void, Never>?

        var deadline: Task<Void, Never>? {
            get { lock.lock(); defer { lock.unlock() }; return _deadline }
            set { lock.lock(); _deadline = newValue; lock.unlock() }
        }

        func retain(_ object: AnyObject) { lock.lock(); delegate = object; lock.unlock() }

        /// Attaches the continuation, replaying an outcome that arrived before it existed.
        func attach(_ continuation: CheckedContinuation<AVCapturePhoto, Error>) {
            lock.lock()
            if let pending, !finished {
                finished = true
                lock.unlock()
                continuation.resume(with: pending)
                return
            }
            self.continuation = continuation
            lock.unlock()
        }

        /// Finishes once. Later callers, and callers arriving before attach, are absorbed.
        func finish(_ result: Result<AVCapturePhoto, Error>) {
            lock.lock()
            if finished { lock.unlock(); return }
            // The deadline is cancelled on the first outcome either way. Returning early without
            // cancelling — the path taken when cancellation beats attach — leaves a live timer
            // holding the box for its full duration.
            let deadline = _deadline
            _deadline = nil
            guard let continuation else {
                if pending == nil { pending = result }
                lock.unlock()
                deadline?.cancel()
                return
            }
            finished = true
            self.continuation = nil
            lock.unlock()
            deadline?.cancel()
            continuation.resume(with: result)
        }
    }

    enum ProbeError: LocalizedError {
        case noDevice
        case cannotConfigure
        case timedOut

        var errorDescription: String? {
            switch self {
            case .noDevice: return "no rear wide-angle camera (expected on a simulator)"
            case .cannotConfigure: return "the device rejected the probe configuration"
            case .timedOut: return "the camera did not return a photo within 15 seconds"
            }
        }
    }
}

private final class ProbeDelegate: NSObject, AVCapturePhotoCaptureDelegate {
    private let box: CapabilityProbe.CaptureBox

    init(box: CapabilityProbe.CaptureBox) { self.box = box }

    func photoOutput(
        _ output: AVCapturePhotoOutput,
        didFinishProcessingPhoto photo: AVCapturePhoto,
        error: Error?
    ) {
        // The timeout or a cancellation may already have finished this; the box absorbs the loser.
        box.finish(error.map { .failure($0) } ?? .success(photo))
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
