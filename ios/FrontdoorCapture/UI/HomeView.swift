import AVFoundation
import SwiftUI

/// Where the app opens. The camera is off until the operator asks for it, so launching the app
/// does not switch on a camera indicator, and there is somewhere to come back to when they stop.
///
/// It also states readiness before anything is tapped. On the two capture phones the answers
/// differ — one has LiDAR, one does not — and an operator at an entrance should not discover that
/// from a viewfinder that will not open.
struct HomeView: View {
    @ObservedObject var controller: CaptureController
    let onStart: () -> Void
    /// Re-open the scan primer. It is shown automatically once per install; this is what keeps
    /// "seen" from meaning "gone" (#275).
    let onPrimer: () -> Void
    let onImport: () -> Void
    let onDiagnostics: () -> Void
    let onEditLabel: (String) -> Void

    /// What is still only on this phone, and a way to send it.
    ///
    /// AC6: nobody should leave a field session unsure whether the day's work is safe. "Captured
    /// this session" answers a different question -- it resets on relaunch and counts frames that
    /// may already be uploaded. This counts what would be lost if the phone were.
    @ViewBuilder
    private var pendingRow: some View {
        let pending = controller.pendingUploads
        let pendingLabels = controller.pendingLabels
        // The result is shown whether or not anything is still queued. It used to live inside
        // `pending > 0`, so a fully successful drain -- the one case worth confirming -- set the
        // count to zero and took its own confirmation with it: the operator tapped Upload now and
        // watched the row vanish with nothing said. AC6 is about not leaving a site unsure.
        if pending > 0 || pendingLabels > 0 || controller.lastDrainMessage != nil
            || controller.lastLabelDrainMessage != nil || controller.labelQueueError != nil {
            VStack(spacing: EntryMapLayout.space2) {
                if pending > 0 {
                    Text("^[\(pending) capture](inflect: true) on this phone only")
                        .entryMapText(EntryMapTypography.subheadingNumeric)
                        .foregroundStyle(EntryMapPalette.ink)
                    Button(controller.isDraining ? "Uploading…" : "Upload now") {
                        Task { await controller.drainQueue() }
                    }
                    .buttonStyle(EntryMapButtonStyle(role: .secondary))
                    .disabled(controller.isDraining)
                }
                if pendingLabels > 0 {
                    Text("^[\(pendingLabels) label record](inflect: true) waiting to upload")
                        .entryMapText(EntryMapTypography.subheadingNumeric)
                        .foregroundStyle(EntryMapPalette.ink)
                    Button("Upload labels now") {
                        Task { await controller.drainLabelQueue() }
                    }
                    .buttonStyle(EntryMapButtonStyle(role: .secondary))
                    ForEach(controller.queuedLabelIds, id: \.self) { entranceId in
                        Button("Edit labels for \(entranceId)") { onEditLabel(entranceId) }
                            .buttonStyle(EntryMapButtonStyle(role: .quiet))
                    }
                }
                if let queueError = controller.labelQueueError {
                    Text(queueError)
                        .entryMapText(EntryMapTypography.callout)
                        .foregroundStyle(EntryMapPalette.onMarigold)
                        .multilineTextAlignment(.center)
                        .padding(EntryMapLayout.space3)
                        .frame(maxWidth: .infinity)
                        .background(EntryMapPalette.marigold400,
                                    in: RoundedRectangle(cornerRadius: EntryMapLayout.radiusSmall))
                        .padding(.horizontal, EntryMapLayout.space5)
                }
                if let outcome = controller.lastDrainMessage {
                    Text(outcome)
                        .entryMapText(EntryMapTypography.callout)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(pending > 0
                                         ? EntryMapPalette.subduedInk : EntryMapPalette.ink)
                        .padding(.horizontal, EntryMapLayout.space5)
                }
                if let outcome = controller.lastLabelDrainMessage {
                    Text(outcome)
                        .entryMapText(EntryMapTypography.callout)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(EntryMapPalette.subduedInk)
                        .padding(.horizontal, EntryMapLayout.space5)
                }
            }
            .padding(.top, EntryMapLayout.space1)
        }
    }

