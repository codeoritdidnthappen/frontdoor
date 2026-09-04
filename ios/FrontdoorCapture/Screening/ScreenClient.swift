import Foundation

/// Sends one photo to `POST /screen` and returns the verdicts that came back (#275).
///
/// The counterpart of `MeasureClient` for the plain-photo protocol: same shape, same error
/// contract, and the same rule — the app renders the server's answer and computes nothing.
struct ScreenClient {

    /// The tokens this endpoint returns. Matched so the operator gets a sentence about the thing
    /// that actually went wrong; an unrecognised token falls through to the server's own detail.
    enum ServerError: String, Decodable, Equatable {
        case missingImage = "missing image"
        case tooManyImages = "too many images"
        case unsupportedContentType = "unsupported content type"
        case invalidEntranceId = "invalid entrance_id"
        case sealedEntrance = "sealed entrance"
        case screeningUnavailable = "screening unavailable"
        case invalidImage = "invalid image"
        case engineFailure = "screening engine failure"
    }

    enum Failure: Error, Equatable {
        case noServerConfigured
        case unreachable(String)
        case rejected(status: Int, error: ServerError?, detail: String)
        case unreadable(String)

        /// Written for someone standing at an entrance. Every message ends by saying where the
        /// photo is, because by the time this runs the capture is already on disk and queued —
        /// a failed screening never costs the operator the shot.
        var message: String {
            switch self {
            case .noServerConfigured:
                return "No screening server is configured, so this photo was saved but not screened."
            case .unreachable(let detail):
                return "The screening server could not be reached (\(detail)). The photo is saved and queued."
            case .rejected(_, let error, let detail):
                switch error {
                case .sealedEntrance:
                    // Not a fault and not worth retrying: the sealed split is evaluated once, at
                    // results freeze, and never through this endpoint (D-007).
                    return "This entrance is in the sealed split, so it is not screened here. "
                        + "The photo is saved and queued."
                case .screeningUnavailable:
                    return "The server has no screening key configured, so it could not assess "
                        + "this photo. The photo is saved and queued."
                default:
                    return "The server could not screen this photo: \(detail) The photo is saved and queued."
                }
            case .unreadable(let detail):
                return "The server's reply could not be read (\(detail)). The photo is saved and queued."
            }
        }
    }

    private struct ServerErrorBody: Decodable {
        let error: ServerError?
        let detail: String?
    }

    var baseURL: URL
    var session: URLSession = .shared

    /// Multipart matching the endpoint: image file parts, plus `entrance_id` as a form field when
    /// there is one. The endpoint takes no sidecar — the plain-photo protocol has nothing to send.
    static func body(image: Data, entranceId: String?, boundary: String, filename: String) -> Data {
        var body = Data()
        func append(_ string: String) { body.append(Data(string.utf8)) }
        if let entranceId {
            append("--\(boundary)\r\n")
            append("Content-Disposition: form-data; name=\"entrance_id\"\r\n\r\n")
            append("\(entranceId)\r\n")
        }
        append("--\(boundary)\r\n")
        append("Content-Disposition: form-data; name=\"image\"; filename=\"\(filename)\"\r\n")
        append("Content-Type: image/jpeg\r\n\r\n")
        body.append(image)
        append("\r\n--\(boundary)--\r\n")
        return body
    }

    func screen(image: Data, entranceId: String?, filename: String) async -> Result<ScreeningResponse, Failure> {
        let boundary = UUID().uuidString
        var request = URLRequest(url: baseURL.appendingPathComponent("screen"))
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.httpBody = Self.body(
            image: image, entranceId: entranceId, boundary: boundary, filename: filename)
        // Longer than /measure's 20 s: this waits on a vision model, and a measured single-view
        // call took 17.3 s on the host. Cutting it off early would report an unreachable server
        // for a request that was about to answer.
        request.timeoutInterval = 45

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
            return .success(try JSONDecoder().decode(ScreeningResponse.self, from: data))
        } catch {
            return .failure(.unreadable(error.localizedDescription))
        }
    }

    /// Decoded leniently, for the same reason `MeasureClient` does it: a captive portal or a proxy
    /// can answer with HTML where JSON was expected, and that must still produce a sentence rather
    /// than a parse failure on stage.
    static func failure(status: Int, data: Data) -> Failure {
        let body = try? JSONDecoder().decode(ServerErrorBody.self, from: data)
        return .rejected(
            status: status,
            error: body?.error,
            detail: body?.detail ?? "the server gave no readable explanation.")
    }
}
