"""POST /screen/publish and GET /scan/photo/<key> (TICK-262, #270).

Fully mocked like test_screen_endpoint: the engine is injected via
app.config[ENGINE_KEY], object storage via app.config[STORE_KEY], and the scan
store is a tmp_path JSONL — no API key, no bucket, no network.

The two claims that matter most are pinned hard:
  * only PROCESSED bytes are ever stored, and only when the face audit
    answered exactly "clear" — face_visible and unknown persist NOTHING;
  * the assess-only POST /screen keeps its zero-persistence guarantee
    untouched (its own test file pins that; here we pin that publishing lives
    in a different module entirely).
"""

import io
import json

import pytest

from frontdoor.scan_records import is_scan_image_key, load_scan_records
from frontdoor.screening import CRITERIA_KEYS, ImageAssessment
from frontdoor.storage import StorageError
from frontdoor_server.app import create_app
from frontdoor_server.scan_view import STORE_KEY
from frontdoor_server.screen_view import ENGINE_KEY
from tests.test_screen_endpoint import (
    FakeEngine,
    image_part,
    ok_assessment,
    real_jpeg,
)

PLACE_FORM = {"place_id": "ChIJexample", "name": "Example Cafe",
              "lat": "40.0", "lng": "-75.0"}


class FakeStore:
    """Stands in for ObjectStore as scan_view uses it: .put and .get."""

    def __init__(self, objects=None, put_raises=None, get_raises=None):
        self.objects = dict(objects or {})
        self.puts = []
        self.get_calls = []
        self._put_raises = put_raises
        self._get_raises = get_raises

    def put(self, key, body, *, if_absent=False):
        if self._put_raises is not None:
            raise self._put_raises
        self.puts.append((key, body, if_absent))
        self.objects[key] = body

    def get(self, key, *, allow_sealed=False):
        self.get_calls.append(key)
        if self._get_raises is not None:
            raise self._get_raises
        if key not in self.objects:
            raise StorageError(f"get s3://bucket/{key} failed (NoSuchKey)")
        return self.objects[key]


@pytest.fixture
def scans_path(tmp_path, monkeypatch):
    path = tmp_path / "scans.jsonl"
    monkeypatch.setenv("FRONTDOOR_SCANS", str(path))
    return path


def make_client(engine=None, store=None):
    app = create_app()
    app.config[ENGINE_KEY] = engine if engine is not None else FakeEngine()
    if store is not None:
        app.config[STORE_KEY] = store
    return app.test_client()


def post_publish(client, parts, form=PLACE_FORM, headers=None):
    data = {"images": parts}
    data.update(form)
    return client.post("/screen/publish", data=data, headers=headers or {},
                       content_type="multipart/form-data")


# --- publishing persists processed bytes only --------------------------------


def test_publish_stores_the_processed_bytes_not_the_raw_upload(
        scans_path, monkeypatch):
    from frontdoor.faceblur import ProcessedImage

    monkeypatch.setattr(
        "frontdoor_server.scan_view.process_upload",
        lambda raw: ProcessedImage(b"blurred:" + raw, face_count=1,
                                   gps_stripped=True),
    )
    store = FakeStore()
    client = make_client(store=store)
    parts = [image_part(f"v{i}.jpg", data=f"raw{i}".encode()) for i in range(2)]

    body = post_publish(client, parts).get_json()

    assert body["published"] is True
    assert body["quarantined"] is False
    assert body["quarantined_count"] == 0
    assert body["faces_blurred"] == 2
    assert len(body["image_keys"]) == 2
    for key in body["image_keys"]:
        assert is_scan_image_key(key)
        assert key.startswith("scans/ChIJexample/")
    # The store received the PROCESSED bytes under the open/ partition twins
    # of the public keys, conditionally, and never the raw upload.
    assert [key for key, _, _ in store.puts] == [
        "open/" + key for key in body["image_keys"]]
    assert [bytes_ for _, bytes_, _ in store.puts] == [b"blurred:raw0",
                                                       b"blurred:raw1"]
    assert all(if_absent for _, _, if_absent in store.puts)


