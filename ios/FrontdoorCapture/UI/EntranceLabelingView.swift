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
                                        .font(.caption.weight(.semibold))
                                        .frame(maxWidth: .infinity)
                                        .padding(.vertical, 8)
                                        .foregroundStyle(selected ? .white : .primary)
                                        .background(
                                            selected ? Color.accentColor : Color.clear,
                                            in: RoundedRectangle(cornerRadius: 8))
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 8)
                                                .stroke(Color.accentColor))
                                }
                                    .buttonStyle(.plain)
                                    .accessibilityAddTraits(
                                        selected ? .isSelected : [])
                            }
                        }
                    }
                }

                if let failure {
                    Text(failure).foregroundStyle(.red)
                }

                Button("Save labels") { save() }
                    .buttonStyle(.borderedProminent)
                    .disabled(!canSave)
            }
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
