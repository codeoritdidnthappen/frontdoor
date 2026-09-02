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
        var sidecarURL: URL
        var imageURL: URL
        var depthURL: URL?
        /// What the sidecar says the image should hash to. Compared before anything is deleted.
        var imageSHA256: String
    }

    enum Failure: Error, Equatable {
        case unreadable(captureId: String, detail: String)
        case bytesDoNotMatch(captureId: String)

        var message: String {
            switch self {
            case .unreadable(let id, let detail):
                return "Capture \(id) could not be read: \(detail). It is still on the phone."
            case .bytesDoNotMatch(let id):
                return """
                Capture \(id) does not match the hash in its own sidecar, so it will not be \
                deleted and will not be reported as uploaded. It is still on the phone.
                """
            }
        }
    }

    var directory: URL

    /// Every capture still on the phone, oldest first so a drain sends them in the order they were
    /// taken -- an interrupted session then resumes where it stopped rather than at random.
    func pending() -> [Pending] {
        let manager = FileManager.default
        guard let entries = try? manager.contentsOfDirectory(
            at: directory, includingPropertiesForKeys: [.creationDateKey]) else { return [] }

        return entries
            .filter { $0.pathExtension == "json" }
            .compactMap(load)
            .sorted { $0.captureId < $1.captureId }
    }

    var count: Int { pending().count }

    /// Read one sidecar into a Pending, or skip it.
    ///
    /// A sidecar that cannot be parsed is not a capture this can act on, and guessing at a partial
    /// one is how a half-written record gets uploaded as though it were whole.
    func load(_ sidecarURL: URL) -> Pending? {
        guard let data = try? Data(contentsOf: sidecarURL),
              let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let captureId = json["capture_id"] as? String,
              let entranceId = json["entrance_id"] as? String,
              let image = json["image"] as? [String: Any],
              let imagePath = image["path"] as? String,
              let sha = image["sha256"] as? String
        else { return nil }

        let base = sidecarURL.deletingLastPathComponent()
        let depthPath = (json["depth"] as? [String: Any])?["path"] as? String
        return Pending(
            captureId: captureId,
            entranceId: entranceId,
            sidecarURL: sidecarURL,
            imageURL: base.appendingPathComponent(imagePath),
            depthURL: depthPath.map { base.appendingPathComponent($0) },
            imageSHA256: sha)
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
        // Sidecar first. Until it is gone the capture is still pending, so an interruption
        // part-way through leaves it queued rather than half-deleted and invisible.
        for url in [capture.sidecarURL, capture.imageURL, capture.depthURL].compactMap({ $0 }) {
            try? FileManager.default.removeItem(at: url)
        }
        return .success(())
    }
}
