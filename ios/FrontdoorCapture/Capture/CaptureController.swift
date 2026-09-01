import AVFoundation
import CoreMotion
import SwiftUI
import UIKit

/// Owns the AVFoundation session and the CoreMotion manager.
///
/// AVFoundation and CoreMotion only — no AR session is ever started (D-014, D-015). That is what
/// makes motion-derived scale unavailable rather than merely forbidden, and it is asserted by
/// Scripts/assert-no-arkit.sh at build time and tests/test_ios_no_arkit.py in CI.
///
/// This type is the whole capture surface. Rendering (EPIC-03) observes it and adds views; it does
/// not reach into the session, so the capture path stays single.
@MainActor
final class CaptureController: ObservableObject {
    enum State: Equatable {
        case stopped
        case starting
        case running
        case unavailable(CaptureUnavailable)
    }

    /// What the instrument can do right now, sampled rather than computed on demand.
    ///
    /// Authorisation changes while the app is backgrounded — the operator goes to Settings and
    /// grants the camera — and a computed property gives SwiftUI nothing to react to. This is
    /// published and re-sampled on foreground, so the home screen cannot go stale.
    struct Readiness: Equatable {
        var cameraAuthorization: AVAuthorizationStatus = .notDetermined
        var motionAvailable: Bool = false

        var blockingReason: CaptureUnavailable? {
            if !motionAvailable { return .motionUnavailable }
            switch cameraAuthorization {
            case .denied: return .cameraDenied
            case .restricted: return .cameraRestricted
            default: return nil
            }
        }
    }

    @Published private(set) var state: State = .stopped
    @Published private(set) var readiness = Readiness()
    @Published private(set) var photosTaken = 0
    /// Most recent still, held in memory only so the operator can see that capture worked.
    /// Nothing is written to disk here — the capture record is TICK-028.
    @Published private(set) var lastThumbnail: UIImage?
    /// Set when a shutter press produced no image, or produced one that was refused. Cleared by
    /// the next success.
    @Published private(set) var lastCaptureError: String?
    /// The method's legal input for the most recent accepted capture (D-015). Held in memory only;
    /// writing it to a sidecar is TICK-028.
    @Published private(set) var lastRecord: CaptureRecord?

    let session = AVCaptureSession()

    private let motion = CMMotionManager()
    private let output = AVCapturePhotoOutput()
    /// Retained so the zoom factor can be read back at the shutter rather than assumed.
    private var device: AVCaptureDevice?
    private let sessionQueue = DispatchQueue(label: "com.frontdoor.capture.session")
    private var delegates: [PhotoCaptureDelegate] = []
    private var observers: [NSObjectProtocol] = []
    /// Invalidates an in-flight `start()` when `stop()` or another `start()` supersedes it.
    private var startGeneration = 0

    /// Fixed capture geometry: 1x main lens, no digital zoom, no crop (ARCHITECTURE.md section 4).
    private static let lens: AVCaptureDevice.DeviceType = .builtInWideAngleCamera

    init() {
        refreshReadiness()
        observeSession()
    }

    deinit {
        observers.forEach(NotificationCenter.default.removeObserver)
        motion.stopDeviceMotionUpdates()
    }

    // MARK: - Readiness

    /// Re-samples what the system will allow. Call on foreground: the operator may have changed
    /// camera permission in Settings while the app was away.
    func refreshReadiness() {
        readiness = Readiness(
            cameraAuthorization: AVCaptureDevice.authorizationStatus(for: .video),
            motionAvailable: motion.isDeviceMotionAvailable
        )
    }

    // MARK: - Lifecycle

