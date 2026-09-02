import Foundation

/// Which kind of record a capture produces (D-034, TICK-027 / #31).
///
/// The app writes one sidecar shape with a discriminator rather than two shapes, so there is one
/// schema, one validator and one loader. What differs is which fields a mode is allowed to carry:
/// a screening capture may not carry a caliper reading, and an imported photo may not carry
/// intrinsics. Those are refusals in the schema, not omissions — a record that claimed either
/// would describe something nobody did.
enum CaptureMode: String, Codable, CaseIterable, Equatable {
    /// The pre-registered study: caliper truth, ROI taps, card placement, intrinsics, gravity.
    case metrology
    /// The 2026-09-01 plain-photo protocol: our camera, entrance and condition tags, nothing else.
    case screening
    /// A photo taken outside this app, brought in from the photo library. None of our capture
    /// metadata exists for it and none is invented.
    case imported

    /// What the app opens into. Screening is the protocol the field is actually running
    /// (docs/capture-protocol.md); metrology stays reachable rather than deleted, because whether
    /// it is alive is an open team question (A-3, #67) and not one this app decides.
    static let `default` = CaptureMode.screening

    /// Whether this mode records a caliper reading, a card placement and ROI taps.
    var carriesMetrologyTruth: Bool { self == .metrology }

    /// Whether this app's camera produced the frame, and so knows its lens and intrinsics.
    var isOurCamera: Bool { self != .imported }
}
