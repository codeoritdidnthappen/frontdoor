import SwiftUI

/// Turns the approved library's SVG path data into a SwiftUI `Path`, verbatim.
///
/// Why a parser rather than an asset catalogue. The library's own PNG exports top out at 48 px,
/// and the pin ladder needs 24 pt through 64 pt — at 3× that is 192 px, so a raster is either
/// blurred or absent. Vector PDFs cannot be produced on the machine this was written on. And
/// hand-transcribing sixty path strings into `addCurve` calls is a transcription error waiting to
/// be shipped, invisible until somebody looks at a screen.
///
/// Holding the `d` strings verbatim removes all three problems at once. The shapes are exact at
/// every size, they take a colour token at the call site instead of baking one in, the diff is
/// readable, and `tests/test_ios_design_system.py` can compare every string in
/// ``EntryMapIcons`` against the SVG master committed under `docs/design/entrymap/svg/` and fail
/// if one character differs.
///
/// The grammar covered is the grammar those files use: `M L H V C S A Z` and their relative forms.
/// Anything else returns `nil` and draws nothing at all — a missing icon is loud, and a
/// half-parsed one is silent.
enum EntryMapPathParser {

    /// Parse SVG path data in its own user-space units. `nil` if the data uses anything unsupported.
    static func path(from data: String) -> Path? {
        var scanner = Scanner(Array(data))
        var path = Path()
        var current = CGPoint.zero
        var subpathStart = CGPoint.zero
        var previousControl: CGPoint?
        var previousCommand: Character = " "

        while let raw = scanner.nextCommand() {
            // An empty result means the coordinates repeat the previous command. A repeated
            // moveto is a lineto, per the SVG grammar; everything else simply repeats.
            var command = raw
            if command == "\0" {
                switch previousCommand {
                case "M": command = "L"
                case "m": command = "l"
                case " ": return nil
                default: command = previousCommand
                }
            }
            let relative = command.isLowercase
            let kind = Character(command.uppercased())

            // Everything the parser measures is `Double`; CGPoint is only how a point is stored.
            func point(_ x: Double, _ y: Double) -> CGPoint {
                relative
                    ? CGPoint(x: Double(current.x) + x, y: Double(current.y) + y)
                    : CGPoint(x: x, y: y)
            }

            switch kind {
            case "M":
                guard let x = scanner.nextNumber(), let y = scanner.nextNumber() else { return nil }
                current = point(x, y)
                subpathStart = current
                path.move(to: current)
                previousControl = nil
            case "L":
                guard let x = scanner.nextNumber(), let y = scanner.nextNumber() else { return nil }
                current = point(x, y)
                path.addLine(to: current)
                previousControl = nil
            case "H":
                guard let x = scanner.nextNumber() else { return nil }
                current = CGPoint(
                    x: relative ? Double(current.x) + x : x, y: Double(current.y))
                path.addLine(to: current)
                previousControl = nil
            case "V":
                guard let y = scanner.nextNumber() else { return nil }
                current = CGPoint(
                    x: Double(current.x), y: relative ? Double(current.y) + y : y)
                path.addLine(to: current)
                previousControl = nil
            case "C":
                guard let a = scanner.nextNumber(), let b = scanner.nextNumber(),
                      let c = scanner.nextNumber(), let d = scanner.nextNumber(),
                      let e = scanner.nextNumber(), let f = scanner.nextNumber() else { return nil }
                let control1 = point(a, b)
                let control2 = point(c, d)
                current = point(e, f)
                path.addCurve(to: current, control1: control1, control2: control2)
                previousControl = control2
            case "S":
                guard let c = scanner.nextNumber(), let d = scanner.nextNumber(),
                      let e = scanner.nextNumber(), let f = scanner.nextNumber() else { return nil }
                // The first control point is the reflection of the previous one, or the current
                // point when the previous command was not a curve.
                let control1 = previousControl.map {
                    CGPoint(x: 2 * current.x - $0.x, y: 2 * current.y - $0.y)
                } ?? current
                let control2 = point(c, d)
                current = point(e, f)
                path.addCurve(to: current, control1: control1, control2: control2)
                previousControl = control2
            case "A":
                guard let rx = scanner.nextNumber(), let ry = scanner.nextNumber(),
                      let rotation = scanner.nextNumber(),
                      let large = scanner.nextFlag(), let sweep = scanner.nextFlag(),
                      let x = scanner.nextNumber(), let y = scanner.nextNumber() else { return nil }
                let end = point(x, y)
                appendArc(
                    into: &path, from: current, to: end,
                    rx: rx, ry: ry, rotationDegrees: rotation,
                    largeArc: large, sweep: sweep)
                current = end
                previousControl = nil
            case "Z":
                path.closeSubpath()
                current = subpathStart
                previousControl = nil
            default:
                return nil
            }
            previousCommand = command
        }
        return path
    }

