import SwiftUI
import UIKit

/// The EntryMap type system: two bundled families, a named scale, and Dynamic Type throughout.
///
/// Source of truth: `docs/design/entrymap/design-tokens.json` names the UI family and the three
/// weights. It no longer names a wordmark family: the library's position is now that the wordmark
/// is approved artwork and is never set as live text, so ``Face/wordmark`` and ``wordmark`` stay
/// only as the fallback for a context that cannot draw the artwork, and ``EntryMapBrandMark`` is
/// still the way to show the lockup. The sizes below are not in the token file either — the library
/// ships no numeric type scale — so they are derived, and each derivation is stated against the
/// artwork it came from.
///
/// **Two things here are not decoration.**
///
/// Atkinson's figures are proportional. A column of counts or distances set in it does not line up,
/// and the misalignment reads as sloppy data rather than as a font setting. So every style that can
/// land in a column carries ``EntryMapTextStyle/tabularNumerals`` and applies `monospacedDigit()`.
/// Picking the wrong style for a number is the mistake this scale is shaped to prevent.
///
/// And every size is declared `relativeTo:` a system text style, so it scales with the reader's
/// Dynamic Type setting. This app's subject is accessibility; a fixed point size in it would be
/// indefensible.
enum EntryMapTypography {

    /// The four bundled faces.
    ///
    /// Weights: the token file names 400 regular, 600 medium, 750 bold. 750 has no static instance,
    /// so `bold` ships the 700 static and the 50-unit difference is accepted rather than faked by
    /// synthetic emboldening. A Mac must confirm these PostScript names against the files actually
    /// dropped into `Resources/Fonts` — `Font.custom` falls back to the system face in silence when
    /// a name is wrong, and silence is the failure mode to watch for here.
    enum Face: String, CaseIterable {
        /// Atkinson Hyperlegible Next, 400. All UI copy.
        case regular = "AtkinsonHyperlegibleNext-Regular"
        /// Atkinson Hyperlegible Next, 600. Labels, buttons, emphasis.
        case semibold = "AtkinsonHyperlegibleNext-SemiBold"
        /// Atkinson Hyperlegible Next, 700 (standing in for the token's 750). Headings.
        case bold = "AtkinsonHyperlegibleNext-Bold"
        /// Nunito Sans, 800. The joined lowercase wordmark only — never UI copy.
        case wordmark = "NunitoSans-ExtraBold"

        /// The file each face expects in `Resources/Fonts`. `project.yml`'s `UIAppFonts` list is
        /// checked against this by `tests/test_ios_design_system.py`, so a font can never be
        /// registered under one name and asked for under another.
        var fileName: String {
            switch self {
            case .regular: return "AtkinsonHyperlegibleNext-Regular.ttf"
            case .semibold: return "AtkinsonHyperlegibleNext-SemiBold.ttf"
            case .bold: return "AtkinsonHyperlegibleNext-Bold.ttf"
            case .wordmark: return "NunitoSans-ExtraBold.ttf"
            }
        }
    }

    // MARK: - The scale
    //
    // Derived. The library gives one direct measurement — badge labels are 16 px at weight 650 —
    // and the boards set body copy one step below their headings. `body` is therefore 16 and the
    // rest is a 1.2 ratio rounded to whole points, with `caption` and `overline` pulled in to the
    // 13/11 the boards use for receipt rows and section eyebrows.

    /// The scan verdict and the measured rise: read from the back of a room.
    static let display = EntryMapTextStyle(
        size: 44, face: .bold, relativeTo: .largeTitle,
        lineHeightMultiple: 1.05, tracking: -0.6, tabularNumerals: true)

    /// Screen titles.
    static let title = EntryMapTextStyle(
        size: 26, face: .bold, relativeTo: .title,
        lineHeightMultiple: 1.2, tracking: -0.3, tabularNumerals: false)

    /// Section headings inside a screen or sheet.
    static let heading = EntryMapTextStyle(
        size: 20, face: .bold, relativeTo: .title3,
        lineHeightMultiple: 1.25, tracking: -0.2, tabularNumerals: false)

    /// Row titles, control labels, anything that needs weight without size.
    static let subheading = EntryMapTextStyle(
        size: 17, face: .semibold, relativeTo: .headline,
        lineHeightMultiple: 1.3, tracking: 0, tabularNumerals: false)

    /// Running copy.
    static let body = EntryMapTextStyle(
        size: 16, face: .regular, relativeTo: .body,
        lineHeightMultiple: 1.45, tracking: 0, tabularNumerals: false)

