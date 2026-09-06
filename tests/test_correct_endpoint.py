"""POST /correct, GET /correct/mine, and the re-look that changes only freshness (TICK-387).

One test per acceptance criterion on #387, named so the mapping is legible, plus
the two invariants the feature is most likely to erode later:

  * a correction NEVER changes a criterion verdict -- pinned both behaviourally
    (the whole /map/data payload is unchanged except for the two freshness
    fields) and structurally (`apply_relook` may write only RELOOK_FIELDS, so
    wiring a verdict up later fails here rather than shipping);
  * the map stays Green-or-Gray: no correction, dispute or re-look can produce
    a state, label or observation outside the public vocabulary.

Fully mocked: object storage is injected through app.config[STORE_KEY], the
correction store and the map dataset are tmp_path files, and no model is
called at all -- /correct does not use one.
"""

import io
import json

import pytest

from frontdoor import corrections as corrections_mod
from frontdoor.corrections import (
    RELOOK_FIELDS,
    RELOOK_MIN_CONTRIBUTORS,
    apply_relook,
    load_corrections,
    review_queue,
)
from frontdoor.faceblur import FaceDetectorError
from frontdoor.map_states import (
    OBSERVATION_LABELS,
    STAMP_LABELS,
    STATES,
    checklist_for_row,
    state_for_row,
)
from frontdoor.storage import StorageError
from frontdoor_server import correct_view
from frontdoor_server.app import create_app
from frontdoor_server.correct_view import STORE_KEY
from tests.test_screen_endpoint import image_part, real_jpeg

CONTRIBUTOR = "em_1111111111111111"
OTHER_CONTRIBUTOR = "em_2222222222222222"

PLACE = {"place_id": "ChIJexample", "name": "Example Cafe",
         "lat": 40.0, "lng": -75.0}


def dataset_row(**overrides):
    base = {
        "place_id": "ChIJexample",
        "name": "Example Cafe",
        "location": {"lat": 40.0, "lng": -75.0},
        "source": "streetview",
        "status": "ai_estimated",
        "imagery_date": "2024-06-01",
        "criteria": {
            "ramp_or_bevel": {"verdict": "present", "confidence": 0.9},
            "handrails": {"verdict": "not_visible", "confidence": 0.6},
            "accessible_door_hardware": {"verdict": "absent", "confidence": 0.8},
            "accessibility_signage": {"verdict": "not_visible", "confidence": None},
        },
    }
    base.update(overrides)
    return base


class FakeStore:
    """ObjectStore as correct_view uses it: .put only."""

    def __init__(self, put_raises=None):
        self.objects = {}
        self.puts = []
        self._put_raises = put_raises

    def put(self, key, body, *, if_absent=False):
        if self._put_raises is not None:
            raise self._put_raises
        self.puts.append((key, body, if_absent))
        self.objects[key] = body


@pytest.fixture
def store_paths(tmp_path, monkeypatch):
    """A corrections store, an empty scan store and a one-row map dataset."""
    corrections_path = tmp_path / "corrections.jsonl"
    dataset_path = tmp_path / "precatalogue.json"
    dataset_path.write_text(
        json.dumps({"ChIJexample": dataset_row()}), encoding="utf-8"
    )
    monkeypatch.setenv("FRONTDOOR_CORRECTIONS", str(corrections_path))
    monkeypatch.setenv("FRONTDOOR_MAP_DATASET", str(dataset_path))
    monkeypatch.setenv("FRONTDOOR_SCANS", str(tmp_path / "scans.jsonl"))
    return {"corrections": corrections_path, "dataset": dataset_path,
            "tmp": tmp_path}


@pytest.fixture
def store():
    return FakeStore()


@pytest.fixture
def client(store):
    app = create_app()
    app.config[STORE_KEY] = store
    return app.test_client()


def post_correct(client, form=None, photo=None, contributor=CONTRIBUTOR):
    data = {"category": "entrance_features", "note": "The knob is now a lever."}
    data.update(PLACE)
    if form:
        data.update(form)
    data = {k: v for k, v in data.items() if v is not None}
    if photo is not None:
        data["photo"] = photo
    headers = {"X-Frontdoor-Contributor": contributor} if contributor else {}
    return client.post("/correct", data=data,
                       content_type="multipart/form-data", headers=headers)


