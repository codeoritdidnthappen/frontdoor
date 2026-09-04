import Foundation

/// The view set from `docs/capture-protocol.md`: six named views of one entrance (#289).
///
/// The app used to know only how many photos an entrance had. An operator with six head-on shots
/// and an operator with a proper view set looked identical to it, which is the gap #4's AC5 was
/// about: the protocol prescribes the set, and the instrument had no notion of it.
///
/// The names and their order are the document's, and a pytest source guard fails if the two ever
/// disagree — the app cannot read a markdown file at the doorstep, so the guard is what makes the
/// document the source of truth rather than a copy of it.
///
/// **Coaching, not a gate.** Nothing here refuses a capture, and nothing marks a shot invalid for
/// filling a slot that is already filled. The protocol is guidance — a seventh angle that shows
/// something the set does not is worth having, and an instrument that refused it would cost
/// captures (#289).
enum ViewSlot: String, CaseIterable, Codable, Equatable {
    case headOn = "head_on"
    case obliqueLeft = "oblique_left"
    case obliqueRight = "oblique_right"
    case near
    case far
    case hardware

    /// Exactly the document's name for this view, so the chip in the viewfinder and the checklist
    /// in the operator's hand say the same words.
    var label: String {
        switch self {
        case .headOn: return "Head-on"
        case .obliqueLeft: return "Oblique, left"
        case .obliqueRight: return "Oblique, right"
        case .near: return "Near, ~1.5 m"
        case .far: return "Far, ~3-4 m"
        case .hardware: return "Hardware close-up"
        }
    }

    /// What to do to take it, in one line, for someone holding the phone up at a doorway.
    var coaching: String {
        switch self {
        case .headOn:
            return "Square to the entrance, doorway centred."
        case .obliqueLeft:
            return "Angled from the left, entrance still fully in frame."
        case .obliqueRight:
            return "Angled from the right, entrance still fully in frame."
        case .near:
            return "Close enough that hardware and surface detail start to read."
        case .far:
            // The pilot finding, not decoration: with no view covering the ground plane the
            // ramp/bevel and handrail criteria come back "not visible" or flip between views,
            // and the engine is then answering about framing rather than about the entrance.
            return "Far enough to show the whole approach path — and the ground at the threshold."
        case .hardware:
            return "The handle, lock, lever or push plate, filling the frame."
        }
    }
}

/// How much of one entrance's view set has been captured.
struct ViewSetCoverage: Equatable {
    /// Which slots have at least one photo. A slot shot twice counts once: this answers "is this
    /// view covered", not "how many photos exist" — `EntranceTally` answers that.
    let captured: Set<ViewSlot>

    var missing: [ViewSlot] { ViewSlot.allCases.filter { !captured.contains($0) } }

    /// What the protocol makes of this coverage.
    ///
    /// Five is not silently treated as done. The document allows five "if one genuinely cannot be
    /// captured — note which one and why in the entrance record", and only the operator standing
    /// there knows whether that is the case. So the app reports the position and says what the
    /// protocol asks; it does not decide on their behalf.
    enum State: Equatable {
        case complete
        /// Five of six. The named slot is the one missing.
        case oneShort(ViewSlot)
        case incomplete([ViewSlot])
    }

    var state: State {
        switch missing.count {
        case 0: return .complete
        case 1: return .oneShort(missing[0])
        default: return .incomplete(missing)
        }
    }

    /// A line for the viewfinder: short enough for a capsule, exact enough to act on.
    var summary: String {
        switch state {
        case .complete:
            return "all 6 views"
        case .oneShort(let slot):
            return "5 of 6 · missing \(slot.label)"
        case .incomplete(let missing):
            return "\(ViewSlot.allCases.count - missing.count) of 6 · next \(missing[0].label)"
        }
    }

    /// The slot to offer for the next shot: the first one not yet captured, or the first of the
    /// set when none is outstanding. Never nil — the operator can always take another photo, and
    /// an extra angle of a covered view is a capture the protocol allows.
    var suggested: ViewSlot { missing.first ?? .headOn }
}
