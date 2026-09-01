import SwiftUI

/// Preview plus a shutter. Nothing else is claimed at this stage (TICK-021).
///
/// The seam for EPIC-03: rendering observes `CaptureController` and adds views alongside this one.
/// It does not reach into the session, so adding the Demo Day result display cannot fork the
/// capture path (R-11).
struct CaptureView: View {
    @StateObject var controller: CaptureController

    init(controller: CaptureController) {
        _controller = StateObject(wrappedValue: controller)
    }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            switch controller.state {
            case .idle:
                ProgressView("Starting the camera")
                    .tint(.white)
                    .foregroundStyle(.white)
            case .unavailable(let reason):
                unavailable(reason)
            case .ready:
                capturing
            }
        }
        .task { await controller.start() }
        .onDisappear(perform: controller.stop)
    }

    private func unavailable(_ reason: CaptureUnavailable) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle")
                .font(.largeTitle)
            Text("Cannot capture")
                .font(.headline)
            Text(reason.message)
                .font(.callout)
                .multilineTextAlignment(.center)
        }
        .foregroundStyle(.white)
        .padding(32)
    }

    private var capturing: some View {
        VStack(spacing: 0) {
            CameraPreview(session: controller.session)
                .ignoresSafeArea(edges: .top)
            HStack {
                Text("\(controller.photosTaken) captured")
                    .font(.footnote.monospacedDigit())
                    .foregroundStyle(.white)
                Spacer()
                Button(action: controller.capturePhoto) {
                    Circle()
                        .strokeBorder(.white, lineWidth: 4)
                        .frame(width: 72, height: 72)
                        .background(Circle().fill(.white.opacity(0.25)))
                }
                .accessibilityLabel("Take photo")
                Spacer()
                // Balances the shutter so it sits centred.
                Text("\(controller.photosTaken) captured")
                    .font(.footnote.monospacedDigit())
                    .foregroundStyle(.clear)
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 20)
        }
    }
}
