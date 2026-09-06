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
            EntryMapPalette.darkGround.ignoresSafeArea()

            switch controller.state {
            case .stopped, .starting:
                ProgressView("Starting the camera")
                    .tint(EntryMapPalette.white)
                    .foregroundStyle(EntryMapPalette.white)
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
        VStack(spacing: EntryMapLayout.space4) {
            EntryMapIconView(icon: .info, size: 40, tint: EntryMapPalette.marigold400)
            Text("Cannot capture")
                .entryMapText(EntryMapTypography.heading)
                .foregroundStyle(EntryMapPalette.white)
            Text(reason.message)
                .entryMapText(EntryMapTypography.body)
                .foregroundStyle(EntryMapPalette.white)
                .multilineTextAlignment(.center)
            HStack(spacing: EntryMapLayout.space3) {
                if reason == .cameraDenied {
                    Button("Open Settings", action: controller.openSystemSettings)
                        .buttonStyle(EntryMapButtonStyle(role: .secondary))
                }
                Button("Back", action: close)
                    .buttonStyle(EntryMapButtonStyle(role: .primary))
            }
            .padding(.top, EntryMapLayout.space2)
        }
        .padding(EntryMapLayout.space6)
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
                    Text("Measuring…")
                        .entryMapText(EntryMapTypography.caption)
                        .padding(EntryMapLayout.space2)
                        .background(Self.scrim, in: Capsule())
                        .foregroundStyle(EntryMapPalette.white)
                }
                if let problem = controller.measurementError {
                    // The capture is on disk and queued before a measurement is attempted, so
                    // this says what failed without implying anything was lost (AC4).
                    Text(problem)
                        .entryMapText(EntryMapTypography.caption)
                        .multilineTextAlignment(.center)
                        .padding(EntryMapLayout.space3)
                        .background(EntryMapPalette.marigold400,
                                    in: RoundedRectangle(
                                        cornerRadius: EntryMapLayout.radiusSmall))
                        .foregroundStyle(EntryMapPalette.onMarigold)
                        .padding(.horizontal, EntryMapLayout.space4)
                }
                if let failure = controller.lastCaptureError {
                    Text(failure)
                        .entryMapText(EntryMapTypography.caption)
                        .foregroundStyle(EntryMapPalette.onMarigold)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, EntryMapLayout.space3)
                        .background(EntryMapPalette.marigold400)
                }
                controls
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .overlay(alignment: .topLeading) { closeButton }
        .overlay(alignment: .top) {
            VStack(spacing: EntryMapLayout.space2) {
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
                VStack(spacing: EntryMapLayout.space1) {
                    HStack(spacing: EntryMapLayout.space2) {
                        Text(controller.viewSlot.label)
                            .entryMapText(EntryMapTypography.overline)
                        EntryMapIconView(icon: .chevronRight, size: 12,
                                         tint: EntryMapPalette.white)
                            .rotationEffect(.degrees(90))
                    }
                    Text(controller.viewSlot.coaching)
                        .entryMapText(EntryMapTypography.caption)
                        .multilineTextAlignment(.center)
                    Text(controller.coverageForSubject.summary)
                        .entryMapText(EntryMapTypography.captionNumeric)
                        .foregroundStyle(EntryMapPalette.onDarkGround)
                }
                .foregroundStyle(EntryMapPalette.white)
                .padding(.horizontal, EntryMapLayout.space4)
                .padding(.vertical, EntryMapLayout.space2)
                .frame(maxWidth: 320)
                .background(Self.scrim,
                            in: RoundedRectangle(cornerRadius: EntryMapLayout.radiusMedium))
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
                HStack(spacing: EntryMapLayout.space2) {
                    Text(subject.entrance.id)
                        .entryMapText(EntryMapTypography.overline)
                    Text("·")
                    // How many photos this doorway has, including the extra angles and
                    // deviations the protocol allows. Which of the named views are covered is the
                    // separate question the coaching bar below answers (#289); the app enforces
                    // neither (D-021 moved to capture-protocol.md in the 2026-09-01 pivot).
                    Text("^[\(controller.capturesForSubject) photo](inflect: true)")
                        .entryMapText(EntryMapTypography.captionNumeric)
                    Text("·")
                    Text(String(format: "%.1f m", subject.conditions.distanceM))
                        .entryMapText(EntryMapTypography.captionNumeric)
                    Text("·")
                    Text(subject.conditions.lighting.label)
                        .entryMapText(EntryMapTypography.caption)
                    EntryMapIconView(icon: .correction, size: 14, tint: EntryMapPalette.white)
                }
                .foregroundStyle(EntryMapPalette.white)
                .padding(.horizontal, EntryMapLayout.space3)
                .padding(.vertical, EntryMapLayout.space2)
                .background(Self.scrim, in: Capsule())
            }
            .padding(.top, EntryMapLayout.space2)
            .accessibilityLabel(
                "Conditions: \(subject.entrance.id), "
                + "\(controller.capturesForSubject) photos so far, "
                + "\(String(format: "%.1f", subject.conditions.distanceM)) metres, "
                + "\(subject.conditions.lighting.label). Tap to change.")
        }
    }

    private var closeButton: some View {
        Button(action: close) {
            EntryMapIconView(icon: .close, size: 20, tint: EntryMapPalette.white)
                .frame(width: EntryMapLayout.touchTargetMinimum,
                       height: EntryMapLayout.touchTargetMinimum)
                .background(Self.scrim, in: Circle())
        }
        .accessibilityLabel("Close camera")
        .padding(.leading, EntryMapLayout.space5)
        .padding(.top, EntryMapLayout.space3)
    }

    private var controls: some View {
        VStack(spacing: EntryMapLayout.space3) {
            HStack(alignment: .center) {
                // Last still, held in memory. Proof that a capture actually produced an image
                // rather than only incrementing a counter.
                Group {
                    if let thumb = controller.lastThumbnail {
                        Image(uiImage: thumb)
                            .resizable()
                            .scaledToFill()
                            .frame(width: 52, height: 52)
                            .clipShape(RoundedRectangle(
                                cornerRadius: EntryMapLayout.radiusSmall))
                            .overlay(RoundedRectangle(
                                cornerRadius: EntryMapLayout.radiusSmall)
                                .stroke(EntryMapPalette.white.opacity(0.6)))
                    } else {
                        RoundedRectangle(cornerRadius: EntryMapLayout.radiusSmall)
                            .stroke(EntryMapPalette.white.opacity(0.3),
                                    style: StrokeStyle(lineWidth: 1, dash: [4]))
                            .frame(width: 52, height: 52)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                Button(action: controller.capturePhoto) {
                    Circle()
                        .strokeBorder(EntryMapPalette.white, lineWidth: 4)
                        .frame(width: 74, height: 74)
                        .background(Circle().fill(EntryMapPalette.white.opacity(0.25)))
                }
                .accessibilityLabel("Take photo")

                VStack(alignment: .trailing, spacing: EntryMapLayout.space1) {
                    Text("\(controller.photosTaken)")
                        .entryMapText(EntryMapTypography.subheadingNumeric)
                        .foregroundStyle(EntryMapPalette.white)
                    if controller.lastCaptureError != nil {
                        EntryMapIconView(icon: .info, size: 16,
                                         tint: EntryMapPalette.marigold400)
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
                .buttonStyle(EntryMapButtonStyle(role: .primary))
                .disabled(!CaptureFinishDecision.isEnabled(
                    mode: controller.captureMode, coverage: controller.coverageForSubject))
                .accessibilityHint(
                    controller.coverageForSubject.isComplete
                        ? "Opens the four human-label questions."
                        : "Available after all six named views are captured.")
            }
        }
        .padding(.horizontal, EntryMapLayout.space5)
        .padding(.top, EntryMapLayout.space4)
        .padding(.bottom, EntryMapLayout.space6)
        .background(Self.scrim)
    }

    /// The viewfinder's scrim. `darkGround` rather than a new colour: the overlays sit on live
    /// video, so they need a ground of their own, and the palette's deep indigo is the one the
    /// design system already gives for type on a dark field.
    private static let scrim = EntryMapPalette.darkGround.opacity(0.55)

    private func close() {
        controller.stop()
        onClose()
    }
}