def write_dataset(path, rows):
    path.write_text(json.dumps(rows), encoding="utf-8")


# --- AC1: the button reaches the server, and a failure says so ---------------


def test_ac1_a_correction_reaches_the_server_and_is_acknowledged(client, store_paths):
    response = post_correct(client)
    assert response.status_code == 201
    body = response.get_json()
    assert body["received"] is True
    assert body["correction_id"]
    assert body["status"] == "received"


def test_ac1_the_send_button_posts_and_never_writes_a_local_row():
    """The defect itself: `corrections.unshift(...)` in one browser.

    The served page must call POST /correct and must not carry the design
    source's local append or its seeded examples -- either one puts a note in
    front of a person that the server has never heard of.
    """
    page = create_app().test_client().get("/app").get_data(as_text=True)
    assert "const CORRECT_API = '/correct';" in page
    assert "fetch(CORRECT_API,{method:'POST'" in page
    assert "corrections.unshift(" not in page
    assert "seeded with three worked examples" not in page


def test_ac1_a_failed_send_says_so_rather_than_showing_the_done_screen():
    """Same rule the scan path got after the fabricated-verdict fix."""
    page = create_app().test_client().get("/app").get_data(as_text=True)
    assert "Couldn't send — " in page
    assert "Opened without a server — a correction cannot be sent from here" in page
    # The confirmation screen is reached only after a 201.
    after_ok = page.split("if(!out.ok){", 1)[1]
    assert after_ok.index("return;") < after_ok.index("goScreen('screen-corr-done')")


def test_ac1_the_confirmation_screen_only_promises_what_the_server_does():
    page = create_app().test_client().get("/app").get_data(as_text=True)
    assert "Your note joins a <b>review queue</b> a person works through" in page
    # The design promised the note becomes a receipt source, and a notification.
    # Neither happens: a correction changes no verdict, and notifying the
    # contributor is out of scope on #387.
    assert "Your note becomes a <b>dated source</b>" not in page
    assert "You'll hear back only if" not in page
    # ...and neither does the row you tap in My corrections.
    assert "stays on the receipt as its own dated source" not in page
    assert "Corrections stay human — a person reads every note before anything changes" in page


def test_a_correction_with_neither_a_note_nor_a_photo_is_refused(client, store_paths):
    response = post_correct(client, form={"note": ""})
    assert response.status_code == 422
    assert response.get_json()["error"] == "empty correction"
    assert not store_paths["corrections"].exists()


def test_a_note_longer_than_the_sheet_allows_is_refused(client, store_paths):
    response = post_correct(client, form={"note": "x" * 301})
    assert response.status_code == 422
    assert response.get_json()["error"] == "note too long"


