import XCTest
@testable import FrontdoorCapture

/// The app and the Python tool must assign the same fold to the same entrance (TICK-025).
///
/// Both read `tests/fixtures/split_golden.json`. A disagreement here does not crash anything: the
/// entrance simply sits in one fold on the phone and another in the analysis, and the sealed set
/// stops being sealed without a single error being raised.
final class SplitAssignmentTests: XCTestCase {

    private struct Golden: Decodable {
        struct Vector: Decodable {
            let entrance_id: String
            let split: String
        }
        let sealed_percent: Int
        let calib_percent: Int
        let vectors: [Vector]
    }

    private func golden() throws -> Golden {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // FrontdoorCaptureTests
            .deletingLastPathComponent()   // ios
            .deletingLastPathComponent()   // repo root
            .appendingPathComponent("tests/fixtures/split_golden.json")
        return try JSONDecoder().decode(Golden.self, from: Data(contentsOf: url))
    }

    /// The AC asks for at least 20 shared IDs matching the tool exactly.
    func testEveryGoldenVectorMatchesTheTool() throws {
        let golden = try golden()
        XCTAssertGreaterThanOrEqual(golden.vectors.count, 20)
        for vector in golden.vectors {
            XCTAssertEqual(
                SplitAssignment.split(for: vector.entrance_id)?.rawValue, vector.split,
                "\(vector.entrance_id) must land in \(vector.split)")
        }
        // All three folds represented, or the vectors would pass while testing one branch.
        XCTAssertEqual(Set(golden.vectors.map(\.split)), ["dev", "calib", "sealed"])
    }

    func testTheBucketBoundariesMatchTheTool() throws {
        let golden = try golden()
        XCTAssertEqual(SplitAssignment.sealedPercent, golden.sealed_percent)
        XCTAssertEqual(SplitAssignment.calibPercent, golden.calib_percent)
    }

    /// Assigned once and never re-rolled: the same ID must always give the same answer, and a
    /// non-canonical spelling of it must give that same answer too.
    func testAssignmentIsStableAndCanonicalising() {
        let first = SplitAssignment.split(for: "E-014")
        XCTAssertNotNil(first)
        XCTAssertEqual(SplitAssignment.split(for: "E-014"), first)
        XCTAssertEqual(SplitAssignment.split(for: "  e-014 "), first)
    }

    /// An unassignable ID must not be bucketed. Defaulting would put a real doorway in an
    /// arbitrary fold and nothing would say so.
    func testAMalformedIdIsNotAssignedAFold() {
        for bad in ["", "E-14", "014", "E-01A"] {
            XCTAssertNil(SplitAssignment.split(for: bad), bad)
        }
    }

    /// Re-entering an entrance reuses its recorded split rather than computing a fresh one.
    @MainActor
    func testReenteringAnEntranceKeepsItsOriginalSplit() throws {
        let store = EntranceStore()
        let first = try store.resolve(
            id: "E-014", rise: "0.75", instrument: "digital caliper").get()
        let second = try store.resolve(
            id: "e-014", rise: "2.00", instrument: "tape").get()
        XCTAssertEqual(second.split, first.split)
    }

    func testAnEntranceCarriesTheSplitTheToolWouldGiveIt() throws {
        let entrance = try TruthValidation.entrance(
            id: "E-014", rise: "0.75", instrument: "digital caliper").get()
        XCTAssertEqual(entrance.split, SplitAssignment.split(for: "E-014"))
    }
}
