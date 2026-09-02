import CoreGraphics
import Foundation
import UIKit

/// The six points Arm A measures from: the two threshold edges, and the four corners of the
/// reference card that give the scene its scale (TICK-026).
///
/// Stored as integer pixel coordinates in the FULL-RESOLUTION image's own coordinate space, never
/// in view coordinates. A still is displayed at a fraction of its size, so a tap recorded where
/// the finger landed on screen is out by that factor -- and the result is a measurement that is
/// wrong by a constant nobody can see afterwards, on every capture, in the same direction.
struct ROITaps: Equatable {
    var thresholdTop: PixelPoint
    var thresholdBottom: PixelPoint
    /// Exactly four, in the winding order `CardCorner.allCases` declares. The homography needs the
    /// correspondence to be known rather than guessed (TICK-043).
    var cardCorners: [PixelPoint]
}

struct PixelPoint: Equatable {
    var x: Int
    var y: Int
}

/// What the operator is being asked for, in the order they are asked for it.
///
/// The order is the contract: it is what lets four unlabelled corner taps become a correspondence
/// the homography can use without inferring which corner is which.
enum ROITarget: Int, CaseIterable {
    case thresholdTop
    case thresholdBottom
    case cardTopLeft
    case cardTopRight
    case cardBottomRight
    case cardBottomLeft

    var prompt: String {
        switch self {
        case .thresholdTop: return "Tap the top edge of the threshold"
        case .thresholdBottom: return "Tap the bottom edge of the threshold"
        case .cardTopLeft: return "Tap the card's top-left corner"
        case .cardTopRight: return "Tap the card's top-right corner"
        case .cardBottomRight: return "Tap the card's bottom-right corner"
        case .cardBottomLeft: return "Tap the card's bottom-left corner"
        }
    }

    var shortLabel: String {
        switch self {
        case .thresholdTop: return "Top"
        case .thresholdBottom: return "Bottom"
        case .cardTopLeft: return "TL"
        case .cardTopRight: return "TR"
        case .cardBottomRight: return "BR"
        case .cardBottomLeft: return "BL"
        }
    }
}

/// Card corners in image space, clockwise from the top-left as the operator sees them.
///
/// Clockwise-from-top-left is written down here and in ARCHITECTURE rather than left to whoever
/// reads the array later: the four points are indistinguishable once they are numbers, and a
/// homography fitted to the wrong correspondence produces a plausible answer rather than an error.
enum CardCorner: Int, CaseIterable {
    case topLeft, topRight, bottomRight, bottomLeft
}

enum ROIRejected: Error, Equatable {
    case incomplete(collected: Int)
    case offImage(ROITarget)

    var message: String {
        switch self {
        case .incomplete(let collected):
            return """
            \(collected) of \(ROITarget.allCases.count) points marked. All six are needed: both \
            threshold edges and all four card corners. Nothing was recorded.
            """
        case .offImage(let target):
            return "The \(target.shortLabel) point landed outside the image. Tap it again."
        }
    }
}

enum ROIValidation {

    /// Turn a point in the displayed image's view coordinates into a pixel in the full-resolution
    /// image.
    ///
    /// `displayed` is the rect the image actually occupies inside the view, which is not the view:
    /// `scaledToFit` letterboxes, and the offset is exactly the error this converts away. Returns
    /// nil for a tap in the letterbox rather than clamping it to an edge -- a clamped tap is a
    /// wrong measurement that looks like a deliberate one.
    static func pixel(
        of point: CGPoint,
        displayed: CGRect,
        orientation: UIImage.Orientation = .up,
        pixelWidth: Int,
        pixelHeight: Int
    ) -> PixelPoint? {
        guard displayed.width > 0, displayed.height > 0, pixelWidth > 0, pixelHeight > 0 else {
            return nil
        }
        let u = (point.x - displayed.minX) / displayed.width
        let v = (point.y - displayed.minY) / displayed.height
        guard (0...1).contains(u), (0...1).contains(v) else { return nil }
        // Back out of the display turn into sensor space. `.right` is the portrait-held capture:
        // the buffer is rotated a quarter turn clockwise to show upright, so the display's top-left
        // is the sensor's bottom-left.
        let fx: CGFloat
        let fy: CGFloat
        switch orientation {
        case .right, .rightMirrored:
            fx = v
            fy = 1 - u
        case .left, .leftMirrored:
            fx = 1 - v
            fy = u
        case .down, .downMirrored:
            fx = 1 - u
            fy = 1 - v
        default:
            fx = u
            fy = v
        }
        // Round rather than truncate: truncation biases every tap towards the top-left by up to a
        // pixel, which is a systematic error across the whole dataset rather than a random one.
        let x = min(pixelWidth - 1, max(0, Int((fx * CGFloat(pixelWidth)).rounded())))
        let y = min(pixelHeight - 1, max(0, Int((fy * CGFloat(pixelHeight)).rounded())))
        return PixelPoint(x: x, y: y)
    }

    /// Whether an orientation puts the image on screen turned a quarter turn from its pixels.
    ///
    /// A still is landscape sensor pixels carrying an EXIF orientation, and on a portrait-held
    /// phone it displays upright -- so what the operator sees is a quarter turn from the buffer
    /// the intrinsics describe. Everything recorded stays in SENSOR space, because that is the
    /// frame `intrinsicMatrixReferenceDimensions` is expressed in; only the display is turned.
    static func isQuarterTurned(_ orientation: UIImage.Orientation) -> Bool {
        switch orientation {
        case .left, .leftMirrored, .right, .rightMirrored: return true
        default: return false
        }
    }

