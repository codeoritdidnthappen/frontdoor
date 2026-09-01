"""The requested photo size and the size AC3 checks against must be one value (TICK-022 AC3).

applyConfiguration asks the camera for a maximum, and CaptureValidation then rejects any frame
smaller than a maximum. If those two read different quantities, they disagree silently until a
device makes them disagree loudly: reading every format's ceiling for the check while requesting
only the active format's rejects *every* capture on a 48MP iPhone, because the device-wide maximum
belongs to a format the `.photo` session never selects. The app would be unable to record anything,
and the operator would be told the camera is delivering less than the sensor.

Nothing in the Swift suite can catch that: CaptureValidation is pure and the tests hand it both
numbers directly, so the two sources of truth never meet. Asserted here instead, where CI runs
without Xcode.
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


def code() -> str:
    """Source with line comments removed.

    The guard has to be able to name the wrong construct in the prose explaining why it is wrong.
    An earlier ARKit guard matched a bare word and failed the build on the comment describing the
    rule (#152); this strips comments rather than repeat that.
    """
    source = CONTROLLER.read_text(encoding="utf-8")
    return "\n".join(re.sub(r"//.*", "", line) for line in source.splitlines())


def test_the_active_format_is_read_in_exactly_one_place():
    assert code().count("supportedMaxPhotoDimensions") == 1, (
        "a second reader is a second source of truth, free to drift from the first"
    )


def test_the_request_and_the_check_share_that_reader():
    source = code()
    assert "static func maxPhotoDimensions(of device: AVCaptureDevice)" in source
    assert "output.maxPhotoDimensions = maxDimensions" in source
    assert "Self.maxPhotoDimensions(of: device)" in source, (
        "applyConfiguration must request through the shared reader"
    )
    assert "maxPhotoDimensions(of: device)\n            .map { SensorResolution" in source, (
        "fullResolution -- what AC3 compares against -- must come from the same reader"
    )


def test_the_check_does_not_reach_past_the_active_format():
    assert "device.formats" not in code(), (
        "comparing against every format's ceiling rejects every capture whenever the active "
        "format is not the device's largest, which is the normal case on a 48MP iPhone"
    )
