"""Dataset closeout and evaluation eligibility (TICK-095, #69)."""

import csv
import hashlib
import json
from pathlib import Path

import pytest

from frontdoor.dataset_closeout import (
    DatasetCloseoutError,
    build_closeout,
    load_eligible_entrances,
    render_closeout,
    write_closeout,
)
from frontdoor.manifest import COLUMNS
from frontdoor.split import assign_split

REPO = Path(__file__).resolve().parents[1]
COMMITTED_MANIFEST = REPO / "data" / "manifest.csv"
COMMITTED_SIDECARS = REPO / "data" / "sidecars"
COMMITTED_CLOSEOUT = REPO / "data" / "dataset-closeout.json"


def _sidecar(capture_id, entrance_id, *, device="iPhone 17 Pro"):
    return {
        "capture_id": capture_id,
        "entrance_id": entrance_id,
        "captured_at": "2026-09-04T12:00:00Z",
        "device_model": device,
        "image": {
            "path": f"{entrance_id}/{capture_id}.jpg",
            "sha256": "0" * 64,
            "width": 10,
            "height": 10,
            "exif_orientation": 1,
        },
        "depth": None,
        "conditions": {
            "distance_m": 2.5,
            "lighting": "direct sun",
            "occlusion": "none",
        },
        "split": assign_split(entrance_id),
        "capture_mode": "imported",
    }


def _write_dataset(tmp_path, entrance_counts=(("E-001", 5), ("E-003", 4))):
    sidecars = tmp_path / "sidecars"
    sidecars.mkdir()
    rows = []
    for entrance_id, count in entrance_counts:
        for index in range(count):
            capture_id = f"{entrance_id}-{index + 1}"
            path = sidecars / f"{capture_id}.json"
            path.write_text(
                json.dumps(_sidecar(capture_id, entrance_id), sort_keys=True),
                encoding="utf-8",
            )
            rows.append({
                "capture_id": capture_id,
                "entrance_id": entrance_id,
                "image_sha256": "0" * 64,
                "depth_sha256": "",
                "sidecar_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "split": assign_split(entrance_id),
            })
    manifest = tmp_path / "manifest.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return manifest, sidecars


def _rehash_sidecar(manifest, capture_id, sidecar_path):
    rows = list(csv.DictReader(manifest.read_text(encoding="utf-8").splitlines()))
    for row in rows:
        if row["capture_id"] == capture_id:
            row["sidecar_sha256"] = hashlib.sha256(sidecar_path.read_bytes()).hexdigest()
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_build_closeout_separates_complete_and_incomplete_entrances(tmp_path):
    manifest, sidecars = _write_dataset(tmp_path)
    record = build_closeout(manifest, sidecars)

    assert record["dataset"]["entrance_count"] == 2
    assert record["dataset"]["capture_count"] == 9
    assert record["eligible"]["entrance_ids"] == ["E-001"]
    assert record["eligible"]["capture_count"] == 5
    assert record["ineligible"] == [{
        "entrance_id": "E-003",
        "split": "dev",
        "capture_count": 4,
        "reason": "fewer than 5 committed captures",
    }]


def test_write_and_load_closeout_are_deterministic(tmp_path):
    manifest, sidecars = _write_dataset(tmp_path)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    record = write_closeout(manifest, sidecars, first)
    write_closeout(manifest, sidecars, second)

    assert first.read_bytes() == second.read_bytes()
    assert first.read_text(encoding="utf-8") == render_closeout(record)
    assert load_eligible_entrances(first, manifest, sidecars) == {"E-001"}


def test_missing_condition_tag_is_rejected(tmp_path):
    manifest, sidecars = _write_dataset(tmp_path, (("E-001", 1),))
    path = sidecars / "E-001-1.json"
    sidecar = json.loads(path.read_text(encoding="utf-8"))
    del sidecar["conditions"]["occlusion"]
    path.write_text(json.dumps(sidecar, sort_keys=True), encoding="utf-8")
    _rehash_sidecar(manifest, "E-001-1", path)

    with pytest.raises(DatasetCloseoutError, match="sidecar failed validation"):
        build_closeout(manifest, sidecars)


def test_capture_from_another_device_is_rejected(tmp_path):
    manifest, sidecars = _write_dataset(tmp_path, (("E-001", 1),))
    path = sidecars / "E-001-1.json"
    sidecar = json.loads(path.read_text(encoding="utf-8"))
    sidecar["device_model"] = "someone else's phone"
    path.write_text(json.dumps(sidecar, sort_keys=True), encoding="utf-8")
    _rehash_sidecar(manifest, "E-001-1", path)

    with pytest.raises(DatasetCloseoutError, match="unexpected device"):
        build_closeout(manifest, sidecars)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("capture_mode", "screening", "only imported captures"),
        ("lighting", "shade", "only direct sun lighting"),
    ],
)
def test_frozen_capture_profile_drift_is_rejected(
    tmp_path, field, value, message
):
    manifest, sidecars = _write_dataset(tmp_path, (("E-001", 1),))
    path = sidecars / "E-001-1.json"
    sidecar = json.loads(path.read_text(encoding="utf-8"))
    if field == "lighting":
        sidecar["conditions"][field] = value
    else:
        sidecar[field] = value
    path.write_text(json.dumps(sidecar, sort_keys=True), encoding="utf-8")
    _rehash_sidecar(manifest, "E-001-1", path)

    with pytest.raises(DatasetCloseoutError, match=message):
        build_closeout(manifest, sidecars)


