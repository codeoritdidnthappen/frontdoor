import SwiftUI

/// What the operator is about to do, before the viewfinder opens (#275, step 1 of the scan flow).
///
/// Three things it says, in this order, because that is the order they matter at a doorway: what
/// to shoot, what happens to the photos, and what the answer will and will not be.
///
/// The view list is `ViewSlot.allCases` rather than six sentences typed here. The coaching bar in
/// the viewfinder reads the same source, and a pytest guard ties that source to
/// `docs/capture-protocol.md` -- so the primer, the coaching and the protocol cannot tell an
/// operator three different things.
///
/// Plain on purpose: the canon boards are with James (#251). What is settled here is what the
/// operator is told, which restyling will not change.
struct ScanPrimerView: View {
    let continueTitle: String
    let onContinue: () -> Void

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    section(
                        "Where to stand",
                        "Photograph the entrance from the public footway. You do not need anyone's "
                            + "permission to do that \u{2014} but if someone objects, stop, and move on to "
                            + "the next one. Stop at the threshold: no interiors."
                    )

                    VStack(alignment: .leading, spacing: 10) {
                        Text("What to take").font(.headline)
                        Text("Six views of the same entrance. The viewfinder will prompt you "
                             + "through them and keeps track of which are done.")
                            .font(.subheadline).foregroundStyle(.secondary)
                        ForEach(ViewSlot.allCases, id: \.self) { slot in
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                Image(systemName: "circle").font(.caption2).foregroundStyle(.secondary)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(slot.label).font(.subheadline.weight(.medium))
                                    Text(slot.coaching).font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }

                    section(
                        "What happens to a photo",
                        "Nothing leaves this phone until you have looked at the photo and chosen to "
                            + "publish it. When one is screened, faces in it are blurred and location "
                            + "data is stripped before the model sees it."
                    )

                    // The honesty rule, in the operator's words rather than the API's. Not copied
                    // from the server's wording -- that is printed from the response so it cannot
                    // drift, and a second copy here is exactly the drift it avoids.
                    section(
                        "What the answer is",
                        "Screening says which accessibility features are visible in your photos. It "
                            + "is not a measurement, and it is not a legal or compliance judgement "
                            + "about the entrance."
                    )
                }
                .padding()
            }
            .navigationTitle("Before you scan")
            .navigationBarTitleDisplayMode(.inline)
            .safeAreaInset(edge: .bottom) {
                Button(action: onContinue) {
                    Text(continueTitle).font(.headline)
                        .frame(maxWidth: .infinity).padding(.vertical, 14)
                }
                .buttonStyle(.borderedProminent)
                .padding()
                .background(.bar)
            }
        }
    }

    private func section(_ title: String, _ body: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.headline)
            Text(body).font(.subheadline).foregroundStyle(.secondary)
        }
    }
}
