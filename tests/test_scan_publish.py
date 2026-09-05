"""Publishing the non-sealed entrances, and the seal that survives it (TICK-333, #333).

Two things are pinned here, and the first one is the point of the ticket.

**A sealed entrance cannot reach the screening engine.** Not "is skipped by the
loop" — cannot. The publishable set is derived from `frontdoor.split` rather
than written down, the one function that calls the engine re-resolves the split
before it does, and the engine resolves it a third time. The tests below drive
all three with an engine that fails the test if it is ever called, for every one
of the eighteen sealed identifiers by name.

**The committed publication is exactly the other forty-six.** Count, identity,
capture date, place reference (or an explicit unmatched record), and the tier
`/map/data` actually serves them at.
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from frontdoor.manifest import read_manifest
from frontdoor.scan_publish import (
    MODEL_VIEW_LONG_EDGE,
    NotPublishableError,
    _fit_for_the_model,
    assess_entrance,
    assess_publishable,
    build_records,
    entrance_captures,
    match_entrance,
    match_entrances,
    publishable_entrances,
)
from frontdoor.scan_records import SCAN_SOURCE, load_scan_records
from frontdoor.screening import CRITERIA_KEYS, ScreeningEngine, SealedSplitError
from frontdoor.split import assign_split, canonical_entrance_id

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "data" / "manifest.csv"
STORE = REPO / "data" / "scans.jsonl"
MATCHES = REPO / "data" / "scan_matches.json"
DATASET = REPO / "data" / "precatalogue.json"

#: The eighteen withheld until results freeze (docs/unsealing-run.md). Written
#: out rather than derived so a change to the seed or the manifest has to change
#: this list too, in a diff a reviewer can see.
SEALED = (
    "E-002", "E-005", "E-006", "E-011", "E-014", "E-015", "E-016", "E-021",
    "E-028", "E-029", "E-032", "E-036", "E-039", "E-044", "E-046", "E-052",
    "E-059", "E-064",
)

PUBLISHED_COUNT = 46


class RefusingEngine:
    """An engine that fails the test if anything reaches it."""

    def __init__(self):
        self.seen = []

    def screen_entrance_integrated(self, entrance_id, images):
        self.seen.append(entrance_id)
        raise AssertionError(
            f"the screening engine was reached for entrance {entrance_id!r}"
        )


class FakeCapture:
    def __init__(self, capture_id):
        self.capture_id = capture_id
        self.image = b"processed-bytes"
        self.sidecar = {"captured_at": "2026-09-04T18:00:00Z"}


class FakeSummary:
    verdict = "not_visible"


class FakeAssessment:
    criteria = {key: {"confidence": 60} for key in CRITERIA_KEYS}
    face_check = "clear"
    error = None


class FakeScreening:
    mode = "integrated"
    assessments = (FakeAssessment(),)
    summary = {key: FakeSummary() for key in CRITERIA_KEYS}


class RecordingEngine:
    """A stand-in that records every entrance it was asked to screen."""

    def __init__(self):
        self.seen = []
        self.images = []

    def screen_entrance_integrated(self, entrance_id, images):
        self.seen.append(entrance_id)
        self.images.extend(images)
        return FakeScreening()


# --- the derived publishable set ---------------------------------------------


def test_the_publishable_set_is_every_non_sealed_entrance_and_nothing_else():
    publishable = publishable_entrances(MANIFEST)
    recorded = {
        canonical_entrance_id(row["entrance_id"]) for row in read_manifest(MANIFEST)
    }
    assert sorted(set(publishable)) == publishable
    assert set(publishable) == recorded - set(SEALED)
    assert len(publishable) == PUBLISHED_COUNT


@pytest.mark.parametrize("entrance_id", SEALED)
def test_every_withheld_identifier_really_is_sealed_under_the_committed_seed(
        entrance_id):
    assert assign_split(entrance_id) == "sealed"


@pytest.mark.parametrize("entrance_id", SEALED)
def test_no_sealed_entrance_is_in_the_publishable_set(entrance_id):
    assert entrance_id not in publishable_entrances(MANIFEST)
    assert entrance_id not in entrance_captures(MANIFEST)


# --- a sealed identifier cannot reach the engine ------------------------------


@pytest.mark.parametrize("entrance_id", SEALED)
def test_a_sealed_entrance_is_refused_before_the_engine_is_touched(entrance_id):
    engine = RefusingEngine()
    with pytest.raises(NotPublishableError, match="sealed"):
        assess_entrance(
            engine, entrance_id, [b"bytes"],
            # Even a caller that hands in a set containing the sealed ID is
            # refused: the split is re-resolved, not trusted.
            publishable=frozenset(SEALED),
        )
    assert engine.seen == []


@pytest.mark.parametrize("entrance_id", ["e-002", " E-002 ", "E-002\n"])
def test_a_sealed_entrance_is_refused_however_it_is_spelled(entrance_id):
    engine = RefusingEngine()
    with pytest.raises(NotPublishableError, match="sealed"):
        assess_entrance(engine, entrance_id, [b"bytes"],
                        publishable=frozenset(publishable_entrances(MANIFEST)))
    assert engine.seen == []


def test_an_entrance_outside_the_publishable_set_is_refused_too():
    engine = RefusingEngine()
    # Not sealed, but not in the derived set either: still no model call.
    assert assign_split("E-900") != "sealed"
    with pytest.raises(NotPublishableError, match="publishable set"):
        assess_entrance(engine, "E-900", [b"bytes"], publishable=frozenset({"E-001"}))
    assert engine.seen == []


def test_the_engine_itself_refuses_a_sealed_entrance_as_the_last_barrier():
    """The third check: even called directly, the engine resolves the split."""
    engine = ScreeningEngine(client=object())
    with pytest.raises(SealedSplitError):
        engine.screen_entrance_integrated("E-002", [b"bytes"])


def test_the_publish_run_never_hands_a_sealed_identifier_to_the_engine(monkeypatch):
    """Drive the real loop over the real manifest, with the model faked out."""
    monkeypatch.setattr(
        "frontdoor.scan_publish.process_upload",
        lambda image_bytes: SimpleNamespace(image_bytes=image_bytes, face_count=0),
    )
    monkeypatch.setattr("frontdoor.scan_publish._fit_for_the_model", lambda b: b)
    engine = RecordingEngine()
    entrances = entrance_captures(MANIFEST)
    results = assess_publishable(
        entrances, get_capture=FakeCapture, engine=engine,
    )
    assert len(engine.seen) == PUBLISHED_COUNT
    assert not set(engine.seen) & set(SEALED)
    assert set(engine.seen) == set(results) == set(publishable_entrances(MANIFEST))


# --- what the engine is handed ------------------------------------------------


def test_every_view_goes_through_the_privacy_pass_before_the_engine(monkeypatch):
    """No original reaches a model call, whatever the capture ID suggests."""
    seen = []

    def fake_process(image_bytes):
        seen.append(image_bytes)
        return SimpleNamespace(image_bytes=b"blurred:" + image_bytes, face_count=2)

    monkeypatch.setattr("frontdoor.scan_publish.process_upload", fake_process)
    monkeypatch.setattr("frontdoor.scan_publish._fit_for_the_model", lambda b: b)
    engine = RecordingEngine()
    results = assess_publishable(
        {"E-001": ["c1", "c2"]}, get_capture=FakeCapture, engine=engine,
    )
    assert seen == [b"processed-bytes", b"processed-bytes"]
    assert engine.images == [b"blurred:processed-bytes"] * 2
    assert results["E-001"]["faces_blurred"] == 4


def test_a_view_is_reduced_to_the_size_the_model_reads():
    import cv2
    import numpy as np

    tall = np.zeros((3000, 2000, 3), dtype=np.uint8)
    raw = cv2.imencode(".jpg", tall)[1].tobytes()
    fitted = cv2.imdecode(
        np.frombuffer(_fit_for_the_model(raw), np.uint8), cv2.IMREAD_COLOR
    )
    assert max(fitted.shape[:2]) == MODEL_VIEW_LONG_EDGE
    # Something already small enough is passed through untouched.
    small = cv2.imencode(".jpg", np.zeros((800, 600, 3), dtype=np.uint8))[1].tobytes()
    assert _fit_for_the_model(small) is small


# --- matching -----------------------------------------------------------------


CATALOGUE = {
    "ChIJnear": {
        "place_id": "ChIJnear",
        "name": "Example Cafe",
        "location": {"lat": 30.2660, "lng": -97.7460},
    },
    "ChIJfar": {
        "place_id": "ChIJfar",
        "name": "Example Cafe",
        "location": {"lat": 30.2700, "lng": -97.7460},
    },
}
HERE = {"name": "Example Cafe", "lat": 30.2660, "lng": -97.7460}


def test_an_unambiguous_nearby_place_matches_and_records_its_basis():
    entry = match_entrance("E-001", HERE, {"ChIJnear": CATALOGUE["ChIJnear"]})
    assert entry["matched"] is True
    assert entry["place_ref"]["place_id"] == "ChIJnear"
    assert entry["distance_m"] == 0.0
    assert "names correspond" in entry["basis"]


def test_a_far_place_does_not_match():
    entry = match_entrance("E-001", HERE, {"ChIJfar": CATALOGUE["ChIJfar"]})
    assert entry["matched"] is False
    assert entry["place_ref"] is None
    assert "within 40 m" in entry["basis"]


def test_two_corresponding_places_are_ambiguous_and_do_not_match():
    catalogue = dict(CATALOGUE)
    catalogue["ChIJalso"] = {
        "place_id": "ChIJalso",
        "name": "Example Cafe",
        "location": {"lat": 30.26602, "lng": -97.74601},
    }
    entry = match_entrance("E-001", HERE, catalogue)
    assert entry["matched"] is False
    assert "ambiguous" in entry["basis"]


def test_a_different_business_at_the_same_spot_does_not_match():
    catalogue = {"ChIJother": dict(CATALOGUE["ChIJnear"], name="Royal Blue Grocery")}
    entry = match_entrance("E-001", HERE, catalogue)
    assert entry["matched"] is False


def test_an_entrance_with_no_surveyed_coordinates_is_recorded_unmatched():
    entry = match_entrance("E-030", None, CATALOGUE)
    assert entry["matched"] is False
    assert entry["place_ref"] is None
    assert "no surveyed door coordinates" in entry["basis"]


def test_every_entrance_gets_a_matching_entry_matched_or_not():
    entries = match_entrances(["E-001", "E-030"], {"E-001": HERE}, CATALOGUE)
    assert [entry["entrance_id"] for entry in entries] == ["E-001", "E-030"]
    assert all(entry["basis"] for entry in entries)


# --- the records this path builds ---------------------------------------------


def _assessment(entrance_id, **overrides):
    base = {
        "entrance_id": entrance_id,
        "captured_at": "2026-09-04T18:00:00Z",
        "view_count": 5,
        "faces_blurred": 0,
        "mode": "integrated",
        "verdicts": {"ramp_or_bevel": "present"},
        "confidences": {"ramp_or_bevel": 80},
        "face_check": "clear",
        "error": None,
    }
    base.update(overrides)
    return base


def test_a_built_record_carries_the_capture_date_and_references_no_bytes():
    matches = match_entrances(["E-001"], {"E-001": HERE},
                              {"ChIJnear": CATALOGUE["ChIJnear"]})
    (record,) = build_records({"E-001": _assessment("E-001")}, matches)
    assert record["created_at"] == "2026-09-04T18:00:00Z"
    assert record["entrance_id"] == "E-001"
    assert record["place_ref"]["place_id"] == "ChIJnear"
    assert record["image_keys"] == []
    assert record["quarantined_count"] == 0


def test_an_unmatched_entrance_still_becomes_a_record_with_no_place_ref():
    matches = match_entrances(["E-030"], {}, CATALOGUE)
    (record,) = build_records({"E-030": _assessment("E-030")}, matches)
    assert record["place_ref"] is None
    assert record["entrance_id"] == "E-030"


# --- the committed publication ------------------------------------------------


#: The publication itself needs live model calls, so on a checkout where it has
#: not been run yet these acceptance tests skip rather than fail. They are not
#: optional: the moment `python -m frontdoor.scan_publish` writes the two
#: artefacts, every one of them starts running and the count, the seal and the
#: served tier are all pinned.
def _require_published():
    records = load_scan_records(STORE)
    if not records or not MATCHES.is_file():
        pytest.skip(
            "the on-site publication has not been run on this checkout; "
            "run python -m frontdoor.scan_publish to produce data/scans.jsonl "
            "and data/scan_matches.json"
        )
    return records


@pytest.fixture(scope="module")
def published():
    return _require_published()


@pytest.fixture(scope="module")
def matches():
    _require_published()
    return json.loads(MATCHES.read_text(encoding="utf-8"))


def test_the_published_count_is_exactly_the_forty_six(published):
    assert len(published) == PUBLISHED_COUNT
    assert len({record["entrance_id"] for record in published}) == PUBLISHED_COUNT


def test_no_sealed_identifier_appears_anywhere_in_the_store(published):
    text = STORE.read_text(encoding="utf-8")
    for entrance_id in SEALED:
        assert entrance_id not in text
    assert not {r["entrance_id"] for r in published} & set(SEALED)


def test_no_sealed_identifier_appears_anywhere_in_the_matching_report(matches):
    text = MATCHES.read_text(encoding="utf-8")
    for entrance_id in SEALED:
        assert entrance_id not in text


def test_every_published_entrance_is_one_the_seed_says_is_publishable(published):
    publishable = set(publishable_entrances(MANIFEST))
    for record in published:
        entrance_id = record["entrance_id"]
        assert entrance_id in publishable
        assert assign_split(entrance_id) != "sealed"


def test_every_record_carries_a_usable_capture_date(published):
    for record in published:
        assert re.match(r"^\d{4}-\d{2}-\d{2}T", record["created_at"] or ""), record
        assert record["contributor"] == "on_site_capture"


def test_every_record_is_matched_to_a_place_or_recorded_unmatched(
        published, matches):
    by_entrance = {entry["entrance_id"]: entry for entry in matches}
    assert set(by_entrance) == {record["entrance_id"] for record in published}
    for record in published:
        entry = by_entrance[record["entrance_id"]]
        assert entry["basis"], f"{record['entrance_id']} has no recorded basis"
        if entry["matched"]:
            assert record["place_ref"]["place_id"] == entry["place_ref"]["place_id"]
        else:
            assert record["place_ref"] is None


def test_no_record_references_an_image(published):
    for record in published:
        assert record["image_keys"] == []


def test_every_matched_place_exists_in_the_committed_catalogue(matches):
    catalogue = json.loads(DATASET.read_text(encoding="utf-8"))
    for entry in matches:
        if entry["matched"]:
            assert entry["place_ref"]["place_id"] in catalogue


# --- what /map/data serves ----------------------------------------------------


@pytest.fixture
def map_payload(monkeypatch, published):
    from frontdoor_server.app import create_app

    monkeypatch.setenv("FRONTDOOR_MAP_DATASET", str(DATASET))
    monkeypatch.setenv("FRONTDOOR_SCANS", str(STORE))
    return create_app().test_client().get("/map/data").get_json()


def test_map_data_serves_every_matched_scan_as_scanned_on_site(
        map_payload, matches, published):
    by_place = {pin["place_id"]: pin for pin in map_payload["pins"]}
    dates = {
        record["entrance_id"]: record["created_at"][:10] for record in published
    }
    matched = [entry for entry in matches if entry["matched"]]
    assert matched, "the publication matched no place at all"
    for entry in matched:
        pin = by_place[entry["place_ref"]["place_id"]]
        assert pin["state"] == "verified_accessible"
        assert pin["ai_estimated"] is False
        assert pin["last_scanned"] == dates[entry["entrance_id"]]
        assert pin["imagery_date"] == dates[entry["entrance_id"]]
        line = pin["provenance"][0]
        assert line["source"] == SCAN_SOURCE
        assert line["label"] == f"Scanned on-site — {dates[entry['entrance_id']]}"


def test_map_data_carries_no_sealed_identifier(map_payload):
    served = json.dumps(map_payload)
    for entrance_id in SEALED:
        assert entrance_id not in served


def test_an_unmatched_scan_does_not_invent_a_pin(map_payload, matches):
    """A record with no place reference adds no location, so it draws nothing."""
    unmatched = [entry for entry in matches if not entry["matched"]]
    if not unmatched:
        pytest.skip("every entrance matched a place")
    assert not [
        pin for pin in map_payload["pins"] if pin["place_id"].startswith("scan:")
    ]