    /// Read by ``statusRow(_:ok:detail:)``, which stacks its two halves at the accessibility
    /// sizes rather than letting them share a line.
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    /// Scrolls, and still centres when it fits.
    ///
    /// A bare VStack truncated two explanations at the DEFAULT text size once the restyle landed:
    /// 32 pt between every child, an 88 pt brand mark, 44 pt display type and 48 pt minimum touch
    /// targets are each right on their own and do not fit together. SwiftUI does not push a
    /// too-tall VStack off the screen -- it shrinks the flexible children, so "Device motion is
    /// unavailable, so the gravity vect..." was the operator's whole explanation of why capture
    /// was blocked.
    ///
    /// `minHeight: geo.size.height` is what keeps the old look: when the content is shorter than
    /// the screen the VStack is stretched to fill it and the Spacers below still centre
    /// everything, which they cannot do inside a plain ScrollView. `basedOnSize` stops the screen
    /// rubber-banding on the phones where it does fit.
    var body: some View {
        GeometryReader { geo in
            ScrollView {
                content.frame(minHeight: geo.size.height)
            }
            .scrollBounceBehavior(.basedOnSize)
        }
    }

    private var content: some View {
        VStack(spacing: EntryMapLayout.space6) {
            Spacer()

            VStack(spacing: EntryMapLayout.space2) {
                EntryMapBrandMark(size: 88, cornerRadius: EntryMapLayout.radiusLarge)
                Text("EntryMap")
                    .entryMapText(EntryMapTypography.display)
                    .foregroundStyle(EntryMapPalette.ink)
                Text("Storefront entrance capture")
                    .entryMapText(EntryMapTypography.callout)
                    .foregroundStyle(EntryMapPalette.subduedInk)
            }

            VStack(spacing: 0) {
                statusRow(
                    "Camera",
                    ok: controller.readiness.cameraAuthorization != .denied
                        && controller.readiness.cameraAuthorization != .restricted,
                    detail: cameraDetail
                )
                EntryMapPalette.edge.frame(height: 1).padding(.leading, EntryMapLayout.space7)
                statusRow(
                    "Device motion",
                    ok: controller.readiness.motionAvailable,
                    detail: controller.readiness.motionAvailable ? "Available" : "Unavailable"
                )
            }
            .background(EntryMapPalette.card,
                        in: RoundedRectangle(cornerRadius: EntryMapLayout.radiusMedium))
            .overlay(RoundedRectangle(cornerRadius: EntryMapLayout.radiusMedium)
                .stroke(EntryMapPalette.edge, lineWidth: 1))
            .padding(.horizontal, EntryMapLayout.space5)

            if let blocked = controller.readiness.blockingReason {
                VStack(spacing: EntryMapLayout.space3) {
                    Text(blocked.message)
                        .entryMapText(EntryMapTypography.callout)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(EntryMapPalette.subduedInk)
                    if blocked == .cameraDenied {
                        Button("Open Settings", action: controller.openSystemSettings)
                            .buttonStyle(EntryMapButtonStyle(role: .secondary))
                    }
                }
                .padding(.horizontal, EntryMapLayout.space6)
            }

            Spacer()

            // Which contract this session records against (D-034). Screening is the protocol the
            // field is running; metrology is still reachable because whether it is alive is an
            // open team question (A-3, #67), not one this screen should settle by omission.
            modePicker
                .padding(.horizontal, EntryMapLayout.space5)

            Text(controller.captureMode == .screening
                 ? "Plain photos: entrance ID and condition tags. No caliper, no card, no taps."
                 : "Caliper reading, reference card and ROI taps are required for every capture.")
                .entryMapText(EntryMapTypography.caption)
                .foregroundStyle(EntryMapPalette.subduedInk)
                .multilineTextAlignment(.center)
                .padding(.horizontal, EntryMapLayout.space6)

            // The scan action, and the only place the marigold role is used (#367).
            Button(action: onStart) {
                Text("Start capture")
            }
            .buttonStyle(EntryMapButtonStyle(
                role: .scan,
                isUnavailable: controller.readiness.blockingReason != nil,
                unavailableExplanation: controller.readiness.blockingReason?.message))
            .disabled(controller.readiness.blockingReason != nil)
            .padding(.horizontal, EntryMapLayout.space5)

            Button("How scanning works") { onPrimer() }
                .buttonStyle(EntryMapButtonStyle(role: .quiet))

            Button("Import photos already on this phone") { onImport() }
                .buttonStyle(EntryMapButtonStyle(role: .quiet))

            Button("Run capability probe") { onDiagnostics() }
                .buttonStyle(EntryMapButtonStyle(role: .quiet))

            Text("\(controller.photosTaken) captured this session")
                .entryMapText(EntryMapTypography.captionNumeric)
                .foregroundStyle(EntryMapPalette.subduedInk)

            pendingRow
                .padding(.bottom, EntryMapLayout.space3)
        }
    }

