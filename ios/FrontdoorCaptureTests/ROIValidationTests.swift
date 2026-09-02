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

    // MARK: tap precision (TICK-135)

    /// AC1 asks for roughly 1:1 image pixels to screen pixels at the moment of placement. A
    /// 4032-wide still fitted to ~400 points is ten image pixels per point, so an unmagnified tap
    /// places a point the operator cannot see -- and that error lands in a rise judged against a
    /// quarter-inch bar.
    func testTheLoupeReachesOneToOneOnBothTeamPhones() {
        let fitted = CGRect(x: 0, y: 0, width: 400, height: 300)
        let zoom = ROIValidation.loupeZoom(
            pixelWidth: w, displayed: fitted, displayScale: 3)
        let screenPixelsPerImagePixel = fitted.width * zoom * 3 / CGFloat(w)
        XCTAssertGreaterThanOrEqual(screenPixelsPerImagePixel, 1.0)
    }

    /// The old fixed 4x cleared 1:1 on these phones by luck. On a narrower display of the same
    /// still it would not, and nothing would have said so.
    func testTheLoupeGrowsWhenTheStillIsShownSmaller() {
        let wide = ROIValidation.loupeZoom(
            pixelWidth: w, displayed: CGRect(x: 0, y: 0, width: 400, height: 300), displayScale: 3)
        let narrow = ROIValidation.loupeZoom(
            pixelWidth: w, displayed: CGRect(x: 0, y: 0, width: 200, height: 150), displayScale: 3)
        XCTAssertGreaterThan(narrow, wide)
    }

    /// It magnifies or leaves alone; it never shrinks what the operator is aiming at.
    func testTheLoupeNeverDeMagnifies() {
        XCTAssertGreaterThanOrEqual(
            ROIValidation.loupeZoom(
                pixelWidth: 100, displayed: CGRect(x: 0, y: 0, width: 400, height: 300),
                displayScale: 3),
            1.0)
    }

    /// A quarter-turned still is shown across the view's height, so that is the extent the ratio
    /// has to be computed against.
    func testTheLoupeMeasuresAcrossTheAxisTheWidthIsShownOn() {
        let portrait = CGRect(x: 0, y: 0, width: 300, height: 400)
        XCTAssertEqual(
            ROIValidation.loupeZoom(
                pixelWidth: w, displayed: portrait, orientation: .right, displayScale: 3),
            ROIValidation.loupeZoom(
                pixelWidth: w, displayed: CGRect(x: 0, y: 0, width: 400, height: 300),
                displayScale: 3))
    }

    /// AC3: precision must not depend on landing the tap first time.
    func testNudgeMovesAPointByWholeImagePixels() {
        let point = PixelPoint(x: 2000, y: 1500)
        XCTAssertEqual(
            ROIValidation.nudge(point, dx: -1, dy: 0, pixelWidth: w, pixelHeight: h),
            PixelPoint(x: 1999, y: 1500))
        XCTAssertEqual(
            ROIValidation.nudge(point, dx: 0, dy: 1, pixelWidth: w, pixelHeight: h),
            PixelPoint(x: 2000, y: 1501))
    }

    /// Nudging off the frame would record a coordinate outside the image the intrinsics describe.
    func testNudgeStaysInsideTheFrame() {
        XCTAssertEqual(
            ROIValidation.nudge(PixelPoint(x: 0, y: 0), dx: -1, dy: -1,
                                pixelWidth: w, pixelHeight: h),
            PixelPoint(x: 0, y: 0))
        XCTAssertEqual(
            ROIValidation.nudge(PixelPoint(x: w - 1, y: h - 1), dx: 1, dy: 1,
                                pixelWidth: w, pixelHeight: h),
            PixelPoint(x: w - 1, y: h - 1))
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

// MARK: - QA #197: the loupe magnified the wrong region, and nudge ignored orientation

extension ROIValidationTests {

    /// The point the operator is placing must be the point under the crosshair.
    ///
    /// It was not. `.frame(width:height:)` centres its content, and the offset was written for a
    /// top-left origin, so the loupe showed a fixed region near the middle of the picture wherever
    /// the finger went (QA B01). Asserted as a round trip so the test does not simply restate the
    /// arithmetic it is checking.
    func testLoupeShowsThePointBeingPlaced() {
        let displayed = CGRect(x: 12, y: 80, width: 366, height: 488)
        for zoom in [1.0, 1.19, 4.0] as [CGFloat] {
            for p in [CGPoint(x: 12, y: 80), CGPoint(x: 195, y: 324),
                      CGPoint(x: 378, y: 568), CGPoint(x: 100, y: 500)] {
                let offset = ROIValidation.loupeOffset(
                    at: p, displayed: displayed, zoom: zoom, windowSize: 120)
                let centre = ROIValidation.loupeCentre(
                    offset: offset, displayed: displayed, zoom: zoom, windowSize: 120)
                XCTAssertEqual(centre.x, p.x, accuracy: 0.001, "zoom \(zoom) at \(p)")
                XCTAssertEqual(centre.y, p.y, accuracy: 0.001, "zoom \(zoom) at \(p)")
            }
        }
    }

    /// A touch outside the image still magnifies inside it, rather than empty space.
    func testLoupeClampsToTheDisplayedImage() {
        let displayed = CGRect(x: 12, y: 80, width: 366, height: 488)
        let offset = ROIValidation.loupeOffset(
            at: CGPoint(x: -500, y: 9999), displayed: displayed, zoom: 2, windowSize: 120)
        let centre = ROIValidation.loupeCentre(
            offset: offset, displayed: displayed, zoom: 2, windowSize: 120)
        XCTAssertEqual(centre.x, displayed.minX, accuracy: 0.001)
        XCTAssertEqual(centre.y, displayed.maxY, accuracy: 0.001)
    }

    /// "Up" must move the marker up the SCREEN, in every orientation.
    ///
    /// The arrows are labelled in screen space and the record is in sensor space; on a
    /// portrait-held phone those are a quarter turn apart. Applying the screen delta straight to
    /// sensor coordinates moved the marker sideways on `.right`, which is the portrait capture
    /// orientation -- so 12 of 16 combinations were wrong and only `.up` was right, which a
    /// portrait-only app never produces (QA B02).
    func testNudgeMovesTheMarkerTheWayTheArrowPoints() {
        let w = 4032, h = 3024
        let start = PixelPoint(x: 2000, y: 1500)
        let displayed = CGRect(x: 0, y: 0, width: 300, height: 400)

        for orientation in [UIImage.Orientation.up, .right, .left, .down] {
            for (dx, dy) in [(-1, 0), (1, 0), (0, -1), (0, 1)] {
                let moved = ROIValidation.nudge(
                    start, dx: dx, dy: dy, orientation: orientation,
                    pixelWidth: w, pixelHeight: h)
                // Round-trip through the same mapping taps use: convert both points back to
                // screen space and check the SCREEN delta matches the arrow.
                let before = Self.screenPoint(start, displayed: displayed, orientation: orientation,
                                              pixelWidth: w, pixelHeight: h)
                let after = Self.screenPoint(moved, displayed: displayed, orientation: orientation,
                                             pixelWidth: w, pixelHeight: h)
                let sdx = after.x - before.x, sdy = after.y - before.y
                XCTAssertEqual(sdx.sign == .minus, dx < 0 && sdx != 0,
                               "\(orientation) dx=\(dx) moved screen x by \(sdx)")
                if dx != 0 { XCTAssertTrue(abs(sdx) > 0 && abs(sdy) < 0.001,
                                           "\(orientation) dx=\(dx) also moved y by \(sdy)") }
                if dy != 0 { XCTAssertTrue(abs(sdy) > 0 && abs(sdx) < 0.001,
                                           "\(orientation) dy=\(dy) also moved x by \(sdx)") }
                if dy < 0 { XCTAssertLessThan(sdy, 0, "\(orientation): up must move up") }
                if dy > 0 { XCTAssertGreaterThan(sdy, 0, "\(orientation): down must move down") }
                if dx < 0 { XCTAssertLessThan(sdx, 0, "\(orientation): left must move left") }
                if dx > 0 { XCTAssertGreaterThan(sdx, 0, "\(orientation): right must move right") }
            }
        }
    }

    /// Sensor pixel -> screen point, the inverse of `pixel(of:)`, for the assertion above.
    private static func screenPoint(
        _ p: PixelPoint, displayed: CGRect, orientation: UIImage.Orientation,
        pixelWidth: Int, pixelHeight: Int
    ) -> CGPoint {
        let fx = CGFloat(p.x) / CGFloat(pixelWidth)
        let fy = CGFloat(p.y) / CGFloat(pixelHeight)
        let u: CGFloat, v: CGFloat
        switch orientation {
        case .right, .rightMirrored: u = 1 - fy; v = fx
        case .left, .leftMirrored:   u = fy;     v = 1 - fx
        case .down, .downMirrored:   u = 1 - fx; v = 1 - fy
        default:                     u = fx;     v = fy
        }
        return CGPoint(x: displayed.minX + u * displayed.width,
                       y: displayed.minY + v * displayed.height)
    }
}
