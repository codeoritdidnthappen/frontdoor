"""POST /labels: one entrance's human presence labels, from the phone (#309).

The rules worth testing are not the plumbing. Labels are recorded once and then locked, because
ground truth that can be revised after the verdicts are known is not ground truth. The server owns
the date, because a phone's clock is settable. And blank means "cannot determine" -- a reviewed
answer, not a missing one.
"""

import csv
import threading
from datetime import date

import pytest

from frontdoor.labels import (
    APPEND_ACCEPTED,
    APPEND_IDENTICAL,
    CRITERIA_KEYS,
    COLUMNS,
    LabelError,
    LabelsLocked,
    append_entrance_labels,
)
from frontdoor_server.app import create_app
from frontdoor_server.label_view import PATH_ENV

KEY = "test-upload-key"
ANSWERS = {
    "ramp_or_bevel": "present",
    "handrails": "absent",
    "accessible_door_hardware": "present",
    "accessibility_signage": "",
}


@pytest.fixture
def labels_csv(tmp_path, monkeypatch):
    path = tmp_path / "labels.csv"
    monkeypatch.setenv(PATH_ENV, str(path))
    monkeypatch.setenv("FRONTDOOR_UPLOAD_KEY", KEY)
    return path


@pytest.fixture
def client(labels_csv):
    return create_app().test_client()


