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
/// This is the worked example for `UI/DesignSystem`: every colour, size, space, radius, shadow and
/// icon on it comes from a token, and nothing here spells a hex, a point size or a system font.
/// The words are unchanged -- what an operator is told was settled before the boards arrived, and
/// restyling does not get to revise it.
struct ScanPrimerView: View {
    let continueTitle: String
    let onContinue: () -> Void

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: EntryMapLayout.space5) {
                    masthead

                    section(
                        "Where to stand",
                        "Photograph the entrance from the public footway. You do not need anyone's "
                            + "permission to do that \u{2014} but if someone objects, stop, and move on to "
                            + "the next one. Stop at the threshold: no interiors."
                    )

                    viewSet

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
                .padding(EntryMapLayout.space4)
            }
            .background(EntryMapPalette.ground)
            .navigationTitle("Before you scan")
            .navigationBarTitleDisplayMode(.inline)
            .safeAreaInset(edge: .bottom) {
                Button(action: onContinue) {
                    Text(continueTitle)
                }
                .buttonStyle(EntryMapButtonStyle(role: .primary))
                .padding(EntryMapLayout.space4)
                .background(EntryMapPalette.card)
            }
        }
        // Toolbar buttons, picker values and cursors. Here and not on the Form or the root --
        // see `entryMapForm()` for why both of those were tried and dropped.
        .tint(EntryMapPalette.violet600)
    }

    /// The brand lockup is a dark-ground piece of artwork, so it brings its own indigo with it
    /// rather than sitting on the canvas.
    private var masthead: some View {
        HStack(spacing: EntryMapLayout.space4) {
            EntryMapBrandMark(size: 64, cornerRadius: EntryMapLayout.radiusMedium)
            Text("Six photographs of one entrance, then a screening.")
                .entryMapText(EntryMapTypography.callout)
                .foregroundStyle(EntryMapPalette.subduedInk)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The view set, rendered from `ViewSlot` rather than restated.
    ///
    /// Slot labels carry distances and six of them stacked is a column, so they are set in the
    /// tabular step. Atkinson's figures are proportional by default, and without it the "1.5" and
    /// the "3-4" sit at different widths down the list.
    private var viewSet: some View {
        VStack(alignment: .leading, spacing: EntryMapLayout.space3) {
            Text("What to take")
                .entryMapText(EntryMapTypography.heading)
                .foregroundStyle(EntryMapPalette.ink)
            Text("Six views of the same entrance. The viewfinder will prompt you "
                 + "through them and keeps track of which are done.")
                .entryMapText(EntryMapTypography.body)
                .foregroundStyle(EntryMapPalette.subduedInk)
            VStack(alignment: .leading, spacing: EntryMapLayout.space3) {
                ForEach(ViewSlot.allCases, id: \.self) { slot in
                    HStack(alignment: .top, spacing: EntryMapLayout.space3) {
                        EntryMapIconView(icon: .photo, size: 22)
                        VStack(alignment: .leading, spacing: EntryMapLayout.space1) {
                            Text(slot.label)
                                .entryMapText(EntryMapTypography.subheadingNumeric)
                                .foregroundStyle(EntryMapPalette.ink)
                            Text(slot.coaching)
                                .entryMapText(EntryMapTypography.callout)
                                .foregroundStyle(EntryMapPalette.subduedInk)
                        }
                    }
                    .accessibilityElement(children: .combine)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .entryMapCard()
    }

    private func section(_ title: String, _ body: String) -> some View {
        VStack(alignment: .leading, spacing: EntryMapLayout.space2) {
            Text(title)
                .entryMapText(EntryMapTypography.heading)
                .foregroundStyle(EntryMapPalette.ink)
            Text(body)
                .entryMapText(EntryMapTypography.body)
                .foregroundStyle(EntryMapPalette.subduedInk)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .entryMapCard()
    }
}
