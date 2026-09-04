import XCTest
@testable import FrontdoorCapture

/// The named checks render `POST /screen`'s reply (#275), so these decode the shape the server
/// actually sends and pin the places where a lenient reader would quietly invent something.
final class ScreeningResponseTests: XCTestCase {

    private func decode(_ json: String) throws -> ScreeningResponse {
        try JSONDecoder().decode(ScreeningResponse.self, from: Data(json.utf8))
    }

    private func envelope(criteria: String) -> String {
        """
        {"entrance_id": "acme-main", "mode": "integrated",
         "images": [{"filename": "a.jpg"}],
         "assessment": {"criteria": \(criteria), "latency_ms": 12100, "error": null},
         "latency_ms": 12400, "faces_blurred": 0, "face_check": "clear",
         "quarantined": false, "model": "claude-opus-5", "status": "ai_estimated",
         "wording": "Screening statements about accessibility features visible in the submitted photos."}
        """
    }

    private let fourCriteria = """
    {"ramp_or_bevel": {"verdict": "not_visible", "confidence": 62, "evidence": "Dark threshold strip"},
     "handrails": {"verdict": "not_visible", "confidence": 70, "evidence": "No steps in frame"},
     "accessible_door_hardware": {"verdict": "present", "confidence": 93, "evidence": "Lever handle"},
     "accessibility_signage": {"verdict": "absent", "confidence": 68, "evidence": "No ISA sign"}}
    """

    // MARK: - decoding what the server sends

    func testARealReplyDecodes() throws {
        let response = try decode(envelope(criteria: fourCriteria))
        XCTAssertEqual(response.entranceId, "acme-main")
        XCTAssertEqual(response.assessment.criteria?.count, 4)
        XCTAssertEqual(response.assessment.criteria?["accessible_door_hardware"]?.verdict, "present")
        XCTAssertEqual(response.assessment.criteria?["accessible_door_hardware"]?.confidence, "93")
        XCTAssertFalse(response.quarantined)
        XCTAssertEqual(response.faceCheck, "clear")
    }

    func testAnEmptyConfidenceIsAbsentRatherThanZero() throws {
        // The server passes the model's own value through and sends "" when it omitted one.
        // Rendering that as 0 would put a confidence nobody stated on the screen.
        let response = try decode(envelope(criteria: """
        {"handrails": {"verdict": "absent", "confidence": "", "evidence": "x"}}
        """))
        XCTAssertNil(response.assessment.criteria?["handrails"]?.confidence)
    }

    func testAnUnrecognisedVerdictSurvivesDecoding() throws {
        // Kept as text so the screen can show it verbatim. Mapped onto a known verdict it would
        // read as a finding the model never made.
        let response = try decode(envelope(criteria: """
        {"handrails": {"verdict": "probably", "confidence": 10, "evidence": "x"}}
        """))
        XCTAssertEqual(response.assessment.criteria?["handrails"]?.verdict, "probably")
    }

    func testAQuarantineIsCarriedWithItsReason() throws {
        let json = envelope(criteria: fourCriteria)
            .replacingOccurrences(of: "\"quarantined\": false", with:
                "\"quarantined\": true, \"quarantine_reason\": \"face_check\"")
            .replacingOccurrences(of: "\"face_check\": \"clear\"", with: "\"face_check\": \"unknown\"")
        let response = try decode(json)
        XCTAssertTrue(response.quarantined)
        XCTAssertEqual(response.quarantineReason, "face_check")
        // "never answered" is a different fact from "checked and clear", and both quarantine.
        XCTAssertEqual(response.faceCheck, "unknown")
    }

    // MARK: - what the run exposes to the screen

    private func run(_ criteria: String) throws -> ScreeningRun {
        ScreeningRun(entranceId: "acme-main", startedAt: Date(),
                     outcome: .assessed(try decode(envelope(criteria: criteria))))
    }

    func testACriterionTheServerDidNotAnswerIsNil() throws {
        // Distinct from `absent`: the screen says "no verdict", not "not present".
        let subject = try run(#"{"handrails": {"verdict": "absent", "confidence": 1, "evidence": "x"}}"#)
        XCTAssertNil(subject.criterion("ramp_or_bevel"))
    }

    func testACriterionThisBuildHasNoLabelForIsStillListed() throws {
        let subject = try run("""
        {"handrails": {"verdict": "absent", "confidence": 1, "evidence": "x"},
         "door_width": {"verdict": "present", "confidence": 50, "evidence": "y"}}
        """)
        XCTAssertEqual(subject.unrecognisedCriterionKeys, ["door_width"])
    }

    func testNothingIsListedWhileTheAnswerIsStillInFlight() {
        let subject = ScreeningRun(entranceId: "acme-main", startedAt: Date(), outcome: .inFlight)
        XCTAssertNil(subject.criterion("handrails"))
        XCTAssertEqual(subject.unrecognisedCriterionKeys, [])
    }

    // MARK: - the request and the error contract

    func testTheRequestCarriesTheEntranceIdAndTheImage() {
        let body = ScreenClient.body(
            image: Data("JPEGBYTES".utf8), entranceId: "acme-main",
            boundary: "B", filename: "a.jpg")
        let text = String(decoding: body, as: UTF8.self)
        XCTAssertTrue(text.contains("name=\"entrance_id\"\r\n\r\nacme-main"))
        XCTAssertTrue(text.contains("name=\"image\"; filename=\"a.jpg\""))
        XCTAssertTrue(text.contains("Content-Type: image/jpeg"))
        XCTAssertTrue(text.hasSuffix("--B--\r\n"))
    }

    func testTheRequestOmitsTheFieldWhenThereIsNoEntranceId() {
        // An empty entrance_id is not the same as none: the server validates the field when it is
        // present, so sending a blank one would turn a capture into a 400.
        let body = ScreenClient.body(
            image: Data("x".utf8), entranceId: nil, boundary: "B", filename: "a.jpg")
        XCTAssertFalse(String(decoding: body, as: UTF8.self).contains("entrance_id"))
    }

    func testASealedEntranceIsExplainedAsAPolicyNotAFault() {
        let failure = ScreenClient.failure(
            status: 403,
            data: Data(#"{"error": "sealed entrance", "detail": "entrance x is sealed"}"#.utf8))
        XCTAssertTrue(failure.message.contains("sealed split"))
        XCTAssertTrue(failure.message.contains("saved and queued"))
    }

    func testAKeylessServerSaysSoRatherThanBlamingThePhoto() {
        let failure = ScreenClient.failure(
            status: 503,
            data: Data(#"{"error": "screening unavailable", "detail": "no key"}"#.utf8))
        XCTAssertTrue(failure.message.contains("no screening key"))
    }

    func testAnUnparseableBodyStillProducesASentence() {
        // TICK-064: a captive portal answers with HTML where JSON was expected, and the operator
        // must still get something actionable rather than a parse failure on stage.
        let failure = ScreenClient.failure(status: 502, data: Data("<html>nope</html>".utf8))
        XCTAssertTrue(failure.message.contains("no readable explanation"))
        XCTAssertTrue(failure.message.contains("saved and queued"))
    }
}
