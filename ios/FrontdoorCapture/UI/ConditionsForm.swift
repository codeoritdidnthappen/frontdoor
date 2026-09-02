import SwiftUI

/// The condition tags for one shot. Shared by the entrance screen and the viewfinder, so the two
/// cannot drift into offering different vocabularies for the same sidecar field.
struct ConditionsForm: View {
    @Binding var distance: String
    @Binding var lighting: Lighting
    @Binding var surface: Surface
    @Binding var occlusion: Occlusion
    /// Screening captures never show a surface picker: `docs/capture-protocol.md` does not ask an
    /// operator to record it, and a picker with a default is a value nobody looked at (D-034).
    var showsSurface: Bool = true

    var body: some View {
        Group {
            HStack {
                TextField("Distance", text: $distance)
                    .keyboardType(.decimalPad)
                Text("m").foregroundStyle(.secondary)
            }
            Picker("Lighting", selection: $lighting) {
                ForEach(Lighting.allCases, id: \.self) { Text($0.label).tag($0) }
            }
            if showsSurface {
                Picker("Surface", selection: $surface) {
                    ForEach(Surface.allCases, id: \.self) { Text($0.label).tag($0) }
                }
            }
            Picker("Occlusion", selection: $occlusion) {
                ForEach(Occlusion.allCases, id: \.self) { Text($0.label).tag($0) }
            }
        }
    }
}

/// Changing the conditions without leaving the camera.
///
/// D-002 wants several distances and angles per entrance, so the operator moves between shots.
/// If the tags could only be set before the viewfinder opened, every frame after the first would
/// silently carry the first one's distance -- wrong in a stratification variable, and undetectable
/// once the capture is over.
struct ConditionsSheet: View {
    /// The session's mode, passed in rather than defaulted (D-034).
    ///
    /// Defaulting to metrology here re-applied R-3's 3 m cap mid-session, so an operator who had
    /// set up the protocol's "far, ~3-4 m" shot was refused the moment they edited conditions from
    /// the viewfinder -- and the saved tags came back carrying `card_placement: vertical` and a
    /// surface, both of which the schema forbids on a screening capture.
    let mode: CaptureMode
    let current: ConditionTags
    let onSave: (ConditionTags) -> Void
    let onCancel: () -> Void

    @State private var distance: String
    @State private var lighting: Lighting
    @State private var surface: Surface
    @State private var occlusion: Occlusion
    @State private var rejection: TruthRejected?

    init(mode: CaptureMode,
         current: ConditionTags,
         onSave: @escaping (ConditionTags) -> Void,
         onCancel: @escaping () -> Void) {
        self.mode = mode
        self.current = current
        self.onSave = onSave
        self.onCancel = onCancel
        _distance = State(initialValue: ConditionsSheet.text(for: current.distanceM))
        _lighting = State(initialValue: current.lighting)
        _surface = State(initialValue: current.surface ?? .concrete)
        _occlusion = State(initialValue: current.occlusion)
    }

    /// Round-trips through the same string the operator typed, so reopening the sheet does not
    /// quietly reformat 2 into 2.0 or lose a second decimal.
    static func text(for metres: Double) -> String {
        metres == metres.rounded() ? String(format: "%.1f", metres) : String(metres)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    ConditionsForm(distance: $distance, lighting: $lighting,
                                   surface: $surface, occlusion: $occlusion,
                                   showsSurface: mode.carriesMetrologyTruth)
                } header: {
                    Text("Conditions for the next shot")
                } footer: {
                    Text("Applies to captures from here on, not to ones already taken.")
                }
                if let rejection {
                    Section { Text(rejection.message).font(.footnote).foregroundStyle(.red) }
                }
            }
            .navigationTitle("Conditions")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel", action: onCancel) }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        switch TruthValidation.conditions(
                            distance: distance, lighting: lighting,
                            surface: surface, occlusion: occlusion, mode: mode
                        ) {
                        case .failure(let error): rejection = error
                        case .success(let tags): rejection = nil; onSave(tags)
                        }
                    }
                }
            }
        }
    }
}
