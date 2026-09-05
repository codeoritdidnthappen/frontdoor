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

    // MARK: - photo ADA screening (#318)

    private let mixedAda = """
    {"score_percent": 75.0, "determined_count": 4, "total_count": 8,
     "true_count": 3, "false_count": 1, "cannot_determine_count": 2, "not_applicable_count": 2,
     "checks": {
       "entrance_route": {"result": "true", "evidence": "Clear approach."},
       "threshold": {"result": "false", "evidence": "Raised transition."},
       "ramp": {"result": "not_applicable", "evidence": "Level approach."},
       "door_hardware": {"result": "true", "evidence": "Lever hardware."},
       "door_opening": {"result": "cannot_determine", "evidence": "Width not measurable."},
       "handrails": {"result": "not_applicable", "evidence": "No ramp or stairs."},
       "signage": {"result": "cannot_determine", "evidence": "Location not fully visible."},
       "temporary_barriers": {"result": "true", "evidence": "No obstruction."}
     },
     "summary": "Three of four determined photo checks were supported. A potential barrier was observed for threshold. Four checks could not be determined or were not applicable.",
     "standards_url": "https://www.ada.gov/law-and-regs/design-standards/2010-stds/",
     "disclaimer": "Photo-based screening only. This is not an ADA compliance or legal determination."}
    """

    private let zeroDeterminedAda = """
    {"score_percent": null, "determined_count": 0, "total_count": 8,
     "true_count": 0, "false_count": 0, "cannot_determine_count": 8, "not_applicable_count": 0,
     "checks": {
       "entrance_route": {"result": "cannot_determine", "evidence": "Not visible."},
       "threshold": {"result": "cannot_determine", "evidence": "Not visible."},
       "ramp": {"result": "cannot_determine", "evidence": "Not visible."},
       "door_hardware": {"result": "cannot_determine", "evidence": "Not visible."},
       "door_opening": {"result": "cannot_determine", "evidence": "Not visible."},
       "handrails": {"result": "cannot_determine", "evidence": "Not visible."},
       "signage": {"result": "cannot_determine", "evidence": "Not visible."},
       "temporary_barriers": {"result": "cannot_determine", "evidence": "Not visible."}
     },
     "summary": "No photo checks were determined. Eight checks could not be determined or were not applicable.",
     "standards_url": "https://www.ada.gov/law-and-regs/design-standards/2010-stds/",
     "disclaimer": "Photo-based screening only. This is not an ADA compliance or legal determination."}
    """

    private func envelopeWithAda(_ ada: String) -> String {
        let json = envelope(criteria: fourCriteria)
        return String(json.dropLast()) + ", \"ada_screening\": \(ada)}"
    }

    func testAMixedAdaScreeningDecodesForTheResultScreen() throws {
        let response = try decode(envelopeWithAda(mixedAda))
        let ada = try XCTUnwrap(response.adaScreening)
        XCTAssertEqual(ada.scorePercent, 75.0)
        XCTAssertEqual(ada.determinedCount, 4)
        XCTAssertEqual(ada.totalCount, 8)
        XCTAssertEqual(ada.checks["threshold"]?.result, "false")
        XCTAssertTrue(ada.summary.contains("potential barrier"))
        XCTAssertFalse(ada.summary.lowercased().contains("compliant"))
        XCTAssertEqual(AdaScreeningCheck.allCases.map(\.rawValue), [
            "entrance_route", "threshold", "ramp", "door_hardware",
            "door_opening", "handrails", "signage", "temporary_barriers",
        ])
        let rendered = ada.renderModel
        XCTAssertEqual(rendered.score, "75.0%")
        XCTAssertEqual(rendered.coverage, "4 of 8 checks determined")
        XCTAssertEqual(rendered.rows.map(\.id), AdaScreeningCheck.allCases.map(\.rawValue))
        let threshold = try XCTUnwrap(rendered.rows.first { $0.id == "threshold" })
        XCTAssertEqual(threshold.label, "Threshold")
        XCTAssertEqual(threshold.result, "Potential barrier")
        XCTAssertEqual(threshold.evidence, "Raised transition.")
        XCTAssertEqual(rendered.summary, ada.summary)
        XCTAssertEqual(rendered.disclaimer, ada.disclaimer)
        XCTAssertEqual(rendered.standardsURL?.host, "www.ada.gov")
    }

    func testAZeroDeterminedAdaScreeningHasNoPercentage() throws {
        let response = try decode(envelopeWithAda(zeroDeterminedAda))
        let ada = try XCTUnwrap(response.adaScreening)
        XCTAssertNil(ada.scorePercent)
        XCTAssertEqual(ada.determinedCount, 0)
        XCTAssertTrue(ada.summary.contains("No photo checks were determined"))
        XCTAssertFalse(ada.disclaimer.lowercased().contains("compliant"))
        let rendered = ada.renderModel
        XCTAssertEqual(rendered.score, "Not enough visible evidence")
        XCTAssertEqual(rendered.coverage, "0 of 8 checks determined")
        XCTAssertEqual(rendered.rows.count, 8)
        XCTAssertTrue(rendered.rows.allSatisfy { $0.result == "Cannot determine" })
        XCTAssertTrue(rendered.rows.allSatisfy { !($0.evidence ?? "").isEmpty })
        XCTAssertEqual(rendered.summary, ada.summary)
        XCTAssertEqual(rendered.disclaimer, ada.disclaimer)
        XCTAssertEqual(rendered.standardsURL?.host, "www.ada.gov")
    }

    func testAnOlderReplyWithoutAdaScreeningStillDecodes() throws {
        let response = try decode(envelope(criteria: fourCriteria))
        XCTAssertNil(response.adaScreening)
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

    private func view(_ name: String) -> ScreenClient.View {
        ScreenClient.View(data: Data("JPEG-\(name)".utf8), filename: name)
    }

    func testTheRequestCarriesTheEntranceIdAndTheImage() {
        let body = ScreenClient.body(
            views: [view("a.jpg")], entranceId: "acme-main", boundary: "B")
        let text = String(decoding: body, as: UTF8.self)
        XCTAssertTrue(text.contains("name=\"entrance_id\"\r\n\r\nacme-main"))
        XCTAssertTrue(text.contains("name=\"image\"; filename=\"a.jpg\""))
        XCTAssertTrue(text.contains("Content-Type: image/jpeg"))
        XCTAssertTrue(text.hasSuffix("--B--\r\n"))
    }

    func testTheRequestOmitsTheFieldWhenThereIsNoEntranceId() {
        // An empty entrance_id is not the same as none: the server validates the field when it is
        // present, so sending a blank one would turn a capture into a 400.
        let body = ScreenClient.body(views: [view("a.jpg")], entranceId: nil, boundary: "B")
        XCTAssertFalse(String(decoding: body, as: UTF8.self).contains("entrance_id"))
    }

    // MARK: - the whole view set goes in one request (#316)

    func testEveryViewIsSentAsItsOwnImagePart() {
        // /screen collects every file part and makes ONE integrated call across them. Sending
        // only the last frame -- a hardware close-up -- answers not_visible for ramp/bevel and
        // handrails, because that photo cannot see the ground plane.
        let names = ["head_on.jpg", "oblique_left.jpg", "far.jpg", "hardware.jpg"]
        let body = ScreenClient.body(
            views: names.map(view), entranceId: "E-101", boundary: "B")
        let text = String(decoding: body, as: UTF8.self)
        for name in names {
            XCTAssertTrue(text.contains("filename=\"\(name)\""), name)
        }
        XCTAssertEqual(text.components(separatedBy: "name=\"image\"").count - 1, names.count)
        XCTAssertEqual(text.components(separatedBy: "name=\"entrance_id\"").count - 1, 1)
        XCTAssertTrue(text.hasSuffix("--B--\r\n"))
    }

    func testTheBoundaryIsClosedExactlyOnce() {
        let body = ScreenClient.body(
            views: [view("a.jpg"), view("b.jpg")], entranceId: nil, boundary: "B")
        let text = String(decoding: body, as: UTF8.self)
        XCTAssertEqual(text.components(separatedBy: "--B--").count - 1, 1)
    }

    func testSendingNothingIsRefusedLocallyAndSaysTheCapturesAreSafe() async {
        // Every view already uploaded and deleted by the drain. Nothing was lost, and the
        // operator should be told that rather than shown a parse error.
        let client = ScreenClient(baseURL: URL(string: "https://example.invalid")!)
        let outcome = await client.screen(views: [], entranceId: "E-101")
        guard case .failure(let failure) = outcome else { return XCTFail("expected a refusal") }
        XCTAssertEqual(failure, .noViewsToSend)
        XCTAssertTrue(failure.message.contains("captures are safe"))
    }

    func testMoreViewsThanTheEndpointTakesIsRefusedHereNotThere() async {
        // Refused before the bytes go over a venue network, not by a 400 afterwards.
        let client = ScreenClient(baseURL: URL(string: "https://example.invalid")!)
        let views = (0...ScreenClient.maxViews).map { view("v\($0).jpg") }
        let outcome = await client.screen(views: views, entranceId: "E-101")
        guard case .failure(let failure) = outcome else { return XCTFail("expected a refusal") }
        XCTAssertEqual(failure, .tooManyViews(ScreenClient.maxViews + 1))
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
