import SwiftUI

/// The capture app is the instrument for the whole dataset (D-014), and it is also the Demo Day
/// app once EPIC-03 adds result rendering on top. There is one capture path, so the demo cannot
/// exhibit behaviour the error budget does not characterise (R-11).
@main
struct FrontdoorCaptureApp: App {
    /// The navigation bar is UIKit and only takes a font from the appearance proxy, so this has
    /// to happen before any bar exists.
    init() { EntryMapNavigationAppearance.install() }

    var body: some Scene {
        WindowGroup {
            RootView()
        }
    }
}
