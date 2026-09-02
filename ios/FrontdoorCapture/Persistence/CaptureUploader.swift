import Foundation

/// What it takes to get one capture off the phone.
///
/// A protocol rather than a concrete client because the destination is not settled: the app cannot
/// hold the R2 credentials -- `.env` scopes the images key to "Loader and server", and a key on a
/// phone in the field is a key that leaves with the phone -- and no server endpoint accepts an
/// upload yet. What IS settled is everything on this side of the seam: when a capture may be
/// deleted, in what order they drain, and what the operator is told. Those are built and tested
/// here so that landing a destination is a small change rather than the whole ticket.
protocol CaptureUploader {
    /// Send one capture. Returning success means the bytes are durably stored elsewhere AND their
    /// hash was checked at the far end -- not merely that a request returned 200. The queue
    /// deletes on this promise, so anything weaker loses data (AC4, AC5).
    func upload(_ capture: CaptureQueue.Pending) async -> Result<Void, Error>
}

/// The uploader in force until a destination exists.
///
/// It refuses every capture, which is the honest behaviour: nothing is uploaded, so nothing may be
/// deleted, and the pending count keeps rising where the operator can see it. The alternative --
/// reporting success and clearing the queue -- would delete the only copy of a day's work.
struct NoDestinationUploader: CaptureUploader {
    struct NotConfigured: LocalizedError {
        var errorDescription: String? {
            """
            No upload destination is configured yet, so captures stay on this phone. They are \
            safe, and they are not backed up anywhere else.
            """
        }
    }

    func upload(_ capture: CaptureQueue.Pending) async -> Result<Void, Error> {
        .failure(NotConfigured())
    }
}

/// Drains the queue, oldest first, and stops at the first failure.
///
/// Stopping rather than continuing is deliberate. The common failures are systemic -- no network,
/// no destination, expired credentials -- and pushing thirty captures at a dead endpoint just to
/// fail thirty times wastes the battery of someone standing outside a shop. The one that failed
/// stays at the head of the queue, so the next drain retries it first.
struct QueueDrain {
    struct Report: Equatable {
        var uploaded: [String] = []
        var remaining: Int = 0
        var stoppedBecause: String?

        /// Written for someone deciding whether it is safe to leave a site.
        var message: String {
            if let stoppedBecause {
                let sent = uploaded.isEmpty ? "Nothing was uploaded" : "\(uploaded.count) uploaded"
                return "\(sent); \(remaining) still on this phone. \(stoppedBecause)"
            }
            if uploaded.isEmpty { return "Nothing to upload. Everything here is already safe." }
            return "\(uploaded.count) uploaded. Nothing left on this phone."
        }
    }

    var queue: CaptureQueue
    var uploader: CaptureUploader

    func drain() async -> Report {
        var report = Report()
        for capture in queue.pending() {
            switch await uploader.upload(capture) {
            case .failure(let error):
                report.stoppedBecause = error.localizedDescription
                report.remaining = queue.count
                return report
            case .success:
                // Only now, and only if the bytes still match what the sidecar promised.
                if case .failure(let failure) = queue.remove(capture) {
                    report.stoppedBecause = failure.message
                    report.remaining = queue.count
                    return report
                }
                report.uploaded.append(capture.captureId)
            }
        }
        report.remaining = queue.count
        return report
    }
}
