import SwiftUI

/// The EntryMap lockup, from the approved artwork.
///
/// **Not a reconstruction of the mark.** An earlier library shipped `svg/brand/mark-primary.svg`,
/// a degraded reproduction of the logo, and it is worth naming why, because it looked plausible in
/// a folder listing. It drew the doorway straight onto the violet pin with no white disc behind it,
/// and it stroked the middle of the three arcs in the pin's own violet, so the mark showed one
/// arc where the logo has three. The current library ships no vector or recoloured brand variant at
/// all, for exactly that reason. The approved artwork has a white disc and three distinct arcs:
/// sky on the left, white across the top, marigold on the right. A copy of it is committed at
/// `docs/brand/entrymap-approved-logo.png` and it is what this view renders.
///
/// The artwork is a **dark-ground lockup** — the wordmark is set in sky blue and white on deep
/// indigo — so the mark carries its own indigo ground and does not sit on a white card. That is a
/// property of the approved artwork, not a choice made here.
struct EntryMapBrandMark: View {
    /// The lockup is square. 128 pt is the natural size; the renditions are 1x/2x/3x of it.
    var size: CGFloat = 128
    /// Rounded corners, for the header of a screen that is itself indigo.
    var cornerRadius: CGFloat = EntryMapLayout.radiusLarge

    var body: some View {
        Image("EntryMapLogo")
            .resizable()
            .interpolation(.high)
            .aspectRatio(1, contentMode: .fit)
            .frame(width: size, height: size)
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
            .accessibilityLabel("EntryMap")
    }
}