    func start() async {
        guard state != .running else { return }
        startGeneration += 1
        let generation = startGeneration
        state = .starting
        refreshReadiness()

        guard readiness.motionAvailable else {
            state = .unavailable(.motionUnavailable)
            return
        }
        switch readiness.cameraAuthorization {
        case .authorized:
            break
        case .notDetermined:
            let granted = await AVCaptureDevice.requestAccess(for: .video)
            guard generation == startGeneration else { return }
            refreshReadiness()
            guard granted else {
                state = .unavailable(.cameraDenied)
                return
            }
        case .denied:
            state = .unavailable(.cameraDenied)
            return
        case .restricted:
            state = .unavailable(.cameraRestricted)
            return
        @unknown default:
            state = .unavailable(.cameraDenied)
            return
        }

        // Gravity is sampled at the shutter, but device motion needs time to settle, so updates
        // run for as long as the viewfinder is open rather than being started per capture.
        if !motion.isDeviceMotionActive {
            motion.deviceMotionUpdateInterval = 1.0 / 60.0
            motion.startDeviceMotionUpdates(using: .xArbitraryZVertical)
        }

        let failure = await configureSession()
        // stop(), or another start(), ran while we were configuring. Committing .running here
        // would claim a live session over a stopped one, and the guard above would then refuse
        // every future start.
        guard generation == startGeneration else { return }
        if let failure {
            state = .unavailable(failure)
            return
        }
        state = .running
    }

    /// Stops the camera and releases it. The operator can leave the viewfinder without killing
    /// the app, and the camera indicator goes out when they do.
    func stop() {
        startGeneration += 1
        delegates.removeAll()
        motion.stopDeviceMotionUpdates()
        sessionQueue.async { [session] in
            if session.isRunning { session.stopRunning() }
        }
        state = .stopped
    }

    func openSystemSettings() {
        guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
        UIApplication.shared.open(url)
    }

    // MARK: - Interruption

    /// A capture session can be taken away — a call, another app claiming the camera, Split View.
    /// Without these the UI keeps drawing a viewfinder over a dead session and the shutter
    /// silently does nothing.
    private func observeSession() {
        let center = NotificationCenter.default
        let onMain = OperationQueue.main

        observers.append(center.addObserver(
            forName: AVCaptureSession.wasInterruptedNotification, object: session, queue: onMain
        ) { [weak self] note in
            let reason = Self.describe(note)
            Task { @MainActor in self?.state = .unavailable(.interrupted(reason)) }
        })

        observers.append(center.addObserver(
            forName: AVCaptureSession.interruptionEndedNotification, object: session, queue: onMain
        ) { [weak self] _ in
            Task { @MainActor in
                guard let self, case .unavailable(.interrupted) = self.state else { return }
                self.state = .stopped
                await self.start()
            }
        })

        observers.append(center.addObserver(
            forName: AVCaptureSession.runtimeErrorNotification, object: session, queue: onMain
        ) { [weak self] note in
            let error = note.userInfo?[AVCaptureSessionErrorKey] as? NSError
            let detail = error?.localizedDescription ?? "unknown runtime error"
            Task { @MainActor in self?.state = .unavailable(.configurationFailed(detail)) }
        })
    }

    private static func describe(_ note: Notification) -> String {
        guard
            let raw = note.userInfo?[AVCaptureSessionInterruptionReasonKey] as? Int,
            let reason = AVCaptureSession.InterruptionReason(rawValue: raw)
        else { return "the camera became unavailable" }

        switch reason {
        case .videoDeviceNotAvailableInBackground: return "the app moved to the background"
        case .audioDeviceInUseByAnotherClient, .videoDeviceInUseByAnotherClient:
            return "another app is using the camera"
        case .videoDeviceNotAvailableWithMultipleForegroundApps:
            return "the camera is unavailable in this multitasking mode"
        case .videoDeviceNotAvailableDueToSystemPressure:
            return "the system throttled the camera"
        @unknown default: return "the camera became unavailable"
        }
    }

    // MARK: - Capture

