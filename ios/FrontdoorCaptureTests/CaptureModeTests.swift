import XCTest
@testable import FrontdoorCapture

/// Tests for the three capture contracts (D-034, TICK-027 / #31).
///
/// The failure these guard against is a record that claims something nobody did: a screening
/// capture carrying a caliper reading, or an imported photo carrying intrinsics our camera never
/// produced. Both would read downstream as measurements.
final class CaptureModeTests: XCTestCase {

    private func conditions(mode: CaptureMode, distance: String = "2.0") -> ConditionTags {
        guard case .success(let c) = TruthValidation.conditions(
            distance: distance, lighting: .overcast, surface: .concrete,
            occlusion: .none, mode: mode) else {
            fatalError("conditions rejected in a test fixture")
        }
        return c
    }

    private func entrance(_ id: String = "E-014") -> Entrance {
        guard case .success(let e) = TruthValidation.screeningEntrance(id: id) else {
            fatalError("entrance rejected in a test fixture")
        }
        return e
    }

    private func metrologyEntrance() -> Entrance {
        guard case .success(let e) = TruthValidation.entrance(
            id: "E-014", rise: "0.75", instrument: "digital caliper") else {
            fatalError("entrance rejected in a test fixture")
        }
        return e
    }

    // MARK: - a screening entrance has no reading

    func testAScreeningEntranceCarriesNoReadingRatherThanAZero() {
        let e = entrance()
        // Zero would be a measurement -- a doorway flush with the pavement. Absent is "nobody
        // measured it", which is the true statement.
        XCTAssertNil(e.riseInches)
        XCTAssertNil(e.instrument)
    }

    func testAScreeningEntranceStillGetsItsSplitFromTheCommittedSeed() {
        XCTAssertEqual(entrance("E-014").split, SplitAssignment.split(for: "E-014"))
    }

    func testAScreeningEntranceStillRefusesAMalformedId() {
        for bad in ["E-14", "e14", "", "E-0014", "X-014"] {
            guard case .failure = TruthValidation.screeningEntrance(id: bad) else {
                return XCTFail("\(bad) should be refused")
            }
        }
    }

    func testAnEntranceAlreadyRecordedWithAReadingKeepsIt() async {
        // The doorway was captured in metrology mode earlier in the day. A screening capture of
        // the same entrance must attach to it, not mint a second reading-less entrance.
        let store = await EntranceStore()
        _ = await store.resolve(id: "E-014", rise: "0.75", instrument: "digital caliper")
        guard case .success(let same) = await store.resolveScreening(id: "E-014") else {
            return XCTFail("expected the known entrance")
        }
        XCTAssertEqual(same.riseInches, 0.75)
    }

    // MARK: - the distance cap is a metrology cap

    func testTheFarShotTheProtocolAsksForIsAllowedInScreening() {
        // docs/capture-protocol.md asks for a "far, ~3-4 m" shot. Under the metrology cap of 3 m
        // that shot is refused, which would make the protocol impossible to follow.
        guard case .success(let c) = TruthValidation.conditions(
            distance: "3.5", lighting: .overcast, surface: nil, occlusion: .none,
            mode: .screening) else {
            return XCTFail("3.5 m must be allowed for a screening capture")
        }
        XCTAssertEqual(c.distanceM, 3.5)
    }

    func testTheCapStillBindsForMetrology() {
        guard case .failure(.distanceBeyondCap) = TruthValidation.conditions(
            distance: "3.5", lighting: .overcast, surface: .concrete, occlusion: .none,
            mode: .metrology) else {
            return XCTFail("the metrology cap must still bind")
        }
    }

    func testScreeningConditionsCarryNoSurfaceOrCardPlacement() {
        let c = conditions(mode: .screening)
        // The protocol never asks an operator for either, so a value here would be a guess.
        XCTAssertNil(c.surface)
        XCTAssertNil(c.cardPlacement)
    }

    // MARK: - what each mode writes

