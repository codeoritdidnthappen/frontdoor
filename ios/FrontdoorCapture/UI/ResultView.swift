import SwiftUI

/// What the server measured, shown beside a caliper reading on stage (PRD section 10).
///
/// Two things drive the design and neither is decoration. The rise and the verdict are read from
/// the back of a room, so they are set large enough to survive a 1080p projection. And abstention
/// is a first-class outcome (D-009): it renders as a stated, explained answer, never as a blank or
/// an error, because "the interval straddles the line" is a finding this project is proud of.
struct ResultView: View {
    let response: MeasureResponse
    let caliperInches: Double
    let onDone: () -> Void

    /// Large enough to read at 3 m on a 1080p projection (AC5).
    private static let headlineSize: CGFloat = 64
    private static let verdictSize: CGFloat = 48

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    if response.stub {
                        stubBanner
                    }
                    primary
                    Divider()
                    ForEach(ArmName.allCases.filter { $0 != .a }, id: \.self) { name in
                        if let arm = response.arms[name] { secondary(name, arm) }
                    }
                }
                .padding()
            }
            .navigationTitle("Measurement")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done", action: onDone) }
            }
        }
    }

    /// The schema requires clients to surface this. A placeholder rendered like a measurement is
    /// the most damaging thing this screen could do, and on stage nobody would know.
    private var stubBanner: some View {
        Label(
            "These are placeholder values, not a measurement. The server has no metrology behind it yet.",
            systemImage: "exclamationmark.triangle.fill")
            .font(.headline)
            .foregroundStyle(.black)
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.yellow, in: RoundedRectangle(cornerRadius: 12))
    }

    /// Arm A is the only arm with a bar drawn against it (D-022, Amendment A-2).
    @ViewBuilder
    private var primary: some View {
        switch response.arms[.a] {
        case .measured(let m)?:
            VStack(spacing: 12) {
                Text(ArmName.a.label).font(.headline).foregroundStyle(.secondary)
                Text(inches(m.riseIn))
                    .font(.system(size: Self.headlineSize, weight: .bold, design: .rounded))
                    .minimumScaleFactor(0.6).lineLimit(1)
                Text("interval \(inches(m.intervalIn.low)) – \(inches(m.intervalIn.high))")
                    .font(.title3).foregroundStyle(.secondary)
                decision(m.decisions.halfInch, line: "1/2\"")
                caliperComparison(measured: m.riseIn)
            }
            .frame(maxWidth: .infinity)
        case .absent(let a)?:
            absence(ArmName.a, a, prominent: true)
        case nil:
            Text("The server returned no result for Arm A.").font(.headline)
        }
    }

    /// The verdict, at stage size. Abstain is styled as an answer, not as a warning.
    private func decision(_ decision: Decision, line: String) -> some View {
        VStack(spacing: 8) {
            Text(verdictText(decision.verdict, line: line))
                .font(.system(size: Self.verdictSize, weight: .heavy, design: .rounded))
                .minimumScaleFactor(0.5).lineLimit(2)
                .multilineTextAlignment(.center)
                .foregroundStyle(colour(decision.verdict))
            if let explanation = decision.explanation, !explanation.isEmpty {
                Text(explanation)
                    .font(.title3)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity)
        .background(colour(decision.verdict).opacity(0.12),
                    in: RoundedRectangle(cornerRadius: 16))
    }

    private func verdictText(_ verdict: Decision.Verdict, line: String) -> String {
        switch verdict {
        case .pass: return "Under \(line)"
        case .fail: return "Over \(line)"
        case .abstain: return "No call at \(line)"
        }
    }

    private func colour(_ verdict: Decision.Verdict) -> Color {
        switch verdict {
        case .pass: return .green
        case .fail: return .red
        // Deliberately not red or orange. An abstention is not a failure and not an error; it is
        // the method declining to claim more than it knows.
        case .abstain: return .blue
        }
    }

    /// The comparison the demo exists to make.
    private func caliperComparison(measured: Double) -> some View {
        VStack(spacing: 4) {
            Text("caliper \(inches(caliperInches))  ·  difference \(inches(abs(measured - caliperInches)))")
                .font(.title3.weight(.medium))
        }
        .padding(.top, 4)
    }

    private func secondary(_ name: ArmName, _ arm: Arm) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(name.label).font(.headline)
            switch arm {
            case .measured(let m):
                Text("\(inches(m.riseIn))   interval \(inches(m.intervalIn.low)) – \(inches(m.intervalIn.high))")
                    .font(.title3)
                // No verdict here: only Arm A carries a bar (D-022).
                Text("reported without a pass/fail bar")
                    .font(.footnote).foregroundStyle(.secondary)
            case .absent(let a):
                Text(a.absentReason.headline).font(.title3)
                Text(a.detail ?? a.absentReason.plain)
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func absence(_ name: ArmName, _ absence: Arm.Absence, prominent: Bool) -> some View {
        VStack(spacing: 10) {
            Text(name.label).font(.headline).foregroundStyle(.secondary)
            Text(absence.absentReason.headline)
                .font(.system(size: prominent ? Self.verdictSize : 24, weight: .bold))
                .multilineTextAlignment(.center)
            Text(absence.detail ?? absence.absentReason.plain)
                .font(.title3).multilineTextAlignment(.center).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    private func inches(_ value: Double) -> String {
        String(format: "%.2f in", value)
    }
}
