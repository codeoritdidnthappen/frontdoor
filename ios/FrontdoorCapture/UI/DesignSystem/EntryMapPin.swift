import SwiftUI

/// The three fixed trust tiers.
///
/// Trust tier and contextual prominence are independent systems: a context may scale a pin, but
/// nothing — selection, matching, freshness, provenance — ever changes what tier it encodes. And
/// no tier is told by colour alone. Each carries a distinct shape treatment, a distinct symbol and
/// a distinct filled-ring count, so the ladder survives a colour-blind reader, a greyscale
/// projector and a screenshot.
enum EntryMapTrustTier: String, CaseIterable {
    case estimated = "pins/estimated"
    case scannedOnSite = "pins/scanned-on-site"
    case ownerConfirmed = "pins/owner-confirmed"

    /// The masters are all 104 units tall. The library's own PNG exports name a pin by its height
    /// (a "48px" Estimated pin exports 44 x 48), so the size tokens are heights and the
    /// Owner-confirmed pin is wider than its size because the outlined check sits beside it.
    static let viewBoxHeight: CGFloat = 104

    var viewBox: CGSize {
        switch self {
        // The extra 16 units carry the separate outlined check.
        case .ownerConfirmed: return CGSize(width: 112, height: 104)
        case .estimated, .scannedOnSite: return CGSize(width: 96, height: 104)
        }
    }

    /// Filled of three. The ring is the non-colour half of the encoding.
    var filledRings: Int {
        switch self {
        case .estimated: return 0
        case .scannedOnSite: return 2
        case .ownerConfirmed: return 3
        }
    }

    var accessibilityLabel: String {
        switch self {
        case .estimated: return "Estimated entrance, no confirmation of three"
        case .scannedOnSite: return "Scanned on site, two confirmations of three"
        case .ownerConfirmed: return "Owner confirmed, three confirmations of three"
        }
    }
}

/// Where a pin is being drawn, which sets its size.
///
/// Straight out of `docs/design/entrymap/pin-hierarchy.json`; pinned by
/// `tests/test_ios_design_system.py`.
enum EntryMapPinContext {
    /// Neighbourhood overview.
    case overview
    /// Street and default map.
    case street
    /// The selected entrance on the map.
    case selected
    /// Inside a card or a receipt.
    case receipt
    /// The pin the live scan drops. Always a Scanned on-site pin, always 64.
    case liveScanDrop

    func size(for tier: EntryMapTrustTier) -> CGFloat {
        switch self {
        case .overview:
            switch tier {
            case .estimated: return 32
            case .scannedOnSite: return 36
            case .ownerConfirmed: return 40
            }
        case .street:
            switch tier {
            case .estimated: return 40
            case .scannedOnSite: return 44
            case .ownerConfirmed: return 48
            }
        case .selected:
            switch tier {
            case .estimated: return 52
            case .scannedOnSite: return 56
            case .ownerConfirmed: return 60
            }
        case .receipt:
            switch tier {
            case .estimated: return 24
            case .scannedOnSite: return 28
            case .ownerConfirmed: return 32
            }
        case .liveScanDrop:
            return 64
        }
    }

    /// A mixed cluster marker, which is never a tier.
    static let clusterSize: CGFloat = 48

    /// Render order, so a map places pins the same way every time.
    ///
    /// The two token files disagree on the name of level 50 — `pin-hierarchy.json` calls it
    /// `matched`, `interaction-motion.json` calls it `needsMatch` — but agree on the number and on
    /// its place in the overlap order, which is what actually matters here.
    enum ZIndex {
        static let cluster: Double = 10
        static let estimated: Double = 20
        static let scannedOnSite: Double = 30
        static let ownerConfirmed: Double = 40
        static let needsMatch: Double = 50
        static let selected: Double = 60
        static let liveScanDrop: Double = 70
    }
}

/// The external match halo. Line style carries the state as well as colour.
enum EntryMapMatchState {
    /// Solid.
    case good
    /// Dashed.
    case partial
    /// Dotted.
    case unknown

    var accessibilityLabel: String {
        switch self {
        case .good: return "Matches what you need"
        case .partial: return "Partly matches what you need"
        case .unknown: return "Not yet known whether it matches"
        }
    }
}

