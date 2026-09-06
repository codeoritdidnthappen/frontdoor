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
                VStack(alignment: .leading, spacing: EntryMapLayout.space4) {
                    header
                    ForEach(ScreeningCriterion.allCases, id: \.self) { criterion in
                        row(criterion)
                        Divider()
                    }
                    extraCriteria
                    adaScreening
                    footer
                }
                .padding(EntryMapLayout.space4)
            }
            .navigationTitle("Screening")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done", action: onDone) }
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: EntryMapLayout.space1) {
            Text("Entrance \(run.entranceId)")
                .entryMapText(EntryMapTypography.heading)
                .foregroundStyle(EntryMapPalette.ink)
            // The same live tag the laptop surface carries (#73): every demo moment says whether
            // it is happening now, so a screenshot of this can never be mistaken for a live run.
            Text("LIVE \(run.startedAt.formatted(date: .omitted, time: .standard))")
                .entryMapText(EntryMapTypography.captionNumeric)
                .foregroundStyle(EntryMapPalette.subduedInk)
            if case .failed(let message) = run.outcome {
                Text(message)
                    .entryMapText(EntryMapTypography.callout)
                    .padding(EntryMapLayout.space3)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(EntryMapPalette.marigold400,
                                in: RoundedRectangle(cornerRadius: EntryMapLayout.radiusSmall))
                    .foregroundStyle(EntryMapPalette.onMarigold)
            }
            if case .assessed(let response) = run.outcome, response.quarantined {
                // Surfaced because it changes what may be kept, not what was assessed. The
                // verdicts stand; the image is the thing under quarantine.
                HStack(alignment: .top, spacing: EntryMapLayout.space2) {
                    EntryMapIconView(icon: .info, size: 20, tint: EntryMapPalette.onMarigold)
                    Text(
                        "Quarantined (\(response.quarantineReason ?? "unspecified")) — the privacy "
                            + "audit answered \(response.faceCheck). The verdicts below still stand.")
                }
                    .entryMapText(EntryMapTypography.callout)
                    .padding(EntryMapLayout.space3)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(EntryMapPalette.marigold400,
                                in: RoundedRectangle(cornerRadius: EntryMapLayout.radiusSmall))
                    .foregroundStyle(EntryMapPalette.onMarigold)
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
        VStack(alignment: .leading, spacing: EntryMapLayout.space2) {
            Text(label)
                .entryMapText(EntryMapTypography.subheading)
                .foregroundStyle(EntryMapPalette.ink)
            switch run.outcome {
            case .inFlight:
                Text("Checking…")
                    .entryMapText(EntryMapTypography.callout)
                    .foregroundStyle(EntryMapPalette.subduedInk)
            case .failed:
                Text("Not assessed")
                    .entryMapText(EntryMapTypography.callout)
                    .foregroundStyle(EntryMapPalette.subduedInk)
            case .assessed:
                verdict(criterion)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private func verdict(_ criterion: ScreeningResponse.Criterion?) -> some View {
        if let criterion, let verdict = criterion.verdict {
            HStack(spacing: EntryMapLayout.space2) {
                EntryMapIconView(icon: icon(for: verdict), size: 22, tint: tint(for: verdict))
                Text(verdict)
                    .entryMapText(EntryMapTypography.subheading)
                    .foregroundStyle(EntryMapPalette.ink)
                if let confidence = criterion.confidence {
                    Text("confidence \(confidence)")
                        .entryMapText(EntryMapTypography.captionNumeric)
                        .foregroundStyle(EntryMapPalette.subduedInk)
                }
            }
            if let evidence = criterion.evidence, !evidence.isEmpty {
                Text(evidence)
                    .entryMapText(EntryMapTypography.callout)
                    .foregroundStyle(EntryMapPalette.subduedInk)
            }
        } else {
            // The server answered, and said nothing about this criterion. Not the same as absent.
            Text("no verdict")
                .entryMapText(EntryMapTypography.subheading)
                .foregroundStyle(EntryMapPalette.subduedInk)
        }
    }

    /// The verdict is carried by an icon and the word, never by a colour.
    ///
    /// An unrecognised verdict still gets the treatment it always had: marked as something the
    /// build does not understand, so a value nobody has seen before cannot read as a finding.
    ///
    /// The approved palette holds no red and no green, and that is not an omission: the map's own
    /// rule is that colour never delivers a verdict about a business (`map_states`). The same rule
    /// belongs here -- an operator reading "absent" in red is reading a judgement the product
    /// explicitly refuses to make.
    private func icon(for verdict: String) -> EntryMapIcon {
        guard Self.knownVerdicts.contains(verdict) else { return .info }
        switch verdict {
        case "present": return .checkOutline
        case "absent": return .close
        default: return .confidence
        }
    }

    /// Amber marks the two cases that need a second look -- a verdict this build does not know,
    /// and one the photographs could not settle. Everything else is ink.
    private func tint(for verdict: String) -> Color {
        guard Self.knownVerdicts.contains(verdict) else { return EntryMapPalette.freshness }
        return verdict == "not_visible" ? EntryMapPalette.freshness : EntryMapPalette.ink
    }

    @ViewBuilder
    private var adaScreening: some View {
        if case .assessed(let response) = run.outcome, let ada = response.adaScreening {
            let presentation = ada.renderModel
            VStack(alignment: .leading, spacing: EntryMapLayout.space3) {
                Text("Photo ADA screening")
                    .entryMapText(EntryMapTypography.heading)
                    .foregroundStyle(EntryMapPalette.ink)
                Text(presentation.score)
                    .entryMapText(EntryMapTypography.title)
                    .foregroundStyle(EntryMapPalette.ink)
                Text(presentation.coverage)
                    .entryMapText(EntryMapTypography.callout)
                    .foregroundStyle(EntryMapPalette.subduedInk)
                ForEach(presentation.rows) { row in
                    adaRow(row)
                    Divider()
                }
                Text(presentation.summary)
                    .entryMapText(EntryMapTypography.body)
                    .foregroundStyle(EntryMapPalette.ink)
                Text(presentation.disclaimer)
                    .entryMapText(EntryMapTypography.caption)
                    .foregroundStyle(EntryMapPalette.subduedInk)
                if let url = presentation.standardsURL {
                    Link("2010 ADA Standards", destination: url)
                        .entryMapText(EntryMapTypography.caption)
                        .foregroundStyle(EntryMapPalette.subduedInk)
                }
            }
            .padding(.top, EntryMapLayout.space2)
        }
    }

    private func adaRow(_ row: AdaScreening.RenderRow) -> some View {
        VStack(alignment: .leading, spacing: EntryMapLayout.space1) {
            Text(row.label)
                .entryMapText(EntryMapTypography.subheading)
                .foregroundStyle(EntryMapPalette.ink)
            Text(row.result)
                .entryMapText(EntryMapTypography.subheading)
                .foregroundStyle(EntryMapPalette.ink)
            if let evidence = row.evidence, !evidence.isEmpty {
                Text(evidence)
                    .entryMapText(EntryMapTypography.callout)
                    .foregroundStyle(EntryMapPalette.subduedInk)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private var footer: some View {
        if case .assessed(let response) = run.outcome {
            VStack(alignment: .leading, spacing: EntryMapLayout.space2) {
                Text(response.wording)
                    .entryMapText(EntryMapTypography.caption)
                    .foregroundStyle(EntryMapPalette.subduedInk)
                if response.facesBlurred > 0 {
                    Text("\(response.facesBlurred) face(s) blurred before this photo was assessed.")
                        .entryMapText(EntryMapTypography.caption).foregroundStyle(EntryMapPalette.subduedInk)
                }
                Text("status \(response.status) · model \(response.model) · \(response.latencyMs) ms")
                    .entryMapText(EntryMapTypography.caption).foregroundStyle(EntryMapPalette.subduedInk)
            }
        }
    }
}
