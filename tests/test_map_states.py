"""The Green-or-Gray rule and the map endpoints (TICK-247, #169).

The two-state rule is load-bearing: the public map may render "Verified
Accessible" (green) or "Not Yet Checked" (neutral) and nothing else — no red
state, no public negative verdict, no third state, for any input including
deliberately adversarial rows. These tests pin that contract on the Python
side (frontdoor.map_states), which is where the server computes every state
the page renders.

The page renders those two server states as the reference UI's trust tiers
(Estimated / Scanned on-site / Owner-confirmed) and the page-level tests
below pin the honesty of that mapping: ai_estimated never renders above
Estimated, nothing renders negatively, and the match-state hue never leaks
into confidence styling.
"""

import json
import re
import subprocess
from importlib import resources

import pytest

from frontdoor.map_states import (
    OBSERVATION_LABELS,
    STAMP_LABELS,
    STATE_NEUTRAL,
    STATE_VERIFIED,
    STATES,
    checklist_for_row,
    pin_for_row,
    prepare_map_payload,
    state_for_row,
)
from frontdoor_server.app import create_app


def row(**overrides):
    """A well-formed TICK-248 pre-catalogue row, overridable per test."""
    base = {
        "place_id": "ChIJexample",
        "name": "Example Cafe",
        "location": {"lat": 40.0, "lng": -75.0},
        "source": "streetview",
        "status": "ai_estimated",
        "covered": True,
        "coverage_status": "OK",
        "imagery_date": "2024-06",
        "headings": [10.0, 50.0],
        "criteria": {
            "ramp_or_bevel": {"verdict": "present", "confidence": 0.9, "flip_rate": 0.0},
            "handrails": {"verdict": "not_visible", "confidence": 0.6, "flip_rate": 0.5},
            "accessible_door_hardware": {"verdict": "absent", "confidence": 0.8, "flip_rate": 0.0},
            "accessibility_signage": {"verdict": "not_visible", "confidence": None, "flip_rate": 0.0},
        },
        "assessment_errors": [],
    }
    base.update(overrides)
    return base


# The contract table: input row -> the one state it must map to.
STATE_CONTRACT = [
    # The only green path: human-verified, non-imagery source.
    (row(status="verified", source="onsite_visit"), STATE_VERIFIED),
    (row(status="verified", source=None), STATE_VERIFIED),
    ({"status": "verified"}, STATE_VERIFIED),
    # Imagery alone never produces green, even claiming verified status.
    (row(status="verified", source="streetview"), STATE_NEUTRAL),
    # The normal pre-catalogue row.
    (row(), STATE_NEUTRAL),
    # Missing / partial / malformed.
    ({}, STATE_NEUTRAL),
    (None, STATE_NEUTRAL),
    ("verified", STATE_NEUTRAL),
    (42, STATE_NEUTRAL),
    (["verified"], STATE_NEUTRAL),
    (row(status=None), STATE_NEUTRAL),
    (row(status=True), STATE_NEUTRAL),
    (row(status={"status": "verified"}), STATE_NEUTRAL),
    # Near-misses on the exact verified token.
    (row(status="VERIFIED", source="onsite_visit"), STATE_NEUTRAL),
    (row(status=" verified ", source="onsite_visit"), STATE_NEUTRAL),
    (row(status="verified!", source="onsite_visit"), STATE_NEUTRAL),
    # Adversarial negative-looking values must render neutral, never as
    # anything resembling a warning.
    (row(status="not_accessible"), STATE_NEUTRAL),
    (row(status="verified_inaccessible"), STATE_NEUTRAL),
    (row(status="failed"), STATE_NEUTRAL),
    (row(status="denied"), STATE_NEUTRAL),
    (row(status="ai_estimated", criteria={
        key: {"verdict": "absent", "confidence": 1.0, "flip_rate": 0.0}
        for key in ("ramp_or_bevel", "handrails",
                    "accessible_door_hardware", "accessibility_signage")
    }), STATE_NEUTRAL),
]


@pytest.mark.parametrize("value,expected", STATE_CONTRACT)
def test_state_contract(value, expected):
    assert state_for_row(value) == expected


