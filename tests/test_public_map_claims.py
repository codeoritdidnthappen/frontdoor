"""What /map/data may claim, and the scale it claims it on (TICK-461, TICK-462).

Two invariants over the public map payload. Both defects were found on the
live URL while every test in this suite passed, which is why both of these
run against what the endpoint actually serves over the committed datasets,
and not only against a hand-built row.

  * **#461 — a label is not a verdict.** Production served DeSano Pizzeria as
    "Verified Accessible" with all four criteria reading ``not_visible``: the
    photographs showed nothing, and the public API said verified. The green
    state is earned by a human standing at the door with a camera, so it is a
    statement about how the evidence was collected. It cannot be a conclusion
    about whether a person can get in — that conclusion is not a thing this
    product produces, and four "we could not see" answers could not support
    it if it were. The rest of the architecture already enforces that
    ``not_visible`` is not ``absent`` and that neither is a verdict; this
    pins the label sitting on top of them.

  * **#462 — one scale.** The same endpoint carried ``confidence`` on two
    scales, inside a single pin: sweetgreen served 20.0, 0.0, 0.85 and 0.95,
    where the 0.85 and 0.95 were the observations the model was SUREST of.
    Anything rendering the field as a percentage showed them as 1%. A viewer
    cannot tell 0.85-of-1 from 0.85-of-100 by looking at it, so the payload
    must carry exactly one scale and must say which.

Deliberately written against the public surface only — the stamp labels, the
state tokens, the served payload — so this file runs unchanged against the
commit before the fix, where both tests fail.
"""

import json
from pathlib import Path

import pytest

from frontdoor.map_states import (
    STAMP_LABELS,
    STATES,
    pin_for_row,
)
from frontdoor.scan_records import merge_scans
from frontdoor_server.app import create_app

REPO = Path(__file__).resolve().parents[1]
DATASET = REPO / "data" / "precatalogue.json"
STORE = REPO / "data" / "published_scans.jsonl"

CRITERIA_KEYS = (
    "ramp_or_bevel",
    "handrails",
    "accessible_door_hardware",
    "accessibility_signage",
)

#: Words a public state token or stamp label may not contain, because each of
#: them turns a statement about evidence into a conclusion about access. The
#: checklist's own vocabulary is exempt by construction: it never reaches this
#: census, and "Accessible door hardware" is the NAME OF A FEATURE somebody
#: looked for, not a claim that anything was found.
CLAIM_WORDS = (
    "accessible",
    "accessibility",
    "compliant",
    "compliance",
    "ada",
    "certified",
    "approved",
)


def _claims(text):
    """Every claim word present in a public string."""
    folded = str(text).casefold()
    return [word for word in CLAIM_WORDS if word in folded]


@pytest.fixture
def payload(monkeypatch, tmp_path):
    """/map/data over the committed datasets — the bytes production serves.

    FRONTDOOR_SCANS is pointed at an empty file for the same reason
    test_scan_publish does it: the runtime community store is a mounted
    volume in production, and whatever a developer published locally must not
    decide whether this passes.
    """
    runtime = tmp_path / "scans.jsonl"
    runtime.write_text("", encoding="utf-8")
    monkeypatch.setenv("FRONTDOOR_MAP_DATASET", str(DATASET))
    monkeypatch.setenv("FRONTDOOR_PUBLISHED_SCANS", str(STORE))
    monkeypatch.setenv("FRONTDOOR_SCANS", str(runtime))
    return create_app().test_client().get("/map/data").get_json()


# --- TICK-461: the label says how the evidence was collected -----------------


def test_no_public_state_or_label_makes_an_accessibility_claim():
    """The census, over every state the map has and every label it can print."""
    for state in STATES:
        assert not _claims(state), f"state token {state!r} claims accessibility"
    for state, label in STAMP_LABELS.items():
        assert not _claims(label), (
            f"the stamp label for {state!r} is {label!r}, which reads as a "
            "conclusion about access rather than about evidence"
        )


def test_all_four_not_visible_cannot_carry_a_positive_label():
    """The exact shape production served for DeSano Pizzeria.

    A published on-site scan, so the row earns the green stamp — and every
    criterion ``not_visible``, because the photographs showed nothing. The
    stamp may say the evidence was collected on site. It may not say the
    place is accessible.
    """
    blind = {
        "name": "Example Pizzeria",
        "location": {"lat": 30.2669, "lng": -97.7428},
        "status": "verified",
        "source": "community_scan",
        "imagery_date": "2026-09-06",
        "criteria": {
            key: {"verdict": "not_visible", "confidence": 50.0}
            for key in CRITERIA_KEYS
        },
    }
    pin = pin_for_row("ChIJblind", blind)

    # The premise: this really is the green state with nothing seen.
    assert pin["state"] != "not_yet_checked"
    assert [item["observation"] for item in pin["checklist"]] == [
        "not_visible"
    ] * 4

    assert not _claims(pin["label"]), (
        f"four not_visible criteria were published as {pin['label']!r}"
    )
    assert not _claims(pin["state"])
    assert pin["label"] == "Scanned on-site"


