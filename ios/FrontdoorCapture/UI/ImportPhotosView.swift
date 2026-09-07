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
                Section {
                    TextField("E-014", text: $entranceId)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                        .entryMapText(EntryMapTypography.bodyNumeric)
                        .foregroundStyle(EntryMapPalette.ink)
                } header: {
                    Text("Entrance").entryMapSectionHeader()
                }

                Section {
                    ConditionsForm(distance: $distance, lighting: $lighting,
                                   surface: $surface, occlusion: $occlusion,
                                   showsSurface: false)
                } header: {
                    Text("Conditions these photos were taken in").entryMapSectionHeader()
                } footer: {
                    Text("Recorded now, from memory, because the photos were taken earlier. "
                         + "That is weaker than tagging at the door and is why importing is a "
                         + "rescue path, not the normal one.")
                        .entryMapSectionFooter()
                }

                Section {
                    PhotosPicker(selection: $picked, matching: .images,
                                 photoLibrary: .shared()) {
                        HStack(spacing: EntryMapLayout.space3) {
                            EntryMapIconView(icon: .photo, size: 22,
                                             tint: EntryMapPalette.violet600)
                            Text(picked.isEmpty
                                 ? "Choose photos"
                                 : "^[\(picked.count) photo](inflect: true) chosen")
                                .entryMapText(EntryMapTypography.body)
                                .foregroundStyle(EntryMapPalette.ink)
                        }
                        .frame(minHeight: EntryMapLayout.touchTargetMinimum)
                    }
                }

                if let rejection {
                    Section {
                        HStack(alignment: .top, spacing: EntryMapLayout.space2) {
                            EntryMapIconView(icon: .info, size: 20,
                                             tint: EntryMapPalette.freshness)
                            Text(rejection)
                                .entryMapText(EntryMapTypography.caption)
                                .foregroundStyle(EntryMapPalette.ink)
                        }
                    }
                }
                if let report {
                    Section {
                        Text(report)
                            .entryMapText(EntryMapTypography.caption)
                            .foregroundStyle(EntryMapPalette.ink)
                    }
                }
            }
            .entryMapForm()
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
        // Toolbar buttons, picker values and cursors. Here and not on the Form or the root --
        // see `entryMapForm()` for why both of those were tried and dropped.
        .tint(EntryMapPalette.violet600)
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