def test_exactly_two_states_exist():
    assert STATES == {STATE_VERIFIED, STATE_NEUTRAL}
    assert set(STAMP_LABELS) == STATES
    assert STAMP_LABELS[STATE_VERIFIED] == "Verified Accessible"
    assert STAMP_LABELS[STATE_NEUTRAL] == "Not Yet Checked"


def test_state_for_row_is_total_over_junk():
    junk = [
        object(), b"verified", 3.14, {"status"}, frozenset(), (), range(3),
        {"status": b"verified"}, {"status": ["verified"]},
        {"status": "verified", "source": "streetview", "extra": object()},
        {i: i for i in range(5)},
    ]
    for value in junk:
        assert state_for_row(value) in STATES


def test_checklist_uses_only_public_vocabulary():
    adversarial = row(criteria={
        "ramp_or_bevel": {"verdict": "DANGEROUS", "confidence": 2},
        "handrails": {"verdict": "absent", "confidence": "high"},
        "accessible_door_hardware": "not a dict",
        # accessibility_signage missing entirely
    })
    checklist = checklist_for_row(adversarial)
    assert len(checklist) == 4
    for item in checklist:
        assert item["observation"] in OBSERVATION_LABELS
        assert item["observation_label"] in OBSERVATION_LABELS.values()
    by_key = {item["key"]: item for item in checklist}
    # An unknown verdict is not assessed, never invented.
    assert by_key["ramp_or_bevel"]["observation"] == "not_assessed"
    # "absent" is published as an observation, not a negative claim.
    assert by_key["handrails"]["observation_label"] == "Not visible in photos"
    assert by_key["handrails"]["confidence"] is None
    assert by_key["accessible_door_hardware"]["observation"] == "not_assessed"
    assert by_key["accessibility_signage"]["observation"] == "not_assessed"


def test_checklist_total_over_missing_criteria():
    for value in ({}, None, "x", row(criteria=None), row(criteria=[1, 2])):
        checklist = checklist_for_row(value)
        assert [item["observation"] for item in checklist] == ["not_assessed"] * 4


def test_pin_carries_state_label_and_freshness():
    pin = pin_for_row("ChIJx", row())
    assert pin["state"] == STATE_NEUTRAL
    assert pin["label"] == "Not Yet Checked"
    assert pin["ai_estimated"] is True
    assert pin["imagery_date"] == "2024-06"
    assert pin["location"] == {"lat": 40.0, "lng": -75.0}
    assert pin["owner_confirmed"] is False


def test_pin_does_not_carry_listing_contact():
    """Catalogue phone/website are claim-channel authority, not map payload."""
    pin = pin_for_row("ChIJx", row(
        phone="(512) 555-0100",
        website="https://secret.example",
        formatted_phone_number="(512) 555-0100",
    ))
    dumped = json.dumps(pin)
    assert "(512) 555-0100" not in dumped
    assert "secret.example" not in dumped
    assert "phone" not in pin
    assert "website" not in pin


def test_pin_without_usable_location_is_dropped():
    assert pin_for_row("a", row(location=None)) is None
    assert pin_for_row("b", row(location={"lat": None, "lng": None})) is None
    assert pin_for_row("c", row(location={"lat": 91, "lng": 0})) is None
    assert pin_for_row("d", "not a row") is None


def test_payload_every_pin_state_is_public():
    dataset = {
        "verified": row(status="verified", source="onsite_visit"),
        "estimated": row(),
        "uncovered": row(covered=False, coverage_status="ZERO_RESULTS",
                         imagery_date=None, headings=[], criteria=None),
        "adversarial": row(status="verified_inaccessible"),
        "no_location": row(location=None),
        "garbage": ["not", "a", "row"],
    }
    payload = prepare_map_payload(dataset)
    assert "photos" in payload["note"]
    assert "not measurements" in payload["note"]
    pins = {pin["place_id"]: pin for pin in payload["pins"]}
    assert set(pins) == {"verified", "estimated", "uncovered", "adversarial"}
    assert all(pin["state"] in STATES for pin in pins.values())
    assert pins["verified"]["state"] == STATE_VERIFIED
    assert pins["estimated"]["state"] == STATE_NEUTRAL
    assert pins["uncovered"]["state"] == STATE_NEUTRAL
    assert pins["adversarial"]["state"] == STATE_NEUTRAL


def test_payload_total_over_malformed_dataset():
    for dataset in (None, [], "junk", 7):
        assert prepare_map_payload(dataset)["pins"] == []