def test_manifest_split_disagreement_is_rejected(tmp_path):
    manifest, sidecars = _write_dataset(tmp_path, (("E-001", 1),))
    text = manifest.read_text(encoding="utf-8").replace(",dev\n", ",sealed\n")
    manifest.write_text(text, encoding="utf-8")

    with pytest.raises(DatasetCloseoutError, match="committed seed assigns"):
        build_closeout(manifest, sidecars)


def test_sidecar_entrance_disagreement_is_rejected(tmp_path):
    manifest, sidecars = _write_dataset(tmp_path, (("E-001", 1),))
    path = sidecars / "E-001-1.json"
    sidecar = json.loads(path.read_text(encoding="utf-8"))
    sidecar["entrance_id"] = "E-003"
    sidecar["split"] = assign_split("E-003")
    path.write_text(json.dumps(sidecar, sort_keys=True), encoding="utf-8")
    _rehash_sidecar(manifest, "E-001-1", path)

    with pytest.raises(DatasetCloseoutError, match="sidecar names entrance"):
        build_closeout(manifest, sidecars)


def test_stale_manifest_hash_fails_before_full_regeneration(tmp_path):
    manifest, sidecars = _write_dataset(tmp_path)
    closeout = tmp_path / "closeout.json"
    write_closeout(manifest, sidecars, closeout)
    manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(DatasetCloseoutError, match="manifest hash does not match"):
        load_eligible_entrances(closeout, manifest, sidecars)


def test_committed_closeout_is_current_and_records_the_actual_corpus():
    expected = build_closeout(COMMITTED_MANIFEST, COMMITTED_SIDECARS)
    assert COMMITTED_CLOSEOUT.read_text(encoding="utf-8") == render_closeout(expected)

    assert expected["dataset"] == {
        "entrance_count": 64,
        "capture_count": 338,
        "entrances_by_split": {"dev": 33, "calib": 13, "sealed": 18},
        "entrance_split_proportions": {
            "dev": 33 / 64, "calib": 13 / 64, "sealed": 18 / 64,
        },
        "captures_by_split": {"dev": 171, "calib": 74, "sealed": 93},
        "capture_split_proportions": {
            "dev": 171 / 338, "calib": 74 / 338, "sealed": 93 / 338,
        },
    }
    assert expected["eligible"]["entrance_count"] == 53
    assert expected["eligible"]["capture_count"] == 300
    assert expected["eligible"]["entrances_by_split"] == {
        "dev": 28, "calib": 12, "sealed": 13,
    }
    assert expected["eligible"]["entrance_split_proportions"] == {
        "dev": 28 / 53, "calib": 12 / 53, "sealed": 13 / 53,
    }
    assert expected["eligible"]["captures_by_split"] == {
        "dev": 154, "calib": 70, "sealed": 76,
    }
    assert expected["eligible"]["capture_split_proportions"] == {
        "dev": 154 / 300, "calib": 70 / 300, "sealed": 76 / 300,
    }
    assert [
        (item["entrance_id"], item["capture_count"])
        for item in expected["ineligible"]
    ] == [
        ("E-009", 3), ("E-012", 4), ("E-013", 3), ("E-014", 1),
        ("E-015", 4), ("E-019", 4), ("E-021", 4), ("E-023", 3),
        ("E-028", 4), ("E-044", 4), ("E-062", 4),
    ]
    assert expected["capture_profile"] == {
        "physical_device": "James's iPhone 17 Pro",
        "normalized_device_model": "iPhone18,1",
        "recorded_device_aliases": ["iPhone 17 Pro"],
        "capture_modes": ["imported"],
        "recorded_lighting": ["direct sun"],
    }


def test_a_crlf_sidecar_mismatch_names_line_endings_as_the_cause(tmp_path):
    # TICK-323: .gitattributes pins sidecars to LF, but a working tree checked
    # out before that attribute keeps CRLF, and the bytes then hash differently
    # from the manifest. The content is identical, so the error has to say so
    # instead of reading like corruption.
    from frontdoor.dataset_closeout import _line_ending_hint

    body = b'{\r\n "capture_id": "E-001-3217"\r\n}\r\n'
    path = tmp_path / "E-001-3217.json"
    path.write_bytes(body)
    lf_sha = hashlib.sha256(body.replace(b"\r\n", b"\n")).hexdigest()

    hint = _line_ending_hint(path, lf_sha)
    assert "CRLF" in hint
    assert "git checkout --" in hint


def test_no_line_ending_hint_when_the_content_really_differs(tmp_path):
    # A genuinely different sidecar must not be excused as a line-ending
    # problem, whether or not it happens to hold CRLF.
    from frontdoor.dataset_closeout import _line_ending_hint

    path = tmp_path / "E-001-3217.json"
    path.write_bytes(b'{\r\n "capture_id": "E-001-9999"\r\n}\r\n')
    assert _line_ending_hint(path, "0" * 64) == ""

    lf_only = tmp_path / "E-001-3218.json"
    lf_only.write_bytes(b'{\n "capture_id": "E-001-3218"\n}\n')
    assert _line_ending_hint(lf_only, "0" * 64) == ""
