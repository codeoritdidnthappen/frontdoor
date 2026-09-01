import AVFoundation
import SwiftUI
import UIKit

/// Live preview of the capture session.
///
/// Deliberately a thin wrapper over AVCaptureVideoPreviewLayer and nothing more. The preview is
/// what the operator aims with; it is not the captured image, and no measurement ever reads it.
struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession

    func makeUIView(context: Context) -> PreviewView {
        let view = PreviewView()
        view.previewLayer.session = session
        view.previewLayer.videoGravity = .resizeAspectFill
        return view
    }

    func updateUIView(_ uiView: PreviewView, context: Context) {
        uiView.previewLayer.session = session
    }

    final class PreviewView: UIView {
        override static var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }

        var previewLayer: AVCaptureVideoPreviewLayer {
            // Safe: layerClass above guarantees the type.
            layer as! AVCaptureVideoPreviewLayer
        }
    }
}
