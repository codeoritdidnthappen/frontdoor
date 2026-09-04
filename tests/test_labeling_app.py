"""Local button-based labeling workflow for TICK-246 / #168."""

import csv
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest

from frontdoor.labels import CRITERIA_KEYS, LabelError
from frontdoor_server import labeling_app


def _fixture(tmp_path, monkeypatch, *, clock=None):
    images = tmp_path / "originals"
    sidecars = tmp_path / "sidecars"
    images.mkdir()
    sidecars.mkdir()
    payload = b"not-a-real-jpeg-but-the-labeler-serves-original-bytes"
    (images / "E-001").mkdir()
    (images / "E-001" / "one.jpg").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "capture_id,entrance_id,image_sha256,depth_sha256,sidecar_sha256,split\n"
        f"C-1,E-001,{digest},,unused,dev\n"
        f"C-2,E-002,{digest},,unused,sealed\n",
        encoding="utf-8",
    )
    (sidecars / "C-1.json").write_text(
        json.dumps({"image": {"path": "E-001/one.jpg"}}), encoding="utf-8"
    )
    (sidecars / "C-2.json").write_text(
        json.dumps({"image": {"path": "E-001/one.jpg"}}), encoding="utf-8"
    )
    monkeypatch.setattr(
        labeling_app, "load_eligible_entrances", lambda *args: frozenset({"E-001"})
    )
    labels = tmp_path / "labels.csv"
    app = labeling_app.create_labeling_app(
        manifest_path=manifest,
        sidecar_dir=sidecars,
        closeout_path=tmp_path / "closeout.json",
        image_root=images,
        labels_path=labels,
        clock=clock or (lambda: date(2026, 9, 4)),
        write_token="test-token",
    )
    return app.test_client(), labels, images / "E-001" / "one.jpg"


def test_surface_lists_only_eligible_entrances_and_no_model_output(
    tmp_path, monkeypatch
):
    client, _, _ = _fixture(tmp_path, monkeypatch)
    page = client.get("/").get_data(as_text=True)
    assert "Present" in page and "Absent" in page and "Cannot determine" in page
    assert "verdict" not in page.lower()
    assert "confidence" not in page.lower()

    body = client.get("/api/entrances").get_json()
    assert [item["entrance_id"] for item in body["entrances"]] == ["E-001"]
    assert body["entrances"][0]["photos"] == [
        {"capture_id": "C-1", "url": "/photos/C-1"}
    ]
    assert "answers = item.reviewed ? {...item.answers} : {}" in page
    assert 'setAttribute("role","radiogroup")' in page
    assert 'setAttribute("aria-checked"' in page
    assert "loadedPhotos !==" in page


def test_save_requires_token_and_complete_fixed_vocabulary(tmp_path, monkeypatch):
    client, labels, _ = _fixture(tmp_path, monkeypatch)
    before = labels.read_bytes()
    complete = {key: "present" for key in CRITERIA_KEYS}
    assert client.post("/api/entrances/E-001", json={"answers": complete}).status_code == 403
    assert client.post(
        "/api/entrances/E-001",
        json={"answers": {"handrails": "present"}},
        headers={"X-Frontdoor-Labeling-Token": "test-token"},
    ).status_code == 422
    assert labels.read_bytes() == before


def test_saved_buttons_reload_and_write_validator_compatible_csv(tmp_path, monkeypatch):
    client, labels, _ = _fixture(tmp_path, monkeypatch)
    answers = {
        "ramp_or_bevel": "present",
        "handrails": "absent",
        "accessible_door_hardware": "",
        "accessibility_signage": "present",
    }
    response = client.post(
        "/api/entrances/E-001",
        json={"answers": answers},
        headers={"X-Frontdoor-Labeling-Token": "test-token"},
    )
    assert response.status_code == 200
    assert response.get_json()["complete"] is True
    reloaded = client.get("/api/entrances").get_json()["entrances"][0]
    assert reloaded["reviewed"] is True
    assert reloaded["answers"] == answers
    with labels.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 4
    assert {row["labeled_by"] for row in rows} == {"James"}
    assert {row["labeled_at"] for row in rows} == {"2026-09-04"}


