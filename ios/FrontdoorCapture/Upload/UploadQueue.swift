import Foundation

/// The pending-upload queue (TICK-029, #33).
///
/// **The queue is the captures directory.** There is no separate index file, and that is the
/// design rather than a shortcut: an index is a second source of truth that can disagree with the
/// disk, and the disagreement shows up as a capture the app believes is safe and deletes. Here,
/// "still on the phone" *is* "not yet uploaded", so the queue survives app termination and device
/// restart for free (AC2) and cannot drift from what actually exists.
///
/// A capture leaves the queue one file at a time. The sidecar is never uploaded and never deleted:
/// `data/STORAGE.md` puts sidecars in git, not in the bucket, so it stays on the device as the
/// record of the capture after its bytes are gone. That is also what makes progress derivable —
/// sidecar present with no `.jpg` beside it means the image is already stored.
enum UploadQueue {

    struct Pending: Equatable {
        enum Kind: String, Equatable {
            case image
            case depth
        }

        var captureId: String
        var split: String
        var kind: Kind
        var fileURL: URL
        var sha256: String
    }

    /// What a sidecar has to tell us to upload the capture it describes.
    ///
    /// A read model of its own rather than making `Sidecar` `Decodable`: the writer's job is to
    /// emit the frozen schema, and widening it to round-trip would let a change here alter what
    /// gets written. This decodes the few fields upload needs and ignores the rest.
    private struct SidecarHead: Decodable {
        struct Ref: Decodable {
            let path: String
            let sha256: String
        }
        let capture_id: String
        let split: String
        let image: Ref
        let depth: Ref?
    }

    /// Everything still waiting to be uploaded, oldest sidecar first.
    ///
    /// Ordering is by sidecar modification date so a field session drains roughly in the order it
    /// was shot: if a drain is cut short by signal or battery, the captures that survive on the
    /// phone are the most recent ones, which are the easiest to re-shoot.
    static func pending(in directory: URL) -> [Pending] {
        let fm = FileManager.default
        guard let names = try? fm.contentsOfDirectory(
            at: directory, includingPropertiesForKeys: [.contentModificationDateKey]) else {
            return []
        }

        let sidecars = names.filter { $0.pathExtension == "json" }.sorted {
            let a = (try? $0.resourceValues(forKeys: [.contentModificationDateKey]))?
                .contentModificationDate ?? .distantPast
            let b = (try? $1.resourceValues(forKeys: [.contentModificationDateKey]))?
                .contentModificationDate ?? .distantPast
            if a == b { return $0.lastPathComponent < $1.lastPathComponent }
            return a < b
        }

        var work: [Pending] = []
        for sidecarURL in sidecars {
            guard let bytes = try? Data(contentsOf: sidecarURL),
                  let head = try? JSONDecoder().decode(SidecarHead.self, from: bytes) else {
                // An unreadable sidecar is left alone rather than skipped past silently -- but it
                // also cannot be uploaded, because nothing here knows where its bytes belong.
                continue
            }

            let imageURL = directory.appendingPathComponent(head.image.path)
            if fm.fileExists(atPath: imageURL.path) {
                work.append(Pending(captureId: head.capture_id, split: head.split,
                                    kind: .image, fileURL: imageURL, sha256: head.image.sha256))
            }
            if let depth = head.depth {
                let depthURL = directory.appendingPathComponent(depth.path)
                if fm.fileExists(atPath: depthURL.path) {
                    work.append(Pending(captureId: head.capture_id, split: head.split,
                                        kind: .depth, fileURL: depthURL, sha256: depth.sha256))
                }
            }
        }
        return work
    }

    /// How many files are still waiting, for the operator-facing count (AC6).
    static func pendingCount(in directory: URL) -> Int {
        pending(in: directory).count
    }

    /// Remove the local copy of one uploaded file.
    ///
    /// Called only after the server has confirmed the stored bytes hash to the value the sidecar
    /// recorded (AC5). The sidecar itself is deliberately never removed.
    @discardableResult
    static func discardLocal(_ item: Pending) -> Bool {
        do {
            try FileManager.default.removeItem(at: item.fileURL)
            return true
        } catch {
            return false
        }
    }
}
