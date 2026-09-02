"""Human ground-truth labels for the screening eval (TICK-246, #168).

The labels CSV is the eval reference: one row per entrance x criterion,
recorded at capture time by the operator who stood at the door. Truth is
presence-only ("present" or "absent") because the labeler saw the door in
person; a criterion the operator genuinely could not observe stays blank,
never guessed. Labels are human ground truth - never derived from, corrected
by, or reconciled against model output.

Sealed-subset entrances are labeled at capture like every other entrance, but
their labels leave this module only through the deliberate results-freeze path
(D-007): labels_for_eval refuses split="sealed" unless audited=True AND the
unsealing is recorded in SEAL_AUDIT.log via seal_audit.record_unsealing
(D-017) — the flag alone never unseals.
"""

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from frontdoor.manifest import read_manifest
from frontdoor.seal_audit import record_unsealing
from frontdoor.split import InvalidEntranceId, assign_split, canonical_entrance_id

# Must match the criterion keys in the screening engine's CRITERIA
# (frontdoor.screening, TICK-245) so eval joins labels to verdicts cleanly.
# test_labels pins this list; change both together or not at all.
CRITERIA_KEYS = (
    "ramp_or_bevel",
    "handrails",
    "accessible_door_hardware",
    "accessibility_signage",
)

# Presence-only vocabulary: the labeler saw the door, so the feature was
# either there or it was not. No not_visible, no appearance-style labels;
# a criterion the operator could not observe is left blank.
ALLOWED_TRUTHS = ("present", "absent")

COLUMNS = ("entrance_id", "criterion", "truth", "labeled_by", "labeled_at")

SPLITS = ("dev", "calib", "sealed")


class LabelError(ValueError):
    """Raised when a labels file cannot be trusted as the eval reference."""


class SealedLabelError(LabelError):
    """Raised when sealed-split labels are requested outside the audited path."""


@dataclass(frozen=True)
class LoadedLabels:
    labels: tuple  # one dict per labeled row, entrance IDs canonical
    blank_skipped: int  # rows whose truth was left blank (could not observe)


def entrance_ids_from_manifest(manifest_path):
    """Entrance IDs from the capture manifest, deduplicated, capture order."""
    seen = {}
    for row in read_manifest(manifest_path):
        seen.setdefault(row["entrance_id"], None)
    return list(seen)


def template_rows(entrance_ids):
    """One blank row per entrance x criterion, ready for the operator."""
    rows = []
    seen = set()
    for raw in entrance_ids:
        entrance_id = canonical_entrance_id(raw)
        if entrance_id in seen:
            continue
        seen.add(entrance_id)
        for criterion in CRITERIA_KEYS:
            rows.append(
                {
                    "entrance_id": entrance_id,
                    "criterion": criterion,
                    "truth": "",
                    "labeled_by": "",
                    "labeled_at": "",
                }
            )
    return rows


