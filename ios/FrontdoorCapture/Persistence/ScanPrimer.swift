import Foundation

/// Whether the operator has been shown what a scan involves (#275, step 1).
///
/// Once per install, not once per entrance. The primer is worth reading before the first scan and
/// is friction on the fortieth: under D-036 a single operator walks 40-60 entrances, and a screen
/// between them and the shutter every time would be dismissed unread by the third one -- which is
/// the state where a primer exists but nobody has read it.
///
/// It stays reachable from the home screen afterwards, so "seen" never means "gone".
struct ScanPrimer {
    static let defaultsKey = "scan-primer-seen"

    var defaults: UserDefaults = .standard

    var hasBeenSeen: Bool { defaults.bool(forKey: Self.defaultsKey) }

    func markSeen() { defaults.set(true, forKey: Self.defaultsKey) }
}