def test_publish_of_a_real_image_stores_reencoded_jpeg_bytes(scans_path):
    raw = real_jpeg()
    store = FakeStore()
    body = post_publish(make_client(store=store), [image_part(data=raw)]).get_json()
    assert body["published"] is True
    ((_, stored, _),) = store.puts
    assert stored[:2] == b"\xff\xd8"
    assert stored != raw  # processed (re-encoded, EXIF-free), never the upload


def test_publish_appends_one_scan_record_the_map_can_read(
        scans_path, monkeypatch):
    # The detector is injected here for the same reason the first test injects
    # it: recall-tuned face detection on a synthetic featureless frame is
    # OpenCV-build-dependent (some builds emit spurious boxes on it - see the
    # PR #243 note in faceblur.py), and this test is about the RECORD, not the
    # detector. tests/test_faceblur.py owns detector behavior.
    from frontdoor.faceblur import ProcessedImage

    monkeypatch.setattr(
        "frontdoor_server.scan_view.process_upload",
        lambda raw: ProcessedImage(b"processed:" + raw, face_count=0,
                                   gps_stripped=True),
    )
    store = FakeStore()
    client = make_client(store=store)
    body = post_publish(
        client, [image_part()], headers={"X-Frontdoor-Contributor": "tok_1"}
    ).get_json()

    (record,) = load_scan_records(scans_path)
    assert record["scan_id"] == body["scan_id"]
    assert record["place_ref"] == {"place_id": "ChIJexample",
                                   "name": "Example Cafe",
                                   "lat": 40.0, "lng": -75.0}
    assert record["created_at"] == body["created_at"]
    assert record["verdicts"] == {key: "present" for key in CRITERIA_KEYS}
    assert record["confidences"] == {key: 80 for key in CRITERIA_KEYS}
    assert record["faces_blurred"] == body["faces_blurred"] == 0
    assert record["quarantined_count"] == 0
    assert record["image_keys"] == body["image_keys"]
    assert record["contributor"] == "tok_1"
    assert scans_path.read_bytes().endswith(b"\n")


def test_a_junk_contributor_header_is_dropped_not_stored(scans_path):
    client = make_client(store=FakeStore())
    post_publish(client, [image_part()],
                 headers={"X-Frontdoor-Contributor": "no spaces or ; commas!"})
    (record,) = load_scan_records(scans_path)
    assert record["contributor"] is None


def test_publish_response_carries_the_same_assessment_contract_as_screen(
        scans_path):
    body = post_publish(make_client(store=FakeStore()), [image_part()]).get_json()
    assert body["mode"] == "integrated"
    assert body["status"] == "ai_estimated"
    assert body["face_check"] == "clear"
    for key in CRITERIA_KEYS:
        assert body["assessment"]["criteria"][key]["verdict"] == "present"
    wording = body["wording"].lower()
    assert "not measurements" in wording and "not compliance" in wording


# --- quarantined frames are NEVER persisted ----------------------------------


@pytest.mark.parametrize("assessment,expected_face_check", [
    (ok_assessment("present", face_check="face_visible"), "face_visible"),
    # Built without the field: the audit never produced an answer. "unknown"
    # fails closed exactly like a visible face.
    (ImageAssessment(
        criteria={key: {"verdict": "present", "confidence": 80, "evidence": ""}
                  for key in CRITERIA_KEYS},
        latency_s=1.0,
    ), "unknown"),
])
def test_quarantined_frames_are_never_persisted(
        scans_path, assessment, expected_face_check):
    store = FakeStore()
    client = make_client(engine=FakeEngine(assessment=assessment), store=store)
    parts = [image_part(f"v{i}.jpg", data=real_jpeg(80 + i)) for i in range(3)]

    response = post_publish(client, parts)

    assert response.status_code == 200
    body = response.get_json()
    # Assessed...
    for key in CRITERIA_KEYS:
        assert body["assessment"]["criteria"][key]["verdict"] == "present"
    # ...but not published, honestly.
    assert body["published"] is False
    assert body["publish_reason"] == "face_check"
    assert expected_face_check in body["publish_detail"]
    assert body["face_check"] == expected_face_check
    assert body["quarantined"] is True
    assert body["quarantine_reason"] == "face_check"
    assert body["quarantined_count"] == 3
    assert body["image_keys"] == []
    # NOTHING was persisted: no object, no record.
    assert store.puts == []
    assert not scans_path.exists()


