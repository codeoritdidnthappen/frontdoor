"""captured_at must be the shutter press, not the photo-completion clock (TICK-022).

ARCHITECTURE.md §4 binds ground truth at the shutter press. Gravity is already sampled
there because the completion fires after the phone can move. The capture timestamp is
the same class of value: sampling Date() inside photoOutput would record the encoder
finishing, not the shutter.
"""

from pathlib import Path

CONTROLLER = (
    Path(__file__).resolve().parents[1]
    / "ios"
    / "FrontdoorCapture"
    / "Capture"
    / "CaptureController.swift"
)


def test_timestamp_is_sampled_at_shutter_not_in_photo_output():
    source = CONTROLLER.read_text(encoding="utf-8")
    capture_photo = source.split("func capturePhoto()", 1)[1].split(
        "private final class PhotoCaptureDelegate", 1
    )[0]
    photo_output = source.split("func photoOutput(", 1)[1]

    assert "let capturedAtShutter = Date()" in capture_photo, (
        "capturePhoto() must sample Date() at the shutter, next to gravity and zoom"
    )
    assert "timestamp: Date()" not in photo_output, (
        "photoOutput must not sample Date(); that clock is the encoder, not the shutter"
    )
    assert "timestamp: capturedAt" in photo_output
