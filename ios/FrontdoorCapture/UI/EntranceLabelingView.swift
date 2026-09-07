import SwiftUI

/// Four explicit button rows after a complete future entrance capture (TICK-282).
struct EntranceLabelingView: View {
    @ObservedObject var controller: CaptureController
    let entranceId: String
    let onSaved: () -> Void

    @State private var draft = EntranceLabelDraft()
    @State private var operatorName = ""
    @State private var failure: String?
    private var operatorStore = LabelOperatorStore()

    init(controller: CaptureController, entranceId: String, onSaved: @escaping () -> Void) {
        self.controller = controller
        self.entranceId = entranceId
        self.onSaved = onSaved
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    if operatorStore.name.isEmpty {
                        TextField("Your name", text: $operatorName)
                            .textContentType(.name)
                            .autocorrectionDisabled()
                    } else {
                        LabeledContent("Labeling as", value: operatorStore.name)
                    }
                } header: {
                    Text("Operator").entryMapSectionHeader()
                } footer: {
                    Text("Set once on this phone. The server records the labeling date.")
                        .entryMapSectionFooter()
                }

                ForEach(ScreeningCriterion.allCases) { criterion in
                    Section {
                        HStack {
                            ForEach(LabelTruth.allCases) { truth in
                                chip(truth, for: criterion)
                            }
                        }
                    } header: {
                        Text(criterion.label).entryMapSectionHeader()
                    }
                }

                if let failure {
                    // No red: the palette has none, so the amber "look again" role plus the
                    // words carry it.
                    HStack(alignment: .top, spacing: EntryMapLayout.space2) {
                        EntryMapIconView(icon: .info, size: 20, tint: EntryMapPalette.freshness)
                        Text(failure)
                            .entryMapText(EntryMapTypography.callout)
                            .foregroundStyle(EntryMapPalette.ink)
                    }
                }

                Button("Save labels") { save() }
                    .buttonStyle(EntryMapButtonStyle(role: .primary))
                    .disabled(!canSave)
                    .listRowInsets(EdgeInsets())
                    .listRowBackground(Color.clear)
            }
            .entryMapForm()
            .navigationTitle("Label \(entranceId)")
            .interactiveDismissDisabled()
            .onAppear(perform: restoreQueuedRecord)
        }
        // Toolbar buttons, picker values and cursors. Here and not on the Form or the root --
        // see `entryMapForm()` for why both of those were tried and dropped.
        .tint(EntryMapPalette.violet600)
    }

    /// One of the four answers for one criterion.
    ///
    /// Lifted out of the `Form` rather than left inline: as one expression, with three ternaries
    /// feeding a background, an overlay and a foreground, the type checker gave up on it.
    private func chip(_ truth: LabelTruth, for criterion: ScreeningCriterion) -> some View {
        let selected = draft.answers[criterion] == truth
        let shape = RoundedRectangle(cornerRadius: EntryMapLayout.radiusSmall)
        let fill: Color = selected ? EntryMapPalette.violet600 : EntryMapPalette.card
        let keyline: Color = selected ? EntryMapPalette.violet600 : EntryMapPalette.edge
        let label: Color = selected ? EntryMapPalette.onViolet : EntryMapPalette.ink
        return Button {
            draft.select(truth, for: criterion)
        } label: {
            Text(truth.label)
                .entryMapText(EntryMapTypography.overline)
                .foregroundStyle(label)
                .frame(maxWidth: .infinity, minHeight: EntryMapLayout.touchTargetMinimum)
                .background(fill, in: shape)
                .overlay(shape.stroke(keyline))
                .contentShape(shape)
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    private var chosenOperator: String {
        let saved = operatorStore.name
        return saved.isEmpty
            ? operatorName.trimmingCharacters(in: .whitespacesAndNewlines) : saved
    }

    private var canSave: Bool {
        draft.canSave(operatorName: chosenOperator)
    }

    private func restoreQueuedRecord() {
        guard case .success(let found) = controller.labelQueue.record(for: entranceId),
              let record = found, record.state == .queued else { return }
        operatorName = record.labeledBy
        draft.restore(record)
    }

    private func save() {
        if operatorStore.name.isEmpty { operatorStore.name = chosenOperator }
        switch controller.queueLabels(
            entranceId: entranceId, labeledBy: chosenOperator, answers: draft.answers) {
        case .success:
            onSaved()
        case .failure(let error):
            failure = error.localizedDescription
        }
    }
}
