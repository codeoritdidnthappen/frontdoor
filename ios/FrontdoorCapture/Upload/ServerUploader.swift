import Foundation

/// The destination `CaptureUploader` was left open for (TICK-029, #33).
///
/// Bytes go phone -> server -> bucket, never phone -> bucket. The seam's own note gives the
/// reason and it still holds: the app cannot hold the R2 credentials. `data/STORAGE.md` scopes the
/// images key to the loader and server, and that key can also READ sealed captures, so a copy
/// inside a free-provisioning build would widen the seal's exposure to anyone holding the build.
/// What travels in the app instead is an ingest key, which grants `POST /upload` and nothing else:
/// it cannot read any bucket. The server holds read+write on images and, per D-039, forwards depth
/// to the isolated ingest Worker without holding an R2 depth credential.
///
/// The contract this promises is the one `CaptureUploader` asks for: success means the bytes are
/// stored AND their hash was checked at the far end, not that a request returned 200.
struct ServerUploader: CaptureUploader {

    struct Refusal: LocalizedError {
        var reason: String
        var errorDescription: String? { reason }
    }

    /// A refusal that belongs to one capture: the server will answer the same way however many
    /// times it is sent, and the captures behind it are fine. Separate type rather than a flag on
    /// `Refusal` so the drain cannot skip something by accident -- a new failure has to be
    /// deliberately declared per-capture to get that treatment.
    struct PermanentRefusal: LocalizedError, PerCaptureUploadFailure {
        var reason: String
        var errorDescription: String? { reason }
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
    /// exceeds every time -- the upload would fail identically on every drain and never once
    /// complete. `timeoutIntervalForResource` is what a whole transfer is allowed;
    /// `waitsForConnectivity` lets a drain that starts a moment too early wait rather than fail.
    static func fieldSession() -> URLSession {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 120
        config.timeoutIntervalForResource = 600
        config.waitsForConnectivity = true
        return URLSession(configuration: config)
    }

    /// One capture is its image and, where the device produced one, its depth map.
    ///
    /// Both must land before the capture counts as uploaded, because `CaptureQueue.remove` deletes
    /// both. Reporting success with the depth map still unsent would delete the only copy of it.
    /// The image goes first: if depth fails, the retry re-sends the image, which the server
    /// recognises as the same bytes and accepts idempotently rather than treating as a conflict.
    func upload(_ capture: CaptureQueue.Pending) async -> Result<Void, Error> {
        var parts: [(kind: String, url: URL, sha: String)] = [
            ("image", capture.imageURL, capture.imageSHA256),
        ]
        if let depthURL = capture.depthURL {
            // The hash comes from the sidecar, never from the file on disk. Hashing the bytes we
            // are about to send would make the claim true by construction, and the server would
            // confirm a corrupt depth map as a match -- the exact check AC4 exists to make.
            guard let depthSHA = capture.depthSHA256 else {
                return .failure(Refusal(reason:
                    "\(capture.captureId): its sidecar records a depth map but no hash for it, "
                    + "so the upload cannot be checked. It stays on the phone"))
            }
            parts.append(("depth", depthURL, depthSHA))
        }

        for part in parts {
            if case .failure(let error) = await send(
                capture: capture, kind: part.kind, fileURL: part.url, sha256: part.sha) {
                return .failure(error)
            }
        }
        return .success(())
    }

    // MARK: - one file

    static let boundary = "frontdoor-upload-boundary"

    static func prologue(captureId: String, entranceId: String, kind: String,
                         sha256: String, filename: String) -> Data {
        var out = Data()
        func field(_ name: String, _ value: String) {
            out.append("--\(boundary)\r\n".data(using: .utf8)!)
            out.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n"
                .data(using: .utf8)!)
            out.append("\(value)\r\n".data(using: .utf8)!)
        }
        // No split is sent. The server derives the partition from entrance_id with the committed
        // seed, so a build carrying a drifted seed cannot land a sealed entrance in the open one.
        // Nothing is padded or case-folded either; the server rejects rather than normalising.
        field("kind", kind)
        field("capture_id", captureId)
        field("entrance_id", entranceId)
        field("sha256", sha256)

        out.append("--\(boundary)\r\n".data(using: .utf8)!)
        out.append("Content-Disposition: form-data; name=\"bytes\"; filename=\"\(filename)\"\r\n"
            .data(using: .utf8)!)
        out.append("Content-Type: application/octet-stream\r\n\r\n".data(using: .utf8)!)
        return out
    }

    static func epilogue() -> Data { "\r\n--\(boundary)--\r\n".data(using: .utf8)! }

    /// Assemble the multipart body into a temporary FILE, streaming the capture through in chunks.
    ///
    /// `httpBody` would hold the whole capture plus a second full copy of it in memory, on a phone
    /// that may be carrying a day of them. Handing `URLSession` a file keeps peak memory at one
    /// chunk.
    static func spool(captureId: String, entranceId: String, kind: String,
                      fileURL: URL, sha256: String) throws -> URL {
        let out = URL.temporaryDirectory
            .appendingPathComponent("upload-\(UUID().uuidString).multipart")
        FileManager.default.createFile(atPath: out.path, contents: nil)
        let handle = try FileHandle(forWritingTo: out)
        defer { try? handle.close() }
        try handle.write(contentsOf: prologue(
            captureId: captureId, entranceId: entranceId, kind: kind,
            sha256: sha256, filename: fileURL.lastPathComponent))
        let input = try FileHandle(forReadingFrom: fileURL)
        defer { try? input.close() }
        while let chunk = try input.read(upToCount: 1024 * 1024), !chunk.isEmpty {
            try handle.write(contentsOf: chunk)
        }
        try handle.write(contentsOf: epilogue())
        return out
    }

