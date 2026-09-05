"""The phone's named checks must say what the server says (#275).

The scan flow's result surface renders `POST /screen`'s answer. Three ways that can quietly stop
being true, all of them invisible in a green build:

* the server assesses a criterion the phone has no case for, so it never reaches the screen;
* the two demo surfaces -- the phone and the laptop page -- drift into different names for the
  same criterion, and the room is told they are different things;
* someone synthesises a verdict on the device, which is a second assessment path with none of the
  server's honesty rules attached to it.

CI runs on Linux and never builds Swift (TICK-005 put macOS runners out of scope), so these are
source-level guards. They read the Swift the way `test_one_measurement_path.py` reads the Python.
"""

import re
from pathlib import Path

import pytest

from frontdoor.screening import ADA_CHECK_KEYS, ADA_DISCLAIMER, ADA_STANDARDS_URL, CRITERIA_KEYS

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_TREE = REPO_ROOT / "ios" / "FrontdoorCapture"
CRITERION_SWIFT = APP_TREE / "Screening" / "ScreeningResponse.swift"
SCREEN_HTML = REPO_ROOT / "src" / "frontdoor_server" / "screen.html"

CASE_RE = re.compile(r'case\s+(\w+)\s*=\s*"([a-z_]+)"')
LABEL_RE = re.compile(r'case\s+\.(\w+):\s*return\s+"([^"]+)"')
HTML_LABEL_RE = re.compile(r'^\s*([a-z_]+):\s*"([^"]+)",\s*$', re.MULTILINE)


def swift_sources():
    return sorted(APP_TREE.rglob("*.swift"))


def criterion_enum(source=None):
    """The `enum ScreeningCriterion` block, so the parsing cannot pick up another enum."""
    if source is None:
        source = CRITERION_SWIFT.read_text(encoding="utf-8")
    start = source.index("enum ScreeningCriterion")
    rest = source[start:]
    nxt = rest.find("\nenum ", 1)
    return rest if nxt == -1 else rest[:nxt]


def ada_enum(source=None):
    if source is None:
        source = CRITERION_SWIFT.read_text(encoding="utf-8")
    start = source.index("enum AdaScreeningCheck")
    rest = source[start:]
    nxt = rest.find("\nenum ", 1)
    return rest if nxt == -1 else rest[:nxt]


def keys_in(swift):
    return [raw for _, raw in CASE_RE.findall(swift)]


def labels_in(swift):
    cases = dict(CASE_RE.findall(swift))  # swift case name -> server key
    return {cases[name]: label for name, label in LABEL_RE.findall(swift) if name in cases}


def html_labels():
    html = SCREEN_HTML.read_text(encoding="utf-8")
    start = html.index("const CRITERION_LABELS")
    return dict(HTML_LABEL_RE.findall(html[start : html.index("}", start)]))


def html_ada_labels():
    html = SCREEN_HTML.read_text(encoding="utf-8")
    start = html.index("const ADA_CHECK_LABELS")
    return dict(HTML_LABEL_RE.findall(html[start : html.index("}", start)]))


def test_the_phone_has_a_case_for_every_criterion_the_server_assesses():
    assert keys_in(criterion_enum()) == list(CRITERIA_KEYS), (
        "ScreeningCriterion and frontdoor.screening.CRITERIA disagree. A criterion the server "
        "assesses and the phone has no case for is simply not shown to the operator."
    )


def test_the_phone_and_the_laptop_page_name_the_criteria_identically():
    assert labels_in(criterion_enum()) == html_labels(), (
        "the two demo surfaces label the same criterion differently; one room, two names for "
        "one thing"
    )


