import XCTest
@testable import FrontdoorCapture

final class LabelQueueTests: XCTestCase {
    private var url: URL!
    private var queue: LabelQueue!
    private let answers = Dictionary(uniqueKeysWithValues: ScreeningCriterion.allCases.map {
        ($0, LabelTruth.present)
    })

    override func setUpWithError() throws {
        url = URL.temporaryDirectory.appendingPathComponent("labels-\(UUID().uuidString).json")
        queue = LabelQueue(url: url)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: url)
    }

    private func record(_ queue: LabelQueue? = nil) throws -> EntranceLabelRecord? {
        guard case .success(let record) = (queue ?? self.queue).record(for: "E-901") else {
            throw LabelQueue.Failure.unreadable
        }
        return record
    }

    func testAC6SaveIsAtomicDurableAndCarriesNoServerDate() throws {
        guard case .success = queue.save(
            entranceId: "E-901", labeledBy: " James ", answers: answers)
        else { return XCTFail("save failed") }
        let reloaded = try XCTUnwrap(record(LabelQueue(url: url)))
        XCTAssertEqual(reloaded.labeledBy, "James")
        XCTAssertEqual(reloaded.answers.count, 4)
        XCTAssertNil(String(data: try Data(contentsOf: url), encoding: .utf8)?
            .range(of: "labeled_at"))
    }

    func testAC3EveryRowMustBeExplicitlySelected() throws {
        var incomplete = answers
        incomplete.removeValue(forKey: .handrails)
        guard case .failure(.incomplete) = queue.save(
            entranceId: "E-901", labeledBy: "James", answers: incomplete)
        else { return XCTFail("incomplete labels were saved") }
        XCTAssertNil(try record())
    }

    func testAC5OperatorMustMatchTheServerBound() {
        guard case .failure(.invalidOperator) = queue.save(
            entranceId: "E-901", labeledBy: String(repeating: "x", count: 101),
            answers: answers)
        else { return XCTFail("oversized operator was queued") }
    }

    func testAC7QueuedLabelsCanBeEditedAndAcceptedLabelsAreLocked() throws {
        _ = queue.save(entranceId: "E-901", labeledBy: "James", answers: answers)
        var changed = answers
        changed[.handrails] = .absent
        guard case .success(let uploaded) = queue.save(
            entranceId: "E-901", labeledBy: "James", answers: changed)
        else { return XCTFail("queued edit failed") }
        XCTAssertEqual(try record()?.answers["handrails"], "absent")
        guard case .success(true) = queue.markAccepted(uploaded) else {
            return XCTFail("could not mark accepted")
        }
        guard case .failure(.locked) = queue.save(
            entranceId: "E-901", labeledBy: "James", answers: answers)
        else { return XCTFail("accepted label changed") }
        XCTAssertEqual(try record(LabelQueue(url: url))?.state, .accepted)
    }

    func testAC7QueueSurvivesRestartAndExposesPendingRecords() {
        _ = queue.save(entranceId: "E-901", labeledBy: "James", answers: answers)
        guard case .success(let pending) = LabelQueue(url: url).pending() else {
            return XCTFail("queue unreadable after restart")
        }
        XCTAssertEqual(pending.map(\.entranceId), ["E-901"])
    }

    func testAC10ConflictIsNamedAndNeverRetried() throws {
        guard case .success(let uploaded) = queue.save(
            entranceId: "E-901", labeledBy: "James", answers: answers)
        else { return XCTFail("save failed") }
        _ = queue.markConflict(uploaded, detail: "different accepted labels")
        guard case .success(let pending) = queue.pending() else {
            return XCTFail("queue unreadable")
        }
        XCTAssertEqual(pending.count, 0)
        XCTAssertEqual(try record()?.state, .conflict)
        XCTAssertEqual(try record()?.failure, "different accepted labels")
    }

    func testAC7CorruptQueueIsAnErrorNotAnEmptyQueueAndIsNotChanged() throws {
        let corrupt = Data("not json".utf8)
        try corrupt.write(to: url)
        guard case .failure(.unreadable) = queue.pending() else {
            return XCTFail("corrupt queue was presented as empty")
        }
        XCTAssertEqual(try Data(contentsOf: url), corrupt)
    }

    func testAC4ModelReleaseRunsOnlyAfterDurableSave() {
        var released = false
        let failed = LabelQueue(url: url) { _, _ in throw LabelQueue.Failure.unreadable }
        let failure = LabelCompletionGate(queue: failed).save(
            entranceId: "E-901", labeledBy: "James", answers: answers
        ) { _ in released = true }
        guard case .failure = failure else { return XCTFail("failed write reported success") }
        XCTAssertFalse(released)

        let success = LabelCompletionGate(queue: queue).save(
            entranceId: "E-901", labeledBy: "James", answers: answers
        ) { _ in released = true }
        guard case .success = success else { return XCTFail("durable save failed") }
        XCTAssertTrue(released)
    }
}

final class EntranceLabelDraftTests: XCTestCase {
    func testAC2And3RowsStartUnselectedAndOneSelectionPerRowCompletesTheDraft() {
        var draft = EntranceLabelDraft()
        XCTAssertTrue(draft.answers.isEmpty)
        XCTAssertFalse(draft.canSave(operatorName: "James"))
        for criterion in ScreeningCriterion.allCases {
            draft.select(.present, for: criterion)
        }
        draft.select(.absent, for: .handrails)
        XCTAssertEqual(draft.answers.count, 4)
        XCTAssertEqual(draft.answers[.handrails], .absent)
        XCTAssertTrue(draft.canSave(operatorName: "James"))
    }

    func testAC1FinishRoutingRequiresScreeningAndAllSixViews() {
        let five = ViewSetCoverage(captured: Set(ViewSlot.allCases.dropLast()))
        let six = ViewSetCoverage(captured: Set(ViewSlot.allCases))
        XCTAssertNil(CaptureFinishDecision.destination(
            mode: .screening, coverage: five, entranceId: "E-901"))
        XCTAssertNil(CaptureFinishDecision.destination(
            mode: .metrology, coverage: six, entranceId: "E-901"))
        XCTAssertEqual(CaptureFinishDecision.destination(
            mode: .screening, coverage: six, entranceId: "E-901"), "E-901")
    }
}

final class LabelOperatorStoreTests: XCTestCase {
    func testAC5NameIsTrimmedAndPersistsAcrossStoreInstances() {
        let suite = "label-operator-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let first = LabelOperatorStore(defaults: defaults)
        first.name = "  James  "
        XCTAssertEqual(LabelOperatorStore(defaults: defaults).name, "James")
    }
}
