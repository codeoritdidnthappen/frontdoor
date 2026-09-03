import XCTest
@testable import FrontdoorCapture

/// The per-entrance photo count (#4 AC5, D-021 as amended).
///
/// The count exists because neither of the obvious sources survives a capture day: the queue is
/// emptied by a successful upload, and `EntranceStore` is in memory only. Both of those are
/// asserted here, because a tally that quietly resets is worse than no tally -- it reads as
/// authoritative while telling an operator an entrance is covered.
final class EntranceTallyTests: XCTestCase {

    private var directory: URL!
    private var tally: EntranceTally!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("tally-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        tally = EntranceTally(url: directory.appendingPathComponent("entrance-tally.json"))
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    func testAnEntranceNobodyHasShotCountsZero() {
        XCTAssertEqual(tally.count(for: "E-014"), 0)
    }

    func testEachCaptureAddsOneAndTheIncrementReportsTheNewTotal() {
        XCTAssertEqual(tally.increment("E-014"), 1)
        XCTAssertEqual(tally.increment("E-014"), 2)
        XCTAssertEqual(tally.increment("E-014"), 3)
        XCTAssertEqual(tally.count(for: "E-014"), 3)
    }

    func testEntrancesAreCountedSeparately() {
        tally.increment("E-014")
        tally.increment("E-014")
        tally.increment("E-015")
        XCTAssertEqual(tally.count(for: "E-014"), 2)
        XCTAssertEqual(tally.count(for: "E-015"), 1)
    }

    /// The reason this is a file rather than a property on the store.
    func testTheCountSurvivesTheAppBeingKilled() {
        tally.increment("E-014")
        tally.increment("E-014")

        // A new instance over the same URL is what a relaunch looks like: no shared memory,
        // nothing carried over but the bytes on disk.
        let afterRelaunch = EntranceTally(url: tally.url)
        XCTAssertEqual(afterRelaunch.count(for: "E-014"), 2)
    }

    /// The reason it is not derived from the capture directory.
    ///
    /// `CaptureQueue.remove` deletes a capture once it is safely uploaded, so an entrance shot in
    /// signal would count zero while the same entrance shot in a dead spot counted six. The tally
    /// is deliberately independent of what is still on the phone.
    func testDrainingTheQueueDoesNotChangeTheCount() throws {
        let captures = directory.appendingPathComponent("captures")
        try FileManager.default.createDirectory(at: captures, withIntermediateDirectories: true)
        let queue = CaptureQueue(directory: captures)

        tally.increment("E-014")
        tally.increment("E-014")
        XCTAssertEqual(queue.count, 0, "nothing was written; the tally is not reading the disk")
        XCTAssertEqual(tally.count(for: "E-014"), 2)
    }

    /// A tally file that a previous version wrote, or that got truncated, must not take the app
    /// down at the door -- it is a convenience, and the captures it counts are already on disk.
    func testUnreadableTallyReadsAsZeroRatherThanFailing() throws {
        try Data("not json".utf8).write(to: tally.url)
        XCTAssertEqual(tally.count(for: "E-014"), 0)
        XCTAssertEqual(tally.increment("E-014"), 1, "a corrupt file is replaced, not honoured")
    }
}