# --- endpoints -------------------------------------------------------------


@pytest.fixture
def client():
    return create_app().test_client()


def page(client):
    response = client.get("/map")
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    return response.get_data(as_text=True)


def test_map_page_defines_exactly_three_tier_classes(client):
    # The page's visual system has exactly the three trust tiers of the
    # agreed UI reference and no others. Tier is encoded shape + glyph +
    # hue, and the "tier-" class prefix is reserved for these three tokens
    # so this census stays meaningful.
    classes = set(re.findall(r"tier-[a-z]+", page(client)))
    assert classes == {"tier-estimated", "tier-scanned", "tier-owner"}


def test_tier_mapping_honesty(client):
    # The client-side tier mapping mirrors the server's two-state contract:
    # total and default-Estimated. Only the exact server-computed verified
    # state (human, non-imagery confirmation) renders the Scanned tier;
    # ai_estimated and every other input render Estimated. Owner-confirmed is
    # an extra pin field, never a third legal stamp.
    html = page(client)
    match = re.search(r"function tierClass\(pin\) \{([\s\S]*?)\n\}", html)
    assert match, "tierClass mapping function must exist"
    body = match.group(1)
    assert "pin.owner_confirmed" in body
    assert '"tier-owner"' in body
    assert 'state === VERIFIED_STATE ? "tier-scanned" : "tier-estimated"' in body
    assert '"verified_accessible"' in html  # the exact server token, nothing looser


def test_page_has_no_negative_and_no_match_state_hue(client):
    # Color rules from the reference: the match-state hue is reserved for a
    # future needs-match chip and must not appear anywhere on this page
    # (confidence dots use the tier's own hue), and no negative hue exists
    # in the product at all. Amber is freshness aging only.
    html = page(client).lower()
    assert "green" not in html
    assert not re.search(r"\bred\b", html)
    for hex_value in ("#15803d", "#bbf7d0", "#22c55e", "#16a34a", "#4ade80",
                      "#dc2626", "#ef4444", "#b91c1c"):
        assert hex_value not in html


def test_estimated_cta_replacement_line(client):
    # The Estimated tier's provenance line always ends with the replacement
    # invitation — the estimate visibly wants to be replaced.
    html = page(client)
    assert "Estimated by AI from street imagery" in html
    assert "been here? Confirm or correct in 30 seconds" in html


def test_card_renders_provenance_when_present_and_degrades_when_absent(client):
    # Provenance rows compose with the external-data work: an optional
    # pin.provenance array renders as receipt rows when present; when the
    # field is absent or a line is malformed, nothing renders and no state
    # is ever derived from it.
    html = page(client)
    assert "pin.provenance || []" in html
    assert 'typeof line.label !== "string"' in html


def test_tick_b03_commons_provenance_links_only_to_commons(client):
    html = page(client)
    script = re.search(r"<script>(.*)</script>", html, re.DOTALL).group(1)
    dom_stub = r"""
class FakeNode {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.attributes = {};
    this.hidden = false;
    this.classList = { add() {}, remove() {}, toggle() {} };
  }
  appendChild(child) { this.children.push(child); return child; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener() {}
  focus() { this.focused = true; }
  set innerHTML(value) {
    this._innerHTML = value;
    if (value === "") this.children = [];
  }
  get innerHTML() { return this._innerHTML || ""; }
}
var qaElements = { banner: new FakeNode("div"), sheet: new FakeNode("div") };
globalThis.document = {
  body: new FakeNode("body"),
  head: new FakeNode("head"),
  createElement: function (tag) { return new FakeNode(tag); },
  createTextNode: function (text) { var node = new FakeNode("#text"); node.textContent = text; return node; },
  getElementById: function (id) { return qaElements[id] || new FakeNode("div"); },
  addEventListener: function () {}
};
globalThis.window = { matchMedia: function () { return { matches: false }; } };
globalThis.location = { search: "" };
"""
    assertions = r"""
openSheet({
  state: "neutral", name: "QA place", checklist: [], provenance: [
    {source: "wikimedia_commons", label: "Good", url: "https://commons.wikimedia.org/wiki/File:Good.jpg"},
    {source: "openstreetmap", label: "Plain", url: "https://commons.wikimedia.org/wiki/File:Wrong.jpg"},
    {source: "wikimedia_commons", label: "Unsafe", url: "javascript:alert(1)"},
    {source: "wikimedia_commons", label: "Wrong port", url: "https://commons.wikimedia.org:444/wiki/File:Bad.jpg"},
    {source: "wikimedia_commons", label: "User info", url: "https://user@commons.wikimedia.org/wiki/File:Bad.jpg"}
  ]
});
var receipts = qaElements.sheet.children.find(function (node) { return node.className === "receipts"; });
var rendered = receipts.children.map(function (row) {
  var text = row.children[1];
  return {tag: text.tagName, label: text.textContent, href: text.href || null,
          target: text.target || null, rel: text.rel || null};
});
console.log(JSON.stringify(rendered));
"""
    completed = subprocess.run(
        ["node"], input=dom_stub + script + assertions,
        text=True, capture_output=True, check=True)
    assert json.loads(completed.stdout) == [
        {"tag": "A", "label": "Good",
         "href": "https://commons.wikimedia.org/wiki/File:Good.jpg",
         "target": "_blank", "rel": "noopener noreferrer"},
        {"tag": "SPAN", "label": "Plain", "href": None,
         "target": None, "rel": None},
        {"tag": "SPAN", "label": "Unsafe", "href": None,
         "target": None, "rel": None},
        {"tag": "SPAN", "label": "Wrong port", "href": None,
         "target": None, "rel": None},
        {"tag": "SPAN", "label": "User info", "href": None,
         "target": None, "rel": None},
    ]
    assert ".provenance-link:focus-visible" in html


