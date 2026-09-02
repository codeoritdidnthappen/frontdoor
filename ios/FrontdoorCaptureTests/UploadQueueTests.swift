import XCTest
@testable import FrontdoorCapture

/// Tests for the pending-upload queue and its client (TICK-029, #33).
///
/// The failure these guard against is not a crash. It is a capture the app reports as uploaded and
/// deletes, which never reached the bucket — on a phone that holds the only copy.
final class UploadQueueTests: XCTestCase {

    private var dir: URL!

    override func setUpWithError() throws {
        dir = URL.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: dir)
    }

    @discardableResult
    private func writeCapture(
        _ id: String, entrance: String = "E-001", withDepth: Bool = false,
        image: Data = Data("jpg".utf8)
    ) throws -> URL {
        try image.write(to: dir.appendingPathComponent("\(id).jpg"))
        var sidecar: [String: Any] = [
            "capture_id": id,
            "entrance_id": entrance,
            "image": ["path": "\(id).jpg", "sha256": String(repeating: "a", count: 64)],
        ]
        if withDepth {
            try Data("depth".utf8).write(to: dir.appendingPathComponent("\(id).depth"))
            sidecar["depth"] = ["path": "\(id).depth",
                                "sha256": String(repeating: "b", count: 64)]
        } else {
            sidecar["depth"] = NSNull()
        }
        let url = dir.appendingPathComponent("\(id).json")
        try JSONSerialization.data(withJSONObject: sidecar).write(to: url)
        return url
    }

    // MARK: - what is pending

    func testAnImageOnlyCaptureQueuesOneFile() throws {
        try writeCapture("cap-1")
        let pending = UploadQueue.pending(in: dir)
        XCTAssertEqual(pending.count, 1)
        XCTAssertEqual(pending.first?.kind, .image)
        XCTAssertEqual(pending.first?.captureId, "cap-1")
        XCTAssertEqual(pending.first?.entranceId, "E-001")
    }

    func testACaptureWithDepthQueuesBothFiles() throws {
        try writeCapture("cap-1", withDepth: true)
        XCTAssertEqual(Set(UploadQueue.pending(in: dir).map(\.kind)), [.image, .depth])
    }

    func testAnAlreadyUploadedImageIsNotQueuedAgain() throws {
        try writeCapture("cap-1", withDepth: true)
        // "Uploaded" is represented by the file being gone, which is the whole state machine.
        try FileManager.default.removeItem(at: dir.appendingPathComponent("cap-1.jpg"))
        let pending = UploadQueue.pending(in: dir)
        XCTAssertEqual(pending.map(\.kind), [.depth])
    }

    func testASidecarWithNoBytesLeftQueuesNothing() throws {
        try writeCapture("cap-1")
        try FileManager.default.removeItem(at: dir.appendingPathComponent("cap-1.jpg"))
        XCTAssertEqual(UploadQueue.pendingCount(in: dir), 0)
    }

    func testAnUnreadableSidecarIsSkippedRatherThanCrashing() throws {
        try writeCapture("good")
        try Data("not json".utf8).write(to: dir.appendingPathComponent("bad.json"))
        XCTAssertEqual(UploadQueue.pending(in: dir).map(\.captureId), ["good"])
    }

    func testAMissingDirectoryIsEmptyNotAnError() {
        let absent = dir.appendingPathComponent("nope", isDirectory: true)
        XCTAssertEqual(UploadQueue.pending(in: absent), [])
    }

    func testTheEntranceIdIsCarriedThroughUnchanged() throws {
        try writeCapture("cap-1", entrance: "E-002")
        // The server derives the partition from this, so a coerced value would land the capture
        // in the wrong one. Nothing here decides the split, which is the point.
        XCTAssertEqual(UploadQueue.pending(in: dir).first?.entranceId, "E-002")
    }

    func testOldestCapturesDrainFirst() throws {
        try writeCapture("older")
        let newer = try writeCapture("newer")
        try FileManager.default.setAttributes(
            [.modificationDate: Date().addingTimeInterval(60)], ofItemAtPath: newer.path)
        XCTAssertEqual(UploadQueue.pending(in: dir).map(\.captureId), ["older", "newer"])
    }

    // MARK: - discarding

    func testDiscardingRemovesTheFileButKeepsTheSidecar() throws {
        try writeCapture("cap-1")
        let item = try XCTUnwrap(UploadQueue.pending(in: dir).first)
        XCTAssertTrue(UploadQueue.discardLocal(item))
        XCTAssertFalse(FileManager.default.fileExists(atPath: dir.appendingPathComponent("cap-1.jpg").path))
        // The sidecar is the record that goes to git (data/STORAGE.md); losing it loses the capture.
        XCTAssertTrue(FileManager.default.fileExists(atPath: dir.appendingPathComponent("cap-1.json").path))
    }

    // MARK: - reading the server's answer

    private func item(sha: String = String(repeating: "a", count: 64)) -> UploadQueue.Pending {
        UploadQueue.Pending(captureId: "cap-1", entranceId: "E-001", kind: .image,
                            fileURL: dir.appendingPathComponent("cap-1.jpg"), sha256: sha)
    }

    private func reply(_ dict: [String: Any]) -> Data {
        try! JSONSerialization.data(withJSONObject: dict)
    }

    func testAConfirmedUploadIsStored() {
        let sha = String(repeating: "a", count: 64)
        let outcome = UploadClient.outcome(
            status: 201,
            body: reply(["stored": true, "sha256": sha, "verified": "read-back"]),
            expecting: item())
        XCTAssertEqual(outcome, .stored(verified: "read-back"))
    }

    func testAConfirmationForADifferentDigestIsNotTreatedAsStored() {
        // Guards the case that would actually destroy data: a reply that says success but
        // describes some other file. Retry, never delete.
        let outcome = UploadClient.outcome(
            status: 201,
            body: reply(["stored": true, "sha256": String(repeating: "f", count: 64)]),
            expecting: item())
        guard case .retry = outcome else { return XCTFail("expected retry, got \(outcome)") }
    }

    func testA201ThatDoesNotSayStoredIsNotTreatedAsStored() {
        let outcome = UploadClient.outcome(
            status: 201, body: reply(["stored": false]), expecting: item())
        guard case .retry = outcome else { return XCTFail("expected retry, got \(outcome)") }
    }

    func testAnUnreadableSuccessBodyIsRetriedNotAssumed() {
        let outcome = UploadClient.outcome(
            status: 201, body: Data("<html>".utf8), expecting: item())
        guard case .retry = outcome else { return XCTFail("expected retry, got \(outcome)") }
    }

    func testAHashMismatchIsTerminalBecauseRetryingResendsTheSameBytes() {
        let outcome = UploadClient.outcome(status: 422, body: Data(), expecting: item())
        guard case .rejected = outcome else { return XCTFail("expected rejected, got \(outcome)") }
    }

    func testARefusedKeyIsTerminal() {
        let outcome = UploadClient.outcome(status: 401, body: Data(), expecting: item())
        guard case .rejected = outcome else { return XCTFail("expected rejected, got \(outcome)") }
    }

    func testServerErrorsAreRetriedSoNothingIsDeletedOnAGuess() {
        for status in [500, 502, 503, 504, 0] {
            let outcome = UploadClient.outcome(status: status, body: Data(), expecting: item())
            guard case .retry = outcome else {
                return XCTFail("status \(status) should retry, got \(outcome)")
            }
        }
    }

    func testTheTwoRetryableClientErrorsAreRetried() {
        for status in [408, 429] {
            let outcome = UploadClient.outcome(status: status, body: Data(), expecting: item())
            guard case .retry = outcome else {
                return XCTFail("status \(status) should retry, got \(outcome)")
            }
        }
    }

    func testOtherClientErrorsAreVisibleRefusalsRatherThanSilentForeverRetries() {
        // A build pointed at the wrong host gets 404 and a capture over the cap gets 413. Retrying
        // those on every connectivity change leaves the operator watching a count that never moves
        // with nothing saying why.
        for status in [404, 413, 415, 405] {
            let outcome = UploadClient.outcome(status: status, body: Data(), expecting: item())
            guard case .rejected = outcome else {
                return XCTFail("status \(status) should be rejected, got \(outcome)")
            }
        }
    }

    func testAConflictIsARefusalBecauseSomethingElseHoldsThatId() {
        let outcome = UploadClient.outcome(status: 409, body: Data(), expecting: item())
        guard case .rejected = outcome else { return XCTFail("expected rejected, got \(outcome)") }
    }

    func testAnIdempotentRepeatIsAcceptedAsStored() {
        // 200 rather than 201: the earlier upload landed and only its acknowledgement was lost.
        let sha = String(repeating: "a", count: 64)
        let outcome = UploadClient.outcome(
            status: 200, body: reply(["stored": true, "sha256": sha, "verified": "read-back"]),
            expecting: item())
        XCTAssertEqual(outcome, .stored(verified: "read-back"))
    }

    func testTheSpooledBodyMatchesTheInMemoryBody() throws {
        // The streaming path and the in-memory one must produce identical bytes, or the server
        // sees a different request than every test in this file exercises.
        let bytes = Data([0x00, 0xFF, 0x10, 0x00, 0x0A])
        let fileURL = dir.appendingPathComponent("cap-1.jpg")
        try bytes.write(to: fileURL)
        let spooled = try UploadClient.spool(item())
        defer { try? FileManager.default.removeItem(at: spooled) }
        XCTAssertEqual(try Data(contentsOf: spooled), UploadClient.body(for: item(), bytes: bytes))
    }

    // MARK: - the request

    func testTheRequestCarriesTheKeyAndEveryFieldTheServerRequires() {
        let client = UploadClient(baseURL: URL(string: "https://example.test")!, uploadKey: "k")
        let request = client.request(for: item(), bytes: Data("jpg".utf8))
        XCTAssertEqual(request.url?.path, "/upload")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-Frontdoor-Upload-Key"), "k")
        let body = String(data: request.httpBody ?? Data(), encoding: .utf8) ?? ""
        for field in ["kind", "capture_id", "entrance_id", "sha256", "bytes"] {
            XCTAssertTrue(body.contains("name=\"\(field)\""), "body is missing \(field)")
        }
        XCTAssertTrue(body.contains("image"), "kind should be the wire spelling")
    }

    func testTheBodyCarriesTheFileBytesVerbatim() {
        let bytes = Data([0x00, 0xFF, 0x10, 0x00])
        let body = UploadClient.body(for: item(), bytes: bytes)
        XCTAssertTrue(body.range(of: bytes) != nil, "raw bytes must survive the multipart encoding")
    }

    // MARK: - configuration

    func testAnUnconfiguredBuildProducesNoClientRatherThanAHalfOne() {
        XCTAssertNil(UploadSettings(serverURL: nil, uploadKey: "k").client())
        XCTAssertNil(UploadSettings(serverURL: URL(string: "https://x.test"), uploadKey: nil).client())
        XCTAssertNotNil(
            UploadSettings(serverURL: URL(string: "https://x.test"), uploadKey: "k").client())
    }
}
