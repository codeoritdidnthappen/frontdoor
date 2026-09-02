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
    var session: URLSession = .shared

    static let boundary = "frontdoor-upload-boundary"

    /// Build the multipart body. Separated from sending so it is testable without a network.
    static func body(for item: UploadQueue.Pending, bytes: Data) -> Data {
        var out = Data()
        func field(_ name: String, _ value: String) {
            out.append("--\(boundary)\r\n".data(using: .utf8)!)
            out.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n"
                .data(using: .utf8)!)
            out.append("\(value)\r\n".data(using: .utf8)!)
        }
        // Exact spellings, uncoerced: the server rejects padded or upper-cased values rather than
        // normalising them, because `split` decides whether a capture is sealed.
        field("kind", item.kind.rawValue)
        field("capture_id", item.captureId)
        field("split", item.split)
        field("sha256", item.sha256)

        out.append("--\(boundary)\r\n".data(using: .utf8)!)
        out.append("Content-Disposition: form-data; name=\"bytes\"; filename=\"\(item.fileURL.lastPathComponent)\"\r\n"
            .data(using: .utf8)!)
        out.append("Content-Type: application/octet-stream\r\n\r\n".data(using: .utf8)!)
        out.append(bytes)
        out.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        return out
    }

    func request(for item: UploadQueue.Pending, bytes: Data) -> URLRequest {
        var request = URLRequest(url: baseURL.appendingPathComponent("upload"))
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(Self.boundary)",
                         forHTTPHeaderField: "Content-Type")
        request.setValue(uploadKey, forHTTPHeaderField: "X-Frontdoor-Upload-Key")
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
        case 201:
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
        case 400:
            return .rejected("the server rejected the request as malformed")
        default:
            return .retry("the server answered \(status)")
        }
    }

    /// Upload one file. Returns `.retry` on any transport error, so nothing is deleted on a guess.
    func send(_ item: UploadQueue.Pending) async -> Outcome {
        guard let bytes = try? Data(contentsOf: item.fileURL) else {
            return .retry("the file could not be read from disk")
        }
        do {
            let (data, response) = try await session.data(for: request(for: item, bytes: bytes))
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            return Self.outcome(status: status, body: data, expecting: item)
        } catch {
            return .retry(error.localizedDescription)
        }
    }
}