def test_state_records_layer_keyed_on_provenance_source(client):
    # The "State records" toggle is keyed on the provenance source string
    # (tabs/tdlr/texas…) and degrades to a disabled toggle with a "coming"
    # hint when zero pins qualify — the mechanism ships before the data.
    html = page(client)
    assert "State records" in html
    assert "isStateRecordLine" in html
    assert re.search(r"tabs\|tdlr\|texas", html)
    assert "toggle.disabled = true" in html
    assert "coming" in html


def test_unknown_row_and_correction_affordance(client):
    html = page(client)
    # Unknowns are an invitation, not an apology.
    assert "Not yet seen — be the first to scan." in html
    # Suggest a correction is on every card.
    assert "Suggest a correction" in html


def test_demo_scan_control_gated_behind_query_param(client):
    html = page(client)
    # The scan simulation exists only behind ?demo=1 …
    assert 'params.get("demo") === "1"' in html
    assert "Simulate scan" in html
    # … and the control is created dynamically inside that gate, never
    # present as an element in the static markup (only its CSS is static).
    assert 'id="simulate-scan"' not in html
    assert 'id="scanbox"' not in html
    static_markup = html.split("<script>")[0]
    assert "Simulate scan" not in static_markup
    # Reduced motion collapses the animation to its end state.
    assert "prefers-reduced-motion" in html


def test_page_accessibility_hooks(client):
    html = page(client)
    # Pins are keyboard-focusable buttons with labels; the card is a
    # labelled dialog with a close control; tier is never color alone
    # (glyph assertions: person/storefront/italic i/sparkle are all in the
    # pin construction code).
    assert 'setAttribute("role", "button")' in html
    assert 'setAttribute("tabindex", "0")' in html
    assert 'role="dialog"' in html
    assert 'aria-label' in html
    assert "Close details" in html
    assert "✦" in html  # AI sparkle glyph accompanies the dashed outline


def test_map_page_html_matches_packaged_file(client):
    packaged = (
        resources.files("frontdoor_server")
        .joinpath("map.html")
        .read_text(encoding="utf-8")
    )
    assert client.get("/map").get_data(as_text=True) == packaged


def test_map_data_serves_precomputed_states(client, tmp_path, monkeypatch):
    dataset = {
        "green": row(status="verified", source="onsite_visit"),
        "gray": row(),
    }
    path = tmp_path / "precatalogue.json"
    path.write_text(json.dumps(dataset), encoding="utf-8")
    monkeypatch.setenv("FRONTDOOR_MAP_DATASET", str(path))
    response = client.get("/map/data")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["dataset_error"] is None
    states = {pin["place_id"]: pin["state"] for pin in payload["pins"]}
    assert states == {"green": STATE_VERIFIED, "gray": STATE_NEUTRAL}


