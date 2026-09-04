"""The instrument's view set must be the protocol's view set (#289).

`docs/capture-protocol.md` prescribes 5-6 named views per entrance. Until now the app knew only a
count, so six head-on shots and a proper set looked identical to it. The app cannot read a markdown
file at the doorstep, so the Swift names the views -- and this guard is what keeps the document the
source of truth rather than something the code once agreed with.

The second rule here matters more than the first. The 2026-09-01 pivot moved D-021's shot plan out
of the instrument and onto paper, and #289 brings back the *knowledge* of the set without bringing
back a gate: nothing may refuse a capture, or make one conditional on coverage. An operator who
needs a seventh angle must get it. CI never builds Swift, so both are read out of the sources.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "capture-protocol.md"
SLOTS = ROOT / "ios" / "FrontdoorCapture" / "Capture" / "ViewSlot.swift"
CONTROLLER = ROOT / "ios" / "FrontdoorCapture" / "Capture" / "CaptureController.swift"

DOC_VIEW_RE = re.compile(r"^\d+\.\s+\*\*(.+?)\*\*", re.MULTILINE)
LABEL_RE = re.compile(r'case\s+\.(\w+):\s*return\s+"([^"]+)"')


def protocol_views():
    text = PROTOCOL.read_text(encoding="utf-8")
    section = text[text.index("## The view set") : text.index("## Fixed geometry")]
    return DOC_VIEW_RE.findall(section)


def swift_labels(source=None):
    source = source or SLOTS.read_text(encoding="utf-8")
    body = source[source.index("var label: String") : source.index("var coaching: String")]
    return [label for _, label in LABEL_RE.findall(body)]


def controller(no_comments=True):
    text = CONTROLLER.read_text(encoding="utf-8")
    if no_comments:
        text = "\n".join(re.sub(r"//.*", "", line) for line in text.splitlines())
    return text


def body_of(signature):
    return controller().split(signature, 1)[1].split("\n    }", 1)[0]


def test_the_app_names_exactly_the_views_the_protocol_prescribes():
    assert swift_labels() == protocol_views(), (
        "ViewSlot and docs/capture-protocol.md disagree about the view set. A view the protocol "
        "asks for and the app cannot name is a view no coverage report will ever miss."
    )


def test_a_renamed_view_is_noticed():
    """Break the rule, confirm red."""
    source = SLOTS.read_text(encoding="utf-8").replace(
        'case .far: return "Far, ~3-4 m"', 'case .far: return "Far"')
    assert swift_labels(source) != protocol_views()


def test_the_shutter_does_not_consult_coverage():
    """Coaching, not a gate: nothing about which views exist may condition taking a photo."""
    shutter = body_of("func capturePhoto()")
    for term in ("coverage", "viewSlot", "ViewSetCoverage"):
        assert term not in shutter, (
            f"capturePhoto references {term}. The protocol is guidance -- an instrument that made "
            "the shutter conditional on the view set would refuse the deviations the protocol "
            "explicitly allows (#289)."
        )


def test_coverage_is_recorded_after_the_capture_is_written():
    """Losing guidance must never cost a photo that is already on disk."""
    body = body_of("private func commit(")
    assert body.index("CaptureWriter.write(") < body.index("coverage.record(")


def test_nothing_refuses_a_capture_for_a_view_already_covered():
    """A second shot of a covered view is a capture the protocol allows."""
    source = controller()
    for pattern in (r"guard\s+!?\s*coverage", r"guard.*ViewSetCoverage", r"if\s+coverage.*return"):
        assert re.search(pattern, source) is None, f"coverage gates a capture: {pattern}"
