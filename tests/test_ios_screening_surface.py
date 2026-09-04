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

from frontdoor.screening import CRITERIA_KEYS
from frontdoor_server.screen_view import WORDING

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
    return source[source.index("enum ScreeningCriterion") :]


def keys_in(swift):
    return [raw for _, raw in CASE_RE.findall(swift)]


def labels_in(swift):
    cases = dict(CASE_RE.findall(swift))  # swift case name -> server key
    return {cases[name]: label for name, label in LABEL_RE.findall(swift) if name in cases}


def html_labels():
    html = SCREEN_HTML.read_text(encoding="utf-8")
    start = html.index("const CRITERION_LABELS")
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
    fragment = WORDING[:40]
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