def test_the_honesty_wording_is_not_copied_into_the_app():
    """It is printed from the response, so it cannot drift from what the API commits to."""
    source = (REPO_ROOT / "src" / "frontdoor_server" / "screen_view.py").read_text(
        encoding="utf-8"
    )
    match = re.search(
        r'WORDING = \(\s*"([^"]+)"\s*"([^"]+)"\s*"([^"]+)"\s*\)',
        source,
    )
    assert match, "WORDING assignment not found in screen_view.py"
    fragment = "".join(match.groups())[:40]
    offenders = [
        path.relative_to(REPO_ROOT)
        for path in swift_sources()
        if fragment in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"the screening wording is hardcoded in {offenders}"


def test_the_app_never_constructs_a_criterion_verdict():
    """Nothing on the device may author a verdict; it may only render one it was sent."""
    offenders = [
        path.relative_to(REPO_ROOT)
        for path in swift_sources()
        if "ScreeningResponse.Criterion(" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], (
        f"{offenders} builds a screening verdict on the device. Verdicts come from /screen; one "
        "made here is a second assessment path the evaluation never characterises (R-11)."
    )


def test_a_dropped_criterion_is_noticed():
    """Break the rule, confirm red: a guard that has never failed is not a guard."""
    without = criterion_enum().replace('case handrails = "handrails"', "")
    assert keys_in(without) != list(CRITERIA_KEYS)


def test_a_renamed_label_is_noticed():
    renamed = criterion_enum().replace(
        'case .handrails: return "Handrails"', 'case .handrails: return "Rails"')
    assert labels_in(renamed) != html_labels()


def test_the_phone_has_a_case_for_every_ada_check_the_server_scores():
    assert keys_in(ada_enum()) == list(ADA_CHECK_KEYS), (
        "AdaScreeningCheck and frontdoor.screening.ADA_CHECK_KEYS disagree. A check the "
        "server scores and the phone has no case for is simply not shown."
    )
    assert labels_in(ada_enum()) == html_ada_labels()


def test_the_ada_score_is_not_turned_into_a_compliance_badge():
    """The percentage is a coverage score, not a pass/fail stamp (#318)."""
    banned = (
        "is ADA compliant",
        "is ada compliant",
        "noncompliant",
        "compliance badge",
        "passes ADA",
        "fails ADA",
    )
    surfaces = [
        APP_TREE / "UI" / "ScreeningChecksView.swift",
        APP_TREE / "Screening" / "ScreeningResponse.swift",
        SCREEN_HTML,
    ]
    offenders = []
    for path in surfaces:
        text = path.read_text(encoding="utf-8")
        for phrase in banned:
            if phrase.lower() in text.lower():
                offenders.append((path.relative_to(REPO_ROOT), phrase))
    assert offenders == []


def test_the_phone_does_not_compute_the_ada_score():
    """Score, counts and summary come from the server. The phone only renders them."""
    view = (APP_TREE / "UI" / "ScreeningChecksView.swift").read_text(encoding="utf-8")
    assert "score_percent" not in view
    assert "true_count /" not in view
    assert ADA_DISCLAIMER not in view, "print the disclaimer from the response"
    assert ADA_STANDARDS_URL not in view, "the tappable link is the URL the server sent"


# --- an entrance is screened on its view set, not on one frame (#316) ---------

CLIENT = APP_TREE / "Screening" / "ScreenClient.swift"
CONTROLLER = APP_TREE / "Capture" / "CaptureController.swift"


def test_the_client_sends_a_set_and_has_no_single_image_route_left():
    """A one-photo screening is a different and worse answer, not a cheaper one.

    /screen makes ONE integrated call across everything it is given. The set is walked head-on,
    obliques, near, far, hardware close-up -- so the last frame is a close-up of a door handle,
    and screening it alone answers `not_visible` for ramp/bevel, handrails and signage. The engine
    is then reporting framing rather than the entrance, which is the pilot finding the far view's
    coaching already carries.
    """
    source = CLIENT.read_text(encoding="utf-8")
    assert "func screen(views:" in source
    assert "static func body(views:" in source
    assert "func screen(image:" not in source, "the single-image route is still reachable"
    assert "static func body(image:" not in source


def test_the_release_after_labeling_sends_every_held_view():
    source = CONTROLLER.read_text(encoding="utf-8")
    assert "screen(views: pending.views" in source
    assert "latestScreeningCapture" not in source, "the last-frame-only field is still there"


def test_a_view_the_upload_drain_removed_does_not_fail_the_whole_set():
    """The drain deletes a capture once the bucket confirms it, and labeling takes minutes.

    A missing file means the capture is safe, not lost. Reading it with `try?` and dropping it is
    what lets the rest of the set still be screened.
    """
    body = _body_of(CONTROLLER.read_text(encoding="utf-8"), "private func screen(views urls:")
    assert "compactMap" in body
    assert "try? Data(contentsOf: url)" in body


def _body_of(source, signature):
    return source.split(signature, 1)[1].split("\n    }", 1)[0]