    /// Takes one photo and, if the frame carries everything the method legally needs, publishes a
    /// `CaptureRecord`. A frame missing intrinsics or taken at the wrong zoom is refused rather
    /// than saved: an unusable still that looks saved is worse than a visible failure.
    func capturePhoto() {
        guard state == .running else { return }
        let zoomFactor = Double(device?.videoZoomFactor ?? 0)
        let lens = Self.lens.rawValue.replacingOccurrences(
            of: "AVCaptureDeviceType", with: ""
        )
        // Sampled here, on the main actor, at the moment of the press — not inside the delegate
        // callback, which runs after the exposure and would describe a different instant.
        let gravity = motion.deviceMotion.map {
            GravitySample(x: $0.gravity.x, y: $0.gravity.y, z: $0.gravity.z)
        }

        let token = UUID()
        let delegate = PhotoCaptureDelegate(token: token) { [weak self] finished, result in
            Task { @MainActor in
                guard let self else { return }
                switch result {
                case .success(let captured):
                    self.accept(captured, gravity: gravity, zoomFactor: zoomFactor, lens: lens)
                case .failure(let message):
                    // Deliberately does not increment. A count that rises on failure is worse
                    // than no count: it tells the operator a still exists when none does.
                    self.lastCaptureError = message
                }
                self.delegates.removeAll { $0.token == finished }
            }
        }
        delegates.append(delegate)

        let settings = AVCapturePhotoSettings()
        settings.maxPhotoDimensions = output.maxPhotoDimensions
        // Only ever set when configuration proved the precondition; see applyConfiguration.
        settings.isCameraCalibrationDataDeliveryEnabled = true
        sessionQueue.async { [output] in
            output.capturePhoto(with: settings, delegate: delegate)
        }
    }

    /// Applies the rules that decide whether a frame is usable, then publishes or refuses.
    private func accept(
        _ captured: CapturedPhoto,
        gravity: GravitySample?,
        zoomFactor: Double,
        lens: String
    ) {
        let intrinsics = captured.calibration.flatMap {
            CameraIntrinsics.from(
                matrix: $0.intrinsicMatrix,
                referenceDimensions: $0.intrinsicMatrixReferenceDimensions,
                distortionTable: $0.lensDistortionLookupTable,
                distortionCenter: $0.lensDistortionCenter,
                pixelWidth: captured.pixelWidth,
                pixelHeight: captured.pixelHeight
            )
        }

        switch CaptureValidation.record(
            pixelWidth: captured.pixelWidth,
            pixelHeight: captured.pixelHeight,
            intrinsics: intrinsics,
            hadCalibrationData: captured.calibration != nil,
            gravity: gravity,
            deviceModel: CaptureValidation.hardwareIdentifier(),
            lens: lens,
            zoomFactor: zoomFactor
        ) {
        case .success(let record):
            photosTaken += 1
            lastThumbnail = captured.image
            lastRecord = record
            lastCaptureError = nil
        case .failure(let rejection):
            lastCaptureError = rejection.message
        }
    }

    private func configureSession() async -> CaptureUnavailable? {
        let outcome: Result<AVCaptureDevice, CaptureUnavailable> = await withCheckedContinuation {
            continuation in
            sessionQueue.async { [session, output] in
                let result = Self.applyConfiguration(to: session, output: output)
                if case .success = result {
                    // startRunning() must be outside beginConfiguration/commitConfiguration.
                    // AVFoundation raises NSGenericException otherwise, and only on a device: the
                    // simulator has no capture device, so configuration returns before this line.
                    session.startRunning()
                }
                continuation.resume(returning: result)
            }
        }
        switch outcome {
        case .success(let configured):
            device = configured
            return nil
        case .failure(let reason):
            return reason
        }
    }

