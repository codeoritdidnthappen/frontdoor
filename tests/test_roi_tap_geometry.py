"""The ROI image must be positioned by the same rect the taps are measured against (TICK-026).

ROIValidation.fittedRect returns a CENTRED rect. ROIReviewView draws the still and converts every
tap using it. If the still is instead laid out by the enclosing stack -- scaledToFit inside a
ZStack, whose alignment decides where it lands -- then the drawing and the arithmetic are two
independent opinions about where the image is, and they agree only by luck.

They did not agree. With ZStack(alignment: .topLeading) the image sat at the top while fittedRect
assumed the centre: taps in the upper half were rejected as off-image, and the ones that did land
were converted against a rect the image did not occupy. Both halves were individually correct and
unit-tested, which is exactly why nothing caught it -- it was found by tapping the screen.

Checked here because the Swift tests cover the geometry functions, not the view that uses them,
and CI has no Xcode.
"""

import re
from pathlib import Path

VIEW = (
    Path(__file__).resolve().parents[1]
    / "ios"
    / "FrontdoorCapture"
    / "UI"
    / "ROIReviewView.swift"
)


def code() -> str:
    source = VIEW.read_text(encoding="utf-8")
    return "\n".join(re.sub(r"//.*", "", line) for line in source.splitlines())


def test_the_still_is_framed_to_the_rect_the_taps_are_measured_against():
    source = code()
    assert ".frame(width: rect.width, height: rect.height)" in source, (
        "the still must be sized to the fitted rect, not left to the stack to place"
    )
    assert ".position(x: rect.midX, y: rect.midY)" in source, (
        "the still must be positioned at the fitted rect, so layout and conversion cannot drift"
    )


def test_the_still_does_not_rely_on_scaled_to_fit_for_placement():
    assert "scaledToFit" not in code().split("private struct Magnifier", 1)[0], (
        "scaledToFit lets the enclosing stack's alignment decide where the image lands, which is "
        "a second opinion about a position fittedRect already computes"
    )


def test_taps_are_converted_through_the_shared_conversion():
    source = code()
    assert "ROIValidation.pixel(" in source, (
        "taps must go through the tested conversion, not be scaled inline in the view"
    )
    assert "ROIValidation.fittedRect(" in source
