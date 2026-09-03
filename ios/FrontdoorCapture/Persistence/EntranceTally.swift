import Foundation

/// How many photos each entrance has, for as long as the app is installed.
///
/// The count cannot be derived from what is on disk. `CaptureQueue` is the directory, and a
/// successful upload deletes the capture from it -- so counting sidecars would show six views for
/// an entrance shot in a dead spot and zero for the identical entrance shot in signal. Nor can it
/// live in `EntranceStore`, which is in memory only and forgets everything when the app is killed
/// mid-day. A capture-day counter that resets on relaunch is worse than none, because it reads as
/// authoritative.
///
/// So it is its own small file, written after the capture it counts. It is a *count*, not a gate:
/// D-021 originally put the shot plan in the instrument and the 2026-09-01 pivot moved it into
/// `docs/capture-protocol.md`, so nothing here refuses a capture or marks an entrance complete.
/// It answers the one question the paper checklist cannot answer at the door -- how many did I
/// already take of this one -- which under D-036 is asked by a single operator across 40-60
/// entrances with no second phone shooting the same doorway.
struct EntranceTally {
    var url: URL

    static func inDocuments() -> EntranceTally {
        EntranceTally(url: URL.documentsDirectory.appendingPathComponent("entrance-tally.json"))
    }

    private func load() -> [String: Int] {
        guard let data = try? Data(contentsOf: url),
              let counts = try? JSONDecoder().decode([String: Int].self, from: data)
        else { return [:] }
        return counts
    }

    func count(for entranceId: String) -> Int {
        load()[entranceId] ?? 0
    }

    var counts: [String: Int] { load() }

    /// Record one more photo for this entrance, and return the new total.
    ///
    /// A failed write returns the count the caller would have seen anyway rather than throwing.
    /// This is a convenience display: losing a tally must never cost a capture that is already
    /// safely on disk, and the capture is written before this runs.
    @discardableResult
    func increment(_ entranceId: String) -> Int {
        var counts = load()
        let updated = (counts[entranceId] ?? 0) + 1
        counts[entranceId] = updated
        if let data = try? JSONEncoder().encode(counts) {
            try? data.write(to: url, options: .atomic)
        }
        return updated
    }
}
