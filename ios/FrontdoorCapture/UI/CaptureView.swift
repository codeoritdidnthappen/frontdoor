import SwiftUI

/// The viewfinder. Preview, a shutter, and a way out that is not force-quitting the app.
///
/// The seam for EPIC-03: rendering observes `CaptureController` and adds views alongside this one.
/// It does not reach into the session, so adding the Demo Day result display cannot fork the
/// capture path (R-11).
struct CaptureView: View {
    @ObservedObject var controller: CaptureController
    let onClose: () -> Void

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            switch controller.state {
            case .stopped, .starting:
                ProgressView("Starting the camera")
                    .tint(.white)
                    .foregroundStyle(.white)
            case .unavailable(let reason):
                unavailable(reason)
            case .running:
                viewfinder
            }
        }
        .task { await controller.start() }
    }

    private func unavailable(_ reason: CaptureUnavailable) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle")
                .font(.largeTitle)
            Text("Cannot capture").font(.headline)
            Text(reason.message)
                .font(.callout)
                .multilineTextAlignment(.center)
            HStack(spacing: 12) {
                if reason == .cameraDenied {
                    Button("Open Settings", action: controller.openSystemSettings)
                        .buttonStyle(.bordered)
                }
                Button("Back", action: close).buttonStyle(.borderedProminent)
            }
            .padding(.top, 8)
        }
        .foregroundStyle(.white)
        .padding(32)
    }

    private var viewfinder: some View {
        ZStack(alignment: .bottom) {
            CameraPreview(session: controller.session)
                // CameraPreview is a UIViewRepresentable with an ambiguous ideal size: its layer
                // fills, but its layout box does not, so without this the ZStack sizes to the
                // smaller box and .bottom lands mid-screen.
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .ignoresSafeArea()

            controls
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .overlay(alignment: .topLeading) { closeButton }
    }

    private var closeButton: some View {
        Button(action: close) {
            Label("Close", systemImage: "xmark")
                .labelStyle(.iconOnly)
                .font(.headline)
                .foregroundStyle(.white)
                .frame(width: 44, height: 44)
                .background(.black.opacity(0.45), in: Circle())
        }
        .accessibilityLabel("Close camera")
        .padding(.leading, 20)
        .padding(.top, 12)
    }

    private var controls: some View {
        HStack(alignment: .center) {
            // Last still, held in memory. Proof that a capture actually produced an image rather
            // than only incrementing a counter.
            Group {
                if let thumb = controller.lastThumbnail {
                    Image(uiImage: thumb)
                        .resizable()
                        .scaledToFill()
                        .frame(width: 52, height: 52)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(.white.opacity(0.6)))
                } else {
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(.white.opacity(0.3), style: StrokeStyle(lineWidth: 1, dash: [4]))
                        .frame(width: 52, height: 52)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            Button(action: controller.capturePhoto) {
                Circle()
                    .strokeBorder(.white, lineWidth: 4)
                    .frame(width: 74, height: 74)
                    .background(Circle().fill(.white.opacity(0.25)))
            }
            .accessibilityLabel("Take photo")

            Text("\(controller.photosTaken)")
                .font(.title3.monospacedDigit().weight(.semibold))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity, alignment: .trailing)
        }
        .padding(.horizontal, 24)
        .padding(.top, 16)
        .padding(.bottom, 28)
        .background(.black.opacity(0.45))
    }

    private func close() {
        controller.stop()
        onClose()
    }
}
