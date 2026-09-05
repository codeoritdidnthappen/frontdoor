"""Phone-to-server human-label contract for TICK-282 / #309."""

import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from frontdoor.labels import COLUMNS, CRITERIA_KEYS
from frontdoor_server.app import ERROR_SCHEMA, create_app

KEY = "test-upload-key"
ANSWERS = {
    "ramp_or_bevel": "present",
    "handrails": "absent",
    "accessible_door_hardware": "",
    "accessibility_signage": "present",
}


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("FRONTDOOR_UPLOAD_KEY", KEY)
    built = create_app()
    built.config.update(TESTING=True, LABELS_PATH=tmp_path / "labels.csv")
    return built


def _post(client, *, entrance_id="E-901", labeled_by="James", answers=None, key=KEY):
    headers = {"X-Frontdoor-Upload-Key": key} if key is not None else {}
    return client.post(
        "/labels",
        json={
            "entrance_id": entrance_id,
            "labeled_by": labeled_by,
            "answers": ANSWERS if answers is None else answers,
        },
        headers=headers,
    )


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_ac_8_label_submission_uses_the_existing_upload_key(app):
    with app.test_client() as client:
        assert _post(client, key=None).status_code == 401
        assert _post(client, key="wrong").status_code == 401
        assert _post(client).status_code == 201


def test_ac_8_unconfigured_server_refuses_every_key(monkeypatch, tmp_path):
    monkeypatch.delenv("FRONTDOOR_UPLOAD_KEY", raising=False)
    app = create_app()
    app.config.update(TESTING=True, LABELS_PATH=tmp_path / "labels.csv")
    with app.test_client() as client:
        assert _post(client).status_code == 401


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("entrance_id", "E-14"),
        ("entrance_id", "e-901"),
        ("labeled_by", "   "),
        ("labeled_by", "x" * 101),
        ("answers", {**ANSWERS, "extra": "present"}),
        ("answers", {"handrails": "present"}),
        ("answers", {**ANSWERS, "handrails": "not_visible"}),
    ],
)
def test_ac_8_invalid_or_oversized_submissions_change_nothing(app, change, value):
    kwargs = {change: value}
    with app.test_client() as client:
        response = _post(client, **kwargs)
    assert response.status_code == 422
    Draft202012Validator(ERROR_SCHEMA).validate(response.get_json())
    assert not Path(app.config["LABELS_PATH"]).exists()


def test_ac_8_requires_exact_json_shape_and_content_type(app):
    with app.test_client() as client:
        extra = client.post(
            "/labels",
            json={
                "entrance_id": "E-901",
                "labeled_by": "James",
                "answers": ANSWERS,
                "labeled_at": "1999-01-01",
            },
            headers={"X-Frontdoor-Upload-Key": KEY},
        )
        not_json = client.post(
            "/labels",
            data="hello",
            headers={"X-Frontdoor-Upload-Key": KEY},
        )
    assert extra.status_code == 422
    assert not_json.status_code == 415


def test_ac_9_server_stamps_four_rows_atomically_and_preserves_blank_truth(app, monkeypatch):
    class FixedDate:
        @classmethod
        def today(cls):
            return date(2026, 9, 5)

    monkeypatch.setattr("frontdoor_server.label_view.date", FixedDate)
    with app.test_client() as client:
        response = _post(client)
    assert response.status_code == 201
    rows = _rows(Path(app.config["LABELS_PATH"]))
    assert tuple(rows[0]) == COLUMNS
    assert [row["criterion"] for row in rows] == list(CRITERIA_KEYS)
    assert [row["truth"] for row in rows] == list(ANSWERS.values())
    assert {row["labeled_by"] for row in rows} == {"James"}
    assert {row["labeled_at"] for row in rows} == {"2026-09-05"}


def test_ac_10_identical_retry_is_success_and_different_retry_is_locked(app):
    path = Path(app.config["LABELS_PATH"])
    with app.test_client() as client:
        assert _post(client).status_code == 201
        original = path.read_bytes()
        repeat = _post(client)
        changed = _post(client, answers={**ANSWERS, "handrails": "present"})
    assert repeat.status_code == 200
    assert repeat.get_json()["created"] is False
    assert changed.status_code == 409
    assert path.read_bytes() == original


def test_ac_9_concurrent_submissions_cannot_lose_or_interleave_rows(app):
    entrances = [f"E-{number:03d}" for number in range(901, 921)]

    def submit(entrance_id):
        with app.test_client() as client:
            return _post(client, entrance_id=entrance_id).status_code

    with ThreadPoolExecutor(max_workers=8) as executor:
        statuses = list(executor.map(submit, entrances))

    assert statuses == [201] * len(entrances)
    rows = _rows(Path(app.config["LABELS_PATH"]))
    assert len(rows) == len(entrances) * len(CRITERIA_KEYS)
    assert {
        rows[index]["entrance_id"] for index in range(0, len(rows), 4)
    } == set(entrances)
    for index in range(0, len(rows), 4):
        assert {row["entrance_id"] for row in rows[index : index + 4]} == {
            rows[index]["entrance_id"]
        }


def test_ac_10_concurrent_identical_submissions_record_one_entrance_once(app):
    def submit():
        with app.test_client() as client:
            return _post(client).status_code

    with ThreadPoolExecutor(max_workers=8) as executor:
        statuses = list(executor.map(lambda _: submit(), range(8)))

    assert statuses.count(201) == 1
    assert statuses.count(200) == 7
    assert len(_rows(Path(app.config["LABELS_PATH"]))) == len(CRITERIA_KEYS)


def test_ac_8_persistence_failure_returns_retryable_error_without_mutating_csv(
    app, monkeypatch
):
    path = Path(app.config["LABELS_PATH"])
    path.write_text(",".join(COLUMNS) + "\n", encoding="utf-8")
    original = path.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("frontdoor_server.label_view.append_future_entrance_labels", fail)
    with app.test_client() as client:
        response = _post(client)
    assert response.status_code == 503
    assert path.read_bytes() == original


def test_ac_8_unreadable_server_sheet_is_retryable_and_unchanged(app):
    path = Path(app.config["LABELS_PATH"])
    path.write_text("wrong,header\n1,2\n", encoding="utf-8")
    original = path.read_bytes()
    with app.test_client() as client:
        response = _post(client)
    assert response.status_code == 503
    assert path.read_bytes() == original


def test_ac_8_oversized_body_is_refused_before_parsing(app):
    with app.test_client() as client:
        response = client.post(
            "/labels",
            data=b"{" + b"x" * 9000 + b"}",
            content_type="application/json",
            headers={"X-Frontdoor-Upload-Key": KEY},
        )
    assert response.status_code == 413
    Draft202012Validator(ERROR_SCHEMA).validate(response.get_json())
    assert not Path(app.config["LABELS_PATH"]).exists()


def test_ac_9_default_path_refuses_to_modify_a_git_checkout(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setenv("FRONTDOOR_UPLOAD_KEY", KEY)
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        response = _post(client)
    assert response.status_code == 503
    assert not (tmp_path / "data" / "labels.csv").exists()


def test_ac_9_explicit_runtime_path_is_honoured_in_a_git_checkout(monkeypatch, tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").mkdir()
    runtime_path = tmp_path / "runtime" / "labels.csv"
    monkeypatch.chdir(checkout)
    monkeypatch.setenv("FRONTDOOR_UPLOAD_KEY", KEY)
    monkeypatch.setenv("FRONTDOOR_LABELS_PATH", str(runtime_path))
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        response = _post(client)
    assert response.status_code == 201
    assert runtime_path.exists()
