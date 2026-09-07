import SwiftUI

/// What the server measured, shown beside a caliper reading on stage (PRD section 10).
///
/// Two things drive the design and neither is decoration. The rise and the verdict are read from
/// the back of a room, so they are set large enough to survive a 1080p projection. And abstention
/// is a first-class outcome (D-009): it renders as a stated, explained answer, never as a blank or
/// an error, because "the interval straddles the line" is a finding this project is proud of.
struct ResultView: View {
    let response: MeasureResponse
    let caliperInches: Double?
    let onDone: () -> Void

    // Read at 3 m on a 1080p projection (AC5). That used to be a hard-coded 64/48 pt; the
    // design system's `display` step is the same requirement answered once -- its own comment is
    // "the scan verdict and the measured rise: read from the back of a room" -- and unlike a
    // fixed size it grows with Dynamic Type.

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: EntryMapLayout.space5) {
                    if response.stub {
                        stubBanner
                    }
                    primary
                    Divider()
                    ForEach(ArmName.allCases.filter { $0 != .a }, id: \.self) { name in
                        if let arm = response.arms[name] { secondary(name, arm) }
                    }
                }
                .padding(EntryMapLayout.space4)
            }
            .background(EntryMapPalette.ground)
            .navigationTitle("Measurement")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done", action: onDone) }
            }
        }
        // Toolbar buttons, picker values and cursors. Here and not on the Form or the root --
        // see `entryMapForm()` for why both of those were tried and dropped.
        .tint(EntryMapPalette.violet600)
    }

    /// The schema requires clients to surface this. A placeholder rendered like a measurement is
    /// the most damaging thing this screen could do, and on stage nobody would know.
    private var stubBanner: some View {
        HStack(alignment: .top, spacing: EntryMapLayout.space3) {
            EntryMapIconView(icon: .info, size: 22, tint: EntryMapPalette.onMarigold)
            Text("These are placeholder values, not a measurement. The server has no metrology "
                 + "behind it yet.")
                .entryMapText(EntryMapTypography.subheading)
        }
        .foregroundStyle(EntryMapPalette.onMarigold)
        .padding(EntryMapLayout.space4)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(EntryMapPalette.marigold400,
                    in: RoundedRectangle(cornerRadius: EntryMapLayout.radiusMedium))
    }

    /// Arm A is the only arm with a bar drawn against it (D-022, Amendment A-2).
    @ViewBuilder
    private var primary: some View {
        switch response.arms[.a] {
        case .measured(let m)?:
            VStack(spacing: EntryMapLayout.space3) {
                Text(ArmName.a.label)
                    .entryMapText(EntryMapTypography.overline)
                    .foregroundStyle(EntryMapPalette.subduedInk)
                Text(inches(m.riseIn))
                    .entryMapText(EntryMapTypography.display)
                    .foregroundStyle(EntryMapPalette.ink)
                    .minimumScaleFactor(0.6).lineLimit(1)
                Text("interval \(inches(m.intervalIn.low)) – \(inches(m.intervalIn.high))")
                    .entryMapText(EntryMapTypography.bodyNumeric)
                    .foregroundStyle(EntryMapPalette.subduedInk)
                decision(m.decisions.halfInch, line: "1/2\"")
                caliperComparison(measured: m.riseIn)
            }
            .frame(maxWidth: .infinity)
        case .absent(let a)?:
            absence(ArmName.a, a, prominent: true)
        case nil:
            Text("The server returned no result for Arm A.")
                .entryMapText(EntryMapTypography.heading)
                .foregroundStyle(EntryMapPalette.ink)
        }
    }

    /// The verdict, at stage size. Abstain is styled as an answer, not as a warning.
    private func decision(_ decision: Decision, line: String) -> some View {
        VStack(spacing: EntryMapLayout.space2) {
            EntryMapIconView(icon: icon(decision.verdict), size: 34, tint: EntryMapPalette.ink)
            Text(verdictText(decision.verdict, line: line))
                .entryMapText(EntryMapTypography.display)
                .foregroundStyle(EntryMapPalette.ink)
                .minimumScaleFactor(0.5).lineLimit(2)
                .multilineTextAlignment(.center)
            if let explanation = decision.explanation, !explanation.isEmpty {
                Text(explanation)
                    .entryMapText(EntryMapTypography.body)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(EntryMapPalette.subduedInk)
            }
        }
        .padding(.vertical, EntryMapLayout.space4)
        .padding(.horizontal, EntryMapLayout.space4)
        .frame(maxWidth: .infinity)
        .background(EntryMapPalette.card,
                    in: RoundedRectangle(cornerRadius: EntryMapLayout.radiusLarge))
        .overlay(RoundedRectangle(cornerRadius: EntryMapLayout.radiusLarge)
            .stroke(EntryMapPalette.edge))
    }

    private func verdictText(_ verdict: Decision.Verdict, line: String) -> String {
        switch verdict {
        case .pass: return "Under \(line)"
        case .fail: return "Over \(line)"
        case .abstain: return "No call at \(line)"
        }
    }

    /// The verdict is an icon and a sentence, never a colour.
    ///
    /// This used to be green / red / blue. The approved palette has none of the three, and that
    /// is deliberate -- colour never delivers a judgement in this product (the map's Green-or-Gray
    /// rule). It also fixes the accessibility hole in a green/red pass/fail shown on a projector.
    /// The abstention keeps its old distinction for the same reason it always had it: it is not a
    /// failure and not an error, it is the method declining to claim more than it knows.
    private func icon(_ verdict: Decision.Verdict) -> EntryMapIcon {
        switch verdict {
        case .pass: return .checkOutline
        case .fail: return .close
        case .abstain: return .confidence
        }
    }

    /// The comparison the demo exists to make -- when there is something to compare against.
    ///
    /// Optional since D-036 superseded D-003: no caliper, no instrument ground truth, and
    /// `Entrance.riseInches` is nil on every capture this study will take. Rendering a reading of
    /// zero would put "caliper 0.00 in - difference 0.11 in" on a projector and invite the room to
    /// read a fabricated agreement as a result. Absent truth shows as nothing, not as zero.
    @ViewBuilder
    private func caliperComparison(measured: Double) -> some View {
        if let caliperInches {
            VStack(spacing: EntryMapLayout.space1) {
                Text("caliper \(inches(caliperInches))  ·  "
                     + "difference \(inches(abs(measured - caliperInches)))")
                    .entryMapText(EntryMapTypography.bodyNumeric)
                    .foregroundStyle(EntryMapPalette.ink)
            }
            .padding(.top, EntryMapLayout.space1)
        }
    }

    private func secondary(_ name: ArmName, _ arm: Arm) -> some View {
        VStack(alignment: .leading, spacing: EntryMapLayout.space2) {
            Text(name.label)
                .entryMapText(EntryMapTypography.heading)
                .foregroundStyle(EntryMapPalette.ink)
            switch arm {
            case .measured(let m):
                Text("\(inches(m.riseIn))   interval \(inches(m.intervalIn.low)) – "
                     + "\(inches(m.intervalIn.high))")
                    .entryMapText(EntryMapTypography.bodyNumeric)
                    .foregroundStyle(EntryMapPalette.ink)
                // No verdict here: only Arm A carries a bar (D-022).
                Text("reported without a pass/fail bar")
                    .entryMapText(EntryMapTypography.caption)
                    .foregroundStyle(EntryMapPalette.subduedInk)
            case .absent(let a):
                Text(a.absentReason.headline)
                    .entryMapText(EntryMapTypography.subheading)
                    .foregroundStyle(EntryMapPalette.ink)
                Text(a.detail ?? a.absentReason.plain)
                    .entryMapText(EntryMapTypography.caption)
                    .foregroundStyle(EntryMapPalette.subduedInk)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func absence(_ name: ArmName, _ absence: Arm.Absence, prominent: Bool) -> some View {
        VStack(spacing: EntryMapLayout.space3) {
            Text(name.label)
                .entryMapText(EntryMapTypography.overline)
                .foregroundStyle(EntryMapPalette.subduedInk)
            Text(absence.absentReason.headline)
                .entryMapText(prominent
                              ? EntryMapTypography.display : EntryMapTypography.heading)
                .foregroundStyle(EntryMapPalette.ink)
                .multilineTextAlignment(.center)
            Text(absence.detail ?? absence.absentReason.plain)
                .entryMapText(EntryMapTypography.body)
                .multilineTextAlignment(.center)
                .foregroundStyle(EntryMapPalette.subduedInk)
        }
        .frame(maxWidth: .infinity)
    }

    private func inches(_ value: Double) -> String {
        String(format: "%.2f in", value)
    }
}
