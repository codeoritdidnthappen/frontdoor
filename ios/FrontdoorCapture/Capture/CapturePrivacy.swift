import CoreImage
import Foundation
import ImageIO
import UniformTypeIdentifiers
import Vision

/// Irreversibly removes face and location information from a DEVICE-CAMERA capture (#328).
///
/// The sibling of `ImportedPhotoPrivacy`, and deliberately not the same function. The importer
/// bakes the EXIF rotation into the pixels and drops every tag, which is right for a photo that
/// carries no intrinsics and records `exif_orientation: 1`.
///
/// A camera capture records intrinsics taken from the sensor buffer, and the sidecar schema is
/// explicit about what that means: *"width, height, intrinsics fx/fy/cx/cy, distortion_center and
/// the roi points  are expressed in the grid the file's pixels are STORED in, with this rotation
/// NOT applied."* Rotate the stored pixels and those numbers describe a grid that no longer
/// exists, with nothing to detect it — D-037's bug, reintroduced by the fix for a different one.
///
/// So this one leaves the grid alone and keeps exactly one tag, the orientation. Faces are
/// blurred, every other tag including GPS is dropped, intrinsics stay true, and the stored image
/// still decodes the right way up for the screening model.
enum CapturePrivacy {

    enum Failure: Error, Equatable {
        case unreadable
        case detectionFailed
        case blurFailed
        case encodingFailed

        /// Written for someone at a doorway. Each one ends with the capture NOT being written:
        /// failing closed is the point, so none of these may read as "saved anyway".
        var message: String {
            switch self {
            case .unreadable:
                return "That photo could not be decoded for privacy processing, so it was not saved."
            case .detectionFailed:
                return "Faces could not be checked, so the photo was not saved. Take it again."
            case .blurFailed:
                return "A face in that photo could not be blurred, so it was not saved. "
                    + "Take it again with the doorway clear."
            case .encodingFailed:
                return "The privacy-processed photo could not be encoded, so it was not saved."
            }
        }
    }

    struct Processed: Equatable {
        var data: Data
        var pixelWidth: Int
        var pixelHeight: Int
        /// Faces this step actually BLURRED, counted as each patch is composited.
        ///
        /// It used to be `faceRectangles.count` — the number DETECTED. The two differed exactly
        /// when it mattered, because the blur loop skipped any face it could not process and the
        /// count then asserted that a face left in the clear had been handled. Derived from the
        /// work rather than from the input, so the two cannot drift apart again.
        var blurredFaceCount: Int
    }

    /// Production entry point. `exifOrientation` is the stored image's tag, 1-8.
    static func process(_ data: Data, exifOrientation: Int) -> Result<Processed, Failure> {
        guard let image = rawImage(from: data) else { return .failure(.unreadable) }
        let orientation = CGImagePropertyOrientation(
            rawValue: UInt32(clamping: exifOrientation)) ?? .up
        let request = VNDetectFaceRectanglesRequest()
        do {
            // Detected on the UPRIGHT interpretation, which is what the detector is good at, by
            // handing Vision the raw pixels plus the tag rather than rotating anything.
            try VNImageRequestHandler(cgImage: image, orientation: orientation).perform([request])
        } catch {
            return .failure(.detectionFailed)
        }
        let upright = request.results?.map(\.boundingBox) ?? []
        let inGrid = upright.map { rawRect(fromUpright: $0, exifOrientation: exifOrientation) }
        return render(image, faceRectangles: inGrid, exifOrientation: exifOrientation)
    }

    /// Deterministic seam for tests: rectangles are already in the STORED grid's normalized space,
    /// and **face detection does not run**.
    ///
    /// Two things keep it out of production, because one is not enough. It no longer shares a name
    /// with `process(_:exifOrientation:)`: an overload set where one member silently skips
    /// detection is one argument away from writing an unblurred capture, and the compiler helps
    /// with neither the mistake nor the review. And it is compiled out of a release build
    /// entirely, so a call site that reaches for it there does not build.
    #if DEBUG
    static func processWithoutDetection(
        _ data: Data, exifOrientation: Int, normalizedFaceRectangles: [CGRect]
    ) -> Result<Processed, Failure> {
        guard let image = rawImage(from: data) else { return .failure(.unreadable) }
        return render(image, faceRectangles: normalizedFaceRectangles,
                      exifOrientation: exifOrientation)
    }
    #endif

