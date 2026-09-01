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

    @Published private(set) var state: State = .stopped
    @Published private(set) var photosTaken = 0
    /// Most recent still, held in memory only so the operator can see that capture worked.
    /// Nothing is written to disk here — the capture record is TICK-028.
    @Published private(set) var lastThumbnail: UIImage?

    let session = AVCaptureSession()

    private let motion = CMMotionManager()
    private let output = AVCapturePhotoOutput()
    private let sessionQueue = DispatchQueue(label: "com.frontdoor.capture.session")
    private var delegates: [PhotoCaptureDelegate] = []

    /// Fixed capture geometry: 1x main lens, no digital zoom, no crop (ARCHITECTURE.md section 4).
    private static let lens: AVCaptureDevice.DeviceType = .builtInWideAngleCamera

    // MARK: - Readiness, checkable before the camera is switched on

    var motionAvailable: Bool { motion.isDeviceMotionAvailable }

    var cameraAuthorization: AVAuthorizationStatus {
        AVCaptureDevice.authorizationStatus(for: .video)
    }

    /// Why capture could not start, checkable without starting it. Lets the home screen say what
    /// is wrong before the operator taps anything.
    var blockingReason: CaptureUnavailable? {
        if !motionAvailable { return .motionUnavailable }
        switch cameraAuthorization {
        case .denied: return .cameraDenied
        case .restricted: return .cameraRestricted
        default: return nil
        }
    }

    // MARK: - Lifecycle

    func start() async {
        guard state != .running else { return }
        state = .starting

        guard motionAvailable else {
            state = .unavailable(.motionUnavailable)
            return
        }
        switch cameraAuthorization {
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
        state = .running
    }

    /// Stops the camera and releases it. The operator can leave the viewfinder without killing
    /// the app, and the camera indicator goes out when they do.
    func stop() {
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

    // MARK: - Capture

    /// Takes one photo. TICK-022 onward attach intrinsics, gravity, depth and the sidecar; this
    /// stage claims nothing beyond "a still was produced", and shows it so that is checkable.
    func capturePhoto() {
        guard state == .running else { return }
        let token = UUID()
        let delegate = PhotoCaptureDelegate(token: token) { [weak self] finished, image in
            Task { @MainActor in
                guard let self else { return }
                self.photosTaken += 1
                if let image { self.lastThumbnail = image }
                self.delegates.removeAll { $0.token == finished }
            }
        }
        delegates.append(delegate)
        sessionQueue.async { [output] in
            output.capturePhoto(with: AVCapturePhotoSettings(), delegate: delegate)
        }
    }

    private func configureSession() async -> CaptureUnavailable? {
        await withCheckedContinuation { continuation in
            sessionQueue.async { [session, output] in
                if let failure = Self.applyConfiguration(to: session, output: output) {
                    continuation.resume(returning: failure)
                    return
                }
                // startRunning() must be outside beginConfiguration/commitConfiguration.
                // AVFoundation raises NSGenericException otherwise, and only on a device: the
                // simulator has no capture device, so configuration returns before this line.
                session.startRunning()
                continuation.resume(returning: nil)
            }
        }
    }

    /// Applies the whole configuration inside one begin/commit pair. Returns the reason it could
    /// not be applied, or nil. Every exit path commits, via `defer`.
    private static func applyConfiguration(
        to session: AVCaptureSession,
        output: AVCapturePhotoOutput
    ) -> CaptureUnavailable? {
        guard let device = AVCaptureDevice.default(lens, for: .video, position: .back) else {
            return .noCaptureDevice
        }
        session.beginConfiguration()
        defer { session.commitConfiguration() }
        session.sessionPreset = .photo

        guard session.inputs.isEmpty, session.outputs.isEmpty else { return nil }

        do {
            let input = try AVCaptureDeviceInput(device: device)
            guard session.canAddInput(input), session.canAddOutput(output) else {
                return .configurationFailed("the device rejected the photo input")
            }
            session.addInput(input)
            session.addOutput(output)
        } catch {
            return .configurationFailed(error.localizedDescription)
        }
        return nil
    }
}

/// AVCapturePhotoOutput holds its delegate weakly, so one is kept alive per in-flight capture.
private final class PhotoCaptureDelegate: NSObject, AVCapturePhotoCaptureDelegate {
    let token: UUID
    private let onFinish: (UUID, UIImage?) -> Void

    init(token: UUID, onFinish: @escaping (UUID, UIImage?) -> Void) {
        self.token = token
        self.onFinish = onFinish
    }

    func photoOutput(
        _ output: AVCapturePhotoOutput,
        didFinishProcessingPhoto photo: AVCapturePhoto,
        error: Error?
    ) {
        let image = photo.fileDataRepresentation().flatMap(UIImage.init(data:))
        onFinish(token, image)
    }
}
