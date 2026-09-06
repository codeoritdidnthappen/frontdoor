import SwiftUI
import UIKit

/// The chrome SwiftUI supplies, brought under the design system.
///
/// A screen can style every view it writes and still not look like EntryMap, because a `Form`
/// draws a great deal that the screen never names: section headers and footers, `Picker` and
/// `LabeledContent` rows, toolbar buttons, the navigation title. All of it arrives in the system
/// font and the system greys. That is what the restyle missed -- the guards check for styling a
/// screen *writes*, and none of this is written anywhere.
extension View {

    /// A `Form` on EntryMap's ground, with EntryMap's face reaching the rows.
    ///
    /// The font and foreground go on as environment values rather than per-row, which is the only
    /// way to reach a `Picker`'s label or a `LabeledContent`'s title -- those views are built by
    /// SwiftUI and take the font of whatever contains them.
    ///
    /// The tint is deliberately not here, and not at the root either. Both were tried:
    ///
    /// - On the Form, "Close" and "Import" stay system blue. A toolbar is attached to the
    ///   content but is not inside it, so the Form's environment never reaches it.
    /// - At the root, nothing is tinted at all, and the picker values that the Form-level tint
    ///   had coloured go grey. `.tint` does not survive the sheet boundary.
    ///
    /// It goes on each `NavigationStack`, which is the one ancestor of both the toolbar and the
    /// content. See ``EntryMapSheet`` --- each screen carries a one-line pointer back here rather
    /// than its own copy of this.
    func entryMapForm() -> some View {
        self
            .scrollContentBackground(.hidden)
            .background(EntryMapPalette.ground)
            .entryMapText(EntryMapTypography.body)
            .foregroundStyle(EntryMapPalette.ink)
    }

    /// A section header in the library's eyebrow style.
    func entryMapSectionHeader() -> some View {
        self
            .entryMapText(EntryMapTypography.overline)
            .foregroundStyle(EntryMapPalette.subduedInk)
            .textCase(nil)
    }

    /// A section footer: the explanatory line under a group.
    func entryMapSectionFooter() -> some View {
        self
            .entryMapText(EntryMapTypography.caption)
            .foregroundStyle(EntryMapPalette.subduedInk)
    }
}

/// The navigation bar, which is UIKit and cannot be reached from SwiftUI.
///
/// `.navigationTitle` renders through `UINavigationBar`, so its font is set by the appearance
/// proxy or not at all. Installed once at launch: an appearance set after a bar exists does not
/// reach it.
enum EntryMapNavigationAppearance {

    static func install() {
        let appearance = UINavigationBarAppearance()
        appearance.configureWithOpaqueBackground()
        appearance.backgroundColor = UIColor(EntryMapPalette.ground)
        appearance.shadowColor = UIColor(EntryMapPalette.edge)

        let ink = UIColor(EntryMapPalette.ink)
        appearance.titleTextAttributes = [
            .font: scaled(EntryMapTypography.subheading, textStyle: .headline),
            .foregroundColor: ink,
        ]
        appearance.largeTitleTextAttributes = [
            .font: scaled(EntryMapTypography.title, textStyle: .largeTitle),
            .foregroundColor: ink,
        ]

        UINavigationBar.appearance().standardAppearance = appearance
        UINavigationBar.appearance().scrollEdgeAppearance = appearance
        UINavigationBar.appearance().compactAppearance = appearance
    }

    /// The step's face at the reader's text size. `UIFontMetrics` is the UIKit twin of
    /// `Font.custom(_:size:relativeTo:)`, so a navigation title grows with Dynamic Type exactly
    /// as the rest of the scale does -- a bar title frozen at one size is the usual way this is
    /// got wrong.
    private static func scaled(
        _ style: EntryMapTextStyle, textStyle: UIFont.TextStyle
    ) -> UIFont {
        guard let face = UIFont(name: style.face.rawValue, size: style.size) else {
            // The face failed to register. Falling back keeps the bar readable rather than
            // crashing the app over a title; `test_the_registered_fonts_are_the_faces_the_layer
            // _asks_for` is what stops this arriving unnoticed.
            return UIFont.preferredFont(forTextStyle: textStyle)
        }
        return UIFontMetrics(forTextStyle: textStyle).scaledFont(for: face)
    }
}
