import SwiftUI

/// Marking the six points Arm A measures from, on the still that was just taken.
///
/// Between the shutter and the record. A frame leaves here either with all six points or not at
/// all: a capture with four taps is not a partial measurement, it is an unmeasurable frame that
/// looks complete (TICK-028 AC5).
struct ROIReviewView: View {
    let image: UIImage
    let pixelWidth: Int
    let pixelHeight: Int
    let onConfirm: (ROITaps) -> Void
    let onDiscard: () -> Void

    @State private var marks: [ROITarget: PixelPoint] = [:]
    @State private var lastTouch: CGPoint?
    @Environment(\.displayScale) private var displayScale

    private var next: ROITarget? {
        ROITarget.allCases.first { marks[$0] == nil }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            GeometryReader { geo in
                let rect = ROIValidation.fittedRect(
                    pixelWidth: pixelWidth, pixelHeight: pixelHeight,
                    orientation: image.imageOrientation, in: geo.size)
                ZStack(alignment: .topLeading) {
                    Color.black
                    // Framed and positioned to `rect` explicitly rather than left to the stack's
                    // alignment: two assumptions about where the image sits disagreed once
                    // already, and taps were converted against a rect the image did not occupy.
                    //
                    // scaledToFit stays because resizable alone STRETCHES to the frame. The rect
                    // now carries the displayed aspect, so fitting inside it is exact rather than
                    // approximate -- and a mismatch shows as letterboxing instead of a silently
                    // squashed picture with silently wrong taps.
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFit()
                        .frame(width: rect.width, height: rect.height)
                        .position(x: rect.midX, y: rect.midY)
                    marksOverlay(in: rect)
                    // While a finger is down, magnify under it. Once the point is placed,
                    // KEEP magnifying it, centred on the mark being nudged.
                    //
                    // These used to be mutually exclusive: `lastTouch` was cleared the instant the
                    // point landed, which is the same instant the nudge pad appeared. So every
                    // nudge happened with no magnified view -- and one image pixel is 0.39 screen
                    // pixels on an iPhone 16, below what the display can render. Pressing an arrow
                    // changed nothing the operator could see except a number (QA B03), which is
                    // exactly the "precision depends on landing it first time" that AC3 exists to
                    // remove.
                    if let focus = lastTouch ?? nudgeFocusPoint(in: rect) {
                        Magnifier(
                            image: image, at: focus, displayed: rect,
                            zoom: ROIValidation.loupeZoom(
                                pixelWidth: pixelWidth, displayed: rect,
                                orientation: image.imageOrientation,
                                displayScale: displayScale))
                    }
                }
                .contentShape(Rectangle())
                .gesture(
                    DragGesture(minimumDistance: 0)
                        .onChanged { lastTouch = $0.location }
                        .onEnded { value in
                            place(value.location, in: rect)
                            lastTouch = nil
                        }
                )
            }
            footer
        }
        .background(.black)
    }

    private var header: some View {
        VStack(spacing: 4) {
            Text(next?.prompt ?? "All six points marked")
                .font(.headline)
            Text("\(marks.count) of \(ROITarget.allCases.count)")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(.thinMaterial)
    }

    @ViewBuilder
    private func marksOverlay(in rect: CGRect) -> some View {
        ForEach(ROITarget.allCases.filter { marks[$0] != nil }, id: \.self) { target in
            if let mark = marks[target] {
                // Sensor pixels turned forward into display space -- the inverse of what `place`
                // does. Drawing them with the untuned mapping would put every marker somewhere the
                // operator did not tap, on exactly the frames where it matters.
                let point = ROIValidation.displayPoint(
                    of: mark, in: rect, orientation: image.imageOrientation,
                    pixelWidth: pixelWidth, pixelHeight: pixelHeight)
                let x = point.x
                let y = point.y
                ZStack {
                    Circle().stroke(.yellow, lineWidth: 2).frame(width: 18, height: 18)
                    Circle().fill(.yellow).frame(width: 3, height: 3)
                    Text(target.shortLabel)
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.yellow)
                        .offset(x: 20)
                }
                .position(x: x, y: y)
                .allowsHitTesting(false)
            }
        }
    }

    /// Adjusts the most recently placed point by one image pixel.
    ///
    /// A finger under a loupe still cannot resolve a single pixel, and the tap error lands
    /// directly in a rise being judged against a quarter-inch bar (TICK-135 AC3).
    ///
    /// Where the loupe should sit while the nudge pad is up: on the point being nudged, so the
    /// operator can see the pixel move. `nil` once every point is placed and there is nothing
    /// left to adjust.
    private func nudgeFocusPoint(in rect: CGRect) -> CGPoint? {
        guard let target = ROITarget.allCases.last(where: { marks[$0] != nil }),
              let mark = marks[target] else { return nil }
        return ROIValidation.screenPoint(
            of: mark, displayed: rect, orientation: image.imageOrientation,
            pixelWidth: pixelWidth, pixelHeight: pixelHeight)
    }

    @ViewBuilder
    private var nudgePad: some View {
        if let target = ROITarget.allCases.last(where: { marks[$0] != nil }) {
            HStack(spacing: 10) {
                // The pixel coordinates, because AC4 asks for a measured standard deviation over
                // ten placements of one edge and an operator cannot record a number the app never
                // shows them. Monospaced so a column of ten readings is easy to compare.
                VStack(alignment: .leading, spacing: 1) {
                    Text(target.shortLabel).font(.caption.weight(.semibold))
                    Text("\(marks[target]!.x), \(marks[target]!.y)")
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)
                }
                .frame(minWidth: 76, alignment: .leading)
                .accessibilityLabel(
                    "\(target.shortLabel) at \(marks[target]!.x), \(marks[target]!.y)")
                ForEach([("chevron.left", -1, 0), ("chevron.right", 1, 0),
                         ("chevron.up", 0, -1), ("chevron.down", 0, 1)], id: \.0) { icon, dx, dy in
                    Button {
                        marks[target] = ROIValidation.nudge(
                            marks[target]!, dx: dx, dy: dy,
                            orientation: image.imageOrientation,
                            pixelWidth: pixelWidth, pixelHeight: pixelHeight)
                    } label: {
                        Image(systemName: icon).frame(width: 34, height: 30)
                    }
                    .buttonStyle(.bordered)
                    .accessibilityLabel("Nudge \(target.shortLabel) \(icon)")
                }
            }
            .padding(.vertical, 6)
        }
    }

    private var footer: some View {
        VStack(spacing: 4) {
            nudgePad
            controls
        }
        .padding()
        .background(.thinMaterial)
    }

    private var controls: some View {
        HStack {
            Button("Discard", role: .destructive, action: onDiscard)
            Spacer()
            Button("Undo") { undo() }
                .disabled(marks.isEmpty)
            Spacer()
            Button("Use frame") {
                if case .success(let taps) = ROIValidation.taps(from: marks) { onConfirm(taps) }
            }
            .buttonStyle(.borderedProminent)
            .disabled(next != nil)
        }
    }

    private func place(_ point: CGPoint, in rect: CGRect) {
        guard let target = next else { return }
        guard let pixel = ROIValidation.pixel(
            of: point, displayed: rect, orientation: image.imageOrientation,
            pixelWidth: pixelWidth, pixelHeight: pixelHeight) else { return }
        marks[target] = pixel
    }

    /// Removes the most recently prompted mark, so a misplaced tap is corrected rather than lived
    /// with. AC: "the operator can correct a tap before confirming".
    private func undo() {
        guard let last = ROITarget.allCases.last(where: { marks[$0] != nil }) else { return }
        marks[last] = nil
    }
}

