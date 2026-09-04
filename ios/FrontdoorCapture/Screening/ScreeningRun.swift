import Foundation

/// One photo's trip through `POST /screen`, from the moment it is sent (#275).
///
/// It exists so the named checks can be on screen while the answer is still being waited for: the
/// criteria are named from the start, and the outcome is what changes. The identity is stable
/// across that change, so the sheet showing it does not close and reopen when the verdicts land.
struct ScreeningRun: Identifiable, Equatable {
    enum Outcome: Equatable {
        case inFlight
        case assessed(ScreeningResponse)
        /// The operator-facing sentence from `ScreenClient.Failure`. Every one of them ends by
        /// saying the photo is saved and queued, because it is: screening happens after the write.
        case failed(String)
    }

    let id = UUID()
    let entranceId: String
    let startedAt: Date
    var outcome: Outcome

    /// The server's answer for one criterion key, or nil when it said nothing about it.
    func criterion(_ key: String) -> ScreeningResponse.Criterion? {
        guard case .assessed(let response) = outcome else { return nil }
        return response.assessment.criteria?[key]
    }

    /// Criteria the server answered that this build has no label for, sorted so the order is
    /// stable. Kept rather than dropped: a server that starts assessing a fifth thing should show
    /// it on the phone the same day, not the day someone remembers to add a label.
    var unrecognisedCriterionKeys: [String] {
        guard case .assessed(let response) = outcome,
              let criteria = response.assessment.criteria else { return [] }
        let known = Set(ScreeningCriterion.allCases.map(\.rawValue))
        return criteria.keys.filter { !known.contains($0) }.sorted()
    }
}
