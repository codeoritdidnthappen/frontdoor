import SwiftUI

/// Where ground truth is entered, before the viewfinder opens.
///
/// Deliberately in the way: D-018 binds truth at the shutter press, so there is no path to a
/// capture that skips this screen and gets reconciled against a spreadsheet later. The operator
/// is standing at the doorway with the caliper in hand -- this is the only moment the reading is
/// cheap to get right.
struct EntranceSetupView: View {
    @ObservedObject var store: EntranceStore
    /// Carried over from the previous entrance so a run of captures does not retype it.
    let initialConditions: ConditionTags?
    let onReady: (CaptureSubject) -> Void
    let onCancel: () -> Void

    @State private var entranceId = ""
    @State private var rise = ""
    @State private var instrument = defaultInstrument
    @State private var distance = "2.0"
    @State private var lighting: Lighting = .overcast
    @State private var surface: Surface = .concrete
    @State private var occlusion: Occlusion = .none
    @State private var rejection: TruthRejected?
    @State private var confirmingRise: Double?

    /// The team's caliper. Prefilled rather than fixed: the schema wants whatever actually took
    /// the reading, and a second instrument would otherwise be recorded as the first.
    static let defaultInstrument = "digital caliper"

    /// The entrance already recorded under this ID, if any. Its reading is reused unchanged.
    private var known: Entrance? { store.existing(id: entranceId) }

    var body: some View {
        NavigationStack {
            Form {
                Section("Entrance") {
                    TextField("E-014", text: $entranceId)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                        .font(.body.monospaced())
                    if let known {
                        LabeledContent("Rise") {
                            Text(String(format: "%.2f in", known.riseInches)).monospacedDigit()
                        }
                        LabeledContent("Instrument", value: known.instrument)
                        Text("Already recorded. Its reading and split are reused unchanged.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    } else {
                        HStack {
                            TextField("Caliper rise", text: $rise)
                                .keyboardType(.decimalPad)
                            Text("in").foregroundStyle(.secondary)
                        }
                        TextField("Instrument", text: $instrument)
                    }
                }

                Section {
                    HStack {
                        TextField("Distance", text: $distance)
                            .keyboardType(.decimalPad)
                        Text("m").foregroundStyle(.secondary)
                    }
                    Picker("Lighting", selection: $lighting) {
                        ForEach(Lighting.allCases, id: \.self) { Text($0.label).tag($0) }
                    }
                    Picker("Surface", selection: $surface) {
                        ForEach(Surface.allCases, id: \.self) { Text($0.label).tag($0) }
                    }
                    Picker("Occlusion", selection: $occlusion) {
                        ForEach(Occlusion.allCases, id: \.self) { Text($0.label).tag($0) }
                    }
                } header: {
                    Text("Conditions for this shot")
                } footer: {
                    Text("Capture angle is not entered. It is derived from the recovered plane "
                         + "pose, which is what makes the error-versus-angle curve a measurement.")
                }

                if let rejection {
                    Section {
                        Text(rejection.message)
                            .font(.footnote)
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Capture")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel", action: onCancel)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Viewfinder") { submit() }
                }
            }
            .alert("Unusual reading", isPresented: confirmingRiseBinding) {
                Button("Cancel", role: .cancel) { confirmingRise = nil }
                Button("That is the reading") { submit(confirmedRise: true) }
            } message: {
                Text(confirmingRise.map { TruthRejected.riseImplausible($0).message } ?? "")
            }
        }
        .onAppear {
            guard let initialConditions else { return }
            distance = String(format: "%.1f", initialConditions.distanceM)
            lighting = initialConditions.lighting
            surface = initialConditions.surface
            occlusion = initialConditions.occlusion
        }
    }

    private var confirmingRiseBinding: Binding<Bool> {
        Binding(get: { confirmingRise != nil }, set: { if !$0 { confirmingRise = nil } })
    }

    private func submit(confirmedRise: Bool = false) {
        confirmingRise = nil
        let resolved = store.resolve(
            id: entranceId, rise: rise, instrument: instrument,
            confirmedImplausibleRise: confirmedRise)
        switch resolved {
        case .failure(.riseImplausible(let value)) where !confirmedRise:
            // Not an error yet: a 7" step is real, and so is a slipped decimal point. Only the
            // operator standing at the doorway can tell them apart.
            confirmingRise = value
            rejection = nil
        case .failure(let error):
            rejection = error
        case .success(let entrance):
            switch TruthValidation.conditions(
                distance: distance, lighting: lighting,
                surface: surface, occlusion: occlusion
            ) {
            case .failure(let error):
                rejection = error
            case .success(let conditions):
                rejection = nil
                onReady(CaptureSubject(entrance: entrance, conditions: conditions))
            }
        }
    }
}
