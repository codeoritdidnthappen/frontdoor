import XCTest
@testable import FrontdoorCapture

final class LabelUploaderTests: XCTestCase {
    private let accepted = Data(#"{"accepted":true,"entrance_id":"E-901","created":true}"#.utf8)

    func testAC10CreatedAndIdempotentResponsesBothLockTheRecord() {
        for status in [200, 201] {
            XCTAssertEqual(
                ServerLabelUploader.outcome(
                    status: status, body: accepted, expectedEntranceId: "E-901"),
                .accepted)
        }
    }

    func testAC10MismatchedAcknowledgementNeverLocksTheRecord() {
        guard case .retry = ServerLabelUploader.outcome(
            status: 201, body: accepted, expectedEntranceId: "E-902")
        else { return XCTFail("mismatched acknowledgement was accepted") }
    }

    func testAC10ConflictIsPermanentAndNamed() {
        let body = Data(#"{"error":"label already locked","detail":"different truth"}"#.utf8)
        XCTAssertEqual(
            ServerLabelUploader.outcome(
                status: 409, body: body, expectedEntranceId: "E-901"),
            .conflict("different truth"))
    }

    func testAC7NetworkAndServerFailuresRemainRetryable() {
        for status in [0, 401, 429, 500, 503] {
            guard case .retry = ServerLabelUploader.outcome(
                status: status, body: Data(), expectedEntranceId: "E-901")
            else { return XCTFail("\(status) must remain queued") }
        }
    }

    func testAC7DrainKeepsRetryableRecordAndLocksAcceptedRecord() async throws {
        let retryURL = URL.temporaryDirectory.appendingPathComponent("retry-\(UUID().uuidString)")
        let acceptedURL = URL.temporaryDirectory.appendingPathComponent("accepted-\(UUID().uuidString)")
        defer {
            try? FileManager.default.removeItem(at: retryURL)
            try? FileManager.default.removeItem(at: acceptedURL)
        }
        let answers = Dictionary(uniqueKeysWithValues: ScreeningCriterion.allCases.map {
            ($0, LabelTruth.present)
        })
        let retryQueue = LabelQueue(url: retryURL)
        _ = retryQueue.save(entranceId: "E-901", labeledBy: "James", answers: answers)
        let retry = await LabelQueueDrain(
            queue: retryQueue, uploader: FixedLabelUploader(outcome: .retry("offline"))).drain()
        XCTAssertEqual(retry.remaining, 1)
        guard case .success(let retryRecord) = retryQueue.record(for: "E-901") else {
            return XCTFail("retry queue unreadable")
        }
        XCTAssertEqual(retryRecord?.state, .queued)

        let acceptedQueue = LabelQueue(url: acceptedURL)
        _ = acceptedQueue.save(entranceId: "E-901", labeledBy: "James", answers: answers)
        let acceptedReport = await LabelQueueDrain(
            queue: acceptedQueue, uploader: FixedLabelUploader(outcome: .accepted)).drain()
        XCTAssertEqual(acceptedReport.remaining, 0)
        guard case .success(let acceptedRecord) = acceptedQueue.record(for: "E-901") else {
            return XCTFail("accepted queue unreadable")
        }
        XCTAssertEqual(acceptedRecord?.state, .accepted)
    }

    func testAC7EditDuringUploadCannotBeLockedByAStaleAcknowledgement() async throws {
        let url = URL.temporaryDirectory.appendingPathComponent("race-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: url) }
        let queue = LabelQueue(url: url)
        var answers = Dictionary(uniqueKeysWithValues: ScreeningCriterion.allCases.map {
            ($0, LabelTruth.present)
        })
        _ = queue.save(entranceId: "E-901", labeledBy: "James", answers: answers)
        let uploader = SuspendedLabelUploader()
        let draining = Task {
            await LabelQueueDrain(queue: queue, uploader: uploader).drain()
        }
        await uploader.waitUntilStarted()
        answers[.handrails] = .absent
        _ = queue.save(entranceId: "E-901", labeledBy: "James", answers: answers)
        await uploader.finish(with: .accepted)
        let report = await draining.value
        XCTAssertEqual(report.remaining, 1)
        guard case .success(let record) = queue.record(for: "E-901") else {
            return XCTFail("queue unreadable")
        }
        XCTAssertEqual(record?.state, .queued)
        XCTAssertEqual(record?.answers["handrails"], "absent")
        XCTAssertTrue(report.message?.contains("changed while uploading") == true)
    }

    func testAC10EditDuringUploadCannotBeConflictedByAStaleResponse() async throws {
        let url = URL.temporaryDirectory.appendingPathComponent("conflict-race-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: url) }
        let queue = LabelQueue(url: url)
        var answers = Dictionary(uniqueKeysWithValues: ScreeningCriterion.allCases.map {
            ($0, LabelTruth.present)
        })
        _ = queue.save(entranceId: "E-901", labeledBy: "James", answers: answers)
        let uploader = SuspendedLabelUploader()
        let draining = Task {
            await LabelQueueDrain(queue: queue, uploader: uploader).drain()
        }
        await uploader.waitUntilStarted()
        answers[.handrails] = .absent
        _ = queue.save(entranceId: "E-901", labeledBy: "James", answers: answers)
        await uploader.finish(with: .conflict("older choices already accepted"))
        let report = await draining.value
        XCTAssertEqual(report.remaining, 1)
        guard case .success(let record) = queue.record(for: "E-901") else {
            return XCTFail("queue unreadable")
        }
        XCTAssertEqual(record?.state, .queued)
        XCTAssertEqual(record?.answers["handrails"], "absent")
        XCTAssertTrue(report.message?.contains("changed while uploading") == true)
    }

    func testAC10ConflictTransitionWriteFailureStaysPendingAndIsReported() async {
        let url = URL.temporaryDirectory.appendingPathComponent("conflict-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: url) }
        let answers = Dictionary(uniqueKeysWithValues: ScreeningCriterion.allCases.map {
            ($0, LabelTruth.present)
        })
        let writable = LabelQueue(url: url)
        _ = writable.save(entranceId: "E-901", labeledBy: "James", answers: answers)
        let failing = LabelQueue(url: url) { _, _ in throw LabelQueue.Failure.unreadable }
        let report = await LabelQueueDrain(
            queue: failing,
            uploader: FixedLabelUploader(outcome: .conflict("different truth"))).drain()
        XCTAssertEqual(report.remaining, 1)
        XCTAssertTrue(report.message?.contains("could not be read") == true)
        guard case .success(let record) = writable.record(for: "E-901") else {
            return XCTFail("queue unreadable")
        }
        XCTAssertEqual(record?.state, .queued)
    }
}

private struct FixedLabelUploader: EntranceLabelUploader {
    let outcome: LabelUploadOutcome

    func upload(_ record: EntranceLabelRecord) async -> LabelUploadOutcome { outcome }
}

private actor SuspendedLabelUploader: EntranceLabelUploader {
    private var started = false
    private var continuation: CheckedContinuation<LabelUploadOutcome, Never>?

    func upload(_ record: EntranceLabelRecord) async -> LabelUploadOutcome {
        await withCheckedContinuation {
            continuation = $0
            started = true
        }
    }

    func waitUntilStarted() async {
        while !started { await Task.yield() }
    }

    func finish(with outcome: LabelUploadOutcome) {
        continuation?.resume(returning: outcome)
        continuation = nil
    }
}