    /// The rect a `scaledToFit` image occupies inside a view of this size.
    ///
    /// Takes the DISPLAYED shape, which is the sensor's swapped when the image is quarter-turned.
    /// Computing it from the sensor dimensions instead fits a landscape rect around a portrait
    /// image: the picture is stretched to fill it, and every tap converts against a rectangle the
    /// image does not occupy.
    static func fittedRect(
        pixelWidth: Int, pixelHeight: Int,
        orientation: UIImage.Orientation = .up,
        in view: CGSize
    ) -> CGRect {
        let turned = isQuarterTurned(orientation)
        let displayedW = turned ? pixelHeight : pixelWidth
        let displayedH = turned ? pixelWidth : pixelHeight
        guard displayedW > 0, displayedH > 0, view.width > 0, view.height > 0 else { return .zero }
        let scale = min(view.width / CGFloat(displayedW), view.height / CGFloat(displayedH))
        let size = CGSize(width: CGFloat(displayedW) * scale, height: CGFloat(displayedH) * scale)
        return CGRect(
            x: (view.width - size.width) / 2,
            y: (view.height - size.height) / 2,
            width: size.width,
            height: size.height
        )
    }

    /// Magnification that puts one image pixel on at least one screen pixel (TICK-135 AC1).
    ///
    /// Derived rather than chosen. A 4032-wide still fitted to ~400 points is about ten image
    /// pixels per point, so a bare tap places a point the operator cannot see -- and the tap error
    /// goes straight into the rise, which is being measured against a quarter-inch bar. The old
    /// fixed 4x happened to clear 1:1 on these phones and would not on a wider screen or a larger
    /// sensor; this cannot drift, because it is computed from both.
    ///
    /// Floored at 1 so the loupe never shrinks the image, and capped so a pathological ratio
    /// cannot magnify to the point of showing nothing but one flat pixel.
    static func loupeZoom(
        pixelWidth: Int,
        displayed: CGRect,
        orientation: UIImage.Orientation = .up,
        displayScale: CGFloat
    ) -> CGFloat {
        // Across the axis the sensor's width is actually shown on, which the quarter turn swaps.
        let shownAcross = isQuarterTurned(orientation) ? displayed.height : displayed.width
        guard pixelWidth > 0, shownAcross > 0, displayScale > 0 else { return 1 }
        let needed = CGFloat(pixelWidth) / (shownAcross * displayScale)
        return min(max(needed, 1), 12)
    }

    /// Move a placed point by whole image pixels, staying inside the frame.
    ///
    /// AC3: precision must not depend on landing the tap first time. A finger cannot reliably
    /// resolve one image pixel even under the loupe, so the last placement is adjustable before it
    /// is committed.
    static func nudge(
        _ point: PixelPoint,
        dx: Int,
        dy: Int,
        pixelWidth: Int,
        pixelHeight: Int
    ) -> PixelPoint {
        PixelPoint(
            x: min(max(point.x + dx, 0), max(pixelWidth - 1, 0)),
            y: min(max(point.y + dy, 0), max(pixelHeight - 1, 0)))
    }

    /// Assemble the six collected points, in ROITarget order, into a record.
    static func taps(from marks: [ROITarget: PixelPoint]) -> Result<ROITaps, ROIRejected> {
        // No separate count check: every one of the six is looked up by name below, so a count
        // guard could not reject anything these do not. Mutation-testing it proved exactly that.
        let corners: [ROITarget] = [.cardTopLeft, .cardTopRight, .cardBottomRight, .cardBottomLeft]
        let collected = corners.compactMap { marks[$0] }
        guard let top = marks[.thresholdTop],
              let bottom = marks[.thresholdBottom],
              collected.count == CardCorner.allCases.count else {
            return .failure(.incomplete(collected: marks.count))
        }
        return .success(ROITaps(
            thresholdTop: top, thresholdBottom: bottom, cardCorners: collected))
    }
}

/// A validated frame waiting for its ROI points. Holds the still only until the operator confirms
/// or discards it; nothing here is a capture yet.
struct PendingReview: Identifiable {
    let id = UUID()
    var record: CaptureRecord
    var image: UIImage
    /// The bytes that will be written and hashed, held from the moment the camera produced
    /// them. `image` is for the screen only.
    var imageData: Data
    var depthBytes: Data?
}

extension ROIValidation {
    /// Where a recorded sensor pixel lands on screen -- the exact inverse of `pixel(of:...)`.
    ///
    /// Marks are stored in sensor space, so drawing them needs the turn applied forward. Doing it
    /// by hand in the view is how the two directions drift apart.
    static func displayPoint(
        of pixel: PixelPoint,
        in displayed: CGRect,
        orientation: UIImage.Orientation = .up,
        pixelWidth: Int,
        pixelHeight: Int
    ) -> CGPoint {
        guard pixelWidth > 0, pixelHeight > 0 else { return .zero }
        let fx = CGFloat(pixel.x) / CGFloat(pixelWidth)
        let fy = CGFloat(pixel.y) / CGFloat(pixelHeight)
        let u: CGFloat
        let v: CGFloat
        switch orientation {
        case .right, .rightMirrored:
            u = 1 - fy
            v = fx
        case .left, .leftMirrored:
            u = fy
            v = 1 - fx
        case .down, .downMirrored:
            u = 1 - fx
            v = 1 - fy
        default:
            u = fx
            v = fy
        }
        return CGPoint(x: displayed.minX + u * displayed.width,
                       y: displayed.minY + v * displayed.height)
    }
}
