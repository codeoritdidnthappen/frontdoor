import Foundation

/// The JSON shape ARCHITECTURE section 4 specifies, and nothing else.
///
/// A hand-built dictionary would drift from the schema silently; this is `Encodable` with
/// `.sortedKeys`, so the bytes are reproducible for identical content and `sidecar_sha256` means
/// something (TICK-028 AC6).
struct Sidecar: Encodable, Equatable {
    /// `width` and `height` belong to the image only; the schema's depth object forbids them, so
    /// they are omitted rather than nulled when absent -- the opposite of `depth` itself.
    struct FileRef: Encodable, Equatable {
        var path: String
        var sha256: String
        var width: Int?
        var height: Int?
    }

    struct Intrinsics: Encodable, Equatable {
        var fx: Double
        var fy: Double
        var cx: Double
        var cy: Double
        /// Verbatim from the camera, never resampled. Undistortion is TICK-042's job.
        var distortionTable: [Double]
        var distortionCenter: Point

        enum CodingKeys: String, CodingKey {
            case fx, fy, cx, cy
            case distortionTable = "distortion_table"
            case distortionCenter = "distortion_center"
        }
    }

    struct Point: Encodable, Equatable {
        var x: Double
        var y: Double
    }

    struct GroundTruth: Encodable, Equatable {
        var riseIn: Double
        var instrument: String

        enum CodingKeys: String, CodingKey {
            case riseIn = "rise_in"
            case instrument
        }
    }

    struct Conditions: Encodable, Equatable {
        var distanceM: Double
        var lighting: String
        var surface: String
        var occlusion: String

        enum CodingKeys: String, CodingKey {
            case distanceM = "distance_m"
            case lighting, surface, occlusion
        }
    }

    struct ROI: Encodable, Equatable {
        var thresholdTop: [Int]
        var thresholdBottom: [Int]
        var cardCorners: [[Int]]

        enum CodingKeys: String, CodingKey {
            case thresholdTop = "threshold_top"
            case thresholdBottom = "threshold_bottom"
            case cardCorners = "card_corners"
        }
    }

    var captureId: String
    var entranceId: String
    var capturedAt: String
    var deviceModel: String
    var lens: String
    var captureDevice: String
    var zoomFactor: Double
    var image: FileRef
    /// Null when the device or the frame produced no depth. Absence must never cost an entrance
    /// (D-020, TICK-023), so this is a value the schema accepts rather than a reason to refuse.
    var depth: FileRef?
    var intrinsics: Intrinsics
    var gravity: [Double]
    var cardPlacement: String
    var groundTruth: GroundTruth
    var conditions: Conditions
    var roi: ROI
    var split: String

    /// Written by hand for one reason: `depth` must be PRESENT AND NULL when there is none.
    ///
    /// The synthesised encoder uses `encodeIfPresent` for optionals, which drops the key entirely
    /// -- and the schema lists `depth` as required with type ["object", "null"]. A capture from a
    /// phone with no depth sensor would have failed validation on write. D-020 says absence is
    /// recorded, never punished; it has to actually be recorded.
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(captureId, forKey: .captureId)
        try c.encode(entranceId, forKey: .entranceId)
        try c.encode(capturedAt, forKey: .capturedAt)
        try c.encode(deviceModel, forKey: .deviceModel)
        try c.encode(lens, forKey: .lens)
        try c.encode(captureDevice, forKey: .captureDevice)
        try c.encode(zoomFactor, forKey: .zoomFactor)
        try c.encode(image, forKey: .image)
        if let depth { try c.encode(depth, forKey: .depth) } else { try c.encodeNil(forKey: .depth) }
        try c.encode(intrinsics, forKey: .intrinsics)
        try c.encode(gravity, forKey: .gravity)
        try c.encode(cardPlacement, forKey: .cardPlacement)
        try c.encode(groundTruth, forKey: .groundTruth)
        try c.encode(conditions, forKey: .conditions)
        try c.encode(roi, forKey: .roi)
        try c.encode(split, forKey: .split)
    }

    enum CodingKeys: String, CodingKey {
        case captureId = "capture_id"
        case entranceId = "entrance_id"
        case capturedAt = "captured_at"
        case deviceModel = "device_model"
        case lens
        case captureDevice = "capture_device"
        case zoomFactor = "zoom_factor"
        case image, depth, intrinsics, gravity
        case cardPlacement = "card_placement"
        case groundTruth = "ground_truth"
        case conditions, roi, split
    }
}
