import UIKit
import XCTest
@testable import FrontdoorCapture

/// The UIImage.Orientation to EXIF tag 274 mapping the sidecar records.
///
/// This is worth its own test because it is a table nobody can check by reading it, and because a
/// wrong entry does not fail -- it writes a plausible number into a field consumers trust. The two
/// enums are deliberately NOT in the same order: `UIImage.Orientation.down` is case 2 and EXIF 3,
/// so bridging by `rawValue` would be silently off for six of the eight values.
final class ImageOrientationTests: XCTestCase {

    /// The whole table, against the EXIF specification's numbering.
    func testEveryOrientationMapsToItsExifValue() {
        let expected: [(UIImage.Orientation, Int)] = [
            (.up, 1), (.upMirrored, 2), (.down, 3), (.downMirrored, 4),
            (.leftMirrored, 5), (.right, 6), (.rightMirrored, 7), (.left, 8),
        ]
        for (orientation, exif) in expected {
            XCTAssertEqual(exifOrientation(of: orientation), exif,
                           "UIImage.Orientation raw \(orientation.rawValue)")
        }
    }

    /// The case that actually happens, called out so a regression names itself.
    ///
    /// The app is portrait-locked (project.yml, D-014), the camera writes a landscape sensor
    /// buffer, and the file is tagged `.right` so a viewer turns it upright. Every pixel quantity
    /// in the sidecar describes the untagged landscape buffer.
    func testAPortraitHeldCaptureIsSix() {
        XCTAssertEqual(exifOrientation(of: .right), 6)
    }

    /// Bridging by rawValue is the mistake this table exists to avoid; if someone "simplifies" it
    /// back, this is what catches them.
    func testTheMappingIsNotTheRawValuePlusOne() {
        XCTAssertNotEqual(exifOrientation(of: .down), UIImage.Orientation.down.rawValue + 1)
    }
}
