import CoreImage
import Foundation
import ImageIO
import UniformTypeIdentifiers
import Vision

/// Irreversibly removes face and location information before a camera-roll photo is stored.
enum ImportedPhotoPrivacy {

    enum Failure: Error, Equatable {
        case unreadable
        case detectionFailed
        case encodingFailed

        var message: String {
            switch self {
            case .unreadable:
                return "That photo could not be decoded for privacy processing."
            case .detectionFailed:
                return "Faces could not be checked, so the original photo was not imported."
            case .encodingFailed:
                return "The privacy-processed photo could not be saved, so the original was not imported."
            }
        }
    }

    struct Processed: Equatable {
        var data: Data
        var pixelWidth: Int
        var pixelHeight: Int
        var faceCount: Int
    }

    /// Production entry point: Apple Vision detects faces in the orientation-applied pixels.
    static func process(_ data: Data) -> Result<Processed, Failure> {
        guard let image = uprightImage(from: data) else { return .failure(.unreadable) }
        let request = VNDetectFaceRectanglesRequest()
        do {
            try VNImageRequestHandler(cgImage: image, orientation: .up).perform([request])
        } catch {
            return .failure(.detectionFailed)
        }
        return render(image, faceRectangles: request.results?.map(\.boundingBox) ?? [])
    }

    /// Deterministic seam for the unit test: rectangles use Vision's normalized coordinates.
    static func process(
        _ data: Data, normalizedFaceRectangles: [CGRect]
    ) -> Result<Processed, Failure> {
        guard let image = uprightImage(from: data) else { return .failure(.unreadable) }
        return render(image, faceRectangles: normalizedFaceRectangles)
    }

    private static func uprightImage(from data: Data) -> CGImage? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil)
                as? [CFString: Any],
              let width = properties[kCGImagePropertyPixelWidth] as? Int,
              let height = properties[kCGImagePropertyPixelHeight] as? Int
        else { return nil }

        return CGImageSourceCreateThumbnailAtIndex(source, 0, [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: max(width, height),
        ] as CFDictionary)
    }

    private static func render(
        _ image: CGImage, faceRectangles: [CGRect]
    ) -> Result<Processed, Failure> {
        let width = CGFloat(image.width)
        let height = CGFloat(image.height)
        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        var output = CIImage(cgImage: image)

        for normalized in faceRectangles {
            var rectangle = CGRect(
                x: normalized.minX * width,
                y: normalized.minY * height,
                width: normalized.width * width,
                height: normalized.height * height)
            let marginX = rectangle.width * 0.30
            let marginY = rectangle.height * 0.30
            rectangle = rectangle.insetBy(dx: -marginX, dy: -marginY).intersection(bounds)
            guard !rectangle.isNull, rectangle.width >= 1, rectangle.height >= 1,
                  let pixelate = CIFilter(name: "CIPixellate")
            else { continue }
            pixelate.setValue(output, forKey: kCIInputImageKey)
            pixelate.setValue(max(1, rectangle.width / 12), forKey: kCIInputScaleKey)
            pixelate.setValue(
                CIVector(x: rectangle.midX, y: rectangle.midY), forKey: kCIInputCenterKey)
            guard let patch = pixelate.outputImage?.cropped(to: rectangle) else { continue }
            output = patch.composited(over: output)
        }

        let context = CIContext(options: [.cacheIntermediates: false])
        guard let rendered = context.createCGImage(output, from: bounds) else {
            return .failure(.encodingFailed)
        }
        let encoded = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(
            encoded, UTType.jpeg.identifier as CFString, 1, nil)
        else { return .failure(.encodingFailed) }
        CGImageDestinationAddImage(destination, rendered, [
            kCGImageDestinationLossyCompressionQuality: 0.92,
        ] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else {
            return .failure(.encodingFailed)
        }
        return .success(Processed(
            data: encoded as Data,
            pixelWidth: rendered.width,
            pixelHeight: rendered.height,
            faceCount: faceRectangles.count))
    }
}