def write_template(path, entrance_ids):
    """Write a labels template CSV for the given entrances."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(template_rows(entrance_ids))


def _require_canonical(raw, line):
    """The label file stores canonical IDs only; a variant spelling in the
    committed record is corruption, not something to repair silently."""
    try:
        canonical = canonical_entrance_id(raw)
    except InvalidEntranceId as exc:
        raise LabelError(f"line {line}: {exc}") from exc
    if canonical != raw:
        raise LabelError(
            f"line {line}: entrance ID {raw!r} is not in canonical form "
            f"({canonical!r}); the label file stores canonical IDs only"
        )
    return canonical


def load_labels(path):
    """Load and validate a labels CSV.

    Returns LoadedLabels. Blank-truth rows (operator could not observe) are
    skipped and counted, never an error. Everything else that would make the
    file ambiguous as ground truth raises LabelError naming the line.
    """
    with open(Path(path), encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(COLUMNS):
            raise LabelError(
                f"label columns {reader.fieldnames!r} do not match {list(COLUMNS)!r}"
            )
        rows = list(reader)
    labels = []
    blank_skipped = 0
    seen = set()
    for line, row in enumerate(rows, start=2):
        if None in row or None in row.values():
            raise LabelError(f"line {line}: wrong number of fields")
        entrance_id = _require_canonical(row["entrance_id"], line)
        criterion = row["criterion"]
        if criterion not in CRITERIA_KEYS:
            raise LabelError(
                f"line {line}: unknown criterion {criterion!r}; "
                f"expected one of {CRITERIA_KEYS}"
            )
        pair = (entrance_id, criterion)
        if pair in seen:
            raise LabelError(
                f"line {line}: duplicate label for {entrance_id} / {criterion}; "
                "the format is one row per entrance x criterion"
            )
        seen.add(pair)
        truth = row["truth"]
        if truth == "":
            blank_skipped += 1
            continue
        if truth not in ALLOWED_TRUTHS:
            raise LabelError(
                f"line {line}: truth {truth!r} is not one of {ALLOWED_TRUTHS}; "
                "the vocabulary is presence-only"
            )
        if row["labeled_by"] == "":
            raise LabelError(
                f"line {line}: labeled_by is blank on a labeled row; every "
                "label names the operator who saw the door"
            )
        try:
            date.fromisoformat(row["labeled_at"])
        except ValueError as exc:
            raise LabelError(
                f"line {line}: labeled_at {row['labeled_at']!r} is not an "
                "ISO date (YYYY-MM-DD)"
            ) from exc
        labels.append(
            {
                "entrance_id": entrance_id,
                "criterion": criterion,
                "truth": truth,
                "labeled_by": row["labeled_by"],
                "labeled_at": row["labeled_at"],
            }
        )
    return LoadedLabels(labels=tuple(labels), blank_skipped=blank_skipped)


#: What labels_for_eval needs to record a sealed unsealing, keyed exactly as
#: record_unsealing's keyword arguments (seal_audit, D-017).
AUDIT_KEYS = ("manifest_path", "audit_path", "repo", "config")


def labels_for_eval(labels, *, split="dev", audited=False, audit=None):
    """Filter labels to one split for eval use; sealed is audited, not flagged.

    Mirrors the screening engine's split discipline: the split is resolved
    here from each entrance ID, and sealed-split labels are handed back only
    through the deliberate, human-run results-freeze path. That path passes
    audited=True AND `audit`, a mapping with AUDIT_KEYS, and the labels are
    released only after seal_audit.record_unsealing has appended one line to
    the audit log (D-017) — same discipline as `python -m frontdoor.eval
    --include-sealed`. audited=True alone never unseals; any SealAuditError
    (dirty tree, unwritable log, ...) propagates and no sealed label is
    returned. Day-to-day eval calls get the dev split by default.
    """
    if split not in SPLITS:
        raise LabelError(f"unknown split {split!r}; expected one of {SPLITS}")
    if split == "sealed":
        if not audited:
            raise SealedLabelError(
                "sealed-split labels are not evaluated until results freeze; "
                "pass audited=True only from the audited freeze path"
            )
        if audit is None:
            raise SealedLabelError(
                "audited=True alone does not unseal: the unsealing must be "
                "recorded first (D-017). Pass audit= a mapping with keys "
                f"{AUDIT_KEYS} so record_unsealing can append the audit line."
            )
        missing = [key for key in AUDIT_KEYS if key not in audit]
        if missing:
            raise SealedLabelError(
                f"audit is missing {missing}; record_unsealing needs all of "
                f"{AUDIT_KEYS} to append the audit line"
            )
        # Raises SealAuditError without writing if the run cannot be recorded;
        # sealed labels are handed back only after the line is on disk.
        record_unsealing(
            argv=["labels", "--split", "sealed"],
            manifest_path=audit["manifest_path"],
            audit_path=audit["audit_path"],
            repo=audit["repo"],
            config=audit["config"],
        )
    return [
        label for label in labels if assign_split(label["entrance_id"]) == split
    ]
