"""The Green-or-Gray rule and the map endpoints (TICK-247, #169).

The two-state rule is load-bearing: the public map may render "Verified
Accessible" (green) or "Not Yet Checked" (neutral) and nothing else — no red
state, no public negative verdict, no third state, for any input including
deliberately adversarial rows. These tests pin that contract on the Python
side (frontdoor.map_states), which is where the server computes every state
the page renders.
"""

import json
import re
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


def test_map_page_serves_html_with_two_stamp_classes(client):
    response = client.get("/map")
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    html = response.get_data(as_text=True)
    # The page defines exactly the two stamp state classes and no others.
    # stamp-drop / stamp-dropping are the drop animation, not a state.
    classes = set(re.findall(r"stamp-(?!drop)[a-z]+", html))
    assert classes == {"stamp-verified", "stamp-neutral"}
    assert "Not Yet Checked" in html


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