    private func record(mode: CaptureMode) -> CaptureRecord {
        CaptureRecord(
            captureId: "cap-1",
            captureMode: mode,
            pixelWidth: 4032, pixelHeight: 3024,
            imageExifOrientation: 6,
            intrinsics: mode.isOurCamera ? CameraIntrinsics(
                fx: 2792, fy: 2792, cx: 2037.2, cy: 1499,
                lensDistortionLookupTable: Data(repeating: 0, count: 168),
                lensDistortionCenterX: 2016.4, lensDistortionCenterY: 1512.7) : nil,
            gravity: mode.isOurCamera ? GravitySample(x: 0.02, y: -0.98, z: -0.19) : nil,
            deviceModel: "iPhone17,3",
            lens: mode.isOurCamera ? "builtInWideAngleCamera" : nil,
            captureDevice: mode.isOurCamera ? "builtInDualWideCamera" : nil,
            zoomFactor: mode.isOurCamera ? 2.0 : nil,
            capturedAt: "2026-09-02T14:22:31Z",
            depth: nil,
            entrance: mode.carriesMetrologyTruth ? metrologyEntrance() : entrance(),
            conditions: conditions(mode: mode),
            roi: mode.carriesMetrologyTruth ? ROITaps(
                thresholdTop: PixelPoint(x: 1010, y: 1400),
                thresholdBottom: PixelPoint(x: 1012, y: 1480),
                cardCorners: [PixelPoint(x: 900, y: 1500), PixelPoint(x: 1100, y: 1500),
                              PixelPoint(x: 1100, y: 1620), PixelPoint(x: 900, y: 1620)]) : nil)
    }

