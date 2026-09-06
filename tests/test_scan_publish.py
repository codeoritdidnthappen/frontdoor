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
    load_identifications,
    match_entrance,
    match_entrances,
    publishable_entrances,
)
from frontdoor.scan_records import SCAN_SOURCE, load_scan_records
from frontdoor.screening import (
    CRITERIA_KEYS,
    FAILURE_REJECTED,
    ScreeningEngine,
    SealedSplitError,
)
from frontdoor.split import assign_split, canonical_entrance_id

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "data" / "manifest.csv"
STORE = REPO / "data" / "published_scans.jsonl"
MATCHES = REPO / "data" / "scan_matches.json"
DATASET = REPO / "data" / "precatalogue.json"
IDENTIFICATIONS = REPO / "data" / "entrance_identification.json"

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
    rejected = 0
    failed = 0


class RejectedSummary:
    """No verdict, and a rejection saying why -- never a clean abstention."""

    verdict = None
    rejected = 1
    failed = 0


class FakeAssessment:
    criteria = {key: {"confidence": 60} for key in CRITERIA_KEYS}
    face_check = "clear"
    error = None
    failure = None
    attempts = 1
    rejected_attempts = 0


class FakeScreening:
    mode = "integrated"
    assessments = (FakeAssessment(),)
    summary = {key: FakeSummary() for key in CRITERIA_KEYS}


class FailedAssessment:
    """What the engine hands back when the model answered off-vocabulary.

    The engine has already spent its own bounded retry by this point
    (TICK-399) and salvaged nothing, so there are no criteria and the failure
    is named as a rejection rather than left as bare text.
    """

    criteria = None
    face_check = "clear"
    error = "ResponseRejected: criterion handrails has invalid verdict"
    failure = FAILURE_REJECTED
    attempts = 2
    rejected_attempts = 2


class FailedScreening:
    mode = "integrated"
    assessments = (FailedAssessment(),)
    summary = {key: RejectedSummary() for key in CRITERIA_KEYS}


class FlakyEngine:
    """Fails its first ``failures`` calls, then answers."""

    def __init__(self, failures):
        self.failures = failures
        self.calls = 0

    def screen_entrance_integrated(self, entrance_id, images):
        self.calls += 1
        if self.calls <= self.failures:
            return FailedScreening()
        return FakeScreening()


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

#: A published catalogue row (name and location committed) and one the
#: catalogue holds by identifier alone, which is the shape the walked-blocks
#: sweep writes under #242.
CATALOGUE = {
    "ChIJnear": {
        "place_id": "ChIJnear",
        "name": "Example Cafe",
        "location": {"lat": 30.2660, "lng": -97.7460},
    },
    "ChIJidonly": {"place_id": "ChIJidonly"},
}


def _identification(**overrides):
    record = {
        "status": "identified",
        "name": "Example Cafe",
        "confidence": "high",
        "basis": ["storefront_signage"],
        "place_id": "ChIJnear",
        "place_match": {
            "how": {"anchor": "address_geocode", "anchor_between": None,
                    "bracket_span_m": None, "distance_m": 11.9,
                    "matched_name": "Example Cafe"},
            "unmatched_reason": None,
            "detail": None,
        },
    }
    record.update(overrides)
    return record


def test_a_resolved_identification_matches_and_carries_its_own_provenance():
    entry = match_entrance("E-001", _identification(), CATALOGUE)
    assert entry["matched"] is True
    assert entry["renderable"] is True
    assert entry["place_ref"] == {
        "place_id": "ChIJnear", "name": "Example Cafe",
        "lat": 30.2660, "lng": -97.7460,
    }
    # The match pass's own basis, not a restatement of it.
    assert entry["how"]["anchor"] == "address_geocode"
    assert "11.9 m" in entry["basis"]
    assert "high confidence" in entry["basis"]


def test_the_match_pass_reason_is_carried_through_verbatim_when_unmatched():
    entry = match_entrance("E-026", _identification(
        place_id=None,
        place_match={"how": None, "unmatched_reason": "bracket_too_wide",
                     "detail": "bracketed by E-024 and E-030, 206 m apart"},
    ), CATALOGUE)
    assert entry["matched"] is False
    assert entry["place_ref"] is None
    assert entry["not_pinnable_reason"] == "bracket_too_wide"
    assert "206 m apart" in entry["basis"]


