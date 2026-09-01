import XCTest
import simd
@testable import FrontdoorCapture

/// TICK-022's rules, tested without a camera.
///
/// Each case is a way a frame can look fine and be useless to the method. A capture silently kept
/// in any of these states corrupts the dataset more expensively than a missing one, because
/// nothing downstream can tell it from a good record.
final class CaptureValidationTests: XCTestCase {

    private let intrinsics = CameraIntrinsics(
        fx: 2934.1, fy: 2934.1, cx: 2016.4, cy: 1512.7,
        lensDistortionLookupTable: Data(count: 128),
        lensDistortionCenterX: 2016.4, lensDistortionCenterY: 1512.7
    )
    private let gravity = GravitySample(x: 0.02, y: -0.98, z: -0.19)
    /// Fixed rather than Date() so an assertion on it cannot pass by accident.
    private let shutter = Date(timeIntervalSince1970: 1_756_684_800)
    private let sensor = SensorResolution(width: 4032, height: 3024)

    private func result(
        width: Int = 4032, height: Int = 3024,
        intrinsics: CameraIntrinsics?? = nil, hadCalibration: Bool = true,
        gravity: GravitySample?? = nil, zoom: Double = 1.0,
        sensor: SensorResolution?? = nil
    ) -> Result<CaptureRecord, CaptureRejected> {
        CaptureValidation.record(
            capturedAt: shutter,
            pixelWidth: width, pixelHeight: height,
            sensor: sensor ?? self.sensor,
            intrinsics: intrinsics ?? self.intrinsics,
            hadCalibrationData: hadCalibration,
            gravity: gravity ?? self.gravity,
            deviceModel: "iPhone17,3", lens: CaptureController.lensName, zoomFactor: zoom
        )
    }

    private func rejection(_ r: Result<CaptureRecord, CaptureRejected>) -> CaptureRejected? {
        if case .failure(let e) = r { return e }
        return nil
    }

    func testAWellFormedCaptureIsAccepted() throws {
        let record = try result().get()
        XCTAssertEqual(record.pixelWidth, 4032)
        XCTAssertEqual(record.lens, "builtInWideAngleCamera")
    }

    /// The recorded lens must match the sidecar example in ARCHITECTURE section 4. Derived from
    /// the AVFoundation raw value it comes out capitalised, and anything filtering on the
    /// documented spelling then matches nothing.
    // MARK: captured_at

    /// captured_at is a required property of the sidecar schema, so a record without it cannot be
    /// serialised at all. The value must be the one handed in at the shutter, not re-sampled.
    func testTheRecordCarriesTheShutterTimestamp() throws {
        XCTAssertEqual(try result().get().capturedAt, shutter)
    }

    /// The schema accepts one spelling: RFC 3339, UTC, `Z` rather than an offset (#102). A local
    /// timezone here would produce +05:00 and the sidecar would be rejected on write.
    func testTheTimestampIsFormattedAsRFC3339InUTC() {
        XCTAssertEqual(CapturedAtFormat.string(from: shutter), "2025-09-01T00:00:00Z")
    }

    // MARK: full sensor resolution (AC3)

    /// A downscaled still looks uncropped. Its intrinsics describe a grid it does not have, and
    /// nothing downstream can detect that from the file.
    func testAFrameSmallerThanTheSensorIsRejected() {
        let r = rejection(result(width: 2016, height: 1512))
        XCTAssertEqual(r, .belowSensorResolution(
            delivered: SensorResolution(width: 2016, height: 1512),
            sensor: sensor
        ))
    }

    /// AC3 asks the operator to be told which two numbers disagreed.
    func testTheRejectionNamesBothResolutions() throws {
        let message = try XCTUnwrap(rejection(result(width: 2016, height: 1512))?.message)
        XCTAssertTrue(message.contains("2016x1512"), message)
        XCTAssertTrue(message.contains("4032x3024"), message)
    }

    /// "Smaller than the sensor" and "no frame at all" are different failures and must not
    /// collapse into one message.
    func testASmallFrameIsDistinguishableFromNoFrame() {
        XCTAssertEqual(rejection(result(width: 0, height: 0)), .noImageData)
        XCTAssertNotEqual(rejection(result(width: 2016, height: 1512)), .noImageData)
    }

    /// An unknown sensor maximum is a gap in what can be checked, not evidence the frame is bad.
    /// Rejecting here would refuse every capture on a device whose formats report nothing.
    func testAnUnknownSensorResolutionDoesNotCostTheCapture() throws {
        XCTAssertEqual(try result(width: 2016, height: 1512, sensor: .some(nil)).get().pixelWidth, 2016)
    }

    func testLensNameMatchesTheDocumentedSidecarValue() {
        XCTAssertEqual(CaptureController.lensName, "builtInWideAngleCamera")
    }

    // MARK: - Zoom is fixed by D-014, not merely preferred

    func testZoomOtherThanOneIsRejected() {
        XCTAssertEqual(rejection(result(zoom: 2.0)), .zoomNotUnity(2.0))
    }

    func testTinyFloatingPointDriftAroundOneIsAccepted() {
        // videoZoomFactor round-trips through the device as a float; exact equality would reject
        // good captures for a reason that has nothing to do with geometry.
        XCTAssertNil(rejection(result(zoom: 1.0000001)))
    }

