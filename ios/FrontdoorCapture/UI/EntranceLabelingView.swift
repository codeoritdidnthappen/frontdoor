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
                    Text("Operator")
                } footer: {
                    Text("Set once on this phone. The server records the labeling date.")
                }

                ForEach(ScreeningCriterion.allCases) { criterion in
                    Section(criterion.label) {
                        HStack {
                            ForEach(LabelTruth.allCases) { truth in
                                let selected = draft.answers[criterion] == truth
                                Button { draft.select(truth, for: criterion) } label: {
                                    Text(truth.label)
                                        .entryMapText(EntryMapTypography.overline)
                                        .frame(maxWidth: .infinity,
                                               minHeight: EntryMapLayout.touchTargetMinimum)
                                        .padding(.vertical, EntryMapLayout.space3)
                                        .foregroundStyle(selected
                                                         ? EntryMapPalette.onViolet
                                                         : EntryMapPalette.ink)
                                        .background(
                                            selected
                                            ? EntryMapPalette.violet600 : EntryMapPalette.card,
                                            in: RoundedRectangle(
                                                cornerRadius: EntryMapLayout.radiusSmall))
                                        .overlay(
                                            RoundedRectangle(
                                                cornerRadius: EntryMapLayout.radiusSmall)
                                                .stroke(selected
                                                        ? EntryMapPalette.violet600
                                                        : EntryMapPalette.edge))
                                }
                                    .buttonStyle(.plain)
                                    .accessibilityAddTraits(
                                        selected ? .isSelected : [])
                            }
                        }
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
            .scrollContentBackground(.hidden)
            .background(EntryMapPalette.ground)
            .navigationTitle("Label \(entranceId)")
            .interactiveDismissDisabled()
            .onAppear(perform: restoreQueuedRecord)
        }
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
