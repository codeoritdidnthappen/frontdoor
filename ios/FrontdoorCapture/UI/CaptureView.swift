import SwiftUI

/// The viewfinder. Preview, a shutter, and a way out that is not force-quitting the app.
///
/// The seam for EPIC-03: rendering observes `CaptureController` and adds views alongside this one.
/// It does not reach into the session, so adding the Demo Day result display cannot fork the
/// capture path (R-11).
struct CaptureView: View {
    @ObservedObject var controller: CaptureController
    @Environment(\.scenePhase) private var scenePhase
    let onClose: () -> Void
    let onFinish: (String) -> Void

    @State private var editingConditions = false

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            switch controller.state {
            case .stopped, .starting:
                ProgressView("Starting the camera")
                    .tint(.white)
                    .foregroundStyle(.white)
            case .unavailable(let reason):
                unavailable(reason)
            case .running:
                viewfinder
            }
        }
        .task { await controller.start() }
        // Leaving the app is not a reason to keep the camera on: the indicator would stay lit and
        // the session would be interrupted out from under us. Stop on the way out, restart on the
        // way back, so returning to the viewfinder shows a live preview rather than a dead one.
        .onChange(of: scenePhase) { _, phase in
            switch phase {
            case .active:
                Task { await controller.start() }
            case .background, .inactive:
                controller.stop()
            @unknown default:
                controller.stop()
            }
        }
    }

    private func unavailable(_ reason: CaptureUnavailable) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle")
                .font(.largeTitle)
            Text("Cannot capture").font(.headline)
            Text(reason.message)
                .font(.callout)
                .multilineTextAlignment(.center)
            HStack(spacing: 12) {
                if reason == .cameraDenied {
                    Button("Open Settings", action: controller.openSystemSettings)
                        .buttonStyle(.bordered)
                }
                Button("Back", action: close).buttonStyle(.borderedProminent)
            }
            .padding(.top, 8)
        }
        .foregroundStyle(.white)
        .padding(32)
    }

    private var viewfinder: some View {
        ZStack(alignment: .bottom) {
            CameraPreview(session: controller.session)
                // CameraPreview is a UIViewRepresentable with an ambiguous ideal size: its layer
                // fills, but its layout box does not, so without this the ZStack sizes to the
                // smaller box and .bottom lands mid-screen.
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .ignoresSafeArea()

            VStack(spacing: 0) {
                if controller.isMeasuring {
                    Label("Measuring…", systemImage: "ruler")
                        .font(.footnote)
                        .padding(8)
                        .background(.black.opacity(0.55), in: Capsule())
                        .foregroundStyle(.white)
                }
                if let problem = controller.measurementError {
                    // The capture is on disk and queued before a measurement is attempted, so
                    // this says what failed without implying anything was lost (AC4).
                    Text(problem)
                        .font(.footnote)
                        .multilineTextAlignment(.center)
                        .padding(10)
                        .background(.orange, in: RoundedRectangle(cornerRadius: 10))
                        .foregroundStyle(.black)
                        .padding(.horizontal, 16)
                }
                if let failure = controller.lastCaptureError {
                    Text(failure)
                        .font(.footnote)
                        .foregroundStyle(.white)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .background(.orange.opacity(0.85))
                }
                controls
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .overlay(alignment: .topLeading) { closeButton }
        .overlay(alignment: .top) {
            VStack(spacing: 6) {
                conditionsBar
                coachingBar
            }
        }
        // Between the shutter and the record. Neither mode writes anything until the frame has
        // been through this: metrology needs its six points marked, screening needs the operator
        // to consent to publishing a photo of someone's premises (#275).
        .fullScreenCover(item: $controller.pendingReview) { pending in
            if controller.captureMode.carriesMetrologyTruth {
                ROIReviewView(
                    image: pending.image,
                    pixelWidth: pending.record.pixelWidth,
                    pixelHeight: pending.record.pixelHeight,
                    onConfirm: controller.confirmReview,
                    onDiscard: controller.discardReview
                )
            } else {
                ScreeningReviewView(
                    image: pending.image,
                    entranceId: pending.record.entrance.id,
                    onPublish: controller.confirmScreeningReview,
                    onDiscard: controller.discardReview
                )
            }
        }
        .sheet(isPresented: $editingConditions) {
            if let subject = controller.subject {
                ConditionsSheet(mode: controller.captureMode, current: subject.conditions) { tags in
                    controller.subject?.conditions = tags
                    editingConditions = false
                } onCancel: {
                    editingConditions = false
                }
            }
        }
    }

    /// Which view of the protocol's set the next shot is, and what is still missing (#289).
    ///
    /// Deliberately an offer and not a gate. It follows the coverage to the next missing view so
    /// an operator who just works through the prompts ends up with the set, but every view stays
    /// selectable — including one already covered. `docs/capture-protocol.md` allows deviation,
    /// and an instrument that refused a seventh angle would cost captures it cannot get back.
    ///
    /// Plain on purpose: the canon boards for this surface are with James (#251), and what is
    /// settled here is which views exist and how coverage is reported, which restyling will not
    /// change.
    @ViewBuilder
    private var coachingBar: some View {
        if controller.subject != nil {
            Menu {
                ForEach(ViewSlot.allCases, id: \.self) { slot in
                    Button {
                        controller.viewSlot = slot
                    } label: {
                        Label(
                            slot.label,
                            systemImage: controller.coverageForSubject.captured.contains(slot)
                                ? "checkmark.circle.fill" : "circle")
                    }
                }
            } label: {
                VStack(spacing: 2) {
                    HStack(spacing: 6) {
                        Text(controller.viewSlot.label).fontWeight(.semibold)
                        Image(systemName: "chevron.down").font(.caption2)
                    }
                    Text(controller.viewSlot.coaching)
                        .font(.caption)
                        .multilineTextAlignment(.center)
                    Text(controller.coverageForSubject.summary)
                        .font(.caption2)
                        .foregroundStyle(.white.opacity(0.75))
                }
                .font(.footnote)
                .foregroundStyle(.white)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .frame(maxWidth: 320)
                .background(.black.opacity(0.45), in: RoundedRectangle(cornerRadius: 14))
            }
            .accessibilityLabel(
                "Next view: \(controller.viewSlot.label). \(controller.viewSlot.coaching) "
                + "\(controller.coverageForSubject.summary). Tap to choose a different view.")
        }
    }

    /// What the next shot will be tagged with, visible without leaving the camera.
    ///
    /// Shown rather than remembered: the operator moves between frames (D-002 wants several
    /// distances per entrance), and a tag that can only be set before the viewfinder opens would
    /// let every later frame inherit the first one's distance. Wrong in a stratification variable
    /// and undetectable afterwards.
    @ViewBuilder
    private var conditionsBar: some View {
        if let subject = controller.subject {
            Button { editingConditions = true } label: {
                HStack(spacing: 6) {
                    Text(subject.entrance.id).fontWeight(.semibold)
                    Text("·")
                    // How many photos this doorway has, including the extra angles and
                    // deviations the protocol allows. Which of the named views are covered is the
                    // separate question the coaching bar below answers (#289); the app enforces
                    // neither (D-021 moved to capture-protocol.md in the 2026-09-01 pivot).
                    Text("^[\(controller.capturesForSubject) photo](inflect: true)")
                        .monospacedDigit()
                    Text("·")
                    Text(String(format: "%.1f m", subject.conditions.distanceM))
                        .monospacedDigit()
                    Text("·")
                    Text(subject.conditions.lighting.label)
                    Image(systemName: "pencil").font(.caption2)
                }
                .font(.footnote)
                .foregroundStyle(.white)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(.black.opacity(0.45), in: Capsule())
            }
            .padding(.top, 8)
            .accessibilityLabel(
                "Conditions: \(subject.entrance.id), "
                + "\(controller.capturesForSubject) photos so far, "
                + "\(String(format: "%.1f", subject.conditions.distanceM)) metres, "
                + "\(subject.conditions.lighting.label). Tap to change.")
        }
    }

    private var closeButton: some View {
        Button(action: close) {
            Label("Close", systemImage: "xmark")
                .labelStyle(.iconOnly)
                .font(.headline)
                .foregroundStyle(.white)
                .frame(width: 44, height: 44)
                .background(.black.opacity(0.45), in: Circle())
        }
        .accessibilityLabel("Close camera")
        .padding(.leading, 20)
        .padding(.top, 12)
    }

    private var controls: some View {
        VStack(spacing: 12) {
            HStack(alignment: .center) {
                // Last still, held in memory. Proof that a capture actually produced an image
                // rather than only incrementing a counter.
                Group {
                    if let thumb = controller.lastThumbnail {
                        Image(uiImage: thumb)
                            .resizable()
                            .scaledToFill()
                            .frame(width: 52, height: 52)
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                            .overlay(RoundedRectangle(cornerRadius: 8).stroke(.white.opacity(0.6)))
                    } else {
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(.white.opacity(0.3), style: StrokeStyle(lineWidth: 1, dash: [4]))
                            .frame(width: 52, height: 52)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                Button(action: controller.capturePhoto) {
                    Circle()
                        .strokeBorder(.white, lineWidth: 4)
                        .frame(width: 74, height: 74)
                        .background(Circle().fill(.white.opacity(0.25)))
                }
                .accessibilityLabel("Take photo")

                VStack(alignment: .trailing, spacing: 2) {
                    Text("\(controller.photosTaken)")
                        .font(.title3.monospacedDigit().weight(.semibold))
                        .foregroundStyle(.white)
                    if controller.lastCaptureError != nil {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.caption)
                            .foregroundStyle(.orange)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .trailing)
            }
            if controller.captureMode == .screening,
               let entranceId = controller.subject?.entrance.id {
                Button("Finish capture") {
                    controller.stop()
                    if let destination = CaptureFinishDecision.destination(
                        mode: controller.captureMode,
                        coverage: controller.coverageForSubject,
                        entranceId: entranceId) {
                        onFinish(destination)
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(!CaptureFinishDecision.isEnabled(
                    mode: controller.captureMode, coverage: controller.coverageForSubject))
                .accessibilityHint(
                    controller.coverageForSubject.isComplete
                        ? "Opens the four human-label questions."
                        : "Available after all six named views are captured.")
            }
        }
        .padding(.horizontal, 24)
        .padding(.top, 16)
        .padding(.bottom, 28)
        .background(.black.opacity(0.45))
    }

    private func close() {
        controller.stop()
        onClose()
    }
}
