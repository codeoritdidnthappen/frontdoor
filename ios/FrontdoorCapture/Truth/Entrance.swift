import Foundation

/// Ground truth and the conditions it was measured under, entered in the app at the entrance
/// (D-018). Nothing is reconciled against filenames afterwards, which is the step where datasets
/// rot: the caliper reading is bound to the capture at the shutter press or the capture does not
/// happen.
///
/// Capture angle is deliberately absent. It is derived from the recovered plane pose (TICK-044),
/// which is what makes the error-versus-angle curve a measurement rather than an operator's
/// estimate. There is no field for it here and there must not be one.

/// One entrance, and the caliper reading that is true of every capture of it.
struct Entrance: Equatable {
    /// Canonical form: `E-` and exactly three digits. Same rule as
    /// `frontdoor.split.canonical_entrance_id`, so the app and the library cannot disagree about
    /// which string gets hashed into the split.
    let id: String
    /// Threshold rise in inches, read from the caliper. The sidecar's `ground_truth.rise_in`.
    let riseInches: Double
    /// The sidecar's `ground_truth.instrument`, required by the schema and recorded per entrance
    /// because a reading is only as good as what it was taken with.
    let instrument: String
    /// Assigned once, when the entrance is created (TICK-025, D-023), and carried so re-entering
    /// an existing ID reuses it rather than re-rolling it. Never surfaced to the operator.
    let split: Split
}

/// The stratification variables the error budget is reported against (PRD section 6). Fixed
/// vocabularies rather than free text, so stratification does not have to clean up strings.
struct ConditionTags: Equatable {
    /// Metres from the lens to the threshold.
    ///
    /// **2.5 m** is the cap, revised from 3 m by TICK-233 (#136) after the Arm A error budget
    /// (`docs/rise-error-vs-angle.md`) found tap precision, not obliquity, to be the binding term.
    /// At 3 m the per-tap budget is 4.12 px against TICK-232's 5 px target; at 2.5 m it is 4.95 px.
    ///
    /// NOT ENFORCED HERE, and deliberately not added blind: the sidecar schema puts no upper bound
    /// on `distance_m`, and the 2026-09-01 pivot's 5-6-view protocol asks for a "far, ~3-4 m" shot
    /// to show the approach path -- a screening view, not a rise measurement. Whether both kinds of
    /// capture share this record is open (A-3, #67), and a hard cap here would silently reject the
    /// screening shots. Recorded so the gap is visible rather than discovered in the field.
    let distanceM: Double
    let lighting: Lighting
    let surface: Surface
    let occlusion: Occlusion
    /// Per shot, not per entrance: the same doorway is captured with the card vertical for Arm A
    /// and on the ground for Arm A-prime.
    let cardPlacement: CardPlacement
}

/// R-3's capture-distance cap. Beyond this the capture is refused, not warned about.
let maxCaptureDistanceM = 3.0

/// The plausible range for a threshold rise, in inches. The ADA limit is 0.5"; a reading outside
/// this range is far more likely to be a typo than a doorway, so it needs saying out loud.
let plausibleRiseInches = 0.0...6.0

enum Lighting: String, CaseIterable, Equatable {
    case directSun = "direct_sun"
    case overcast
    case shade
    case artificial

    var label: String {
        switch self {
        case .directSun: return "Direct sun"
        case .overcast: return "Overcast"
        case .shade: return "Shade"
        case .artificial: return "Artificial"
        }
    }
}

enum Surface: String, CaseIterable, Equatable {
    case concrete, brick, tile, metal, wood, stone

    var label: String { rawValue.capitalized }
}

/// Where the reference card is for this shot, which is what separates the arms: Arm A measures
/// from a card held flat against the riser face, Arm A-prime from one lying on the ground
/// (TICK-043, TICK-045). Required by the sidecar, and not derivable after the fact -- only the
/// operator standing there knows where they put it.
enum CardPlacement: String, CaseIterable, Equatable {
    case vertical, ground

    var label: String {
        switch self {
        case .vertical: return "Vertical (against the riser)"
        case .ground: return "Flat on the ground"
        }
    }
}

enum Occlusion: String, CaseIterable, Equatable {
    case none, partial, heavy

    var label: String { rawValue.capitalized }
}

/// Why an entrance or a set of conditions was refused. Each message is read by an operator
/// standing at a doorway, so it says what to do next.
enum TruthRejected: Error, Equatable {
    case entranceIdMalformed(String)
    case riseNotANumber(String)
    case riseImplausible(Double)
    case instrumentMissing
    case distanceNotANumber(String)
    case distanceNotPositive(Double)
    case distanceBeyondCap(Double)

