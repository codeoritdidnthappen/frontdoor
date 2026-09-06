import SwiftUI

/// The library's pill badges: trust, freshness and confidence.
///
/// The masters under `docs/design/entrymap/svg/badges/` are 48 units tall with a 22-unit radius,
/// a 2-unit keyline, a 27-unit icon and a 16 px label. Their `<text>` elements carry no copy — the
/// words belong to the call site — so a badge here takes its label rather than inventing one.
struct EntryMapBadge: View {
    enum Kind {
        case estimated
        case scannedOnSite
        case ownerConfirmed
        /// Checked recently enough to trust.
        case freshnessCurrent
        /// Old enough to be worth looking at again. Amber, never red, never a failing grade.
        case freshnessRecheck

        var fill: Color {
            switch self {
            case .estimated: return EntryMapPalette.card
            case .scannedOnSite: return EntryMapPalette.marigold400
            case .ownerConfirmed: return EntryMapPalette.violet600
            case .freshnessCurrent: return EntryMapPalette.lavender100
            case .freshnessRecheck: return EntryMapPalette.marigold400
            }
        }

        var keyline: Color {
            switch self {
            case .estimated: return EntryMapPalette.sky400
            case .scannedOnSite: return EntryMapPalette.marigold400
            case .ownerConfirmed: return EntryMapPalette.violet600
            case .freshnessCurrent: return EntryMapPalette.edge
            case .freshnessRecheck: return EntryMapPalette.indigo900
            }
        }

        /// Approved pairings only: 17.30:1 `ink` on `card`, 15.64:1 `ink` on `lavender100`,
        /// 9.60:1 `ink` on `marigold400`, 7.38:1 `onViolet` on `violet600` — which now clears the
        /// report's 7:1 body floor, so the semibold label is legibility rather than the thing
        /// holding that last pairing up.
        var label: Color {
            switch self {
            case .ownerConfirmed: return EntryMapPalette.onViolet
            case .estimated, .scannedOnSite, .freshnessCurrent, .freshnessRecheck:
                return EntryMapPalette.ink
            }
        }

        var icon: EntryMapIcon {
            switch self {
            case .estimated: return .info
            case .scannedOnSite: return .person
            case .ownerConfirmed: return .storefront
            case .freshnessCurrent, .freshnessRecheck: return .freshness
            }
        }

        var iconTint: Color {
            switch self {
            case .estimated: return EntryMapPalette.informationInk
            case .scannedOnSite, .freshnessRecheck: return EntryMapPalette.indigo900
            case .ownerConfirmed: return EntryMapPalette.card
            case .freshnessCurrent: return EntryMapPalette.deepAccent
            }
        }
    }

    let kind: Kind
    let text: String

    var body: some View {
        HStack(spacing: EntryMapLayout.space2) {
            EntryMapIconView(icon: kind.icon, size: 20, tint: kind.iconTint)
            Text(text)
                .entryMapText(EntryMapTypography.caption)
                .foregroundStyle(kind.label)
        }
        .padding(.horizontal, EntryMapLayout.space3)
        .padding(.vertical, EntryMapLayout.space2)
        .background(kind.fill, in: Capsule())
        .overlay(Capsule().strokeBorder(kind.keyline, lineWidth: 2))
        .accessibilityElement(children: .combine)
    }
}

/// Confidence as filled dots, one to three.
///
/// The count is also spoken, because three dots against three outlines is not something a screen
/// reader can infer and not something a low-vision reader should have to count.
struct EntryMapConfidenceDots: View {
    /// 1, 2 or 3.
    let filled: Int

    var body: some View {
        HStack(spacing: EntryMapLayout.space1 + 2) {
            ForEach(0..<3, id: \.self) { index in
                Circle()
                    .fill(index < filled ? EntryMapPalette.violet600 : EntryMapPalette.card)
                    .overlay(Circle().strokeBorder(EntryMapPalette.deepAccent, lineWidth: 2))
                    .frame(width: 12, height: 12)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Confidence \(filled) of 3")
    }
}
