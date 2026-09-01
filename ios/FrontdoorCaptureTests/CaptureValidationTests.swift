import XCTest
@testable import FrontdoorCapture

/// TICK-022's rules, tested without a camera.
///
/// Every case here is a way a frame can look fine and be useless to the method. A capture silently
/// kept in one of these states corrupts the dataset more expensively than a missing one, because
/// nothing downstream can tell it apart from a good record.
///
/// Ported from the parallel implementation in PR #144, which had these tests where #142 did not.
///
/// Two things #144 validated are absent from this layer and so are untested here — a `captured_at`
/// timestamp sampled at the shutter, and the delivered frame checked against the sensor's full
/// resolution. Both are real gaps, filed rather than quietly dropped.
final class CaptureValidationTests: XCTestCase {

    private let goodIntrinsics = CameraIntrinsics(
        fx: 2934.1, fy: 2934.1, cx: 2016.4, cy: 1512.7,
        lensDistortionLookupTable: Data([0x01, 0x02, 0x03]),
        lensDistortionCenterX: 2016.4, lensDistortionCenterY: 1512.7
    )
    private let goodGravity = GravitySample(x: 0.02, y: -0.98, z: -0.19)

    private func validate(
        width: Int = 4032,
        height: Int = 3024,
        intrinsics: CameraIntrinsics?? = nil,
        hadCalibration: Bool = true,
        gravity: GravitySample?? = nil,
        zoom: Double = 1.0,
        depth: DepthRecord? = nil
    ) -> Result<CaptureRecord, CaptureRejected> {
        CaptureValidation.record(
            pixelWidth: width,
            pixelHeight: height,
            intrinsics: intrinsics ?? goodIntrinsics,
            hadCalibrationData: hadCalibration,
            gravity: gravity ?? goodGravity,
            deviceModel: "iPhone17,1",
            lens: "builtInWideAngleCamera",
            zoomFactor: zoom,
            depth: depth
        )
    }

    private func rejection(_ result: Result<CaptureRecord, CaptureRejected>) -> CaptureRejected? {
        if case .failure(let reason) = result { return reason }
        return nil
    }

    // MARK: - The happy path

    func testAWellFormedCaptureIsAccepted() {
        guard case .success(let record) = validate() else {
            return XCTFail("a well-formed capture must be accepted")
        }
        XCTAssertEqual(record.pixelWidth, 4032)
        XCTAssertEqual(record.deviceModel, "iPhone17,1")
        XCTAssertEqual(record.lens, "builtInWideAngleCamera")
    }

    // MARK: - Zoom is fixed by D-014, not merely preferred

    func testZoomOtherThanOneIsRejected() {
        XCTAssertEqual(rejection(validate(zoom: 2.0)), .zoomNotUnity(2.0))
        XCTAssertEqual(rejection(validate(zoom: 1.5)), .zoomNotUnity(1.5))
    }

    func testTinyFloatingPointDriftAroundOneIsAccepted() {
        // videoZoomFactor is a CGFloat round-tripped through the device. Exact equality would
        // reject good captures for a reason that has nothing to do with geometry.
        XCTAssertNil(rejection(validate(zoom: 1.0000001)))
    }

    // MARK: - A frame without intrinsics is unusable by every arm (D-015)

    func testMissingCalibrationIsRejected() {
        XCTAssertEqual(rejection(validate(hadCalibration: false)), .noCalibrationData)
    }

    func testCalibrationDeliveredButUnusableIsDistinguished() {
        // "None arrived" and "one arrived that cannot describe this image" need different messages:
        // the first is a device capability question, the second is a bug.
        XCTAssertEqual(
            rejection(validate(intrinsics: .some(nil), hadCalibration: true)),
            .unusableCalibrationData
        )
    }

    func testMissingCalibrationIsReportedBeforeZoom() {
        // Both are wrong. The message must name the one that makes the frame unusable rather than
        // whichever happens to be checked first.
        XCTAssertEqual(rejection(validate(hadCalibration: false, zoom: 2.0)), .noCalibrationData)
    }

    // MARK: - Gravity is what makes capture angle a measurement

    func testMissingGravitySampleIsRejected() {
        XCTAssertEqual(rejection(validate(gravity: .some(nil))), .noGravitySample)
    }

    func testImplausibleGravityMagnitudeIsRejected() {
        // Motion updates that never started return a plausible-looking vector rather than an
        // obviously wrong one. The magnitude is the cheap check that they were running.
        let flat = GravitySample(x: 0, y: 0, z: 0)
        XCTAssertEqual(rejection(validate(gravity: .some(flat))), .gravityImplausible(0))
    }

    func testGravityWithinFivePercentOfOneGIsAccepted() {
        XCTAssertNil(rejection(validate(gravity: .some(GravitySample(x: 0, y: -1.04, z: 0)))))
        XCTAssertNil(rejection(validate(gravity: .some(GravitySample(x: 0, y: -0.96, z: 0)))))
    }

    func testGravityJustOutsideToleranceIsRejected() {
        XCTAssertNotNil(rejection(validate(gravity: .some(GravitySample(x: 0, y: -1.06, z: 0)))))
    }

    // MARK: - No image is not a measurement

    func testZeroDimensionsAreRejected() {
        XCTAssertEqual(rejection(validate(width: 0)), .noImageData)
        XCTAssertEqual(rejection(validate(height: 0)), .noImageData)
    }

    // MARK: - Depth is a comparison, never a method input (D-020)

    func testAbsentDepthDoesNotCostTheCapture() {
        // TICK-023: depth's absence must never reject a frame, because it is not a method input.
        guard case .success(let record) = validate(depth: nil) else {
            return XCTFail("a capture without depth must still be accepted")
        }
        XCTAssertNil(record.depth)
    }

    func testDepthIsCarriedWhenPresent() {
        let depth = DepthRecord(
            width: 320, height: 240, sha256: String(repeating: "a", count: 64),
            byteCount: 320 * 240 * 4, isAbsolutelyAccurate: true, isFiltered: false
        )
        guard case .success(let record) = validate(depth: depth) else {
            return XCTFail("depth must not affect acceptance")
        }
        XCTAssertEqual(record.depth, depth)
    }

    // MARK: - Every rejection has to be sayable to an operator

    func testEveryRejectionCarriesANonEmptyMessage() {
        let all: [CaptureRejected] = [
            .noImageData, .noCalibrationData, .unusableCalibrationData,
            .zoomNotUnity(2.0), .noGravitySample, .gravityImplausible(0.4)
        ]
        for reason in all {
            XCTAssertFalse(
                reason.message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                "\(reason) must carry a sentence an operator can act on"
            )
        }
    }
}
