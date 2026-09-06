import SwiftUI

/// TICK-020 spike surface. Runs the capability probe and shows the result as text that can be
/// copied straight into the committed note the ticket asks for.
///
/// Deliberately plain. This is a measurement instrument for one question, and it comes out again
/// once the answer is recorded and the decision taken.
struct DiagnosticsView: View {
    let onClose: () -> Void

    @State private var report: CapabilityProbe.Report?
    @State private var probe: Task<Void, Never>?

    private var running: Bool { probe != nil }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: EntryMapLayout.space4) {
                    Text(
                        "Answers whether AVFoundation delivers camera calibration data and depth "
                            + "alongside a full-resolution still from the 1x lens (ASM-2, R-9). "
                            + "Run this on a real device; a simulator has no camera and proves nothing."
                    )
                    .entryMapText(EntryMapTypography.caption)
                    .foregroundStyle(EntryMapPalette.subduedInk)

                    if let report {
                        Text(report.plainText)
                            .entryMapText(EntryMapTypography.captionNumeric)
                            .foregroundStyle(EntryMapPalette.ink)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(EntryMapLayout.space3)
                            .background(EntryMapPalette.card,
                                        in: RoundedRectangle(
                                            cornerRadius: EntryMapLayout.radiusSmall))
                            .overlay(
                                RoundedRectangle(cornerRadius: EntryMapLayout.radiusSmall)
                                    .stroke(EntryMapPalette.edge))

                        Button("Copy result") {
                            UIPasteboard.general.string = report.plainText
                        }
                        .buttonStyle(EntryMapButtonStyle(role: .secondary))
                    }

                    Button {
                        probe = Task {
                            let result = await CapabilityProbe.run()
                            // A cancelled probe was abandoned by dismissing the sheet; its result
                            // is not wanted and the session it opened is already being torn down.
                            guard !Task.isCancelled else { return }
                            report = result
                            probe = nil
                        }
                    } label: {
                        if running {
                            ProgressView().frame(maxWidth: .infinity)
                        } else {
                            Text(report == nil ? "Run probe" : "Run again")
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .buttonStyle(EntryMapButtonStyle(role: .primary))
                    .disabled(running)
                }
                .padding(EntryMapLayout.space5)
            }
            .background(EntryMapPalette.ground)
            .navigationTitle("Capability probe")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        // Cancelling matters: an in-flight probe holds an AVCaptureSession, and
                        // leaving it running would light the camera indicator over a screen that
                        // shows nothing capturing.
                        cancelProbe()
                        onClose()
                    }
                }
            }
        }
        // Tints the toolbar buttons, picker values and text cursors. It goes here rather
        // than on the content because a toolbar is attached to the content but is not inside
        // it, and it does not survive the sheet boundary from the root either.
        .tint(EntryMapPalette.violet600)
    }

    private func cancelProbe() {
        probe?.cancel()
        probe = nil
    }
}
