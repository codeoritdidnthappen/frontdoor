import SwiftUI

/// Home and viewfinder are separate screens, so the camera is only on while the operator is
/// actually pointing it at something, and leaving the viewfinder does not mean leaving the app.
struct RootView: View {
    @StateObject private var controller = CaptureController()
    @Environment(\.scenePhase) private var scenePhase
    @State private var isCapturing = false

    var body: some View {
        Group {
            if isCapturing {
                CaptureView(controller: controller) { isCapturing = false }
            } else {
                HomeView(controller: controller) { isCapturing = true }
            }
        }
        .animation(.default, value: isCapturing)
        // Camera authorisation can change while the app is away — the operator taps Open Settings,
        // grants it, and comes back. Re-sample on foreground so the home screen cannot keep
        // showing Denied over a permission that has since been granted.
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { controller.refreshReadiness() }
        }
    }
}