def test_a_low_confidence_identification_never_becomes_a_confident_pin():
    """#341 grades a reading it could not make unambiguously `low`.

    A pin says the business by name and stamps it scanned on-site; there is no
    room on it for "we think this is whose door it is". So the scan is
    published with no place at all rather than as a claim we cannot back.
    """
    entry = match_entrance("E-034", _identification(confidence="low"), CATALOGUE)
    assert entry["matched"] is False
    assert entry["place_ref"] is None
    assert entry["not_pinnable_reason"] == "low_confidence_identification"
    assert "'low'" in entry["basis"]


@pytest.fixture
def no_image_work(monkeypatch):
    """The privacy pass and the resize, stubbed. FakeCapture carries no real
    image bytes, and neither step is what these tests are about."""
    monkeypatch.setattr(
        "frontdoor.scan_publish.process_upload",
        lambda image_bytes: SimpleNamespace(image_bytes=image_bytes, face_count=0),
    )
    monkeypatch.setattr("frontdoor.scan_publish._fit_for_the_model", lambda b: b)


def test_an_off_vocabulary_answer_is_asked_again_and_never_reinterpreted(
        no_image_work):
    """The model sometimes answers `not_applicable` on a four-criterion
    verdict, which is the ADA-check vocabulary in the wrong block. Guessing
    what it meant would be exactly the collapsing of `not_visible` into
    `absent` the project forbids, so the entrance is asked again -- and a door
    that keeps answering off-vocabulary publishes no verdicts at all."""
    engine = FlakyEngine(failures=2)
    results = assess_publishable(
        {"E-001": ["E-001-1"]},
        get_capture=lambda capture_id: FakeCapture(capture_id),
        engine=engine,
    )
    assert engine.calls == 3
    assert results["E-001"]["error"] is None

    stubborn = FlakyEngine(failures=99)
    results = assess_publishable(
        {"E-001": ["E-001-1"]},
        get_capture=lambda capture_id: FakeCapture(capture_id),
        engine=stubborn,
    )
    assert stubborn.calls == 3
    assert results["E-001"]["error"]
    # The record says WHAT went wrong, not just that something did: a rejected
    # reply is a failure of the call, and every criterion is recorded as not
    # assessed rather than as a verdict guessed from an off-vocabulary word.
    assert results["E-001"]["failure"] == FAILURE_REJECTED
    assert set(results["E-001"]["verdicts"].values()) == {"not_assessed"}


def test_a_retry_is_a_fresh_call_into_the_sealed_guard_not_a_way_round_it(
        no_image_work):
    """Every attempt goes through assess_entrance, so three attempts are three
    refusals for a sealed entrance, never one refusal and two free passes."""
    engine = FlakyEngine(failures=99)
    with pytest.raises(NotPublishableError):
        assess_publishable(
            {"E-002": ["E-002-1"]},
            get_capture=lambda capture_id: FakeCapture(capture_id),
            engine=engine,
        )
    assert engine.calls == 0


def test_an_entrance_whose_assessment_produced_nothing_gets_no_place():
    """A matched record upgrades the pin to Scanned on-site. The tier says a
    scan of this door is what did it, so a failed assessment must not carry
    one: the record is still published, with no place and no claim."""
    entry = match_entrance("E-010", _identification(), CATALOGUE, assessed=False)
    assert entry["matched"] is False
    assert entry["place_ref"] is None
    assert entry["not_pinnable_reason"] == "assessment_produced_no_verdicts"
    entries = match_entrances(["E-001", "E-010"],
                              {"E-001": _identification(),
                               "E-010": _identification()},
                              CATALOGUE, unassessed=["E-010"])
    assert [e["matched"] for e in entries] == [True, False]


def test_an_unidentified_entrance_is_recorded_unmatched_with_its_reason():
    entry = match_entrance("E-030", _identification(
        status="unidentified", name=None, confidence=None, place_id=None,
        place_match={"how": None, "unmatched_reason": "not_identified",
                     "detail": "the entrance was never identified"},
    ), CATALOGUE)
    assert entry["matched"] is False
    assert entry["not_pinnable_reason"] == "not_identified"


def test_an_entrance_absent_from_the_identification_file_is_unmatched():
    entry = match_entrance("E-030", None, CATALOGUE)
    assert entry["matched"] is False
    assert entry["place_ref"] is None
    assert entry["not_pinnable_reason"] == "no_identification_record"


