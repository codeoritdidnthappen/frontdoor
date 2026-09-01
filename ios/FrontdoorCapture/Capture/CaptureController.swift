import AVFoundation
import CoreMotion
import Foundation

/// Owns the AVFoundation session and the CoreMotion manager.
///
/// AVFoundation and CoreMotion only — no AR session is ever started (D-014, D-015). That is what
/// makes motion-derived scale unavailable rather than merely forbidden, and it is asserted by
/// Scripts/assert-no-arkit.sh at build time and by tests/test_ios_no_arkit.py in CI.
///
/// This type is the whole capture surface. Rendering (EPIC-03) observes it and adds views; it does
/// not reach into the session, so the capture path stays single.
@MainActor
final class CaptureController: ObservableObject {
    enum State: Equatable {
        case idle
        case ready
        case unavailable(CaptureUnavailable)
    }

    @Published private(set) var state: State = .idle
    /// Count of stills taken this launch. TICK-022 replaces this with a real capture record.
    @Published private(set) var photosTaken = 0

    let session = AVCaptureSession()

    private let motion = CMMotionManager()
    private let output = AVCapturePhotoOutput()
    private let sessionQueue = DispatchQueue(label: "com.frontdoor.capture.session")
    private var delegates: [PhotoCaptureDelegate] = []

    /// Fixed capture geometry: 1x main lens, no digital zoom, no crop (ARCHITECTURE.md section 4).
    /// The error budget is counted in pixels across the threshold rise, so the lens is not a choice.
    private static let lens: AVCaptureDevice.DeviceType = .builtInWideAngleCamera

    func start() async {
        guard motion.isDeviceMotionAvailable else {
            state = .unavailable(.motionUnavailable)
            return
        }
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            break
        case .notDetermined:
            guard await AVCaptureDevice.requestAccess(for: .video) else {
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

        if let failure = await configureSession() {
            state = .unavailable(failure)
            return
        }
        motion.startDeviceMotionUpdates()
        state = .ready
    }

    func stop() {
        motion.stopDeviceMotionUpdates()
        sessionQueue.async { [session] in
            if session.isRunning { session.stopRunning() }
        }
    }

    /// Takes one photo. TICK-022 onward attach intrinsics, gravity, depth and the sidecar; this
    /// stage claims nothing beyond "a still was produced".
    func capturePhoto() {
        guard case .ready = state else { return }
        let settings = AVCapturePhotoSettings()
        let token = UUID()
        let delegate = PhotoCaptureDelegate(token: token) { [weak self] finished in
            Task { @MainActor in
                self?.photosTaken += 1
                self?.delegates.removeAll { $0.token == finished }
            }
        }
        delegates.append(delegate)
        sessionQueue.async { [output] in
            output.capturePhoto(with: settings, delegate: delegate)
        }
    }

    private func configureSession() async -> CaptureUnavailable? {
        await withCheckedContinuation { continuation in
            sessionQueue.async { [session, output] in
                guard let device = AVCaptureDevice.default(
                    Self.lens, for: .video, position: .back
                ) else {
                    continuation.resume(returning: .noCaptureDevice)
                    return
                }
                session.beginConfiguration()
                session.sessionPreset = .photo
                defer { session.commitConfiguration() }

                do {
                    let input = try AVCaptureDeviceInput(device: device)
                    guard session.canAddInput(input), session.canAddOutput(output) else {
                        continuation.resume(
                            returning: .configurationFailed("the device rejected the photo input")
                        )
                        return
                    }
                    session.addInput(input)
                    session.addOutput(output)
                } catch {
                    continuation.resume(
                        returning: .configurationFailed(error.localizedDescription)
                    )
                    return
                }
                session.startRunning()
                continuation.resume(returning: nil)
            }
        }
    }
}

/// AVCapturePhotoOutput holds its delegate weakly, so one is kept alive per in-flight capture.
private final class PhotoCaptureDelegate: NSObject, AVCapturePhotoCaptureDelegate {
    let token: UUID
    private let onFinish: (UUID) -> Void

    init(token: UUID, onFinish: @escaping (UUID) -> Void) {
        self.token = token
        self.onFinish = onFinish
    }

    func photoOutput(
        _ output: AVCapturePhotoOutput,
        didFinishProcessingPhoto photo: AVCapturePhoto,
        error: Error?
    ) {
        onFinish(token)
    }
}
