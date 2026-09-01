import AVFoundation
import CoreMotion
import SwiftUI
import UIKit
import simd

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
    /// Set when a shutter press produced no image, or produced one the method cannot use.
    /// Cleared by the next success.
    @Published private(set) var lastCaptureError: String?
    /// Records accepted this session. TICK-028 writes these to sidecars; nothing is persisted yet.
    @Published private(set) var records: [CaptureRecord] = []

    let session = AVCaptureSession()

    private let motion = CMMotionManager()
    private let output = AVCapturePhotoOutput()
    private let sessionQueue = DispatchQueue(label: "com.frontdoor.capture.session")
    private var delegates: [PhotoCaptureDelegate] = []
    private var observers: [NSObjectProtocol] = []
    /// Invalidates an in-flight `start()` when `stop()` or another `start()` supersedes it.
    private var startGeneration = 0
    /// Sensor maximum for the active format, so "full resolution" is a comparison not an
    /// assumption. Set when the session is configured.
    private var sensorDimensions: (width: Int, height: Int)?
    private var activeDevice: AVCaptureDevice?

    /// Fixed capture geometry: 1x main lens, no digital zoom, no crop (ARCHITECTURE.md section 4).
    private static let lens: AVCaptureDevice.DeviceType = .builtInWideAngleCamera

    init() {
        refreshReadiness()
        observeSession()
    }

    deinit {
        observers.forEach(NotificationCenter.default.removeObserver)
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

        let failure = await configureSession()
        // stop(), or another start(), ran while we were configuring. Committing .running here
        // would claim a live session over a stopped one, and the guard above would then refuse
        // every future start.
        guard generation == startGeneration else { return }
        if let failure {
            state = .unavailable(failure)
            return
        }
        // Started only now that something reads it: capturePhoto() samples gravity at the shutter.
        motion.startDeviceMotionUpdates()
        state = .running
    }

    /// Stops the camera and releases it. The operator can leave the viewfinder without killing
    /// the app, and the camera indicator goes out when they do.
    func stop() {
        motion.stopDeviceMotionUpdates()
        startGeneration += 1
        delegates.removeAll()
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

    /// Takes one photo. TICK-022 onward attach intrinsics, gravity, depth and the sidecar; this
    /// stage claims nothing beyond "a still was produced", and shows it so that is checkable.
    func capturePhoto() {
        guard state == .running else { return }
        // Read gravity now, not in the completion: the vector must describe the instant of
        // capture, and the completion arrives long enough afterwards for the phone to have moved.
        let gravityAtShutter = motion.deviceMotion.map {
            SIMD3<Double>($0.gravity.x, $0.gravity.y, $0.gravity.z)
        }
        let zoomAtShutter = activeDevice.map { Double($0.videoZoomFactor) } ?? .nan
        // Same instant as gravity: the completion fires after encoding and is the wrong clock
        // for captured_at (ground truth binds at the shutter press).
        let capturedAtShutter = Date()

        let token = UUID()
        let delegate = PhotoCaptureDelegate(
            token: token, capturedAt: capturedAtShutter
        ) { [weak self] finished, result in
            Task { @MainActor in
                guard let self else { return }
                switch result {
                case .success(let capture):
                    self.accept(capture, zoom: zoomAtShutter, gravity: gravityAtShutter)
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
        if let sensorDimensions {
            settings.maxPhotoDimensions = CMVideoDimensions(
                width: Int32(sensorDimensions.width), height: Int32(sensorDimensions.height)
            )
        }
        if output.isCameraCalibrationDataDeliverySupported {
            settings.isCameraCalibrationDataDeliveryEnabled = true
        }
        sessionQueue.async { [output] in
            output.capturePhoto(with: settings, delegate: delegate)
        }
    }

    /// A frame is kept only if it carries everything the method needs. Anything else is discarded
    /// with a reason, because a record that looks complete and is not corrupts the dataset far
    /// more expensively than a missing one.
    private func accept(_ capture: CapturedFrame, zoom: Double, gravity: SIMD3<Double>?) {
        if let rejection = CaptureValidator.rejection(
            zoomFactor: zoom,
            intrinsics: capture.intrinsics,
            gravity: gravity,
            deliveredWidth: capture.pixelWidth,
            deliveredHeight: capture.pixelHeight,
            sensorWidth: sensorDimensions?.width,
            sensorHeight: sensorDimensions?.height
        ) {
            lastCaptureError = rejection.message
            return
        }
        guard let intrinsics = capture.intrinsics, let gravity else { return }

        records.append(
            CaptureRecord(
                captureId: UUID(),
                capturedAt: capture.timestamp,
                deviceModel: Self.hardwareIdentifier(),
                lens: AVCaptureDevice.DeviceType.builtInWideAngleCamera.rawValue,
                pixelWidth: capture.pixelWidth,
                pixelHeight: capture.pixelHeight,
                intrinsics: intrinsics,
                gravity: gravity
            )
        )
        photosTaken += 1
        lastThumbnail = capture.image
        lastCaptureError = nil
    }

    static func hardwareIdentifier() -> String {
        var info = utsname()
        uname(&info)
        let raw = withUnsafePointer(to: &info.machine) {
            $0.withMemoryRebound(to: CChar.self, capacity: 1) { String(validatingUTF8: $0) }
        }
        return raw ?? UIDevice.current.model
    }

    private func configureSession() async -> CaptureUnavailable? {
        let outcome = await withCheckedContinuation { continuation in
            sessionQueue.async { [session, output] in
                let result = Self.applyConfiguration(to: session, output: output)
                if case .failure(let reason) = result {
                    continuation.resume(returning: result)
                    _ = reason
                    return
                }
                // startRunning() must be outside beginConfiguration/commitConfiguration.
                // AVFoundation raises NSGenericException otherwise, and only on a device: the
                // simulator has no capture device, so configuration returns before this line.
                session.startRunning()
                continuation.resume(returning: result)
            }
        }
        switch outcome {
        case .failure(let reason):
            return reason
        case .success(let device, let dimensions):
            activeDevice = device
            sensorDimensions = dimensions
            return nil
        }
    }

    enum ConfigurationOutcome {
        case success(device: AVCaptureDevice, dimensions: (width: Int, height: Int)?)
        case failure(CaptureUnavailable)
    }

    /// Applies the whole configuration inside one begin/commit pair, then pins zoom and enables
    /// calibration delivery in a second transaction — those reads are only meaningful once the
    /// first is committed.
    private static func applyConfiguration(
        to session: AVCaptureSession,
        output: AVCapturePhotoOutput
    ) -> ConfigurationOutcome {
        guard let device = AVCaptureDevice.default(lens, for: .video, position: .back) else {
            return .failure(.noCaptureDevice)
        }

        if session.inputs.isEmpty, session.outputs.isEmpty {
            session.beginConfiguration()
            session.sessionPreset = .photo
            do {
                let input = try AVCaptureDeviceInput(device: device)
                guard session.canAddInput(input), session.canAddOutput(output) else {
                    session.commitConfiguration()
                    return .failure(.configurationFailed("the device rejected the photo input"))
                }
                session.addInput(input)
                session.addOutput(output)
            } catch {
                session.commitConfiguration()
                return .failure(.configurationFailed(error.localizedDescription))
            }
            session.commitConfiguration()
        }

        // D-014 fixes capture geometry: 1x main lens, no digital zoom, no crop. Pinned here so a
        // zoomed frame cannot be produced at all, rather than only rejected afterwards.
        do {
            try device.lockForConfiguration()
            device.videoZoomFactor = 1.0
            device.unlockForConfiguration()
        } catch {
            return .failure(.configurationFailed("could not pin zoom to 1x: \(error.localizedDescription)"))
        }

        let sensorMax = device.activeFormat.supportedMaxPhotoDimensions.last
        session.beginConfiguration()
        if let sensorMax { output.maxPhotoDimensions = sensorMax }
        session.commitConfiguration()

        return .success(
            device: device,
            dimensions: sensorMax.map { (width: Int($0.width), height: Int($0.height)) }
        )
    }
}

/// One accepted frame plus everything the method is allowed to consume from it (D-015).
struct CapturedFrame {
    var image: UIImage
    var timestamp: Date
    var pixelWidth: Int
    var pixelHeight: Int
    var intrinsics: Intrinsics?
}

/// AVCapturePhotoOutput holds its delegate weakly, so one is kept alive per in-flight capture.
private final class PhotoCaptureDelegate: NSObject, AVCapturePhotoCaptureDelegate {
    enum Result {
        case success(CapturedFrame)
        case failure(String)
    }

    let token: UUID
    private let capturedAt: Date
    private let onFinish: (UUID, Result) -> Void

    init(token: UUID, capturedAt: Date, onFinish: @escaping (UUID, Result) -> Void) {
        self.token = token
        self.capturedAt = capturedAt
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
        let calibration = photo.cameraCalibrationData
        let intrinsics = calibration.map { data -> Intrinsics in
            let m = data.intrinsicMatrix
            return Intrinsics(
                fx: Double(m.columns.0.x),
                fy: Double(m.columns.1.y),
                cx: Double(m.columns.2.x),
                cy: Double(m.columns.2.y),
                referenceWidth: Int(data.intrinsicMatrixReferenceDimensions.width),
                referenceHeight: Int(data.intrinsicMatrixReferenceDimensions.height),
                distortionLookupTable: Intrinsics.lookupTable(
                    fromPacked: data.lensDistortionLookupTable
                )
            )
        }
        let dims = photo.resolvedSettings.photoDimensions
        onFinish(token, .success(CapturedFrame(
            image: image,
            timestamp: capturedAt,
            pixelWidth: Int(dims.width),
            pixelHeight: Int(dims.height),
            intrinsics: intrinsics
        )))
    }
}
