import ImageIO
import UniformTypeIdentifiers
import XCTest
@testable import FrontdoorCapture

/// Tests for reading a photo taken outside this app (D-034, TICK-027 / #31).
///
/// The value at risk is `captured_at`. If a photo with no date were imported anyway, the record
/// would say the entrance was seen at import time — which is a wrong answer in the field that
/// says when it was seen, and worse than having no photo.
final class ImportedPhotoTests: XCTestCase {

    /// A real JPEG with whatever EXIF/TIFF the test asks for, built through ImageIO so the
    /// reader is exercised against the same encoding a camera produces.
    private func jpeg(exif: [CFString: Any]? = nil, tiff: [CFString: Any]? = nil,
                      orientation: Int? = nil,
                      width: Int = 8, height: Int = 6) -> Data {
        let bytes = [UInt8](repeating: 200, count: width * height * 4)
        let provider = CGDataProvider(data: Data(bytes) as CFData)!
        let image = CGImage(
            width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 32,
            bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipLast.rawValue),
            provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent)!

        let out = NSMutableData()
        let dest = CGImageDestinationCreateWithData(
            out, UTType.jpeg.identifier as CFString, 1, nil)!
        var props: [CFString: Any] = [:]
        if let exif { props[kCGImagePropertyExifDictionary] = exif }
        if let tiff { props[kCGImagePropertyTIFFDictionary] = tiff }
        if let orientation { props[kCGImagePropertyOrientation] = orientation }
        CGImageDestinationAddImage(dest, image, props as CFDictionary)
        CGImageDestinationFinalize(dest)
        return out as Data
    }

    private func details(_ data: Data, zone: TimeZone = TimeZone(secondsFromGMT: 0)!)
        -> ImportedPhoto.Details? {
        guard case .success(let d) = ImportedPhoto.read(data, timeZone: zone) else { return nil }
        return d
    }

    // MARK: - the date

    func testAPhotoWithAnExifDateAndModelIsRead() throws {
        let data = jpeg(exif: [kCGImagePropertyExifDateTimeOriginal: "2026:09:01 14:22:31"],
                        tiff: [kCGImagePropertyTIFFModel: "iPhone 17 Pro"])
        let d = try XCTUnwrap(details(data))
        XCTAssertEqual(d.capturedAt, "2026-09-01T14:22:31Z")
        XCTAssertEqual(d.deviceModel, "iPhone 17 Pro")
        XCTAssertEqual(d.pixelWidth, 8)
        XCTAssertEqual(d.pixelHeight, 6)
    }

    func testAPhotoWithNoDateIsRefusedRatherThanDatedToNow() {
        let data = jpeg(tiff: [kCGImagePropertyTIFFModel: "iPhone 17 Pro"])
        guard case .failure(.noCaptureDate) = ImportedPhoto.read(data) else {
            return XCTFail("a photo with no capture date must be refused")
        }
    }

    func testAPhotoWithNoModelIsRefused() {
        let data = jpeg(exif: [kCGImagePropertyExifDateTimeOriginal: "2026:09:01 14:22:31"])
        guard case .failure(.noDeviceModel) = ImportedPhoto.read(data) else {
            return XCTFail("a photo that does not say what took it must be refused")
        }
    }

    func testSomethingThatIsNotAnImageIsRefused() {
        guard case .failure(.notAnImage) = ImportedPhoto.read(Data("not a photo".utf8)) else {
            return XCTFail("expected notAnImage")
        }
    }

    // MARK: - timezone handling, which is where a plausible wrong answer would come from

    func testAnExifOffsetIsHonouredOverTheDeviceZone() {
        // EXIF writes local time with no zone. When the file carries OffsetTimeOriginal, that is
        // the truth, and the device's current zone -- which may be a flight away -- is not.
        let data = jpeg(exif: [
            kCGImagePropertyExifDateTimeOriginal: "2026:09:01 14:22:31",
            kCGImagePropertyExifOffsetTimeOriginal: "+02:00",
        ], tiff: [kCGImagePropertyTIFFModel: "iPhone 17 Pro"])
        XCTAssertEqual(details(data, zone: TimeZone(secondsFromGMT: -25200)!)?.capturedAt,
                       "2026-09-01T12:22:31Z")
    }

    func testWithoutAnOffsetTheGivenZoneIsUsed() {
        let data = jpeg(exif: [kCGImagePropertyExifDateTimeOriginal: "2026:09:01 14:22:31"],
                        tiff: [kCGImagePropertyTIFFModel: "iPhone 17 Pro"])
        // -07:00 local becomes 21:22:31Z.
        XCTAssertEqual(details(data, zone: TimeZone(secondsFromGMT: -25200)!)?.capturedAt,
                       "2026-09-01T21:22:31Z")
    }

    func testTheTimestampIsTheSpellingTheSchemaPins() throws {
        let data = jpeg(exif: [kCGImagePropertyExifDateTimeOriginal: "2026:09:01 04:02:03"],
                        tiff: [kCGImagePropertyTIFFModel: "iPhone 17 Pro"])
        let stamp = try XCTUnwrap(details(data)?.capturedAt)
        // Zero padded, seconds resolution, Z. The schema rejects an offset, so producing one
        // here would write a sidecar the validator refuses.
        XCTAssertEqual(stamp, "2026-09-01T04:02:03Z")
        XCTAssertTrue(stamp.hasSuffix("Z"))
    }

    // MARK: - the offset parser on its own

    func testOffsetParsing() {
        XCTAssertEqual(ImportedPhoto.zone(from: "+02:00")?.secondsFromGMT(), 7200)
        XCTAssertEqual(ImportedPhoto.zone(from: "-05:30")?.secondsFromGMT(), -19800)
        for bad in ["", "+2:00", "02:00", "+02:60", "+24:00", "abcdef", "+02:0"] {
            XCTAssertNil(ImportedPhoto.zone(from: bad), "\(bad) should not parse")
        }
    }

    func testAMalformedExifDateIsRefusedRatherThanGuessed() {
        let data = jpeg(exif: [kCGImagePropertyExifDateTimeOriginal: "not a date"],
                        tiff: [kCGImagePropertyTIFFModel: "iPhone 17 Pro"])
        guard case .failure(.noCaptureDate) = ImportedPhoto.read(data) else {
            return XCTFail("an unparseable date must be refused, not coerced")
        }
    }
}