    var message: String {
        switch self {
        case .entranceIdMalformed(let entered):
            return """
            \(entered.isEmpty ? "No entrance ID" : "\"\(entered)\"") is not an entrance ID. \
            The form is E- followed by exactly three digits, like E-014.
            """
        case .riseNotANumber(let entered):
            return """
            \"\(entered)\" is not a number. Enter the caliper reading in inches, like 0.75.
            """
        case .riseImplausible(let value):
            return """
            \(String(format: "%.2f", value))" is outside the usual 0-6" range for a threshold. \
            Check the caliper, then confirm if that is really the reading.
            """
        case .instrumentMissing:
            return "Name the instrument the reading was taken with; the sidecar records it."
        case .distanceNotANumber(let entered):
            return "\"\(entered)\" is not a number. Enter the distance in metres, like 2.0."
        case .distanceNotPositive(let value):
            return "Distance was \(String(format: "%.2f", value)) m. It must be greater than zero."
        case .distanceBeyondCap(let value):
            let cap = String(format: "%.0f", maxCaptureDistanceM)
            return """
            \(String(format: "%.2f", value)) m is beyond the \(cap) m capture cap (R-3). Move \
            closer; a capture from further away cannot be measured to the accuracy this study \
            claims.
            """
        }
    }
}

/// Decides whether entered truth is usable. Pure, so the rules are testable without a UI, in the
/// same shape as CaptureValidation.
enum TruthValidation {

    /// Parse a number the operator typed on a decimal keypad.
    ///
    /// `.decimalPad` shows the *locale's* decimal separator, so on a device set to French or
    /// German there is no period key at all -- and `Double("0,75")` is nil, which would refuse
    /// every reading and every distance on that phone. Both separators are accepted.
    ///
    /// The character filter is not decoration: `Double` also accepts "0x1p3" (8.0), "nan" and
    /// "inf", none of which are caliper readings and all of which the schema would take.
    static func number(from entered: String) -> Double? {
        let trimmed = entered.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        guard trimmed.allSatisfy({ $0.isASCII && ($0.isNumber || "+-.,".contains($0)) }) else {
            return nil
        }
        let normalised = trimmed.replacingOccurrences(of: ",", with: ".")
        guard normalised.filter({ $0 == "." }).count <= 1 else { return nil }
        guard let value = Double(normalised), value.isFinite else { return nil }
        return value
    }

    /// Canonicalise an entrance ID the way `frontdoor.split.canonical_entrance_id` does: NFC,
    /// trimmed, upper-cased, then matched whole. Returns nil when it is not an entrance ID.
    ///
    /// Matching the library exactly matters more than being lenient here: an ID the app accepts
    /// and the split module rejects is an entrance that cannot be assigned to a fold.
    static func canonicalEntranceId(_ entered: String) -> String? {
        let canonical = entered
            .precomposedStringWithCanonicalMapping
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .uppercased()
        guard canonical.count == 5, canonical.hasPrefix("E-") else { return nil }
        guard canonical.dropFirst(2).allSatisfy({ $0.isASCII && $0.isNumber }) else { return nil }
        return canonical
    }

    /// An entrance from what the operator typed.
    ///
    /// `confirmedImplausibleRise` is the operator explicitly standing behind a reading outside
    /// 0-6". An out-of-range value is never silently accepted and never silently dropped -- a real
    /// 7" step exists, and so does a mistyped one.
    static func entrance(
        id: String,
        rise: String,
        instrument: String,
        confirmedImplausibleRise: Bool = false
    ) -> Result<Entrance, TruthRejected> {
        guard let canonical = canonicalEntranceId(id) else {
            return .failure(.entranceIdMalformed(
                id.trimmingCharacters(in: .whitespacesAndNewlines)))
        }
        let trimmedRise = rise.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let value = number(from: trimmedRise) else {
            return .failure(.riseNotANumber(trimmedRise))
        }
        if !plausibleRiseInches.contains(value) && !confirmedImplausibleRise {
            return .failure(.riseImplausible(value))
        }
        let trimmedInstrument = instrument.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedInstrument.isEmpty else { return .failure(.instrumentMissing) }

        // Assigned here and nowhere else. canonicalEntranceId has already accepted the ID, so
        // the only way this returns nil is a disagreement between the two, which would be a bug
        // rather than a state to recover from.
        guard let split = SplitAssignment.split(for: canonical) else {
            return .failure(.entranceIdMalformed(canonical))
        }
        return .success(Entrance(
            id: canonical,
            riseInches: value,
            instrument: trimmedInstrument,
            split: split
        ))
    }

    /// Condition tags from what the operator entered. The three tags are already constrained by
    /// their types; only the distance can be wrong.
    static func conditions(
        distance: String,
        lighting: Lighting,
        surface: Surface,
        occlusion: Occlusion,
        cardPlacement: CardPlacement = .vertical
    ) -> Result<ConditionTags, TruthRejected> {
        let trimmed = distance.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let value = number(from: trimmed) else {
            return .failure(.distanceNotANumber(trimmed))
        }
        guard value > 0 else { return .failure(.distanceNotPositive(value)) }
        guard value <= maxCaptureDistanceM else { return .failure(.distanceBeyondCap(value)) }
        return .success(ConditionTags(
            distanceM: value, lighting: lighting, surface: surface, occlusion: occlusion,
            cardPlacement: cardPlacement))
    }
}

/// What the viewfinder is pointed at: one entrance, and the conditions of this shot of it.
///
/// The entrance persists across a run of captures; the conditions change between them, which is
/// the whole point of D-002's depth-per-entrance. Changing them is done from the viewfinder, so
/// stepping closer between two frames does not require leaving the camera -- and so the second
/// frame cannot quietly inherit the first one's distance.
struct CaptureSubject: Equatable {
    var entrance: Entrance
    var conditions: ConditionTags
}
