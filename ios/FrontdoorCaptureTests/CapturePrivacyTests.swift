import CoreImage
import ImageIO
import UniformTypeIdentifiers
import XCTest
@testable import FrontdoorCapture

/// Device-camera captures must be blurred and stripped before they are written (#328).
final class CapturePrivacyTests: XCTestCase {

    /// A JPEG carrying real GPS metadata and an orientation tag, as the camera would write it.
    private func jpeg(width: Int, height: Int, orientation: Int, withGPS: Bool) -> Data {
        let context = CIContext()
        let image = CIImage(color: .gray).cropped(
            to: CGRect(x: 0, y: 0, width: width, height: height))
        let cg = context.createCGImage(image, from: image.extent)!
        let data = NSMutableData()
        let destination = CGImageDestinationCreateWithData(
            data, UTType.jpeg.identifier as CFString, 1, nil)!
        var properties: [CFString: Any] = [kCGImagePropertyOrientation: orientation]
        if withGPS {
            properties[kCGImagePropertyGPSDictionary] = [
                kCGImagePropertyGPSLatitude: 37.7749,
                kCGImagePropertyGPSLatitudeRef: "N",
                kCGImagePropertyGPSLongitude: 122.4194,
                kCGImagePropertyGPSLongitudeRef: "W",
            ] as CFDictionary
        }
        CGImageDestinationAddImage(destination, cg, properties as CFDictionary)
        CGImageDestinationFinalize(destination)
        return data as Data
    }

    private func properties(of data: Data) -> [CFString: Any] {
        let source = CGImageSourceCreateWithData(data as CFData, nil)!
        return CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as! [CFString: Any]
    }

    // MARK: - location

    func testGPSDoesNotSurviveProcessing() {
        // The fixture really carries GPS: if this fails the test is proving nothing.
        let original = jpeg(width: 64, height: 48, orientation: 6, withGPS: true)
        XCTAssertNotNil(properties(of: original)[kCGImagePropertyGPSDictionary],
                        "fixture has no GPS to strip")

        guard case .success(let out) = CapturePrivacy.processWithoutDetection(
            original, exifOrientation: 6, normalizedFaceRectangles: []) else {
            return XCTFail("processing failed")
        }
        XCTAssertNil(properties(of: out.data)[kCGImagePropertyGPSDictionary],
                     "GPS survived: it must be stripped, not merely absent by luck")
    }

    func testTheOrientationTagIsTheOneThingKept() {
        // Stripping it too would make the stored image decode sideways for every consumer,
        // including the screening model.
        for tag in 1...8 {
            let out = CapturePrivacy.processWithoutDetection(
                jpeg(width: 64, height: 48, orientation: tag, withGPS: true),
                exifOrientation: tag, normalizedFaceRectangles: [])
            guard case .success(let processed) = out else {
                return XCTFail("processing failed for orientation \(tag)")
            }
            let kept = properties(of: processed.data)[kCGImagePropertyOrientation] as? Int
            XCTAssertEqual(kept, tag, "orientation \(tag) was not preserved")
        }
    }

    // MARK: - the grid must not move

    func testThePixelGridIsUnchanged() {
        // The sidecar's intrinsics, distortion_center and roi points are all expressed in the
        // STORED grid. Rotating the pixels here would describe a grid that no longer exists.
        guard case .success(let out) = CapturePrivacy.processWithoutDetection(
            jpeg(width: 64, height: 48, orientation: 6, withGPS: false),
            exifOrientation: 6, normalizedFaceRectangles: []) else {
            return XCTFail("processing failed")
        }
        XCTAssertEqual(out.pixelWidth, 64)
        XCTAssertEqual(out.pixelHeight, 48, "the grid was rotated; intrinsics would now be wrong")
    }

    // MARK: - the blur

    func testAFaceRegionIsActuallyAlteredNotJustCounted() {
        let original = jpeg(width: 64, height: 64, orientation: 1, withGPS: false)
        guard case .success(let out) = CapturePrivacy.processWithoutDetection(
            original, exifOrientation: 1,
            normalizedFaceRectangles: [CGRect(x: 0.25, y: 0.25, width: 0.5, height: 0.5)])
        else { return XCTFail("processing failed") }
        XCTAssertEqual(out.blurredFaceCount, 1)
        XCTAssertNotEqual(out.data, original, "the bytes are unchanged; nothing was blurred")
    }

    // MARK: - mapping a detection back into the stored grid

    private func assertMaps(
        _ orientation: Int, _ upright: CGPoint, to expected: CGPoint,
        line: UInt = #line
    ) {
        let rect = CapturePrivacy.rawRect(
            fromUpright: CGRect(origin: upright, size: .zero), exifOrientation: orientation)
        XCTAssertEqual(rect.origin.x, expected.x, accuracy: 0.0001, line: line)
        XCTAssertEqual(rect.origin.y, expected.y, accuracy: 0.0001, line: line)
    }

    func testEveryOrientationMapsAKnownCornerBack() {
        // Upright bottom-left (0,0) -> where it sits in the stored grid. Checked per case,
        // because a sign error blurs the wrong part of the frame and still looks plausible.
        assertMaps(1, CGPoint(x: 0, y: 0), to: CGPoint(x: 0, y: 0))
        assertMaps(2, CGPoint(x: 0, y: 0), to: CGPoint(x: 1, y: 0))
        assertMaps(3, CGPoint(x: 0, y: 0), to: CGPoint(x: 1, y: 1))
        assertMaps(4, CGPoint(x: 0, y: 0), to: CGPoint(x: 0, y: 1))
        assertMaps(5, CGPoint(x: 0, y: 0), to: CGPoint(x: 0, y: 0))
        assertMaps(6, CGPoint(x: 0, y: 0), to: CGPoint(x: 1, y: 0))
        assertMaps(7, CGPoint(x: 0, y: 0), to: CGPoint(x: 1, y: 1))
        assertMaps(8, CGPoint(x: 0, y: 0), to: CGPoint(x: 0, y: 1))
    }

