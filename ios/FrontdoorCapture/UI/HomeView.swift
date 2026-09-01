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
                    ok: controller.cameraAuthorization != .denied
                        && controller.cameraAuthorization != .restricted,
                    detail: cameraDetail
                )
                Divider().padding(.leading, 48)
                statusRow(
                    "Device motion",
                    ok: controller.motionAvailable,
                    detail: controller.motionAvailable ? "Available" : "Unavailable"
                )
            }
            .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 12))
            .padding(.horizontal, 24)

            if let blocked = controller.blockingReason {
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
            .disabled(controller.blockingReason != nil)
            .padding(.horizontal, 24)

            Text("\(controller.photosTaken) captured this session")
                .font(.footnote.monospacedDigit())
                .foregroundStyle(.secondary)
                .padding(.bottom, 12)
        }
    }

    private var cameraDetail: String {
        switch controller.cameraAuthorization {
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
