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

    private func result(
        width: Int = 4032, height: Int = 3024,
        intrinsics: CameraIntrinsics?? = nil, hadCalibration: Bool = true,
        gravity: GravitySample?? = nil, zoom: Double = 1.0, mainLensZoom: Double = 1.0,
        capturedAt: String = "2026-09-01T14:22:31Z",
        sensorWidth: Int?? = nil, sensorHeight: Int?? = nil
    ) -> Result<CaptureRecord, CaptureRejected> {
        CaptureValidation.record(
            pixelWidth: width, pixelHeight: height,
            intrinsics: intrinsics ?? self.intrinsics,
            hadCalibrationData: hadCalibration,
            gravity: gravity ?? self.gravity,
            deviceModel: "iPhone17,3", lens: CaptureController.lensName,
            captureDevice: "builtInDualWideCamera", zoomFactor: zoom, mainLensZoomFactor: mainLensZoom,
            capturedAt: capturedAt,
            // Default to the frame's own size, so cases not about resolution stay unaffected.
            sensorWidth: sensorWidth ?? width, sensorHeight: sensorHeight ?? height,
            entrance: testEntrance, conditions: testConditions
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
    // MARK: the 1x main lens is a device-dependent number (TICK-020, both team phones)

    /// On builtInDualWideCamera the zoom scale is relative to the ultra-wide, so the main lens
    /// exposes at 2.00. TICK-020's probe measured exactly that on iPhone16,2 and iPhone17,3, and
    /// fx=2792 confirms the main lens rather than the ultra-wide's ~1456. Demanding a literal 1.0
    /// would reject every measurable frame either phone can produce.
    func testTheMainLensFactorOnTheDualWideIsAccepted() throws {
        let record = try result(zoom: 2.0, mainLensZoom: 2.0).get()
        XCTAssertEqual(record.zoomFactor, 2.0)
    }

    /// The other half of the trap: 1.0 on that device is the ultra-wide, roughly 120 degrees of
    /// barrel distortion. It must be refused, not waved through for looking like "1x".
    func testUnityZoomOnTheDualWideIsRefusedAsTheWrongLens() {
        XCTAssertEqual(
            rejection(result(zoom: 1.0, mainLensZoom: 2.0)),
            .zoomNotMainLens(factor: 1.0, expected: 2.0))
    }

    /// Digital zoom past the main lens is still digital zoom.
    func testZoomBeyondTheMainLensFactorIsRefused() {
        XCTAssertEqual(
            rejection(result(zoom: 3.0, mainLensZoom: 2.0)),
            .zoomNotMainLens(factor: 3.0, expected: 2.0))
    }

    /// The message has to name both numbers, or an operator sees "2.00, not 2.00".
    func testTheRefusalNamesBothFactors() {
        let message = CaptureRejected.zoomNotMainLens(factor: 1.0, expected: 2.0).message
        XCTAssertTrue(message.contains("1.00"), message)
        XCTAssertTrue(message.contains("2.00"), message)
    }

    /// The optics and the device opened are different claims, and the record has to carry both.
    /// A sidecar naming only builtInWideAngleCamera describes a capture that could not have
    /// happened: that device delivers no calibration data on either team phone (TICK-020).
    func testTheRecordNamesBothTheOpticsAndTheDeviceOpened() throws {
        let record = try result().get()
        XCTAssertEqual(record.lens, "builtInWideAngleCamera")
        XCTAssertEqual(record.captureDevice, "builtInDualWideCamera")
        XCTAssertNotEqual(record.lens, record.captureDevice)
    }

    func testLensNameMatchesTheDocumentedSidecarValue() {
        XCTAssertEqual(CaptureController.lensName, "builtInWideAngleCamera")
    }

    // MARK: - Zoom is fixed by D-014, not merely preferred

    func testZoomOtherThanOneIsRejected() {
        XCTAssertEqual(rejection(result(zoom: 2.0)), .zoomNotMainLens(factor: 2.0, expected: 1.0))
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
            .zoomNotMainLens(factor: 2.0, expected: 1.0), .noGravitySample, .gravityImplausible(0.2),
        ]
        for rejection in all {
            XCTAssertTrue(
                rejection.message.contains("Nothing was recorded"),
                "\(rejection) does not tell the operator the capture was discarded"
            )
        }
    }
    // MARK: - The session can go away between the press and the capture (#134)

    func testSessionNotReadyCarriesAnActionableMessage() {
        // capturePhoto() re-checks the video connection on the session queue and reports this,
        // rather than calling AVFoundation with no active connection — which raises an uncatchable
        // NSInvalidArgumentException and kills the app on an operator's phone.
        let message = CaptureRejected.sessionNotReady.message
        XCTAssertFalse(message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        XCTAssertTrue(
            message.contains("nothing was recorded"),
            "a refused shutter press must tell the operator nothing was saved"
        )
    }

    func testSessionNotReadyIsDistinctFromEveryOtherRejection() {
        let others: [CaptureRejected] = [
            .noImageData, .noCalibrationData, .unusableCalibrationData,
            .zoomNotMainLens(factor: 2.0, expected: 1.0), .noGravitySample, .gravityImplausible(0.4)
        ]
        for other in others {
            XCTAssertNotEqual(CaptureRejected.sessionNotReady, other)
            XCTAssertNotEqual(CaptureRejected.sessionNotReady.message, other.message)
        }
    }
    // MARK: - The frame must be the sensor's full resolution (TICK-022 AC3, #163)

    func testADownscaledFrameIsRejected() {
        // A quarter-size frame is not a readout mode; it is the output having been configured
        // below what the format offers. Uncropped-looking, and every ROI tap lands on a grid four
        // times coarser than the one the measurement assumes.
        let r = rejection(result(width: 1008, height: 756, sensorWidth: 4032, sensorHeight: 3024))
        XCTAssertEqual(r, .notFullResolution(delivered: "1008x756", sensor: "4032x3024"))
    }

    /// One binning step down is what a 48MP sensor actually does: TICK-020's probe requested
    /// 8064x6048 on iPhone17,3 and was handed 4032x3024. Refusing it would refuse every capture
    /// the team can take.
    func testTheBinnedReadoutIsAccepted() throws {
        let record = try result(width: 2016, height: 1512,
                                sensorWidth: 4032, sensorHeight: 3024).get()
        XCTAssertEqual(record.pixelWidth, 2016)
    }

    func testAnUnknownSensorResolutionIsNotAPass() {
        // An unknown maximum cannot confirm anything; accepting it silently is how the check would
        // stop meaning something.
        XCTAssertEqual(rejection(result(sensorWidth: .some(nil))), .sensorResolutionUnknown)
        XCTAssertEqual(rejection(result(sensorHeight: .some(nil))), .sensorResolutionUnknown)
    }

    func testAFullResolutionFrameIsAccepted() {
        XCTAssertNil(rejection(result(width: 4032, height: 3024,
                                      sensorWidth: 4032, sensorHeight: 3024)))
    }

    // MARK: - captured_at, sampled at the shutter (#163)

    func testTheRecordCarriesTheCaptureTime() throws {
        let record = try result(capturedAt: "2026-09-01T14:22:31Z").get()
        XCTAssertEqual(record.capturedAt, "2026-09-01T14:22:31Z")
    }

    func testNonUTCAndMalformedTimestampsAreRejected() {
        // The schema requires a literal Z. A formatter carrying the device's locale or time zone
        // produces a plausible string the schema refuses — after the entrance has been shot.
        for bad in ["2026-09-01T14:22:31+01:00", "2026-09-01 14:22:31Z", "banana", "",
                    "2026-09-01T14:22:31Z\n"] {
            XCTAssertEqual(rejection(result(capturedAt: bad)), .captureTimeUnusable(bad),
                           "\(bad) must not be accepted as a capture time")
        }
    }

    func testFractionalSecondsAreAccepted() {
        XCTAssertNil(rejection(result(capturedAt: "2026-09-01T14:22:31.482Z")))
    }

    func testTheGeneratedTimestampSatisfiesTheSchemaRule() {
        // The producer and the checker must agree, or every capture fails in the field.
        XCTAssertTrue(CaptureValidation.isUTCRFC3339(CaptureValidation.timestamp(for: Date())))
    }
}
