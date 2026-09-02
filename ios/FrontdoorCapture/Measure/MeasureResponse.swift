import Foundation

/// The response from `POST /measure`, exactly as TICK-060 froze it.
///
/// Modelled against the committed schema rather than against what the stub happens to send today,
/// so the client is already right when TICK-061 fills real values in behind the identical shape.
struct MeasureResponse: Decodable, Equatable {
    /// True while the endpoint returns fixed placeholders. The schema requires clients to surface
    /// it: on stage, a fabricated number rendered like a measurement is the single most damaging
    /// thing this app could do.
    let stub: Bool
    let captureId: String
    let arms: [ArmName: Arm]

    enum CodingKeys: String, CodingKey {
        case stub
        case captureId = "capture_id"
        case arms
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        stub = try c.decode(Bool.self, forKey: .stub)
        captureId = try c.decode(String.self, forKey: .captureId)
        let raw = try c.decode([String: Arm].self, forKey: .arms)
        arms = raw.reduce(into: [:]) { out, pair in
            if let name = ArmName(rawValue: pair.key) { out[name] = pair.value }
        }
    }
}

/// The four arms, in the order they are presented. Arm A is the pre-registered primary (D-022);
/// the others report measurement error alone and carry no pass/fail bar.
enum ArmName: String, CaseIterable, Equatable {
    case a = "A"
    case aPrime = "A_prime"
    case b = "B"
    case c = "C"

    var label: String {
        switch self {
        case .a: return "Arm A"
        case .aPrime: return "Arm A′"
        case .b: return "Arm B"
        case .c: return "Arm C"
        }
    }

    /// Only Arm A carries a pass/fail bar (D-022, and Amendment A-2). The others are reported
    /// without one, so the app must not draw a verdict against them.
    var carriesTheBar: Bool { self == .a }
}

/// One arm is either a measurement or a stated absence -- never nothing at all.
enum Arm: Decodable, Equatable {
    case measured(Measurement)
    case absent(Absence)

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Absence.CodingKeys.self)
        // Discriminated on absent_reason, the way the schema discriminates it.
        if c.contains(.absentReason) {
            self = .absent(try Absence(from: decoder))
        } else {
            self = .measured(try Measurement(from: decoder))
        }
    }

    struct Measurement: Decodable, Equatable {
        let riseIn: Double
        let intervalIn: Interval
        let decisions: Decisions

        enum CodingKeys: String, CodingKey {
            case riseIn = "rise_in"
            case intervalIn = "interval_in"
            case decisions
        }
    }

    struct Absence: Decodable, Equatable {
        let absentReason: Reason
        let detail: String?

        enum CodingKeys: String, CodingKey {
            case absentReason = "absent_reason"
            case detail
        }

        /// Three different things, and the operator needs them told apart: a cut arm is expected,
        /// a failed arm is about this capture, an unavailable arm is about this deployment.
        enum Reason: String, Decodable, Equatable {
            case cut, failed, unavailable

            var headline: String {
                switch self {
                case .cut: return "Not run"
                case .failed: return "Could not measure"
                case .unavailable: return "Not available here"
                }
            }

            var plain: String {
                switch self {
                case .cut:
                    return "This arm was dropped by a project decision, so it is not run at all."
                case .failed:
                    return "This arm could not measure this capture."
                case .unavailable:
                    return "This arm is not served by this deployment."
                }
            }
        }
    }
}

struct Interval: Decodable, Equatable {
    let low: Double
    let high: Double
}

struct Decisions: Decodable, Equatable {
    let halfInch: Decision
    let quarterInch: Decision

    enum CodingKeys: String, CodingKey {
        case halfInch = "half_inch"
        case quarterInch = "quarter_inch"
    }
}

struct Decision: Decodable, Equatable {
    let verdict: Verdict
    /// Present when there is no verdict to give. The schema calls abstain first-class; the reason
    /// is what makes it one rather than a gap.
    let explanation: String?

    enum Verdict: String, Decodable, Equatable {
        case pass, fail, abstain
    }
}