    /// Supporting copy under a row or heading.
    static let callout = EntryMapTextStyle(
        size: 15, face: .regular, relativeTo: .callout,
        lineHeightMultiple: 1.4, tracking: 0, tabularNumerals: false)

    /// Receipt lines, badge text, metadata.
    static let caption = EntryMapTextStyle(
        size: 13, face: .semibold, relativeTo: .caption,
        lineHeightMultiple: 1.35, tracking: 0.2, tabularNumerals: false)

    /// The uppercase eyebrow above a group.
    static let overline = EntryMapTextStyle(
        size: 11, face: .bold, relativeTo: .caption2,
        lineHeightMultiple: 1.3, tracking: 0.9, tabularNumerals: false)

    // MARK: - Numerals in columns
    //
    // Same sizes as `body` and `caption`, tabular. Use these — not their proportional twins — for
    // counts, distances, rise readings, confidence figures, timestamps, anything stacked.

    /// A number in running copy that sits above or below another number.
    static let bodyNumeric = EntryMapTextStyle(
        size: 16, face: .regular, relativeTo: .body,
        lineHeightMultiple: 1.45, tracking: 0, tabularNumerals: true)

    /// A row title carrying a figure — a distance, a count — above or below another row title.
    static let subheadingNumeric = EntryMapTextStyle(
        size: 17, face: .semibold, relativeTo: .headline,
        lineHeightMultiple: 1.3, tracking: 0, tabularNumerals: true)

    /// A number in a receipt row or a badge.
    static let captionNumeric = EntryMapTextStyle(
        size: 13, face: .semibold, relativeTo: .caption,
        lineHeightMultiple: 1.35, tracking: 0.2, tabularNumerals: true)

    /// The wordmark, when it is reconstructed in code rather than drawn from the approved artwork.
    /// Prefer ``EntryMapBrandMark``, which uses the artwork.
    static let wordmark = EntryMapTextStyle(
        size: 28, face: .wordmark, relativeTo: .title,
        lineHeightMultiple: 1.1, tracking: -0.8, tabularNumerals: false)
}

/// One step of the scale: size, face, the system style it scales against, leading and tracking.
struct EntryMapTextStyle {
    let size: CGFloat
    let face: EntryMapTypography.Face
    let relativeTo: Font.TextStyle
    let lineHeightMultiple: CGFloat
    let tracking: CGFloat
    let tabularNumerals: Bool

    /// The font, scaled by the reader's Dynamic Type setting.
    var font: Font {
        let base = Font.custom(face.rawValue, size: size, relativeTo: relativeTo)
        return tabularNumerals ? base.monospacedDigit() : base
    }

    /// Extra leading, in points, at the reader's current text size.
    ///
    /// SwiftUI's `lineSpacing` is added to the font's own line height rather than replacing it, so
    /// the multiple is converted against a natural leading of 1.2 — which is what both families
    /// report. A Mac should check the shipped files' ascent + descent + line gap and correct the
    /// 1.2 here if they differ; the visible symptom would be paragraphs set slightly too open.
    var scaledLineSpacing: CGFloat {
        max(0, scaled(size) * (lineHeightMultiple - 1.2))
    }

    /// Tracking, in points, at the reader's current text size.
    var scaledTracking: CGFloat { scaled(tracking) }

    private func scaled(_ value: CGFloat) -> CGFloat {
        UIFontMetrics(forTextStyle: relativeTo.uiTextStyle).scaledValue(for: value)
    }
}

extension View {
    /// Apply a step of the EntryMap scale: font, leading and tracking together.
    ///
    /// Always this, never `.font(...)` on its own — leading and tracking are part of the step, and
    /// a step applied without them is a different step.
    func entryMapText(_ style: EntryMapTextStyle) -> some View {
        self
            .font(style.font)
            .lineSpacing(style.scaledLineSpacing)
            .tracking(style.scaledTracking)
    }
}

extension Font.TextStyle {
    /// The UIKit twin, so `UIFontMetrics` can scale leading and tracking the same way
    /// `Font.custom(_:size:relativeTo:)` scales the size.
    fileprivate var uiTextStyle: UIFont.TextStyle {
        switch self {
        case .largeTitle: return .largeTitle
        case .title: return .title1
        case .title2: return .title2
        case .title3: return .title3
        case .headline: return .headline
        case .subheadline: return .subheadline
        case .body: return .body
        case .callout: return .callout
        case .footnote: return .footnote
        case .caption: return .caption1
        case .caption2: return .caption2
        @unknown default: return .body
        }
    }
}
