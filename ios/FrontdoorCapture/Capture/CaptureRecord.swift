import Foundation
import simd

/// Camera intrinsics for one specific frame (D-015). Not "the camera's intrinsics" — they are a
/// property of the frame, and travel with it or the frame is unusable.
struct Intrinsics: Equatable {
    var fx: Double
    var fy: Double
    var cx: Double
    var cy: Double
    /// The pixel dimensions the matrix is expressed against. A matrix read against the wrong
    /// reference is silently wrong rather than obviously wrong, which is why it is carried.
    var referenceWidth: Int
    var referenceHeight: Int
    /// Packed `Float` coefficients from `AVCameraCalibrationData.lensDistortionLookupTable`.
    /// Recorded here for the sidecar; the app never applies them — undistortion is TICK-042.
    var distortionLookupTable: [Float]
    /// Entry count of the table. Derived, so a log line cannot drift from the retained values.
    var distortionTableEntries: Int { distortionLookupTable.count }

    /// Unpack AVFoundation's packed lookup table. Remainder bytes shorter than one `Float` are
    /// dropped — the same truncation the previous count-only path used.
    static func lookupTable(fromPacked data: Data?) -> [Float] {
        guard let data, data.count >= MemoryLayout<Float>.size else { return [] }
        let count = data.count / MemoryLayout<Float>.size
        return data.withUnsafeBytes { raw in
            Array(raw.bindMemory(to: Float.self).prefix(count))
        }
    }
}

/// Everything one shutter press must produce for the record. The sidecar file is TICK-028; this
/// is the value it will be written from.
struct CaptureRecord: Equatable {
    var captureId: UUID
    var capturedAt: Date
    var deviceModel: String
    var lens: String
    var pixelWidth: Int
    var pixelHeight: Int
    var intrinsics: Intrinsics
    /// Gravity at the instant of capture, device frame. Makes capture angle a measured quantity
    /// rather than an operator's estimate.
    var gravity: SIMD3<Double>
}

/// Why a capture was refused. Every case means the frame cannot be used by the method, so it is
/// discarded rather than stored — a record that looks complete but is not is worse than no record.
enum CaptureRejection: Equatable {
    case zoomNotOne(Double)
    case missingCalibration
    case missingGravity
    case gravityImplausible(magnitude: Double)
    case notFullResolution(delivered: String, expected: String)

    var message: String {
        switch self {
        case .zoomNotOne(let factor):
            return String(
                format: """
                Discarded: digital zoom was %.2fx, not 1.0x. Capture geometry is fixed at the 1x \
                main lens (D-014); a zoomed frame invalidates the intrinsics travelling with it.
                """, factor
            )
        case .missingCalibration:
            return """
            Discarded: the camera delivered no calibration data for this frame. Without intrinsics \
            the frame cannot be undistorted and is unusable by every arm, so it is not kept.
            """
        case .missingGravity:
            return """
            Discarded: no gravity vector at the instant of capture. Capture angle would become an \
            operator's estimate rather than a measurement.
            """
        case .gravityImplausible(let magnitude):
            return String(
                format: """
                Discarded: gravity magnitude was %.3f g, not close to 1.0. Motion updates were \
                probably not running, so the vector cannot be trusted.
                """, magnitude
            )
        case .notFullResolution(let delivered, let expected):
            return """
            Discarded: the still was \(delivered) but the sensor offers \(expected). A cropped or \
            downscaled frame changes the pixel scale the error budget is counted in.
            """
        }
    }
}

/// Pure validation, deliberately separated from AVFoundation so it can be tested without a camera.
/// Every rule here corresponds to a way a frame can look fine and be useless.
enum CaptureValidator {
    /// Gravity magnitude must be within 5% of 1 g. Outside that, device motion was not really
    /// running and the vector is noise wearing the shape of a measurement.
    static let gravityTolerance = 0.05

    static func rejection(
        zoomFactor: Double,
        intrinsics: Intrinsics?,
        gravity: SIMD3<Double>?,
        deliveredWidth: Int,
        deliveredHeight: Int,
        sensorWidth: Int?,
        sensorHeight: Int?
    ) -> CaptureRejection? {
        guard abs(zoomFactor - 1.0) < 0.001 else { return .zoomNotOne(zoomFactor) }
        guard intrinsics != nil else { return .missingCalibration }
        guard let gravity else { return .missingGravity }

        let magnitude = simd_length(gravity)
        guard abs(magnitude - 1.0) <= gravityTolerance else {
            return .gravityImplausible(magnitude: magnitude)
        }

        // Only comparable when the sensor maximum is known; an unknown maximum is not a rejection,
        // because refusing every capture on a device we cannot interrogate helps nobody.
        if let sensorWidth, let sensorHeight,
            deliveredWidth != sensorWidth || deliveredHeight != sensorHeight {
            return .notFullResolution(
                delivered: "\(deliveredWidth)x\(deliveredHeight)",
                expected: "\(sensorWidth)x\(sensorHeight)"
            )
        }
        return nil
    }
}
