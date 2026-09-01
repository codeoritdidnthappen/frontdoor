"""Tests for the append-only capture manifest (TICK-013, #21)."""

import hashlib
from pathlib import Path

import pytest

from frontdoor.manifest import (
    COLUMNS,
    ManifestError,
    append_capture,
    manifest_sha256,
    sha256_file,
)
from frontdoor.split import assign_split

HEADER = ",".join(COLUMNS) + "\n"


def _empty_manifest(tmp_path: Path) -> Path:
    path = tmp_path / "manifest.csv"
    path.write_bytes(HEADER.encode("utf-8"))
    return path


def _blob(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _append(manifest, tmp_path, capture_id="cap-1", entrance_id="E-001", **blobs):
    image = _blob(tmp_path, blobs.get("image_name", "img.bin"), blobs.get("image", b"image-bytes"))
    depth = _blob(tmp_path, blobs.get("depth_name", "depth.bin"), blobs.get("depth", b"depth-bytes"))
    sidecar = _blob(tmp_path, blobs.get("sidecar_name", "side.json"), blobs.get("sidecar", b"{}"))
    append_capture(
        manifest,
        capture_id=capture_id,
        entrance_id=entrance_id,
        image_path=image,
        depth_path=depth,
        sidecar_path=sidecar,
        split=blobs.get("split"),
    )
    return image, depth, sidecar


def test_committed_manifest_has_exact_header():
    repo = Path(__file__).resolve().parents[1]
    raw = (repo / "data" / "manifest.csv").read_bytes()
    assert raw == HEADER.encode("utf-8")


def test_column_order_is_exact(tmp_path):
    manifest = _empty_manifest(tmp_path)
    _append(manifest, tmp_path)
    assert manifest.read_text(encoding="utf-8").splitlines()[0] == ",".join(COLUMNS)


def test_hashes_match_independently_computed_digests(tmp_path):
    manifest = _empty_manifest(tmp_path)
    image, depth, sidecar = _append(manifest, tmp_path, image=b"IMG", depth=b"DEP", sidecar=b"SID")
    row = manifest.read_text(encoding="utf-8").splitlines()[1].split(",")
    assert row[0] == "cap-1"
    assert row[1] == "E-001"
    assert row[2] == hashlib.sha256(b"IMG").hexdigest()
    assert row[3] == hashlib.sha256(b"DEP").hexdigest()
    assert row[4] == hashlib.sha256(b"SID").hexdigest()
    assert row[2] == sha256_file(image)
    assert row[3] == sha256_file(depth)
    assert row[4] == sha256_file(sidecar)


def test_split_matches_assignment_tool(tmp_path):
    manifest = _empty_manifest(tmp_path)
    _append(manifest, tmp_path, entrance_id="E-014")
    row = manifest.read_text(encoding="utf-8").splitlines()[1].split(",")
    assert row[5] == assign_split("E-014") == "sealed"


def test_split_mismatch_is_an_error(tmp_path):
    manifest = _empty_manifest(tmp_path)
    with pytest.raises(ManifestError, match="split"):
        _append(manifest, tmp_path, entrance_id="E-014", split="dev")


def test_duplicate_capture_id_same_bytes_is_idempotent(tmp_path):
    manifest = _empty_manifest(tmp_path)
    _append(manifest, tmp_path)
    before = manifest.read_text(encoding="utf-8")
    digest = manifest_sha256(manifest)
    _append(manifest, tmp_path)
    assert manifest.read_text(encoding="utf-8") == before
    assert manifest_sha256(manifest) == digest


def test_duplicate_capture_id_different_bytes_fails(tmp_path):
    manifest = _empty_manifest(tmp_path)
    _append(manifest, tmp_path, image=b"one")
    with pytest.raises(ManifestError, match="capture_id"):
        _append(manifest, tmp_path, image=b"two")


def test_manifest_sha256_stable_for_unchanged_content(tmp_path):
    manifest = _empty_manifest(tmp_path)
    _append(manifest, tmp_path)
    assert manifest_sha256(manifest) == manifest_sha256(manifest)
    assert manifest_sha256(manifest) == hashlib.sha256(manifest.read_bytes()).hexdigest()
