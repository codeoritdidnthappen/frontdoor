import XCTest
@testable import FrontdoorCapture

/// Tests for the upload destination (TICK-029, #33).
///
/// `CaptureQueue` deletes a capture on this uploader's word, so the failure these guard against is
/// a `.success` for bytes that never reached the bucket, on a phone holding the only copy.
final class ServerUploaderTests: XCTestCase {

    private var dir: URL!
    private let sha = String(repeating: "a", count: 64)

    override func setUpWithError() throws {
        dir = URL.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: dir)
    }

    private func reply(_ dict: [String: Any]) -> Data {
        try! JSONSerialization.data(withJSONObject: dict)
    }

    private func isSuccess(_ result: Result<Void, Error>) -> Bool {
        if case .success = result { return true }
        return false
    }

    // MARK: - reading the server's answer

    func testAConfirmedUploadSucceeds() {
        XCTAssertTrue(isSuccess(ServerUploader.outcome(
            status: 201, body: reply(["stored": true, "sha256": sha, "verified": "read-back"]),
            expecting: sha)))
    }

    func testAnIdempotentRepeatSucceeds() {
        // 200: the earlier upload landed and only its acknowledgement was lost, which is the
        // ordinary outcome of a drain interrupted by a dropped connection.
        XCTAssertTrue(isSuccess(ServerUploader.outcome(
            status: 200, body: reply(["stored": true, "sha256": sha]), expecting: sha)))
    }

    func testAConfirmationForADifferentFileIsNotSuccess() {
        // The case that would actually destroy data: a reply that says success but describes some
        // other file. The queue would delete a capture that was never stored.
        XCTAssertFalse(isSuccess(ServerUploader.outcome(
            status: 201, body: reply(["stored": true, "sha256": String(repeating: "f", count: 64)]),
            expecting: sha)))
    }

    func testA201ThatDoesNotSayStoredIsNotSuccess() {
        XCTAssertFalse(isSuccess(ServerUploader.outcome(
            status: 201, body: reply(["stored": false, "sha256": sha]), expecting: sha)))
    }

    func testAnUnreadableSuccessBodyIsNotSuccess() {
        XCTAssertFalse(isSuccess(ServerUploader.outcome(
            status: 201, body: Data("<html>".utf8), expecting: sha)))
    }

    func testEveryErrorStatusFails() {
        for status in [400, 401, 404, 408, 409, 413, 415, 422, 429, 500, 502, 503, 0] {
            XCTAssertFalse(
                isSuccess(ServerUploader.outcome(status: status, body: Data(), expecting: sha)),
                "status \(status) must not be reported as stored")
        }
    }

    func testAPermanentRefusalSaysItWillNotFixItself() {
        // The operator reads this message while deciding whether to keep shooting. A wrong host
        // (404) must not read like weather.
        let result = ServerUploader.outcome(status: 404, body: Data(), expecting: sha)
        guard case .failure(let error) = result else { return XCTFail("expected failure") }
        XCTAssertTrue(error.localizedDescription.contains("will not fix itself"))
    }

    func testAHashMismatchSaysNothingWasStored() {
        let result = ServerUploader.outcome(status: 422, body: Data(), expecting: sha)
        guard case .failure(let error) = result else { return XCTFail("expected failure") }
        XCTAssertTrue(error.localizedDescription.contains("Nothing was stored"))
    }

    // MARK: - the request

    func testTheBodyCarriesEveryFieldTheServerRequiresAndNoSplit() throws {
        let file = dir.appendingPathComponent("cap-1.jpg")
        try Data("jpg".utf8).write(to: file)
        let spooled = try ServerUploader.spool(
            captureId: "cap-1", entranceId: "E-001", kind: "image", fileURL: file, sha256: sha)
        defer { try? FileManager.default.removeItem(at: spooled) }
        let body = String(data: try Data(contentsOf: spooled), encoding: .utf8) ?? ""

        for field in ["kind", "capture_id", "entrance_id", "sha256", "bytes"] {
            XCTAssertTrue(body.contains("name=\"\(field)\""), "body is missing \(field)")
        }
        // The server derives the partition from entrance_id. Sending a split would be an authority
        // this app does not have, and a drifted seed could then place a sealed capture in open/.
        XCTAssertFalse(body.contains("name=\"split\""), "the app must not send a split")
        XCTAssertTrue(body.contains("E-001"))
    }

    func testTheSpooledBodyCarriesTheFileBytesVerbatim() throws {
        let bytes = Data([0x00, 0xFF, 0x10, 0x00, 0x0A])
        let file = dir.appendingPathComponent("cap-1.jpg")
        try bytes.write(to: file)
        let spooled = try ServerUploader.spool(
            captureId: "cap-1", entranceId: "E-001", kind: "depth", fileURL: file, sha256: sha)
        defer { try? FileManager.default.removeItem(at: spooled) }
        XCTAssertNotNil(try Data(contentsOf: spooled).range(of: bytes),
                        "raw bytes must survive the multipart encoding")
    }

    func testSpoolingStreamsAFileLargerThanOneChunk() throws {
        // The spool reads in 1 MB chunks; a file spanning several must come through whole.
        let bytes = Data(repeating: 0xAB, count: 3 * 1024 * 1024 + 17)
        let file = dir.appendingPathComponent("cap-1.jpg")
        try bytes.write(to: file)
        let spooled = try ServerUploader.spool(
            captureId: "cap-1", entranceId: "E-001", kind: "image", fileURL: file, sha256: sha)
        defer { try? FileManager.default.removeItem(at: spooled) }
        let written = try Data(contentsOf: spooled)
        XCTAssertEqual(written.count,
                       ServerUploader.prologue(captureId: "cap-1", entranceId: "E-001",
                                               kind: "image", sha256: sha,
                                               filename: "cap-1.jpg").count
                       + bytes.count + ServerUploader.epilogue().count)
    }

    // MARK: - configuration

    func testAnUnconfiguredBuildGetsNoUploaderRatherThanAHalfOne() {
        XCTAssertNil(UploadSettings(serverURL: nil, uploadKey: "k").uploader())
        XCTAssertNil(UploadSettings(serverURL: URL(string: "https://x.test"), uploadKey: nil).uploader())
        XCTAssertNotNil(
            UploadSettings(serverURL: URL(string: "https://x.test"), uploadKey: "k").uploader())
    }

    // MARK: - a capture is its image AND its depth

    /// Answers every request from a script, recording what was asked.
    ///
    /// A real transport stub rather than a stand-in uploader: the two-part contract lives inside
    /// `ServerUploader.upload`, so testing it through a fake `CaptureUploader` would only assert
    /// that the fake does what the fake does.
    private final class StubProtocol: URLProtocol {
        nonisolated(unsafe) static var script: [(status: Int, body: Data)] = []
        nonisolated(unsafe) static var seen: [String] = []

        override class func canInit(with request: URLRequest) -> Bool { true }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

        override func startLoading() {
            let body = (request.httpBodyStream.map { stream -> Data in
                stream.open()
                defer { stream.close() }
                var data = Data()
                var buffer = [UInt8](repeating: 0, count: 4096)
                while stream.hasBytesAvailable {
                    let read = stream.read(&buffer, maxLength: buffer.count)
                    if read <= 0 { break }
                    data.append(contentsOf: buffer[0..<read])
                }
                return data
            }) ?? request.httpBody ?? Data()
            let text = String(data: body, encoding: .utf8) ?? ""
            Self.seen.append(text.contains("name=\"kind\"\r\n\r\ndepth") ? "depth" : "image")

            let step = Self.script.isEmpty
                ? (status: 500, body: Data())
                : Self.script.removeFirst()
            let response = HTTPURLResponse(
                url: request.url!, statusCode: step.status, httpVersion: nil, headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: step.body)
            client?.urlProtocolDidFinishLoading(self)
        }

        override func stopLoading() {}
    }

    private func stubbedUploader() -> ServerUploader {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        return ServerUploader(baseURL: URL(string: "https://example.test")!,
                              uploadKey: "k", session: URLSession(configuration: config))
    }

    private func captureWithDepth() throws -> CaptureQueue.Pending {
        let image = dir.appendingPathComponent("cap-1.jpg")
        let depth = dir.appendingPathComponent("cap-1.depth")
        let imageBytes = Data("jpg".utf8)
        let depthBytes = Data("depth".utf8)
        try imageBytes.write(to: image)
        try depthBytes.write(to: depth)
        return CaptureQueue.Pending(
            captureId: "cap-1", entranceId: "E-001", capturedAt: "2026-09-02T12:00:00Z",
            sidecarURL: dir.appendingPathComponent("cap-1.json"),
            imageURL: image, depthURL: depth,
            imageSHA256: CaptureWriter.sha256(imageBytes),
            depthSHA256: CaptureWriter.sha256(depthBytes))
    }

    private func ok(_ sha: String) -> Data {
        reply(["stored": true, "sha256": sha, "verified": "read-back"])
    }

    func testACaptureWithDepthUploadsBothParts() async throws {
        let capture = try captureWithDepth()
        StubProtocol.seen = []
        StubProtocol.script = [
            (201, ok(capture.imageSHA256)),
            (201, ok(capture.depthSHA256!)),
        ]
        let result = await stubbedUploader().upload(capture)
        XCTAssertTrue(isSuccess(result))
        XCTAssertEqual(StubProtocol.seen, ["image", "depth"], "image first, then depth")
    }

    func testACaptureIsNotStoredWhenOnlyItsImageLands() async throws {
        // CaptureQueue.remove deletes the depth map too, so a success here with depth unsent
        // destroys the only copy of it.
        let capture = try captureWithDepth()
        StubProtocol.seen = []
        StubProtocol.script = [(201, ok(capture.imageSHA256)), (503, Data())]
        let result = await stubbedUploader().upload(capture)
        XCTAssertFalse(isSuccess(result))
        XCTAssertEqual(StubProtocol.seen, ["image", "depth"])
    }

    func testDepthIsNotSentWhenTheImageIsRefused() async throws {
        let capture = try captureWithDepth()
        StubProtocol.seen = []
        StubProtocol.script = [(422, Data())]
        let result = await stubbedUploader().upload(capture)
        XCTAssertFalse(isSuccess(result))
        XCTAssertEqual(StubProtocol.seen, ["image"], "a refused image must not be followed by depth")
    }

    func testDepthIsSentWithTheHashFromTheSidecarNotTheFileOnDisk() async throws {
        // The file is corrupted after the sidecar was written. Sending a hash computed from disk
        // would make the claim true by construction and the server would confirm the corruption.
        let capture = try captureWithDepth()
        try Data("corrupted".utf8).write(to: capture.depthURL!)
        StubProtocol.seen = []
        StubProtocol.script = [(201, ok(capture.imageSHA256)), (201, ok(capture.depthSHA256!))]
        _ = await stubbedUploader().upload(capture)
        // The recorded hash is what travels; the server is what rejects the mismatch (422 there).
        XCTAssertEqual(capture.depthSHA256, CaptureWriter.sha256(Data("depth".utf8)))
    }

    func testACaptureWhoseSidecarRecordsDepthWithNoHashIsRefused() async throws {
        var capture = try captureWithDepth()
        capture.depthSHA256 = nil
        StubProtocol.script = [(201, ok(capture.imageSHA256))]
        let result = await stubbedUploader().upload(capture)
        XCTAssertFalse(isSuccess(result))
    }

    func testAnImageOnlyCaptureSendsOnePart() async throws {
        let image = dir.appendingPathComponent("cap-2.jpg")
        let bytes = Data("jpg".utf8)
        try bytes.write(to: image)
        let capture = CaptureQueue.Pending(
            captureId: "cap-2", entranceId: "E-001", capturedAt: "2026-09-02T12:00:00Z",
            sidecarURL: dir.appendingPathComponent("cap-2.json"),
            imageURL: image, depthURL: nil,
            imageSHA256: CaptureWriter.sha256(bytes), depthSHA256: nil)
        StubProtocol.seen = []
        StubProtocol.script = [(201, ok(capture.imageSHA256))]
        let result = await stubbedUploader().upload(capture)
        XCTAssertTrue(isSuccess(result))
        XCTAssertEqual(StubProtocol.seen, ["image"])
    }
}
