import Foundation

/// Human presence truth sent after a complete future entrance capture (TICK-282).
enum LabelTruth: String, CaseIterable, Codable, Identifiable {
    case present
    case absent
    case cannotDetermine = ""

    var id: String { rawValue }

    var label: String {
        switch self {
        case .present: return "Present"
        case .absent: return "Absent"
        case .cannotDetermine: return "Cannot determine"
        }
    }
}

enum EntranceLabelState: String, Codable {
    case queued
    case accepted
    case conflict
}

struct EntranceLabelRecord: Codable, Equatable {
    let entranceId: String
    let labeledBy: String
    let answers: [String: String]
    var state: EntranceLabelState
    var failure: String?

    private enum CodingKeys: String, CodingKey {
        case entranceId = "entrance_id"
        case labeledBy = "labeled_by"
        case answers, state, failure
    }
}

/// Inspectable state behind the four button rows; one dictionary entry per exclusive row.
struct EntranceLabelDraft: Equatable {
    private(set) var answers: [ScreeningCriterion: LabelTruth] = [:]

    mutating func select(_ truth: LabelTruth, for criterion: ScreeningCriterion) {
        answers[criterion] = truth
    }

    mutating func restore(_ record: EntranceLabelRecord) {
        answers = Dictionary(uniqueKeysWithValues: ScreeningCriterion.allCases.compactMap {
            guard let raw = record.answers[$0.rawValue], let truth = LabelTruth(rawValue: raw)
            else { return nil }
            return ($0, truth)
        })
    }

    func canSave(operatorName: String) -> Bool {
        let name = operatorName.trimmingCharacters(in: .whitespacesAndNewlines)
        return !name.isEmpty && name.count <= 100
            && answers.count == ScreeningCriterion.allCases.count
    }
}

/// The runtime decision used by the visible Finish button and exercised without a camera.
enum CaptureFinishDecision {
    static func isEnabled(mode: CaptureMode, coverage: ViewSetCoverage) -> Bool {
        mode == .screening && coverage.isComplete
    }

    static func destination(
        mode: CaptureMode, coverage: ViewSetCoverage, entranceId: String?
    ) -> String? {
        guard isEnabled(mode: mode, coverage: coverage) else { return nil }
        return entranceId
    }
}

/// James enters this once; criterion choices never use a keyboard or dictation.
struct LabelOperatorStore {
    var defaults: UserDefaults = .standard
    static let key = "frontdoor.label-operator"

    var name: String {
        get { defaults.string(forKey: Self.key) ?? "" }
        nonmutating set { defaults.set(newValue.trimmingCharacters(in: .whitespacesAndNewlines),
                                       forKey: Self.key) }
    }
}