    /// The mode switch, built from the tokens.
    ///
    /// `.pickerStyle(.segmented)` put a grey system control with the system font in the middle of
    /// a restyled screen. The design canon has no segmented control of its own, so this composes
    /// one from tokens already in the library -- a violet pill on the lavender edge colour,
    /// nothing new invented. Worth a designer's eye before it spreads to a second screen.
    private var modePicker: some View {
        HStack(spacing: 0) {
            modeSegment("Screening", mode: .screening)
            modeSegment("Metrology", mode: .metrology)
        }
        .padding(EntryMapLayout.space1)
        .background(EntryMapPalette.edge, in: Capsule())
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Capture mode")
    }

    private func modeSegment(_ title: String, mode: CaptureMode) -> some View {
        let selected = controller.captureMode == mode
        return Button {
            controller.captureMode = mode
        } label: {
            Text(title)
                .entryMapText(EntryMapTypography.subheading)
                .foregroundStyle(selected ? EntryMapPalette.onViolet : EntryMapPalette.subduedInk)
                .frame(maxWidth: .infinity)
                .frame(minHeight: EntryMapLayout.touchTargetMinimum)
                .background(selected ? EntryMapPalette.violet600 : Color.clear, in: Capsule())
                .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    private var cameraDetail: String {
        switch controller.readiness.cameraAuthorization {
        case .authorized: return "Allowed"
        case .notDetermined: return "Will ask on first capture"
        case .denied: return "Denied"
        case .restricted: return "Restricted"
        @unknown default: return "Unknown"
        }
    }

    /// Label and value side by side, until they no longer fit.
    ///
    /// At the accessibility text sizes an HStack gives each half less than a word: the row read
    /// "Came / ra" against "Will / ask on / first / captur / e". Stacking is what the OS's own
    /// settings rows do at those sizes, and it is the difference between a readable explanation
    /// and a column of syllables.
    private func statusRow(_ title: String, ok: Bool, detail: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: EntryMapLayout.space3) {
            // No green and no red: the approved palette contains neither, and the map's own rule
            // is that colour never carries a verdict. Readiness is an icon plus its words.
            EntryMapIconView(icon: ok ? .checkOutline : .info, size: 22,
                             tint: ok ? EntryMapPalette.ink : EntryMapPalette.freshness)
            let stack = dynamicTypeSize.isAccessibilitySize
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: EntryMapLayout.space1))
                : AnyLayout(HStackLayout(spacing: EntryMapLayout.space3))
            stack {
                Text(title)
                    .entryMapText(EntryMapTypography.body)
                    .foregroundStyle(EntryMapPalette.ink)
                if !dynamicTypeSize.isAccessibilitySize { Spacer(minLength: 0) }
                Text(detail)
                    .entryMapText(EntryMapTypography.callout)
                    .foregroundStyle(EntryMapPalette.subduedInk)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, EntryMapLayout.space4)
        .padding(.vertical, EntryMapLayout.space3)
        .frame(minHeight: EntryMapLayout.touchTargetMinimum)
    }
}
