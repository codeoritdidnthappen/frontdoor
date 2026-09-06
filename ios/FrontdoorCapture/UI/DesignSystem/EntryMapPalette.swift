import SwiftUI

/// The eleven official EntryMap colours, and the semantic roles this app spends them on.
///
/// Source of truth: `docs/design/entrymap/design-tokens.json` and `contrast-report.md`, copied
/// verbatim from the approved asset library. `tests/test_ios_design_system.py` reads both and
/// fails if a hex here stops matching the token file, so this list cannot quietly drift.
///
/// **Light-only, deliberately.** The approved library defines one surface system: deep indigo ink
/// on white or pale lavender, with sky, marigold and violet as accents. It approves no dark-surface
/// pairing except `sky400`/`indigo900` and `marigold400`/`indigo900`, which cover the wordmark and
/// information cues — not body text, not cards, not keylines. Inventing the missing eight roles
/// here would be inventing colour outside the approved set, which is exactly what this layer exists
/// to stop. So every EntryMap surface paints its own ground explicitly and does not inherit the
/// system's. When the library ships a dark ramp, it lands here as a second set of role values.
enum EntryMapPalette {

    // MARK: - The eleven official colours
    //
    // Named exactly as the token file names them. Nothing else in the app may spell a hex.

    static let indigo900 = Color(entryMapHex: 0x17103D)
    static let indigo800 = Color(entryMapHex: 0x211054)
    static let violet600 = Color(entryMapHex: 0x5B35F5)
    static let violet800 = Color(entryMapHex: 0x4020B5)
    static let sky400 = Color(entryMapHex: 0x69B7FF)
    static let sky700 = Color(entryMapHex: 0x1266A6)
    static let marigold400 = Color(entryMapHex: 0xFFBF24)
    static let amber700 = Color(entryMapHex: 0x9A5700)
    static let lavender100 = Color(entryMapHex: 0xF2EEFF)
    static let lavender200 = Color(entryMapHex: 0xE2DAFF)
    static let white = Color(entryMapHex: 0xFFFFFF)

    // MARK: - Semantic roles
    //
    // Every role below is one of the eleven. Where the contrast report names an approved pairing
    // the role is that pairing; where it does not, the derivation is stated.

    /// Body text, headings and icons. 17.83:1 on `card`, 15.66:1 on `ground`.
    static let ink = indigo900

    /// Secondary copy, labels and links.
    ///
    /// Derived: the library has no "muted ink" token. The obvious move — indigo at reduced opacity
    /// — is the wrong one, because the contrast report requires body copy to hold 7:1 and an
    /// opacity-derived grey stops doing that well before it reads as subdued. `violet800` is an
    /// official colour the report already approves for "links, labels, UI icons" at 10.04:1 on
    /// white, so subdued copy is a hue change rather than a contrast loss.
    static let subduedInk = violet800

    /// The map and screen canvas. The library calls `lavender100` "canvas and quiet supporting
    /// surfaces".
    static let ground = lavender100

    /// Sheets and cards. The library calls `white` "sheets, cards, and dark-surface type".
    static let card = white

    /// Keylines and dividers.
    ///
    /// Derived: no token names a border colour, but the approved badge artwork draws the card
    /// keyline as `stroke="#E2DAFF"` (`docs/design/entrymap/svg/badges/confidence-1.svg` and
    /// siblings). So the edge role is read off the approved artwork rather than invented.
    static let edge = lavender200

    /// The dark surface the brand lockup and the wordmark sit on.
    static let darkGround = indigo900

    /// Type and cues on `darkGround`. 8.33:1.
    static let onDarkGround = sky400

    /// Labels on `violet600`. 6.42:1 — approved for large or bold control labels and graphic marks
    /// only, which is why ``EntryMapButtonStyle`` sets primary labels bold and never below 17 pt.
    static let onViolet = white

    /// Labels on `marigold400`. 10.81:1.
    static let onMarigold = indigo900

    /// Freshness marks. The report calls `amber700` a non-body colour: it may carry an icon, but
    /// small text beside it is set in `ink`.
    static let freshness = amber700

    /// The keyboard focus ring. The motion spec: "3 px sky-blue outer ring with 3 px offset".
    static let focusRing = sky400

    /// The veil the map takes at a full-height sheet. The motion spec: "a 7% deep-indigo veil".
    static let veil = indigo900.opacity(0.07)
}

extension Color {
    /// sRGB from a 24-bit token value. Private to the design system on purpose — a hex literal
    /// anywhere else in the app is a colour that never went through the approved set.
    fileprivate init(entryMapHex value: UInt32) {
        self.init(
            .sRGB,
            red: Double((value >> 16) & 0xFF) / 255,
            green: Double((value >> 8) & 0xFF) / 255,
            blue: Double(value & 0xFF) / 255,
            opacity: 1)
    }
}