def test_a_correction_without_a_place_reference_is_refused(client, store_paths):
    response = client.post(
        "/correct",
        data={"category": "other", "note": "hello"},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "missing place reference"


def test_an_unknown_category_is_refused(client, store_paths):
    response = post_correct(client, form={"category": "verdict_is_wrong"})
    assert response.status_code == 422
    assert response.get_json()["error"] == "invalid category"


def test_the_sheets_own_wording_is_accepted_as_a_category(client, store_paths):
    response = post_correct(client, form={"category": "Business name or location"})
    assert response.status_code == 201
    record = load_corrections(store_paths["corrections"])[0]
    assert record["category"] == "business_identity"


# --- AC2: it persists, append-only, on the volume ----------------------------


def test_ac2_the_correction_is_appended_to_the_store_as_one_jsonl_line(
    client, store_paths
):
    post_correct(client, form={"note": "first"})
    post_correct(client, form={"note": "second"})
    text = store_paths["corrections"].read_text(encoding="utf-8")
    assert text.endswith("\n")
    lines = [line for line in text.splitlines() if line.strip()]
    assert len(lines) == 2
    assert [json.loads(line)["note"] for line in lines] == ["first", "second"]


def test_ac2_a_torn_last_line_is_recovered_rather_than_wedging_the_store(
    client, store_paths
):
    """The scan store's discipline, reused rather than re-implemented."""
    store_paths["corrections"].write_text(
        '{"correction_id": "aaa", "note": "complete"}\n{"correction_id": "bbb"',
        encoding="utf-8",
    )
    assert post_correct(client).status_code == 201
    records = load_corrections(store_paths["corrections"])
    assert [r.get("correction_id") for r in records][0] == "aaa"
    assert len(records) == 2  # the torn line was dropped, not concatenated


def test_ac2_a_missing_volume_is_a_503_that_says_it_was_not_received(
    client, store_paths, monkeypatch
):
    monkeypatch.setenv(
        "FRONTDOOR_CORRECTIONS",
        str(store_paths["tmp"] / "not-mounted" / "corrections.jsonl"),
    )
    response = post_correct(client)
    assert response.status_code == 503
    assert response.get_json()["error"] == "correction not received"


def test_ac2_the_default_store_sits_beside_the_scan_records():
    from frontdoor.scan_records import DEFAULT_SCANS_PATH

    from frontdoor.corrections import DEFAULT_CORRECTIONS_PATH

    assert (DEFAULT_CORRECTIONS_PATH.rsplit("/", 1)[0]
            == DEFAULT_SCANS_PATH.rsplit("/", 1)[0])


# --- AC3: photos are privacy-processed first, and the failure path is closed --


def test_ac3_only_privacy_processed_bytes_are_stored(client, store, store_paths):
    raw = real_jpeg()
    response = post_correct(client, photo=image_part(data=raw))
    assert response.status_code == 201
    assert len(store.puts) == 1
    key, body, if_absent = store.puts[0]
    assert key.startswith("open/corrections/")
    assert if_absent is True
    assert body != raw, "the raw upload reached storage unprocessed"


def test_ac3_the_stored_key_is_the_one_recorded(client, store, store_paths):
    post_correct(client, photo=image_part())
    record = load_corrections(store_paths["corrections"])[0]
    assert record["image_key"].startswith("corrections/")
    assert store.puts[0][0] == "open/" + record["image_key"]


def test_ac3_undecodable_bytes_store_nothing_and_record_nothing(
    client, store, store_paths
):
    response = post_correct(
        client, photo=(io.BytesIO(b"not-an-image"), "a.png", "image/png")
    )
    assert response.status_code == 422
    assert store.puts == []
    assert not store_paths["corrections"].exists()


def test_ac3_a_detector_non_answer_is_fail_closed(
    client, store, store_paths, monkeypatch
):
    """No answer from the detector means nobody can say the faces are blurred.

    Nothing is stored and nothing is recorded -- a note whose photo silently
    vanished is the same lie in a smaller font.
    """
    def refuse(_raw):
        raise FaceDetectorError("the detector did not answer")

    monkeypatch.setattr(correct_view, "process_upload", refuse)
    response = post_correct(client, photo=image_part())
    assert response.status_code == 500
    assert store.puts == []
    assert not store_paths["corrections"].exists()


def test_ac3_the_privacy_pass_runs_before_anything_is_written(
    client, store, store_paths, monkeypatch
):
    """Ordering, not just outcome: storage is never touched before the blur."""
    seen = []

    real = correct_view.process_upload

    def watched(raw):
        seen.append(("processed", len(store.puts)))
        return real(raw)

    monkeypatch.setattr(correct_view, "process_upload", watched)
    post_correct(client, photo=image_part())
    assert seen == [("processed", 0)]


def test_ac3_a_storage_failure_writes_no_correction_at_all(store_paths):
    app = create_app()
    app.config[STORE_KEY] = FakeStore(put_raises=StorageError("bucket is gone"))
    response = post_correct(app.test_client(), photo=image_part())
    assert response.status_code == 503
    assert response.get_json()["error"] == "correction not received"
    assert not store_paths["corrections"].exists(), (
        "the note was written without the photo the person attached to it"
    )


def test_ac3_the_module_uses_faceblurs_public_entry_point():
    source = (
        __import__("pathlib").Path(correct_view.__file__).read_text(encoding="utf-8")
    )
    assert "from frontdoor.faceblur import" in source
    assert "process_upload(raw)" in source
    for private in ("_detect(", "_blur(", "_encode(", "_decode("):
        assert private not in source, "correct_view reaches past process_upload"


def test_a_non_image_content_type_is_refused(client, store, store_paths):
    response = post_correct(
        client, photo=(io.BytesIO(b"hello"), "a.txt", "text/plain")
    )
    assert response.status_code == 415
    assert store.puts == []


def test_more_than_one_photo_is_refused(client, store, store_paths):
    data = {"category": "other", "note": "two photos"}
    data.update(PLACE)
    data["photo"] = [image_part("a.jpg"), image_part("b.jpg")]
    response = client.post("/correct", data=data,
                           content_type="multipart/form-data")
    assert response.status_code == 400
    assert response.get_json()["error"] == "too many images"
    assert store.puts == []


# --- AC4: a correction NEVER changes a criterion verdict ---------------------


def _map_payload(client):
    payload = client.get("/map/data").get_json()
    return {p["place_id"]: p for p in payload["pins"]}


def test_ac4_no_correction_of_any_category_changes_a_verdict(client, store_paths):
    before = _map_payload(client)
    for category in ("entrance_features", "business_identity",
                     "photo_issue", "other"):
        for who in (CONTRIBUTOR, OTHER_CONTRIBUTOR):
            assert post_correct(
                client,
                form={"category": category, "note": f"{category} from {who}"},
                contributor=who,
            ).status_code == 201
    after = _map_payload(client)
    for place_id, pin in after.items():
        was = before[place_id]
        assert pin["checklist"] == was["checklist"], "a correction moved a checklist entry"
        assert pin["state"] == was["state"]
        assert pin["label"] == was["label"]
        assert pin["ai_estimated"] == was["ai_estimated"]
        assert pin["owner_confirmed"] == was["owner_confirmed"]


def test_ac4_apply_relook_may_write_only_the_freshness_fields():
    """The pin that fails if somebody wires a verdict up later.

    apply_relook is the only function in frontdoor.corrections that touches a
    dataset row. If a future change makes it write a criterion, a status, a
    source or anything else, the key diff below stops being a subset of
    RELOOK_FIELDS and this fails.
    """
    dataset = {"ChIJexample": dataset_row()}
    corrections = [
        {"place_key": "ChIJexample", "category": "entrance_features",
         "created_at": f"2026-09-0{n}T10:00:00Z", "contributor": f"em_{n}"}
        for n in range(1, RELOOK_MIN_CONTRIBUTORS + 1)
    ]
    merged, requests = apply_relook(dataset, corrections)
    assert requests, "the corroborated correction did not register at all"
    row_before, row_after = dataset["ChIJexample"], merged["ChIJexample"]
    changed = {
        key for key in set(row_before) | set(row_after)
        if row_before.get(key) != row_after.get(key)
    }
    assert changed <= set(RELOOK_FIELDS), (
        f"a correction changed {sorted(changed - set(RELOOK_FIELDS))} on a map row"
    )
    assert state_for_row(row_after) == state_for_row(row_before)
    assert checklist_for_row(row_after) == checklist_for_row(row_before)


def test_ac4_only_the_freshness_fields_are_assignable_on_a_map_row():
    """A source-level pin, because the behavioural one only sees what is called.

    apply_relook is the one place a correction can reach a dataset row. Every
    literal key it assigns must be a freshness field; a future
    `row["criteria"] = ...` or `row["status"] = "..."` fails here whether or
    not any test happens to exercise that branch.
    """
    import inspect
    import re

    source = inspect.getsource(apply_relook)
    assigned = set(re.findall(r'\[\s*"([A-Za-z_]+)"\s*\]\s*=', source))
    assert assigned <= set(RELOOK_FIELDS), (
        f"apply_relook assigns {sorted(assigned - set(RELOOK_FIELDS))} on a map "
        "row; a correction must never change what the map says about a business"
    )
    # ...and nothing else in the module reaches a dataset row at all: the map
    # imports exactly these two names.
    from frontdoor_server import map_view

    reached = {
        name for name in dir(corrections_mod)
        if not name.startswith("_") and getattr(map_view, name, None)
        is getattr(corrections_mod, name)
    }
    assert reached == {"apply_relook", "load_correction_store",
                       "CORRECTIONS_ENV", "DEFAULT_CORRECTIONS_PATH"}


def test_ac4_a_correction_cannot_put_a_business_on_the_map():
    dataset = {"ChIJexample": dataset_row()}
    corrections = [
        {"place_key": "somewhere-else", "category": "entrance_features",
         "created_at": f"2026-09-0{n}T10:00:00Z", "contributor": f"em_{n}"}
        for n in range(1, RELOOK_MIN_CONTRIBUTORS + 1)
    ]
    merged, _ = apply_relook(dataset, corrections)
    assert set(merged) == {"ChIJexample"}


# --- AC5: a correction may lower freshness, and only freshness ---------------


def _corroborate(client, note="the ramp was removed last month"):
    for who in (CONTRIBUTOR, OTHER_CONTRIBUTOR)[:RELOOK_MIN_CONTRIBUTORS]:
        assert post_correct(
            client,
            form={"category": "entrance_features", "note": note},
            contributor=who,
        ).status_code == 201


def test_ac5_corroborated_corrections_mark_the_place_as_needing_a_re_look(
    client, store_paths
):
    assert _map_payload(client)["ChIJexample"].get("needs_relook") is not True
    _corroborate(client)
    pin = _map_payload(client)["ChIJexample"]
    assert pin["needs_relook"] is True
    assert pin["relook_since"]
    assert any(line["source"] == "community_correction"
               for line in pin.get("provenance", []))


def test_ac5_one_contributor_alone_cannot_mark_a_place_stale(client, store_paths):
    for n in range(4):
        post_correct(client, form={"note": f"note {n}"}, contributor=CONTRIBUTOR)
    assert _map_payload(client)["ChIJexample"].get("needs_relook") is not True


def test_ac5_anonymous_corrections_never_corroborate_each_other(
    client, store_paths
):
    for n in range(4):
        post_correct(client, form={"note": f"note {n}"}, contributor=None)
    assert _map_payload(client)["ChIJexample"].get("needs_relook") is not True


def test_ac5_a_photo_complaint_is_not_evidence_the_doorway_changed(
    client, store_paths
):
    for who in (CONTRIBUTOR, OTHER_CONTRIBUTOR):
        post_correct(client, form={"category": "photo_issue",
                                   "note": "blurry"}, contributor=who)
    assert _map_payload(client)["ChIJexample"].get("needs_relook") is not True


def test_ac5_a_re_look_is_answered_by_newer_evidence(client, store_paths):
    _corroborate(client)
    assert _map_payload(client)["ChIJexample"]["needs_relook"] is True
    write_dataset(
        store_paths["dataset"],
        {"ChIJexample": dataset_row(imagery_date="2030-01-01")},
    )
    assert _map_payload(client)["ChIJexample"].get("needs_relook") is not True


def test_ac5_the_re_look_reaches_the_card_as_the_existing_nudge():
    page = create_app().test_client().get("/app").get_data(as_text=True)
    assert "p.relook = pin.needs_relook===true" in page
    assert "if((p.tier==='est' && aged) || p.relook){" in page
    assert "Could you take another look?" in page


def test_ac5_an_unreadable_correction_store_is_reported_not_silent(
    client, store_paths
):
    store_paths["corrections"].write_text("", encoding="utf-8")
    payload = client.get("/map/data").get_json()
    assert "corrections_error" in payload
    page = create_app().test_client().get("/map").get_data(as_text=True)
    assert "payload.corrections_error" in page


# --- AC6: a dispute is distinguishable in the queue --------------------------


def test_ac6_entrance_features_against_a_scanned_place_is_a_dispute(
    client, store_paths
):
    write_dataset(
        store_paths["dataset"],
        {"ChIJexample": dataset_row(status="verified", source="community_scan")},
    )
    assert post_correct(client, form={"category": "entrance_features"}).status_code == 201
    record = load_corrections(store_paths["corrections"])[0]
    assert record["place_tier"] == "scanned"
    assert record["dispute"] is True


def test_ac6_entrance_features_against_an_owner_confirmed_place_is_a_dispute(
    client, store_paths
):
    write_dataset(
        store_paths["dataset"],
        {"ChIJexample": dataset_row(status="verified", source="owner_attested",
                                    owner_confirmed=True)},
    )
    post_correct(client, form={"category": "entrance_features"})
    record = load_corrections(store_paths["corrections"])[0]
    assert record["place_tier"] == "owner_confirmed"
    assert record["dispute"] is True


def test_ac6_the_same_note_against_an_estimate_is_a_routine_note(
    client, store_paths
):
    post_correct(client, form={"category": "entrance_features"})
    record = load_corrections(store_paths["corrections"])[0]
    assert record["place_tier"] == "estimated"
    assert record["dispute"] is False


def test_ac6_a_non_entrance_category_is_never_a_dispute(client, store_paths):
    write_dataset(
        store_paths["dataset"],
        {"ChIJexample": dataset_row(status="verified", source="community_scan")},
    )
    post_correct(client, form={"category": "photo_issue"})
    assert load_corrections(store_paths["corrections"])[0]["dispute"] is False


def test_ac6_the_tier_is_the_servers_answer_not_the_callers(client, store_paths):
    """A caller cannot promote its own note to a dispute, or demote one."""
    post_correct(client, form={"place_tier": "owner_confirmed", "dispute": "1"})
    record = load_corrections(store_paths["corrections"])[0]
    assert record["place_tier"] == "estimated"
    assert record["dispute"] is False


def test_ac6_disputes_sort_above_routine_notes_in_the_queue():
    notes = [
        {"correction_id": "old-dispute", "dispute": True,
         "created_at": "2026-01-01T00:00:00Z", "status": "received"},
        {"correction_id": "new-note", "dispute": False,
         "created_at": "2026-09-01T00:00:00Z", "status": "received"},
        {"correction_id": "older-note", "dispute": False,
         "created_at": "2026-08-01T00:00:00Z", "status": "received"},
    ]
    assert [r["correction_id"] for r in review_queue(notes)] == [
        "old-dispute", "new-note", "older-note",
    ]


def test_ac6_a_reviewed_record_leaves_the_open_queue():
    notes = [{"correction_id": "done", "dispute": True, "status": "reviewed",
              "created_at": "2026-09-01T00:00:00Z"}]
    assert review_queue(notes) == []
    assert len(review_queue(notes, include_resolved=True)) == 1


def test_ac6_the_queue_is_readable_and_marks_the_disputes():
    from frontdoor.corrections import format_queue

    lines = format_queue([
        {"dispute": True, "created_at": "2026-09-01T10:00:00Z",
         "place_ref": {"name": "Example Cafe"}, "category": "entrance_features",
         "place_tier": "scanned", "note": "the ramp is gone",
         "status": "received", "image_key": "corrections/x/" + "0" * 32 + ".jpg"},
        {"dispute": False, "created_at": "2026-08-01T10:00:00Z",
         "place_ref": {"name": "Other Place"}, "category": "other",
         "place_tier": "estimated", "note": "", "status": "received"},
    ])
    assert lines[0].startswith("DISPUTE")
    assert "+photo" in lines[0]
    assert lines[1].startswith("note")
    assert "(photo only)" in lines[1]


# --- AC7: the Contributions tab shows the server's state ---------------------


def test_ac7_a_contributor_reads_back_their_own_correction_and_its_status(
    client, store_paths
):
    post_correct(client, form={"note": "mine"}, contributor=CONTRIBUTOR)
    response = client.get(
        "/correct/mine", headers={"X-Frontdoor-Contributor": CONTRIBUTOR}
    )
    assert response.status_code == 200
    rows = response.get_json()["corrections"]
    assert [r["note"] for r in rows] == ["mine"]
    assert rows[0]["status"] == "received"


def test_ac7_a_reviewers_status_change_is_what_the_tab_then_shows(
    client, store_paths
):
    post_correct(client, form={"note": "mine"})
    records = load_corrections(store_paths["corrections"])
    records[0]["status"] = "reviewed"
    store_paths["corrections"].write_text(
        json.dumps(records[0], sort_keys=True) + "\n", encoding="utf-8"
    )
    rows = client.get(
        "/correct/mine", headers={"X-Frontdoor-Contributor": CONTRIBUTOR}
    ).get_json()["corrections"]
    assert rows[0]["status"] == "reviewed"


def test_ac7_one_contributor_never_reads_anothers_corrections(
    client, store_paths
):
    post_correct(client, form={"note": "mine"}, contributor=CONTRIBUTOR)
    post_correct(client, form={"note": "theirs"}, contributor=OTHER_CONTRIBUTOR)
    rows = client.get(
        "/correct/mine", headers={"X-Frontdoor-Contributor": CONTRIBUTOR}
    ).get_json()["corrections"]
    assert [r["note"] for r in rows] == ["mine"]


def test_ac7_reading_back_without_the_token_is_refused(client, store_paths):
    assert client.get("/correct/mine").status_code == 400


def test_ac7_the_page_reads_the_tab_from_the_server(client, store_paths):
    page = client.get("/app").get_data(as_text=True)
    assert "function loadMyCorrections(){" in page
    assert "fetch(CORRECT_API+'/mine'" in page
    assert "if(id==='screen-contrib'){ renderYourScans(); loadMyCorrections(); }" in page


def test_ac7_the_queue_flag_is_not_published_back_to_the_contributor(
    client, store_paths
):
    write_dataset(
        store_paths["dataset"],
        {"ChIJexample": dataset_row(status="verified", source="community_scan")},
    )
    post_correct(client, form={"category": "entrance_features"})
    rows = client.get(
        "/correct/mine", headers={"X-Frontdoor-Contributor": CONTRIBUTOR}
    ).get_json()["corrections"]
    assert "dispute" not in rows[0]
    assert "place_tier" not in rows[0]


def test_a_junk_contributor_header_is_dropped_not_stored(client, store_paths):
    post_correct(client, contributor="../../etc/passwd")
    assert load_corrections(store_paths["corrections"])[0]["contributor"] is None


# --- AC8: sealed entrances accept no corrections -----------------------------


SEALED = ("E-002", "E-005", "E-006", "E-011", "E-014", "E-015", "E-016",
          "E-021", "E-028", "E-029", "E-032", "E-036", "E-039", "E-044",
          "E-046", "E-052", "E-059", "E-064")


@pytest.mark.parametrize("entrance_id", SEALED)
def test_ac8_a_sealed_entrance_accepts_no_correction(
    client, store, store_paths, entrance_id
):
    response = post_correct(
        client, form={"entrance_id": entrance_id}, photo=image_part()
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "sealed entrance"
    assert store.puts == [], "a sealed entrance's photo reached storage"
    assert not store_paths["corrections"].exists()


def test_ac8_an_unsealed_entrance_is_accepted(client, store_paths):
    from frontdoor.split import assign_split

    unsealed = next(f"E-{n:03d}" for n in range(1, 70)
                    if assign_split(f"E-{n:03d}") != "sealed")
    assert post_correct(client, form={"entrance_id": unsealed}).status_code == 201


def test_ac8_the_sealed_check_runs_before_the_photo_is_read(
    client, store, store_paths, monkeypatch
):
    def refuse(_raw):  # pragma: no cover - must never be reached
        raise AssertionError("a sealed entrance's photo was processed")

    monkeypatch.setattr(correct_view, "process_upload", refuse)
    assert post_correct(
        client, form={"entrance_id": "E-014"}, photo=image_part()
    ).status_code == 403


# --- the map stays Green-or-Gray --------------------------------------------


def test_no_correction_produces_a_state_outside_green_or_gray(
    client, store_paths
):
    write_dataset(store_paths["dataset"], {
        "ChIJexample": dataset_row(),
        "scanned": dataset_row(place_id="scanned", name="Scanned Place",
                               location={"lat": 41.0, "lng": -75.0},
                               status="verified", source="community_scan"),
    })
    for key, place_id in (("a", "ChIJexample"), ("b", "scanned")):
        for who in (CONTRIBUTOR, OTHER_CONTRIBUTOR):
            post_correct(
                client,
                form={"place_id": place_id, "name": None, "lat": None,
                      "lng": None, "category": "entrance_features",
                      "note": "it changed"},
                contributor=who,
            )
    payload = client.get("/map/data").get_json()
    assert payload["pins"]
    for pin in payload["pins"]:
        assert pin["state"] in STATES
        assert pin["label"] == STAMP_LABELS[pin["state"]]
        for entry in pin["checklist"]:
            assert entry["observation_label"] == OBSERVATION_LABELS[entry["observation"]]


def test_a_dispute_never_turns_a_green_pin_neutral(client, store_paths):
    write_dataset(
        store_paths["dataset"],
        {"ChIJexample": dataset_row(status="verified", source="community_scan")},
    )
    before = _map_payload(client)["ChIJexample"]
    assert before["state"] == "verified_accessible"
    _corroborate(client)
    after = _map_payload(client)["ChIJexample"]
    assert after["state"] == "verified_accessible"
    assert after["label"] == before["label"]
    assert after["checklist"] == before["checklist"]
    assert after["needs_relook"] is True


def test_the_correct_route_is_outside_the_screening_cors_scope(
    client, store_paths
):
    """/correct is called same-origin from /app; a wildcard would open a public
    write path to origins with no reason to reach it."""
    response = post_correct(client)
    assert "Access-Control-Allow-Origin" not in response.headers


def test_two_reports_of_an_uncatalogued_doorway_share_a_key(store_paths, client):
    """Otherwise nobody could corroborate a place the map has never heard of.

    The scan merge's fallback key is built from the record's own id, which for
    a correction is a fresh uuid every time; the queue would then list two
    reports of the same doorway as two unrelated places.
    """
    for who in (CONTRIBUTOR, OTHER_CONTRIBUTOR):
        assert post_correct(
            client,
            form={"place_id": None, "name": "Unlisted Diner",
                  "lat": "10.0", "lng": "10.0"},
            contributor=who,
        ).status_code == 201
    keys = {r["place_key"] for r in load_corrections(store_paths["corrections"])}
    assert len(keys) == 1
    assert keys.pop().startswith("correction:")


# --- the review pass: failures this feature must not report as emptiness ------


def test_an_unreadable_store_is_not_reported_as_no_corrections(
    client, store_paths, monkeypatch
):
    """#387 inverted, and the worst way to fail it.

    A note the server DID receive, drawn in the Contributions tab as one that
    was never sent, is exactly the belief this endpoint exists to stop being
    false. The read must say the list could not be read.
    """
    post_correct(client, form={"note": "mine"})
    monkeypatch.setenv(
        "FRONTDOOR_CORRECTIONS",
        str(store_paths["tmp"] / "not-mounted" / "corrections.jsonl"),
    )
    response = client.get(
        "/correct/mine", headers={"X-Frontdoor-Contributor": CONTRIBUTOR}
    )
    assert response.status_code == 503
    assert response.get_json()["error"] == "correction not received"


def test_the_store_errors_name_the_correction_store_not_the_scan_store(
    client, store_paths, monkeypatch
):
    """The reader is the scan store's; its noun would send an operator to the
    wrong file on the volume."""
    monkeypatch.setenv(
        "FRONTDOOR_CORRECTIONS",
        str(store_paths["tmp"] / "not-mounted" / "corrections.jsonl"),
    )
    error = client.get("/map/data").get_json()["corrections_error"]
    assert error and "corrections" in error and "scans" not in error


def test_a_nameless_report_is_never_filed_against_a_nearby_named_business(
    client, store_paths
):
    """A written complaint must not land on a business the reporter never named.

    The scan merge matches by distance when a reference carries no name --
    for a photograph that is the nearest plausible pin, for a correction it is
    somebody's complaint attributed to a business they never mentioned, with
    the dispute flag and, once corroborated, a public re-look line on that
    business's pin.
    """
    response = client.post(
        "/correct",
        data={"place_id": "not-in-the-dataset", "lat": "40.0", "lng": "-75.0",
              "category": "entrance_features", "note": "the ramp is gone"},
        content_type="multipart/form-data",
        headers={"X-Frontdoor-Contributor": CONTRIBUTOR},
    )
    assert response.status_code == 201
    record = load_corrections(store_paths["corrections"])[0]
    assert record["place_key"] != "ChIJexample"
    assert _map_payload(client)["ChIJexample"].get("needs_relook") is not True


def test_a_note_about_a_different_entrance_does_not_age_this_one(
    client, store_paths
):
    for who in (CONTRIBUTOR, OTHER_CONTRIBUTOR):
        assert post_correct(
            client,
            form={"scope": "other_entrance", "note": "the side door changed"},
            contributor=who,
        ).status_code == 201
    assert _map_payload(client)["ChIJexample"].get("needs_relook") is not True
    # ...but it is still in the queue for a person to read.
    assert len(review_queue(load_corrections(store_paths["corrections"]))) == 2


def test_the_sheets_own_wording_is_accepted_as_a_scope(client, store_paths):
    post_correct(
        client, form={"scope": "A different entrance of this business"}
    )
    assert load_corrections(store_paths["corrections"])[0]["scope"] == "other_entrance"


def test_a_refresh_of_the_tab_is_queued_rather_than_dropped():
    """A send followed immediately by a refresh must not lose the new note."""
    page = create_app().test_client().get("/app").get_data(as_text=True)
    assert "function fetchMyCorrections(){" in page
    assert "correctionsFetch.then(fetchMyCorrections, fetchMyCorrections)" in page
