import AVFoundation
import CoreMotion
import Network
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

    /// Fixed capture geometry: the 1x main lens, no digital zoom, no crop (D-014).
    ///
    /// Reached through builtInDualWideCamera rather than builtInWideAngleCamera, on the evidence
    /// of TICK-020's probe run on iPhone17,3 and iPhone16,2. Both report depth=false on the bare
    /// wide camera, and depthData.cameraCalibrationData is the only channel that delivers
    /// intrinsics -- direct delivery needs two constituent devices, which a single physical lens
    /// cannot offer. So the documented device type can never produce a measurable frame on either
    /// team phone, while the dual-wide does: fx=2792 fy=2792, reference dimensions matching the
    /// still, and a 42-entry distortion table.
    ///
    /// The optics D-014 fixes are unchanged. builtInDualWideCamera is ultra-wide plus wide, and at
    /// its switch-over factor the main lens is the one taking the picture -- fx=2792 on a
    /// 4032-wide frame is the ~24mm main lens, nowhere near the ultra-wide's ~1456.
    private static let lens: AVCaptureDevice.DeviceType = .builtInDualWideCamera

    /// Fallback for a device with no dual-wide. It cannot deliver intrinsics on either phone
    /// tested, so a capture will be refused rather than silently recorded without them -- which is
    /// the correct outcome, not a workaround.
    private static let fallbackLens: AVCaptureDevice.DeviceType = .builtInWideAngleCamera

    /// Spelled to match the sidecar example in ARCHITECTURE.md section 4. Derived from the raw
    /// value it would be "BuiltInWideAngleCamera", and anything filtering on the documented
    /// spelling would silently match nothing.
    static let lensName = "builtInWideAngleCamera"

    /// The device type actually opened, as a string for the record. `lensName` is the optics;
    /// this is the door they were reached through, and the two differ on both team phones.
    static func deviceName(for device: AVCaptureDevice) -> String {
        deviceName(fromRawValue: device.deviceType.rawValue)
    }

    /// Split out from the device so a test can reach it. An AVCaptureDevice cannot be constructed
    /// in a unit test, so the previous test re-implemented the transform and asserted against its
    /// own copy -- which is the mistake #154 was filed for, and it passed while the real function
    /// was wrong.
    static func deviceName(fromRawValue rawValue: String) -> String {
        // Stripping the prefix alone yields "BuiltInDualWideCamera" with a capital B, while the
        // schema, ARCHITECTURE section 4 and every document spell it "builtInDualWideCamera".
        // The same trap `lensName` has a comment about, walked into again -- and invisible to the
        // tests, which hardcode the lowercase string on both sides of the assertion.
        let stripped = rawValue.replacingOccurrences(of: "AVCaptureDeviceType", with: "")
        guard let first = stripped.first else { return stripped }
        return first.lowercased() + stripped.dropFirst()
    }

    /// The zoom factor at which the 1x main lens is the one exposing.
    ///
    /// On a virtual device the scale is relative to its WIDEST constituent, so 1.0 selects the
    /// ultra-wide and the main lens sits at the first switch-over point -- 2.00 on both team
    /// phones. Pinning the literal number 1.0 here would pin the wrong glass: ~120 degrees of
    /// barrel distortion, while every check in the app still reported 1x. A physical wide device
    /// publishes no switch-over factors and is already the main lens at 1.0.
    static func mainLensZoomFactor(for device: AVCaptureDevice) -> Double {
        device.virtualDeviceSwitchOverVideoZoomFactors.first?.doubleValue ?? 1.0
    }

    init() {
        refreshReadiness()
        // A cold launch fires no scenePhase change, so without this the count reads zero after
        // exactly the event AC2 is about -- termination or a restart -- while the captures sit in
        // Documents. It corrected itself on the next background-and-return, which made it look
        // imagined rather than wrong.
        refreshPendingUploads()
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

    /// The entrance and conditions every capture is bound to. Set before the viewfinder opens and
    /// editable from it; a shutter press with it missing is refused rather than saved without
    /// ground truth (TICK-024, D-018).
    /// Which contract captures are written against (D-034). Screening is what the app opens into,
    /// because it is the protocol the field is running (docs/capture-protocol.md); metrology stays
    /// reachable rather than deleted, because whether it is alive is an open question (A-3, #67).
    @Published var captureMode: CaptureMode = .default

    @Published var subject: CaptureSubject?

    /// A frame that passed validation and is waiting for its six ROI points (TICK-026).
    ///
    /// It is not a capture yet. `photosTaken` does not count it and `lastRecord` does not hold it:
    /// Arm A measures from the taps, so a frame without them is unmeasurable, and a count that
    /// rose here would tell the operator an entrance was covered when nothing usable exists.
    @Published var pendingReview: PendingReview?

    /// Takes one photo and, if the frame carries everything the method legally needs, publishes a
    /// `CaptureRecord`. A frame missing intrinsics or taken at the wrong zoom is refused rather
    /// than saved: an unusable still that looks saved is worse than a visible failure.
    func capturePhoto() {
        guard state == .running else { return }
        guard let subject else {
            lastCaptureError = CaptureUnavailable.noSubject.message
            return
        }
        // nil would mean the controller lost its device, which is not a zoom problem — reporting
        // it as "zoom was 0.00x" would send the operator after the wrong thing.
        guard let device else {
            lastCaptureError = CaptureUnavailable.noCaptureDevice.message
            return
        }
        let zoomFactor = Double(device.videoZoomFactor)
        // Read from the device, not assumed: what "1x main lens" means as a number differs
        // between a physical wide camera and the dual-wide virtual device.
        let mainLensZoom = Self.mainLensZoomFactor(for: device)
        let lens = Self.lensName
        let captureDevice = Self.deviceName(for: device)
        let captureId = UUID().uuidString
        // Sampled here, on the main actor, at the moment of the press — not inside the delegate
        // callback, which runs after the exposure and would describe a different instant.
        let gravity = motion.deviceMotion.map {
            GravitySample(x: $0.gravity.x, y: $0.gravity.y, z: $0.gravity.z)
        }
        // Sampled here for the same reason gravity is: the delegate callback arrives after the
        // exposure, and a timestamp taken there describes when processing finished rather than when
        // the shutter fired (#163).
        let capturedAt = CaptureValidation.timestamp(for: Date())
        // The SENSOR's maximum, read from the active format — not output.maxPhotoDimensions, which
        // is the value we requested. Comparing the delivered frame against our own request is
        // tautological: it passes whenever the request was honoured, including when the request
        // itself was below the sensor maximum because applyConfiguration could not read it or a
        // reconfiguration lowered it. That is precisely the case the check exists to catch.
        let sensorMax = device.activeFormat.supportedMaxPhotoDimensions.last

        let token = UUID()
        let delegate = PhotoCaptureDelegate(token: token) { [weak self] finished, result in
            Task { @MainActor in
                guard let self else { return }
                switch result {
                case .success(let captured):
                    self.accept(
                        captured,
                        subject: subject, gravity: gravity, zoomFactor: zoomFactor,
                        mainLensZoom: mainLensZoom, lens: lens, captureDevice: captureDevice,
                        captureId: captureId,
                        capturedAt: capturedAt, sensorMax: sensorMax
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
        // The readiness decision above was made on the main actor; the capture happens here, later,
        // on the session queue. In that window the session can stop or be reconfigured — an
        // incoming call, another app taking the camera, stop() racing the shutter — and calling
        // capturePhoto with no active video connection raises NSInvalidArgumentException, which is
        // uncatchable from Swift and kills the app (#134).
        //
        // So the decision is remade on the queue that performs the capture, immediately before it,
        // against the connection actually being used.
        sessionQueue.async { [weak self, output, session] in
            let connection = output.connection(with: .video)
            guard session.isRunning, let connection, connection.isActive, connection.isEnabled else {
                Task { @MainActor in
                    guard let self else { return }
                    // Not a silent no-op: a shutter press that produces nothing and says nothing is
                    // indistinguishable from a broken app to an operator at an entrance.
                    self.lastCaptureError = CaptureRejected.sessionNotReady.message
                    self.delegates.removeAll { $0.token == token }
                }
                return
            }
            output.capturePhoto(with: settings, delegate: delegate)
        }
    }

    /// Applies the rules that decide whether a frame is usable, then publishes or refuses.
    private func accept(
        _ captured: CapturedPhoto,
        subject: CaptureSubject,
        gravity: GravitySample?,
        zoomFactor: Double,
        mainLensZoom: Double,
        lens: String,
        captureDevice: String,
        captureId: String,
        capturedAt: String,
        sensorMax: CMVideoDimensions?
    ) {
        // Intrinsics ride in on the depth data (see applyConfiguration), with the photo's own
        // calibration kept as a fallback in case a future configuration can supply it directly.
        let depth = DepthCapture.record(from: captured.depthData)
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
            captureId: captureId,
            pixelWidth: captured.pixelWidth,
            pixelHeight: captured.pixelHeight,
            intrinsics: intrinsics,
            hadCalibrationData: calibration != nil,
            gravity: gravity,
            deviceModel: CaptureValidation.hardwareIdentifier(),
            lens: lens,
            captureDevice: captureDevice,
            zoomFactor: zoomFactor,
            mainLensZoomFactor: mainLensZoom,
            capturedAt: capturedAt,
            sensorWidth: sensorMax.map { Int($0.width) },
            sensorHeight: sensorMax.map { Int($0.height) },
            entrance: subject.entrance,
            conditions: subject.conditions,
            // Absence is recorded, never punished: depth is a comparison, so a frame without it
            // must still cost nothing (D-020, TICK-023).
            depth: depth?.record
        ) {
        case .success(let validated):
            var record = validated
            record.captureMode = captureMode
            lastCaptureError = nil
            let pending = PendingReview(
                record: record, image: captured.image,
                imageData: captured.imageData, depthBytes: depth?.bytes)
            if captureMode.carriesMetrologyTruth {
                pendingReview = pending
            } else {
                // No ROI step under the plain-photo protocol: there are no taps to place, so a
                // review screen asking for six of them would be a gate with nothing behind it.
                // The frame becomes a capture at the shutter. `pendingReview` is never set, so
                // the review sheet cannot flicker into view and back out within one update.
                commit(pending, taps: nil)
            }
        case .failure(let rejection):
            lastCaptureError = rejection.message
        }
    }

    /// Write a photo taken outside this app as an `imported` capture (D-034, TICK-027 / #31).
    ///
    /// Everything recorded comes from the file itself. If it cannot say when it was taken or what
    /// took it, it is refused: dating the record to the import time would put a wrong answer in
    /// the field that says when the entrance was seen, and a wrong answer is worse than no photo.
    ///
    /// It goes through `CaptureWriter` and lands in the same directory as every other capture, so
    /// the queue and the uploader treat it identically -- there is no second path to keep working.
    func importPhoto(
        _ data: Data, entrance: Entrance, conditions: ConditionTags
    ) -> ImportOutcome {
        let details: ImportedPhoto.Details
        switch ImportedPhoto.read(data) {
        case .success(let read): details = read
        case .failure(let refusal): return .refused(refusal.message)
        }

        let record = CaptureRecord(
            captureId: UUID().uuidString,
            captureMode: .imported,
            pixelWidth: details.pixelWidth,
            pixelHeight: details.pixelHeight,
            intrinsics: nil,
            gravity: nil,
            deviceModel: details.deviceModel,
            lens: nil,
            captureDevice: nil,
            zoomFactor: nil,
            capturedAt: details.capturedAt,
            depth: nil,
            entrance: entrance,
            conditions: conditions,
            roi: nil)

        switch CaptureWriter.write(record, imageData: data, depthData: nil,
                                   into: Self.capturesDirectory,
                                   imageExtension: details.fileExtension) {
        case .success:
            photosTaken += 1
            refreshPendingUploads()
            // The same evidence any other capture leaves. Without it the home screen keeps
            // showing the previous capture as the most recent one, which is the state an operator
            // reads to decide whether the last thing they did worked.
            lastRecord = record
            lastCaptureError = nil
            return .imported
        case .failure(let failure):
            lastCaptureError = failure.message
            return .refused(failure.message)
        }
    }

    /// Accept the frame under review once its six ROI points are marked. Only here does a frame
    /// become a capture.
    func confirmReview(_ taps: ROITaps) {
        guard let pending = pendingReview else { return }
        commit(pending, taps: taps)
    }

    /// Turn the frame under review into a capture on disk.
    ///
    /// `taps` is nil for a screening capture, which places none. Everything after this point --
    /// hashing, the write, the counter, the queue -- is identical in both modes, which is what
    /// keeps one path to test rather than two.
    private func commit(_ pending: PendingReview, taps: ROITaps?) {
        var record = pending.record
        record.roi = taps

        // Write before counting. `photosTaken` and `lastRecord` are the operator's evidence
        // that the capture exists, and until this call they were the ONLY evidence: the record
        // lived in memory, the encoded bytes were discarded with the delegate, and nothing
        // reached the disk. A field session would have ended with a full counter and an empty
        // directory (TICK-028, QA B02).
        let written = CaptureWriter.write(
            record,
            imageData: pending.imageData,
            depthData: pending.depthBytes,
            into: Self.capturesDirectory)

        switch written {
        case .success:
            photosTaken += 1
            refreshPendingUploads()
            lastThumbnail = pending.image
            lastRecord = record
            lastCaptureError = nil
            pendingReview = nil
        case .failure(let failure):
            // Complete-or-nothing (AC5): nothing is counted for a capture that is not on disk.
            //
            // In METROLOGY the frame stays under review, so the operator can fix what is missing
            // and confirm again. In SCREENING there is no review screen to stay on -- the frame
            // was never held there -- so a failed write means the shot is gone and has to be
            // retaken. That is why the screening path refuses so little: the camera-model gate
            // does not apply to it, and the remaining failures are disk failures.
            lastCaptureError = failure.message
        }
    }

    /// How many captures exist only on this phone. Read from disk rather than counted in memory:
    /// a number kept in a variable is a number that can disagree with the folder, and the whole
    /// point of it is to be trusted when deciding whether to leave a site.
    @Published private(set) var pendingUploads = 0
    @Published private(set) var isDraining = false
    @Published private(set) var lastDrainMessage: String?

    /// The destination, when this build has one configured.
    ///
    /// Falls back to `NoDestinationUploader`, which refuses everything: captures stay on the phone
    /// rather than being reported safe. A build with no server URL or no ingest key is the case
    /// that fallback exists for, and it is silent about nothing -- the count keeps rising and the
    /// drain says why (TICK-029).
    var uploader: CaptureUploader = UploadSettings.fromBundle().uploader() ?? NoDestinationUploader()

    private let networkMonitor = NWPathMonitor()
    private var watchingNetwork = false

    /// Drain whenever a usable connection appears (AC2).
    ///
    /// The monitor is the whole of "uploads when connectivity returns": there is no timer and no
    /// backoff schedule, because the queue is the directory and a drain is cheap to repeat. A
    /// field session that walks back into signal drains without anyone deciding to.
    func startDrainingWhenConnected() {
        guard !watchingNetwork else { return }
        watchingNetwork = true
        networkMonitor.pathUpdateHandler = { [weak self] path in
            guard path.status == .satisfied else { return }
            Task { @MainActor in await self?.drainQueue() }
        }
        networkMonitor.start(queue: DispatchQueue(label: "frontdoor.upload.path"))
    }

    var queue: CaptureQueue { CaptureQueue(directory: Self.capturesDirectory) }

    func refreshPendingUploads() {
        pendingUploads = queue.count
    }

    func drainQueue() async {
        guard !isDraining else { return }
        isDraining = true
        let report = await QueueDrain(queue: queue, uploader: uploader).drain()
        lastDrainMessage = report.message
        isDraining = false
        refreshPendingUploads()
    }

    /// Captures live beside the app's own data, so iOS backs them up and Files can reach them.
    static var capturesDirectory: URL {
        URL.documentsDirectory.appendingPathComponent("captures", isDirectory: true)
    }

    /// Throw the frame away. Nothing is recorded and nothing is counted: re-shooting is free, and
    /// a bad frame kept is not (TICK-026).
    func discardReview() {
        pendingReview = nil
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
        guard let device = AVCaptureDevice.default(lens, for: .video, position: .back)
            ?? AVCaptureDevice.default(fallbackLens, for: .video, position: .back) else {
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

        // The 1x main lens, no digital zoom, no crop (D-014). Pinned rather than assumed: the
        // system can restore a previous zoom, and a cropped frame silently invalidates the
        // intrinsics beside it. On the dual-wide this is 2.00 -- the factor at which the main lens
        // exposes, not a 2x crop of anything.
        let mainLens = Self.mainLensZoomFactor(for: device)
        do {
            try device.lockForConfiguration()
            device.videoZoomFactor = CGFloat(mainLens)
            device.unlockForConfiguration()
        } catch {
            return .failure(.configurationFailed(
                "zoom could not be pinned to the main lens: \(error.localizedDescription)"))
        }

        return .success(device)
    }
}

/// What one finished exposure yielded, before any judgement about whether it is usable.
private struct CapturedPhoto {
    var image: UIImage
    /// The camera's OWN encoded bytes. Held because AC2 hashes what is written, and a
    /// UIImage re-encoded on the way to disk is a different file with a different digest.
    var imageData: Data
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
        guard let imageData = photo.fileDataRepresentation(),
              let image = UIImage(data: imageData) else {
            onFinish(token, .failure("the camera returned no image data"))
            return
        }
        let dimensions = photo.resolvedSettings.photoDimensions
        onFinish(token, .success(CapturedPhoto(
            image: image,
            imageData: imageData,
            pixelWidth: Int(dimensions.width),
            pixelHeight: Int(dimensions.height),
            calibration: photo.cameraCalibrationData,
            depthData: photo.depthData
        )))
    }
}
