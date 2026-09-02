import XCTest
@testable import FrontdoorCapture

/// TICK-063 renders whatever TICK-060 froze, so these decode the committed contract rather than
/// whatever the stub happens to send today.
final class MeasureResponseTests: XCTestCase {

    private func decode(_ json: String) throws -> MeasureResponse {
        try JSONDecoder().decode(MeasureResponse.self, from: Data(json.utf8))
    }

    private let measuredArm = """
    {"rise_in": 0.11, "interval_in": {"low": 0.06, "high": 0.16},
     "decisions": {"half_inch": {"verdict": "pass"},
                   "quarter_inch": {"verdict": "pass"}}}
    """

    private func envelope(a: String, others: String = #"{"absent_reason": "unavailable"}"#,
                          stub: Bool = true) -> String {
        """
        {"stub": \(stub), "capture_id": "abc",
         "arms": {"A": \(a), "A_prime": \(others), "B": \(others), "C": \(others)}}
        """
    }

    func testAMeasuredArmDecodes() throws {
        let response = try decode(envelope(a: measuredArm))
        guard case .measured(let m)? = response.arms[.a] else {
            return XCTFail("Arm A should be a measurement")
        }
        XCTAssertEqual(m.riseIn, 0.11, accuracy: 0.0001)
        XCTAssertEqual(m.intervalIn.low, 0.06, accuracy: 0.0001)
        XCTAssertEqual(m.decisions.halfInch.verdict, .pass)
    }

    /// Abstain is a first-class outcome (D-009), not a null measurement or a missing decision.
    /// rise_in is still present when a decision abstains -- the number exists, the verdict does not.
    func testAnAbstainingArmKeepsItsMeasurementAndExplanation() throws {
        let abstaining = """
        {"rise_in": 0.55, "interval_in": {"low": 0.40, "high": 0.70},
         "decisions": {"half_inch": {"verdict": "abstain",
                                     "explanation": "The 0.40-0.70 in interval straddles the 1/2 in line."},
                       "quarter_inch": {"verdict": "fail"}}}
        """
        let response = try decode(envelope(a: abstaining))
        guard case .measured(let m)? = response.arms[.a] else { return XCTFail("expected a measurement") }
        XCTAssertEqual(m.decisions.halfInch.verdict, .abstain)
        XCTAssertEqual(m.riseIn, 0.55, accuracy: 0.0001, "an abstention still carries its rise")
        XCTAssertFalse(m.decisions.halfInch.explanation?.isEmpty ?? true,
                       "an abstention without a reason is a blank, which AC3 forbids")
    }