/// A loupe over the finger.
///
/// Threshold edges are a few pixels of shadow on a 4032-wide still shown about 350 points wide --
/// roughly a tenth of the pixels. Without magnification the operator is placing a point they
/// cannot see, and the tap error goes straight into the measurement (TICK-135).
private struct Magnifier: View {
    let image: UIImage
    let at: CGPoint
    let displayed: CGRect
    /// Computed from the still and the screen so 1:1 holds on any device (TICK-135 AC1), rather
    /// than a constant that happened to clear it on the two phones to hand.
    let zoom: CGFloat

    private let size: CGFloat = 120

    var body: some View {
        // Still needed below, to place the loupe WINDOW away from the finger; the region it
        // magnifies is `loupeOffset`'s job.
        let clamped = CGPoint(
            x: min(max(at.x, displayed.minX), displayed.maxX),
            y: min(max(at.y, displayed.minY), displayed.maxY))
        ZStack {
            Image(uiImage: image)
                .resizable()
                .scaledToFit()
                .frame(width: displayed.width * zoom, height: displayed.height * zoom)
                .offset(ROIValidation.loupeOffset(
                    at: at, displayed: displayed, zoom: zoom, windowSize: size))
                // topLeading, not the default centre. `.frame(width:height:)` CENTRES its
                // content, so the offset above -- which positions the magnified still as if its
                // origin sat at the window's top-left -- was off by half the magnified image.
                // The loupe showed a fixed region near the picture's middle no matter where the
                // finger was, at the derived zoom and at the old 4x alike.
                .frame(width: size, height: size, alignment: .topLeading)
                .clipped()
            Path { p in
                p.move(to: CGPoint(x: size / 2, y: 0)); p.addLine(to: CGPoint(x: size / 2, y: size))
                p.move(to: CGPoint(x: 0, y: size / 2)); p.addLine(to: CGPoint(x: size, y: size / 2))
            }
            .stroke(.yellow.opacity(0.9), lineWidth: 1)
            .frame(width: size, height: size)
            Circle().stroke(.white, lineWidth: 2).frame(width: size, height: size)
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        // Above the finger, and out of the way when the finger is near the top.
        .position(x: clamped.x, y: clamped.y > displayed.minY + size ? clamped.y - size : clamped.y + size)
        .allowsHitTesting(false)
    }
}
