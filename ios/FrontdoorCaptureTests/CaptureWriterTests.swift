import CryptoKit
import XCTest
@testable import FrontdoorCapture

/// TICK-028: one capture writes one image, one optional depth map, and one sidecar.
final class CaptureWriterTests: XCTestCase {

    private var directory: URL!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("writer-\(UUID().uuidString)")
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    private func record(roi: ROITaps? = ROITaps(
        thresholdTop: PixelPoint(x: 1010, y: 1400),
        thresholdBottom: PixelPoint(x: 1012, y: 1480),
        cardCorners: [
            PixelPoint(x: 900, y: 1500), PixelPoint(x: 1100, y: 1500),
            PixelPoint(x: 1100, y: 1620), PixelPoint(x: 900, y: 1620),
        ]),
        table: Data? = Data(repeating: 0, count: 42 * MemoryLayout<Float>.size),
        depth: DepthRecord? = nil
    ) -> CaptureRecord {
        CaptureRecord(
            captureId: "3F2504E0-4F89-11D3-9A0C-0305E82C3301",
            pixelWidth: 4032, pixelHeight: 3024,
            intrinsics: CameraIntrinsics(
                fx: 2792.0, fy: 2792.0, cx: 2037.2, cy: 1499.0,
                lensDistortionLookupTable: table,
                lensDistortionCenterX: 2016.4, lensDistortionCenterY: 1512.7),
            gravity: GravitySample(x: 0.02, y: -0.98, z: -0.19),
            deviceModel: "iPhone17,3",
            lens: "builtInWideAngleCamera",
            captureDevice: "builtInDualWideCamera",
            zoomFactor: 2.0,
            capturedAt: "2026-09-02T14:22:31Z",
            depth: depth,
            entrance: Entrance(
                id: "E-014", riseInches: 0.75, instrument: "digital caliper", split: .dev),
            conditions: ConditionTags(
                distanceM: 2.0, lighting: .overcast, surface: .concrete,
                occlusion: Occlusion.none, cardPlacement: .vertical),
            roi: roi)
    }

    // MARK: complete or nothing (AC5)