def test_map_data_degrades_when_dataset_missing(client, tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTDOOR_MAP_DATASET", str(tmp_path / "nope.json"))
    response = client.get("/map/data")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["pins"] == []
    assert "not found" in payload["dataset_error"]


def test_map_data_degrades_when_dataset_unreadable(client, tmp_path, monkeypatch):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("FRONTDOOR_MAP_DATASET", str(path))
    response = client.get("/map/data")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["pins"] == []
    assert "unreadable" in payload["dataset_error"]


# --- every degraded input names itself in the payload (#353) -----------------
#
# /map/data degrades over three inputs and only one of them said so. An empty
# or thinner map is otherwise indistinguishable from a working one, which is
# how the dataset went missing from the image for a day. Each test below fails
# against the old code, which returned the same 200 and the same pins.


@pytest.fixture
def clean_side_files(tmp_path, monkeypatch):
    """A store and side files that exist and are empty, so each test changes
    exactly the one input it is about."""
    (tmp_path / "external").mkdir()
    for env, name in (
        ("FRONTDOOR_EXTERNAL_OSM", "osm_accessibility.json"),
        ("FRONTDOOR_EXTERNAL_COMMONS", "commons_imagery.json"),
    ):
        path = tmp_path / "external" / name
        path.write_text(json.dumps({"records": []}), encoding="utf-8")
        monkeypatch.setenv(env, str(path))
    monkeypatch.setenv("FRONTDOOR_SCANS", str(tmp_path / "scans.jsonl"))
    dataset = tmp_path / "precatalogue.json"
    dataset.write_text(json.dumps({"gray": row()}), encoding="utf-8")
    monkeypatch.setenv("FRONTDOOR_MAP_DATASET", str(dataset))
    return monkeypatch


def test_map_data_reports_a_clean_read_of_every_input(client, clean_side_files):
    payload = client.get("/map/data").get_json()
    assert payload["dataset_error"] is None
    assert payload["scans_error"] is None
    assert payload["provenance_error"] is None
    assert payload["scan_count"] == 0
    assert payload["scans_skipped"] == 0


def test_map_data_distinguishes_no_scans_from_an_unreachable_store(
        client, clean_side_files, tmp_path):
    """"Nobody has published yet" and "the volume is not mounted" were the
    same empty map."""
    assert client.get("/map/data").get_json()["scans_error"] is None

    clean_side_files.setenv(
        "FRONTDOOR_SCANS", str(tmp_path / "not-mounted" / "scans.jsonl"))
    payload = client.get("/map/data").get_json()
    assert payload["scans_error"] is not None
    assert payload["scan_count"] == 0


def test_map_data_reports_a_scan_it_could_not_read(
        client, clean_side_files, tmp_path):
    """One torn line silently deleted that scan from the map forever while its
    contributor held a 200 saying it published."""
    store = tmp_path / "scans.jsonl"
    store.write_text(
        json.dumps({
            "scan_id": "good", "created_at": "2026-09-05T12:00:00Z",
            "place_ref": {"place_id": "gray"},
            "verdicts": {}, "confidences": {},
        }) + "\n" + '{"scan_id": "torn"\n',
        encoding="utf-8",
    )
    clean_side_files.setenv("FRONTDOOR_SCANS", str(store))
    payload = client.get("/map/data").get_json()
    assert payload["scan_count"] == 1
    assert payload["scans_skipped"] == 1
    assert payload["scans_error"] is not None


def test_map_data_reports_a_missing_provenance_side_file(
        client, clean_side_files, tmp_path):
    """Losing the side files takes every provenance and attribution line off
    every pin, and the map looks entirely normal. Attribution is a licence
    obligation for ODbL and CC BY records, so this cannot be silent."""
    clean_side_files.setenv(
        "FRONTDOOR_EXTERNAL_OSM", str(tmp_path / "external" / "gone.json"))
    payload = client.get("/map/data").get_json()
    assert payload["provenance_error"] is not None
    assert payload["dataset_error"] is None


def test_map_data_reports_an_unreadable_provenance_side_file(
        client, clean_side_files, tmp_path):
    broken = tmp_path / "external" / "commons_imagery.json"
    broken.write_text("{not json", encoding="utf-8")
    payload = client.get("/map/data").get_json()
    assert payload["provenance_error"] is not None
