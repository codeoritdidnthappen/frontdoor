import PhotosUI
import SwiftUI

/// Bring photos already on the phone into the dataset (D-034, TICK-027 / #31).
///
/// The pivot to plain-photo screening happened after entrances had been shot with the stock
/// camera. Those photos are real work and are not re-shootable at will, so they can be imported —
/// with an entrance ID and condition tags attached at import, and nothing invented. What the file
/// does not say, the record does not claim: no intrinsics, no gravity, no lens.
///
/// A photo whose own metadata cannot supply a capture date or a device is refused rather than
/// dated to now. "Now" is when it was imported, not when the entrance was seen, and a record that
/// confuses the two is worse than one that is missing.
struct ImportPhotosView: View {
    @ObservedObject var store: EntranceStore
    @ObservedObject var controller: CaptureController
    let onDone: () -> Void

    @State private var picked: [PhotosPickerItem] = []
    @State private var entranceId = ""
    @State private var distance = "2.0"
    @State private var lighting: Lighting = .overcast
    @State private var surface: Surface = .concrete
    @State private var occlusion: Occlusion = .none
    @State private var busy = false
    @State private var report: String?
    @State private var rejection: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Entrance") {
                    TextField("E-014", text: $entranceId)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                        .font(.body.monospaced())
                }

                Section {
                    ConditionsForm(distance: $distance, lighting: $lighting,
                                   surface: $surface, occlusion: $occlusion,
                                   showsSurface: false)
                } header: {
                    Text("Conditions these photos were taken in")
                } footer: {
                    Text("Recorded now, from memory, because the photos were taken earlier. "
                         + "That is weaker than tagging at the door and is why importing is a "
                         + "rescue path, not the normal one.")
                }

                Section {
                    PhotosPicker(selection: $picked, matching: .images,
                                 photoLibrary: .shared()) {
                        Label(picked.isEmpty ? "Choose photos"
                                             : "^[\(picked.count) photo](inflect: true) chosen",
                              systemImage: "photo.on.rectangle")
                    }
                }

                if let rejection {
                    Section { Text(rejection).foregroundStyle(.orange).font(.footnote) }
                }
                if let report {
                    Section { Text(report).font(.footnote) }
                }
            }
            .navigationTitle("Import photos")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close", action: onDone)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(busy ? "Importing…" : "Import") { Task { await runImport() } }
                        .disabled(busy || picked.isEmpty || entranceId.isEmpty)
                }
            }
        }
    }

    private func runImport() async {
        busy = true
        defer { busy = false }
        rejection = nil
        report = nil

        let checkedConditions = TruthValidation.conditions(
            distance: distance, lighting: lighting, surface: surface, occlusion: occlusion,
            mode: .imported)
        guard case .success(let conditions) = checkedConditions else {
            if case .failure(let error) = checkedConditions { rejection = error.message }
            return
        }
        // Same store as the camera path, so importing photos of an entrance already captured
        // today attaches to it and keeps its split rather than minting a second one.
        guard case .success(let entrance) = store.resolveScreening(id: entranceId) else {
            rejection = TruthRejected.entranceIdMalformed(entranceId).message
            return
        }

        var imported = 0
        var refused: [String] = []
        for item in picked {
            guard let data = try? await item.loadTransferable(type: Data.self) else {
                refused.append(ImportedPhoto.Refusal.notAnImage.message)
                continue
            }
            switch controller.importPhoto(data, entrance: entrance, conditions: conditions) {
            case .imported:
                imported += 1
            case .refused(let why):
                refused.append(why)
            }
        }

        picked = []
        report = "Imported \(imported). "
            + (refused.isEmpty ? "None refused." : "\(refused.count) refused: \(refused[0])")
    }
}