extension ImportedPhotoTests {

    func testATiffDateAloneIsNotAcceptedAsACaptureDate() {
        // TIFF tag 306 is the file's last-modified time. A photo re-saved by an editor, or one
        // that came through an app which stripped DateTimeOriginal while writing its own DateTime,
        // would otherwise import with a handling time in captured_at -- indistinguishable
        // downstream from a real one.
        let data = jpegForExtension(tiff: [
            kCGImagePropertyTIFFDateTime: "2026:09:01 14:22:31",
            kCGImagePropertyTIFFModel: "iPhone 17 Pro",
        ])
        guard case .failure(.noCaptureDate) = ImportedPhoto.read(data) else {
            return XCTFail("a TIFF DateTime is a file time, not a capture time")
        }
    }

    func testTheExtensionFollowsTheActualFormat() {
        // PhotosPicker returns the ORIGINAL representation: HEIC on an iPhone, PNG for a
        // screenshot. Writing those as .jpg names a file for a format it does not hold.
        XCTAssertEqual(ImportedPhoto.extension(for: "public.heic"), "heic")
        XCTAssertEqual(ImportedPhoto.extension(for: "public.png"), "png")
        XCTAssertEqual(ImportedPhoto.extension(for: "public.jpeg"), "jpeg")
        // Only a genuinely unknown type falls back.
        XCTAssertEqual(ImportedPhoto.extension(for: nil), "jpg")
        XCTAssertEqual(ImportedPhoto.extension(for: "not.a.real.uti"), "jpg")
    }

    func testAReadPhotoReportsItsOwnFormat() throws {
        let data = jpegForExtension(exif: [kCGImagePropertyExifDateTimeOriginal: "2026:09:01 14:22:31"],
                                    tiff: [kCGImagePropertyTIFFModel: "iPhone 17 Pro"])
        guard case .success(let d) = ImportedPhoto.read(data) else {
            return XCTFail("expected a readable photo")
        }
        XCTAssertEqual(d.fileExtension, "jpeg")
    }

    /// Same builder as the main suite; named separately so the extension can reach it.
    private func jpegForExtension(exif: [CFString: Any]? = nil,
                                  tiff: [CFString: Any]? = nil) -> Data {
        let width = 8, height = 6
        let bytes = [UInt8](repeating: 200, count: width * height * 4)
        let provider = CGDataProvider(data: Data(bytes) as CFData)!
        let image = CGImage(
            width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 32,
            bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipLast.rawValue),
            provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent)!
        let out = NSMutableData()
        let dest = CGImageDestinationCreateWithData(
            out, UTType.jpeg.identifier as CFString, 1, nil)!
        var props: [CFString: Any] = [:]
        if let exif { props[kCGImagePropertyExifDictionary] = exif }
        if let tiff { props[kCGImagePropertyTIFFDictionary] = tiff }
        CGImageDestinationAddImage(dest, image, props as CFDictionary)
        CGImageDestinationFinalize(dest)
        return out as Data
    }
}

extension ImportedPhotoTests {

    // MARK: - which way the pixels are stored

    /// An imported photo carries its own orientation, and the record must not invent one: the
    /// sidecar's width, height and ROI points are all in the stored grid, so a reader needs to be
    /// told whether that grid is a quarter turn from upright.
    func testTheStoredOrientationIsRead() throws {
        let data = jpeg(exif: [kCGImagePropertyExifDateTimeOriginal: "2026:09:01 14:22:31"],
                        tiff: [kCGImagePropertyTIFFModel: "iPhone 17 Pro"],
                        orientation: 6)
        let d = try XCTUnwrap(details(data))
        XCTAssertEqual(d.exifOrientation, 6)
    }

    /// The one default in this reader that is not a guess: EXIF defines an absent tag as 1.
    /// Every other missing field is a refusal, so this is stated rather than assumed.
    func testAPhotoWithNoOrientationTagReadsAsUpright() throws {
        let data = jpeg(exif: [kCGImagePropertyExifDateTimeOriginal: "2026:09:01 14:22:31"],
                        tiff: [kCGImagePropertyTIFFModel: "iPhone 17 Pro"])
        let d = try XCTUnwrap(details(data))
        XCTAssertEqual(d.exifOrientation, 1)
    }
}
