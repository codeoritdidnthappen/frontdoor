import XCTest
@testable import FrontdoorCapture

/// TICK-026's one dangerous rule: taps are stored in the full-resolution image's coordinate space.
///
/// A still 4032 px wide is shown about 350 points wide. A tap recorded where the finger landed is
/// out by that factor on every capture, in the same direction, and nothing downstream can see it --
/// the measurement is simply wrong by a constant.
final class ROIValidationTests: XCTestCase {

    private let w = 4032
    private let h = 3024

    // MARK: the fitted rect

    /// scaledToFit letterboxes. The offset it introduces is exactly the error the conversion has
    /// to remove, so the rect has to be the image's, not the view's.
    func testAWiderViewLetterboxesLeftAndRight() {
        let rect = ROIValidation.fittedRect(
            pixelWidth: w, pixelHeight: h, in: CGSize(width: 800, height: 400))
        // 4:3 into 2:1 -> height-limited: 533.33 x 400, centred horizontally
        XCTAssertEqual(rect.height, 400, accuracy: 0.01)
        XCTAssertEqual(rect.width, 400 * 4 / 3, accuracy: 0.01)
        XCTAssertEqual(rect.minX, (800 - 400 * 4 / 3) / 2, accuracy: 0.01)
        XCTAssertEqual(rect.minY, 0, accuracy: 0.01)
    }

    func testATallerViewLetterboxesTopAndBottom() {
        let rect = ROIValidation.fittedRect(
            pixelWidth: w, pixelHeight: h, in: CGSize(width: 400, height: 800))
        XCTAssertEqual(rect.width, 400, accuracy: 0.01)
        XCTAssertEqual(rect.height, 300, accuracy: 0.01)
        XCTAssertEqual(rect.minY, 250, accuracy: 0.01)
    }

    func testADegenerateViewProducesNoRect() {
        XCTAssertEqual(
            ROIValidation.fittedRect(pixelWidth: w, pixelHeight: h, in: .zero), .zero)
        XCTAssertEqual(
            ROIValidation.fittedRect(pixelWidth: 0, pixelHeight: 0,
                                     in: CGSize(width: 100, height: 100)), .zero)
    }

    // MARK: view point -> image pixel

    func testTheCentreOfTheImageMapsToTheCentrePixel() throws {
        let rect = CGRect(x: 25, y: 0, width: 400, height: 300)
        let pixel = try XCTUnwrap(ROIValidation.pixel(
            of: CGPoint(x: 225, y: 150), displayed: rect, pixelWidth: w, pixelHeight: h))
        XCTAssertEqual(pixel, PixelPoint(x: 2016, y: 1512))
    }

    /// The letterbox offset is the whole point. The same finger position in a view that letterboxes
    /// differently must land on a different pixel.
    func testTheLetterboxOffsetIsRemoved() throws {
        let offset = CGRect(x: 100, y: 0, width: 400, height: 300)
        let flush = CGRect(x: 0, y: 0, width: 400, height: 300)
        let touch = CGPoint(x: 100, y: 0)
        XCTAssertEqual(
            ROIValidation.pixel(of: touch, displayed: offset, pixelWidth: w, pixelHeight: h),
            PixelPoint(x: 0, y: 0))
        XCTAssertEqual(
            ROIValidation.pixel(of: touch, displayed: flush, pixelWidth: w, pixelHeight: h),
            PixelPoint(x: 1008, y: 0))
    }

    func testTheCornersMapToTheImagesCorners() {
        let rect = CGRect(x: 25, y: 0, width: 400, height: 300)
        XCTAssertEqual(
            ROIValidation.pixel(of: CGPoint(x: 25, y: 0), displayed: rect,
                                pixelWidth: w, pixelHeight: h),
            PixelPoint(x: 0, y: 0))
        XCTAssertEqual(
            ROIValidation.pixel(of: CGPoint(x: 425, y: 300), displayed: rect,
                                pixelWidth: w, pixelHeight: h),
            PixelPoint(x: w - 1, y: h - 1))
    }

    /// A tap in the letterbox is not a point on the entrance. Clamping it to the edge would record
    /// a coordinate the operator never chose, and it would look deliberate.
    func testATapOutsideTheImageIsRefusedRatherThanClamped() {
        let rect = CGRect(x: 100, y: 50, width: 400, height: 300)
        for outside in [CGPoint(x: 50, y: 100), CGPoint(x: 550, y: 100),
                        CGPoint(x: 200, y: 10), CGPoint(x: 200, y: 400)] {
            XCTAssertNil(ROIValidation.pixel(of: outside, displayed: rect,
                                             pixelWidth: w, pixelHeight: h),
                         "\(outside) is off the image")
        }
    }

    /// Truncation would bias every tap towards the top-left by up to a pixel -- systematic across
    /// the dataset, not random.
    func testSubPixelPositionsRoundRatherThanTruncate() throws {
        let rect = CGRect(x: 0, y: 0, width: 4032, height: 3024)
        let pixel = try XCTUnwrap(ROIValidation.pixel(
            of: CGPoint(x: 100.6, y: 100.6), displayed: rect, pixelWidth: w, pixelHeight: h))
        XCTAssertEqual(pixel, PixelPoint(x: 101, y: 101))
    }

    // MARK: orientation (a portrait-held capture is landscape pixels)