    /// Applies the whole configuration inside one begin/commit pair. Every exit path commits, via
    /// `defer`.
    private static func applyConfiguration(
        to session: AVCaptureSession,
        output: AVCapturePhotoOutput
    ) -> Result<AVCaptureDevice, CaptureUnavailable> {
        guard let device = AVCaptureDevice.default(lens, for: .video, position: .back) else {
            return .failure(.noCaptureDevice)
        }
        session.beginConfiguration()
        defer { session.commitConfiguration() }
        session.sessionPreset = .photo

        if session.inputs.isEmpty, session.outputs.isEmpty {
            do {
                let input = try AVCaptureDeviceInput(device: device)
                guard session.canAddInput(input), session.canAddOutput(output) else {
                    return .failure(.configurationFailed("the device rejected the photo input"))
                }
                session.addInput(input)
                session.addOutput(output)
            } catch {
                return .failure(.configurationFailed(error.localizedDescription))
            }
        }

        // Full sensor resolution. Without this the output silently caps at a smaller size, and the
        // intrinsics would then describe a grid the still does not have.
        if let maxDimensions = device.activeFormat.supportedMaxPhotoDimensions.last {
            output.maxPhotoDimensions = maxDimensions
        }

        // Intrinsics are the blocking problem, and the constraint is the API, not the hardware.
        // AVCapturePhotoSettings.isCameraCalibrationDataDeliveryEnabled may only be set when the
        // output supports it AND two or more devices are selected for virtual-device constituent
        // photo delivery (AVCapturePhotoOutput.h:1496). D-014 pins capture to the single 1x
        // builtInWideAngleCamera, so that precondition can never hold here, and setting the flag
        // anyway raises an uncatchable exception.
        //
        // Detected rather than attempted: a still without intrinsics is unusable by every arm
        // (D-015), so the session refuses to start rather than letting an operator collect frames
        // that cannot be measured. This is R-9, and it is resolved in TICK-023 (#27), where depth
        // delivery carries AVDepthData.cameraCalibrationData on the same single lens.
        let constituents = device.constituentDevices.count
        guard output.isCameraCalibrationDataDeliverySupported, constituents >= 2 else {
            return .failure(.calibrationUnavailable)
        }

        // 1x, no digital zoom, no crop (D-014). Pinned rather than assumed: the system can restore
        // a previous zoom, and a cropped frame silently invalidates the intrinsics beside it.
        do {
            try device.lockForConfiguration()
            device.videoZoomFactor = 1.0
            device.unlockForConfiguration()
        } catch {
            return .failure(.configurationFailed("zoom could not be pinned to 1x: \(error.localizedDescription)"))
        }

        return .success(device)
    }
}

/// What one finished exposure yielded, before any judgement about whether it is usable.
private struct CapturedPhoto {
    var image: UIImage
    var pixelWidth: Int
    var pixelHeight: Int
    var calibration: AVCameraCalibrationData?
}

/// AVCapturePhotoOutput holds its delegate weakly, so one is kept alive per in-flight capture.
private final class PhotoCaptureDelegate: NSObject, AVCapturePhotoCaptureDelegate {
    enum Result {
        case success(CapturedPhoto)
        case failure(String)
    }

    let token: UUID
    private let onFinish: (UUID, Result) -> Void

    init(token: UUID, onFinish: @escaping (UUID, Result) -> Void) {
        self.token = token
        self.onFinish = onFinish
    }

    func photoOutput(
        _ output: AVCapturePhotoOutput,
        didFinishProcessingPhoto photo: AVCapturePhoto,
        error: Error?
    ) {
        if let error {
            onFinish(token, .failure(error.localizedDescription))
            return
        }
        guard let image = photo.fileDataRepresentation().flatMap(UIImage.init(data:)) else {
            onFinish(token, .failure("the camera returned no image data"))
            return
        }
        let dimensions = photo.resolvedSettings.photoDimensions
        onFinish(token, .success(CapturedPhoto(
            image: image,
            pixelWidth: Int(dimensions.width),
            pixelHeight: Int(dimensions.height),
            calibration: photo.cameraCalibrationData
        )))
    }
}