def test_the_served_payload_states_no_accessibility_conclusion(payload):
    """Over every pin the endpoint actually produces, not a built one."""
    assert payload["pins"], "the endpoint served no pins at all"
    for pin in payload["pins"]:
        assert not _claims(pin["label"]), (pin["name"], pin["label"])
        assert not _claims(pin["state"]), (pin["name"], pin["state"])
        assert pin["label"] == STAMP_LABELS[pin["state"]]

    # And no pin that saw nothing is celebrated for it.
    for pin in payload["pins"]:
        observations = {item["observation"] for item in pin["checklist"]}
        if observations == {"not_visible"}:
            assert not _claims(pin["label"]), pin["name"]


# --- TICK-462: one confidence scale, stated -----------------------------------


def _confidences(payload):
    return [
        item["confidence"]
        for pin in payload["pins"]
        for item in pin["checklist"]
        if isinstance(item["confidence"], (int, float))
        and not isinstance(item["confidence"], bool)
    ]


def test_the_payload_states_its_confidence_scale(payload):
    """A reader must not have to infer the scale from the values."""
    assert payload["confidence_scale"] == "percent_0_100"
    assert "0 through 100" in payload["confidence_note"]


def test_every_confidence_in_the_payload_is_on_one_scale(payload):
    """The invariant, over every record the endpoint can produce.

    Two populations is the failure: a value above 1 can only be a percentage,
    a value strictly between 0 and 1 can only be a fraction, and a response
    carrying both has published a field that means two different things. (0.0
    and 1.0 are the same number on either scale and prove nothing either way,
    so they are not evidence of a second population.)
    """
    values = _confidences(payload)
    assert values, "no pin carried a confidence at all"

    percentages = sorted({v for v in values if v > 1})
    fractions = sorted({v for v in values if 0 < v < 1})
    assert not (percentages and fractions), (
        "confidence is on two scales in one response: "
        f"{len(fractions)} value(s) in (0, 1) — {fractions[:8]} — beside "
        f"{len(percentages)} value(s) above 1, e.g. {percentages[:8]}"
    )
    for value in values:
        assert 0.0 <= value <= 100.0, value


def test_one_pin_never_carries_both_scales(payload):
    """The sweetgreen case: 20.0 and 0.85 on the same card."""
    for pin in payload["pins"]:
        values = [
            item["confidence"]
            for item in pin["checklist"]
            if isinstance(item["confidence"], (int, float))
            and not isinstance(item["confidence"], bool)
        ]
        assert not (
            any(v > 1 for v in values) and any(0 < v < 1 for v in values)
        ), (pin["name"], values)


def test_the_merge_publishes_a_scan_confidence_unrescaled():
    """The producer, pinned where it lives rather than at the edge.

    The scan path is the one that used to rescale, and it rescaled exactly
    the entries the merge accepts — the ones where the scan RAISES the
    observation — so the highest-confidence readings were the ones that came
    out wrong.
    """
    dataset = {
        "ChIJplace": {
            "name": "Example Cafe",
            "location": {"lat": 30.2669, "lng": -97.7428},
            "status": "ai_estimated",
            "source": "streetview",
            "criteria": {
                "ramp_or_bevel": {"verdict": "not_visible", "confidence": 20.0},
            },
        }
    }
    scan = {
        "scan_id": "s1",
        "created_at": "2026-09-06T12:00:00Z",
        "place_ref": {"place_id": "ChIJplace", "name": "Example Cafe"},
        "verdicts": {"accessibility_signage": "present"},
        "confidences": {"accessibility_signage": 95},
    }
    merged, _meta = merge_scans(dataset, [scan])
    entry = merged["ChIJplace"]["criteria"]["accessibility_signage"]
    assert entry["confidence"] == 95, (
        "the merge rescaled the scan's confidence; 95 became "
        f"{entry['confidence']!r}, which a percentage renderer shows as 1%"
    )

    pin = pin_for_row("ChIJplace", merged["ChIJplace"])
    by_key = {item["key"]: item for item in pin["checklist"]}
    assert by_key["accessibility_signage"]["confidence"] == 95
    assert by_key["ramp_or_bevel"]["confidence"] == 20.0


def test_the_committed_scan_store_is_on_the_engine_scale():
    """Where the published records already are, so nothing needs re-deriving.

    frontdoor.screening refuses a criterion confidence outside 0..100, so the
    engine's answer, the pre-catalogue's aggregate of it and these records are
    all one scale already. The two populations were made in the merge, not in
    the data.
    """
    records = [
        json.loads(line)
        for line in STORE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert records, "the committed publication is empty"
    values = [
        value
        for record in records
        for value in (record.get("confidences") or {}).values()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    assert values
    assert not [v for v in values if 0 < v < 1], (
        "a published record is on the fraction scale; the records themselves "
        "would need re-deriving, not just the merge"
    )
    for value in values:
        assert 0 <= value <= 100, value
