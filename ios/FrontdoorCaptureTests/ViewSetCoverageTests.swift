import XCTest
@testable import FrontdoorCapture

/// The view set the protocol prescribes, and what the app makes of partial coverage (#289).
final class ViewSetCoverageTests: XCTestCase {

    private var url: URL!
    private var store: EntranceCoverage!

    override func setUpWithError() throws {
        url = URL.temporaryDirectory.appendingPathComponent("\(UUID().uuidString).json")
        store = EntranceCoverage(url: url)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: url)
    }

    private func coverage(_ slots: [ViewSlot]) -> ViewSetCoverage {
        ViewSetCoverage(captured: Set(slots))
    }

    // MARK: - what coverage means

    func testAnEmptyEntranceIsMissingTheWholeSet() {
        let state = coverage([]).state
        guard case .incomplete(let missing) = state else { return XCTFail("\(state)") }
        XCTAssertEqual(missing, ViewSlot.allCases)
    }

    func testFiveOfSixIsReportedAsOneShortAndNamesWhich() {
        let state = coverage(ViewSlot.allCases.filter { $0 != .hardware }).state
        XCTAssertEqual(state, .oneShort(.hardware))
    }

    func testFiveIsNotSilentlyTreatedAsDone() {
        // TICK-282 opens Finish capture and labeling only for the complete six-view set.
        XCTAssertNotEqual(coverage(ViewSlot.allCases.filter { $0 != .far }).state, .complete)
    }

    func testTheFullSetIsComplete() {
        XCTAssertEqual(coverage(ViewSlot.allCases).state, .complete)
    }

    func testAC1FinishGateRequiresEveryNamedView() {
        XCTAssertFalse(coverage(ViewSlot.allCases.filter { $0 != .hardware }).isComplete)
        XCTAssertTrue(coverage(ViewSlot.allCases).isComplete)
    }

    func testTheSummarySaysWhatIsMissingRatherThanACount() {
        XCTAssertEqual(coverage([.headOn]).summary, "1 of 6 · next Oblique, left")
        XCTAssertEqual(
            coverage(ViewSlot.allCases.filter { $0 != .near }).summary,
            "5 of 6 · missing Near, ~1.5 m")
        XCTAssertEqual(coverage(ViewSlot.allCases).summary, "all 6 views")
    }

    func testTheSuggestionIsTheFirstMissingView() {
        XCTAssertEqual(coverage([.headOn, .obliqueLeft]).suggested, .obliqueRight)
    }

    func testACoveredSetStillSuggestsSomething() {
        // An extra angle is a capture the protocol allows, so there is always something to offer.
        XCTAssertEqual(coverage(ViewSlot.allCases).suggested, .headOn)
    }

    // MARK: - the store

    func testAViewIsRememberedAcrossReads() {
        store.record(.far, for: "E-014")
        XCTAssertEqual(EntranceCoverage(url: url).coverage(for: "E-014").captured, [.far])
    }

    func testTheSameViewTwiceCoversItOnce() {
        store.record(.far, for: "E-014")
        let after = store.record(.far, for: "E-014")
        XCTAssertEqual(after.captured, [.far])
    }

    func testEntrancesDoNotShareCoverage() {
        store.record(.far, for: "E-014")
        XCTAssertEqual(store.coverage(for: "E-015").captured, [])
    }

    func testAnUnknownSlotInTheFileIsIgnoredRatherThanRefused() {
        // A build that dropped a view should still show the operator the views it does have.
        try? Data(#"{"E-014": ["far", "aerial"]}"#.utf8).write(to: url)
        XCTAssertEqual(store.coverage(for: "E-014").captured, [.far])
    }

    func testAnUnreadableFileReadsAsNoCoverage() {
        // Guidance degrades; it never throws. The captures are on disk either way.
        try? Data("not json".utf8).write(to: url)
        XCTAssertEqual(store.coverage(for: "E-014").captured, [])
    }
}