# --- storage failure: assessed-but-not-published, never silent ---------------


def test_a_storage_write_failure_is_503_with_the_verdicts_still_in_the_body(
        scans_path):
    store = FakeStore(put_raises=StorageError("put s3://bucket/k failed (500)"))
    response = post_publish(make_client(store=store), [image_part()])
    assert response.status_code == 503
    body = response.get_json()
    assert body["published"] is False
    assert body["publish_reason"] == "storage_unavailable"
    assert body["error"] == "scan not published"
    assert body["detail"]
    # The verdicts still stand in the same response.
    for key in CRITERIA_KEYS:
        assert body["assessment"]["criteria"][key]["verdict"] == "present"
    assert not scans_path.exists()


def test_missing_storage_credentials_are_a_named_503_not_a_500(
        scans_path, monkeypatch):
    for name in ("FRONTDOOR_IMAGES_BUCKET", "FRONTDOOR_IMAGES_ACCESS_KEY",
                 "FRONTDOOR_IMAGES_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    response = post_publish(make_client(), [image_part()])  # no injected store
    assert response.status_code == 503
    body = response.get_json()
    assert body["publish_reason"] == "storage_unavailable"
    assert body["assessment"]["criteria"]
    assert not scans_path.exists()


def test_a_record_store_failure_is_503_and_publishes_nothing_to_the_map(
        tmp_path, monkeypatch):
    # Point the scan store somewhere unwritable: a path UNDER an existing file.
    blocker = tmp_path / "blocker"
    blocker.write_text("file, not a directory", encoding="utf-8")
    monkeypatch.setenv("FRONTDOOR_SCANS", str(blocker / "scans.jsonl"))
    store = FakeStore()
    response = post_publish(make_client(store=store), [image_part()])
    assert response.status_code == 503
    body = response.get_json()
    assert body["published"] is False
    assert body["publish_reason"] == "record_store_unavailable"
    assert body["assessment"]["criteria"]
    # The response does not claim keys it did not record.
    assert body["image_keys"] == []


def test_no_credential_material_appears_in_a_publish_response(
        scans_path, monkeypatch):
    monkeypatch.setenv("FRONTDOOR_IMAGES_ACCESS_KEY", "AKIASECRETID")
    monkeypatch.setenv("FRONTDOOR_IMAGES_SECRET_KEY", "s3cret-value")
    response = post_publish(make_client(store=FakeStore()), [image_part()])
    text = response.get_data(as_text=True)
    assert "AKIASECRETID" not in text
    assert "s3cret-value" not in text


# --- request validation ------------------------------------------------------


def test_publish_without_a_place_reference_is_refused_before_the_engine(
        scans_path):
    engine = FakeEngine()
    client = make_client(engine=engine, store=FakeStore())
    response = post_publish(client, [image_part()], form={})
    assert response.status_code == 400
    assert response.get_json()["error"] == "missing place reference"
    assert engine.calls == []


def test_coordinates_without_a_name_are_not_a_place_reference(scans_path):
    response = post_publish(make_client(store=FakeStore()), [image_part()],
                            form={"lat": "40.0", "lng": "-75.0"})
    assert response.status_code == 400
    assert response.get_json()["error"] == "missing place reference"


@pytest.mark.parametrize("form,token", [
    ({"place_id": "x" * 200}, "invalid place_id"),
    ({"place_id": "ChIJ x/y"}, "invalid place_id"),
    ({"name": "Spot", "lat": "91", "lng": "0"}, "invalid location"),
    ({"name": "Spot", "lat": "40.0", "lng": "not-a-number"}, "invalid location"),
    ({"name": "Spot", "lat": "40.0"}, "invalid location"),
])
def test_bad_place_fields_are_400(scans_path, form, token):
    response = post_publish(make_client(store=FakeStore()), [image_part()],
                            form=form)
    assert response.status_code == 400
    assert response.get_json()["error"] == token


def test_lat_lng_plus_name_is_a_sufficient_place_reference(scans_path):
    body = post_publish(
        make_client(store=FakeStore()), [image_part()],
        form={"name": "Example Cafe", "lat": "40.0", "lng": "-75.0"},
    ).get_json()
    assert body["published"] is True
    assert body["place_ref"] == {"name": "Example Cafe",
                                 "lat": 40.0, "lng": -75.0}


def test_no_image_and_too_many_images_are_400(scans_path):
    client = make_client(store=FakeStore())
    assert post_publish(client, []).status_code == 400
    parts = [image_part(f"v{i}.jpg") for i in range(7)]
    response = post_publish(client, parts)
    assert response.status_code == 400
    assert response.get_json()["error"] == "too many images"


def test_a_sealed_entrance_is_refused_before_any_engine_call(scans_path):
    engine = FakeEngine()
    client = make_client(engine=engine, store=FakeStore())
    form = dict(PLACE_FORM, entrance_id="E-014")  # sealed under the seed
    response = post_publish(client, [image_part()], form=form)
    assert response.status_code == 403
    assert engine.calls == []


def test_keyless_publish_is_503_screening_unavailable(scans_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    app = create_app()  # no injected engine
    app.config[STORE_KEY] = FakeStore()
    response = post_publish(app.test_client(), [image_part()])
    assert response.status_code == 503
    assert response.get_json()["error"] == "screening unavailable"


def test_undecodable_bytes_are_422_and_nothing_is_stored(scans_path):
    store = FakeStore()
    response = post_publish(
        make_client(store=store),
        [image_part("a.png", "image/png", b"not-an-image")],
    )
    assert response.status_code == 422
    assert store.puts == []
    assert not scans_path.exists()


# --- the receipt photo: GET /scan/photo/<key> --------------------------------

GOOD_KEY = "scans/ChIJexample/" + "a" * 32 + ".jpg"


def test_the_receipt_photo_streams_the_stored_processed_bytes():
    store = FakeStore(objects={"open/" + GOOD_KEY: b"\xff\xd8processed"})
    response = make_client(store=store).get(f"/scan/photo/{GOOD_KEY}")
    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    assert response.get_data() == b"\xff\xd8processed"
    assert "immutable" in response.headers["Cache-Control"]


@pytest.mark.parametrize("key", [
    "open/cap-1",                            # a capture key
    "sealed/cap-1",                          # sealed material
    "scans/../open/cap-1.jpg",               # traversal
    "scans/a/b/" + "a" * 32 + ".jpg",        # extra segment
    "scans/pl.ce/" + "a" * 32 + ".jpg",      # dots in the slug
    "scans/place/" + "a" * 32 + ".png",      # wrong extension
    "scans/place/notahex.jpg",
    "..%2F..%2Fsealed%2Fcap-1",              # encoded traversal
    "scans/place/" + "a" * 32 + ".jpg/extra",
])
def test_only_keys_under_the_scans_prefix_resolve_and_storage_is_never_asked(key):
    store = FakeStore(objects={"open/cap-1": b"capture", "sealed/cap-1": b"sealed"})
    response = make_client(store=store).get(f"/scan/photo/{key}")
    assert response.status_code == 404
    assert store.get_calls == []


def test_a_missing_photo_is_404(scans_path):
    store = FakeStore()
    response = make_client(store=store).get(f"/scan/photo/{GOOD_KEY}")
    assert response.status_code == 404
    assert response.get_json()["error"] == "no such scan photo"


def test_a_storage_outage_on_the_photo_path_is_503():
    store = FakeStore(get_raises=StorageError("get failed (SlowDown)"))
    response = make_client(store=store).get(f"/scan/photo/{GOOD_KEY}")
    assert response.status_code == 503
    assert response.get_json()["error"] == "scan photos unavailable"


# --- /map/data merges published scans ----------------------------------------


def _dataset(tmp_path, monkeypatch):
    dataset = {
        "ChIJexample": {
            "place_id": "ChIJexample",
            "name": "Example Cafe",
            "location": {"lat": 40.0, "lng": -75.0},
            "source": "streetview",
            "status": "ai_estimated",
            "imagery_date": "2024-06",
            "criteria": {"ramp_or_bevel": {"verdict": "not_visible",
                                           "confidence": 0.5}},
        }
    }
    path = tmp_path / "precatalogue.json"
    path.write_text(json.dumps(dataset), encoding="utf-8")
    monkeypatch.setenv("FRONTDOOR_MAP_DATASET", str(path))
    return dataset


def test_a_published_scan_upgrades_its_pin_on_map_data(
        tmp_path, monkeypatch, scans_path):
    _dataset(tmp_path, monkeypatch)
    client = make_client(store=FakeStore())
    publish = post_publish(client, [image_part()]).get_json()
    assert publish["published"] is True

    payload = client.get("/map/data").get_json()
    (pin,) = payload["pins"]
    assert pin["place_id"] == "ChIJexample"
    # Scanned tier: the merged row passed the same Green-or-Gray gate.
    assert pin["state"] == "verified_accessible"
    assert pin["ai_estimated"] is False
    # Freshness from the newest scan.
    assert pin["imagery_date"] == publish["created_at"][:10]
    assert pin["last_scanned"] == publish["created_at"][:10]
    # The provenance receipt row leads.
    line = pin["provenance"][0]
    assert line["source"] == "community_scan"
    assert line["label"] == f"Scanned on-site — {publish['created_at'][:10]}"
    # The scan's criteria raised the checklist.
    checklist = {item["key"]: item for item in pin["checklist"]}
    assert checklist["ramp_or_bevel"]["observation"] == "visible"
    assert checklist["ramp_or_bevel"]["confidence"] == 0.8


def test_the_receipt_photo_round_trip_from_map_record_to_bytes(
        tmp_path, monkeypatch, scans_path):
    _dataset(tmp_path, monkeypatch)
    store = FakeStore()
    client = make_client(store=store)
    publish = post_publish(client, [image_part()]).get_json()
    (record,) = load_scan_records(scans_path)
    (key,) = record["image_keys"]
    assert key == publish["image_keys"][0]
    response = client.get(f"/scan/photo/{key}")
    assert response.status_code == 200
    assert response.get_data() == store.objects["open/" + key]


def test_map_data_is_unchanged_when_no_scan_store_exists(
        tmp_path, monkeypatch, scans_path):
    _dataset(tmp_path, monkeypatch)
    client = make_client()
    payload = client.get("/map/data").get_json()
    (pin,) = payload["pins"]
    assert pin["state"] == "not_yet_checked"
    assert pin["ai_estimated"] is True
    assert "last_scanned" not in pin
    assert payload["dataset_error"] is None


def test_a_scan_for_an_uncatalogued_place_adds_its_own_pin(
        tmp_path, monkeypatch, scans_path):
    _dataset(tmp_path, monkeypatch)
    client = make_client(store=FakeStore())
    post_publish(client, [image_part()],
                 form={"name": "Brand New Bakery", "lat": "41.0", "lng": "-76.0"})
    payload = client.get("/map/data").get_json()
    pins = {pin["name"]: pin for pin in payload["pins"]}
    assert pins["Example Cafe"]["state"] == "not_yet_checked"  # untouched
    new_pin = pins["Brand New Bakery"]
    assert new_pin["state"] == "verified_accessible"
    assert new_pin["location"] == {"lat": 41.0, "lng": -76.0}
    assert new_pin["provenance"][0]["source"] == "community_scan"


def test_a_quarantined_publish_changes_the_map_not_at_all(
        tmp_path, monkeypatch, scans_path):
    _dataset(tmp_path, monkeypatch)
    engine = FakeEngine(assessment=ok_assessment(face_check="face_visible"))
    client = make_client(engine=engine, store=FakeStore())
    post_publish(client, [image_part()])
    payload = client.get("/map/data").get_json()
    (pin,) = payload["pins"]
    assert pin["state"] == "not_yet_checked"
    assert "last_scanned" not in pin


# --- the assess-only path stays persistence-free -----------------------------


def test_screen_view_still_has_no_persistence_facility():
    """Publishing lives in scan_view; the assess-only module must stay exactly
    as pinned by test_screen_endpoint. This is a cheap tripwire for the same
    guarantee from this side: scan_view must not be imported by screen_view."""
    import inspect

    from frontdoor_server import screen_view

    source = inspect.getsource(screen_view)
    assert "scan_view" not in source
    assert "scan_records" not in source
    assert "publish" not in source


def test_posting_to_screen_writes_no_scan_record(scans_path):
    client = make_client(store=FakeStore())
    response = client.post(
        "/screen", data={"images": [image_part()]},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert not scans_path.exists()
