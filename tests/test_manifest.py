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
    """The committed manifest's FIRST LINE is the header, byte for byte.

    This asserted the whole file equalled the header, which quietly also asserted the manifest
    was empty. That held only while the dataset had no captures, so ingesting the first real ones
    (TICK-092, 48 rows) turned a green suite red on main and took every open PR with it -- for a
    change that was correct and that this test was never about.

    The invariant worth keeping is the header itself: `frontdoor.manifest` appends positionally,
    so a renamed or reordered column silently rewrites what every existing row MEANS. The row
    count is not an invariant; it is the point of the file.
    """
    repo = Path(__file__).resolve().parents[1]
    raw = (repo / "data" / "manifest.csv").read_bytes()
    assert raw.split(b"\n", 1)[0] == HEADER.encode("utf-8").rstrip(b"\n")


def test_the_committed_manifest_is_readable_as_rows():
    """What the old assertion was really standing in for: the file is well formed.

    An empty file trivially satisfied "starts with the header". Now that rows exist, check they
    parse and carry the columns the loader indexes by, so a truncated or half-written manifest
    fails here rather than in the middle of an evaluation run.
    """
    import csv

    repo = Path(__file__).resolve().parents[1]
    with (repo / "data" / "manifest.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        assert set(row) == set(COLUMNS), f"row has columns {sorted(row)}"
        # DictReader keys off the HEADER, so a short row still has every key -- with None for
        # the fields it never supplied, and extras collected under the None key. Checking the
        # keys alone therefore catches nothing; the values are where a truncated row shows.
        assert None not in row, f"row has more fields than the header: {row.get(None)}"
        assert all(v is not None for v in row.values()), f"row is short: {row}"
        assert row["capture_id"], "a row with no capture_id cannot be resolved to bytes"
        assert row["entrance_id"], "a row with no entrance_id cannot be split-checked"


def test_column_order_is_exact(tmp_path):
    manifest = _empty_manifest(tmp_path)
    _append(manifest, tmp_path)
    assert manifest.read_text(encoding="utf-8").splitlines()[0] == ",".join(COLUMNS)


def test_append_with_no_depth_writes_empty_depth_sha256(tmp_path):
    """TICK-023 AC5: a capture with no depth file is still recorded."""
    manifest = _empty_manifest(tmp_path)
    image = _blob(tmp_path, "img.bin", b"IMG")
    sidecar = _blob(tmp_path, "side.json", b"{}")
    append_capture(
        manifest,
        capture_id="cap-1",
        entrance_id="E-001",
        image_path=image,
        depth_path=None,
        sidecar_path=sidecar,
    )
    row = manifest.read_text(encoding="utf-8").splitlines()[1].split(",")
    assert row[2] == hashlib.sha256(b"IMG").hexdigest()
    assert row[3] == ""
    assert row[4] == hashlib.sha256(b"{}").hexdigest()


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


def test_append_refuses_a_manifest_with_an_unterminated_last_line(tmp_path):
    """Appending onto a partial row merges two capture records silently (TICK-230, #130)."""
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        ",".join(COLUMNS) + "\n" + f"c1,E-001,{'0' * 64},{'1' * 64},{'2' * 64},dev",
        encoding="utf-8",
    )
    for name in ("img", "dep", "car"):
        (tmp_path / name).write_bytes(name.encode())

    with pytest.raises(ManifestError, match="does not end with a newline"):
        append_capture(
            manifest,
            capture_id="c2",
            entrance_id="E-002",
            image_path=tmp_path / "img",
            depth_path=tmp_path / "dep",
            sidecar_path=tmp_path / "car",
        )
    assert len(manifest.read_text().rstrip("\n").split("\n")) == 2
