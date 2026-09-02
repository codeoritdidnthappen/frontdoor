import Foundation

/// The captures on this phone that have not been confirmed safe elsewhere yet (TICK-029).
///
/// The queue is the directory. There is no separate index, no plist of pending ids, nothing that
/// can disagree with what is actually on disk -- and so nothing to rebuild after a crash, and no
/// way for a capture to be dropped from a list while its bytes sit there unnoticed. A capture is
/// pending because its sidecar is present; it stops being pending when it is deleted, and it is
/// only deleted once its bytes have been read back and matched (AC5).
///
/// That also makes AC2 fall out rather than need arranging: surviving termination and restart is
/// the default when the state is the filesystem.
struct CaptureQueue {

    /// One capture, as it sits on disk.
    struct Pending: Equatable, Identifiable {
        var id: String { captureId }
        var captureId: String
        var entranceId: String
        /// The shutter press, RFC 3339 UTC, straight from the sidecar. Ordering comes from this
        /// rather than from `captureId`, which is a random UUID and carries no time at all, and
        /// rather than from the filesystem's creation date, which a backup or a restore rewrites.
        var capturedAt: String
        var sidecarURL: URL
        var imageURL: URL
        var depthURL: URL?
        /// What the sidecar says the image should hash to. Compared before anything is deleted.
        var imageSHA256: String
        /// What the sidecar says the depth map should hash to, when there is one.
        ///
        /// Carried for the same reason as the image's: an uploader that hashed the file on disk
        /// instead would send whatever is there, corruption included, and the far end would
        /// confirm the corrupt bytes as a match. The sidecar is the record that vouches for them.
        var depthSHA256: String?
    }

    enum Failure: Error, Equatable {
        case unreadable(captureId: String, detail: String)
        case bytesDoNotMatch(captureId: String)
        case partiallyDeleted(captureId: String, leftBehind: [String])

        var message: String {
            switch self {
            case .unreadable(let id, let detail):
                return "Capture \(id) could not be read: \(detail). It is still on the phone."
            case .bytesDoNotMatch(let id):
                return """
                Capture \(id) does not match the hash in its own sidecar, so it will not be \
                deleted and will not be reported as uploaded. It is still on the phone.
                """
            case .partiallyDeleted(let id, let leftBehind):
                return """
                Capture \(id) uploaded, but \(leftBehind.joined(separator: " and ")) could not be \
                removed from the phone. Those files are taking up space and nothing will collect \
                them; the capture itself is safely uploaded.
                """
            }
        }
    }

    var directory: URL

    /// Every capture still on the phone, oldest first so a drain sends them in the order they were
    /// taken -- an interrupted session then resumes where it stopped rather than at random.
    ///
    /// Ordered by `captured_at`. An earlier version sorted by `captureId`, which is a random UUID,
    /// so the promise in the line above was simply false: the order was arbitrary, and neither
    /// "resumes where it stopped" nor QueueDrain's "the failure stays at the head" held. Its test
    /// passed because the fixtures were named c1, c2, c3, which sort into the answer by accident.
    ///
    /// RFC 3339 UTC sorts correctly as text -- fixed width, zero padded, one timezone -- which is
    /// why the schema pins that spelling.
    func pending() -> [Pending] {
        guard let entries = try? FileManager.default.contentsOfDirectory(
            at: directory, includingPropertiesForKeys: nil) else { return [] }

        return entries
            .filter { $0.pathExtension == "json" }
            .compactMap(load)
            // captureId breaks ties. captured_at has second resolution, so two presses inside one
            // second share a timestamp -- and without a tie-break their relative order is whatever
            // the filesystem enumerated, which differs between runs. An unstable order means "the
            // failure stays at the head" stops holding exactly when captures come fastest.
            .sorted { ($0.capturedAt, $0.captureId) < ($1.capturedAt, $1.captureId) }
    }

    /// How many captures are on the phone.
    ///
    /// Counts sidecars without opening them. This runs on the main actor after every shutter press
    /// and on every foreground, and parsing 200-odd JSON files there is a hitch that grows through
    /// the day -- worst exactly when the operator is busiest. Nothing inside a sidecar is needed to
    /// count it.
    var count: Int {
        guard let entries = try? FileManager.default.contentsOfDirectory(
            at: directory, includingPropertiesForKeys: nil) else { return 0 }
        return entries.filter { $0.pathExtension == "json" }.count
    }

    /// Read one sidecar into a Pending, or skip it.
    ///
    /// A sidecar that cannot be parsed is not a capture this can act on, and guessing at a partial
    /// one is how a half-written record gets uploaded as though it were whole.
    func load(_ sidecarURL: URL) -> Pending? {
        guard let data = try? Data(contentsOf: sidecarURL),
              let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let captureId = json["capture_id"] as? String,
              let entranceId = json["entrance_id"] as? String,
              let capturedAt = json["captured_at"] as? String,
              let image = json["image"] as? [String: Any],
              let imagePath = image["path"] as? String,
              let sha = image["sha256"] as? String
        else { return nil }

        let base = sidecarURL.deletingLastPathComponent()
        let depth = json["depth"] as? [String: Any]
        let depthPath = depth?["path"] as? String
        return Pending(
            captureId: captureId,
            entranceId: entranceId,
            capturedAt: capturedAt,
            sidecarURL: sidecarURL,
            imageURL: base.appendingPathComponent(imagePath),
            depthURL: depthPath.map { base.appendingPathComponent($0) },
            imageSHA256: sha,
            depthSHA256: depth?["sha256"] as? String)
    }

    /// Remove a capture from the phone, but only once its bytes have been proven intact.
    ///
    /// AC5 says a local capture is deleted only after its upload is confirmed by a successful hash
    /// check. The confirmation belongs to whoever uploaded it; what this guarantees is the other
    /// half -- that the bytes still on disk are the bytes the sidecar vouches for. Deleting on a
    /// mismatch would destroy the only copy of a capture whose record was already wrong.
    func remove(_ capture: Pending) -> Result<Void, Failure> {
        let data: Data
        do {
            data = try Data(contentsOf: capture.imageURL)
        } catch {
            return .failure(.unreadable(
                captureId: capture.captureId, detail: error.localizedDescription))
        }
        guard CaptureWriter.sha256(data) == capture.imageSHA256 else {
            return .failure(.bytesDoNotMatch(captureId: capture.captureId))
        }
        // Image and depth first, sidecar last. The sidecar is what makes a capture visible to
        // `pending()`, so removing it first and then failing on the image would strand bytes that
        // nothing ever enumerates again -- invisible to the count, never drained, never collected.
        // This way a failure leaves the capture whole and still queued.
        var leftBehind: [String] = []
        for url in [capture.imageURL, capture.depthURL].compactMap({ $0 }) {
            guard FileManager.default.fileExists(atPath: url.path) else { continue }
            do {
                try FileManager.default.removeItem(at: url)
            } catch {
                leftBehind.append(url.lastPathComponent)
            }
        }
        guard leftBehind.isEmpty else {
            // Reported rather than swallowed, and the sidecar is left in place so the capture is
            // still listed. Better a capture that drains twice than bytes nothing can see.
            return .failure(.partiallyDeleted(
                captureId: capture.captureId, leftBehind: leftBehind))
        }
        try? FileManager.default.removeItem(at: capture.sidecarURL)
        return .success(())
    }
}
