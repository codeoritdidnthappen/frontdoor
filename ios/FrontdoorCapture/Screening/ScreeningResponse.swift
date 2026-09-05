import Foundation

/// What `POST /screen` said about one entrance (#275, step 3 of the scan flow).
///
/// Everything here is read from the server's reply. The app decides no verdict, aggregates
/// nothing and fills in no blank: a screening verdict is a statement the model made about a
/// photograph, and a phone that computed one would be a second assessment path with none of the
/// server's honesty rules attached to it.
struct ScreeningResponse: Decodable, Equatable {

    /// One criterion's answer. `verdict` is a plain String on purpose — the server may send a
    /// verdict this build has never heard of, and the rule (shared with the laptop surface) is to
    /// show it verbatim rather than map it onto something legible.
    struct Criterion: Decodable, Equatable {
        let verdict: String?
        /// Rendered, never compared. The server passes the model's own value through and it is
        /// documented as a number but arrives as `""` when the model omitted it, so this decodes
        /// either and keeps the text.
        let confidence: String?
        let evidence: String?

        private enum CodingKeys: String, CodingKey { case verdict, confidence, evidence }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            verdict = try container.decodeIfPresent(String.self, forKey: .verdict)
            evidence = try container.decodeIfPresent(String.self, forKey: .evidence)
            if let number = try? container.decode(Int.self, forKey: .confidence) {
                confidence = String(number)
            } else {
                let text = try container.decodeIfPresent(String.self, forKey: .confidence)
                confidence = (text?.isEmpty ?? true) ? nil : text
            }
        }

        init(verdict: String?, confidence: String?, evidence: String?) {
            self.verdict = verdict
            self.confidence = confidence
            self.evidence = evidence
        }
    }

    struct Assessment: Decodable, Equatable {
        let criteria: [String: Criterion]?
        let error: String?
    }

    let entranceId: String?
    let assessment: Assessment
    /// The honesty statement, printed from the response so this screen cannot drift from what the
    /// API commits to — the same rule the laptop surface follows.
    let wording: String
    let status: String
    let model: String
    let latencyMs: Int
    /// How many faces the ingest step blurred before the model saw anything.
    let facesBlurred: Int
    /// The privacy audit's own answer: `clear`, `face_visible`, or `unknown`. Kept distinct from
    /// `quarantined` because "checked and clear" and "never answered" are different facts.
    let faceCheck: String
    let quarantined: Bool
    let quarantineReason: String?
    /// Server-computed photo ADA score (#318). Optional so an older envelope still decodes;
    /// the phone never fills this in.
    let adaScreening: AdaScreening?

    private enum CodingKeys: String, CodingKey {
        case entranceId = "entrance_id"
        case assessment, wording, status, model
        case latencyMs = "latency_ms"
        case facesBlurred = "faces_blurred"
        case faceCheck = "face_check"
        case quarantined
        case quarantineReason = "quarantine_reason"
        case adaScreening = "ada_screening"
    }
}

/// One of the eight photo ADA checks. `result` is a plain String so an unknown state is shown
/// verbatim rather than mapped onto a familiar one.
struct AdaCheck: Decodable, Equatable {
    let result: String?
    let evidence: String?
}

/// The photo-based ADA screening block. Score, counts and summary are computed on the server.
struct AdaScreening: Decodable, Equatable {
    let scorePercent: Double?
    let determinedCount: Int
    let totalCount: Int
    let trueCount: Int
    let falseCount: Int
    let cannotDetermineCount: Int
    let notApplicableCount: Int
    let checks: [String: AdaCheck]
    let summary: String
    let standardsUrl: String
    let disclaimer: String

    private enum CodingKeys: String, CodingKey {
        case scorePercent = "score_percent"
        case determinedCount = "determined_count"
        case totalCount = "total_count"
        case trueCount = "true_count"
        case falseCount = "false_count"
        case cannotDetermineCount = "cannot_determine_count"
        case notApplicableCount = "not_applicable_count"
        case checks, summary, disclaimer
        case standardsUrl = "standards_url"
    }
}

/// The criteria the screening engine answers, in the order they are shown.
///
/// The keys are the server's (`frontdoor.screening.CRITERIA`), and a pytest source guard fails if
/// the two lists ever disagree — a criterion the server assesses and this list omits would simply
/// not appear on the phone, which is the quiet failure worth preventing.
enum ScreeningCriterion: String, CaseIterable, Codable, Identifiable {
    case rampOrBevel = "ramp_or_bevel"
    case handrails = "handrails"
    case accessibleDoorHardware = "accessible_door_hardware"
    case accessibilitySignage = "accessibility_signage"

    var id: String { rawValue }

    /// The same labels the laptop surface prints, so the two demo surfaces name the same things.
    var label: String {
        switch self {
        case .rampOrBevel: return "Ramp or bevelled threshold"
        case .handrails: return "Handrails"
        case .accessibleDoorHardware: return "Accessible door hardware"
        case .accessibilitySignage: return "Accessibility signage"
        }
    }
}

/// The eight photo ADA checks, in the order the iPhone displays them (#318).
enum AdaScreeningCheck: String, CaseIterable, Identifiable {
    case entranceRoute = "entrance_route"
    case threshold = "threshold"
    case ramp = "ramp"
    case doorHardware = "door_hardware"
    case doorOpening = "door_opening"
    case handrails = "handrails"
    case signage = "signage"
    case temporaryBarriers = "temporary_barriers"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .entranceRoute: return "Entrance route"
        case .threshold: return "Threshold"
        case .ramp: return "Ramp"
        case .doorHardware: return "Door hardware"
        case .doorOpening: return "Door opening"
        case .handrails: return "Handrails"
        case .signage: return "Signage"
        case .temporaryBarriers: return "Temporary barriers"
        }
    }
}
