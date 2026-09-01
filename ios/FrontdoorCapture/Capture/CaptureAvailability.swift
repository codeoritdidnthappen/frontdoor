import Foundation

/// Why the instrument cannot capture right now. Every case is something an operator standing in
/// front of an entrance needs to act on, so each carries a sentence rather than a code.
enum CaptureUnavailable: Equatable {
    case cameraDenied
    case cameraRestricted
    case noCaptureDevice
    case motionUnavailable
    case configurationFailed(String)
    case interrupted(String)

    /// Shown verbatim. The app degrades to this rather than crashing.
    var message: String {
        switch self {
        case .cameraDenied:
            return """
            Frontdoor cannot use the camera. Grant camera access in Settings, then reopen the app. \
            The camera is the measuring instrument, so there is nothing to fall back to.
            """
        case .cameraRestricted:
            return "Camera access is restricted on this device by a profile or parental control."
        case .noCaptureDevice:
            return """
            No rear wide-angle camera was found. Captures must use the 1x main lens (D-014), so \
            this device cannot be used for the dataset.
            """
        case .motionUnavailable:
            return """
            Device motion is unavailable, so the gravity vector cannot be recorded. Capture angle \
            would become an operator's estimate rather than a measurement.
            """
        case .configurationFailed(let detail):
            return "The capture session could not be configured: \(detail)"
        case .interrupted(let detail):
            return """
            Capture was interrupted: \(detail). Nothing was recorded. Close and reopen the \
            viewfinder once the camera is free.
            """
        }
    }
}
