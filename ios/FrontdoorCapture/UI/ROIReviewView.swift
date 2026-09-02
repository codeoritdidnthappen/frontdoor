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

    private var next: ROITarget? {
        ROITarget.allCases.first { marks[$0] == nil }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            GeometryReader { geo in
                let rect = ROIValidation.fittedRect(
                    pixelWidth: pixelWidth, pixelHeight: pixelHeight, in: geo.size)
                ZStack(alignment: .topLeading) {
                    Color.black
                    // Framed and positioned to `rect` explicitly rather than left to scaledToFit
                    // inside the stack. The stack's alignment and fittedRect's centring are two
                    // separate assumptions about where the image sits, and when they disagreed
                    // taps were mapped against a rect the image did not occupy -- silently, since
                    // both halves are individually correct.
                    Image(uiImage: image)
                        .resizable()
                        .frame(width: rect.width, height: rect.height)
                        .position(x: rect.midX, y: rect.midY)
                    marksOverlay(in: rect)
                    if let lastTouch, next != nil {
                        Magnifier(image: image, at: lastTouch, displayed: rect)
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
                let x = rect.minX + CGFloat(mark.x) / CGFloat(pixelWidth) * rect.width
                let y = rect.minY + CGFloat(mark.y) / CGFloat(pixelHeight) * rect.height
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

    private var footer: some View {
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
        .padding()
        .background(.thinMaterial)
    }

    private func place(_ point: CGPoint, in rect: CGRect) {
        guard let target = next else { return }
        guard let pixel = ROIValidation.pixel(
            of: point, displayed: rect,
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

    private let size: CGFloat = 120
    private let zoom: CGFloat = 4

    var body: some View {
        let clamped = CGPoint(
            x: min(max(at.x, displayed.minX), displayed.maxX),
            y: min(max(at.y, displayed.minY), displayed.maxY))
        ZStack {
            Image(uiImage: image)
                .resizable()
                .scaledToFit()
                .frame(width: displayed.width * zoom, height: displayed.height * zoom)
                .offset(
                    x: -(clamped.x - displayed.minX) * zoom + size / 2,
                    y: -(clamped.y - displayed.minY) * zoom + size / 2)
                .frame(width: size, height: size)
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
