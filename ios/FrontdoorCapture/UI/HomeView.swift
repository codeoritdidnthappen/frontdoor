import AVFoundation
import SwiftUI

/// Where the app opens. The camera is off until the operator asks for it, so launching the app
/// does not switch on a camera indicator, and there is somewhere to come back to when they stop.
///
/// It also states readiness before anything is tapped. On the two capture phones the answers
/// differ — one has LiDAR, one does not — and an operator at an entrance should not discover that
/// from a viewfinder that will not open.
struct HomeView: View {
    @ObservedObject var controller: CaptureController
    let onStart: () -> Void
    let onDiagnostics: () -> Void

    /// What is still only on this phone, and a way to send it.
    ///
    /// AC6: nobody should leave a field session unsure whether the day's work is safe. "Captured
    /// this session" answers a different question -- it resets on relaunch and counts frames that
    /// may already be uploaded. This counts what would be lost if the phone were.
    @ViewBuilder
    private var pendingRow: some View {
        let pending = controller.pendingUploads
        if pending > 0 {
            VStack(spacing: 6) {
                Text("^[\(pending) capture](inflect: true) on this phone only")
                    .font(.subheadline.weight(.medium))
                Button(controller.isDraining ? "Uploading…" : "Upload now") {
                    Task { await controller.drainQueue() }
                }
                .buttonStyle(.bordered)
                .disabled(controller.isDraining)
                if let outcome = controller.lastDrainMessage {
                    Text(outcome)
                        .font(.footnote)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 24)
                }
            }
            .padding(.top, 4)
        }
    }

    var body: some View {
        VStack(spacing: 28) {
            Spacer()

            VStack(spacing: 8) {
                Image(systemName: "ruler")
                    .font(.system(size: 44, weight: .light))
                Text("Frontdoor")
                    .font(.largeTitle.weight(.semibold))
                Text("Storefront entrance capture")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            VStack(spacing: 0) {
                statusRow(
                    "Camera",
                    ok: controller.readiness.cameraAuthorization != .denied
                        && controller.readiness.cameraAuthorization != .restricted,
                    detail: cameraDetail
                )
                Divider().padding(.leading, 48)
                statusRow(
                    "Device motion",
                    ok: controller.readiness.motionAvailable,
                    detail: controller.readiness.motionAvailable ? "Available" : "Unavailable"
                )
            }
            .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 12))
            .padding(.horizontal, 24)

            if let blocked = controller.readiness.blockingReason {
                VStack(spacing: 12) {
                    Text(blocked.message)
                        .font(.footnote)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.secondary)
                    if blocked == .cameraDenied {
                        Button("Open Settings", action: controller.openSystemSettings)
                            .buttonStyle(.bordered)
                    }
                }
                .padding(.horizontal, 32)
            }

            Spacer()

            Button(action: onStart) {
                Text("Start capture")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
            }
            .buttonStyle(.borderedProminent)
            .disabled(controller.readiness.blockingReason != nil)
            .padding(.horizontal, 24)

            Button("Run capability probe") { onDiagnostics() }
                .font(.footnote)

            Text("\(controller.photosTaken) captured this session")
            pendingRow
                .font(.footnote.monospacedDigit())
                .foregroundStyle(.secondary)
                .padding(.bottom, 12)
        }
    }

    private var cameraDetail: String {
        switch controller.readiness.cameraAuthorization {
        case .authorized: return "Allowed"
        case .notDetermined: return "Will ask on first capture"
        case .denied: return "Denied"
        case .restricted: return "Restricted"
        @unknown default: return "Unknown"
        }
    }

    private func statusRow(_ title: String, ok: Bool, detail: String) -> some View {
        HStack(spacing: 12) {
            Image(systemName: ok ? "checkmark.circle.fill" : "exclamationmark.circle.fill")
                .foregroundStyle(ok ? .green : .orange)
            Text(title)
            Spacer()
            Text(detail)
                .foregroundStyle(.secondary)
        }
        .font(.callout)
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
    }
}
