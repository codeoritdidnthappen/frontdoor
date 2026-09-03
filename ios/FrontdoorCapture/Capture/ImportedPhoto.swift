import Foundation
import ImageIO
import UniformTypeIdentifiers

/// A photo taken outside this app, read well enough to become a capture record (D-034, #31).
///
/// The pivot to plain-photo screening happened after operators had already shot entrances with the
/// stock camera. Those photos exist and are not re-shootable at will, so the app can take them in
/// — but it records only what the file actually says. None of this app's capture metadata is
/// invented for them: no intrinsics, no gravity, no lens, no zoom factor. The schema forbids all
/// of it in `imported` mode rather than merely allowing it to be absent, because a plausible
/// number in one of those fields would be read downstream as a measurement.
enum ImportedPhoto {

    enum Refusal: Error, Equatable {
        case notAnImage
        case noCaptureDate
        case noDeviceModel

        var message: String {
            switch self {
            case .notAnImage:
                return "That file could not be read as a photo."
            case .noCaptureDate:
                return """
                That photo carries no capture date, so there is no honest value for when the \
                entrance was seen. Importing it would date the record to now, which is not when \
                the photo was taken.
                """
            case .noDeviceModel:
                return """
                That photo does not say which device took it, and the record has to name one. \
                A photo re-saved by another app often loses this.
                """
            }
        }
    }

    struct Details: Equatable {
        /// The file extension the bytes actually deserve. `PhotosPicker` hands back the ORIGINAL
        /// representation -- HEIC on an iPhone, PNG for a screenshot -- so writing everything as
        /// `.jpg` would name a file for a format it does not hold. The hash stays honest either
        /// way, but anything dispatching on extension, or a person opening the file, is misled.
        var fileExtension: String
        /// RFC 3339 UTC, from the file's own EXIF, never from the clock at import time.
        var capturedAt: String
        /// Whatever EXIF says took it. A marketing name like "iPhone 17 Pro" rather than the
        /// `iPhone18,1` identifier our own captures record — recorded as found, not translated,
        /// because a translation is a guess and this field is read as fact.
        var deviceModel: String
        var pixelWidth: Int
        var pixelHeight: Int
        var exifOrientation: Int
    }

    /// EXIF writes local time with no zone, so the zone has to come from somewhere. `OffsetTime`
    /// carries it when present; without it the only honest reading is the device's current zone,
    /// which is what the Photos app itself assumes.
    static func read(_ data: Data, timeZone: TimeZone = .current) -> Result<Details, Refusal> {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
        else { return .failure(.notAnImage) }

        guard let width = props[kCGImagePropertyPixelWidth] as? Int,
              let height = props[kCGImagePropertyPixelHeight] as? Int,
              width > 0, height > 0
        else { return .failure(.notAnImage) }

        // Absent means 1 by the EXIF specification -- top-left, nothing to rotate -- so this is
        // the one default here that is not a guess. Every other missing field is a refusal.
        let orientation = props[kCGImagePropertyOrientation] as? Int ?? 1

        let exif = props[kCGImagePropertyExifDictionary] as? [CFString: Any]
        let tiff = props[kCGImagePropertyTIFFDictionary] as? [CFString: Any]

        // EXIF DateTimeOriginal ONLY. TIFF tag 306 (`DateTime`) is the file's last-modified time,
        // not the shutter press: a photo re-saved by an editor, or one that came through a
        // messaging app which stripped DateTimeOriginal while writing its own DateTime, would
        // import with a handling time in `captured_at`. That is the exact failure the refusal
        // below exists to prevent, arriving through the back door and indistinguishable
        // downstream. A photo that cannot say when it was taken is refused instead.
        guard let taken = exif?[kCGImagePropertyExifDateTimeOriginal] as? String,
              let stamp = rfc3339(from: taken,
                                  offset: exif?[kCGImagePropertyExifOffsetTimeOriginal] as? String,
                                  timeZone: timeZone)
        else { return .failure(.noCaptureDate) }

        guard let model = (tiff?[kCGImagePropertyTIFFModel] as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines), !model.isEmpty
        else { return .failure(.noDeviceModel) }

        let uti = CGImageSourceGetType(source) as String?
        return .success(Details(
            fileExtension: Self.extension(for: uti),
            capturedAt: stamp, deviceModel: model,
            pixelWidth: width, pixelHeight: height,
            exifOrientation: orientation))
    }

    /// The extension for a UTI, defaulting to `jpg` only when the type is genuinely unknown.
    static func `extension`(for uti: String?) -> String {
        guard let uti, let type = UTType(uti) else { return "jpg" }
        return type.preferredFilenameExtension ?? "jpg"
    }

    /// EXIF's `yyyy:MM:dd HH:mm:ss` into the UTC spelling the schema pins.
    static func rfc3339(from exif: String, offset: String?, timeZone: TimeZone) -> String? {
        let input = DateFormatter()
        input.locale = Locale(identifier: "en_US_POSIX")
        input.dateFormat = "yyyy:MM:dd HH:mm:ss"
        input.timeZone = offset.flatMap(zone(from:)) ?? timeZone
        guard let date = input.date(from: exif.trimmingCharacters(in: .whitespaces)) else {
            return nil
        }
        let output = DateFormatter()
        output.locale = Locale(identifier: "en_US_POSIX")
        output.dateFormat = "yyyy-MM-dd'T'HH:mm:ss'Z'"
        output.timeZone = TimeZone(secondsFromGMT: 0)
        return output.string(from: date)
    }

    /// `+01:00` / `-05:30` as EXIF writes them.
    static func zone(from offset: String) -> TimeZone? {
        let text = offset.trimmingCharacters(in: .whitespaces)
        guard text.count == 6, let sign = text.first, sign == "+" || sign == "-" else { return nil }
        let parts = text.dropFirst().split(separator: ":")
        guard parts.count == 2, let h = Int(parts[0]), let m = Int(parts[1]),
              (0...23).contains(h), (0...59).contains(m) else { return nil }
        let seconds = (h * 3600 + m * 60) * (sign == "-" ? -1 : 1)
        return TimeZone(secondsFromGMT: seconds)
    }
}


/// What became of one imported photo. A plain enum rather than `Result<Void, Error>` because the
/// refusal is a sentence for the operator, not an error to be thrown.
enum ImportOutcome: Equatable {
    case imported
    case refused(String)
}