    /// The still is 4032x3024 sensor pixels carrying .right, and displays upright on a portrait
    /// phone. Fitting it against the SENSOR shape wraps a landscape rect around a portrait image:
    /// the picture stretches to fill and every tap converts against a rect the image does not
    /// occupy. Found on device -- the operator said the picture looked distorted.
    func testAQuarterTurnedImageIsFittedByItsDisplayedShape() {
        let rect = ROIValidation.fittedRect(
            pixelWidth: w, pixelHeight: h, orientation: .right,
            in: CGSize(width: 400, height: 800))
        // Displayed 3:4, so width-limited at 400x533, centred vertically.
        XCTAssertEqual(rect.width, 400, accuracy: 0.01)
        XCTAssertEqual(rect.height, 400 * 4 / 3, accuracy: 0.01)
    }

    /// Sensor space is what the intrinsics are expressed in, so that is what gets recorded no
    /// matter how the still is shown. `.right` turns the buffer a quarter clockwise for display,
    /// which puts the sensor's bottom-left at the display's top-left.
    func testDisplayCornersMapToTheRightSensorCornersWhenTurned() {
        let rect = CGRect(x: 0, y: 0, width: 300, height: 400)
        XCTAssertEqual(
            ROIValidation.pixel(of: CGPoint(x: 0, y: 0), displayed: rect, orientation: .right,
                                pixelWidth: w, pixelHeight: h),
            PixelPoint(x: 0, y: h - 1))
        XCTAssertEqual(
            ROIValidation.pixel(of: CGPoint(x: 300, y: 0), displayed: rect, orientation: .right,
                                pixelWidth: w, pixelHeight: h),
            PixelPoint(x: 0, y: 0))
        XCTAssertEqual(
            ROIValidation.pixel(of: CGPoint(x: 300, y: 400), displayed: rect, orientation: .right,
                                pixelWidth: w, pixelHeight: h),
            PixelPoint(x: w - 1, y: 0))
    }

    /// Marks are stored in sensor space and drawn in display space. If the two directions disagree
    /// the markers appear somewhere the operator did not tap, which is how a wrong tap gets
    /// accepted as a correct one.
    func testTapAndMarkerRoundTripForEveryOrientation() throws {
        let rect = CGRect(x: 12, y: 30, width: 300, height: 400)
        for orientation in [UIImage.Orientation.up, .right, .left, .down] {
            for touch in [CGPoint(x: 40, y: 60), CGPoint(x: 200, y: 330),
                          CGPoint(x: 312, y: 430), CGPoint(x: 12, y: 30)] {
                let pixel = try XCTUnwrap(
                    ROIValidation.pixel(of: touch, displayed: rect, orientation: orientation,
                                        pixelWidth: w, pixelHeight: h),
                    "\(orientation) \(touch)")
                let back = ROIValidation.displayPoint(
                    of: pixel, in: rect, orientation: orientation,
                    pixelWidth: w, pixelHeight: h)
                XCTAssertEqual(back.x, touch.x, accuracy: 0.5, "\(orientation) x")
                XCTAssertEqual(back.y, touch.y, accuracy: 0.5, "\(orientation) y")
            }
        }
    }

    // MARK: assembling the six

    func testAllSixInOrderProduceTheRecord() throws {
        var marks: [ROITarget: PixelPoint] = [:]
        for (i, t) in ROITarget.allCases.enumerated() {
            marks[t] = PixelPoint(x: i * 10, y: i * 20)
        }
        let taps = try ROIValidation.taps(from: marks).get()
        XCTAssertEqual(taps.thresholdTop, PixelPoint(x: 0, y: 0))
        XCTAssertEqual(taps.thresholdBottom, PixelPoint(x: 10, y: 20))
        // Clockwise from top-left: the correspondence the homography relies on.
        XCTAssertEqual(taps.cardCorners, [
            PixelPoint(x: 20, y: 40), PixelPoint(x: 30, y: 60),
            PixelPoint(x: 40, y: 80), PixelPoint(x: 50, y: 100),
        ])
    }

    /// A capture cannot be saved with fewer than six taps (TICK-026, and TICK-028 AC5).
    func testFewerThanSixIsRefused() {
        var marks: [ROITarget: PixelPoint] = [:]
        for t in ROITarget.allCases.dropLast() { marks[t] = PixelPoint(x: 1, y: 1) }
        guard case .failure(let error) = ROIValidation.taps(from: marks) else {
            return XCTFail("five taps must not produce a record")
        }
        XCTAssertEqual(error, .incomplete(collected: 5))
    }

    /// Each of the six is looked up by name, so each one's absence must be refused on its own.
    func testEveryMissingPointIsRefusedIndividually() {
        for missing in ROITarget.allCases {
            var marks: [ROITarget: PixelPoint] = [:]
            for t in ROITarget.allCases where t != missing { marks[t] = PixelPoint(x: 1, y: 1) }
            guard case .failure = ROIValidation.taps(from: marks) else {
                return XCTFail("missing \(missing) must be refused")
            }
        }
    }

    func testTheOrderIsTheDocumentedWindingOrder() {
        XCTAssertEqual(ROITarget.allCases.map(\.shortLabel),
                       ["Top", "Bottom", "TL", "TR", "BR", "BL"])
        XCTAssertEqual(CardCorner.allCases.count, 4)
    }
}
