"""Deterministic capture closeout and evaluation eligibility (TICK-095, #69).

The manifest is append-only capture history.  This module does not rewrite it;
it records which entrances meet the screening protocol's minimum retained-view
and condition-tag requirements, and makes that decision reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from jsonschema import ValidationError

from frontdoor.manifest import manifest_sha256, read_manifest, sha256_file
from frontdoor.sidecar import validate_sidecar
from frontdoor.split import InvalidEntranceId, assign_split, canonical_entrance_id

CLOSEOUT_SCHEMA_VERSION = 1
DECISION_DATE = "2026-09-04"
MINIMUM_CAPTURES = 5
REQUIRED_CONDITIONS = ("distance_m", "lighting", "occlusion")
EXPECTED_DEVICE_ALIASES = ("iPhone 17 Pro", "iPhone18,1")
NORMALIZED_DEVICE = "iPhone18,1"
SPLITS = ("dev", "calib", "sealed")


class DatasetCloseoutError(ValueError):
    """The committed dataset cannot support a trustworthy closeout record."""


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise DatasetCloseoutError(f"{label} must be a JSON object")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise DatasetCloseoutError(f"{label} must be a non-empty string")
    return value


def _line_ending_hint(path: Path, expected_sha256: str) -> str:
    """Name CRLF as the cause when that alone explains a sidecar mismatch.

    .gitattributes pins these files to LF, but git does not renormalize a
    working tree that was checked out before the attribute existed, so an
    older Windows clone holds CRLF sidecars whose bytes hash differently.
    The content is fine; only the line endings differ. Without this the
    error reads like data corruption and sends the reader after the wrong
    problem (TICK-323).
    """
    try:
        raw = path.read_bytes()
    except OSError:  # unreadable is a different failure; say nothing extra
        return ""
    if b"\r\n" not in raw:
        return ""
    normalized = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    if normalized != expected_sha256:
        return ""
    return (
        ". The file holds CRLF line endings and matches the manifest once they "
        "are LF, so only the line endings differ. This working tree predates "
        "the eol=lf attribute; restore it with "
        "'git rm -r --cached data/sidecars data/manifest.csv' followed by "
        "'git checkout -- data/sidecars data/manifest.csv', or re-clone"
    )


def _read_sidecar(path: Path, capture_id: str) -> dict[str, object]:
    if not path.is_file():
        raise DatasetCloseoutError(
            f"capture {capture_id} has no committed sidecar at {path}"
        )
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetCloseoutError(
            f"capture {capture_id} sidecar is not valid JSON: {exc}"
        ) from exc
    sidecar = _mapping(raw, f"capture {capture_id} sidecar")
    try:
        validate_sidecar(sidecar)
    except ValidationError as exc:
        raise DatasetCloseoutError(
            f"capture {capture_id} sidecar failed validation: {exc.message}"
        ) from exc
    return sidecar


def _split_counts(values: list[str]) -> dict[str, int]:
    counts = Counter(values)
    return {split: counts[split] for split in SPLITS}


def _split_proportions(counts: dict[str, int]) -> dict[str, float]:
    total = sum(counts.values())
    return {split: counts[split] / total for split in SPLITS}


def build_closeout(manifest_path: Path, sidecar_dir: Path) -> dict[str, object]:
    """Build the closeout record after validating every manifest/sidecar pair."""
    rows = read_manifest(manifest_path)
    if not rows:
        raise DatasetCloseoutError("the manifest is empty; there is no dataset to close")

    capture_ids: set[str] = set()
    entrance_captures: dict[str, list[str]] = defaultdict(list)
    entrance_splits: dict[str, str] = {}
    capture_splits: list[str] = []
    capture_dates: list[str] = []
    devices: set[str] = set()
    modes: set[str] = set()
    lighting: set[str] = set()

    for row in rows:
        capture_id = row["capture_id"]
        if capture_id in capture_ids:
            raise DatasetCloseoutError(
                f"capture_id {capture_id!r} appears more than once in the manifest"
            )
        capture_ids.add(capture_id)
        try:
            entrance_id = canonical_entrance_id(row["entrance_id"])
        except InvalidEntranceId as exc:
            raise DatasetCloseoutError(
                f"capture {capture_id} has invalid entrance_id {row['entrance_id']!r}"
            ) from exc
        expected_split = assign_split(entrance_id)
        if row["split"] != expected_split:
            raise DatasetCloseoutError(
                f"capture {capture_id} records split {row['split']!r}; "
                f"the committed seed assigns {expected_split!r}"
            )

        sidecar_path = sidecar_dir / f"{capture_id}.json"
        if sidecar_path.is_file() and sha256_file(sidecar_path) != row["sidecar_sha256"]:
            raise DatasetCloseoutError(
                f"capture {capture_id} sidecar hash does not match the manifest"
                + _line_ending_hint(sidecar_path, row["sidecar_sha256"])
            )
        sidecar = _read_sidecar(sidecar_path, capture_id)
        if sidecar.get("capture_id") != capture_id:
            raise DatasetCloseoutError(
                f"capture {capture_id} sidecar names capture {sidecar.get('capture_id')!r}"
            )
        if sidecar.get("entrance_id") != entrance_id:
            raise DatasetCloseoutError(
                f"capture {capture_id} sidecar names entrance "
                f"{sidecar.get('entrance_id')!r}, expected {entrance_id!r}"
            )
        if sidecar.get("split") != expected_split:
            raise DatasetCloseoutError(
                f"capture {capture_id} sidecar records split {sidecar.get('split')!r}, "
                f"expected {expected_split!r}"
            )

        device = _string(sidecar.get("device_model"), f"capture {capture_id} device_model")
        if device not in EXPECTED_DEVICE_ALIASES:
            raise DatasetCloseoutError(
                f"capture {capture_id} uses unexpected device {device!r}; "
                "this dataset is restricted to James's iPhone 17 Pro"
            )
        conditions = _mapping(
            sidecar.get("conditions"), f"capture {capture_id} conditions"
        )
        missing = [key for key in REQUIRED_CONDITIONS if conditions.get(key) is None]
        if missing:
            raise DatasetCloseoutError(
                f"capture {capture_id} is missing required condition tags: "
                + ", ".join(missing)
            )

        captured_at = _string(
            sidecar.get("captured_at"), f"capture {capture_id} captured_at"
        )
        mode = _string(sidecar.get("capture_mode"), f"capture {capture_id} capture_mode")
        entrance_captures[entrance_id].append(capture_id)
        entrance_splits[entrance_id] = expected_split
        capture_splits.append(expected_split)
        capture_dates.append(captured_at[:10])
        devices.add(device)
        modes.add(mode)
        lighting.add(_string(conditions.get("lighting"), f"capture {capture_id} lighting"))

    if modes != {"imported"}:
        raise DatasetCloseoutError(
            "the frozen dataset must contain only imported captures; "
            f"recorded modes: {', '.join(sorted(modes))}"
        )
    if lighting != {"direct sun"}:
        raise DatasetCloseoutError(
            "the frozen dataset must contain only direct sun lighting; "
            f"recorded values: {', '.join(sorted(lighting))}"
        )

    eligible_ids = sorted(
        entrance_id
        for entrance_id, ids in entrance_captures.items()
        if len(ids) >= MINIMUM_CAPTURES
    )
    ineligible_ids = sorted(set(entrance_captures) - set(eligible_ids))
    eligible_capture_ids = {
        capture_id
        for entrance_id in eligible_ids
        for capture_id in entrance_captures[entrance_id]
    }
    eligible_capture_splits = [
        row["split"] for row in rows if row["capture_id"] in eligible_capture_ids
    ]
    dataset_entrance_counts = _split_counts(list(entrance_splits.values()))
    dataset_capture_counts = _split_counts(capture_splits)
    eligible_entrance_counts = _split_counts(
        [entrance_splits[entrance_id] for entrance_id in eligible_ids]
    )
    eligible_capture_counts = _split_counts(eligible_capture_splits)

    return {
        "schema_version": CLOSEOUT_SCHEMA_VERSION,
        "decision": {
            "action": "stop",
            "date": DECISION_DATE,
            "reason": (
                "The 60-entrance goal is exceeded; remaining time is reserved "
                "for labeling, evaluation, and the deck."
            ),
        },
        "manifest_sha256": manifest_sha256(manifest_path),
        "capture_date_range": {
            "first": min(capture_dates),
            "last": max(capture_dates),
        },
        "protocol": {
            "minimum_captures_per_entrance": MINIMUM_CAPTURES,
            "required_condition_tags": list(REQUIRED_CONDITIONS),
            "semantic_view_roles_recorded": False,
        },
        "dataset": {
            "entrance_count": len(entrance_captures),
            "capture_count": len(rows),
            "entrances_by_split": dataset_entrance_counts,
            "entrance_split_proportions": _split_proportions(dataset_entrance_counts),
            "captures_by_split": dataset_capture_counts,
            "capture_split_proportions": _split_proportions(dataset_capture_counts),
        },
        "eligible": {
            "entrance_count": len(eligible_ids),
            "capture_count": len(eligible_capture_ids),
            "entrances_by_split": eligible_entrance_counts,
            "entrance_split_proportions": _split_proportions(eligible_entrance_counts),
            "captures_by_split": eligible_capture_counts,
            "capture_split_proportions": _split_proportions(eligible_capture_counts),
            "entrance_ids": eligible_ids,
        },
        "ineligible": [
            {
                "entrance_id": entrance_id,
                "split": entrance_splits[entrance_id],
                "capture_count": len(entrance_captures[entrance_id]),
                "reason": f"fewer than {MINIMUM_CAPTURES} committed captures",
            }
            for entrance_id in ineligible_ids
        ],
        "capture_profile": {
            "physical_device": "James's iPhone 17 Pro",
            "normalized_device_model": NORMALIZED_DEVICE,
            "recorded_device_aliases": sorted(devices),
            "capture_modes": sorted(modes),
            "recorded_lighting": sorted(lighting),
        },
        "limitations": [
            (
                "Semantic view roles were not stored in these imported sidecars, "
                "so named-view coverage cannot be verified retroactively."
            ),
            (
                "All retained captures are imported and all recorded lighting is "
                "direct sun, so lighting-condition comparisons are unavailable."
            ),
        ],
    }


def render_closeout(record: dict[str, object]) -> str:
    """Serialize a closeout record with a stable byte representation."""
    return json.dumps(record, indent=2, sort_keys=True) + "\n"


def write_closeout(
    manifest_path: Path, sidecar_dir: Path, output_path: Path
) -> dict[str, object]:
    """Validate the dataset and write its deterministic closeout record."""
    record = build_closeout(manifest_path, sidecar_dir)
    output_path.write_text(render_closeout(record), encoding="utf-8")
    return record


def load_eligible_entrances(
    closeout_path: Path, manifest_path: Path, sidecar_dir: Path
) -> frozenset[str]:
    """Return eligible entrance IDs only when the closeout exactly matches input."""
    try:
        raw: object = json.loads(closeout_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DatasetCloseoutError(f"dataset closeout is missing: {closeout_path}") from exc
    except json.JSONDecodeError as exc:
        raise DatasetCloseoutError(f"dataset closeout is not valid JSON: {exc}") from exc
    recorded = _mapping(raw, "dataset closeout")
    current_hash = manifest_sha256(manifest_path)
    if recorded.get("manifest_sha256") != current_hash:
        raise DatasetCloseoutError(
            "dataset closeout manifest hash does not match the current manifest"
        )
    expected = build_closeout(manifest_path, sidecar_dir)
    if recorded != expected:
        raise DatasetCloseoutError(
            "dataset closeout does not match the validated committed dataset; regenerate it"
        )
    eligible = _mapping(recorded.get("eligible"), "dataset closeout eligible")
    entrance_ids = eligible.get("entrance_ids")
    if not isinstance(entrance_ids, list) or not all(
        isinstance(entrance_id, str) for entrance_id in entrance_ids
    ):
        raise DatasetCloseoutError("dataset closeout eligible.entrance_ids must be strings")
    return frozenset(entrance_ids)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m frontdoor.dataset_closeout",
        description="Validate and record the stopped screening-capture dataset.",
    )
    parser.add_argument("--manifest", type=Path, default=Path("data/manifest.csv"))
    parser.add_argument("--sidecars", type=Path, default=Path("data/sidecars"))
    parser.add_argument("--out", type=Path, default=Path("data/dataset-closeout.json"))
    args = parser.parse_args(argv)
    record = write_closeout(args.manifest, args.sidecars, args.out)
    dataset = _mapping(record["dataset"], "dataset")
    eligible = _mapping(record["eligible"], "eligible")
    print(
        f"stopped at {dataset['entrance_count']} entrances / "
        f"{dataset['capture_count']} captures; evaluation eligible: "
        f"{eligible['entrance_count']} entrances / {eligible['capture_count']} captures"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
