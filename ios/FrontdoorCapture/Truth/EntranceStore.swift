import Foundation

/// The entrances seen this session, keyed by canonical ID.
///
/// Re-entering an ID attaches to the existing entrance rather than creating a second one: its
/// caliper reading and split are reused unchanged. Two rows for one doorway, disagreeing about
/// its rise, is the failure this exists to prevent -- nothing downstream could tell which one was
/// the real measurement.
///
/// In memory only. Surviving app relaunch is TICK-028's problem, when captures start being
/// written to disk; keeping it here would be a second store to keep in step with that one.
@MainActor
final class EntranceStore: ObservableObject {
    @Published private(set) var entrances: [String: Entrance] = [:]

    func existing(id: String) -> Entrance? {
        TruthValidation.canonicalEntranceId(id).flatMap { entrances[$0] }
    }

    /// The entrance for a metrology capture, supplying a reading if it does not have one yet.
    ///
    /// The no-overwrite rule stands where it matters: an entrance that already HAS a reading keeps
    /// it, so a second operator cannot give E-014 a different rise. What this adds is the one case
    /// the rule was never meant to cover -- an entrance first recorded by a screening capture,
    /// which has no reading at all. Without it that doorway could never be captured in metrology
    /// mode on this device, because `resolve` returns the reading-less entrance unchanged and the
    /// writer then refuses it (D-034).
    func upgradeToMetrology(
        id: String,
        rise: String,
        instrument: String,
        confirmedImplausibleRise: Bool = false
    ) -> Result<Entrance, TruthRejected> {
        if let known = existing(id: id), known.riseInches != nil { return .success(known) }
        let created = TruthValidation.entrance(
            id: id, rise: rise, instrument: instrument,
            confirmedImplausibleRise: confirmedImplausibleRise)
        if case .success(let entrance) = created {
            entrances[entrance.id] = entrance
        }
        return created
    }

    /// The entrance for a screening capture: the one already recorded, or a new one with no
    /// reading (D-034).
    ///
    /// An ID already known still wins outright, exactly as below. That matters more here than it
    /// looks: if a doorway was captured in metrology mode earlier in the day, a screening capture
    /// of the same entrance attaches to it and keeps its caliper reading, rather than creating a
    /// second, reading-less entrance for the same door.
    func resolveScreening(id: String) -> Result<Entrance, TruthRejected> {
        if let known = existing(id: id) { return .success(known) }
        let created = TruthValidation.screeningEntrance(id: id)
        if case .success(let entrance) = created {
            entrances[entrance.id] = entrance
        }
        return created
    }

    /// The entrance for this ID: the one already recorded, or a new one from what was entered.
    ///
    /// An ID already known wins outright, and what was typed into the reading field is not even
    /// looked at. That is the point of the rule -- the second visit to E-014 must not be able to
    /// give it a different rise, whether by typo or by a second operator reading the caliper
    /// differently. Correcting a reading is deliberately not doable here (out of scope: a
    /// correction is a new capture with a note, not a silent edit).
    func resolve(
        id: String,
        rise: String,
        instrument: String,
        confirmedImplausibleRise: Bool = false
    ) -> Result<Entrance, TruthRejected> {
        if let known = existing(id: id) { return .success(known) }
        let created = TruthValidation.entrance(
            id: id, rise: rise, instrument: instrument,
            confirmedImplausibleRise: confirmedImplausibleRise)
        if case .success(let entrance) = created {
            entrances[entrance.id] = entrance
        }
        return created
    }
}
