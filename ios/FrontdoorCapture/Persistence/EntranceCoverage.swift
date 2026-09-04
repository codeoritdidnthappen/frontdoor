import Foundation

/// Which views of the protocol's set each entrance has (#289).
///
/// A sibling of `EntranceTally` rather than a change to it, for two reasons. The tally's file is
/// `[String: Int]` and it returns an empty map when decoding fails, so widening its shape would
/// silently reset every count already on the capture device. And the two answer different
/// questions: the tally counts photos, including the deviations and extra angles the protocol
/// explicitly allows, while this records which named views are covered. A count of six is not the
/// same fact as a complete set.
///
/// Written after the capture it records, and a failed write costs guidance rather than data: the
/// photo and its sidecar are already on disk before this is touched.
struct EntranceCoverage {
    var url: URL

    static func inDocuments() -> EntranceCoverage {
        EntranceCoverage(url: URL.documentsDirectory.appendingPathComponent("entrance-views.json"))
    }

    private func load() -> [String: [String]] {
        guard let data = try? Data(contentsOf: url),
              let stored = try? JSONDecoder().decode([String: [String]].self, from: data)
        else { return [:] }
        return stored
    }

    func coverage(for entranceId: String) -> ViewSetCoverage {
        // An unrecognised slot in the file is dropped rather than refused: a build that removed a
        // view should still show the operator the views it does have.
        ViewSetCoverage(captured: Set((load()[entranceId] ?? []).compactMap(ViewSlot.init(rawValue:))))
    }

    /// Every entrance this phone has recorded a view for, by ID.
    ///
    /// The file is the only durable record of which doorways have been shot: `EntranceStore` is in
    /// memory and forgets on relaunch, and the capture directory empties as the queue drains. So
    /// this is what answers "did I finish E-014?" after leaving the street.
    func all() -> [String: ViewSetCoverage] {
        load().mapValues {
            ViewSetCoverage(captured: Set($0.compactMap(ViewSlot.init(rawValue:))))
        }
    }

    /// Record that this entrance now has this view, and return the coverage that results.
    @discardableResult
    func record(_ slot: ViewSlot, for entranceId: String) -> ViewSetCoverage {
        var stored = load()
        var slots = stored[entranceId] ?? []
        if !slots.contains(slot.rawValue) {
            slots.append(slot.rawValue)
            stored[entranceId] = slots
            if let data = try? JSONEncoder().encode(stored) {
                try? data.write(to: url, options: .atomic)
            }
        }
        return ViewSetCoverage(captured: Set(slots.compactMap(ViewSlot.init(rawValue:))))
    }
}
