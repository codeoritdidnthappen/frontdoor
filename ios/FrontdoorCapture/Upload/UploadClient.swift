import Foundation

/// Sends one pending file to `POST /upload` (TICK-029, #33).
///
/// Bytes go phone -> server -> bucket. No R2 credential ships inside this app: a free-provisioning
/// build sits on several phones, and the images token can also READ sealed captures
/// (`data/STORAGE.md`), so a token in the binary would widen the seal's exposure to anyone holding
/// a build. The only secret here is the upload key, which grants ingest and nothing else.
struct UploadClient {

    enum Outcome: Equatable {
        /// Stored and confirmed. The local copy may be discarded (AC5).
        case stored(verified: String)
        /// The server refused this file and will refuse it again. Retrying is pointless.
        case rejected(String)
        /// Transient. The file stays queued and is retried.
        case retry(String)
    }

    var baseURL: URL
    var uploadKey: String
    var session: URLSession

    init(baseURL: URL, uploadKey: String, session: URLSession? = nil) {
        self.baseURL = baseURL
        self.uploadKey = uploadKey
        self.session = session ?? Self.fieldSession()
    }

    /// A session tuned for a storefront pavement rather than a desk.
    ///
    /// `.shared` gives a 60-second request timeout, which a multi-megabyte capture on a weak link
    /// will exceed every single time — the upload would classify as retryable and never once
    /// complete, no matter how many drains ran. The resource timeout is what a whole transfer is
    /// allowed; `waitsForConnectivity` lets a drain that starts a moment too early wait rather
    /// than fail.
    static func fieldSession() -> URLSession {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 120
        config.timeoutIntervalForResource = 600
        config.waitsForConnectivity = true
        return URLSession(configuration: config)
    }

    static let boundary = "frontdoor-upload-boundary"

    static func prologue(for item: UploadQueue.Pending) -> Data {
        var out = Data()
        func field(_ name: String, _ value: String) {
            out.append("--\(boundary)\r\n".data(using: .utf8)!)
            out.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n"
                .data(using: .utf8)!)
            out.append("\(value)\r\n".data(using: .utf8)!)
        }
        // Exact spellings, uncoerced: the server rejects padded or upper-cased values rather than
        // normalising them. No split is sent at all — the server derives it from entrance_id.
        field("kind", item.kind.rawValue)
        field("capture_id", item.captureId)
        field("entrance_id", item.entranceId)
        field("sha256", item.sha256)

        out.append("--\(boundary)\r\n".data(using: .utf8)!)
        out.append("Content-Disposition: form-data; name=\"bytes\"; filename=\"\(item.fileURL.lastPathComponent)\"\r\n"
            .data(using: .utf8)!)
        out.append("Content-Type: application/octet-stream\r\n\r\n".data(using: .utf8)!)
        return out
    }

    static func epilogue() -> Data {
        "\r\n--\(boundary)--\r\n".data(using: .utf8)!
    }

    /// Build the multipart body in memory. Used by the tests and by nothing else.
    static func body(for item: UploadQueue.Pending, bytes: Data) -> Data {
        prologue(for: item) + bytes + epilogue()
    }

    /// Assemble the multipart body into a temporary FILE, streaming the capture through in chunks.
    ///
    /// `httpBody` would hold the whole capture plus a second full copy of it in memory, on a phone
    /// that may be carrying a day of them. Writing to disk and handing `URLSession` the file keeps
    /// peak memory at one chunk.
    static func spool(_ item: UploadQueue.Pending) throws -> URL {
        let url = URL.temporaryDirectory
            .appendingPathComponent("upload-\(UUID().uuidString).multipart")
        FileManager.default.createFile(atPath: url.path, contents: nil)
        let out = try FileHandle(forWritingTo: url)
        defer { try? out.close() }
        try out.write(contentsOf: prologue(for: item))
        let input = try FileHandle(forReadingFrom: item.fileURL)
        defer { try? input.close() }
        while let chunk = try input.read(upToCount: 1024 * 1024), !chunk.isEmpty {
            try out.write(contentsOf: chunk)
        }
        try out.write(contentsOf: epilogue())
        return url
    }

    func request(for item: UploadQueue.Pending) -> URLRequest {
        var request = URLRequest(url: baseURL.appendingPathComponent("upload"))
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(Self.boundary)",
                         forHTTPHeaderField: "Content-Type")
        request.setValue(uploadKey, forHTTPHeaderField: "X-Frontdoor-Upload-Key")
        return request
    }

    /// The in-memory form, kept for tests.
    func request(for item: UploadQueue.Pending, bytes: Data) -> URLRequest {
        var request = self.request(for: item)
        request.httpBody = Self.body(for: item, bytes: bytes)
        return request
    }

    /// Decide what a response means. Pure, so every branch is testable.
    ///
    /// The split between `rejected` and `retry` is the one that matters in the field: this app may
    /// hold the only copy of a capture, so anything that might succeed later must stay queued. A
    /// 5xx, a timeout and a lost connection are all retries; only a refusal the server will repeat
    /// is terminal.
    static func outcome(status: Int, body: Data, expecting item: UploadQueue.Pending) -> Outcome {
        switch status {
        case 200, 201:
            guard let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
                  let stored = json["stored"] as? Bool, stored,
                  let echoed = json["sha256"] as? String else {
                return .retry("the server accepted the upload but its reply could not be read")
            }
            // The server hashed what it received; this checks it hashed OUR file. Without it a
            // mixed-up response would let the app delete a capture that was never stored.
            guard echoed == item.sha256 else {
                return .retry("the server confirmed a different digest than this file's")
            }
            return .stored(verified: (json["verified"] as? String) ?? "received")
        case 401:
            return .rejected("the upload key was refused")
        case 422:
            // The bytes on disk do not hash to what the sidecar says. Retrying re-sends the same
            // bytes and fails the same way, so this needs a person.
            return .rejected("the server found this file does not match its recorded hash")
        case 409:
            return .rejected("a different capture is already stored under this id; it was not overwritten")
        case 408, 429:
            // The two 4xx that genuinely mean "try again".
            return .retry("the server asked us to try again (\(status))")
        case 400...499:
            // Everything else in this range is a request this build will keep getting wrong: a 404
            // from a mistyped host, a 413 from an oversized capture, a 415 from a bad content type.
            // Retrying forever would leave the operator staring at a count that never moves with
            // nothing saying why, so it becomes a visible refusal instead.
            return .rejected("the server rejected this upload (\(status))")
        default:
            return .retry("the server answered \(status)")
        }
    }

    /// Upload one file. Returns `.retry` on any transport error, so nothing is deleted on a guess.
    func send(_ item: UploadQueue.Pending) async -> Outcome {
        let spooled: URL
        do {
            spooled = try Self.spool(item)
        } catch {
            return .retry("the file could not be prepared for upload: \(error.localizedDescription)")
        }
        defer { try? FileManager.default.removeItem(at: spooled) }
        do {
            let (data, response) = try await session.upload(
                for: request(for: item), fromFile: spooled)
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            return Self.outcome(status: status, body: data, expecting: item)
        } catch {
            return .retry(error.localizedDescription)
        }
    }
}
