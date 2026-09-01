import SwiftUI

/// TICK-020 spike surface. Runs the capability probe and shows the result as text that can be
/// copied straight into the committed note the ticket asks for.
///
/// Deliberately plain. This is a measurement instrument for one question, and it comes out again
/// once the answer is recorded and the decision taken.
struct DiagnosticsView: View {
    let onClose: () -> Void

    @State private var report: CapabilityProbe.Report?
    @State private var running = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(
                        "Answers whether AVFoundation delivers camera calibration data and depth "
                            + "alongside a full-resolution still from the 1x lens (ASM-2, R-9). "
                            + "Run this on a real device; a simulator has no camera and proves nothing."
                    )
                    .font(.footnote)
                    .foregroundStyle(.secondary)

                    if let report {
                        Text(report.plainText)
                            .font(.system(.footnote, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(12)
                            .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 10))

                        Button {
                            UIPasteboard.general.string = report.plainText
                        } label: {
                            Label("Copy result", systemImage: "doc.on.doc")
                        }
                        .buttonStyle(.bordered)
                    }

                    Button {
                        Task {
                            running = true
                            report = await CapabilityProbe.run()
                            running = false
                        }
                    } label: {
                        if running {
                            ProgressView().frame(maxWidth: .infinity)
                        } else {
                            Text(report == nil ? "Run probe" : "Run again")
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(running)
                }
                .padding(20)
            }
            .navigationTitle("Capability probe")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done", action: onClose)
                }
            }
        }
    }
}
