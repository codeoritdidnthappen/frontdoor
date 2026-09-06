import SwiftUI

/// The approved library's icon set, held as the SVG masters' own path data.
///
/// Every case's raw value is the master it came from, relative to `docs/design/entrymap/svg/`.
/// `tests/test_ios_design_system.py` opens each of those files and fails if a single character of
/// geometry here differs from it, so this catalogue cannot drift from the approved artwork and no
/// icon can be quietly redrawn by hand.
///
/// All of them are 32 x 32 line art, stroked, round caps and joins. The stroke colour is a token,
/// not part of the glyph, so the call site picks a pairing the contrast report approves.
enum EntryMapIcon: String, CaseIterable {

    // MARK: - UI icons
    //
    // Navigation, actions, trust and receipt controls. Stroke 2.3.

    case camera = "ui-icons/camera"
    case checkOutline = "ui-icons/check-outline"
    case chevronRight = "ui-icons/chevron-right"
    case close = "ui-icons/close"
    case confidence = "ui-icons/confidence"
    case correction = "ui-icons/correction"
    case filters = "ui-icons/filters"
    case freshness = "ui-icons/freshness"
    case info = "ui-icons/info"
    case location = "ui-icons/location"
    case map = "ui-icons/map"
    case menu = "ui-icons/menu"
    case myNeeds = "ui-icons/my-needs"
    case person = "ui-icons/person"
    case photo = "ui-icons/photo"
    case profile = "ui-icons/profile"
    case receipt = "ui-icons/receipt"
    case scan = "ui-icons/scan"
    case search = "ui-icons/search"
    case storefront = "ui-icons/storefront"

    // MARK: - Feature icons
    //
    // The seven visually confirmable entrance features, plus "not yet seen". Stroke 2.2.

    case accessibilitySignage = "feature-icons/accessibility-signage"
    case autoDoorButton = "feature-icons/auto-door-button"
    case clearApproach = "feature-icons/clear-approach"
    case easyGripHandle = "feature-icons/easy-grip-handle"
    case rampVisible = "feature-icons/ramp-visible"
    case stepFreeEntry = "feature-icons/step-free-entry"
    case wideDoor = "feature-icons/wide-door"
    case featureUnknown = "feature-icons/unknown"

    /// The master viewBox every icon is drawn in.
    static let viewBox = CGSize(width: 32, height: 32)

    /// Stroke width in master units, as the SVG group sets it.
    var strokeWidth: CGFloat {
        switch self {
        case .accessibilitySignage, .autoDoorButton, .clearApproach, .easyGripHandle,
             .rampVisible, .stepFreeEntry, .wideDoor, .featureUnknown:
            return 2.2
        default:
            return 2.3
        }
    }

    /// The colour the master draws the icon in.
    ///
    /// Every icon but one is `#38239B`, which is ``EntryMapPalette/subduedInk``. "Not yet seen" is
    /// `#1B6599` — ``EntryMapPalette/informationInk`` — because it is an informational state rather
    /// than a claim, and the library never lets a state be told by colour alone: it is also the
    /// only dashed icon.
    var defaultTint: Color {
        self == .featureUnknown ? EntryMapPalette.informationInk : EntryMapPalette.subduedInk
    }