def rows_of(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def post(client, **overrides):
    body = {"entrance_id": "E-101", "labeled_by": "James", "answers": dict(ANSWERS)}
    body.update(overrides)
    return client.post("/labels", json=body, headers={"X-Frontdoor-Upload-Key": KEY})


# --- the core append ---------------------------------------------------------


def test_four_rows_are_appended_in_criterion_order(labels_csv):
    outcome = append_entrance_labels(
        labels_csv, "E-101", ANSWERS, labeled_by="James", labeled_at=date(2026, 9, 5))
    assert outcome == APPEND_ACCEPTED
    rows = rows_of(labels_csv)
    assert [row["criterion"] for row in rows] == list(CRITERIA_KEYS)
    assert list(rows[0]) == list(COLUMNS)
    assert {row["labeled_at"] for row in rows} == {"2026-09-05"}


def test_cannot_determine_is_blank_truth_with_the_operator_still_recorded(labels_csv):
    append_entrance_labels(
        labels_csv, "E-101", ANSWERS, labeled_by="James", labeled_at=date(2026, 9, 5))
    signage = [r for r in rows_of(labels_csv) if r["criterion"] == "accessibility_signage"][0]
    # Blank truth, but reviewed: an undecidable criterion must stay distinguishable from one
    # nobody looked at, which is exactly what an empty labeled_by would make it.
    assert signage["truth"] == ""
    assert signage["labeled_by"] == "James"


def test_an_identical_resend_is_a_success_and_does_not_move_the_date(labels_csv):
    append_entrance_labels(
        labels_csv, "E-101", ANSWERS, labeled_by="James", labeled_at=date(2026, 9, 5))
    outcome = append_entrance_labels(
        labels_csv, "E-101", ANSWERS, labeled_by="James", labeled_at=date(2026, 9, 6))
    assert outcome == APPEND_IDENTICAL
    rows = rows_of(labels_csv)
    assert len(rows) == 4, "a replay must not duplicate rows"
    assert {row["labeled_at"] for row in rows} == {"2026-09-05"}


def test_a_disagreeing_resend_is_locked_and_changes_nothing(labels_csv):
    append_entrance_labels(
        labels_csv, "E-101", ANSWERS, labeled_by="James", labeled_at=date(2026, 9, 5))
    before = labels_csv.read_bytes()
    with pytest.raises(LabelsLocked):
        append_entrance_labels(
            labels_csv, "E-101", {**ANSWERS, "handrails": "present"},
            labeled_by="James", labeled_at=date(2026, 9, 6))
    assert labels_csv.read_bytes() == before, "byte-for-byte unchanged"


def test_a_different_operator_is_locked_too(labels_csv):
    append_entrance_labels(
        labels_csv, "E-101", ANSWERS, labeled_by="James", labeled_at=date(2026, 9, 5))
    with pytest.raises(LabelsLocked):
        append_entrance_labels(
            labels_csv, "E-101", ANSWERS, labeled_by="Emily", labeled_at=date(2026, 9, 5))


def test_another_entrance_appends_beside_the_first(labels_csv):
    append_entrance_labels(
        labels_csv, "E-101", ANSWERS, labeled_by="James", labeled_at=date(2026, 9, 5))
    append_entrance_labels(
        labels_csv, "E-102", ANSWERS, labeled_by="James", labeled_at=date(2026, 9, 5))
    assert len(rows_of(labels_csv)) == 8


@pytest.mark.parametrize(
    "answers, reason",
    [
        ({k: "present" for k in list(CRITERIA_KEYS)[:3]}, "a missing criterion"),
        ({**ANSWERS, "door_width": "present"}, "an unknown criterion"),
        ({**ANSWERS, "handrails": "maybe"}, "an unknown truth"),
        ({**ANSWERS, "handrails": "not_visible"}, "the screening vocabulary, not the label one"),
    ],
)
def test_malformed_answers_write_nothing(labels_csv, answers, reason):
    with pytest.raises(LabelError):
        append_entrance_labels(
            labels_csv, "E-101", answers, labeled_by="James", labeled_at=date(2026, 9, 5))
    assert not labels_csv.exists(), reason


@pytest.mark.parametrize("name", ["", "   ", "x" * 65])
def test_a_bad_operator_name_writes_nothing(labels_csv, name):
    with pytest.raises(LabelError):
        append_entrance_labels(
            labels_csv, "E-101", ANSWERS, labeled_by=name, labeled_at=date(2026, 9, 5))
    assert not labels_csv.exists()


def test_concurrent_submissions_do_not_lose_or_interleave_rows(labels_csv):
    """Read-modify-write under a lock: two phones finishing at the same moment.

    Without the lock both read the same file, both write their own four rows, and one entrance's
    labels vanish -- silently, because each request succeeded.
    """
    entrances = [f"E-{n:03d}" for n in range(101, 121)]
    errors = []

    def submit(entrance_id):
        try:
            append_entrance_labels(
                labels_csv, entrance_id, ANSWERS,
                labeled_by="James", labeled_at=date(2026, 9, 5))
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            errors.append(exc)

    threads = [threading.Thread(target=submit, args=(e,)) for e in entrances]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    rows = rows_of(labels_csv)
    assert len(rows) == 4 * len(entrances)
    assert {row["entrance_id"] for row in rows} == set(entrances)


# --- the endpoint ------------------------------------------------------------


def test_the_endpoint_requires_the_upload_key(client, labels_csv):
    assert client.post("/labels", json={}).status_code == 401
    assert not labels_csv.exists()


def test_a_wrong_key_is_refused(client, labels_csv):
    response = client.post(
        "/labels", json={}, headers={"X-Frontdoor-Upload-Key": "wrong"})
    assert response.status_code == 401
    assert not labels_csv.exists()


def test_an_accepted_submission_writes_four_rows(client, labels_csv):
    response = post(client)
    assert response.status_code == 200
    assert response.get_json()["accepted"] is True
    assert response.get_json()["idempotent"] is False
    assert len(rows_of(labels_csv)) == 4


def test_the_server_assigns_the_date_not_the_phone(client, labels_csv):
    """A phone's clock is settable; a date it chose would be a claim nobody could check."""
    from datetime import datetime, timezone

    post(client, labeled_at="1999-01-01")
    today = datetime.now(timezone.utc).date().isoformat()
    assert {row["labeled_at"] for row in rows_of(labels_csv)} == {today}


def test_a_replay_is_an_idempotent_success(client, labels_csv):
    post(client)
    response = post(client)
    assert response.status_code == 200
    assert response.get_json()["idempotent"] is True
    assert len(rows_of(labels_csv)) == 4


def test_a_conflicting_submission_is_409_and_changes_nothing(client, labels_csv):
    post(client)
    before = labels_csv.read_bytes()
    response = post(client, answers={**ANSWERS, "handrails": "present"})
    assert response.status_code == 409
    assert response.get_json()["error"] == "labels already recorded"
    assert labels_csv.read_bytes() == before


def test_a_malformed_entrance_id_is_refused(client, labels_csv):
    response = post(client, entrance_id="entrance 101")
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid entrance_id"
    assert not labels_csv.exists()


@pytest.mark.parametrize(
    "body",
    [
        {"labeled_by": "James", "answers": ANSWERS},
        {"entrance_id": "E-101", "answers": ANSWERS},
        {"entrance_id": "E-101", "labeled_by": "James"},
        {"entrance_id": "E-101", "labeled_by": "James", "answers": "present"},
    ],
)
def test_a_partial_submission_writes_nothing(client, labels_csv, body):
    response = client.post(
        "/labels", json=body, headers={"X-Frontdoor-Upload-Key": KEY})
    assert response.status_code == 400
    assert not labels_csv.exists()


def test_an_oversized_body_is_refused_before_it_is_parsed(client, labels_csv):
    response = client.post(
        "/labels",
        data=b"{" + b"x" * 9000 + b"}",
        content_type="application/json",
        headers={"X-Frontdoor-Upload-Key": KEY},
    )
    assert response.status_code == 413
    assert not labels_csv.exists()


def test_the_response_carries_the_contract_the_phone_bundles(client, labels_csv):
    """So a drifted build can be noticed from the response rather than from wrong labels."""
    body = post(client).get_json()
    assert body["criteria"] == list(CRITERIA_KEYS)
    assert body["allowed_truths"] == ["present", "absent", ""]
