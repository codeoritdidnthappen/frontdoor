"""The requested photo size and the size AC3 checks against must not drift (TICK-022 AC3).

applyConfiguration asks the camera for a maximum; capturePhoto reads a maximum to compare the
delivered frame against. #174 deliberately makes both `device.activeFormat.supportedMaxPhotoDim
ensions.last` -- the active format's ceiling -- rather than comparing against
`output.maxPhotoDimensions`, which would be tautological.

They are two separate reads of the same expression, so nothing but this test stops one from being
edited without the other. Widening only the check to `device.formats` is the dangerous direction:
on a 48MP iPhone the device-wide maximum belongs to a format the `.photo` session never selects,
so every capture would be refused for being smaller than a size the camera was never asked for,
and the app could record nothing at all.

The Swift suite cannot catch this. CaptureValidation is pure and its tests hand it both numbers
directly, so the two sources of truth never meet there.
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

READ = "device.activeFormat.supportedMaxPhotoDimensions.last"


def code() -> str:
    """Source with line comments removed.

    The guard has to be able to name the wrong construct in the prose explaining why it is wrong.
    An earlier ARKit guard matched a bare word and failed the build on the comment describing its
    own rule (#152); this strips comments rather than repeat that.
    """
    source = CONTROLLER.read_text(encoding="utf-8")
    return "\n".join(re.sub(r"//.*", "", line) for line in source.splitlines())


def test_both_sides_read_the_active_format_the_same_way():
    source = code()
    assert source.count("supportedMaxPhotoDimensions") == 2, (
        "expected exactly two reads: the request in applyConfiguration and the check in "
        "capturePhoto. A third is a third source of truth; a first means one side stopped reading"
    )
    assert source.count(READ) == 2, (
        f"both reads must be spelled `{READ}`, or the request and the check can diverge"
    )


def test_the_check_does_not_widen_to_every_format():
    assert "device.formats" not in code(), (
        "comparing against every format's ceiling rejects every capture whenever the active "
        "format is not the device's largest -- the normal case on a 48MP iPhone"
    )
