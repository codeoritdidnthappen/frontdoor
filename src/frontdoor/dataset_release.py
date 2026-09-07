"""Stage the labeled screening dataset for a GitHub release (TICK-015, #23).

Does not publish. The GitHub release waits on the audited unsealing run (#63)
and on operator labels (#302). This module copies the git-side records, writes
release notes and the R2 object map, and names what still blocks publication.

Photograph and depth bytes stay in the private buckets. The archive documents
each object's key and the SHA-256 the manifest already recorded.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

from frontdoor.dataset_closeout import (
    EXPECTED_DEVICE_ALIASES,
    NORMALIZED_DEVICE,
    _line_ending_hint,
)
from frontdoor.labels import ALLOWED_TRUTHS, COLUMNS as LABEL_COLUMNS, CRITERIA_KEYS
from frontdoor.manifest import read_manifest, sha256_file
from frontdoor.storage import storage_key

IMAGE_BUCKET = "frontdoor-image"
DEPTH_BUCKET = "frontdoor-depth"

SECRET_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY"),
    re.compile(r"AIza[0-9A-Za-z\-_]{20,}"),
    re.compile(r"FRONTDOOR_(?:IMAGES|DEPTH|UPLOAD)_SECRET\s*="),
)

_TEXT_SUFFIXES = {".csv", ".json", ".log", ".md", ".txt"}


class DatasetReleaseError(ValueError):
    """The tree cannot be packed into an honest release staging directory."""


def label_counts(path):
    """Presence / absence / blank, splitting reviewed blanks from untouched."""
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(LABEL_COLUMNS):
            raise DatasetReleaseError(
                f"label columns {reader.fieldnames!r} do not match "
                f"{list(LABEL_COLUMNS)!r}"
            )
        rows = list(reader)
    present = absent = blank_reviewed = blank_untouched = 0
    for row in rows:
        truth = (row.get("truth") or "").strip()
        reviewed = bool((row.get("labeled_by") or "").strip())
        if truth == "present":
            present += 1
        elif truth == "absent":
            absent += 1
        elif truth:
            raise DatasetReleaseError(
                f"truth {truth!r} is not one of {ALLOWED_TRUTHS} or blank"
            )
        elif reviewed:
            blank_reviewed += 1
        else:
            blank_untouched += 1
    return {
        "rows": len(rows),
        "present": present,
        "absent": absent,
        "blank_reviewed": blank_reviewed,
        "blank_untouched": blank_untouched,
        "missing": blank_reviewed + blank_untouched,
    }


def _sidecar_stats(rows, sidecar_dir):
    devices = set()
    dates = []
    for row in rows:
        capture_id = row["capture_id"]
        path = sidecar_dir / f"{capture_id}.json"
        if not path.is_file():
            raise DatasetReleaseError(
                f"capture {capture_id} has no sidecar at {path}"
            )
        digest = sha256_file(path)
        if digest != row["sidecar_sha256"]:
            raise DatasetReleaseError(
                f"capture {capture_id} sidecar hash does not match the manifest"
                + _line_ending_hint(path, row["sidecar_sha256"])
            )
        sidecar = json.loads(path.read_text(encoding="utf-8"))
        device = sidecar.get("device_model")
        if device not in EXPECTED_DEVICE_ALIASES:
            raise DatasetReleaseError(
                f"capture {capture_id} uses unexpected device {device!r}; "
                "this dataset is one physical phone, James's iPhone 17 Pro"
            )
        devices.add(device)
        captured_at = sidecar.get("captured_at")
        if isinstance(captured_at, str) and len(captured_at) >= 10:
            dates.append(captured_at[:10])
    return {
        "devices": sorted(devices),
        "first_date": min(dates) if dates else None,
        "last_date": max(dates) if dates else None,
    }


def collect_stats(root):
    root = Path(root)
    manifest_path = root / "data" / "manifest.csv"
    sidecar_dir = root / "data" / "sidecars"
    labels_path = root / "data" / "labels.csv"
    seed_path = root / "src" / "frontdoor" / "split_seed.json"
    audit_path = root / "SEAL_AUDIT.log"
    for path, label in (
        (manifest_path, "manifest"),
        (sidecar_dir, "sidecar directory"),
        (labels_path, "labels"),
        (seed_path, "split seed"),
    ):
        if not path.exists():
            raise DatasetReleaseError(f"{label} not found: {path}")

    rows = read_manifest(manifest_path)
    if not rows:
        raise DatasetReleaseError("the manifest is empty")
    splits = Counter(row["split"] for row in rows)
    entrances = {row["entrance_id"] for row in rows}
    entrance_splits = {}
    for row in rows:
        entrance_splits[row["entrance_id"]] = row["split"]
    sidecar = _sidecar_stats(rows, sidecar_dir)
    labels = label_counts(labels_path)
    blockers = []
    if not audit_path.is_file() or not audit_path.read_text(encoding="utf-8").strip():
        blockers.append(
            "SEAL_AUDIT.log is missing; the audited unsealing run (#63) has not landed."
        )
    if labels["blank_untouched"]:
        blockers.append(
            f"{labels['blank_untouched']} label rows are untouched "
            "(no labeled_by); operator labels (#302) are not complete."
        )
    return {
        "capture_count": len(rows),
        "entrance_count": len(entrances),
        "captures_by_split": {name: splits[name] for name in ("dev", "calib", "sealed")},
        "entrances_by_split": dict(Counter(entrance_splits.values())),
        "with_depth": sum(1 for row in rows if (row.get("depth_sha256") or "").strip()),
        "labels": labels,
        "audit_present": audit_path.is_file() and bool(
            audit_path.read_text(encoding="utf-8").strip()
        ),
        "publish_blockers": blockers,
        **sidecar,
    }


def render_notes(stats):
    aliases = stats["devices"]
    alias_line = (
        f"Sidecars record {', '.join(aliases)}. That name is the same physical "
        f"phone as `{NORMALIZED_DEVICE}` (D-040)."
        if any(name != NORMALIZED_DEVICE for name in aliases)
        else f"Sidecars record `{NORMALIZED_DEVICE}` only."
    )
    blockers = stats["publish_blockers"]
    status = (
        "This staging directory is **not** the published release. "
        + " ".join(blockers)
        if blockers
        else "Git-side records are complete. Publish only after a clean-room hash check."
    )
    labels = stats["labels"]
    splits = stats["captures_by_split"]
    return "\n".join([
        "# Screening dataset release notes",
        "",
        status,
        "",
        "## Counts",
        "",
        f"- Entrances: {stats['entrance_count']}",
        f"- Images (manifest rows): {stats['capture_count']}",
        f"- Realized split (captures): dev {splits['dev']}, "
        f"calib {splits['calib']}, sealed {splits['sealed']}",
        f"- Capture date range: {stats['first_date']} to {stats['last_date']}",
        f"- Depth objects present: {stats['with_depth']} "
        "(imported captures record `depth: null`; depth is not ground truth)",
        "",
        "## Device",
        "",
        "One physical capture device: James's iPhone 17 Pro with LiDAR, "
        f"normalized as `{NORMALIZED_DEVICE}` for reporting.",
        alias_line,
        "",
        "## Labels",
        "",
        "Ground truth is the capturing operator's per-entrance presence labels "
        "for ramp or beveled threshold, handrails, accessible door hardware, "
        "and accessibility signage.",
        f"Vocabulary: `{ALLOWED_TRUTHS[0]}`, `{ALLOWED_TRUTHS[1]}`, or blank "
        "when the operator could not observe the feature. Criteria: "
        + ", ".join(CRITERIA_KEYS) + ".",
        f"- present: {labels['present']}",
        f"- absent: {labels['absent']}",
        f"- blank (reviewed, could not determine): {labels['blank_reviewed']}",
        f"- blank (untouched): {labels['blank_untouched']}",
        f"- missing-label count (all blanks): {labels['missing']}",
        "Labels are human ground truth. They are not model output.",
        "",
        "## What this dataset is not",
        "",
        "- Depth is captured sensor output, not metric LiDAR range, and not ground truth.",
        "- No caliper measurements, threshold-rise measurements, or dimensional accuracy.",
        "- No ADA compliance claim and no legal accessibility determination.",
        "",
        "## Bytes",
        "",
        "Photographs and depth objects are not in this archive. `OBJECTS.md` lists "
        f"each R2 key in `{IMAGE_BUCKET}` / `{DEPTH_BUCKET}` and the SHA-256 "
        "recorded by `data/manifest.csv`. A third party with the team's read "
        "credential (never shipped in this archive) can fetch those objects; "
        "recomputing hashes must reproduce the manifest with no differences.",
        "",
    ]) + "\n"


def render_objects(rows):
    lines = [
        "# Photograph and depth objects",
        "",
        "Private Cloudflare R2 buckets. This archive does not contain credentials "
        "and does not contain the bytes.",
        "",
        f"Image bucket: `{IMAGE_BUCKET}`. Depth bucket: `{DEPTH_BUCKET}`.",
        "Object key is `open/<capture_id>` or `sealed/<capture_id>` from the "
        "manifest split (D-007).",
        "",
        "| capture_id | split | image_key | image_sha256 | depth_key | depth_sha256 |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        key = storage_key(row["capture_id"], row["split"])
        depth_hash = (row.get("depth_sha256") or "").strip()
        depth_key = key if depth_hash else ""
        lines.append(
            f"| {row['capture_id']} | {row['split']} | {key} | "
            f"{row['image_sha256']} | {depth_key} | {depth_hash} |"
        )
    return "\n".join(lines) + "\n"


def _copy(src, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def scan_for_secrets(out_dir):
    """Refuse a pack that would ship credentials or key material."""
    out_dir = Path(out_dir)
    hits = []
    for path in out_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        if path.name == ".env":
            hits.append(f"{path}: .env must not ship")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                hits.append(f"{path}: matches {pattern.pattern}")
    if hits:
        raise DatasetReleaseError(
            "packed files look like they contain secrets:\n" + "\n".join(hits)
        )


def pack(root, out_dir):
    """Copy git-side dataset records into out_dir and write notes.

    Returns the stats dict, including publish_blockers. Never creates a
    GitHub release.
    """
    root = Path(root)
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise DatasetReleaseError(
            f"{out_dir} already exists; refusing to overwrite a staged release"
        )
    stats = collect_stats(root)
    rows = read_manifest(root / "data" / "manifest.csv")
    out_dir.mkdir(parents=True)
    _copy(root / "data" / "manifest.csv", out_dir / "data" / "manifest.csv")
    _copy(root / "data" / "labels.csv", out_dir / "data" / "labels.csv")
    _copy(
        root / "src" / "frontdoor" / "split_seed.json",
        out_dir / "src" / "frontdoor" / "split_seed.json",
    )
    sidecar_src = root / "data" / "sidecars"
    sidecar_dest = out_dir / "data" / "sidecars"
    sidecar_dest.mkdir(parents=True)
    for row in rows:
        name = f"{row['capture_id']}.json"
        _copy(sidecar_src / name, sidecar_dest / name)
    audit = root / "SEAL_AUDIT.log"
    if stats["audit_present"]:
        _copy(audit, out_dir / "SEAL_AUDIT.log")
    (out_dir / "RELEASE_NOTES.md").write_text(render_notes(stats), encoding="utf-8")
    (out_dir / "OBJECTS.md").write_text(render_objects(rows), encoding="utf-8")
    scan_for_secrets(out_dir)
    return stats


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] != "pack" or len(args) > 2:
        print(
            "usage: python -m frontdoor.dataset_release pack [out_dir]",
            file=sys.stderr,
        )
        return 2
    out_dir = args[1] if len(args) == 2 else "dist/dataset-release"
    try:
        stats = pack(Path("."), out_dir)
    except DatasetReleaseError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(json.dumps({
        "out_dir": str(out_dir),
        "capture_count": stats["capture_count"],
        "entrance_count": stats["entrance_count"],
        "publish_blockers": stats["publish_blockers"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
