import XCTest
@testable import FrontdoorCapture

/// A capture always has an entrance and conditions behind it now (TICK-024); these stand in for
/// the ones the operator entered, so the other suites stay about the frame.
let testEntrance = Entrance(
    id: "E-014", riseInches: 0.75, instrument: "digital caliper", split: nil)
let testConditions = ConditionTags(
    distanceM: 2.0, lighting: .overcast, surface: .concrete, occlusion: .none)

/// TICK-024's rules: ground truth binds at the shutter press, so everything a capture needs to be
/// interpretable later has to be right before the viewfinder opens.
final class TruthValidationTests: XCTestCase {

    private func entrance(
        id: String = "E-014", rise: String = "0.75",
        instrument: String = "digital caliper", confirmed: Bool = false
    ) -> Result<Entrance, TruthRejected> {
        TruthValidation.entrance(
            id: id, rise: rise, instrument: instrument, confirmedImplausibleRise: confirmed)
    }

    private func conditions(
        distance: String = "2.0", lighting: Lighting = .overcast,
        surface: Surface = .concrete, occlusion: Occlusion = .none
    ) -> Result<ConditionTags, TruthRejected> {
        TruthValidation.conditions(
            distance: distance, lighting: lighting, surface: surface, occlusion: occlusion)
    }

    private func rejection<T>(_ result: Result<T, TruthRejected>) -> TruthRejected? {
        if case .failure(let error) = result { return error }
        return nil
    }

    // MARK: entrance ID

    /// The app's rule has to be the library's rule. An ID the app accepts and
    /// frontdoor.split.canonical_entrance_id rejects is an entrance that cannot be assigned to a
    /// fold, discovered long after the operator has left the doorway.
    func testEntranceIdIsCanonicalisedTheWayTheSplitModuleDoesIt() throws {
        XCTAssertEqual(try entrance(id: "  e-014  ").get().id, "E-014")
        XCTAssertEqual(TruthValidation.canonicalEntranceId("e-000"), "E-000")
    }

    func testMalformedEntranceIdsAreRefused() {
        for bad in ["", "E-14", "E-0141", "014", "X-014", "E-01A", "E014"] {
            XCTAssertNotNil(rejection(entrance(id: bad)), "\(bad) should be refused")
        }
    }

    /// Full-width digits are not ASCII, and a split keyed on them would not match the same
    /// entrance typed normally.
    func testNonAsciiDigitsAreRefused() {
        XCTAssertNotNil(rejection(entrance(id: "E-\u{FF10}\u{FF11}\u{FF14}")))
    }

    // MARK: the caliper reading

    func testACaptureCannotBeSavedWithoutACaliperReading() {
        XCTAssertEqual(rejection(entrance(rise: "")), .riseNotANumber(""))
        XCTAssertEqual(rejection(entrance(rise: "about half an inch")),
                       .riseNotANumber("about half an inch"))
    }

    /// Out of range is neither silently accepted nor silently dropped: a 7" step is real, and so
    /// is a slipped decimal point, and only the operator can tell them apart.
    func testAnImplausibleReadingIsGatedBehindConfirmationNotRejected() throws {
        XCTAssertEqual(rejection(entrance(rise: "7.5")), .riseImplausible(7.5))
        XCTAssertEqual(try entrance(rise: "7.5", confirmed: true).get().riseInches, 7.5)
    }

    func testTheEndsOfThePlausibleRangeAreInside() throws {
        XCTAssertEqual(try entrance(rise: "0").get().riseInches, 0)
        XCTAssertEqual(try entrance(rise: "6").get().riseInches, 6)
        XCTAssertEqual(rejection(entrance(rise: "6.01")), .riseImplausible(6.01))
        XCTAssertEqual(rejection(entrance(rise: "-0.5")), .riseImplausible(-0.5))
    }

