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
        /// EXIF tag 274 for the bytes on disk, 1-8. Recorded because `width`, `height`, the
        /// intrinsics and the ROI points are all in the STORED pixel grid with this rotation
        /// unapplied -- and a phone held portrait writes a landscape buffer tagged 6, so a reader
        /// that honours EXIF silently disagrees with every one of them.
        ///
        /// NOT optional, unlike `width`/`height`: the schema requires `exif_orientation`, and
        /// Swift's synthesized encoding omits a nil Optional rather than writing null -- so a
        /// caller who left it out would write a sidecar to disk, queue it, and only learn at
        /// upload, from a 422 the client treats as not worth retrying. Same argument as
        /// `DepthRef` below: make the invalid state unrepresentable (QA B01).
        var exifOrientation: Int

        enum CodingKeys: String, CodingKey {
            case path, sha256, width, height
            case exifOrientation = "exif_orientation"
        }
    }

    /// A card is a rectangle, so the homography needs all four of its corners.
    /// Mirrors `card_corners` minItems/maxItems in capture_sidecar.schema.json.
    static let requiredCardCorners = 4

    /// Depth is `{path, sha256}` and nothing else (ARCHITECTURE section 4).
    ///
    /// A separate type rather than a reused `FileRef`: the schema declares this object
    /// `additionalProperties: false`, so a `width` that rides along on the shared type
    /// makes every depth capture fail validation. Structure it so the extra fields
    /// cannot be passed rather than trusting a caller to leave them nil (QA B01).
    struct DepthRef: Encodable, Equatable {
        var path: String
        var sha256: String
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
        /// Optional since D-034: the screening protocol never asks for it.
        var surface: String?
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
    /// Present when this app's camera took the photo; absent for an imported one.
    var lens: String?
    var captureDevice: String?
    var zoomFactor: Double?
    /// Which kind of record this is, and therefore which fields it carries (D-034).
    ///
    /// Written for every capture, including metrology ones. The schema treats an ABSENT mode as
    /// metrology so that sidecars from before D-034 stay valid, but a record this app writes
    /// today should say what it is rather than lean on that fallback.
    var captureMode: CaptureMode
    var image: FileRef
    /// Null when the device or the frame produced no depth. Absence must never cost an entrance
    /// (D-020, TICK-023), so this is a value the schema accepts rather than a reason to refuse.
    var depth: DepthRef?
    /// Present for metrology and screening captures; absent for an imported photo, which was
    /// taken outside this app and has none of our camera's numbers.
    var intrinsics: Intrinsics?
    var gravity: [Double]?
    /// Metrology only. A screening capture places no card, and the schema forbids the field
    /// rather than merely allowing it to be missing: a placement recorded for a capture that had
    /// no card would describe something nobody did.
    var cardPlacement: String?
    /// Metrology only. No caliper is carried under the plain-photo protocol.
    var groundTruth: GroundTruth?
    var conditions: Conditions
    /// Metrology only. The taps are inputs to a measurement, and a screening capture makes none.
    var roi: ROI?
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
        // Omitted entirely rather than written as null for an imported photo: the schema forbids
        // these in that mode, and a null would still be a claim that the field applies.
        try c.encodeIfPresent(lens, forKey: .lens)
        try c.encodeIfPresent(captureDevice, forKey: .captureDevice)
        try c.encodeIfPresent(zoomFactor, forKey: .zoomFactor)
        try c.encode(captureMode, forKey: .captureMode)
        try c.encode(image, forKey: .image)
        if let depth { try c.encode(depth, forKey: .depth) } else { try c.encodeNil(forKey: .depth) }
        try c.encodeIfPresent(intrinsics, forKey: .intrinsics)
        try c.encodeIfPresent(gravity, forKey: .gravity)
        try c.encodeIfPresent(cardPlacement, forKey: .cardPlacement)
        try c.encodeIfPresent(groundTruth, forKey: .groundTruth)
        try c.encode(conditions, forKey: .conditions)
        try c.encodeIfPresent(roi, forKey: .roi)
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
        case captureMode = "capture_mode"
        case image, depth, intrinsics, gravity
        case cardPlacement = "card_placement"
        case groundTruth = "ground_truth"
        case conditions, roi, split
    }
}
