import XCTest
@testable import FrontdoorCapture

/// TICK-029's local half: what is pending, what may be deleted, and what the operator is told.
final class CaptureQueueTests: XCTestCase {

    private var directory: URL!
    private var queue: CaptureQueue!
    /// Successive captures get successive times, so "written in this order" means "taken in this
    /// order" unless a test says otherwise.
    private var clock = 0

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("queue-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        queue = CaptureQueue(directory: directory)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    @discardableResult
    private func writeCapture(_ id: String, image: Data = Data("jpeg".utf8),
                              corruptHash: Bool = false,
                              capturedAt: String? = nil, withDepth: Bool = false) throws -> URL {
        clock += 1
        let stamp = capturedAt ?? String(format: "2026-09-02T%02d:00:00Z", 7 + clock)
        let imageURL = directory.appendingPathComponent("\(id).jpg")
        try image.write(to: imageURL)
        let sha = corruptHash ? String(repeating: "0", count: 64) : CaptureWriter.sha256(image)
        let sidecar: [String: Any] = [
            "capture_id": id, "entrance_id": "E-014", "captured_at": stamp,
            "image": ["path": "\(id).jpg", "sha256": sha, "width": 4032, "height": 3024],
            "depth": withDepth
                ? ["path": "\(id).depth", "sha256": String(repeating: "a", count: 64)]
                : NSNull(),
        ]
        let url = directory.appendingPathComponent("\(id).json")
        try JSONSerialization.data(withJSONObject: sidecar).write(to: url)
        return url
    }

    // MARK: what is pending (AC2)

    /// The queue is the directory, so surviving termination and restart is not a feature that has
    /// to work -- it is what reading the disk means. A fresh CaptureQueue over the same folder is
    /// exactly what the app has after a cold launch.
    func testAFreshQueueOverTheSameFolderSeesTheSameCaptures() throws {
        try writeCapture("c1"); try writeCapture("c2")
        XCTAssertEqual(CaptureQueue(directory: directory).count, 2)
    }

    /// Ids that sort the OPPOSITE way to the timestamps, so the order can only come from
    /// captured_at. The previous version used c1/c2/c3 written in scrambled order, which sorted
    /// into the right answer under either rule -- and it passed while pending() was sorting by a
    /// random UUID and promising "oldest first".
    func testCapturesDrainOldestFirstByCaptureTimeNotByIdentifier() throws {
        try writeCapture("zzz-first", capturedAt: "2026-09-02T08:00:00Z")
        try writeCapture("mmm-second", capturedAt: "2026-09-02T09:00:00Z")
        try writeCapture("aaa-third", capturedAt: "2026-09-02T10:00:00Z")
        XCTAssertEqual(
            queue.pending().map(\.captureId), ["zzz-first", "mmm-second", "aaa-third"],
            "order must follow captured_at, not the identifier")
    }

    /// Real capture ids are random UUIDs and carry no time at all, which is what made the old
    /// ordering meaningless in the field while passing in the suite.
    func testRealUUIDIdentifiersStillDrainInCaptureOrder() throws {
        let ids = (0..<6).map { _ in UUID().uuidString }
        for (index, id) in ids.enumerated() {
            try writeCapture(id, capturedAt: String(format: "2026-09-02T%02d:00:00Z", 8 + index))
        }
        XCTAssertEqual(queue.pending().map(\.captureId), ids)
    }

    /// Two presses inside one second share a timestamp. The order must still be the same on every
    /// run, or "the failure stays at the head" fails exactly when captures come fastest.
    func testCapturesSharingASecondAreOrderedDeterministically() throws {
        try writeCapture("b", capturedAt: "2026-09-02T09:00:00Z")
        try writeCapture("a", capturedAt: "2026-09-02T09:00:00Z")
        try writeCapture("c", capturedAt: "2026-09-02T09:00:00Z")
        XCTAssertEqual(queue.pending().map(\.captureId), ["a", "b", "c"])
        XCTAssertEqual(CaptureQueue(directory: directory).pending().map(\.captureId),
                       ["a", "b", "c"], "the order must not change between reads")
    }

    /// A sidecar with no captured_at cannot be placed in the order, and captured_at is a required
    /// schema field -- so its absence means a malformed record, not one to guess a position for.
    func testASidecarWithoutACaptureTimeIsSkipped() throws {
        try writeCapture("good")
        let bad: [String: Any] = [
            "capture_id": "no-time", "entrance_id": "E-014",
            "image": ["path": "x.jpg", "sha256": String(repeating: "0", count: 64)],
        ]
        try JSONSerialization.data(withJSONObject: bad)
            .write(to: directory.appendingPathComponent("no-time.json"))
        XCTAssertEqual(queue.pending().map(\.captureId), ["good"])
    }

    /// A sidecar that cannot be parsed is not a capture this can act on. Guessing at a partial one
    /// is how a half-written record gets uploaded as though it were whole.
    func testAnUnparseableSidecarIsSkippedRatherThanGuessedAt() throws {
        try writeCapture("good")
        try Data("{ not json".utf8).write(to: directory.appendingPathComponent("bad.json"))
        XCTAssertEqual(queue.pending().map(\.captureId), ["good"])
    }

    // MARK: deletion is gated on the bytes (AC5)

    func testACaptureIsDeletedOnlyAfterItsBytesMatchItsSidecar() throws {
        try writeCapture("c1")
        let capture = try XCTUnwrap(queue.pending().first)
        XCTAssertNoThrow(try queue.remove(capture).get())
        XCTAssertEqual(queue.count, 0)
    }

    /// The capture whose record is already wrong is the one that must not be destroyed: it is the
    /// only copy, and the mismatch is the evidence something went wrong.
    func testAMismatchedCaptureIsKeptNotDeleted() throws {
        try writeCapture("c1", corruptHash: true)
        let capture = try XCTUnwrap(queue.pending().first)
        guard case .failure(let failure) = queue.remove(capture) else {
            return XCTFail("a capture that does not match its own hash must not be deleted")
        }
        XCTAssertEqual(failure, .bytesDoNotMatch(captureId: "c1"))
        XCTAssertEqual(queue.count, 1, "it must still be on the phone")
        XCTAssertTrue(failure.message.contains("still on the phone"))
    }

    // MARK: draining (AC6)

    private struct AlwaysFails: CaptureUploader {
        struct Nope: LocalizedError { var errorDescription: String? { "the network is down." } }
        func upload(_ capture: CaptureQueue.Pending) async -> Result<Void, Error> {
            .failure(Nope())
        }
    }

    private struct AlwaysWorks: CaptureUploader {
        func upload(_ capture: CaptureQueue.Pending) async -> Result<Void, Error> { .success(()) }
    }

    private struct FailsAfter: CaptureUploader {
        let succeedFirst: Int
        final class Count: @unchecked Sendable { var value = 0 }
        let seen = Count()
        struct Nope: LocalizedError { var errorDescription: String? { "the network went away." } }
        func upload(_ capture: CaptureQueue.Pending) async -> Result<Void, Error> {
            seen.value += 1
            return seen.value <= succeedFirst ? .success(()) : .failure(Nope())
        }
    }

    func testADrainUploadsEverythingAndEmptiesThePhone() async throws {
        try writeCapture("c1"); try writeCapture("c2")
        let report = await QueueDrain(queue: queue, uploader: AlwaysWorks()).drain()
        XCTAssertEqual(report.uploaded, ["c1", "c2"])
        XCTAssertEqual(report.remaining, 0)
        XCTAssertTrue(report.message.contains("Nothing left on this phone"), report.message)
    }

    /// Nothing uploaded means nothing deleted. The failure that matters is the one that silently
    /// clears the queue.
    func testAFailedUploadDeletesNothing() async throws {
        try writeCapture("c1"); try writeCapture("c2")
        let report = await QueueDrain(queue: queue, uploader: AlwaysFails()).drain()
        XCTAssertTrue(report.uploaded.isEmpty)
        XCTAssertEqual(report.remaining, 2)
        XCTAssertEqual(queue.count, 2, "a failed drain must not remove captures")
    }

    /// Stopping at the first failure is deliberate: the common causes are systemic, and the one
    /// that failed stays at the head so the next drain retries it first.
    func testADrainStopsAtTheFirstFailureAndKeepsTheRest() async throws {
        try writeCapture("c1"); try writeCapture("c2"); try writeCapture("c3")
        let report = await QueueDrain(queue: queue, uploader: FailsAfter(succeedFirst: 1)).drain()
        XCTAssertEqual(report.uploaded, ["c1"])
        XCTAssertEqual(report.remaining, 2)
        XCTAssertEqual(queue.pending().map(\.captureId), ["c2", "c3"])
        XCTAssertTrue(report.message.contains("2 still on this phone"), report.message)
    }

    /// The default uploader refuses everything, because reporting success with no destination
    /// would delete a day's work.
    func testWithNoDestinationNothingIsUploadedAndNothingIsLost() async throws {
        try writeCapture("c1")
        let report = await QueueDrain(queue: queue, uploader: NoDestinationUploader()).drain()
        XCTAssertTrue(report.uploaded.isEmpty)
        XCTAssertEqual(queue.count, 1)
        XCTAssertTrue(report.message.contains("still on this phone"), report.message)
    }

    private struct FailsOnlyOn: CaptureUploader {
        let badId: String
        struct Nope: LocalizedError { var errorDescription: String? { "that one would not send." } }
        func upload(_ capture: CaptureQueue.Pending) async -> Result<Void, Error> {
            capture.captureId == badId ? .failure(Nope()) : .success(())
        }
    }

    /// Distinguishes stopping from merely reporting the last error.
    ///
    /// The earlier test used an uploader that failed from a point onward, so "stopped at c2" and
    /// "tried c2 and c3 and both failed" produced identical counts -- and a mutation that removed
    /// the early return passed. Here only c2 fails: if the drain carried on, c3 would upload and
    /// the queue would hold one capture instead of two.
    func testADrainReallyStopsRatherThanSkippingTheFailure() async throws {
        try writeCapture("c1"); try writeCapture("c2"); try writeCapture("c3")
        let report = await QueueDrain(queue: queue, uploader: FailsOnlyOn(badId: "c2")).drain()
        XCTAssertEqual(report.uploaded, ["c1"], "c3 must not be attempted after c2 failed")
        XCTAssertEqual(report.remaining, 2)
        XCTAssertEqual(queue.pending().map(\.captureId), ["c2", "c3"],
                       "the failed capture stays at the head so the next drain retries it first")
    }

    // MARK: deletion leaves nothing behind

    /// Image and depth go before the sidecar. The sidecar is what makes a capture visible to
    /// pending(), so removing it first and then failing on the image would strand bytes nothing
    /// ever enumerates again -- invisible to the count, never drained, never collected.
    func testNoFilesAreLeftBehindWhenACaptureIsRemoved() throws {
        try writeCapture("c1", withDepth: true)
        try Data("depth".utf8).write(to: directory.appendingPathComponent("c1.depth"))
        let capture = try XCTUnwrap(queue.pending().first)
        XCTAssertNotNil(capture.depthURL, "the sidecar must name the depth map for it to be removed")
        XCTAssertNoThrow(try queue.remove(capture).get())

        let left = try FileManager.default.contentsOfDirectory(atPath: directory.path)
        XCTAssertEqual(left.filter { $0.hasPrefix("c1") }, [], "orphans: \(left)")
    }

    /// A capture whose image cannot be read is refused before anything is deleted. The hash check
    /// is the gate, and it cannot pass on bytes it never saw.
    func testACaptureWhoseImageIsGoneIsRefusedNotDeleted() throws {
        try writeCapture("c1")
        let capture = try XCTUnwrap(queue.pending().first)
        try FileManager.default.removeItem(at: capture.imageURL)

        guard case .failure(let failure) = queue.remove(capture) else {
            return XCTFail("a capture with no readable image must not be removed")
        }
        guard case .unreadable = failure else {
            return XCTFail("expected unreadable, got \(failure)")
        }
        XCTAssertEqual(queue.count, 1, "its sidecar must survive so the capture stays visible")
        XCTAssertTrue(failure.message.contains("still on the phone"), failure.message)
    }

    /// An empty queue is not a failure, and must not read like one to someone about to leave.
    func testAnEmptyQueueSaysEverythingIsSafe() async throws {
        let report = await QueueDrain(queue: queue, uploader: AlwaysWorks()).drain()
        XCTAssertTrue(report.message.contains("already safe"), report.message)
    }
}
