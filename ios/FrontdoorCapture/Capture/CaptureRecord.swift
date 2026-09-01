import AVFoundation
import CoreMotion
import Foundation

/// The method's entire legal input for one shutter press: one RGB still, the intrinsics for that
/// specific frame, and the gravity vector at the instant it was taken (D-015).
///
/// Nothing the metrology consumes exists outside this record. It is a value type with no
/// AVFoundation objects in it, so the rules that decide whether a capture is usable are ordinary
/// functions that can be tested without a camera.
struct CaptureRecord: Equatable {
    /// The instant of the shutter press, not of encoding. Serialised as the sidecar's required
    /// `captured_at` (RFC 3339, UTC). Sampled next to gravity for the same reason gravity is:
    /// the delegate callback runs after the exposure and describes a different moment.
    var capturedAt: Date
    var pixelWidth: Int
    var pixelHeight: Int
    var intrinsics: CameraIntrinsics
    var gravity: GravitySample
    /// Hardware identifier, e.g. `iPhone17,1` — not the marketing name, which collapses variants
    /// that have different cameras. Per-device effects are analysable later (ASM-1).
    var deviceModel: String
    /// e.g. `builtInWideAngleCamera`. Fixed by D-014, recorded so the record proves it.
    var lens: String
    var zoomFactor: Double
    /// Metadata for the quarantined depth map, or nil when the device or the frame produced none.
    /// Never nil-checked to decide anything about the measurement (D-020).
    var depth: DepthRecord?
}

/// Intrinsics as delivered for one frame, already expressed in the pixel grid of the still that
/// carries them.
struct CameraIntrinsics: Equatable {
    var fx: Double
    var fy: Double
    var cx: Double
    var cy: Double
    /// Radial distortion lookup table, recorded verbatim. The app never alters pixels; undistortion
    /// happens in the metrology library (TICK-042).
    var lensDistortionLookupTable: Data?
    var lensDistortionCenterX: Double
    var lensDistortionCenterY: Double

    /// AVFoundation reports intrinsics against a reference grid that need not match the still's
    /// own dimensions. Scaling here rather than at analysis time keeps one convention: the numbers
    /// in the record always describe the image beside them.
    static func from(
        matrix: matrix_float3x3,
        referenceDimensions: CGSize,
        distortionTable: Data?,
        distortionCenter: CGPoint,
        pixelWidth: Int,
        pixelHeight: Int
    ) -> CameraIntrinsics? {
        guard referenceDimensions.width > 0, referenceDimensions.height > 0,
              pixelWidth > 0, pixelHeight > 0 else { return nil }
        let sx = Double(pixelWidth) / Double(referenceDimensions.width)
        let sy = Double(pixelHeight) / Double(referenceDimensions.height)
        return CameraIntrinsics(
            fx: Double(matrix.columns.0.x) * sx,
            fy: Double(matrix.columns.1.y) * sy,
            cx: Double(matrix.columns.2.x) * sx,
            cy: Double(matrix.columns.2.y) * sy,
            lensDistortionLookupTable: distortionTable,
            lensDistortionCenterX: Double(distortionCenter.x) * sx,
            lensDistortionCenterY: Double(distortionCenter.y) * sy
        )
    }
}

/// Gravity in g units at the capture instant.
struct GravitySample: Equatable {
    var x: Double
    var y: Double
    var z: Double

    var magnitude: Double { (x * x + y * y + z * z).squareRoot() }

    /// Motion updates that were never started, or a stale sample, do not read as an obviously wrong
    /// number — they read as a plausible-looking vector. The magnitude is the cheap check that they
    /// were genuinely running.
    static let magnitudeTolerance = 0.05
    var isPlausible: Bool { abs(magnitude - 1.0) <= Self.magnitudeTolerance }
}

/// Why a shutter press produced nothing. Distinct from `CaptureUnavailable`, which is about the
/// session; these are frames that were taken and then refused.
enum CaptureRejected: Error, Equatable {
    case noImageData
    case noCalibrationData
    case unusableCalibrationData
    case zoomNotUnity(Double)
    case noGravitySample
    case gravityImplausible(Double)

    /// Shown verbatim to an operator standing at an entrance.
    var message: String {
        switch self {
        case .noImageData:
            return "The camera returned no image data. Nothing was recorded; take the shot again."
        case .noCalibrationData:
            return """
            The camera returned no calibration data for that frame, so the still has no intrinsics \
            and cannot be measured. Nothing was recorded.
            """
        case .unusableCalibrationData:
            return """
            The calibration data for that frame could not be matched to the image, so the \
            intrinsics would not describe it. Nothing was recorded.
            """
        case .zoomNotUnity(let factor):
            return """
            Zoom was \(String(format: "%.2f", factor))x, not 1x. Captures must use the 1x main lens \
            with no crop, or the intrinsics travelling with the frame are wrong. Nothing was recorded.
            """
        case .noGravitySample:
            return """
            No device-motion reading was available at the shutter, so capture angle could not be \
            measured. Nothing was recorded; hold the phone still for a moment and try again.
            """
        case .gravityImplausible(let magnitude):
            return """
            The gravity reading was \(String(format: "%.2f", magnitude))g rather than about 1g, so \
            device motion was not settled. Nothing was recorded; hold the phone steady and retry.
            """
        }
    }
}

/// Decides whether a frame is usable. Pure, so the rules are testable without a camera.
enum CaptureValidation {
    static func record(
        capturedAt: Date,
        pixelWidth: Int,
        pixelHeight: Int,
        intrinsics: CameraIntrinsics?,
        hadCalibrationData: Bool,
        gravity: GravitySample?,
        deviceModel: String,
        lens: String,
        zoomFactor: Double,
        depth: DepthRecord? = nil
    ) -> Result<CaptureRecord, CaptureRejected> {
        guard pixelWidth > 0, pixelHeight > 0 else { return .failure(.noImageData) }
        guard hadCalibrationData else { return .failure(.noCalibrationData) }
        guard let intrinsics else { return .failure(.unusableCalibrationData) }
        // Compared against a tolerance rather than !=: videoZoomFactor is a float the system may
        // return as 1.0000001, and rejecting a capture over that would be a lie.
        guard abs(zoomFactor - 1.0) < 0.001 else { return .failure(.zoomNotUnity(zoomFactor)) }
        guard let gravity else { return .failure(.noGravitySample) }
        guard gravity.isPlausible else { return .failure(.gravityImplausible(gravity.magnitude)) }

        return .success(CaptureRecord(
            capturedAt: capturedAt,
            pixelWidth: pixelWidth,
            pixelHeight: pixelHeight,
            intrinsics: intrinsics,
            gravity: gravity,
            deviceModel: deviceModel,
            lens: lens,
            zoomFactor: zoomFactor,
            depth: depth
        ))
    }

    /// Hardware identifier such as `iPhone17,1`. `UIDevice.model` returns "iPhone" for every
    /// iPhone, which would make per-device analysis impossible.
    static func hardwareIdentifier(
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> String {
        if let simulated = environment["SIMULATOR_MODEL_IDENTIFIER"] { return simulated }
        var system = utsname()
        uname(&system)
        let identifier = withUnsafeBytes(of: &system.machine) { raw -> String in
            let bytes = raw.bindMemory(to: CChar.self)
            return String(cString: bytes.baseAddress!)
        }
        return identifier
    }
}
