import SwiftUI

/// Spacing, radii, control metrics and elevation.
///
/// Spacing, radius and the interaction metrics come straight from
/// `docs/design/entrymap/design-tokens.json` and `interaction-motion.json`; the numbers are pinned
/// by `tests/test_ios_design_system.py`. Elevation is derived, and says so below.
enum EntryMapLayout {

    // MARK: - Spacing

    /// 4 pt. Between a glyph and its label.
    static let space1: CGFloat = 4
    /// 8 pt. Between the lines of one thought.
    static let space2: CGFloat = 8
    /// 12 pt. Between rows of a list.
    static let space3: CGFloat = 12
    /// 16 pt. The screen gutter.
    static let space4: CGFloat = 16
    /// 24 pt. Between sections.
    static let space5: CGFloat = 24
    /// 32 pt. Between a screen's major regions.
    static let space6: CGFloat = 32
    /// 48 pt. Above a screen's closing action.
    static let space7: CGFloat = 48

    // MARK: - Radius

    /// 8 pt. Chips and inline notes.
    static let radiusSmall: CGFloat = 8
    /// 14 pt. Cards and controls.
    static let radiusMedium: CGFloat = 14
    /// 22 pt. Sheets and hero cards.
    static let radiusLarge: CGFloat = 22
    /// Fully rounded. Badges and pills.
    static let radiusPill: CGFloat = 999

    // MARK: - Control metrics

    /// 48 pt. No actionable control is ever smaller than this in either dimension.
    static let touchTargetMinimum: CGFloat = 48
    /// 3 pt sky-blue ring.
    static let focusRingWidth: CGFloat = 3
    /// 3 pt of clear space between the control and its ring.
    static let focusRingOffset: CGFloat = 3
    /// A pressed control scales to 97%.
    static let pressedScale: CGFloat = 0.97
    /// Bottom-sheet detents, as fractions of screen height: peek, half, full.
    static let sheetStops: [CGFloat] = [0.18, 0.54, 0.92]

    // MARK: - Elevation
    //
    // Derived. The library ships no shadow token. What it does fix is the colour of shade: the ink
    // is deep indigo, so a neutral black shadow reads as a different, greyer system sitting under
    // an indigo one. The web build's card shadow — a single 10/30 drop at 16% — is the geometry
    // this ladder keeps; the colour is swapped to the approved `indigo900` and the ladder extended
    // to the three heights the boards actually use, plus the compressed shadow the motion spec
    // calls for on press.

    enum Elevation {
        /// A keyline-and-a-hint: chips, inline notes.
        case resting
        /// Cards and controls sitting on the canvas.
        case raised
        /// Sheets, and a selected pin.
        case lifted
        /// What `raised` becomes while a control is held down.
        case pressed

        var radius: CGFloat {
            switch self {
            case .resting: return 6
            case .raised: return 30
            case .lifted: return 46
            case .pressed: return 3
            }
        }

        var yOffset: CGFloat {
            switch self {
            case .resting: return 2
            case .raised: return 10
            case .lifted: return 18
            case .pressed: return 1
            }
        }

        var opacity: Double {
            switch self {
            case .resting: return 0.10
            case .raised: return 0.16
            case .lifted: return 0.20
            case .pressed: return 0.12
            }
        }
    }
}

extension View {
    /// Drop the named EntryMap shadow.
    func entryMapElevation(_ elevation: EntryMapLayout.Elevation) -> some View {
        shadow(
            color: EntryMapPalette.indigo900.opacity(elevation.opacity),
            radius: elevation.radius,
            x: 0,
            y: elevation.yOffset)
    }

    /// A card: white ground, medium radius, keyline, raised.
    func entryMapCard(
        padding: CGFloat = EntryMapLayout.space4,
        radius: CGFloat = EntryMapLayout.radiusMedium,
        elevation: EntryMapLayout.Elevation = .raised
    ) -> some View {
        self
            .padding(padding)
            .background(EntryMapPalette.card, in: RoundedRectangle(cornerRadius: radius))
            .overlay(
                RoundedRectangle(cornerRadius: radius)
                    .strokeBorder(EntryMapPalette.edge, lineWidth: 1))
            .entryMapElevation(elevation)
    }

    /// Guarantee the 48 pt minimum in both dimensions without changing what the control looks like.
    func entryMapTouchTarget() -> some View {
        frame(
            minWidth: EntryMapLayout.touchTargetMinimum,
            minHeight: EntryMapLayout.touchTargetMinimum)
            .contentShape(Rectangle())
    }
}