/// A trust pin, at the size its context calls for, with the overlays the spec allows.
///
/// Overlays never recolour the pin. Selection adds a keyline and lifts it; a match halo is drawn
/// outside it; freshness adds a separate amber clock. All three leave the tier encoding alone.
struct EntryMapPin: View {
    let tier: EntryMapTrustTier
    var context: EntryMapPinContext = .street
    /// White keyline, indigo outer line, and a 6 pt lift. The 12% scale the spec describes is
    /// already expressed by the size table's `selected` row, so it is not applied twice.
    var isSelected: Bool = false
    /// Drawn outside the pin, never on it.
    var matchState: EntryMapMatchState?
    /// A muted-amber clock. Never a recolour.
    var needsRecheck: Bool = false

    private var size: CGFloat { context.size(for: tier) }
    private var scale: CGFloat { size / EntryMapTrustTier.viewBoxHeight }
    private var box: CGSize { tier.viewBox }

    var body: some View {
        ZStack {
            if let matchState {
                EntryMapMatchHalo(state: matchState)
                    // Derived: the halo master's ring is 84 of its 104 units across, so a halo
                    // drawn at the pin's own height would sit inside the pin. 1.35 puts it just
                    // outside the widest pin in the ladder.
                    .frame(width: size * 1.35, height: size * 1.35)
            }
            pinGlyphs
                .frame(width: box.width * scale, height: box.height * scale)
        }
        .offset(y: isSelected ? -6 : 0)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spokenLabel)
    }

    private var spokenLabel: String {
        var parts = [tier.accessibilityLabel]
        if let matchState { parts.append(matchState.accessibilityLabel) }
        if needsRecheck { parts.append("Due for a re-check") }
        if isSelected { parts.append("Selected") }
        return parts.joined(separator: ". ")
    }

    @ViewBuilder
    private var pinGlyphs: some View {
        ZStack {
            if isSelected {
                // Derived: the library states the selected overlay in words — "white keyline +
                // indigo outer line" — and gives no widths, so the two lines are drawn under the
                // body at a shade over the tier's own 4-unit stroke.
                bodyOutline(EntryMapPalette.indigo900, width: 9)
                bodyOutline(EntryMapPalette.card, width: 6)
            }
            tierBody
            tierSymbol
            confidenceRing
            if needsRecheck {
                EntryMapIconView(icon: .freshness, size: size * 0.34, tint: EntryMapPalette.amber700)
                    .background(Circle().fill(EntryMapPalette.card).padding(-1))
                    .offset(x: box.width * scale * 0.30, y: size * 0.24)
            }
        }
    }

    private func bodyOutline(_ colour: Color, width: CGFloat) -> some View {
        bodyShape.stroke(colour, lineWidth: width * scale)
    }

    private var bodyShape: EntryMapVectorShape {
        EntryMapVectorShape(glyph: .path(Self.bodyCommands), viewBox: box)
    }

    /// The pin body, identical in all three masters.
    private static let bodyCommands =
        "M48 6c-21 0-36 15.7-36 35.3 0 25.1 24.3 45.8 33.5 52.8a4 4 0 0 0 5 0C59.7 87.1 84 66.4 "
        + "84 41.3 84 21.7 69 6 48 6Z"

    @ViewBuilder
    private var tierBody: some View {
        switch tier {
        case .estimated:
            // Hollow and dashed: the tier that has not been visited reads as provisional even in
            // greyscale.
            bodyShape.fill(EntryMapPalette.card)
            bodyShape.stroke(
                EntryMapPalette.sky400,
                style: StrokeStyle(lineWidth: 4 * scale, dash: [7 * scale, 6 * scale]))
        case .scannedOnSite:
            bodyShape.fill(EntryMapPalette.marigold400)
            bodyOutline(EntryMapPalette.card, width: 4)
        case .ownerConfirmed:
            bodyShape.fill(EntryMapPalette.violet600)
            bodyOutline(EntryMapPalette.card, width: 4)
        }
    }

    @ViewBuilder
    private var tierSymbol: some View {
        switch tier {
        case .estimated:
            // The master sets an italic serif "i" in Georgia, which ships with iOS. Size and
            // baseline are the master's, converted from its 39-unit type at a y of 56.
            Text(verbatim: "i")
                .font(.custom("Georgia", fixedSize: 39 * scale).weight(.bold).italic())
                .foregroundStyle(EntryMapPalette.sky700)
                .offset(y: (42 - EntryMapTrustTier.viewBoxHeight / 2) * scale)
        case .scannedOnSite:
            stroked(
                [.circle(x: 48, y: 34, radius: 9), .path("M30 69c1-15 8-23 18-23s17 8 18 23Z")],
                colour: EntryMapPalette.indigo900, width: 4)
        case .ownerConfirmed:
            stroked(
                [
                    .path("M28 38h40l-4-12H32Z"),
                    .path("M30 38v30h36V38M42 68V51h13v17"),
                    .path("M28 38c0 5 6 7 10 3 4 4 9 4 13 0 4 4 9 4 13 0 4 4 10 2 10-3"),
                ],
                colour: EntryMapPalette.card, width: 3.8)
            // The outlined check is a separate mark beside the pin, never on its face.
            EntryMapVectorShape(glyph: .circle(x: 88, y: 28, radius: 14), viewBox: box)
                .fill(EntryMapPalette.card)
            EntryMapVectorShape(glyph: .circle(x: 88, y: 28, radius: 14), viewBox: box)
                .stroke(EntryMapPalette.violet800, lineWidth: 3 * scale)
            stroked(
                [.path("m81 28 5 5 9-11")], colour: EntryMapPalette.violet800, width: 3)
        }
    }

    /// The filled-of-three ring above the pin: 0, 2 or 3.
    private var confidenceRing: some View {
        ZStack {
            ForEach(0..<3, id: \.self) { index in
                let filled = index < tier.filledRings
                let glyph = EntryMapGlyph.circle(x: 35 + Double(index) * 13, y: 15, radius: 4.5)
                EntryMapVectorShape(glyph: glyph, viewBox: box)
                    .fill(filled ? ringColour : EntryMapPalette.card)
                EntryMapVectorShape(glyph: glyph, viewBox: box)
                    .stroke(ringColour, lineWidth: 2 * scale)
            }
        }
    }

    private var ringColour: Color {
        switch tier {
        case .estimated: return EntryMapPalette.sky700
        case .scannedOnSite: return EntryMapPalette.marigold400
        case .ownerConfirmed: return EntryMapPalette.violet600
        }
    }

    private func stroked(
        _ glyphs: [EntryMapGlyph], colour: Color, width: CGFloat
    ) -> some View {
        ZStack {
            ForEach(glyphs.indices, id: \.self) { index in
                EntryMapVectorShape(glyph: glyphs[index], viewBox: box)
                    .stroke(
                        colour,
                        style: StrokeStyle(
                            lineWidth: width * scale, lineCap: .round, lineJoin: .round))
            }
        }
    }
}

