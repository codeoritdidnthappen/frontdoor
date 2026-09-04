import SwiftUI

/// The review-before-publish consent gate for a screening capture (#275, canon via #251).
///
/// A community scan is a photograph of someone's premises. The canon puts a review step in front
/// of publishing one, and until now there was no moment at which that question could be asked --
/// a screening frame became a capture at the shutter.
///
/// Deliberately plain. The canon boards for this surface are with James (#251); what is settled
/// here is the BEHAVIOUR, which the boards will not change: the frame is shown at a size worth
/// judging, publishing is the deliberate action, and discarding leaves nothing behind. Restyling
/// this does not touch `CaptureController`.
struct ScreeningReviewView: View {
    let image: UIImage
    let entranceId: String
    let onPublish: () -> Void
    let onDiscard: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            // The photo, as large as the frame allows: a gate the operator cannot see through is
            // not a review.
            Image(uiImage: image)
                .resizable()
                .scaledToFit()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(.black)
                .accessibilityLabel("The photo just taken of entrance \(entranceId)")

            VStack(spacing: 12) {
                Text("Publish this photo of \(entranceId)?")
                    .font(.headline)
                // Says what publishing MEANS, rather than assuming the operator infers it. The
                // honesty rule the screening wording follows applies to the consent question too.
                Text("It will be uploaded and screened. Discarding keeps nothing — the photo is "
                     + "not saved and nothing is counted.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)

                HStack(spacing: 12) {
                    Button(role: .destructive, action: onDiscard) {
                        Text("Discard").frame(maxWidth: .infinity).padding(.vertical, 6)
                    }
                    .buttonStyle(.bordered)

                    Button(action: onPublish) {
                        Text("Publish").frame(maxWidth: .infinity).padding(.vertical, 6)
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
            .padding()
            .frame(maxWidth: .infinity)
            .background(.regularMaterial)
        }
    }
}
