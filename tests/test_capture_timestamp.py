"""`captured_at` must be the shutter press, not the photo-completion clock (TICK-022).

The Swift tests can only see the value handed to `CaptureValidation.record`; they cannot tell
where it was sampled. Sampling `Date()` inside `photoOutput` would compile, pass every unit test,
and record the moment the encoder finished instead of the moment the operator pressed the shutter
-- off by however long the exposure and encode took. Every reading would be consistently late,
which is exactly the kind of error that survives review because nothing looks wrong.

Checked here rather than in XCTest because CI runs on Linux and has no Xcode, so this is the only
place the rule can be enforced on every pull request.
"""

from pathlib import Path

CONTROLLER = (
    Path(__file__).resolve().parents[1]
    / "ios/FrontdoorCapture/Capture/CaptureController.swift"
)


def test_timestamp_is_sampled_at_the_shutter_not_in_photo_output():
    source = CONTROLLER.read_text(encoding="utf-8")
    capture_photo = source.split("func capturePhoto()", 1)[1].split(
        "private func accept(", 1
    )[0]
    photo_output = source.split("func photoOutput(", 1)[1]

    assert "let capturedAtShutter = Date()" in capture_photo, (
        "capturePhoto() must sample Date() at the shutter, next to gravity and zoom"
    )
    assert "Date()" not in photo_output, (
        "photoOutput must not sample Date(); that clock is the encoder, not the shutter"
    )
    assert "capturedAt: capturedAtShutter" in capture_photo, (
        "the shutter sample must be the value that reaches the record"
    )