    var glyphs: [EntryMapGlyph] {
        switch self {
        case .camera:
            return [
                .path("M5 10h5l2-4h8l2 4h5v17H5Z"),
                .circle(x: 16, y: 18, radius: 5),
            ]
        case .checkOutline:
            return [
                .circle(x: 16, y: 16, radius: 13),
                .path("m9 16 5 5 10-12"),
            ]
        case .chevronRight:
            return [.path("m11 5 11 11-11 11")]
        case .close:
            return [.path("m7 7 18 18M25 7 7 25")]
        case .confidence:
            return [.path("M7 27V19M13 27V14M19 27V9M25 27V5")]
        case .correction:
            return [
                .path("m6 25 5-1 14-14-4-4L7 20Z"),
                .path("m18 9 4 4M5 28h22"),
            ]
        case .filters:
            return [
                .path("M5 8h22M9 16h18M13 24h14"),
                .circle(x: 9, y: 8, radius: 2),
                .circle(x: 13, y: 16, radius: 2),
                .circle(x: 17, y: 24, radius: 2),
            ]
        case .freshness:
            return [
                .circle(x: 16, y: 16, radius: 12),
                .path("M16 9v8l5 3"),
            ]
        case .info:
            return [
                .circle(x: 16, y: 16, radius: 12),
                .path("M16 14v8M16 9h.01"),
            ]
        case .location:
            return [
                .path("M16 29S6 21 6 12a10 10 0 0 1 20 0c0 9-10 17-10 17Z"),
                .circle(x: 16, y: 12, radius: 3),
            ]
        case .map:
            return [
                .path("m4 7 7-3 7 3 7-3v22l-7 3-7-3-7 3Z"),
                .path("M11 4v22M18 7v22"),
            ]
        case .menu:
            return [.path("M5 8h22M5 16h22M5 24h22")]
        case .myNeeds:
            return [.path("M16 28S4 20 4 11c0-7 9-10 12-4 3-6 12-3 12 4 0 9-12 17-12 17Z")]
        case .person:
            return [
                .circle(x: 16, y: 9, radius: 5),
                .path("M7 28c1-9 4-13 9-13s8 4 9 13Z"),
            ]
        case .photo:
            return [
                .rect(x: 4, y: 6, width: 24, height: 21, radius: 3),
                .circle(x: 12, y: 13, radius: 3),
                .path("m7 24 7-7 5 5 3-3 4 5"),
            ]
        case .profile:
            return [
                .circle(x: 16, y: 10, radius: 6),
                .path("M5 29c1-9 5-13 11-13s10 4 11 13Z"),
            ]
        case .receipt:
            return [
                .path("M8 4h16v25l-4-3-4 3-4-3-4 3Z"),
                .path("M12 10h8M12 15h8M12 20h5"),
            ]
        case .scan:
            return [
                .path("M5 11V6a2 2 0 0 1 2-2h5M25 11V6a2 2 0 0 0-2-2h-5M5 21v5a2 2 0 0 0 2 2h5M25 21v5a2 2 0 0 1-2 2h-5"),
                .path("M10 15h12M10 20h12"),
            ]
        case .search:
            return [
                .circle(x: 14, y: 14, radius: 9),
                .path("m21 21 7 7"),
            ]
        case .storefront:
            return [
                .path("M5 13h22L24 6H8Z"),
                .path("M7 13v15h18V13M12 28v-9h8v9"),
                .path("M5 13c0 4 5 5 7 2 3 3 6 3 8 0 3 3 6 3 8-2"),
            ]
        case .accessibilitySignage:
            return [
                .rect(x: 5, y: 4, width: 22, height: 24, radius: 3),
                .circle(x: 16, y: 10, radius: 2),
                .path("M16 13v7M11 16h10M16 20l-4 6M16 20l5 6"),
            ]
        case .autoDoorButton:
            return [
                .rect(x: 5, y: 4, width: 14, height: 24, radius: 2),
                .circle(x: 23, y: 16, radius: 5),
                .path("M23 13v6M20 16h6"),
            ]
        case .clearApproach:
            return [
                .path("M5 27 12 5h8l7 22Z"),
                .path("M16 9v4M16 18v4"),
            ]
        case .easyGripHandle:
            return [
                .rect(x: 5, y: 4, width: 15, height: 24, radius: 2),
                .path("M18 15h7M25 12v8"),
            ]
        case .rampVisible:
            return [
                .path("M4 26h24L28 12 4 26Z"),
                .path("M9 23h15M14 20h10M19 17h5"),
            ]
        case .stepFreeEntry:
            return [.path("M5 25h22M8 25V9h15v16M13 17h8")]
        case .wideDoor:
            return [.path("M4 27V5h10v22M18 27V5h10v22M14 16h4")]
        case .featureUnknown:
            return [
                .path("M11 11a5 5 0 1 1 8 4c-2 1-3 3-3 5M16 26h.01"),
                // stroke-dasharray="4 4" in the master.
                .circle(x: 16, y: 16, radius: 13, dash: [4, 4]),
            ]
        }
    }
}

/// An icon at a given size, in a token colour.
///
/// Decorative by default: an icon in this app always sits beside its own label, and a second
/// spoken copy of that label is noise. Pass `label` only where the icon is the whole control.
struct EntryMapIconView: View {
    let icon: EntryMapIcon
    var size: CGFloat = 24
    var tint: Color?
    var label: String?

    var body: some View {
        let scale = size / EntryMapIcon.viewBox.width
        ZStack {
            ForEach(icon.glyphs.indices, id: \.self) { index in
                let glyph = icon.glyphs[index]
                EntryMapVectorShape(glyph: glyph, viewBox: EntryMapIcon.viewBox)
                    .stroke(
                        tint ?? icon.defaultTint,
                        style: StrokeStyle(
                            lineWidth: icon.strokeWidth * scale,
                            lineCap: .round,
                            lineJoin: .round,
                            dash: glyph.dash.map { $0 * scale }))
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(label == nil)
        .accessibilityLabel(label ?? "")
    }
}
