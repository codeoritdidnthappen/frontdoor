"""The committed manifest and the committed sidecars must agree (TICK-014, D-018).

`DatasetLoader` refuses a capture whose sidecar does not hash to what the manifest recorded --
bytes in, hashes checked, or nothing out. That check only runs when something loads a capture,
and the only test that did was `test_live_load_one_capture_from_the_image_bucket`, skipped unless
FRONTDOOR_STORAGE_LIVE is set. So CI never verified the two committed halves against each other.

The first real ingest (TICK-092, 48 captures) landed with every `sidecar_sha256` disagreeing with
its committed sidecar file, and the suite stayed green. Nothing could load a single row of the
dataset and no test said so.

These need no bucket and no credentials: both halves are in the repo.
"""

import csv
import hashlib
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "data" / "manifest.csv"
SIDECARS = REPO / "data" / "sidecars"


def _rows():
    with MANIFEST.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _sidecar_path(capture_id):
    return SIDECARS / f"{capture_id}.json"


@pytest.fixture(scope="module")
def rows():
    found = _rows()
    if not found:
        pytest.skip("the committed manifest has no captures yet; nothing to cross-check")
    return found


def test_every_manifest_row_has_a_committed_sidecar(rows):
    missing = [r["capture_id"] for r in rows if not _sidecar_path(r["capture_id"]).exists()]
    assert not missing, f"manifest rows with no sidecar in data/sidecars: {missing[:5]}"


def test_every_sidecar_hashes_to_what_the_manifest_recorded(rows):
    """The check `DatasetLoader` makes at load time, made once over the whole committed dataset.

    A mismatch is not cosmetic: the loader refuses the capture outright, so a dataset in this
    state cannot be evaluated at all. Recomputing the manifest's digests would silence this
    without finding out which step wrote bytes different from the ones it hashed --
    `manifest.append_capture` hashes the sidecar file on disk, so a row it wrote agrees by
    construction.
    """
    bad = []
    for row in rows:
        path = _sidecar_path(row["capture_id"])
        if not path.exists():
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != row["sidecar_sha256"]:
            bad.append((row["capture_id"], row["sidecar_sha256"][:12], actual[:12]))

    assert not bad, (
        f"{len(bad)} of {len(rows)} committed sidecars do not hash to the manifest's "
        f"sidecar_sha256, so DatasetLoader refuses them: "
        + ", ".join(f"{c} recorded {r}... actual {a}..." for c, r, a in bad[:3])
    )


def test_the_manifest_and_the_sidecar_agree_on_the_image(rows):
    """Two records of the same digest, written by different steps. If these disagree the row and
    the sidecar are describing different captures, which is a worse failure than a stale hash."""
    bad = [
        row["capture_id"] for row in rows
        if _sidecar_path(row["capture_id"]).exists()
        and json.loads(_sidecar_path(row["capture_id"]).read_bytes())["image"]["sha256"]
        != row["image_sha256"]
    ]
    assert not bad, f"manifest image_sha256 disagrees with the sidecar's image.sha256: {bad[:5]}"


def test_the_manifest_and_the_sidecar_agree_on_depth(rows):
    """Depth is optional, so the two ways of saying "there is none" must not drift apart: an empty
    cell in the manifest and an absent `depth` object in the sidecar have to mean each other."""
    bad = []
    for row in rows:
        path = _sidecar_path(row["capture_id"])
        if not path.exists():
            continue
        depth = json.loads(path.read_bytes()).get("depth")
        recorded = row["depth_sha256"]
        actual = (depth or {}).get("sha256", "")
        if actual != recorded:
            bad.append((row["capture_id"], recorded[:12] or "(none)", actual[:12] or "(none)"))
    assert not bad, (
        "manifest depth_sha256 disagrees with the sidecar's depth: "
        + ", ".join(f"{c} recorded {r} actual {a}" for c, r, a in bad[:3])
    )