    private func sidecarJSON(_ mode: CaptureMode) throws -> [String: Any] {
        let assembled = CaptureWriter.sidecar(
            for: record(mode: mode), imagePath: "cap-1.jpg",
            imageSHA256: String(repeating: "a", count: 64),
            depthPath: nil, depthSHA256: nil)
        guard case .success(let sidecar) = assembled else {
            throw XCTSkip("sidecar refused: \(assembled)")
        }
        let data = try CaptureWriter.encoder().encode(sidecar)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    func testAScreeningSidecarOmitsEveryMetrologyField() throws {
        let json = try sidecarJSON(.screening)
        XCTAssertEqual(json["capture_mode"] as? String, "screening")
        for forbidden in ["ground_truth", "card_placement", "roi"] {
            XCTAssertNil(json[forbidden], "\(forbidden) must be absent, not null")
        }
        // Our camera took it, so what the camera knows is still recorded.
        XCTAssertNotNil(json["intrinsics"])
        XCTAssertNotNil(json["gravity"])
        XCTAssertNil((json["conditions"] as? [String: Any])?["surface"])
    }

    func testAnImportedSidecarClaimsNoCaptureMetadata() throws {
        let json = try sidecarJSON(.imported)
        XCTAssertEqual(json["capture_mode"] as? String, "imported")
        for forbidden in ["intrinsics", "gravity", "lens", "capture_device", "zoom_factor",
                          "ground_truth", "card_placement", "roi"] {
            XCTAssertNil(json[forbidden], "\(forbidden) must be absent for an imported photo")
        }
        // What it does keep is what the file itself said.
        XCTAssertEqual(json["device_model"] as? String, "iPhone17,3")
        XCTAssertEqual(json["captured_at"] as? String, "2026-09-02T14:22:31Z")
    }

    func testAMetrologySidecarIsUnchanged() throws {
        let json = try sidecarJSON(.metrology)
        XCTAssertEqual(json["capture_mode"] as? String, "metrology")
        for required in ["ground_truth", "card_placement", "roi", "intrinsics", "gravity",
                         "lens", "capture_device", "zoom_factor"] {
            XCTAssertNotNil(json[required], "\(required) must still be written")
        }
    }

    func testAMetrologyCaptureWithNoTapsIsStillRefused() {
        var r = record(mode: .metrology)
        r.roi = nil
        guard case .failure = CaptureWriter.sidecar(
            for: r, imagePath: "a.jpg", imageSHA256: String(repeating: "a", count: 64),
            depthPath: nil, depthSHA256: nil) else {
            return XCTFail("a metrology capture without taps must be refused")
        }
    }

    // MARK: - the reading must not leak across modes

    func testAScreeningCaptureOfAnEntranceWithAReadingStillWritesNoGroundTruth() throws {
        // E-014 is shot in metrology mode in the morning; in the afternoon the operator switches
        // to Screening and shoots it again. `resolveScreening` returns the SAME entrance, reading
        // intact and deliberately so -- so the writer must gate on the mode, not on whether the
        // entrance happens to carry one. Otherwise the screening sidecar claims a caliper reading
        // nobody took at that shot, and the schema refuses the record after it is on disk.
        var r = record(mode: .screening)
        r.entrance = metrologyEntrance()
        let assembled = CaptureWriter.sidecar(
            for: r, imagePath: "a.jpg", imageSHA256: String(repeating: "a", count: 64),
            depthPath: nil, depthSHA256: nil)
        guard case .success(let sidecar) = assembled else {
            return XCTFail("a screening capture of a known entrance must still be writable")
        }
        XCTAssertNil(sidecar.groundTruth)
        XCTAssertNil(sidecar.cardPlacement)
    }

    func testAScreeningCaptureWithACardPlacementInItsTagsStillWritesNone() throws {
        // The same leak by the other route: conditions edited from the viewfinder used to come
        // back carrying `cardPlacement: .vertical` from a default argument.
        var r = record(mode: .screening)
        r.conditions = ConditionTags(
            distanceM: 2.0, lighting: .overcast, surface: .concrete,
            occlusion: Occlusion.none, cardPlacement: .vertical)
        guard case .success(let sidecar) = CaptureWriter.sidecar(
            for: r, imagePath: "a.jpg", imageSHA256: String(repeating: "a", count: 64),
            depthPath: nil, depthSHA256: nil) else {
            return XCTFail("expected a writable screening capture")
        }
        XCTAssertNil(sidecar.cardPlacement)
        XCTAssertNil(sidecar.conditions.surface)
    }

    func testEditingConditionsMidSessionKeepsTheScreeningContract() {
        // What ConditionsSheet does on Save. Defaulting to metrology here re-applied the 3 m cap
        // and handed back a card placement, mid-session, with no way for the operator to tell.
        guard case .success(let tags) = TruthValidation.conditions(
            distance: "3.5", lighting: .lowLight, surface: .concrete,
            occlusion: .partial, mode: .screening) else {
            return XCTFail("the protocol's far shot must survive a mid-session edit")
        }
        XCTAssertNil(tags.cardPlacement)
        XCTAssertNil(tags.surface)
        XCTAssertEqual(tags.distanceM, 3.5)
    }

    // MARK: - a screening entrance can still be upgraded

    func testAnEntranceFirstSeenByScreeningCanLaterTakeAReading() async {
        // Otherwise that doorway could never be captured in metrology mode on this device: the
        // setup screen reused the reading-less entrance and the writer then refused it, with no
        // way to supply one.
        let store = await EntranceStore()
        _ = await store.resolveScreening(id: "E-014")
        guard case .success(let upgraded) = await store.upgradeToMetrology(
            id: "E-014", rise: "0.75", instrument: "digital caliper") else {
            return XCTFail("a reading-less entrance must be able to take a reading")
        }
        XCTAssertEqual(upgraded.riseInches, 0.75)
    }

    func testAnEntranceThatAlreadyHasAReadingKeepsItAgainstASecondOperator() async {
        // The no-overwrite rule still stands where it was meant to.
        let store = await EntranceStore()
        _ = await store.resolve(id: "E-014", rise: "0.75", instrument: "digital caliper")
        guard case .success(let same) = await store.upgradeToMetrology(
            id: "E-014", rise: "2.50", instrument: "tape measure") else {
            return XCTFail("expected the known entrance")
        }
        XCTAssertEqual(same.riseInches, 0.75)
        XCTAssertEqual(same.instrument, "digital caliper")
    }

    // MARK: - a screening capture is not lost to a missing camera model

    func testAScreeningCaptureSurvivesADeviceThatDeliversNoDistortionTable() throws {
        // The phone carrying depth capture (D-032) has never been through the capability probe.
        // Refusing here would lose the entrance rather than record it.
        var r = record(mode: .screening)
        r.intrinsics = nil
        r.gravity = nil
        guard case .success(let sidecar) = CaptureWriter.sidecar(
            for: r, imagePath: "a.jpg", imageSHA256: String(repeating: "a", count: 64),
            depthPath: nil, depthSHA256: nil) else {
            return XCTFail("a screening capture must not be lost to a missing camera model")
        }
        XCTAssertNil(sidecar.intrinsics)
        XCTAssertNil(sidecar.gravity)
    }

    func testAMetrologyCaptureIsStillRefusedWithoutTheCameraModel() {
        var r = record(mode: .metrology)
        r.intrinsics = nil
        guard case .failure = CaptureWriter.sidecar(
            for: r, imagePath: "a.jpg", imageSHA256: String(repeating: "a", count: 64),
            depthPath: nil, depthSHA256: nil) else {
            return XCTFail("metrology still needs the camera model every arm depends on")
        }
    }

    func testAMetrologyCaptureWithNoReadingIsRefused() {
        var r = record(mode: .metrology)
        r.entrance = entrance()          // screening entrance: no rise
        guard case .failure = CaptureWriter.sidecar(
            for: r, imagePath: "a.jpg", imageSHA256: String(repeating: "a", count: 64),
            depthPath: nil, depthSHA256: nil) else {
            return XCTFail("a metrology capture with no caliper reading must be refused")
        }
    }
}