    /// Endpoint to centre parameterisation (SVG 1.1 F.6.5), then one cubic per quarter turn
    /// (F.6.2). The library uses arcs only for small rounded corners and two circle halves, so a
    /// quarter-turn split is well inside visual tolerance.
    private static func appendArc(
        into path: inout Path,
        from start: CGPoint,
        to end: CGPoint,
        rx rxIn: Double,
        ry ryIn: Double,
        rotationDegrees: Double,
        largeArc: Bool,
        sweep: Bool
    ) {
        guard rxIn != 0, ryIn != 0 else {
            path.addLine(to: end)
            return
        }
        var rx = abs(rxIn)
        var ry = abs(ryIn)
        let startX = Double(start.x)
        let startY = Double(start.y)
        let endX = Double(end.x)
        let endY = Double(end.y)
        let phi = rotationDegrees * .pi / 180
        let cosPhi = cos(phi)
        let sinPhi = sin(phi)
        let dx = (startX - endX) / 2
        let dy = (startY - endY) / 2
        let x1 = cosPhi * dx + sinPhi * dy
        let y1 = -sinPhi * dx + cosPhi * dy

        // F.6.6: grow the radii if they cannot span the chord.
        let lambda = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
        if lambda > 1 {
            let growth = lambda.squareRoot()
            rx *= growth
            ry *= growth
        }

        let numerator = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
        let denominator = rx * rx * y1 * y1 + ry * ry * x1 * x1
        var factor: Double = denominator == 0 ? 0 : max(0, numerator / denominator).squareRoot()
        if largeArc == sweep { factor = -factor }
        let cx1 = factor * rx * y1 / ry
        let cy1 = -factor * ry * x1 / rx
        let cx = cosPhi * cx1 - sinPhi * cy1 + (startX + endX) / 2
        let cy = sinPhi * cx1 + cosPhi * cy1 + (startY + endY) / 2

        func angle(_ ux: Double, _ uy: Double, _ vx: Double, _ vy: Double) -> Double {
            let magnitude = ((ux * ux + uy * uy) * (vx * vx + vy * vy)).squareRoot()
            guard magnitude != 0 else { return 0 }
            let value = acos(min(1, max(-1, (ux * vx + uy * vy) / magnitude)))
            return ux * vy - uy * vx < 0 ? -value : value
        }

        let startVectorX = (x1 - cx1) / rx
        let startVectorY = (y1 - cy1) / ry
        let endVectorX = (-x1 - cx1) / rx
        let endVectorY = (-y1 - cy1) / ry
        let theta = angle(1, 0, startVectorX, startVectorY)
        var delta = angle(startVectorX, startVectorY, endVectorX, endVectorY)
        if !sweep, delta > 0 {
            delta -= 2 * .pi
        } else if sweep, delta < 0 {
            delta += 2 * .pi
        }

        let segments = max(1, Int((abs(delta) / (.pi / 2)).rounded(.up)))
        let step = delta / Double(segments)
        let handle = 4.0 / 3.0 * tan(step / 4)

        func onArc(_ cosine: Double, _ sine: Double) -> (x: Double, y: Double) {
            (cx + rx * cosine * cosPhi - ry * sine * sinPhi,
             cy + rx * cosine * sinPhi + ry * sine * cosPhi)
        }
        func tangent(_ cosine: Double, _ sine: Double) -> (x: Double, y: Double) {
            (-rx * sine * cosPhi - ry * cosine * sinPhi,
             -rx * sine * sinPhi + ry * cosine * cosPhi)
        }

        for index in 0..<segments {
            let a0 = theta + Double(index) * step
            let a1 = a0 + step
            let p0 = onArc(cos(a0), sin(a0))
            let p1 = onArc(cos(a1), sin(a1))
            let t0 = tangent(cos(a0), sin(a0))
            let t1 = tangent(cos(a1), sin(a1))
            path.addCurve(
                to: CGPoint(x: p1.x, y: p1.y),
                control1: CGPoint(x: p0.x + handle * t0.x, y: p0.y + handle * t0.y),
                control2: CGPoint(x: p1.x - handle * t1.x, y: p1.y - handle * t1.y))
        }
    }

    /// A cursor over path data. Separators in SVG path data are optional, so everything here has
    /// to cope with `h.01`, `M5 8h22M5 16h22` and `a2 2 0 0 1 2-2` alike.
    private struct Scanner {
        private let characters: [Character]
        private var index = 0

