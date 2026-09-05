import SwiftUI

/// Xcode previews of the whole layer, so the first person on a Mac can compare it to the boards
/// without running the app or building a screen.
///
/// Everything on this repo's CI is Linux and Python, so nothing here has ever been compiled or
/// drawn. These previews are the fastest way to find out what that cost.
/// One row of the pin gallery: a context, and the three tiers drawn at its sizes.
private struct EntryMapGalleryRow: Identifiable {
    let id: String
    let context: EntryMapPinContext

    static let all = [
        EntryMapGalleryRow(id: "Overview", context: .overview),
        EntryMapGalleryRow(id: "Street", context: .street),
        EntryMapGalleryRow(id: "Selected", context: .selected),
        EntryMapGalleryRow(id: "Receipt", context: .receipt),
    ]
}

#Preview("Pins") {
    ScrollView {
        VStack(alignment: .leading, spacing: EntryMapLayout.space5) {
            ForEach(EntryMapGalleryRow.all) { row in
                VStack(alignment: .leading, spacing: EntryMapLayout.space2) {
                    Text(row.id)
                        .entryMapText(EntryMapTypography.overline)
                        .foregroundStyle(EntryMapPalette.subduedInk)
                    HStack(alignment: .bottom, spacing: EntryMapLayout.space5) {
                        ForEach(EntryMapTrustTier.allCases, id: \.self) { tier in
                            EntryMapPin(
                                tier: tier,
                                context: row.context,
                                isSelected: row.context == .selected)
                        }
                    }
                }
            }

            Text("Halos and overlays")
                .entryMapText(EntryMapTypography.overline)
                .foregroundStyle(EntryMapPalette.subduedInk)
            HStack(spacing: EntryMapLayout.space5) {
                EntryMapPin(tier: .ownerConfirmed, matchState: .good)
                EntryMapPin(tier: .scannedOnSite, matchState: .partial)
                EntryMapPin(tier: .estimated, matchState: .unknown)
                EntryMapPin(tier: .scannedOnSite, needsRecheck: true)
                EntryMapPin(tier: .scannedOnSite, context: .liveScanDrop)
            }
        }
        .padding(EntryMapLayout.space5)
    }
    .background(EntryMapPalette.ground)
}

#Preview("Controls") {
    VStack(spacing: EntryMapLayout.space4) {
        Button("Continue") {}
            .buttonStyle(EntryMapButtonStyle(role: .primary))
        Button("Not now") {}
            .buttonStyle(EntryMapButtonStyle(role: .secondary))
        Button("Scan an entrance") {}
            .buttonStyle(EntryMapButtonStyle(role: .scan))
        Button("Continue") {}
            .buttonStyle(
                EntryMapButtonStyle(
                    role: .primary,
                    isUnavailable: true,
                    unavailableExplanation: "Pick an entrance first."))
        Button("Suggest a correction") {}
            .buttonStyle(EntryMapButtonStyle(role: .quiet))
    }
    .padding(EntryMapLayout.space5)
    .background(EntryMapPalette.ground)
}

#Preview("Badges and icons") {
    ScrollView {
        VStack(alignment: .leading, spacing: EntryMapLayout.space4) {
            EntryMapBadge(kind: .estimated, text: "Estimated")
            EntryMapBadge(kind: .scannedOnSite, text: "Scanned on-site")
            EntryMapBadge(kind: .ownerConfirmed, text: "Owner-confirmed")
            EntryMapBadge(kind: .freshnessCurrent, text: "Checked this month")
            EntryMapBadge(kind: .freshnessRecheck, text: "Worth a re-check")
            EntryMapConfidenceDots(filled: 2)

            LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 6)) {
                ForEach(EntryMapIcon.allCases, id: \.self) { icon in
                    EntryMapIconView(icon: icon, size: 28)
                }
            }

            EntryMapBrandMark()
        }
        .padding(EntryMapLayout.space5)
    }
    .background(EntryMapPalette.ground)
}
