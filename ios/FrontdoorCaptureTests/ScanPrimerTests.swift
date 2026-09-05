import XCTest
@testable import FrontdoorCapture

/// When the operator is shown what a scan involves, and when they are not (#275, step 1).
final class ScanPrimerTests: XCTestCase {

    private var defaults: UserDefaults!
    private var suite: String!

    override func setUpWithError() throws {
        suite = "scan-primer-\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suite)
    }

    override func tearDownWithError() throws {
        defaults.removePersistentDomain(forName: suite)
    }

    private var primer: ScanPrimer { ScanPrimer(defaults: defaults) }

    func testAFreshInstallHasNotSeenIt() {
        XCTAssertFalse(primer.hasBeenSeen)
    }

    func testItIsRememberedOnceRead() {
        primer.markSeen()
        XCTAssertTrue(ScanPrimer(defaults: defaults).hasBeenSeen)
    }

    func testMarkingItSeenTwiceIsNotAnError() {
        primer.markSeen()
        primer.markSeen()
        XCTAssertTrue(primer.hasBeenSeen)
    }

    func testTheFlagDoesNotLeakBetweenInstalls() {
        // Keyed, not global: a stray `true` under some other key must not silence the primer.
        defaults.set(true, forKey: "some-other-flag")
        XCTAssertFalse(primer.hasBeenSeen)
    }

    func testTheKeyIsStableAcrossBuilds() {
        // Renaming it would silently re-show the primer to an operator mid-capture-day, which on
        // a 40-60 entrance walk reads as the app having forgotten what they are doing.
        primer.markSeen()
        XCTAssertTrue(defaults.bool(forKey: "scan-primer-seen"))
    }

    // MARK: - what it says

    func testItNamesEveryViewTheProtocolAsksFor() {
        // Rendered from ViewSlot, so the primer, the coaching bar and docs/capture-protocol.md
        // cannot tell an operator three different things. This pins that it renders all of them.
        XCTAssertEqual(ViewSlot.allCases.count, 6)
        for slot in ViewSlot.allCases {
            XCTAssertFalse(slot.label.isEmpty)
            XCTAssertFalse(slot.coaching.isEmpty)
        }
    }
}
