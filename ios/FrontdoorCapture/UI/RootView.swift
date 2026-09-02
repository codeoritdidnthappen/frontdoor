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
    @State private var importing = false

    var body: some View {
        Group {
            if isCapturing {
                CaptureView(controller: controller) { isCapturing = false }
            } else {
                HomeView(controller: controller) {
                    // Truth first, viewfinder second. There is no route to the camera that
                    // skips the entrance ID and the caliper reading (D-018, TICK-024).
                    settingUpEntrance = true
                } onImport: {
                    importing = true
                } onDiagnostics: {
                    showingDiagnostics = true
                }
            }
        }
        .animation(.default, value: isCapturing)
        .sheet(isPresented: $settingUpEntrance) {
            EntranceSetupView(
                store: entrances,
                mode: controller.captureMode,
                initialConditions: controller.subject?.conditions
            ) { subject in
                controller.subject = subject
                settingUpEntrance = false
                isCapturing = true
            } onCancel: {
                settingUpEntrance = false
            }
        }
        .sheet(isPresented: $importing) {
            ImportPhotosView(store: entrances, controller: controller) { importing = false }
        }
        // Over the viewfinder, so the operator sees the result beside the doorway they just shot.
        // Dismissing returns them to the shutter rather than out of the session.
        //
        // The reading it is shown beside was a caliper's until D-036 superseded D-003: there is no
        // instrument ground truth, so metrology mode is inert for this study and this sheet has
        // nothing to compare against this week. It stays because A-3 keeps the mode in the app.
        .sheet(item: $controller.measurement) { response in
            ResultView(
                response: response,
                caliperInches: controller.measurementCaliperInches
            ) {
                controller.measurement = nil
            }
        }
        .sheet(isPresented: $showingDiagnostics) {
            DiagnosticsView { showingDiagnostics = false }
        }
        // Camera authorisation can change while the app is away — the operator taps Open Settings,
        // grants it, and comes back. Re-sample on foreground so the home screen cannot keep
        // showing Denied over a permission that has since been granted.
        .task { controller.startDrainingWhenConnected() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active {
                controller.refreshReadiness()
                controller.refreshPendingUploads()
            }
        }
    }
}
