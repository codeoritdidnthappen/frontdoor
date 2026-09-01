import XCTest
import simd
@testable import FrontdoorCapture

/// TICK-022's rules, tested without a camera.
///
/// Each case here is a way a frame can look fine and be useless to the method. A capture that is
/// silently kept in any of these states corrupts the dataset more expensively than a missing one,
/// because nothing downstream can tell it apart from a good record.
final class CaptureValidationTests: XCTestCase {

    private let goodIntrinsics = Intrinsics(
        fx: 2934.1, fy: 2934.1, cx: 2016.4, cy: 1512.7,
        referenceWidth: 4032, referenceHeight: 3024, distortionTableEntries: 42
    )
    private let goodGravity = SIMD3<Double>(0.02, -0.98, -0.19)

    private func rejection(
        zoom: Double = 1.0,
        intrinsics: Intrinsics? = nil,
        gravity: SIMD3<Double>?? = nil,
        delivered: (Int, Int) = (4032, 3024),
        sensor: (Int, Int)? = (4032, 3024)
    ) -> CaptureRejection? {
        CaptureValidator.rejection(
            zoomFactor: zoom,
            intrinsics: intrinsics ?? goodIntrinsics,
            gravity: gravity ?? goodGravity,
            deliveredWidth: delivered.0,
            deliveredHeight: delivered.1,
            sensorWidth: sensor?.0,
            sensorHeight: sensor?.1
        )
    }

    func testAWellFormedCaptureIsAccepted() {
        XCTAssertNil(rejection())
    }

    // MARK: - Zoom is fixed by D-014, not merely preferred

    func testZoomOtherThanOneIsRejected() {
        XCTAssertEqual(rejection(zoom: 2.0), .zoomNotOne(2.0))
        XCTAssertEqual(rejection(zoom: 1.5), .zoomNotOne(1.5))
    }

    func testTinyFloatingPointDriftAroundOneIsAccepted() {
        // videoZoomFactor is a CGFloat round-tripped through the device; exact equality would
        // reject good captures for a reason that has nothing to do with geometry.
        XCTAssertNil(rejection(zoom: 1.0000001))
    }

    // MARK: - A frame without intrinsics is unusable by every arm

    func testMissingCalibrationIsRejected() {
        let result = CaptureValidator.rejection(
            zoomFactor: 1.0, intrinsics: nil, gravity: goodGravity,
            deliveredWidth: 4032, deliveredHeight: 3024, sensorWidth: 4032, sensorHeight: 3024
        )
        XCTAssertEqual(result, .missingCalibration)
    }

    func testMissingCalibrationIsCheckedBeforeGravity() {
        // Both are wrong; the message must name the one that makes the frame unusable rather than
        // the one that happens to be checked first.
        let result = CaptureValidator.rejection(
            zoomFactor: 1.0, intrinsics: nil, gravity: nil,
            deliveredWidth: 4032, deliveredHeight: 3024, sensorWidth: 4032, sensorHeight: 3024
        )
        XCTAssertEqual(result, .missingCalibration)
    }

    // MARK: - Gravity, the thing that makes capture angle a measurement

    func testMissingGravityIsRejected() {
        let result = CaptureValidator.rejection(
            zoomFactor: 1.0, intrinsics: goodIntrinsics, gravity: nil,
            deliveredWidth: 4032, deliveredHeight: 3024, sensorWidth: 4032, sensorHeight: 3024
        )
        XCTAssertEqual(result, .missingGravity)
    }

    func testGravityFarFromOneGIsRejected() {
        // Motion updates not actually running: the vector is noise wearing the shape of a
        // measurement, which is exactly what D-019's angle model must not be fitted against.
        guard case .gravityImplausible(let magnitude)? =
            rejection(gravity: .some(SIMD3(0.1, 0.1, 0.1)))
        else { return XCTFail("expected an implausible-gravity rejection") }
        XCTAssertEqual(magnitude, 0.1732, accuracy: 0.001)
    }

    func testGravityAtTheEdgeOfToleranceIsAccepted() {
        XCTAssertNil(rejection(gravity: .some(SIMD3(1.04, 0, 0))))
        XCTAssertNotNil(rejection(gravity: .some(SIMD3(1.06, 0, 0))))
    }

    func testAZeroGravityVectorIsRejectedRatherThanTreatedAsValid() {
        guard case .gravityImplausible? = rejection(gravity: .some(SIMD3(0, 0, 0))) else {
            return XCTFail("a zero vector must not pass as a gravity reading")
        }
    }

    // MARK: - Full resolution, because the error budget is counted in pixels

    func testADownscaledStillIsRejected() {
        XCTAssertEqual(
            rejection(delivered: (1920, 1440), sensor: (4032, 3024)),
            .notFullResolution(delivered: "1920x1440", expected: "4032x3024")
        )
    }

    func testAnUnknownSensorMaximumIsNotTreatedAsAFailure() {
        // Refusing every capture on a device we cannot interrogate helps nobody; the dimensions
        // are still recorded, so the gap is visible in the data rather than fatal in the field.
        XCTAssertNil(rejection(delivered: (1920, 1440), sensor: nil))
    }

    // MARK: - The messages are what an operator acts on

    func testEveryRejectionExplainsItselfWithoutJargon() {
        let all: [CaptureRejection] = [
            .zoomNotOne(2.0), .missingCalibration, .missingGravity,
            .gravityImplausible(magnitude: 0.2),
            .notFullResolution(delivered: "1x1", expected: "2x2"),
        ]
        for rejection in all {
            XCTAssertFalse(
                rejection.message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                "\(rejection) has no message"
            )
            XCTAssertTrue(
                rejection.message.contains("Discarded"),
                "\(rejection) does not say the capture was discarded"
            )
        }
    }
}
