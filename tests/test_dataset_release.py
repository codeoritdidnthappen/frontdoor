"""Stage the labeled screening dataset for a GitHub release (TICK-015, #23)."""

import csv
import hashlib
import json
from pathlib import Path

import pytest

from frontdoor.dataset_release import (
    DatasetReleaseError,
    collect_stats,
    pack,
    render_notes,
)
from frontdoor.manifest import COLUMNS
from frontdoor.split import assign_split

REPO = Path(__file__).resolve().parents[1]


def _sidecar(capture_id, entrance_id, *, device="iPhone 17 Pro", extra=None):
    body = {
        "capture_id": capture_id,
        "entrance_id": entrance_id,
        "captured_at": "2026-09-01T12:00:00Z",
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
    if extra:
        body.update(extra)
    return body


def _write_tree(tmp_path, *, device="iPhone 17 Pro", labels=None, audit=None,
                depth_sha256=""):
    root = tmp_path / "repo"
    sidecars = root / "data" / "sidecars"
    sidecars.mkdir(parents=True)
    (root / "src" / "frontdoor").mkdir(parents=True)
    (root / "src" / "frontdoor" / "split_seed.json").write_text(
        '{"seed": "00"}\n', encoding="utf-8"
    )
    entrance_id = "E-001"
    capture_id = "E-001-1"
    path = sidecars / f"{capture_id}.json"
    path.write_text(
        json.dumps(_sidecar(capture_id, entrance_id, device=device),
                   sort_keys=True) + "\n",
        encoding="utf-8",
    )
    row = {
        "capture_id": capture_id,
        "entrance_id": entrance_id,
        "image_sha256": "ab" * 32,
        "depth_sha256": depth_sha256,
        "sidecar_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "split": assign_split(entrance_id),
    }
    manifest = root / "data" / "manifest.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerow(row)
    if labels is None:
        labels = (
            "entrance_id,criterion,truth,labeled_by,labeled_at\n"
            "E-001,ramp_or_bevel,,,\n"
        )
    (root / "data" / "labels.csv").write_text(labels, encoding="utf-8")
    if audit is not None:
        (root / "SEAL_AUDIT.log").write_text(audit, encoding="utf-8")
    (root / ".env").write_text("FRONTDOOR_IMAGES_SECRET=do-not-ship\n",
                               encoding="utf-8")
    return root, row


def test_pack_copies_git_records_and_omits_env(tmp_path):
    root, row = _write_tree(tmp_path)
    out = tmp_path / "stage"
    stats = pack(root, out)
    assert stats["capture_count"] == 1
    assert stats["entrance_count"] == 1
    assert not (out / ".env").exists()
    assert (out / "data" / "manifest.csv").is_file()
    assert (out / "data" / "labels.csv").is_file()
    assert (out / "data" / "sidecars" / "E-001-1.json").is_file()
    assert (out / "src" / "frontdoor" / "split_seed.json").is_file()
    assert not (out / "SEAL_AUDIT.log").exists()
    notes = (out / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    assert "iPhone18,1" in notes
    assert "iPhone 17 Pro" in notes
    assert "same physical phone" in notes
    assert "caliper" in notes.lower()
    assert "ADA" in notes
    assert "metric LiDAR" in notes
    assert "**not** the published release" in notes
    objects = (out / "OBJECTS.md").read_text(encoding="utf-8")
    assert f"| {row['capture_id']} |" in objects
    assert row["image_sha256"] in objects
    assert "open/" in objects or "sealed/" in objects
    assert "FRONTDOOR_IMAGES_SECRET" not in objects
    assert "do-not-ship" not in objects
    assert any("#63" in b for b in stats["publish_blockers"])
    assert any("#302" in b for b in stats["publish_blockers"])


def test_notes_name_reviewed_blanks_separately_from_untouched(tmp_path):
    labels = (
        "entrance_id,criterion,truth,labeled_by,labeled_at\n"
        "E-001,ramp_or_bevel,present,James,2026-09-06T00:00:00Z\n"
        "E-001,handrails,absent,James,2026-09-06T00:00:00Z\n"
        "E-001,accessible_door_hardware,,James,2026-09-06T00:00:00Z\n"
        "E-001,accessibility_signage,,,\n"
    )
    root, _ = _write_tree(tmp_path, labels=labels)
    notes = render_notes(collect_stats(root))
    assert "- present: 1" in notes
    assert "- absent: 1" in notes
    assert "- blank (reviewed, could not determine): 1" in notes
    assert "- blank (untouched): 1" in notes


def test_other_phone_is_refused(tmp_path):
    root, _ = _write_tree(tmp_path, device="iPhone16,1")
    with pytest.raises(DatasetReleaseError, match="unexpected device"):
        pack(root, tmp_path / "stage")


def test_sidecar_hash_mismatch_is_refused(tmp_path):
    root, _ = _write_tree(tmp_path)
    sidecar = root / "data" / "sidecars" / "E-001-1.json"
    sidecar.write_text(sidecar.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(DatasetReleaseError, match="sidecar hash"):
        pack(root, tmp_path / "stage")


def test_secret_in_a_packed_file_is_refused(tmp_path):
    root, _ = _write_tree(tmp_path)
    sidecar = root / "data" / "sidecars" / "E-001-1.json"
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["image"]["path"] = "AIzaSyAAAAAAAAAAAAAAAAAAAAAAAAAAAAA.jpg"
    sidecar.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(sidecar.read_bytes()).hexdigest()
    manifest = root / "data" / "manifest.csv"
    rows = list(csv.DictReader(manifest.read_text(encoding="utf-8").splitlines()))
    rows[0]["sidecar_sha256"] = digest
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(DatasetReleaseError, match="secrets"):
        pack(root, tmp_path / "stage")


def test_existing_out_dir_is_not_overwritten(tmp_path):
    root, _ = _write_tree(tmp_path)
    out = tmp_path / "stage"
    out.mkdir()
    with pytest.raises(DatasetReleaseError, match="already exists"):
        pack(root, out)


def test_audit_log_is_copied_when_present(tmp_path):
    root, _ = _write_tree(
        tmp_path,
        labels=(
            "entrance_id,criterion,truth,labeled_by,labeled_at\n"
            "E-001,ramp_or_bevel,present,James,2026-09-06T00:00:00Z\n"
        ),
        audit="2026-09-07T00:00:00Z sha manifest python -m frontdoor.screening_eval\n",
    )
    stats = pack(root, tmp_path / "stage")
    assert (tmp_path / "stage" / "SEAL_AUDIT.log").is_file()
    assert stats["audit_present"] is True
    assert not any("#63" in b for b in stats["publish_blockers"])


def test_committed_tree_packs_and_still_names_blockers():
    stats = collect_stats(REPO)
    assert stats["capture_count"] >= 1
    assert stats["entrance_count"] >= 1
    assert "iPhone 17 Pro" in stats["devices"] or "iPhone18,1" in stats["devices"]
    assert stats["publish_blockers"]