    // MARK: - A frame without intrinsics is unusable by every arm

    func testMissingCalibrationIsRejected() {
        XCTAssertEqual(
            rejection(result(intrinsics: .some(nil), hadCalibration: false)), .noCalibrationData
        )
    }

    /// Calibration that arrived but could not be matched to the image is a different fault from
    /// none arriving, and the operator is told which.
    func testCalibrationThatArrivedButIsUnusableIsDistinguished() {
        XCTAssertEqual(
            rejection(result(intrinsics: .some(nil), hadCalibration: true)),
            .unusableCalibrationData
        )
    }

    func testAZeroSizedFrameIsRejectedBeforeAnythingElse() {
        XCTAssertEqual(rejection(result(width: 0, height: 0)), .noImageData)
    }

    // MARK: - Gravity, the thing that makes capture angle a measurement

    func testMissingGravityIsRejected() {
        XCTAssertEqual(rejection(result(gravity: .some(nil))), .noGravitySample)
    }

    func testGravityFarFromOneGIsRejected() {
        // Motion updates not actually running: the vector is noise wearing the shape of a
        // measurement, which is exactly what D-019's angle model must not be fitted against.
        guard case .gravityImplausible(let magnitude)? =
            rejection(result(gravity: .some(GravitySample(x: 0.1, y: 0.1, z: 0.1))))
        else { return XCTFail("expected an implausible-gravity rejection") }
        XCTAssertEqual(magnitude, 0.1732, accuracy: 0.001)
    }

    func testGravityToleranceBoundary() {
        XCTAssertNil(rejection(result(gravity: .some(GravitySample(x: 1.04, y: 0, z: 0)))))
        XCTAssertNotNil(rejection(result(gravity: .some(GravitySample(x: 1.06, y: 0, z: 0)))))
    }

    func testAZeroVectorIsRejectedRatherThanTreatedAsValid() {
        guard case .gravityImplausible? =
            rejection(result(gravity: .some(GravitySample(x: 0, y: 0, z: 0))))
        else { return XCTFail("a zero vector must not pass as a gravity reading") }
    }

    // MARK: - Intrinsics must describe the image beside them

    /// AVFoundation reports the matrix against a reference grid that need not match the still.
    /// Unscaled, an fx measured on a 2016-wide grid would be applied to a 4032-wide image, and
    /// every length the metrology derives from it would be out by a factor of two.
    func testIntrinsicsAreScaledOntoTheStillsPixelGrid() throws {
        var matrix = matrix_float3x3(diagonal: SIMD3<Float>(1, 1, 1))
        matrix.columns.0.x = 1467.0   // fx on the reference grid
        matrix.columns.1.y = 1467.0
        matrix.columns.2.x = 1008.0   // cx
        matrix.columns.2.y = 756.0

        let scaled = try XCTUnwrap(CameraIntrinsics.from(
            matrix: matrix,
            referenceDimensions: CGSize(width: 2016, height: 1512),
            distortionTable: nil,
            distortionCenter: CGPoint(x: 1008, y: 756),
            pixelWidth: 4032, pixelHeight: 3024
        ))

        XCTAssertEqual(scaled.fx, 2934.0, accuracy: 0.01)
        XCTAssertEqual(scaled.cx, 2016.0, accuracy: 0.01)
        XCTAssertEqual(scaled.cy, 1512.0, accuracy: 0.01)
        XCTAssertEqual(scaled.lensDistortionCenterX, 2016.0, accuracy: 0.01)
    }

    func testIntrinsicsNeedNoScalingWhenTheGridsAlreadyMatch() throws {
        var matrix = matrix_float3x3(diagonal: SIMD3<Float>(1, 1, 1))
        matrix.columns.0.x = 2934.0
        let same = try XCTUnwrap(CameraIntrinsics.from(
            matrix: matrix,
            referenceDimensions: CGSize(width: 4032, height: 3024),
            distortionTable: nil, distortionCenter: .zero,
            pixelWidth: 4032, pixelHeight: 3024
        ))
        XCTAssertEqual(same.fx, 2934.0, accuracy: 0.01)
    }

    /// A zero reference grid would divide by zero and produce infinities that look like numbers.
    func testADegenerateReferenceGridYieldsNoIntrinsics() {
        XCTAssertNil(CameraIntrinsics.from(
            matrix: matrix_float3x3(diagonal: SIMD3<Float>(1, 1, 1)),
            referenceDimensions: CGSize(width: 0, height: 0),
            distortionTable: nil, distortionCenter: .zero,
            pixelWidth: 4032, pixelHeight: 3024
        ))
    }

    // MARK: - The messages are what an operator acts on

    func testEveryRejectionSaysNothingWasRecorded() {
        let all: [CaptureRejected] = [
            .noImageData, .noCalibrationData, .unusableCalibrationData,
            .zoomNotUnity(2.0), .noGravitySample, .gravityImplausible(0.2),
        ]
        for rejection in all {
            XCTAssertTrue(
                rejection.message.contains("Nothing was recorded"),
                "\(rejection) does not tell the operator the capture was discarded"
            )
        }
    }
}