        init(_ characters: [Character]) { self.characters = characters }

        private mutating func skipSeparators() {
            while index < characters.count,
                  characters[index] == " " || characters[index] == ","
                    || characters[index] == "\n" || characters[index] == "\t"
                    || characters[index] == "\r" {
                index += 1
            }
        }

        /// The next command letter, `"\0"` when coordinates follow without one, or `nil` at the end.
        mutating func nextCommand() -> Character? {
            skipSeparators()
            guard index < characters.count else { return nil }
            if characters[index].isLetter {
                defer { index += 1 }
                return characters[index]
            }
            return "\0"
        }

        mutating func nextNumber() -> Double? {
            skipSeparators()
            let start = index
            if index < characters.count, characters[index] == "-" || characters[index] == "+" {
                index += 1
            }
            while index < characters.count, characters[index].isNumber { index += 1 }
            if index < characters.count, characters[index] == "." {
                index += 1
                while index < characters.count, characters[index].isNumber { index += 1 }
            }
            if index < characters.count, characters[index] == "e" || characters[index] == "E" {
                let mark = index
                index += 1
                if index < characters.count, characters[index] == "-" || characters[index] == "+" {
                    index += 1
                }
                if index < characters.count, characters[index].isNumber {
                    while index < characters.count, characters[index].isNumber { index += 1 }
                } else {
                    index = mark
                }
            }
            guard index > start else { return nil }
            return Double(String(characters[start..<index]))
        }

        /// Arc flags are single characters and may be written with no separator at all.
        mutating func nextFlag() -> Bool? {
            skipSeparators()
            guard index < characters.count else { return nil }
            switch characters[index] {
            case "0": index += 1; return false
            case "1": index += 1; return true
            default: return nil
            }
        }
    }
}

/// One drawable element of an approved SVG, in the master's own units.
///
/// `<path>`, `<circle>` and `<rect>` are the only three elements the library's icons and pins use,
/// and each is kept in the form the master writes it — a circle stays a circle rather than being
/// rewritten as four arcs — so `tests/test_ios_design_system.py` can compare a glyph here against
/// the attributes in the SVG file directly.
struct EntryMapGlyph {
    enum Form {
        case path(String)
        case circle(x: Double, y: Double, radius: Double)
        case rect(x: Double, y: Double, width: Double, height: Double, radius: Double)
    }

    let form: Form
    /// Dash pattern in master units, empty for a solid line. Scaled with the glyph.
    let dash: [CGFloat]

    static func path(_ commands: String, dash: [CGFloat] = []) -> EntryMapGlyph {
        EntryMapGlyph(form: .path(commands), dash: dash)
    }

    static func circle(
        x: Double, y: Double, radius: Double, dash: [CGFloat] = []
    ) -> EntryMapGlyph {
        EntryMapGlyph(form: .circle(x: x, y: y, radius: radius), dash: dash)
    }

    static func rect(
        x: Double, y: Double, width: Double, height: Double, radius: Double,
        dash: [CGFloat] = []
    ) -> EntryMapGlyph {
        EntryMapGlyph(
            form: .rect(x: x, y: y, width: width, height: height, radius: radius), dash: dash)
    }
}

/// One glyph, drawn to fill a rect while keeping the master's aspect ratio.
struct EntryMapVectorShape: Shape {
    let glyph: EntryMapGlyph
    /// The master's viewBox.
    let viewBox: CGSize

    func path(in rect: CGRect) -> Path {
        var unit = Path()
        switch glyph.form {
        case .path(let commands):
            guard let parsed = EntryMapPathParser.path(from: commands) else { return Path() }
            unit = parsed
        case .circle(let x, let y, let radius):
            unit.addEllipse(
                in: CGRect(x: x - radius, y: y - radius, width: radius * 2, height: radius * 2))
        case .rect(let x, let y, let width, let height, let radius):
            unit.addRoundedRect(
                in: CGRect(x: x, y: y, width: width, height: height),
                cornerSize: CGSize(width: radius, height: radius))
        }
        let scale = Self.scale(fitting: viewBox, in: rect)
        let offsetX = rect.minX + (rect.width - viewBox.width * scale) / 2
        let offsetY = rect.minY + (rect.height - viewBox.height * scale) / 2
        return unit.applying(
            CGAffineTransform(translationX: offsetX, y: offsetY).scaledBy(x: scale, y: scale))
    }

    /// The factor a stroke width or dash pattern in master units must be multiplied by.
    static func scale(fitting viewBox: CGSize, in rect: CGRect) -> CGFloat {
        min(rect.width / viewBox.width, rect.height / viewBox.height)
    }
}