    /// A frame with no taps is not a partial record to repair later: no arm can measure it, and a
    /// row nothing can use is indistinguishable from a good one once it is in the dataset.
    func testACaptureWithoutTapsWritesNothing() throws {
        let result = CaptureWriter.write(
            record(roi: nil), imageData: Data("jpeg".utf8), depthData: nil, into: directory)
        guard case .failure(let failure) = result else {
            return XCTFail("a capture with no ROI taps must not be written")
        }
        XCTAssertTrue(failure.message.contains("no ROI taps"), failure.message)
        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.path),
                       "nothing at all should have been written")
    }

    /// Without a distortion table the taps cannot be undistorted, so Arms A and A-prime cannot run
    /// on the frame at all (#36 AC5).
    func testACaptureWithoutADistortionTableWritesNothing() throws {
        let result = CaptureWriter.write(
            record(table: nil), imageData: Data("jpeg".utf8), depthData: nil, into: directory)
        guard case .failure(let failure) = result else {
            return XCTFail("a capture with no distortion table must not be written")
        }
        XCTAssertTrue(failure.message.contains("distortion table"), failure.message)
        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.path))
    }

    // MARK: hashes over the written bytes (AC2)

    func testHashesAreOverWhatReachedTheDisk() throws {
        let image = Data("a real jpeg would go here".utf8)
        let written = try CaptureWriter.write(
            record(), imageData: image, depthData: nil, into: directory).get()

        let onDisk = try Data(contentsOf: written.imageURL)
        let sidecar = try JSONSerialization.jsonObject(
            with: Data(contentsOf: written.sidecarURL)) as! [String: Any]
        let image_ = sidecar["image"] as! [String: Any]
        XCTAssertEqual(image_["sha256"] as? String, CaptureWriter.sha256(onDisk))
        XCTAssertEqual(image_["width"] as? Int, 4032)
        XCTAssertEqual(image_["path"] as? String, written.imageURL.lastPathComponent)
    }

    // MARK: ordering (AC4)

    /// The sidecar is what makes a capture real. It must not exist before the files it vouches
    /// for, or a crash between the two leaves a row pointing at a truncated image.
    func testTheSidecarIsWrittenAfterTheFilesItDescribes() throws {
        let written = try CaptureWriter.write(
            record(), imageData: Data("jpeg".utf8), depthData: Data("depth".utf8),
            into: directory).get()

        let attributes = { (url: URL) in
            try! FileManager.default.attributesOfItem(atPath: url.path)[.creationDate] as! Date
        }
        XCTAssertGreaterThanOrEqual(
            attributes(written.sidecarURL), attributes(written.imageURL))
        XCTAssertGreaterThanOrEqual(
            attributes(written.sidecarURL), attributes(try XCTUnwrap(written.depthURL)))
    }

    // MARK: reproducible bytes (AC6)

    func testIdenticalContentProducesIdenticalBytes() throws {
        let a = try CaptureWriter.write(
            record(), imageData: Data("jpeg".utf8), depthData: nil, into: directory).get()
        let second = directory.appendingPathComponent("again")
        let b = try CaptureWriter.write(
            record(), imageData: Data("jpeg".utf8), depthData: nil, into: second).get()
        XCTAssertEqual(a.sidecarBytes, b.sidecarBytes)
    }

    // MARK: depth is optional, never fatal (D-020)

    func testACaptureWithNoDepthStillWrites() throws {
        let written = try CaptureWriter.write(
            record(), imageData: Data("jpeg".utf8), depthData: nil, into: directory).get()
        XCTAssertNil(written.depthURL)
        let json = try JSONSerialization.jsonObject(
            with: Data(contentsOf: written.sidecarURL)) as! [String: Any]
        XCTAssertTrue(json["depth"] is NSNull, "depth must be present and null, not absent")
    }

    /// The golden sidecar the Python suite validates against the committed schema. Regenerated
    /// here so the two languages cannot drift: if Swift starts emitting a shape the schema
    /// rejects, tests/test_written_sidecar.py fails.
    /// Compare, do not regenerate. A test that rewrites its own expectation cannot fail:
    /// the fixture silently became whatever Swift last emitted, so the Python suite was
    /// only ever shown output Swift already agreed with (QA B04). Set
    /// FRONTDOOR_UPDATE_FIXTURES=1 to rewrite deliberately.
    func testGoldenSidecarsMatchTheCommittedFixtures() throws {
        let cases: [(String, DepthRecord?)] = [
            ("written_sidecar.json", nil),
            // The depth shape had NO coverage on either side: every case here passed
            // depth: nil, so the fixture read "depth": null and Python never saw a depth
            // capture. That is how the writer came to emit width/height into an object the
            // schema declares additionalProperties: false (QA B01).
            ("written_sidecar_with_depth.json",
             DepthRecord(
                width: 320, height: 240, sha256: String(repeating: "a", count: 64),
                byteCount: 320 * 240 * 4, isAbsolutelyAccurate: true, isFiltered: false)),
        ]
        for (name, depth) in cases {
            let written = try CaptureWriter.write(
                record(depth: depth),
                imageData: Data("jpeg".utf8),
                depthData: depth == nil ? nil : Data("depth".utf8),
                into: directory.appendingPathComponent(name)).get()
            let golden = Self.fixtures.appendingPathComponent(name)
            // Bootstrap a fixture that does not exist yet, and rewrite on request; otherwise
            // COMPARE. test_written_sidecar.py asserts both files exist, so a fixture that
            // never got committed fails CI rather than quietly regenerating itself here.
            let missing = !FileManager.default.fileExists(atPath: golden.path)
            if missing || ProcessInfo.processInfo.environment["FRONTDOOR_UPDATE_FIXTURES"] == "1" {
                try written.sidecarBytes.write(to: golden, options: .atomic)
                continue
            }
            let committed = try Data(contentsOf: golden)
            XCTAssertEqual(
                String(decoding: written.sidecarBytes, as: UTF8.self),
                String(decoding: committed, as: UTF8.self),
                "\(name) drifted. Re-run with FRONTDOOR_UPDATE_FIXTURES=1 if the change is intended.")
        }
    }

    private static var fixtures: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("tests/fixtures")
    }

    /// The shape that had no test at all: a real depth capture (QA B01).
    func testADepthCaptureWritesOnlyPathAndSha256() throws {
        let written = try CaptureWriter.write(
            record(depth: DepthRecord(
                width: 320, height: 240, sha256: String(repeating: "a", count: 64),
                byteCount: 320 * 240 * 4, isAbsolutelyAccurate: true, isFiltered: false)),
            imageData: Data("jpeg".utf8), depthData: Data("depth".utf8), into: directory).get()
        let json = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: written.sidecarBytes) as? [String: Any])
        let depth = try XCTUnwrap(json["depth"] as? [String: Any])
        XCTAssertEqual(
            Set(depth.keys), ["path", "sha256"],
            "the schema declares depth additionalProperties: false")
    }

    /// A card is a rectangle; three corners do not determine the homography (QA B03).
    func testACaptureWithoutFourCardCornersWritesNothing() throws {
        let short = ROITaps(
            thresholdTop: PixelPoint(x: 1010, y: 1400),
            thresholdBottom: PixelPoint(x: 1012, y: 1480),
            cardCorners: [PixelPoint(x: 900, y: 1500), PixelPoint(x: 1100, y: 1500)])
        let result = CaptureWriter.write(
            record(roi: short), imageData: Data("jpeg".utf8), depthData: nil, into: directory)
        guard case .failure(.incomplete) = result else {
            return XCTFail("a two-corner ROI must write nothing, got \(result)")
        }
        XCTAssertFalse(
            FileManager.default.fileExists(atPath: directory.path),
            "an incomplete capture must leave no image behind it (AC5)")
    }
}
