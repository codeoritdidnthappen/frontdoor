import CryptoKit
import Foundation

/// Which fold an entrance belongs to. Assigned once, at creation, and never again (D-023).
enum Split: String, Equatable {
    case dev, calib, sealed
}

/// Assigns the split the same way `frontdoor.split.assign_split` does.
///
/// Two implementations of one rule disagreeing is not a bug that announces itself. It shows up as
/// an entrance sitting in a different fold on the phone than in the analysis -- the sealed set
/// quietly stops being sealed, and nothing downstream can tell. The golden vectors in
/// `tests/fixtures/split_golden.json` are read by both suites so neither can drift alone.
///
/// There is deliberately no way to view, choose, override or re-roll an assignment, and the
/// operator is never shown which fold an entrance landed in: knowing an entrance is sealed is
/// enough to photograph it differently without meaning to (D-007).
enum SplitAssignment {

    /// The committed seed from `src/frontdoor/split_seed.json`.
    ///
    /// Duplicated here because the app ships without the Python package, and pinned by
    /// `tests/test_split_seed_matches.py`, which fails if this string and the committed file ever
    /// disagree. A build carrying a different seed would assign a different, self-consistent, and
    /// completely wrong set of folds.
    static let seed = "24f19370b92d067c0b1a5c717ef6b8996dc6b87f8fd914f9c93ba21e0f826b71"

    static let sealedPercent = 30
    static let calibPercent = 20

    /// nil when the ID is not canonical -- the caller has an entrance that cannot be assigned, and
    /// silently bucketing it would put a real doorway in an arbitrary fold.
    static func split(for entranceId: String) -> Split? {
        guard let canonical = TruthValidation.canonicalEntranceId(entranceId) else { return nil }
        let digest = SHA256.hash(data: Data((canonical + seed).utf8))
        // First eight bytes, big-endian, exactly as int.from_bytes(digest[:8], "big") reads them.
        let bucket = digest.prefix(8).reduce(into: UInt64(0)) { acc, byte in
            acc = (acc << 8) | UInt64(byte)
        } % 100
        if bucket < UInt64(sealedPercent) { return .sealed }
        if bucket < UInt64(sealedPercent + calibPercent) { return .calib }
        return .dev
    }
}
