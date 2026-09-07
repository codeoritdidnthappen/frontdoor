import SwiftUI
import UIKit
import XCTest
@testable import FrontdoorCapture

/// Renders the screens a simulator cannot reach, so somebody can look at them.
///
/// Seven of the twelve screens sit behind a camera. A simulator has none, so the whole result
/// half of the app -- the screening verdicts, the measurement, the ROI marking, the review gate --
/// had never been seen by anyone when this was written, while every screen that *had* been looked
/// at turned out to have something wrong with it.
///
/// This is a rendering harness, not an assertion suite. It writes PNGs to
/// `FRONTDOOR_RENDER_DIR` (default: the test bundle's temporary directory, printed on the way
/// out) at the default text size and at the largest accessibility size, which is where the
/// defects found by hand all lived. What it cannot do is tell you they are wrong -- that still
/// takes eyes.
@MainActor
final class ScreenRenderTests: XCTestCase {

    private var outputDirectory: URL!

    override func setUpWithError() throws {
        let configured = ProcessInfo.processInfo.environment["FRONTDOOR_RENDER_DIR"]
        outputDirectory = URL(fileURLWithPath: configured ?? NSTemporaryDirectory())
            .appendingPathComponent("frontdoor-screens", isDirectory: true)
        try FileManager.default.createDirectory(
            at: outputDirectory, withIntermediateDirectories: true)
    }

    override func tearDown() {
        print("RENDERED SCREENS -> \(outputDirectory.path)")
    }

    /// iPhone 17 Pro in points. Fixed rather than read from a device so the images are
    /// comparable between runs and between machines.
    private static let size = CGSize(width: 402, height: 874)

    /// Hosted in a real window rather than passed to `ImageRenderer`.
    ///
    /// `ImageRenderer` cannot draw a `NavigationStack` -- it returns SwiftUI's unrenderable
    /// placeholder, a red bar on yellow, which is what the first version of this file produced
    /// for every screen that has one. Nine of the twelve do. A `UIHostingController` in a visible
    /// window is the same hierarchy UIKit would lay out on the device, so the title bar, the
    /// toolbar and the safe area are all real.
    private func write<V: View>(_ view: V, _ name: String, _ size: DynamicTypeSize) {
        let host = view
            .environment(\.dynamicTypeSize, size)
            .background(EntryMapPalette.ground)

        let controller = UIHostingController(rootView: host)
        let bounds = CGRect(origin: .zero, size: Self.size)
        let window = UIWindow(frame: bounds)
        window.rootViewController = controller
        window.makeKeyAndVisible()
        controller.view.frame = bounds
        controller.view.setNeedsLayout()
        controller.view.layoutIfNeeded()
        // One turn of the run loop, or a screen whose content arrives in `task`/`onAppear`
        // photographs itself empty.
        RunLoop.current.run(until: Date().addingTimeInterval(0.35))

        let renderer = UIGraphicsImageRenderer(bounds: bounds)
        let image = renderer.image { _ in
            controller.view.drawHierarchy(in: bounds, afterScreenUpdates: true)
        }
        guard let data = image.pngData() else {
            return XCTFail("\(name) produced no image")
        }
        let suffix = size == .large ? "default" : "ax5"
        let url = outputDirectory.appendingPathComponent("\(name)-\(suffix).png")
        XCTAssertNoThrow(try data.write(to: url), "could not write \(url.lastPathComponent)")
    }

    /// Both ends of the range that matters: the size everything is designed at, and the one that
    /// broke the readiness rows and the mode picker on the screens that were reachable.
    private func writeBoth<V: View>(_ view: V, _ name: String) {
        write(view, name, .large)
        write(view, name, .accessibility5)
    }

    // MARK: Fixtures

    private func screeningResponse(
        quarantined: Bool = false, criteria: String? = nil
    ) throws -> ScreeningResponse {
        let criteria = criteria ?? Self.fourVerdicts
        let json = """
        {
          "entrance_id": "E-014",
          "assessment": { "criteria": \(criteria) },
          "wording": "Screened from one photograph. This is a screening, not an inspection, \
        and it does not establish compliance with the 2010 ADA Standards.",
          "status": "ok", "model": "claude-opus", "latency_ms": 2140,
          "faces_blurred": 2, "face_check": "clear",
          "quarantined": \(quarantined),
          "quarantine_reason": \(quarantined ? "\"face_visible\"" : "null")
        }
        """
        return try JSONDecoder().decode(ScreeningResponse.self, from: Data(json.utf8))
    }

