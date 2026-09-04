import Foundation

/// What it takes to get one capture off the phone.
///
/// A protocol rather than a concrete client because the destination is not settled: the app cannot
/// hold the R2 credentials -- `.env` scopes the images key to "Loader and server", and a key on a
/// phone in the field is a key that leaves with the phone -- and no server endpoint accepts an
/// upload yet. What IS settled is everything on this side of the seam: when a capture may be
/// deleted, in what order they drain, and what the operator is told. Those are built and tested
/// here so that landing a destination is a small change rather than the whole ticket.
/// A failure that belongs to ONE capture rather than to the run.
///
/// The distinction the drain needs and could not previously make. A dead network, a refused key
/// or a missing destination are properties of the moment: every capture behind this one will fail
/// the same way, so stopping saves an operator's battery. A capture the server will never accept
/// -- a hash that does not match its own sidecar, an id already taken, a body too large -- is a
/// property of that capture, and stopping on it means every capture behind it never uploads.
///
/// Conforming says only "skip this one and carry on". It never authorises deleting anything: a
/// rejected capture stays on the phone, is named in the report, and is retried on the next drain.
protocol PerCaptureUploadFailure: Error {}

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

/// Drains the queue, oldest first, stopping at the first SYSTEMIC failure and skipping captures
/// the destination will never accept.
///
/// Stopping rather than continuing is deliberate, and unchanged: the common failures are systemic
/// -- no network, no destination, expired credentials -- and pushing thirty captures at a dead
/// endpoint just to fail thirty times wastes the battery of someone standing outside a shop. The
/// one that failed stays at the head of the queue, so the next drain retries it first.
///
/// What changed (2026-09-04): that argument was being applied to failures it does not fit. A
/// capture the server refuses permanently -- 422 on its own hash, 409 on a taken id, 413 too
/// large -- would halt the drain at the head of the queue and EVERY capture behind it would never
/// upload, on every drain, for as long as the bad one sat there. A phone that looks like it is
/// syncing and is not. Those failures now skip: they are named in the report, nothing is deleted,
/// and the rest of the queue drains.
struct QueueDrain {
    struct Report: Equatable {
        var uploaded: [String] = []
        /// Captures the destination will never accept. Skipped, never deleted, always named --
        /// an operator who is told "3 uploaded" while two were silently dropped has been lied to.
        var rejected: [String] = []
        var remaining: Int = 0
        var stoppedBecause: String?
        /// Why the first rejected capture was refused, so the message can say something an
        /// operator can act on rather than just a count.
        var rejectionReason: String?

        /// Written for someone deciding whether it is safe to leave a site.
        var message: String {
            let rejects = rejected.isEmpty ? "" :
                " \(rejected.count) will not be accepted and need re-taking"
                + (rejectionReason.map { ": \($0)" } ?? ".")
            if let stoppedBecause {
                let sent = uploaded.isEmpty ? "Nothing was uploaded" : "\(uploaded.count) uploaded"
                return "\(sent); \(remaining) still on this phone. \(stoppedBecause)\(rejects)"
            }
            if uploaded.isEmpty && rejected.isEmpty {
                return "Nothing to upload. Everything here is already safe."
            }
            if uploaded.isEmpty {
                return "Nothing was uploaded; \(remaining) still on this phone.\(rejects)"
            }
            let left = remaining == 0 ? "Nothing left on this phone." : "\(remaining) still on this phone."
            return "\(uploaded.count) uploaded. \(left)\(rejects)"
        }
    }

    var queue: CaptureQueue
    var uploader: CaptureUploader

    func drain() async -> Report {
        var report = Report()
        for capture in queue.pending() {
            switch await uploader.upload(capture) {
            case .failure(let error) where error is PerCaptureUploadFailure:
                // This capture, not this run. Skip it and keep going: it stays on the phone, it
                // is named in the report, and the captures behind it are not held hostage to it.
                report.rejected.append(capture.captureId)
                if report.rejectionReason == nil {
                    report.rejectionReason = error.localizedDescription
                }
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