    /// Map a normalized rect from the upright interpretation back into the stored grid.
    ///
    /// Every corner is mapped and the bounding box taken, rather than transforming origin and size
    /// separately — under a transpose the width and height swap, and a sign error there blurs the
    /// wrong part of the frame while still looking plausible.
    static func rawRect(fromUpright rect: CGRect, exifOrientation: Int) -> CGRect {
        let corners = [
            CGPoint(x: rect.minX, y: rect.minY), CGPoint(x: rect.maxX, y: rect.minY),
            CGPoint(x: rect.minX, y: rect.maxY), CGPoint(x: rect.maxX, y: rect.maxY),
        ].map { rawPoint(fromUpright: $0, exifOrientation: exifOrientation) }
        let xs = corners.map(\.x), ys = corners.map(\.y)
        return CGRect(x: xs.min()!, y: ys.min()!,
                      width: xs.max()! - xs.min()!, height: ys.max()! - ys.min()!)
    }

    /// Normalized, bottom-left origin, both spaces. The inverse of what the EXIF tag asks a viewer
    /// to do: the tag says how to turn the stored grid upright, so this undoes it.
    private static func rawPoint(fromUpright p: CGPoint, exifOrientation: Int) -> CGPoint {
        switch exifOrientation {
        case 2: return CGPoint(x: 1 - p.x, y: p.y)          // mirrored horizontally
        case 3: return CGPoint(x: 1 - p.x, y: 1 - p.y)      // rotated 180
        case 4: return CGPoint(x: p.x, y: 1 - p.y)          // mirrored vertically
        case 5: return CGPoint(x: p.y, y: p.x)              // transposed
        case 6: return CGPoint(x: 1 - p.y, y: p.x)          // stored is rotated 90 CW to display
        case 7: return CGPoint(x: 1 - p.y, y: 1 - p.x)      // transverse
        case 8: return CGPoint(x: p.y, y: 1 - p.x)          // rotated 270 CW to display
        default: return p                                    // 1, and anything out of range
        }
    }

    /// The stored pixels, with NO transform applied. `ImportedPhotoPrivacy` deliberately does the
    /// opposite; see this type's own note for why they differ.
    private static func rawImage(from data: Data) -> CGImage? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
        return CGImageSourceCreateImageAtIndex(source, 0, nil)
    }

    private static func render(
        _ image: CGImage, faceRectangles: [CGRect], exifOrientation: Int
    ) -> Result<Processed, Failure> {
        let width = CGFloat(image.width)
        let height = CGFloat(image.height)
        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        var output = CIImage(cgImage: image)
        var blurred = 0

        for normalized in faceRectangles {
            var rectangle = CGRect(
                x: normalized.minX * width, y: normalized.minY * height,
                width: normalized.width * width, height: normalized.height * height)
            let marginX = rectangle.width * 0.30
            let marginY = rectangle.height * 0.30
            rectangle = rectangle.insetBy(dx: -marginX, dy: -marginY).intersection(bounds)
            // A DETECTED face that cannot be blurred refuses the capture, like every other
            // failure in this file. Both of these used to `continue`: the loop moved on, the
            // frame was written and uploaded with that face in the clear, and `faceCount` said it
            // had been handled. A small or distant face at the edge of the frame is exactly what
            // trips the `>= 1` after the margin intersection, so the case that failed open was
            // the ordinary one, in the path that fills the dataset.
            guard !rectangle.isNull, rectangle.width >= 1, rectangle.height >= 1,
                  let pixelate = CIFilter(name: "CIPixellate")
            else { return .failure(.blurFailed) }
            pixelate.setValue(output, forKey: kCIInputImageKey)
            pixelate.setValue(max(1, rectangle.width / 12), forKey: kCIInputScaleKey)
            pixelate.setValue(
                CIVector(x: rectangle.midX, y: rectangle.midY), forKey: kCIInputCenterKey)
            guard let patch = pixelate.outputImage?.cropped(to: rectangle) else {
                return .failure(.blurFailed)
            }
            output = patch.composited(over: output)
            blurred += 1
        }

        let context = CIContext(options: [.cacheIntermediates: false])
        guard let rendered = context.createCGImage(output, from: bounds) else {
            return .failure(.encodingFailed)
        }
        let encoded = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(
            encoded, UTType.jpeg.identifier as CFString, 1, nil)
        else { return .failure(.encodingFailed) }
        // The ONLY tag carried over. Everything the camera attached -- GPS above all -- is left
        // behind by writing a fresh dictionary rather than editing the original's.
        CGImageDestinationAddImage(destination, rendered, [
            kCGImageDestinationLossyCompressionQuality: 0.92,
            kCGImagePropertyOrientation: exifOrientation,
        ] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { return .failure(.encodingFailed) }
        return .success(Processed(
            data: encoded as Data,
            pixelWidth: rendered.width,
            pixelHeight: rendered.height,
            blurredFaceCount: blurred))
    }
}