    /// The four keys this build knows (`ScreeningCriterion`), plus one it does not.
    ///
    /// The unknown key is deliberate: a server that starts assessing a fifth thing should show it
    /// on the phone the same day, and the only way to see that path is to send one.
    private static let fourVerdicts = """
    {
      "ramp_or_bevel":            {"verdict": "present", "confidence": "high",
        "evidence": "The threshold is flush with the footway across the full door width."},
      "handrails":                {"verdict": "absent", "confidence": "medium",
        "evidence": "No rail on either side of the approach."},
      "accessible_door_hardware": {"verdict": "not_visible", "confidence": "low",
        "evidence": "The handle is behind the reflection in the glass."},
      "accessibility_signage":    {"verdict": "present", "confidence": "high"},
      "handrail_status":          {"verdict": "unheard_of", "confidence": "low"}
    }
    """

    private func swatch(_ colour: UIColor, _ size: CGSize) -> UIImage {
        UIGraphicsImageRenderer(size: size).image { context in
            colour.setFill()
            context.fill(CGRect(origin: .zero, size: size))
        }
    }

    // MARK: The screens no one has seen

    func testRenderScreeningChecks() throws {
        let assessed = ScreeningRun(
            entranceId: "E-014", startedAt: Date(timeIntervalSince1970: 1_757_000_000),
            outcome: .assessed(try screeningResponse()))
        writeBoth(ScreeningChecksView(run: assessed) {}, "screening-checks")

        let quarantined = ScreeningRun(
            entranceId: "E-014", startedAt: Date(timeIntervalSince1970: 1_757_000_000),
            outcome: .assessed(try screeningResponse(quarantined: true)))
        writeBoth(ScreeningChecksView(run: quarantined) {}, "screening-checks-quarantined")

        let inFlight = ScreeningRun(
            entranceId: "E-014", startedAt: Date(timeIntervalSince1970: 1_757_000_000),
            outcome: .inFlight)
        writeBoth(ScreeningChecksView(run: inFlight) {}, "screening-checks-inflight")

        let failed = ScreeningRun(
            entranceId: "E-014", startedAt: Date(timeIntervalSince1970: 1_757_000_000),
            outcome: .failed("The screening service did not answer in time. "
                             + "The photo is saved and queued for upload."))
        writeBoth(ScreeningChecksView(run: failed) {}, "screening-checks-failed")
    }

    func testRenderResult() throws {
        let json = """
        {
          "arms": {
            "A": { "rise_in": 0.11, "interval_in": {"low": 0.09, "high": 0.13},
                   "decisions": {"half_inch": {"verdict": "pass"},
                                 "quarter_inch": {"verdict": "pass"}} },
            "A_prime": { "rise_in": 0.55, "interval_in": {"low": 0.40, "high": 0.70},
              "decisions": {"half_inch": {"verdict": "abstain",
                "explanation": "The 0.40-0.70 in interval straddles the 1/2 in line, so this \
        capture cannot be classified against it either way."},
                "quarter_inch": {"verdict": "fail"}} }
          },
          "stub": true,
          "capture_id": "E-014-20260906-103320"
        }
        """
        let response = try JSONDecoder().decode(MeasureResponse.self, from: Data(json.utf8))
        writeBoth(ResultView(response: response, caliperInches: 0.50) {}, "result")
    }

    func testRenderReviewGate() {
        let photo = swatch(.systemGray3, CGSize(width: 1200, height: 1600))
        writeBoth(ScreeningReviewView(image: photo, entranceId: "E-014",
                                      onPublish: {}, onDiscard: {}), "review-gate")
    }

    /// The metrology tap screen, and the only one with light type on a dark chrome.
    ///
    /// Rendered because its footer controls were changed to fix a contrast failure that was
    /// computed, not seen: the quiet role's label is `subduedInk`, which is 1.78:1 on this
    /// chrome. The arithmetic said unreadable and the fix went in blind. This is the picture.
    ///
    /// The marks are left unplaced, so this is the first prompt an operator meets. The nudge pad
    /// only appears once a point exists, which is why the footer here is the confirm row alone.
    func testRenderROIReview() {
        let doorway = swatch(.darkGray, CGSize(width: 3024, height: 4032))
        writeBoth(
            ROIReviewView(image: doorway, pixelWidth: 3024, pixelHeight: 4032,
                          onConfirm: { _ in }, onDiscard: {}),
            "roi-review")
    }

    func testRenderConditionsSheet() {
        let sheet = ConditionsSheet(
            mode: .screening,
            current: ConditionTags(distanceM: 2.0, lighting: .overcast,
                                   surface: nil, occlusion: .none, cardPlacement: nil),
            onSave: { _ in }, onCancel: {})
        writeBoth(sheet, "conditions-sheet")
    }

    func testRenderPrimerAndDiagnostics() {
        writeBoth(ScanPrimerView(continueTitle: "Start") {}, "scan-primer")
        writeBoth(DiagnosticsView {}, "diagnostics")
    }
}
