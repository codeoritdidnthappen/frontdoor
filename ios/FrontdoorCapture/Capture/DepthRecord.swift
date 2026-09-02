import AVFoundation
import CoreVideo
import CryptoKit
import Foundation

/// What was recorded about one depth map. Metadata only — no depth *values* live here, and nothing
/// in the app reads one.
///
/// D-020 quarantines depth from the metrology path: it is captured on every entrance, written, and
/// forgotten. The only consumer is the evaluation harness, for the monocular-versus-LiDAR
/// comparison. If depth sits where the method can reach it, it eventually gets used to tune and the
/// comparison stops meaning anything.
struct DepthRecord: Equatable {
    /// Documented for TICK-077, which has to interpret these bytes without asking anyone.
    ///
    /// Always `DepthFloat32`: 32-bit float, one value per pixel, rows tightly packed at
    /// `width * 4` bytes with no padding, in the capture device's native orientation. Converted
    /// from whatever the sensor delivered so the harness reads one format rather than four.
    ///
    /// **The unit is not always metres.** This constant used to say it was. TICK-020 (#24) measured
    /// `accuracy=relative` on both verified phones: the values are stereo-derived and usable for
    /// ordering, not as distances. `isAbsolutelyAccurate` on each record is the only thing that says
    /// which you have, so read that rather than assuming — a relative map treated as metres is a
    /// number in the wrong unit that looks entirely plausible.
    static let pixelFormat = "DepthFloat32"
    static let units = "metres when isAbsolutelyAccurate, otherwise relative"

    var width: Int
    var height: Int
    /// SHA-256 over the tightly packed rows described above — not over the CVPixelBuffer's padded
    /// backing store, whose row stride is a device detail that would make the hash irreproducible.
    var sha256: String
    var byteCount: Int
    /// `absolute` values are real-world distances; `relative` are only usable for ordering. Recorded
    /// rather than acted on: the harness decides what a relative map is worth (R-10).
    var isAbsolutelyAccurate: Bool
    var isFiltered: Bool
}

enum DepthCapture {
    /// Converts to the one documented format and hashes the bytes.
    ///
    /// Returns nil when depth is absent or unreadable. That is not an error: D-020 makes depth a
    /// comparison, never a method input, so its absence must never cost an entrance (TICK-023).
    /// Returns the record AND the bytes it describes. The bytes are what gets written to
    /// disk, so discarding them here meant the only way to produce a depth file later was to
    /// re-derive it -- and a re-derived buffer is not the buffer the hash was taken over.
    static func record(from depthData: AVDepthData?) -> (record: DepthRecord, bytes: Data)? {
        guard let depthData else { return nil }

        let converted: AVDepthData
        if depthData.depthDataType == kCVPixelFormatType_DepthFloat32 {
            converted = depthData
        } else if depthData.availableDepthDataTypes.contains(kCVPixelFormatType_DepthFloat32) {
            converted = depthData.converting(toDepthDataType: kCVPixelFormatType_DepthFloat32)
        } else {
            return nil
        }

        let buffer = converted.depthDataMap
        guard let bytes = tightlyPackedBytes(of: buffer) else { return nil }

        let record = DepthRecord(
            width: CVPixelBufferGetWidth(buffer),
            height: CVPixelBufferGetHeight(buffer),
            sha256: SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined(),
            byteCount: bytes.count,
            isAbsolutelyAccurate: converted.depthDataAccuracy == .absolute,
            isFiltered: converted.isDepthDataFiltered
        )
        return (record, bytes)
    }

    /// Copies row by row, dropping the stride padding CoreVideo adds for alignment. Hashing the
    /// padded buffer would make the digest depend on the device rather than on the depth.
    private static func tightlyPackedBytes(of buffer: CVPixelBuffer) -> Data? {
        CVPixelBufferLockBaseAddress(buffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }

        guard let base = CVPixelBufferGetBaseAddress(buffer) else { return nil }
        let width = CVPixelBufferGetWidth(buffer)
        let height = CVPixelBufferGetHeight(buffer)
        let stride = CVPixelBufferGetBytesPerRow(buffer)
        let rowBytes = width * MemoryLayout<Float32>.size
        guard width > 0, height > 0, stride >= rowBytes else { return nil }

        var out = Data(capacity: rowBytes * height)
        for row in 0..<height {
            let start = base.advanced(by: row * stride)
            out.append(contentsOf: UnsafeRawBufferPointer(start: start, count: rowBytes))
        }
        return out
    }
}
