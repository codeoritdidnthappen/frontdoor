import CoreGraphics
import XCTest
import simd
@testable import FrontdoorCapture

/// The rules `CaptureValidationTests` states, tested where they actually bite.
///
/// Written by independent QA against PR #164, after mutation testing showed the first 14 tests
/// caught 2 of 20 deliberate breakages. Those 14 assert that a rejection *happens*; these assert
/// that the record carries what it validated, that each tolerance holds at its boundary rather
/// than only in its interior, and that each rejection is distinguishable from the others.
///
/// Mutation score with both suites: 20/20.
final class CaptureValidationBoundaryTests: XCTestCase {

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
            pixelWidth: width, pixelHeight: height,
            intrinsics: intrinsics ?? goodIntrinsics,
            hadCalibrationData: hadCalibration,
            gravity: gravity ?? goodGravity,
            deviceModel: "iPhone17,1", lens: "builtInWideAngleCamera",
            zoomFactor: zoom, depth: depth
        )
    }

    private func rejection(_ r: Result<CaptureRecord, CaptureRejected>) -> CaptureRejected? {
        if case .failure(let reason) = r { return reason }
        return nil
    }

    private func accepted(
        _ r: Result<CaptureRecord, CaptureRejected>, _ file: StaticString = #filePath,
        _ line: UInt = #line
    ) -> CaptureRecord? {
        guard case .success(let record) = r else {
            XCTFail("expected acceptance", file: file, line: line)
            return nil
        }
        return record
    }

    // MARK: - Kills M01-M04: the accepted record's payload is never asserted

    /// TICK-022 AC2: fx, fy, cx, cy and the distortion table are captured for that specific frame
    /// and *retained*. Nothing in the shipped suite asserts they survive validation.
    func testTheAcceptedRecordCarriesEveryValidatedValueThrough() {
        guard let record = accepted(validate(width: 4032, height: 3024, zoom: 1.0000001)) else {
            return
        }
        XCTAssertEqual(record.pixelWidth, 4032)
        XCTAssertEqual(record.pixelHeight, 3024)          // kills M01
        XCTAssertEqual(record.intrinsics, goodIntrinsics)  // kills M02 (incl. distortion table)
        XCTAssertEqual(record.gravity, goodGravity)        // kills M03
        XCTAssertEqual(record.zoomFactor, 1.0000001)       // kills M04
        XCTAssertEqual(record.deviceModel, "iPhone17,1")
        XCTAssertEqual(record.lens, "builtInWideAngleCamera")
    }

    // MARK: - Kills M05: the zoom check only ever sees zoom > 1

    func testZoomBelowUnityIsRejected() {
        XCTAssertEqual(rejection(validate(zoom: 0.5)), .zoomNotUnity(0.5))
        XCTAssertEqual(rejection(validate(zoom: 0.0)), .zoomNotUnity(0.0))
    }

    // MARK: - Kills M06/M18: pins the 0.001 zoom tolerance on both sides

    func testTheZoomToleranceBoundaryIsWhereItIsDocumented() {
        XCTAssertNil(rejection(validate(zoom: 1.0009)))       // just inside
        XCTAssertNotNil(rejection(validate(zoom: 1.0011)))    // just outside — kills M06
        XCTAssertNotNil(rejection(validate(zoom: 0.9989)))    // just outside, low side
    }

    // MARK: - Kills M07: the realistic "no calibration arrived" input

    /// `CaptureController.accept` derives both arguments from one optional: when calibration is
    /// nil, `hadCalibrationData` is false AND `intrinsics` is nil. The shipped suite only ever
    /// tests `hadCalibration: false` alongside *valid* intrinsics — a combination production
    /// cannot produce — so it cannot see the ordering of the two guards.
    func testNoCalibrationAtAllIsReportedAsNoneArrivedNotAsUnusable() {
        XCTAssertEqual(
            rejection(validate(intrinsics: .some(nil), hadCalibration: false)),
            .noCalibrationData
        )
    }

    // MARK: - Kills M08: the realistic "no frame" input

    /// When pixelWidth is 0, `CameraIntrinsics.from` returns nil, so production reaches the
    /// validator with intrinsics already nil. The shipped zero-dimension test injects *good*
    /// intrinsics instead, so it cannot see the dimension check being demoted.
    func testAZeroSizedFrameIsReportedAsNoImageDataEvenWithNoIntrinsics() {
        XCTAssertEqual(
            rejection(validate(width: 0, intrinsics: .some(nil))), .noImageData
        )
        XCTAssertEqual(
            rejection(validate(height: 0, intrinsics: .some(nil))), .noImageData
        )
    }

    // MARK: - Kills M09: messages are checked for non-emptiness but never for content

    func testEachRejectionSaysSomethingDifferentToTheOperator() {
        let all: [CaptureRejected] = [
            .noImageData, .noCalibrationData, .unusableCalibrationData,
            .zoomNotUnity(2.0), .noGravitySample, .gravityImplausible(0.4)
        ]
        let messages = Set(all.map(\.message))
        XCTAssertEqual(messages.count, all.count, "operator messages must be distinguishable")
        XCTAssertTrue(CaptureRejected.zoomNotUnity(2.0).message.contains("2.00"))
        XCTAssertTrue(CaptureRejected.gravityImplausible(0.4).message.contains("0.40"))
    }

    // MARK: - Kills M10/M16/M17: pins the 5% gravity band from TICK-022 AC3

    func testTheGravityBandIsExactlyFivePercent() {
        XCTAssertNil(rejection(validate(gravity: .some(GravitySample(x: 0, y: -1.0499, z: 0)))))
        XCTAssertNotNil(rejection(validate(gravity: .some(GravitySample(x: 0, y: -1.0501, z: 0)))))
        XCTAssertNil(rejection(validate(gravity: .some(GravitySample(x: 0, y: -0.9501, z: 0)))))
        // The low side of the band is never exercised by the shipped suite except at exactly 0.
        XCTAssertNotNil(rejection(validate(gravity: .some(GravitySample(x: 0, y: -0.9499, z: 0)))))
        XCTAssertNotNil(rejection(validate(gravity: .some(GravitySample(x: 0, y: -0.80, z: 0)))))
    }

    // MARK: - Kills M11

    func testNegativeDimensionsAreRejected() {
        XCTAssertEqual(rejection(validate(width: -1)), .noImageData)
        XCTAssertEqual(rejection(validate(height: -1)), .noImageData)
    }

    // MARK: - Kills M12/M13/M14: CameraIntrinsics.from has no tests at all

    /// The function that makes the intrinsics describe the image beside them. Untested by the PR,
    /// yet it is the only reason the numbers in a record mean anything.
    func testIntrinsicsAreRescaledIntoTheStillsOwnPixelGrid() {
        var matrix = matrix_float3x3(diagonal: SIMD3<Float>(1, 1, 1))
        matrix.columns.0.x = 1000   // fx
        matrix.columns.1.y = 1000   // fy
        matrix.columns.2.x = 960    // cx
        matrix.columns.2.y = 540    // cy

        let scaled = CameraIntrinsics.from(
            matrix: matrix,
            referenceDimensions: CGSize(width: 1920, height: 1080),
            distortionTable: Data([0xAB]),
            distortionCenter: CGPoint(x: 960, y: 540),
            pixelWidth: 3840, pixelHeight: 2160
        )
        guard let scaled else { return XCTFail("well-formed calibration must scale") }
        XCTAssertEqual(scaled.fx, 2000, accuracy: 0.001)   // kills M12
        XCTAssertEqual(scaled.fy, 2000, accuracy: 0.001)
        XCTAssertEqual(scaled.cx, 1920, accuracy: 0.001)
        XCTAssertEqual(scaled.cy, 1080, accuracy: 0.001)
        XCTAssertEqual(scaled.lensDistortionLookupTable, Data([0xAB]))
    }

    /// x and y scale independently, so a suite that only uses square-ish scale factors cannot
    /// tell sx from sy.
    func testTheXAndYScaleFactorsAreNotInterchangeable() {
        var matrix = matrix_float3x3(diagonal: SIMD3<Float>(1, 1, 1))
        matrix.columns.0.x = 1000
        matrix.columns.1.y = 1000
        let scaled = CameraIntrinsics.from(
            matrix: matrix, referenceDimensions: CGSize(width: 1000, height: 1000),
            distortionTable: nil, distortionCenter: .zero,
            pixelWidth: 4000, pixelHeight: 2000
        )
        guard let scaled else { return XCTFail("well-formed calibration must scale") }
        XCTAssertEqual(scaled.fx, 4000, accuracy: 0.001)   // kills M13
        XCTAssertEqual(scaled.fy, 2000, accuracy: 0.001)
    }

    func testDegenerateReferenceDimensionsProduceNoIntrinsicsRatherThanInfinities() {
        let matrix = matrix_float3x3(diagonal: SIMD3<Float>(1, 1, 1))
        XCTAssertNil(CameraIntrinsics.from(                 // kills M14
            matrix: matrix, referenceDimensions: CGSize(width: 0, height: 1080),
            distortionTable: nil, distortionCenter: .zero,
            pixelWidth: 4032, pixelHeight: 3024
        ))
    }

    // MARK: - Kills M15: hardwareIdentifier takes an injectable environment and is never called

    func testHardwareIdentifierPrefersTheSimulatorModelOverUname() {
        XCTAssertEqual(
            CaptureValidation.hardwareIdentifier(
                environment: ["SIMULATOR_MODEL_IDENTIFIER": "iPhone17,2"]
            ),
            "iPhone17,2"
        )
        XCTAssertNotEqual(CaptureValidation.hardwareIdentifier(environment: [:]), "")
    }
}