def test_a_place_the_catalogue_holds_by_identifier_alone_draws_no_pin():
    """#242 keeps the walked-blocks rows identifier-only, so there is no name
    or location to put on a pin -- and none is invented from anywhere else."""
    entry = match_entrance("E-020", _identification(place_id="ChIJidonly"),
                           CATALOGUE)
    assert entry["matched"] is True
    assert entry["renderable"] is False
    assert entry["place_ref"] == {"place_id": "ChIJidonly"}
    assert entry["not_pinnable_reason"] == "place_not_in_published_catalogue"
    assert "draws no pin yet" in entry["basis"]


def test_every_entrance_gets_a_matching_entry_matched_or_not():
    entries = match_entrances(
        ["E-001", "E-030"], {"E-001": _identification()}, CATALOGUE)
    assert [entry["entrance_id"] for entry in entries] == ["E-001", "E-030"]
    assert all(entry["basis"] for entry in entries)


def test_the_committed_identification_file_loads_and_is_keyed_by_entrance():
    identifications = load_identifications(IDENTIFICATIONS)
    assert set(identifications) == set(publishable_entrances(MANIFEST))
    for entrance_id in SEALED:
        assert entrance_id not in identifications


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
    matches = match_entrances(["E-001"], {"E-001": _identification()}, CATALOGUE)
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
            "run python -m frontdoor.scan_publish to produce "
            "data/published_scans.jsonl and data/scan_matches.json"
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


def test_every_matched_place_is_in_the_catalogue_or_says_it_is_not(matches):
    """A match either draws a pin from the published catalogue, or records
    that the catalogue does not carry the place yet. Nothing in between: a
    place_ref never carries a name or a location from anywhere else."""
    catalogue = json.loads(DATASET.read_text(encoding="utf-8"))
    for entry in matches:
        if not entry["matched"]:
            continue
        place_id = entry["place_ref"]["place_id"]
        if entry["renderable"]:
            assert place_id in catalogue
            assert catalogue[place_id].get("location")
        else:
            assert place_id not in catalogue or not catalogue[place_id].get(
                "location")
            assert entry["not_pinnable_reason"] == (
                "place_not_in_published_catalogue")
            assert set(entry["place_ref"]) <= {"place_id", "name"}


def test_no_published_record_states_a_negative_conclusion(published, matches):
    """The honesty gate, run over the bytes that ship (#333, #385).

    A published record carries per-criterion verdicts and a place; it must
    never carry prose that concludes anything about whether a person can get
    in. Grepping the artefacts themselves is the check, because that is what
    a reader sees.
    """
    forbidden = (
        "cannot get", "can not get", "may not be able", "not accessible",
        "inaccessible", "unlikely", "no wheelchair", "not wheelchair",
        "cannot enter", "unable to enter", "denied entry",
    )
    for artefact in (STORE, MATCHES):
        text = artefact.read_text(encoding="utf-8").casefold()
        for phrase in forbidden:
            assert phrase not in text, f"{artefact.name} contains {phrase!r}"


def test_no_published_verdict_is_outside_the_screening_vocabulary(published):
    """`absent` stays `absent` in the record and `not_visible` stays
    `not_visible`; collapsing one into the other would lose the difference
    between "the photo shows there is none" and "the photo does not show"."""
    allowed = {"present", "absent", "not_visible", "not_assessed"}
    for record in published:
        # A subset, not an equality: a criterion added after this run was
        # published is simply absent from these records, and the map renders an
        # absent criterion as "Not assessed", which is what it is. A verdict
        # this vocabulary does not contain is the failure worth catching.
        assert set(record["verdicts"]) <= set(CRITERIA_KEYS), record["entrance_id"]
        assert record["verdicts"], record["entrance_id"]
        for key, verdict in record["verdicts"].items():
            assert verdict in allowed, (record["entrance_id"], key, verdict)


# --- what /map/data serves ----------------------------------------------------