    /// Three different absences, and the operator has to be able to tell them apart: cut is
    /// expected, failed is about this capture, unavailable is about this deployment.
    func testEachAbsenceReasonDecodesAndReadsDifferently() throws {
        for reason in ["cut", "failed", "unavailable"] {
            let response = try decode(envelope(a: #"{"absent_reason": "\#(reason)"}"#))
            guard case .absent(let absence)? = response.arms[.a] else {
                return XCTFail("\(reason) should decode as an absence")
            }
            XCTAssertEqual(absence.absentReason.rawValue, reason)
            XCTAssertFalse(absence.absentReason.headline.isEmpty)
            XCTAssertFalse(absence.absentReason.plain.isEmpty)
        }
        XCTAssertEqual(
            Set(["cut", "failed", "unavailable"].map {
                Arm.Absence.Reason(rawValue: $0)!.headline
            }).count, 3, "the three reasons must not read identically")
    }

    /// The schema says clients must surface it. A placeholder rendered like a measurement is the
    /// worst thing this app could put on a projector.
    func testTheStubFlagIsCarriedThrough() throws {
        XCTAssertTrue(try decode(envelope(a: measuredArm, stub: true)).stub)
        XCTAssertFalse(try decode(envelope(a: measuredArm, stub: false)).stub)
    }

    func testAllFourArmsAreDecoded() throws {
        let response = try decode(envelope(a: measuredArm))
        XCTAssertEqual(Set(response.arms.keys), Set(ArmName.allCases))
    }

    /// Only Arm A carries a pass/fail bar (D-022, Amendment A-2), so the app must not draw a
    /// verdict against the others.
    func testOnlyArmACarriesTheBar() {
        XCTAssertTrue(ArmName.a.carriesTheBar)
        for other in ArmName.allCases where other != .a {
            XCTAssertFalse(other.carriesTheBar, other.label)
        }
    }

    // MARK: the request

    func testTheMultipartBodyCarriesBothParts() {
        let body = MeasureClient.body(
            sidecar: Data(#"{"capture_id":"abc"}"#.utf8), image: Data("jpeg".utf8),
            boundary: "B", filename: "abc.jpg")
        let text = String(decoding: body, as: UTF8.self)
        XCTAssertTrue(text.contains(#"name="sidecar""#))
        XCTAssertTrue(text.contains(#"name="image"; filename="abc.jpg""#))
        XCTAssertTrue(text.contains(#"{"capture_id":"abc"}"#))
        XCTAssertTrue(text.hasSuffix("--B--\r\n"))
    }

    /// AC4: a failed measurement never costs a dataset record, and the message has to say so.
    func testEveryFailureSaysTheCaptureIsSafe() {
        let failures: [MeasureClient.Failure] = [
            .noServerConfigured,
            .unreachable("timed out"),
            .rejected(status: 422, error: .sidecarInvalid, detail: "'gravity' is required."),
            .unreadable("bad JSON"),
        ]
        for failure in failures {
            XCTAssertTrue(failure.message.lowercased().contains("saved"),
                          "\(failure) must tell the operator the capture is not lost: \(failure.message)")
        }
    }

    // MARK: against what the server actually sends

    /// Hand-written JSON only proves the client can read what I imagined. This is the real
    /// response, captured from the Flask app and committed; the Python suite regenerates and
    /// re-checks it, so the two cannot drift into agreeing with themselves.
    func testTheClientDecodesTheServersActualResponse() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("tests/fixtures/measure_response.json")
        let response = try JSONDecoder().decode(
            MeasureResponse.self, from: Data(contentsOf: url))

        XCTAssertEqual(Set(response.arms.keys), Set(ArmName.allCases))
        XCTAssertTrue(response.stub, "the endpoint is still a stub; the client must surface that")
        guard case .measured? = response.arms[.a] else {
            return XCTFail("Arm A should carry a measurement in the current stub")
        }
    }

    // MARK: the error contract, against what the server actually returns

    private struct ErrorCase: Decodable {
        let status: Int
        let body: Body
        struct Body: Decodable {
            let error: String
            let detail: String
            let field: String?
        }
    }

    private func errorCases() throws -> [String: ErrorCase] {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("tests/fixtures/measure_errors.json")
        return try JSONDecoder().decode([String: ErrorCase].self, from: Data(contentsOf: url))
    }

    /// Every error the endpoint can produce, captured from it rather than imagined.
    ///
    /// The first version of this client read a `message` key the contract has never had --
    /// `measure_error.schema.json` is error/detail/field with additionalProperties false -- so every
    /// 4xx and 5xx rendered "no explanation given". Hand-written JSON could not catch that, because
    /// I wrote the fixture and the parser from the same wrong assumption.
    func testEveryRealServerErrorMapsToAToken() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("tests/fixtures/measure_errors.json")
        let raw = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]

        for (name, case_) in try errorCases() {
            // Through the client's own parser, over the server's own bytes. Asserting against a
            // re-implementation here is what let the `message` bug live.
            let body = try JSONSerialization.data(
                withJSONObject: (raw[name] as! [String: Any])["body"]!)
            let failure = MeasureClient.failure(status: case_.status, data: body)
            guard case .rejected(let status, let token, let detail) = failure else {
                return XCTFail("\(name) should be a rejection")
            }
            XCTAssertEqual(status, case_.status, name)
            XCTAssertEqual(token?.rawValue, case_.body.error, "unmapped token for \(name)")
            XCTAssertEqual(detail, case_.body.detail, name)
            XCTAssertTrue(failure.message.contains(case_.body.error), failure.message)
        }
    }

    /// The distinction TICK-224 built the token for: a malformed sidecar is a property of the
    /// capture, so retrying it forever is how a queue silently stops draining.
    func testAMalformedSidecarIsNotWorthRetryingButAnInternalErrorIs() {
        XCTAssertFalse(MeasureClient.ServerError.sidecarInvalid.isWorthRetrying)
        XCTAssertFalse(MeasureClient.ServerError.missingImage.isWorthRetrying)
        XCTAssertTrue(MeasureClient.ServerError.internalError.isWorthRetrying)
    }

    /// A proxy or captive portal answering HTML must still produce a sentence, not a crash.
    func testAnUnreadableErrorBodyStillProducesAnActionableMessage() {
        let failure = MeasureClient.Failure.rejected(
            status: 502, error: nil, detail: "the server gave no readable explanation.")
        XCTAssertTrue(failure.message.contains("saved"))
        XCTAssertFalse(failure.message.contains("no explanation given"))
    }

    func testTheRejectionMessageNamesTheTokenAndSaysWhetherToRetry() {
        let failure = MeasureClient.Failure.rejected(
            status: 422, error: .sidecarInvalid, detail: "'gravity' is a required property.")
        XCTAssertTrue(failure.message.contains("sidecar failed validation"), failure.message)
        XCTAssertTrue(failure.message.contains("re-taking"), failure.message)
        XCTAssertTrue(failure.message.contains("saved"), failure.message)
    }
}
