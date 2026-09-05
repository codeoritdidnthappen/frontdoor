import Foundation

enum LabelUploadOutcome: Equatable {
    case accepted
    case retry(String)
    case conflict(String)
}

protocol EntranceLabelUploader {
    func upload(_ record: EntranceLabelRecord) async -> LabelUploadOutcome
}

struct NoLabelDestinationUploader: EntranceLabelUploader {
    func upload(_ record: EntranceLabelRecord) async -> LabelUploadOutcome {
        .retry("No label destination is configured; the labels remain on this phone.")
    }
}

struct ServerLabelUploader: EntranceLabelUploader {
    var baseURL: URL
    var uploadKey: String
    var session: URLSession

    init(baseURL: URL, uploadKey: String, session: URLSession? = nil) {
        self.baseURL = baseURL
        self.uploadKey = uploadKey
        self.session = session ?? ServerUploader.fieldSession()
    }

    static func outcome(
        status: Int, body: Data, expectedEntranceId: String
    ) -> LabelUploadOutcome {
        if status == 200 || status == 201 {
            guard let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
                  json["accepted"] as? Bool == true,
                  json["entrance_id"] as? String == expectedEntranceId
            else { return .retry("The server accepted labels but its reply could not be verified.") }
            return .accepted
        }
        let detail = (try? JSONSerialization.jsonObject(with: body) as? [String: Any])?["detail"]
            as? String
        if status == 409 {
            return .conflict(detail ?? "The server already locked different labels for this entrance.")
        }
        if status == 401 {
            return .retry("The upload key was refused. Labels remain on this phone.")
        }
        return .retry(detail ?? "The label server answered \(status). Labels remain on this phone.")
    }

    func upload(_ record: EntranceLabelRecord) async -> LabelUploadOutcome {
        var request = URLRequest(url: baseURL.appendingPathComponent("labels"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(uploadKey, forHTTPHeaderField: "X-Frontdoor-Upload-Key")
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: [
                "entrance_id": record.entranceId,
                "labeled_by": record.labeledBy,
                "answers": record.answers,
            ])
            let (data, response) = try await session.data(for: request)
            return Self.outcome(
                status: (response as? HTTPURLResponse)?.statusCode ?? 0,
                body: data,
                expectedEntranceId: record.entranceId)
        } catch {
            return .retry(error.localizedDescription)
        }
    }
}

struct LabelQueueDrain {
    struct Report: Equatable {
        var accepted = 0
        /// Nil means the durable queue could not be read; zero must never make that claim.
        var remaining: Int?
        var message: String?
    }

    var queue: LabelQueue
    var uploader: EntranceLabelUploader

    func drain() async -> Report {
        var report = Report()
        let pending: [EntranceLabelRecord]
        switch queue.pending() {
        case .failure(let failure):
            report.message = failure.localizedDescription
            return report
        case .success(let records):
            pending = records
        }
        for record in pending {
            switch await uploader.upload(record) {
            case .accepted:
                switch queue.markAccepted(record) {
                case .failure(let failure):
                    report.message = failure.localizedDescription
                    report.remaining = pendingCount()
                    return report
                case .success(false):
                    report.message = "Labels changed while uploading; the latest choices remain queued."
                case .success(true):
                    report.accepted += 1
                }
            case .conflict(let detail):
                switch queue.markConflict(record, detail: detail) {
                case .failure(let failure):
                    report.message = failure.localizedDescription
                    report.remaining = pendingCount()
                    return report
                case .success(false):
                    report.message = "Labels changed while uploading; the latest choices remain queued."
                case .success(true):
                    report.message = "\(record.entranceId): \(detail)"
                }
            case .retry(let detail):
                report.message = detail
                report.remaining = pendingCount()
                return report
            }
        }
        report.remaining = pendingCount()
        return report
    }

    private func pendingCount() -> Int? {
        guard case .success(let records) = queue.pending() else { return nil }
        return records.count
    }
}

extension UploadSettings {
    func labelUploader() -> EntranceLabelUploader? {
        guard let serverURL, let uploadKey else { return nil }
        return ServerLabelUploader(baseURL: serverURL, uploadKey: uploadKey)
    }
}
