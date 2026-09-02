import SwiftUI

/// Home and viewfinder are separate screens, so the camera is only on while the operator is
/// actually pointing it at something, and leaving the viewfinder does not mean leaving the app.
struct RootView: View {
    @StateObject private var controller = CaptureController()
    @StateObject private var entrances = EntranceStore()
    @Environment(\.scenePhase) private var scenePhase
    @State private var isCapturing = false
    @State private var settingUpEntrance = false
    @State private var showingDiagnostics = false

    var body: some View {
        Group {
            if isCapturing {
                CaptureView(controller: controller) { isCapturing = false }
            } else {
                HomeView(controller: controller) {
                    // Truth first, viewfinder second. There is no route to the camera that
                    // skips the entrance ID and the caliper reading (D-018, TICK-024).
                    settingUpEntrance = true
                } onDiagnostics: {
                    showingDiagnostics = true
                }
            }
        }
        .animation(.default, value: isCapturing)
        .sheet(isPresented: $settingUpEntrance) {
            EntranceSetupView(
                store: entrances,
                initialConditions: controller.subject?.conditions
            ) { subject in
                controller.subject = subject
                settingUpEntrance = false
                isCapturing = true
            } onCancel: {
                settingUpEntrance = false
            }
        }
        .sheet(isPresented: $showingDiagnostics) {
            DiagnosticsView { showingDiagnostics = false }
        }
        // Camera authorisation can change while the app is away — the operator taps Open Settings,
        // grants it, and comes back. Re-sample on foreground so the home screen cannot keep
        // showing Denied over a permission that has since been granted.
        .onChange(of: scenePhase) { _, phase in
            if phase == .active {
                controller.refreshReadiness()
                controller.refreshPendingUploads()
            }
        }
    }
}