    func testTheMappingIsAnInvolutionWhereItShouldBe() {
        // 1,2,3,4,5,7 are their own inverse; 6 and 8 are each other's. Applying twice returns
        // the point, which catches a transposed pair that a single corner check would not.
        for tag in [1, 2, 3, 4, 5, 7] {
            let start = CGPoint(x: 0.3, y: 0.8)
            let once = CapturePrivacy.rawRect(
                fromUpright: CGRect(origin: start, size: .zero), exifOrientation: tag).origin
            let twice = CapturePrivacy.rawRect(
                fromUpright: CGRect(origin: once, size: .zero), exifOrientation: tag).origin
            XCTAssertEqual(twice.x, start.x, accuracy: 0.0001, "orientation \(tag)")
            XCTAssertEqual(twice.y, start.y, accuracy: 0.0001, "orientation \(tag)")
        }
    }

    func testATransposingOrientationSwapsWidthAndHeight() {
        // Under orientation 6 a wide detection becomes a tall region in the stored grid. Mapping
        // origin and size separately would keep it wide and blur past the face on one axis while
        // missing it on the other.
        let wide = CGRect(x: 0.1, y: 0.4, width: 0.6, height: 0.2)
        let mapped = CapturePrivacy.rawRect(fromUpright: wide, exifOrientation: 6)
        XCTAssertEqual(mapped.width, 0.2, accuracy: 0.0001)
        XCTAssertEqual(mapped.height, 0.6, accuracy: 0.0001)
    }

    func testAnOutOfRangeTagIsTreatedAsUpright() {
        // ImageIO normalises these away, but a wrong guess here blurs the wrong region silently.
        assertMaps(0, CGPoint(x: 0.2, y: 0.7), to: CGPoint(x: 0.2, y: 0.7))
        assertMaps(9, CGPoint(x: 0.2, y: 0.7), to: CGPoint(x: 0.2, y: 0.7))
    }

    // MARK: - failing closed

    func testUndecodableBytesAreRefusedRatherThanPassedThrough() {
        let outcome = CapturePrivacy.process(Data("not a jpeg".utf8), exifOrientation: 1)
        guard case .failure(let failure) = outcome else {
            return XCTFail("undecodable bytes must not process")
        }
        XCTAssertEqual(failure, .unreadable)
        XCTAssertTrue(failure.message.contains("not saved"))
    }

    func testAFaceTooSmallToBlurRefusesTheCaptureRatherThanWritingItInTheClear() {
        // The one that shipped. A tiny or distant detection collapses below a pixel once the
        // 30% margin is intersected with the frame, and the blur loop used to `continue` -- so
        // the image was written and uploaded with that face untouched, and the reported count
        // said it had been handled. It has to refuse.
        let outcome = CapturePrivacy.processWithoutDetection(
            jpeg(width: 64, height: 64, orientation: 1, withGPS: false),
            exifOrientation: 1,
            normalizedFaceRectangles: [CGRect(x: 0, y: 0, width: 0.001, height: 0.001)])
        guard case .failure(let failure) = outcome else {
            return XCTFail("a detected face was not blurred and the capture was produced anyway")
        }
        XCTAssertEqual(failure, .blurFailed)
        XCTAssertTrue(failure.message.contains("not saved"),
                      "the refusal must not read as 'saved anyway'")
    }

    func testADetectionOutsideTheFrameRefusesRatherThanBeingSkipped() {
        // The other way the intersection empties: `isNull`. Same rule -- a face this step cannot
        // account for is a capture that does not get written.
        let outcome = CapturePrivacy.processWithoutDetection(
            jpeg(width: 64, height: 64, orientation: 1, withGPS: false),
            exifOrientation: 1,
            normalizedFaceRectangles: [CGRect(x: 2.0, y: 2.0, width: 0.1, height: 0.1)])
        guard case .failure(let failure) = outcome else {
            return XCTFail("an unaccounted-for detection produced a capture")
        }
        XCTAssertEqual(failure, .blurFailed)
    }

    func testNoSuccessEverReportsFewerBlursThanFacesItWasGiven() {
        // The count is the only thing that says a face was handled, so it must be impossible for
        // a success to carry a number smaller than the detections it was handed. Awkward inputs,
        // one per way the loop can give up: each must refuse, never succeed short.
        let awkward: [[CGRect]] = [
            [CGRect(x: 0.25, y: 0.25, width: 0.5, height: 0.5)],
            [CGRect(x: 0, y: 0, width: 0.001, height: 0.001)],
            [CGRect(x: 2.0, y: 2.0, width: 0.1, height: 0.1)],
            [CGRect(x: 0.1, y: 0.1, width: 0.3, height: 0.3),
             CGRect(x: 0, y: 0, width: 0.001, height: 0.001)],
        ]
        for rectangles in awkward {
            let outcome = CapturePrivacy.processWithoutDetection(
                jpeg(width: 64, height: 64, orientation: 1, withGPS: false),
                exifOrientation: 1, normalizedFaceRectangles: rectangles)
            if case .success(let out) = outcome {
                XCTAssertEqual(out.blurredFaceCount, rectangles.count,
                               "a capture was produced with \(rectangles.count - out.blurredFaceCount) "
                               + "face(s) left in the clear")
            }
        }
    }
}