    /// What a response means. Pure, so every branch is testable without a network.
    ///
    /// The split that matters in the field: this phone may hold the only copy, so anything that
    /// might succeed later has to stay queued. `QueueDrain` stops at the first failure either way,
    /// but the message is what the operator reads, so a permanent refusal has to say so rather
    /// than look like weather.
    static func outcome(status: Int, body: Data, expecting sha256: String) -> Result<Void, Error> {
        func refuse(_ reason: String) -> Result<Void, Error> {
            .failure(Refusal(reason: reason))
        }
        // Refused for a reason that is about THIS capture. Retrying cannot change the answer, and
        // stopping the drain here would strand every capture queued behind it.
        func refusePermanently(_ reason: String) -> Result<Void, Error> {
            .failure(PermanentRefusal(reason: reason))
        }
        switch status {
        // 200 is an idempotent repeat: the earlier upload landed and only its reply was lost.
        case 200, 201:
            guard let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
                  let stored = json["stored"] as? Bool, stored,
                  let echoed = json["sha256"] as? String else {
                return refuse("the server accepted the upload but its reply could not be read")
            }
            // The server hashed what it received; this checks it hashed OUR file. Without it a
            // mixed-up reply would let the queue delete a capture that was never stored.
            guard echoed == sha256 else {
                return refuse("the server confirmed a different file than the one sent")
            }
            return .success(())
        case 401:
            return refuse("the upload key was refused. This build cannot upload until it is fixed")
        case 409:
            return refusePermanently("a different capture is already stored under this id. "
                          + "It was not overwritten, and this one is still on the phone")
        case 422:
            return refusePermanently("the bytes on this phone do not match the hash in the capture's own "
                          + "sidecar. Nothing was stored and nothing will be deleted")
        case 408, 429:
            return refuse("the server asked us to try again (\(status))")
        case 400...499:
            // A wrong host gives 404 and an oversized capture gives 413. Both would repeat on every
            // drain, so the message names the status rather than reading as a transient blip.
            return refusePermanently(
                "the server rejected this upload (\(status)). This will not fix itself")
        case 503:
            // Weather, not a bug. #258 made a misconfigured or still-booting deploy answer 503
            // precisely so the client had something to branch on -- and until now the branch did
            // not exist: 500 and 503 both fell through to `default` and read as
            // "the server answered 503", which tells an operator nothing about whether to wait or
            // to stop for the day.
            return refuse("the server is temporarily unavailable. The capture is still on the "
                          + "phone and the next drain will try again")
        case 500...599:
            // A fault at the far end, which retrying will probably not clear. Still a Refusal
            // rather than a PermanentRefusal: it is a property of the server, not of this
            // capture, so the bytes stay queued -- but the message says it is worth reporting
            // rather than waiting out.
            return refuse("the server failed while storing this capture (\(status)). The capture "
                          + "is still on the phone; this is a fault worth reporting, not weather")
        default:
            return refuse("the server answered \(status)")
        }
    }

    private func send(capture: CaptureQueue.Pending, kind: String,
                      fileURL: URL, sha256: String) async -> Result<Void, Error> {
        let spooled: URL
        do {
            spooled = try Self.spool(
                captureId: capture.captureId, entranceId: capture.entranceId,
                kind: kind, fileURL: fileURL, sha256: sha256)
        } catch {
            return .failure(Refusal(reason:
                "\(capture.captureId): could not be prepared for upload (\(error.localizedDescription))"))
        }
        defer { try? FileManager.default.removeItem(at: spooled) }

        var request = URLRequest(url: baseURL.appendingPathComponent("upload"))
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(Self.boundary)",
                         forHTTPHeaderField: "Content-Type")
        request.setValue(uploadKey, forHTTPHeaderField: "X-Frontdoor-Upload-Key")

        do {
            let (data, response) = try await session.upload(for: request, fromFile: spooled)
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            return Self.outcome(status: status, body: data, expecting: sha256)
        } catch {
            return .failure(Refusal(reason: error.localizedDescription))
        }
    }
}

/// Where the app sends captures, and the secret that lets it.
///
/// Both come from Info.plist via build settings rather than source, so the upload key is not
/// committed -- the same arrangement as `DEVELOPMENT_TEAM`. When either is missing the app keeps
/// `NoDestinationUploader`, which refuses everything: nothing uploads, nothing is deleted, and the
/// count keeps rising where the operator can see it.
struct UploadSettings {
    var serverURL: URL?
    var uploadKey: String?

    static func fromBundle(_ bundle: Bundle = .main) -> UploadSettings {
        func string(_ key: String) -> String? {
            let value = (bundle.object(forInfoDictionaryKey: key) as? String)?
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return (value?.isEmpty ?? true) ? nil : value
        }
        return UploadSettings(
            serverURL: string("FrontdoorServerURL").flatMap(URL.init(string:)),
            uploadKey: string("FrontdoorUploadKey"))
    }

    /// An uploader, or nil when the build has no server or no key.
    func uploader() -> CaptureUploader? {
        guard let serverURL, let uploadKey else { return nil }
        return ServerUploader(baseURL: serverURL, uploadKey: uploadKey)
    }
}