@pytest.fixture
def map_payload(monkeypatch, tmp_path, published):
    """/map/data over the CURATED store alone.

    FRONTDOOR_SCANS is pointed at an empty file on purpose: the runtime
    community store is a mounted volume in production and whatever a developer
    has published locally must not decide whether this test passes.
    """
    from frontdoor_server.app import create_app

    runtime = tmp_path / "scans.jsonl"
    runtime.write_text("", encoding="utf-8")
    monkeypatch.setenv("FRONTDOOR_MAP_DATASET", str(DATASET))
    monkeypatch.setenv("FRONTDOOR_PUBLISHED_SCANS", str(STORE))
    monkeypatch.setenv("FRONTDOOR_SCANS", str(runtime))
    return create_app().test_client().get("/map/data").get_json()


def test_the_curated_store_is_the_one_map_data_loads(map_payload, published):
    assert map_payload["published_scans_loaded"] == len(published)
    assert map_payload["published_scans_error"] is None
    assert map_payload["published_scans_skipped"] == 0


def test_map_data_serves_every_matched_scan_as_scanned_on_site(
        map_payload, matches, published):
    by_place = {pin["place_id"]: pin for pin in map_payload["pins"]}
    dates = {
        record["entrance_id"]: record["created_at"][:10] for record in published
    }
    matched = [entry for entry in matches if entry["renderable"]]
    assert matched, "the publication put nothing on the map at all"
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


def test_a_place_held_by_identifier_alone_draws_no_pin_either(
        map_payload, matches):
    """It is keyed, and it is invisible until the catalogue carries the place.

    The alternative would be a pin at coordinates taken from somewhere the
    published catalogue may not keep them, which is the licensing posture #242
    settled and not something a publication run gets to reopen.
    """
    by_place = {pin["place_id"]: pin for pin in map_payload["pins"]}
    keyed_only = [e for e in matches if e["matched"] and not e["renderable"]]
    if not keyed_only:
        pytest.skip("every matched place is in the published catalogue")
    for entry in keyed_only:
        assert entry["place_ref"]["place_id"] not in by_place


def test_the_map_publishes_no_negative_state_or_wording(map_payload):
    """Green-or-Gray, checked on what /map/data actually serves."""
    for pin in map_payload["pins"]:
        assert pin["state"] in ("verified_accessible", "not_yet_checked")
        assert pin["label"] in ("Verified Accessible", "Not Yet Checked")
        for item in pin["checklist"]:
            assert item["observation"] in (
                "visible", "not_visible", "not_assessed")
            assert item["observation_label"] in (
                "Visible in photos", "Not visible in photos", "Not assessed")
    served = json.dumps(map_payload).casefold()
    for phrase in ("cannot get", "may not be able", "not accessible",
                   "unlikely", "inaccessible"):
        assert phrase not in served


class RecoveredScreening:
    """All four verdicts, out of a reply that was still refused somewhere.

    What the engine hands back when it recovered every criterion but the ADA
    half of the same reply was refused: usable verdicts, and an error beside
    them.
    """

    mode = "integrated"
    summary = {key: FakeSummary() for key in CRITERIA_KEYS}

    class _Assessment:
        criteria = {key: {"confidence": 60} for key in CRITERIA_KEYS}
        face_check = "clear"
        error = "ResponseRejected: model must not supply aggregate fields"
        failure = FAILURE_REJECTED
        attempts = 2
        rejected_attempts = 2

    assessments = (_Assessment(),)


class RecoveredThenCleanEngine:
    """First call recovers everything but is still rejected; second is clean."""

    def __init__(self):
        self.calls = 0

    def screen_entrance_integrated(self, entrance_id, images):
        self.calls += 1
        return RecoveredScreening() if self.calls == 1 else FakeScreening()


def test_tick_399_a_clean_attempt_beats_a_recovered_one_with_the_same_verdicts(
        no_image_work, tmp_path):
    """Verdict count alone is not enough to pick the attempt to publish.

    A first attempt that recovered all four criteria out of a rejected reply
    carries the same four verdicts as a clean second attempt -- and an error.
    Keeping it publishes a record that says the assessment failed when a clean
    answer was in hand, and blocks the cache write, so the next run pays for
    the whole entrance again.
    """
    engine = RecoveredThenCleanEngine()
    results = assess_publishable(
        {"E-001": ["E-001-1"]},
        get_capture=lambda capture_id: FakeCapture(capture_id),
        engine=engine,
        cache_dir=tmp_path,
    )
    assert engine.calls == 2
    result = results["E-001"]
    assert result["error"] is None
    assert result["failure"] is None
    assert (tmp_path / "E-001.json").is_file()  # cached, so a resume is free
