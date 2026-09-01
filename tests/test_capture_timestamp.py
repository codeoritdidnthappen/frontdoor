"""captured_at must be the shutter press, not the photo-completion clock (TICK-022).

ARCHITECTURE.md §4 binds ground truth at the shutter press. Gravity is already sampled
there because the completion fires after the phone can move. The capture timestamp is
the same class of value: sampling Date() inside photoOutput would record the encoder
finishing, not the shutter -- every reading consistently late by an amount that varies
with lighting. It would compile, pass every Swift test, and look correct in review,
because CaptureValidation only ever sees the value it is handed and cannot tell where
it came from.

Written by rubanikov for #145, dropped when #144 closed, and required back by #163's
last acceptance criterion. Reapplied against the implementation that landed in #174,
which samples through CaptureValidation.timestamp(for:) rather than a bare Date().
"""

import re
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
        "private func accept(", 1
    )[0]
    # Bounded at the enclosing type's closing brace -- a brace in column 0 -- rather than run to
    # end of file. photoOutput is the last method in this file, so an unbounded slice would scan
    # anything appended below it and blame photoOutput for a Date() nowhere near it.
    photo_output = source.split("func photoOutput(", 1)[1].split("\n}", 1)[0]

    assert re.search(r"let capturedAt = CaptureValidation\.timestamp\(for: Date\(\)\)", capture_photo), (
        "capturePhoto() must sample the clock at the shutter, next to gravity and zoom"
    )
    assert "Date()" not in photo_output, (
        "photoOutput must not read the clock; that instant is the encoder, not the shutter"
    )
    assert "capturedAt: capturedAt" in capture_photo, (
        "the shutter sample must be the value that reaches the record"
    )
