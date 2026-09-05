import SwiftUI

/// The five control states, in the four roles the library draws.
///
/// Colours and geometry are read off `docs/design/entrymap/svg/controls/`, which draws every state
/// explicitly, rather than guessed from the prose.
///
/// **Unavailable is a state, not a disabled control.** The spec says a control that cannot act yet
/// takes a pale-lavender fill and a deep-indigo label, and that "tapping explains what is needed".
/// So this style never applies `.disabled(_:)` — a disabled SwiftUI button does not receive the
/// tap, and the explanation is exactly what the person needed. It also never goes grey: grey is a
/// failure colour, and "not yet" is not a failure.
struct EntryMapButtonStyle: ButtonStyle {

    enum Role {
        /// Violet fill, white label. The one action a screen is for.
        case primary
        /// White fill, violet keyline and label. The alternative.
        case secondary
        /// Marigold fill, indigo label. Only ever the scan action, and the only one with a medium
        /// haptic.
        case scan
        /// No chrome at all. "Suggest a correction" and its kind.
        case quiet
    }

    let role: Role
    /// Pale lavender and a deep-indigo label. The button still receives the tap.
    var isUnavailable: Bool = false
    /// Spoken when the control is unavailable. Supply the sentence that says what is needed.
    var unavailableExplanation: String?

    func makeBody(configuration: Configuration) -> some View {
        StyledButton(
            configuration: configuration,
            role: role,
            isUnavailable: isUnavailable,
            unavailableExplanation: unavailableExplanation)
    }

    /// The control's own radius. The library draws controls at 16, between the medium and large
    /// radius tokens; it is a control measurement rather than a card one.
    static let cornerRadius: CGFloat = 16

    /// Named so it cannot be mistaken for -- or collide with -- `ButtonStyle`'s own `Body`
    /// associated type.
    private struct StyledButton: View {
        @Environment(\.isFocused) private var isFocused
        @Environment(\.accessibilityReduceMotion) private var reduceMotion

        let configuration: ButtonStyleConfiguration
        let role: Role
        let isUnavailable: Bool
        let unavailableExplanation: String?

        private var pressed: Bool { configuration.isPressed }

        var body: some View {
            configuration.label
                .entryMapText(EntryMapTypography.subheading)
                .foregroundStyle(labelColour)
                .padding(.horizontal, EntryMapLayout.space5)
                // A quiet action is as wide as its words; every other role fills its row.
                .frame(maxWidth: role == .quiet ? nil : CGFloat.infinity)
                .frame(minHeight: EntryMapLayout.touchTargetMinimum)
                .background(background)
                .overlay(focusRing)
                .scaleEffect(pressed && role != .quiet ? EntryMapLayout.pressedScale : 1)
                .animation(pressAnimation, value: pressed)
                .animation(focusAnimation, value: isFocused)
                .contentShape(RoundedRectangle(cornerRadius: EntryMapButtonStyle.cornerRadius))
                .accessibilityHint(isUnavailable ? (unavailableExplanation ?? "") : "")
                .sensoryFeedback(trigger: pressed) { _, isNowPressed in
                    // The scan control gets a medium impact; everything else a light one.
                    guard isNowPressed else { return nil }
                    return .impact(weight: role == .scan ? .medium : .light)
                }
        }

        // MARK: Motion
        //
        // Down and up are different lengths on purpose: 100 ms in, 180 ms back out. Under Reduce
        // Motion both are nil, so the control simply is pressed or is not.

        private var pressAnimation: Animation? {
            pressed
                ? EntryMapMotion.animation(.press, reduceMotion: reduceMotion)
                : EntryMapMotion.releaseAnimation(reduceMotion: reduceMotion)
        }

        private var focusAnimation: Animation? {
            EntryMapMotion.animation(.focus, reduceMotion: reduceMotion)
        }

        // MARK: Paint

        @ViewBuilder
        private var background: some View {
            if role == .quiet {
                Color.clear
            } else {
                RoundedRectangle(cornerRadius: EntryMapButtonStyle.cornerRadius)
                    .fill(fillColour)
                    .overlay {
                        // The scan master keeps its marigold and lays a separate 8% indigo wash
                        // over it while pressed, so the tier colour is deepened, never replaced.
                        if role == .scan, pressed, !isUnavailable {
                            RoundedRectangle(cornerRadius: EntryMapButtonStyle.cornerRadius)
                                .fill(EntryMapPalette.indigo900.opacity(0.08))
                        }
                    }
                    .overlay(
                        RoundedRectangle(cornerRadius: EntryMapButtonStyle.cornerRadius)
                            .strokeBorder(keylineColour, lineWidth: 2.5))
                    .entryMapElevation(pressed ? .pressed : .raised)
            }
        }

        @ViewBuilder
        private var focusRing: some View {
            if isFocused {
                RoundedRectangle(
                    cornerRadius: EntryMapButtonStyle.cornerRadius
                        + EntryMapLayout.focusRingOffset)
                    .strokeBorder(
                        EntryMapPalette.focusRing, lineWidth: EntryMapLayout.focusRingWidth)
                    .padding(-(EntryMapLayout.focusRingOffset + EntryMapLayout.focusRingWidth / 2))
            }
        }

        private var fillColour: Color {
            // The library's `primary-unavailable` draws #E2DAFF. The prose calls it "pale
            // lavender"; the artwork picks the deeper of the two pale lavenders, which is what
            // keeps a 17.83:1 indigo label from floating.
            if isUnavailable { return EntryMapPalette.lavender200 }
            switch role {
            case .primary:
                return pressed ? EntryMapPalette.violet800 : EntryMapPalette.violet600
            case .secondary:
                return pressed ? EntryMapPalette.lavender100 : EntryMapPalette.card
            case .scan:
                // Unchanged under press; the wash above does the deepening.
                return EntryMapPalette.marigold400
            case .quiet:
                return .clear
            }
        }

        private var keylineColour: Color {
            if isUnavailable { return EntryMapPalette.lavender200 }
            switch role {
            case .primary:
                return pressed ? EntryMapPalette.violet800 : EntryMapPalette.violet600
            case .secondary:
                return pressed ? EntryMapPalette.violet800 : EntryMapPalette.violet600
            case .scan:
                return pressed ? EntryMapPalette.indigo900 : EntryMapPalette.marigold400
            case .quiet:
                return .clear
            }
        }

        private var labelColour: Color {
            if isUnavailable { return EntryMapPalette.ink }
            switch role {
            case .primary: return EntryMapPalette.onViolet
            case .secondary, .quiet: return EntryMapPalette.subduedInk
            case .scan: return EntryMapPalette.onMarigold
            }
        }
    }
}
