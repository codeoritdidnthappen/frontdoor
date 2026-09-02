import Foundation

/// Sends one capture to `POST /measure` and returns what came back.
///
/// The app computes nothing. It renders the server's answer, because the demo and the error budget
/// must run the same library (R-11) -- a client-side shortcut would be a second measurement path
/// that Demo Day exhibits and the evaluation never characterises.
struct MeasureClient {

    /// The server's error contract, which is `error`/`detail`/`field` and carries no `message`
    /// key. The token is the stable class of failure -- the schema says explicitly that TICK-063
    /// branches on it, not on the wording of `detail` -- and it is what separates a capture worth
    /// retrying from one that never will be.
    enum ServerError: String, Decodable, Equatable {
        case missingImage = "missing image"
        case missingSidecar = "missing sidecar"
        case sidecarNotJSON = "sidecar is not valid JSON"
        case sidecarInvalid = "sidecar failed validation"
        case noSuchEndpoint = "no such endpoint"
        case wrongMethod = "wrong method for this endpoint"
        case bodyTooLarge = "request body too large"
        case unsupportedContentType = "unsupported content type"
        case internalError = "internal error"

        /// Whether sending the same capture again could ever succeed. A malformed sidecar is a
        /// property of the capture, so retrying it forever is how a queue silently stops draining;
        /// an internal error is a property of the moment.
        var isWorthRetrying: Bool {
            switch self {
            case .internalError, .noSuchEndpoint, .wrongMethod:
                return true
            case .missingImage, .missingSidecar, .sidecarNotJSON, .sidecarInvalid,
                 .bodyTooLarge, .unsupportedContentType:
                return false
            }
        }
    }

    enum Failure: Error, Equatable {
        case noServerConfigured
        case unreachable(String)
        case rejected(status: Int, error: ServerError?, detail: String)
        case unreadable(String)

        /// Written for someone holding a phone at an entrance, not for a log.
        var message: String {
            switch self {
            case .noServerConfigured:
                return "No measurement server is configured, so this capture was saved but not measured."
            case .unreachable(let detail):
                return "The measurement server could not be reached (\(detail)). The capture is saved; it can be measured later."
            case .rejected(_, let error, let detail):
                guard let error else {
                    return "The server refused this capture: \(detail) The capture is saved."
                }
                let next = error.isWorthRetrying
                    ? "It is worth sending again."
                    : "Sending it again will not help; this capture needs re-taking."
                return "The server refused this capture — \(error.rawValue): \(detail) \(next) The capture is saved."
            case .unreadable(let detail):
                return "The server's reply could not be read (\(detail)). The capture is saved."
            }
        }
    }

    /// Exactly the shape of `measure_error.schema.json`.
    private struct ServerErrorBody: Decodable {
        let error: ServerError?
        let detail: String?
    }

    var baseURL: URL
    var session: URLSession = .shared

    /// Multipart, matching the endpoint's contract: a `sidecar` form field and an `image` file part.
    static func body(sidecar: Data, image: Data, boundary: String, filename: String) -> Data {
        var body = Data()
        func append(_ string: String) { body.append(Data(string.utf8)) }
        append("--\(boundary)\r\n")
        append("Content-Disposition: form-data; name=\"sidecar\"\r\n\r\n")
        body.append(sidecar)
        append("\r\n--\(boundary)\r\n")
        append("Content-Disposition: form-data; name=\"image\"; filename=\"\(filename)\"\r\n")
        append("Content-Type: image/jpeg\r\n\r\n")
        body.append(image)
        append("\r\n--\(boundary)--\r\n")
        return body
    }

    func measure(sidecar: Data, image: Data, filename: String) async -> Result<MeasureResponse, Failure> {
        let boundary = UUID().uuidString
        var request = URLRequest(url: baseURL.appendingPathComponent("measure"))
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.httpBody = Self.body(
            sidecar: sidecar, image: image, boundary: boundary, filename: filename)
        // A venue network that hangs is worse than one that fails: the operator is standing there.
        request.timeoutInterval = 20

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            return .failure(.unreachable(error.localizedDescription))
        }

        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            return .failure(Self.failure(status: status, data: data))
        }
        do {
            return .success(try JSONDecoder().decode(MeasureResponse.self, from: data))
        } catch {
            return .failure(.unreadable(error.localizedDescription))
        }
    }

    /// Turn a non-2xx body into a Failure. Extracted so it can be tested against real server
    /// bodies -- inline, the parsing had no call site a test could reach, which is how it shipped
    /// reading a key the contract has never had.
    static func failure(status: Int, data: Data) -> Failure {
        // error / detail / field, with additionalProperties false. An earlier version read a
        // `message` key the contract has never had, so every 4xx and 5xx rendered "no explanation
        // given" and the retryable-versus-not distinction was thrown away.
        //
        // Decoded leniently on purpose: TICK-064 exists because a proxy or a captive portal can
        // answer with HTML where JSON was expected, and that must still produce a sentence an
        // operator can act on rather than a parse failure on stage.
        let body = try? JSONDecoder().decode(ServerErrorBody.self, from: data)
        return .rejected(
            status: status,
            error: body?.error,
            detail: body?.detail ?? "the server gave no readable explanation.")
    }
}
