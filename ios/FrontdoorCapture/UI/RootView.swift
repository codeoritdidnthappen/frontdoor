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
    /// Shown before the first scan on this install, and on request afterwards (#275).
    @State private var showingPrimer = false
    /// True when the primer is standing between the operator and the viewfinder, rather than
    /// being read from the home screen. Continuing then goes on to the entrance, not back.
    @State private var primerLeadsToScan = false
    private let primer = ScanPrimer()

    var body: some View {
        Group {
            if isCapturing {
                CaptureView(controller: controller) { isCapturing = false }
            } else {
                HomeView(controller: controller) {
                    // Truth first, viewfinder second. There is no route to the camera that
                    // skips the entrance ID and the caliper reading (D-018, TICK-024).
                    //
                    // The primer comes before even that, once per install, and only for the scan
                    // flow: it describes screening, and metrology is a different protocol (#275).
                    if !controller.captureMode.carriesMetrologyTruth && !primer.hasBeenSeen {
                        primerLeadsToScan = true
                        showingPrimer = true
                    } else {
                        settingUpEntrance = true
                    }
                } onPrimer: {
                    primerLeadsToScan = false
                    showingPrimer = true
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
                // Before the viewfinder opens, so the count on the conditions bar is right on the
                // first frame rather than after the first shutter press.
                controller.refreshSubjectTally()
                settingUpEntrance = false
                isCapturing = true
            } onCancel: {
                settingUpEntrance = false
            }
        }
        // Before the viewfinder, not over it: this is what the operator is about to do, and it
        // is useless read through a live camera preview.
        .sheet(isPresented: $showingPrimer) {
            ScanPrimerView(continueTitle: primerLeadsToScan ? "Start" : "Done") {
                // Marked seen whichever way it was opened. Reading it from the home screen is
                // still having read it, and asking again on the next scan would be nagging.
                primer.markSeen()
                showingPrimer = false
                if primerLeadsToScan { settingUpEntrance = true }
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
        // The scan flow's result surface, over the viewfinder like the measurement sheet. It
        // opens when the photo is SENT, not when the answer arrives, so the checks are named while
        // the server is still reading the photo (#275).
        .sheet(item: $controller.screeningRun) { run in
            ScreeningChecksView(run: run) {
                controller.screeningRun = nil
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
