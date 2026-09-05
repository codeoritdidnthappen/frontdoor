import Foundation

/// Durable, editable-until-accepted human labels for future captures (TICK-282).
struct LabelQueue {
    enum Failure: LocalizedError, Equatable {
        case unreadable
        case incomplete
        case invalidOperator
        case locked

        var errorDescription: String? {
            switch self {
            case .unreadable: return "The saved label queue could not be read. Nothing was changed."
            case .incomplete: return "Choose one answer for every criterion before saving."
            case .invalidOperator: return "Enter a name between 1 and 100 characters."
            case .locked: return "These labels were already accepted by the server and are locked."
            }
        }
    }

    typealias Writer = (Data, URL) throws -> Void

    var url: URL
    private var writer: Writer

    init(url: URL, writer: @escaping Writer = LabelQueue.atomicWrite) {
        self.url = url
        self.writer = writer
    }

    static func inDocuments() -> LabelQueue {
        LabelQueue(url: URL.documentsDirectory.appendingPathComponent("entrance-labels.json"))
    }

    func record(for entranceId: String) -> Result<EntranceLabelRecord?, Failure> {
        do { return .success(try load()[entranceId]) }
        catch { return .failure(.unreadable) }
    }

    func pending() -> Result<[EntranceLabelRecord], Failure> {
        do {
            return .success(try load().values.filter { $0.state == .queued }.sorted {
                $0.entranceId < $1.entranceId
            })
        } catch {
            return .failure(.unreadable)
        }
    }

    @discardableResult
    func save(
        entranceId: String,
        labeledBy: String,
        answers: [ScreeningCriterion: LabelTruth]
    ) -> Result<EntranceLabelRecord, Failure> {
        guard answers.count == ScreeningCriterion.allCases.count,
              ScreeningCriterion.allCases.allSatisfy({ answers[$0] != nil })
        else { return .failure(.incomplete) }
        let operatorName = labeledBy.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !operatorName.isEmpty, operatorName.count <= 100 else {
            return .failure(.invalidOperator)
        }
        do {
            var stored = try load()
            if let current = stored[entranceId], current.state != .queued {
                return .failure(.locked)
            }
            let record = EntranceLabelRecord(
                entranceId: entranceId,
                labeledBy: operatorName,
                answers: Dictionary(uniqueKeysWithValues: ScreeningCriterion.allCases.map {
                    ($0.rawValue, answers[$0]!.rawValue)
                }),
                state: .queued,
                failure: nil)
            stored[entranceId] = record
            try write(stored)
            return .success(record)
        } catch {
            return .failure(.unreadable)
        }
    }

    /// Apply a response only if the record still equals the exact snapshot that was uploaded.
    /// A newer edit remains queued and will be sent on the next drain.
    func markAccepted(_ uploaded: EntranceLabelRecord) -> Result<Bool, Failure> {
        update(uploaded, state: .accepted, failure: nil)
    }

    func markConflict(
        _ uploaded: EntranceLabelRecord, detail: String
    ) -> Result<Bool, Failure> {
        update(uploaded, state: .conflict, failure: detail)
    }

    private func update(
        _ uploaded: EntranceLabelRecord,
        state: EntranceLabelState,
        failure: String?
    ) -> Result<Bool, Failure> {
        do {
            var stored = try load()
            guard var current = stored[uploaded.entranceId] else {
                return .failure(.unreadable)
            }
            guard current == uploaded else { return .success(false) }
            current.state = state
            current.failure = failure
            stored[uploaded.entranceId] = current
            try write(stored)
            return .success(true)
        } catch {
            return .failure(.unreadable)
        }
    }

    private func load() throws -> [String: EntranceLabelRecord] {
        guard FileManager.default.fileExists(atPath: url.path) else { return [:] }
        return try JSONDecoder().decode(
            [String: EntranceLabelRecord].self,
            from: Data(contentsOf: url))
    }

    private func write(_ records: [String: EntranceLabelRecord]) throws {
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try writer(try JSONEncoder().encode(records), url)
    }

    private static func atomicWrite(_ data: Data, to url: URL) throws {
        try data.write(
            to: url,
            options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }
}

/// Makes the ordering executable: model release happens only after the atomic queue write passes.
struct LabelCompletionGate {
    var queue: LabelQueue

    func save(
        entranceId: String,
        labeledBy: String,
        answers: [ScreeningCriterion: LabelTruth],
        afterDurableSave: (EntranceLabelRecord) -> Void
    ) -> Result<Void, LabelQueue.Failure> {
        switch queue.save(entranceId: entranceId, labeledBy: labeledBy, answers: answers) {
        case .failure(let failure):
            return .failure(failure)
        case .success(let record):
            afterDurableSave(record)
            return .success(())
        }
    }
}
