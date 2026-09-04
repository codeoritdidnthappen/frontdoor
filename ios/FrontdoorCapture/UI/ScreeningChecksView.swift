import SwiftUI

/// The named checks: what the server is looking for, named while it looks, and its answers when
/// they arrive (#275, step 3 of the scan flow).
///
/// Two things about this screen are deliberate and neither is styling.
///
/// **The checks are named before there are answers, and they all resolve at once.** The canon asks
/// for named checks rather than a spinner, and naming them is real information — it tells the
/// operator what this photo is being read for. What it does not do is stagger them: `/screen`
/// makes ONE integrated model call across the views, so there is no moment at which handrails are
/// known and signage is not. Revealing them one by one would be an animation pretending to be
/// progress, and this project does not put invented timing in front of a room.
///
/// **Nothing here is computed.** Verdicts, confidence, evidence and the honesty wording are all
/// printed from the response. A verdict this build does not recognise is shown verbatim rather
/// than mapped onto a familiar one — same rule as the laptop surface.
struct ScreeningChecksView: View {
    let run: ScreeningRun
    let onDone: () -> Void

    private static let knownVerdicts = ["present", "absent", "not_visible"]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    header
                    ForEach(ScreeningCriterion.allCases, id: \.self) { criterion in
                        row(criterion)
                        Divider()
                    }
                    extraCriteria
                    footer
                }
                .padding()
            }
            .navigationTitle("Screening")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done", action: onDone) }
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Entrance \(run.entranceId)").font(.headline)
            // The same live tag the laptop surface carries (#73): every demo moment says whether
            // it is happening now, so a screenshot of this can never be mistaken for a live run.
            Text("LIVE \(run.startedAt.formatted(date: .omitted, time: .standard))")
                .font(.caption.monospaced()).foregroundStyle(.secondary)
            if case .failed(let message) = run.outcome {
                Text(message)
                    .font(.footnote)
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.orange, in: RoundedRectangle(cornerRadius: 10))
                    .foregroundStyle(.black)
            }
            if case .assessed(let response) = run.outcome, response.quarantined {
                // Surfaced because it changes what may be kept, not what was assessed. The
                // verdicts stand; the image is the thing under quarantine.
                Label(
                    "Quarantined (\(response.quarantineReason ?? "unspecified")) — the privacy "
                        + "audit answered \(response.faceCheck). The verdicts below still stand.",
                    systemImage: "eye.trianglebadge.exclamationmark")
                    .font(.footnote)
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.yellow, in: RoundedRectangle(cornerRadius: 10))
                    .foregroundStyle(.black)
            }
        }
    }

    private func row(_ criterion: ScreeningCriterion) -> some View {
        entry(label: criterion.label, criterion: run.criterion(criterion.rawValue))
    }

    /// A criterion the server sent that this build has no label for. Shown by its raw key rather
    /// than dropped: an answer that never reaches the screen is indistinguishable from one that
    /// was never given.
    @ViewBuilder
    private var extraCriteria: some View {
        ForEach(run.unrecognisedCriterionKeys, id: \.self) { key in
            entry(label: key, criterion: run.criterion(key))
            Divider()
        }
    }

    private func entry(label: String, criterion: ScreeningResponse.Criterion?) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(.headline)
            switch run.outcome {
            case .inFlight:
                Label("Checking…", systemImage: "hourglass")
                    .font(.subheadline).foregroundStyle(.secondary)
            case .failed:
                Text("Not assessed").font(.subheadline).foregroundStyle(.secondary)
            case .assessed:
                verdict(criterion)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private func verdict(_ criterion: ScreeningResponse.Criterion?) -> some View {
        if let criterion, let verdict = criterion.verdict {
            HStack(spacing: 8) {
                Text(verdict)
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(colour(verdict))
                if let confidence = criterion.confidence {
                    Text("confidence \(confidence)")
                        .font(.subheadline).foregroundStyle(.secondary)
                }
            }
            if let evidence = criterion.evidence, !evidence.isEmpty {
                Text(evidence).font(.subheadline).foregroundStyle(.secondary)
            }
        } else {
            // The server answered, and said nothing about this criterion. Not the same as absent.
            Text("no verdict").font(.title3.weight(.semibold)).foregroundStyle(.secondary)
        }
    }

    /// An unrecognised verdict is styled as invalid rather than given a plausible colour, so a
    /// value nobody has seen before cannot read as a finding.
    private func colour(_ verdict: String) -> Color {
        guard Self.knownVerdicts.contains(verdict) else { return .purple }
        switch verdict {
        case "present": return .green
        case "absent": return .red
        default: return .blue
        }
    }

    @ViewBuilder
    private var footer: some View {
        if case .assessed(let response) = run.outcome {
            VStack(alignment: .leading, spacing: 6) {
                Text(response.wording).font(.footnote).foregroundStyle(.secondary)
                if response.facesBlurred > 0 {
                    Text("\(response.facesBlurred) face(s) blurred before this photo was assessed.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Text("status \(response.status) · model \(response.model) · \(response.latencyMs) ms")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}
