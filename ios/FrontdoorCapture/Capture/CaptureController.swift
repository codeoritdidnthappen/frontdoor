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
    /// Spelled to match the sidecar example in ARCHITECTURE.md section 4. Derived from the raw
    /// value it would be "BuiltInWideAngleCamera", and anything filtering on the documented
    /// spelling would silently match nothing.
    static let lensName = "builtInWideAngleCamera"

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
        if failure != nil { motion.stopDeviceMotionUpdates() }
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
        // nil would mean the controller lost its device, which is not a zoom problem — reporting
        // it as "zoom was 0.00x" would send the operator after the wrong thing.
        guard let device else {
            lastCaptureError = CaptureUnavailable.noCaptureDevice.message
            return
        }
        let zoomFactor = Double(device.videoZoomFactor)
        let lens = Self.lensName
        // Sampled here, on the main actor, at the moment of the press — not inside the delegate
        // callback, which runs after the exposure and would describe a different instant.
        let gravity = motion.deviceMotion.map {
            GravitySample(x: $0.gravity.x, y: $0.gravity.y, z: $0.gravity.z)
        }
        let capturedAtShutter = Date()
        let sensor = Self.fullResolution(of: device)

        let token = UUID()
        let delegate = PhotoCaptureDelegate(token: token) { [weak self] finished, result in
            Task { @MainActor in
                guard let self else { return }
                switch result {
                case .success(let captured):
                    self.accept(
                        captured,
                        capturedAt: capturedAtShutter,
                        sensor: sensor,
                        gravity: gravity,
                        zoomFactor: zoomFactor,
                        lens: lens
                    )
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
        // Depth is the intrinsics carrier on a single lens; mirror the output's own state,
        // because enabling it here when the output has not is a hard error.
        settings.isDepthDataDeliveryEnabled = output.isDepthDataDeliveryEnabled
        // Where a device does offer calibration directly, take it as a second route. Setting this
        // when the output does not support it raises an uncatchable NSException, so it is gated at
        // the point of use rather than on a precondition proved elsewhere. Where neither route is
        // available the frame simply arrives without intrinsics, and validation refuses it with a
        // message naming that as the reason.
        if output.isCameraCalibrationDataDeliverySupported {
            settings.isCameraCalibrationDataDeliveryEnabled = true
        }
        sessionQueue.async { [output] in
            output.capturePhoto(with: settings, delegate: delegate)
        }
    }

    /// The largest still the configured camera can deliver. Read from the active format, and it
    /// is the same call `applyConfiguration` uses to request the size -- deliberately so. A
    /// request bound to one ceiling and a check bound to another reject every capture the moment
    /// they disagree, which is what happens if this reads `device.formats` instead: on a 48MP
    /// iPhone the device-wide maximum is a format the `.photo` session never selects, so every
    /// frame would be refused for being smaller than a size the camera was never asked for.
    ///
    /// max(by:) rather than `.last`: the array's ordering is not documented, and taking the wrong
    /// element here would cap the still below what the format can produce.
    static func maxPhotoDimensions(of device: AVCaptureDevice) -> CMVideoDimensions? {
        device.activeFormat.supportedMaxPhotoDimensions
            .max { Int($0.width) * Int($0.height) < Int($1.width) * Int($1.height) }
    }

    /// What TICK-022 AC3 compares the delivered frame against: proof the still was not cropped or
    /// downscaled relative to what the camera was configured to produce.
    ///
    /// It does not prove the active format is the device's best. A session that selected a
    /// lower-resolution format would pass this check. Choosing the format explicitly is not free
    /// -- depth delivery is what carries intrinsics to a single lens (D-015) and not every format
    /// supports it -- so which format `.photo` settles on is a question for #24's device work
    /// rather than something to guess at here.
    static func fullResolution(of device: AVCaptureDevice) -> SensorResolution? {
        maxPhotoDimensions(of: device)
            .map { SensorResolution(width: Int($0.width), height: Int($0.height)) }
    }

    /// Applies the rules that decide whether a frame is usable, then publishes or refuses.
    private func accept(
        _ captured: CapturedPhoto,
        capturedAt: Date,
        sensor: SensorResolution?,
        gravity: GravitySample?,
        zoomFactor: Double,
        lens: String
    ) {
        // Intrinsics ride in on the depth data (see applyConfiguration), with the photo's own
        // calibration kept as a fallback in case a future configuration can supply it directly.
        let calibration = captured.depthData?.cameraCalibrationData ?? captured.calibration
        let intrinsics = calibration.flatMap {
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
            capturedAt: capturedAt,
            pixelWidth: captured.pixelWidth,
            pixelHeight: captured.pixelHeight,
            sensor: sensor,
            intrinsics: intrinsics,
            hadCalibrationData: calibration != nil,
            gravity: gravity,
            deviceModel: CaptureValidation.hardwareIdentifier(),
            lens: lens,
            zoomFactor: zoomFactor,
            // Absence is recorded, never punished: depth is a comparison, so a frame without it
            // must still cost nothing (D-020, TICK-023).
            depth: DepthCapture.record(from: captured.depthData)
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
        if let maxDimensions = Self.maxPhotoDimensions(of: device) {
            output.maxPhotoDimensions = maxDimensions
        }

        // Depth delivery is how intrinsics reach a single-lens capture. Camera calibration data
        // cannot be requested directly here: AVCapturePhotoSettings.isCameraCalibrationDataDelivery
        // Enabled additionally requires two or more constituent devices selected for virtual-device
        // photo delivery (AVCapturePhotoOutput.h:1496), which D-014's fixed 1x wide lens rules out.
        // AVDepthData carries cameraCalibrationData with no such precondition, so enabling depth
        // delivery is what makes the frame measurable at all (D-015).
        //
        // Requested, not required. A device without a depth sensor still opens the camera: TICK-023
        // made the sidecar accept "depth": null precisely so that absence does not cost an
        // entrance, and refusing to start the session here would contradict that on the one phone
        // it was written for — Emily's iPhone 16 has no depth sensor, and a hard refusal leaves the
        // team with a single capture device.
        //
        // The guarantee worth keeping survives one layer down: CaptureValidation refuses any frame
        // that arrives without usable intrinsics, so an unmeasurable still is never recorded.
        // Refusing the whole session instead conflates "this frame is unusable" with "this device
        // is unusable", and only the first is knowable here.
        //
        // Enabling this reconfigures the render pipeline, so it must happen before startRunning.
        if output.isDepthDataDeliverySupported {
            output.isDepthDataDeliveryEnabled = true
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
    var depthData: AVDepthData?
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
            calibration: photo.cameraCalibrationData,
            depthData: photo.depthData
        )))
    }
}
