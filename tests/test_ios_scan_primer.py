"""The scan primer must not become a fourth version of the view set (#275, #289).

The operator can now be told what to shoot in three places: `docs/capture-protocol.md`, the
coaching bar in the viewfinder, and the primer before the viewfinder opens. Two of those are
already tied together by `test_ios_view_set.py`; this ties the third, by requiring the primer to
render `ViewSlot` rather than a list of its own.

CI never builds Swift, so it is read out of the source.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIMER = ROOT / "ios" / "FrontdoorCapture" / "UI" / "ScanPrimerView.swift"
SLOTS = ROOT / "ios" / "FrontdoorCapture" / "Capture" / "ViewSlot.swift"
ROOT_VIEW = ROOT / "ios" / "FrontdoorCapture" / "UI" / "RootView.swift"

LABEL_RE = re.compile(r'case\s+\.\w+:\s*return\s+"([^"]+)"')


def view_labels():
    source = SLOTS.read_text(encoding="utf-8")
    body = source[source.index("var label: String") : source.index("var coaching: String")]
    return LABEL_RE.findall(body)


def test_the_primer_renders_the_view_set_rather_than_listing_it():
    source = PRIMER.read_text(encoding="utf-8")
    assert "ViewSlot.allCases" in source, (
        "the primer must render the view set, not restate it -- a fourth copy of 'which views "
        "exist' is a fourth thing to keep in step with the protocol"
    )


def test_the_primer_hardcodes_no_view_name():
    source = PRIMER.read_text(encoding="utf-8")
    offenders = [label for label in view_labels() if label in source]
    assert offenders == [], f"the primer spells out view names itself: {offenders}"


def test_the_primer_is_shown_before_the_viewfinder_and_only_for_screening():
    """Metrology is a different protocol, and a primer over a live preview is useless."""
    source = ROOT_VIEW.read_text(encoding="utf-8")
    gate = source.split("onPrimer:", 1)[0]
    assert "!controller.captureMode.carriesMetrologyTruth" in gate
    assert "primer.hasBeenSeen" in gate


def test_the_primer_stays_reachable_after_it_has_been_seen():
    """Seen once must not mean gone: the home screen keeps a way back to it."""
    home = (ROOT / "ios" / "FrontdoorCapture" / "UI" / "HomeView.swift").read_text(
        encoding="utf-8")
    assert "onPrimer" in home
    assert "How scanning works" in home
