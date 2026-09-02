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
        pixelWidth: Int,
        pixelHeight: Int
    ) -> PixelPoint? {
        guard displayed.width > 0, displayed.height > 0, pixelWidth > 0, pixelHeight > 0 else {
            return nil
        }
        let fx = (point.x - displayed.minX) / displayed.width
        let fy = (point.y - displayed.minY) / displayed.height
        guard (0...1).contains(fx), (0...1).contains(fy) else { return nil }
        // Round rather than truncate: truncation biases every tap towards the top-left by up to a
        // pixel, which is a systematic error across the whole dataset rather than a random one.
        let x = min(pixelWidth - 1, max(0, Int((fx * CGFloat(pixelWidth)).rounded())))
        let y = min(pixelHeight - 1, max(0, Int((fy * CGFloat(pixelHeight)).rounded())))
        return PixelPoint(x: x, y: y)
    }

    /// The rect a `scaledToFit` image occupies inside a view of this size.
    static func fittedRect(pixelWidth: Int, pixelHeight: Int, in view: CGSize) -> CGRect {
        guard pixelWidth > 0, pixelHeight > 0, view.width > 0, view.height > 0 else { return .zero }
        let scale = min(view.width / CGFloat(pixelWidth), view.height / CGFloat(pixelHeight))
        let size = CGSize(width: CGFloat(pixelWidth) * scale, height: CGFloat(pixelHeight) * scale)
        return CGRect(
            x: (view.width - size.width) / 2,
            y: (view.height - size.height) / 2,
            width: size.width,
            height: size.height
        )
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
}