def test_photo_is_hash_verified_each_time_it_is_served(tmp_path, monkeypatch):
    client, _, photo = _fixture(tmp_path, monkeypatch)
    assert client.get("/photos/C-1").status_code == 200
    photo.write_bytes(b"substituted")
    response = client.get("/photos/C-1")
    assert response.status_code == 422
    assert "hash does not match" in response.get_json()["error"]

    response = client.post(
        "/api/entrances/E-001",
        json={"answers": {key: "present" for key in CRITERIA_KEYS}},
        headers={"X-Frontdoor-Labeling-Token": "test-token"},
    )
    assert response.status_code == 422


def test_verified_response_uses_the_bytes_that_were_hashed(tmp_path, monkeypatch):
    client, _, photo = _fixture(tmp_path, monkeypatch)
    original_send_file = labeling_app.send_file

    def swap_then_send(source, **kwargs):
        photo.write_bytes(b"substituted-after-verification")
        return original_send_file(source, **kwargs)

    monkeypatch.setattr(labeling_app, "send_file", swap_then_send)
    response = client.get("/photos/C-1")
    assert response.status_code == 200
    assert response.data == b"not-a-real-jpeg-but-the-labeler-serves-original-bytes"


def test_hostile_host_cannot_read_token_or_write_labels(tmp_path, monkeypatch):
    client, labels, _ = _fixture(tmp_path, monkeypatch)
    before = labels.read_bytes()
    assert client.get("/", headers={"Host": "attacker.example"}).status_code == 403
    response = client.post(
        "/api/entrances/E-001",
        json={"answers": {key: "present" for key in CRITERIA_KEYS}},
        headers={"Host": "127.0.0.1.evil", "X-Frontdoor-Labeling-Token": "test-token"},
    )
    assert response.status_code == 403
    assert labels.read_bytes() == before


def test_each_save_uses_the_current_date(tmp_path, monkeypatch):
    current = [date(2026, 9, 4)]
    client, labels, _ = _fixture(tmp_path, monkeypatch, clock=lambda: current[0])
    headers = {"X-Frontdoor-Labeling-Token": "test-token"}
    answers = {key: "present" for key in CRITERIA_KEYS}
    assert client.post("/api/entrances/E-001", json={"answers": answers}, headers=headers).status_code == 200
    current[0] = date(2026, 9, 5)
    assert client.post("/api/entrances/E-001", json={"answers": answers}, headers=headers).status_code == 200
    with labels.open(encoding="utf-8", newline="") as handle:
        assert {row["labeled_at"] for row in csv.DictReader(handle)} == {"2026-09-05"}


def test_threaded_requests_serialize_the_read_modify_write_transaction(
    tmp_path, monkeypatch
):
    client, _, _ = _fixture(tmp_path, monkeypatch)
    original_save = labeling_app.save_entrance_labels
    state = {"active": 0, "maximum": 0}
    state_lock = threading.Lock()

    def observed_save(*args, **kwargs):
        with state_lock:
            state["active"] += 1
            state["maximum"] = max(state["maximum"], state["active"])
        time.sleep(0.03)
        try:
            return original_save(*args, **kwargs)
        finally:
            with state_lock:
                state["active"] -= 1

    monkeypatch.setattr(labeling_app, "save_entrance_labels", observed_save)
    headers = {"X-Frontdoor-Labeling-Token": "test-token"}

    def submit(truth):
        with client.application.test_client() as thread_client:
            return thread_client.post(
                "/api/entrances/E-001",
                json={"answers": {key: truth for key in CRITERIA_KEYS}},
                headers=headers,
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(submit, ["present", "absent"])) == [200, 200]
    assert state["maximum"] == 1


def test_path_escaping_local_image_root_is_refused(tmp_path, monkeypatch):
    client, _, _ = _fixture(tmp_path, monkeypatch)
    # Rebuild with a malicious committed-looking relative path; app construction fails
    # before any file outside the selected image root can be served.
    sidecar = tmp_path / "sidecars" / "C-1.json"
    sidecar.write_text(json.dumps({"image": {"path": "../../secret.jpg"}}), encoding="utf-8")
    with pytest.raises(LabelError, match="escapes the local image root"):
        labeling_app.create_labeling_app(
            manifest_path=tmp_path / "manifest.csv",
            sidecar_dir=tmp_path / "sidecars",
            closeout_path=tmp_path / "closeout.json",
            image_root=tmp_path / "originals",
            labels_path=tmp_path / "second-labels.csv",
        )
