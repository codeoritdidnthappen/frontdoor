import SwiftUI

/// The named durations and curves, and one rule about how they may be used.
///
/// Source of truth: `docs/design/entrymap/interaction-motion.json`, pinned by
/// `tests/test_ios_design_system.py`.
///
/// **Reduce Motion here means no motion, not less motion.**
///
/// The web build got this wrong in a way worth naming, because the shape of the mistake is easy to
/// repeat. It scaled every duration down under Reduce Motion and left the delays alone. That was
/// survivable until a sheet's visibility was guarded by one of those delays: the delay stayed at
/// full length while everything around it went instant, the sheet's content existed before it was
/// on screen, and focus fell into every sheet in the app.
///
/// Two rules come out of that, and both are enforced below rather than remembered:
///
/// 1. ``animation(_:reduceMotion:)`` returns `nil` under Reduce Motion for anything that moves.
///    `nil` is SwiftUI's genuine instant: the value changes and the final state is what draws.
///    Nothing is shortened, so nothing can be shortened inconsistently.
/// 2. There is exactly one function in this layer that produces a delay — ``stagger(index:)`` —
///    and it may only space out elements that are *already present and already visible*. Presence,
///    visibility, focusability and interactivity are state, and state is set by the event that
///    caused it. Never by a timer, and never by an animation completing.
enum EntryMapMotion {

    // MARK: - Curves

    enum Curve {
        /// `cubic-bezier(.2,.75,.25,1)` — screen transitions and ordinary feedback.
        case standard
        /// `cubic-bezier(.16,1,.3,1)` — things arriving and settling.
        case decelerate
        /// `cubic-bezier(.22,.9,.28,1.08)` — sheet snapping, with a small overshoot.
        case sheetSpring
        /// `cubic-bezier(.2,.9,.25,1.2)` — the pin drop, with a larger overshoot.
        case pinSpring

        fileprivate var points: (Double, Double, Double, Double) {
            switch self {
            case .standard: return (0.2, 0.75, 0.25, 1)
            case .decelerate: return (0.16, 1, 0.3, 1)
            case .sheetSpring: return (0.22, 0.9, 0.28, 1.08)
            case .pinSpring: return (0.2, 0.9, 0.25, 1.2)
            }
        }
    }

    // MARK: - Steps

    /// What happens under Reduce Motion.
    enum ReducedBehaviour {
        /// The final state, immediately. Anything that moves, scales, rotates or ripples.
        case instant
        /// An opacity-only crossfade, capped at the spec's 80 ms. Only for changes that are
        /// already nothing but a fade, where an abrupt swap would read as a glitch.
        case crossfade
    }

    /// Every named duration in the interaction tokens that describes a piece of motion.
    enum Step {
        case instant
        case shutter
        case press
        case focus
        case tabSwitch
        case checkDraw
        case toastEnter
        case receiptExpand
        case screenTransition
        case sheetSnap
        case mapCamera
        case pinDrop

        /// The token value, in milliseconds.
        var milliseconds: Int {
            switch self {
            case .instant: return 0
            case .shutter: return 90
            case .press: return 100
            case .focus: return 120
            case .tabSwitch: return 180
            case .checkDraw: return 180
            case .toastEnter: return 220
            case .receiptExpand: return 240
            case .screenTransition: return 260
            case .sheetSnap: return 320
            case .mapCamera: return 450
            case .pinDrop: return 620
            }
        }

        var seconds: TimeInterval { TimeInterval(milliseconds) / 1000 }

        var curve: Curve {
            switch self {
            case .instant, .shutter, .press, .focus, .tabSwitch, .screenTransition:
                return .standard
            case .checkDraw, .toastEnter, .receiptExpand, .mapCamera:
                return .decelerate
            case .sheetSnap:
                return .sheetSpring
            case .pinDrop:
                return .pinSpring
            }
        }

        var reducedBehaviour: ReducedBehaviour {
            switch self {
            // Peer and hierarchical navigation are the two the spec keeps as crossfades: "screen
            // transitions become instant crossfades no longer than 80 ms".
            case .tabSwitch, .screenTransition:
                return .crossfade
            // Everything else moves, scales or draws, so under Reduce Motion it simply is.
            case .instant, .shutter, .press, .focus, .checkDraw, .toastEnter, .receiptExpand,
                 .sheetSnap, .mapCamera, .pinDrop:
                return .instant
            }
        }
    }

    /// The cap the spec puts on a reduced crossfade.
    static let reducedCrossfade: TimeInterval = 0.080

    // MARK: - Process budgets
    //
    // Not motion. The live scan takes as long as the work takes, and Reduce Motion removes the
    // sweep and the bounce around it without shortening the work or the checklist.

    /// About seven and a half seconds, end to end.
    static let scanTargetDuration: TimeInterval = 7.600
    /// The ceiling. Past this the scan has failed to be a seven-second experience.
    static let scanMaximumDuration: TimeInterval = 8.000

    // MARK: - Building an animation

    /// The animation for a step, or `nil` when the reader has asked for less motion.
    ///
    /// Pass the result straight to `withAnimation(_:)` or `.animation(_:value:)`; both take an
    /// optional and treat `nil` as "apply the change now".
    static func animation(_ step: Step, reduceMotion: Bool) -> Animation? {
        guard step.milliseconds > 0 else { return nil }
        if reduceMotion {
            switch step.reducedBehaviour {
            case .instant:
                return nil
            case .crossfade:
                return .linear(duration: min(reducedCrossfade, step.seconds))
            }
        }
        let (x1, y1, x2, y2) = step.curve.points
        return .timingCurve(x1, y1, x2, y2, duration: step.seconds)
    }

    /// A control returning to 100% after a press: "Return to 100% with a soft spring", 180 ms.
    ///
    /// Stated here rather than in ``Step`` because the token file carries 180 ms twice — as
    /// `tabSwitch` and as `checkDraw` — and names neither of them for this. Borrowing one of those
    /// would put a token in a place its own file never put it.
    static func releaseAnimation(reduceMotion: Bool) -> Animation? {
        guard !reduceMotion else { return nil }
        let (x1, y1, x2, y2) = Curve.decelerate.points
        return .timingCurve(x1, y1, x2, y2, duration: 0.180)
    }

    /// The only delay this layer produces.
    ///
    /// Feature chips enter 60 ms apart and confidence dots fill 70 ms apart. Both are decoration on
    /// top of elements that are **already inserted, already laid out, already focusable and already
    /// readable by VoiceOver** — the stagger only spaces out how they animate in. Never reach for
    /// this to decide when something exists, becomes visible, or becomes tappable. That is the
    /// mistake in this file's opening note, and it is the reason there is one delay here and not
    /// several.
    ///
    /// Returns 0 under Reduce Motion, so a reduced run has no timing to get out of step with.
    static func stagger(index: Int, step: TimeInterval = 0.060, reduceMotion: Bool) -> TimeInterval {
        guard !reduceMotion, index > 0 else { return 0 }
        return TimeInterval(index) * step
    }
}

extension View {
    /// Animate `value` with a named step, honouring the reader's Reduce Motion setting.
    func entryMapAnimation<V: Equatable>(_ step: EntryMapMotion.Step, value: V) -> some View {
        modifier(EntryMapAnimationModifier(step: step, value: value))
    }
}

private struct EntryMapAnimationModifier<V: Equatable>: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let step: EntryMapMotion.Step
    let value: V

    func body(content: Content) -> some View {
        content.animation(
            EntryMapMotion.animation(step, reduceMotion: reduceMotion), value: value)
    }
}
