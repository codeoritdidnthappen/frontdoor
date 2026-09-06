import SwiftUI

/// The twelve official EntryMap colours, and the semantic roles this app spends them on.
///
/// Source of truth: `docs/design/entrymap/design-tokens.json` and `contrast-report.md`, copied
/// verbatim from the approved asset library. `tests/test_ios_design_system.py` reads both and
/// fails if a hex here stops matching the token file, so this list cannot quietly drift.
///
/// **Every ratio below is recomputed against these values.** The library's `2026-09-05` version
/// moved ten of the eleven colours it previously named — only white stayed — so no figure measured
/// against the retired set carries over. The report also now sets a **7:1 floor for body copy**.
/// Labels on the violet were the pairing that could not meet it: 6.42:1 against the retired violet,
/// restricted to large or bold labels and graphic marks. Against the canonical violet the same
/// pairing is 7.38:1 `onViolet` on `violet600`, and it clears the floor.
///
/// Every figure in this layer is written so a test can recompute it. Inside a role's own
/// documentation a figure names the background only — "ratio:1 on `card`" — and takes its
/// foreground from the role being documented; anywhere else it names both — "ratio:1 `ink` on
/// `card`". A figure that is deliberately historical carries the word "retired" on its line, and
/// `tests/test_ios_design_system.py` refuses a figure written in any other way.
///
/// **Light-only, deliberately.** The approved library defines one surface system: deep indigo ink
/// on white or pale lavender, with sky, marigold and violet as accents. It approves no dark-surface
/// pairing except `sky400`/`indigo900` and `marigold400`/`indigo900`, which cover the wordmark and
/// information cues — not body text, not cards, not keylines. Inventing the missing eight roles
/// here would be inventing colour outside the approved set, which is exactly what this layer exists
/// to stop. So every EntryMap surface paints its own ground explicitly and does not inherit the
/// system's. When the library ships a dark ramp, it lands here as a second set of role values.
enum EntryMapPalette {

    // MARK: - The twelve official colours
    //
    // Named exactly as the token file names them. Nothing else in the app may spell a hex.

    static let indigo900 = Color(entryMapHex: 0x1E1142)
    static let indigo800 = Color(entryMapHex: 0x28165A)
    static let violet600 = Color(entryMapHex: 0x4F34DB)
    static let violet800 = Color(entryMapHex: 0x38239B)
    static let sky400 = Color(entryMapHex: 0x76BCFD)
    static let sky700 = Color(entryMapHex: 0x1B6599)
    static let marigold400 = Color(entryMapHex: 0xFDB327)
    static let amber700 = Color(entryMapHex: 0x8C5400)
    static let lavenderPath = Color(entryMapHex: 0xCFBCEE)
    static let lavender100 = Color(entryMapHex: 0xF5F2FC)
    static let lavender200 = Color(entryMapHex: 0xE8E1F7)
    static let white = Color(entryMapHex: 0xFFFFFF)

    // MARK: - Semantic roles
    //
    // Every role below is one of the twelve. Where the contrast report names an approved pairing
    // the role is that pairing; where it does not, the derivation is stated.
    //
    // `indigo800` has no role. It is an official token, so it is declared above, but nothing in the
    // library draws it — it appears in the token file and in no piece of artwork, no control state
    // and no row of the contrast report. Naming a role for it here would be inventing a use, so it
    // stays a declared colour with nothing spending it until the library says what it is for.

    /// Body text, headings and icons. 17.30:1 on `card`, 15.64:1 on `ground`.
    static let ink = indigo900

    /// Secondary copy, labels and links.
    ///
    /// Derived: the library has no "muted ink" token. The obvious move — indigo at reduced opacity
    /// — is the wrong one, because the contrast report requires body copy to hold 7:1 and an
    /// opacity-derived grey stops doing that well before it reads as subdued. `violet800` is an
    /// official colour the report already approves for "links, labels, UI icons", and it holds
    /// 11.16:1 on `card`, so subdued copy is a hue change rather than a contrast loss.
    static let subduedInk = violet800

    /// The deeper violet as a mark rather than as copy: the pressed step of an accented control,
    /// the confidence ring's stroke, the outlined check beside an owner-confirmed pin.
    ///
    /// Same colour as ``subduedInk``, named separately because it is a different decision — this
    /// one is about strokes and fills, and a change to either role must not silently move the
    /// other. Read off the approved artwork: `docs/design/entrymap/svg/badges/confidence-1.svg` and
    /// siblings stroke the confidence ring in it, and the library's control masters fill and stroke
    /// the pressed primary in it where the resting one is `violet600`. 11.16:1 on `card`, so a
    /// label may sit on it.
    static let deepAccent = violet800

    /// The map and screen canvas. The library calls `lavender100` "canvas and quiet supporting
    /// surfaces".
    static let ground = lavender100

    /// Sheets and cards. The library calls `white` "sheets, cards, and dark-surface type".
    static let card = white

    /// Keylines and dividers.
    ///
    /// Derived: no token names a border colour, but the approved badge artwork draws the card
    /// keyline as `stroke="#E8E1F7"` (`docs/design/entrymap/svg/badges/confidence-1.svg` and
    /// siblings). So the edge role is read off the approved artwork rather than invented.
    static let edge = lavender200

    /// The line the map draws an entrance path with.
    ///
    /// `lavenderPath` is the sampled approved entrance path, and it is **not** a surface. The
    /// library separates it from the two UI lavenders on purpose: the web build spent one lavender
    /// family on both jobs, so every screen came out carrying a purple cast with white slots cut
    /// into it. `ground` and `edge` are the surface lavenders; this one paints a line, and nothing
    /// that fills a background may reach for it. `tests/test_ios_design_system.py` enforces that.
    ///
    /// It has no contrast row because it is not a foreground on anything: at 1.57:1 on `ground` it
    /// could not carry a mark, and the map states the path by its shape.
    static let pathLine = lavenderPath

    /// The dark surface the brand lockup and the wordmark sit on.
    static let darkGround = indigo900

    /// Type and cues on `darkGround`. 8.55:1 on `darkGround`.
    static let onDarkGround = sky400

    /// Labels on `violet600`. 7.38:1 on `violet600`, which clears the report's 7:1 body floor.
    ///
    /// This pairing sat at 6.42:1 against the retired violet and was restricted to large or bold
    /// labels and graphic marks; the canonical violet is what lifts it. ``EntryMapButtonStyle``
    /// still sets primary labels bold and never below 17 pt, which is now a legibility choice
    /// rather than the thing holding the pairing up.
    static let onViolet = white

    /// Labels on `marigold400`. 9.60:1 on `marigold400`.
    static let onMarigold = indigo900

    /// Freshness marks. 6.21:1 on `card` — below the 7:1 body floor, which is why the report calls
    /// `amber700` a non-body colour: it may carry an icon, but small text beside it is set in
    /// `ink`.
    static let freshness = amber700

    /// A state that is information rather than a claim: "not yet seen", the estimated tier's
    /// symbol and ring, the unknown-match halo.
    ///
    /// The library reaches for `sky700` at every one of those places — `svg/pins/estimated.svg`,
    /// `svg/halos/unknown-match.svg`, `svg/feature-icons/unknown.svg` — and this layer was spelling
    /// the token at each call site instead of naming what it meant. 6.24:1 on `card`, below the 7:1
    /// body floor, so like `freshness` it carries marks and symbols and never small body copy; the
    /// library never lets a state be told by colour alone, and each of these is also dashed or
    /// dotted.
    static let informationInk = sky700

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
