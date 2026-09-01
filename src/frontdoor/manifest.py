"""Append-only capture manifest (TICK-013, D-017, D-018).

data/manifest.csv is the committed record of what was captured. One row per
capture, written at capture time, never edited. Hashes are SHA-256 of file
bytes; split must match assign_split for the entrance.
"""

import csv
import hashlib
from pathlib import Path

from frontdoor.split import assign_split

COLUMNS = (
    "capture_id",
    "entrance_id",
    "image_sha256",
    "depth_sha256",
    "sidecar_sha256",
    "split",
)


class ManifestError(ValueError):
    """Raised when an append would rewrite history or disagree with the seed."""


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_sha256(path):
    """SHA-256 of the manifest file bytes. Stable for unchanged content."""
    return sha256_file(path)


def _row(capture_id, entrance_id, image_sha256, depth_sha256, sidecar_sha256, split):
    return {
        "capture_id": capture_id,
        "entrance_id": entrance_id,
        "image_sha256": image_sha256,
        "depth_sha256": depth_sha256,
        "sidecar_sha256": sidecar_sha256,
        "split": split,
    }


def _require_newline_terminated(path):
    """Refuse to append to a manifest whose last line was never finished.

    open(path, "a") writes from wherever the file ends, so appending to an
    unterminated last line concatenates two capture records into one. csv then
    parses the merged line as a single row with extra fields rather than
    failing, so the corruption is silent - in the one file D-017 relies on to
    prove the seal. A truncated last line means an earlier write was
    interrupted, so this raises rather than repairing: the operator needs to
    know.
    """
    if path.stat().st_size and path.read_bytes()[-1:] != b"\n":
        raise ManifestError(
            f"{path} does not end with a newline; a previous append was "
            "interrupted. Refusing to append onto a partial row."
        )


def _read_rows(path):
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(COLUMNS):
            raise ManifestError(
                f"manifest columns {reader.fieldnames!r} do not match {list(COLUMNS)!r}"
            )
        return list(reader)


def read_manifest(path):
    """Return every row. The loader is the doorway that then verifies hashes."""
    return _read_rows(Path(path))


def append_capture(
    manifest_path,
    *,
    capture_id,
    entrance_id,
    image_path,
    depth_path,
    sidecar_path,
    split=None,
):
    """Append one capture to the manifest, or no-op if the same row already exists."""
    manifest_path = Path(manifest_path)
    expected_split = assign_split(entrance_id)
    if split is not None and split != expected_split:
        raise ManifestError(
            f"split {split!r} does not match assign_split({entrance_id!r})={expected_split!r}"
        )
    new_row = _row(
        capture_id,
        entrance_id,
        sha256_file(image_path),
        sha256_file(depth_path),
        sha256_file(sidecar_path),
        expected_split,
    )
    _require_newline_terminated(manifest_path)
    existing = _read_rows(manifest_path)
    for row in existing:
        if row["capture_id"] != capture_id:
            continue
        if row == new_row:
            return
        raise ManifestError(
            f"capture_id {capture_id!r} already recorded with a different row; "
            "the manifest is append-only"
        )
    with open(manifest_path, "a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writerow(new_row)
