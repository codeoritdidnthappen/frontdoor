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
    var pixelWidth: Int
    var pixelHeight: Int
    var intrinsics: CameraIntrinsics
    var gravity: GravitySample
    /// Hardware identifier, e.g. `iPhone17,1` — not the marketing name, which collapses variants
    /// that have different cameras. Per-device effects are analysable later (ASM-1).
    var deviceModel: String
    /// e.g. `builtInWideAngleCamera`. Fixed by D-014, recorded so the record proves it.
    /// The OPTICS that took the picture. Always the 1x main lens, because a frame taken on any
    /// other is refused -- the zoom check compares against the device's main-lens factor.
    var lens: String
    /// The AVFoundation device type actually opened. Not the same as `lens`: on both team phones
    /// the main lens is reached through builtInDualWideCamera, since the bare wide camera delivers
    /// no calibration data and cannot produce a measurable frame at all (TICK-020). Recording only
    /// the lens name would describe a capture that could not have happened.
    var captureDevice: String
    var zoomFactor: Double
    /// UTC RFC 3339, sampled at the shutter press. The schema requires `Z`; offsets are rejected so
    /// capture time has one spelling.
    var capturedAt: String
    /// Metadata for the quarantined depth map, or nil when the device or the frame produced none.
    /// Never nil-checked to decide anything about the measurement (D-020).
    var depth: DepthRecord?
    /// The entrance this capture is of, and the caliper reading that is true of it. Not optional:
    /// a capture with no ground truth cannot be saved (TICK-024), and making that unrepresentable
    /// is stronger than checking for it.
    var entrance: Entrance
    /// The stratification variables this frame was taken under.
    var conditions: ConditionTags
    /// The six points Arm A measures from, marked after the shutter (TICK-026). Optional on the
    /// record only because it is filled in a step later; a frame leaves review with all six or is
    /// discarded, so nothing reaches the sidecar without them.
    var roi: ROITaps?
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
    /// The session stopped or was reconfigured between the shutter press and the capture itself.
    case sessionNotReady
    case sensorResolutionUnknown
    case notFullResolution(delivered: String, sensor: String)
    case captureTimeUnusable(String)
    case noImageData
    case noCalibrationData
    case unusableCalibrationData
    case zoomNotMainLens(factor: Double, expected: Double)
    case noGravitySample
    case gravityImplausible(Double)

    /// Shown verbatim to an operator standing at an entrance.
    var message: String {
        switch self {
        case .sessionNotReady:
            return """
            The camera stopped being available between the shutter press and the capture, so \
            nothing was recorded. Reopen the viewfinder and take the shot again.
            """
        case .sensorResolutionUnknown:
            return """
            The camera did not report its full resolution, so this frame cannot be confirmed \
            uncropped. Nothing was recorded; reopen the viewfinder and try again.
            """
        case .notFullResolution(let delivered, let sensor):
            return """
            The frame came back at \(delivered), a different shape from the sensor's \(sensor), \
            so it is cropped and its intrinsics would not describe it. Nothing was recorded; \
            check that no zoom or crop is applied and take the shot again.
            """
        case .captureTimeUnusable(let value):
            return """
            The capture time \(value) is not a UTC timestamp, so this frame could not be placed \
            in sequence. Nothing was recorded.
            """
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
        case .zoomNotMainLens(let factor, let expected):
            return """
            Zoom was \(String(format: "%.2f", factor)), not the \(String(format: "%.2f", expected)) \
            this camera uses for its 1x main lens. Captures must be on the main lens with no crop, \
            or the intrinsics travelling with the frame are wrong. Nothing was recorded.
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
        pixelWidth: Int,
        pixelHeight: Int,
        intrinsics: CameraIntrinsics?,
        hadCalibrationData: Bool,
        gravity: GravitySample?,
        deviceModel: String,
        lens: String,
        captureDevice: String,
        zoomFactor: Double,
        /// The factor at which the 1x main lens exposes on THIS camera. 1.0 on a physical wide
        /// device; the first switch-over factor on a virtual one, which is 2.00 on both team
        /// phones. Passed in rather than assumed, because the number that means "main lens" is a
        /// property of the device, not a constant.
        mainLensZoomFactor: Double,
        capturedAt: String,
        sensorWidth: Int?,
        sensorHeight: Int?,
        entrance: Entrance,
        conditions: ConditionTags,
        depth: DepthRecord? = nil
    ) -> Result<CaptureRecord, CaptureRejected> {
        guard pixelWidth > 0, pixelHeight > 0 else { return .failure(.noImageData) }
        guard hadCalibrationData else { return .failure(.noCalibrationData) }
        guard let intrinsics else { return .failure(.unusableCalibrationData) }
        // Compared against a tolerance rather than !=: videoZoomFactor is a float the system may
        // return as 2.0000001, and rejecting a capture over that would be a lie.
        //
        // Against the device's main-lens factor, not the literal 1.0. On builtInDualWideCamera the
        // scale is relative to the ultra-wide, so the main lens is at 2.00 -- demanding 1.0 there
        // would reject every measurable frame, and accepting 1.0 would silently accept the
        // ultra-wide's ~120-degree glass.
        guard abs(zoomFactor - mainLensZoomFactor) < 0.001 else {
            return .failure(.zoomNotMainLens(factor: zoomFactor, expected: mainLensZoomFactor))
        }
        guard let gravity else { return .failure(.noGravitySample) }
        guard gravity.isPlausible else { return .failure(.gravityImplausible(gravity.magnitude)) }
        // TICK-022 AC3: no crop and no digital zoom. Zoom pinned to 1.0 is not a substitute --
        // maxPhotoDimensions can be set below what the format can deliver, and a cropped still
        // looks uncropped while its intrinsics describe a grid it does not have.
        //
        // An unknown maximum is not a pass: it cannot confirm anything, and accepting it silently
        // is how this check would stop meaning something.
        guard let sensorWidth, let sensorHeight, sensorWidth > 0, sensorHeight > 0 else {
            return .failure(.sensorResolutionUnknown)
        }
        // Compared by ASPECT, not by pixel count. A 48MP sensor delivers a binned 4032x3024 frame
        // against a 8064x6048 maximum -- confirmed on iPhone17,3 by TICK-020's probe, which
        // requested 8064x6048 and was given 4032x3024. That frame is the FULL field of view, not a
        // crop: same 4:3 geometry, and CameraIntrinsics.from already rescales fx, fy, cx and cy
        // onto whichever grid arrived. Requiring equal pixel counts would refuse every capture on
        // both team phones while proving nothing about cropping, which is what AC3 is for.
        //
        // A crop changes the field of view and therefore the aspect ratio; that is what this
        // catches. The tolerance absorbs the odd-pixel rounding in dimensions like 5712x4284.
        let deliveredAspect = Double(pixelWidth) / Double(pixelHeight)
        let sensorAspect = Double(sensorWidth) / Double(sensorHeight)
        guard abs(deliveredAspect - sensorAspect) <= 0.01 else {
            return .failure(.notFullResolution(
                delivered: "\(pixelWidth)x\(pixelHeight)",
                sensor: "\(sensorWidth)x\(sensorHeight)"
            ))
        }
        // Shape alone is not enough: a half-size frame is uncropped and still costs precision the
        // measurement cannot get back, since every ROI tap lands on a coarser grid.
        //
        // The floor is half the sensor's linear dimension, which is not arbitrary -- it is exactly
        // one binning step. A 48MP sensor reads out 8064x6048 or bins to 4032x3024, and TICK-020's
        // probe saw the second on iPhone17,3. Anything smaller than that is not a readout mode; it
        // is the output having been configured below what the format offers, which is the case
        // AC3 exists to catch. Upscaling past the sensor is likewise not something a camera does.
        guard pixelWidth <= sensorWidth, pixelHeight <= sensorHeight,
              pixelWidth * 2 >= sensorWidth, pixelHeight * 2 >= sensorHeight else {
            return .failure(.notFullResolution(
                delivered: "\(pixelWidth)x\(pixelHeight)",
                sensor: "\(sensorWidth)x\(sensorHeight)"
            ))
        }
        guard CaptureValidation.isUTCRFC3339(capturedAt) else {
            return .failure(.captureTimeUnusable(capturedAt))
        }

        return .success(CaptureRecord(
            pixelWidth: pixelWidth,
            pixelHeight: pixelHeight,
            intrinsics: intrinsics,
            gravity: gravity,
            deviceModel: deviceModel,
            lens: lens,
            captureDevice: captureDevice,
            zoomFactor: zoomFactor,
            capturedAt: capturedAt,
            depth: depth,
            entrance: entrance,
            conditions: conditions
        ))
    }

    /// The schema requires UTC RFC 3339 with a literal `Z`; offsets are rejected so capture time
    /// has one spelling. Checked rather than trusted, because a formatter carrying the device's
    /// locale or time zone produces a plausible string the schema refuses after the entrance has
    /// already been shot.
    static func isUTCRFC3339(_ value: String) -> Bool {
        let pattern = #"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"#
        return value.range(of: pattern, options: .regularExpression) != nil
    }

    /// UTC RFC 3339 for an instant, in the one spelling the schema accepts.
    static func timestamp(for date: Date) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        return formatter.string(from: date)
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