    /// nan parses as a Double and would reach the sidecar as a number the schema accepts and no
    /// analysis can use.
    func testNonFiniteReadingsAreRefusedOutright() {
        XCTAssertEqual(rejection(entrance(rise: "nan")), .riseNotANumber("nan"))
        XCTAssertEqual(rejection(entrance(rise: "inf")), .riseNotANumber("inf"))
    }

    func testTheInstrumentIsRequiredBecauseTheSchemaRequiresIt() {
        XCTAssertEqual(rejection(entrance(instrument: "   ")), .instrumentMissing)
    }

    // MARK: conditions

    func testDistanceBeyondTheCapIsRefused() {
        XCTAssertEqual(rejection(conditions(distance: "3.01")), .distanceBeyondCap(3.01))
        XCTAssertEqual(rejection(conditions(distance: "5")), .distanceBeyondCap(5))
    }

    /// R-3 caps at 3 m, so 3 m itself is allowed.
    func testTheCapItselfIsAllowed() throws {
        XCTAssertEqual(try conditions(distance: "3.0").get().distanceM, 3.0)
    }

    func testDistanceMustBePositive() {
        XCTAssertEqual(rejection(conditions(distance: "0")), .distanceNotPositive(0))
        XCTAssertEqual(rejection(conditions(distance: "-1")), .distanceNotPositive(-1))
        XCTAssertEqual(rejection(conditions(distance: "close")), .distanceNotANumber("close"))
    }

    /// The tags are the stratification variables the error budget is reported against. Their
    /// spellings reach the sidecar, so they are the schema's business, not display strings.
    func testTagVocabulariesAreTheSpellingsTheSidecarCarries() {
        XCTAssertEqual(Lighting.directSun.rawValue, "direct_sun")
        XCTAssertEqual(Surface.concrete.rawValue, "concrete")
        XCTAssertEqual(Occlusion.none.rawValue, "none")
        XCTAssertTrue(Lighting.allCases.allSatisfy { !$0.rawValue.isEmpty })
        XCTAssertTrue(Surface.allCases.allSatisfy { !$0.rawValue.isEmpty })
        XCTAssertTrue(Occlusion.allCases.allSatisfy { !$0.rawValue.isEmpty })
    }

    // MARK: re-entry

    @MainActor
    func testReenteringAnIdReusesItsReadingAndSplitUnchanged() throws {
        let store = EntranceStore()
        let first = try store.resolve(
            id: "E-014", rise: "0.75", instrument: "digital caliper").get()

        // Second visit, a different reading typed. The recorded one wins.
        let second = try store.resolve(
            id: "e-014", rise: "1.50", instrument: "tape measure").get()

        XCTAssertEqual(second, first)
        XCTAssertEqual(second.riseInches, 0.75)
        XCTAssertEqual(second.instrument, "digital caliper")
        XCTAssertEqual(store.entrances.count, 1, "re-entry must not create a second entrance")
    }

    @MainActor
    func testDifferentEntrancesAreKeptApart() throws {
        let store = EntranceStore()
        _ = try store.resolve(id: "E-014", rise: "0.75", instrument: "c").get()
        _ = try store.resolve(id: "E-015", rise: "1.25", instrument: "c").get()
        XCTAssertEqual(store.entrances.count, 2)
        XCTAssertEqual(store.existing(id: "E-015")?.riseInches, 1.25)
    }

    @MainActor
    func testARefusedEntranceIsNotRecorded() {
        let store = EntranceStore()
        _ = store.resolve(id: "E-14", rise: "0.75", instrument: "c")
        XCTAssertTrue(store.entrances.isEmpty)
    }

    // MARK: the field that must not exist

    /// Angle is derived from the recovered plane pose (TICK-044). A typed angle would turn the
    /// error-versus-angle curve into a plot of what operators guessed, and afterwards the guess
    /// would be indistinguishable from a measurement.
    func testThereIsNoAngleField() throws {
        let source = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("FrontdoorCapture/Truth/Entrance.swift"),
            encoding: .utf8)
        let code = source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
        XCTAssertFalse(code.lowercased().contains("angle"),
                       "angle is derived, never entered")
    }
}