/// The external match halo, drawn from `docs/design/entrymap/svg/halos/`.
struct EntryMapMatchHalo: View {
    let state: EntryMapMatchState

    private static let viewBox = CGSize(width: 104, height: 104)

    var body: some View {
        GeometryReader { proxy in
            let scale = EntryMapVectorShape.scale(
                fitting: Self.viewBox,
                in: CGRect(origin: .zero, size: proxy.size))
            ZStack {
                ring(scale: scale)
                if state == .good {
                    // The inner sky ring the good-match master carries.
                    EntryMapVectorShape(
                        glyph: .circle(x: 52, y: 52, radius: 32), viewBox: Self.viewBox)
                        .stroke(EntryMapPalette.sky400.opacity(0.65), lineWidth: 2 * scale)
                }
            }
        }
        .accessibilityHidden(true)
    }

    @ViewBuilder
    private func ring(scale: CGFloat) -> some View {
        let shape = EntryMapVectorShape(
            glyph: .circle(x: 52, y: 52, radius: 42), viewBox: Self.viewBox)
        switch state {
        case .good:
            shape.stroke(EntryMapPalette.indigo900, lineWidth: 5 * scale)
        case .partial:
            shape.stroke(
                EntryMapPalette.violet600,
                style: StrokeStyle(lineWidth: 5 * scale, dash: [15 * scale, 9 * scale]))
        case .unknown:
            shape.stroke(
                EntryMapPalette.sky700,
                style: StrokeStyle(
                    lineWidth: 5 * scale, lineCap: .round, dash: [1 * scale, 11 * scale]))
        }
    }
}
