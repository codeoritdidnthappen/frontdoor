"""Human ground-truth labels for the screening eval (TICK-246, #168).

The labels CSV is the eval reference: one row per eligible entrance x
criterion. For the frozen 2026-09-04 dataset, James records them
retrospectively from his original photos and recollection; they are not
capture-time labels. Truth is presence-only ("present" or "absent"); a
criterion he genuinely cannot determine stays blank, never guessed. Labels
are human ground truth - never derived from, corrected by, or reconciled
against model output.

Sealed-subset entrances are labeled like every other eligible entrance, but
their labels leave this module only through the deliberate results-freeze path
(D-007): labels_for_eval refuses split="sealed" unless audited=True AND the
unsealing is recorded in SEAL_AUDIT.log via seal_audit.record_unsealing
(D-017) — the flag alone never unseals.
"""

import csv
import fcntl
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import Mapping, Sequence

from frontdoor import seal_audit
from frontdoor.manifest import read_manifest
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


class LabelConflict(LabelError):
    """Raised when an accepted future-capture label is changed."""


_future_label_write_lock = Lock()


@dataclass(frozen=True)
class LoadedLabels:
    labels: tuple  # one dict per labeled row, entrance IDs canonical
    blank_skipped: int  # rows whose truth was left blank (could not observe)


@dataclass(frozen=True)
class LabelingProgress:
    """How much of an eligible entrance-level label sheet James reviewed."""

    reviewed_entrances: int
    total_entrances: int

    @property
    def complete(self) -> bool:
        return self.reviewed_entrances == self.total_entrances


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


def _read_sheet(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(COLUMNS):
                raise LabelError(
                    f"label columns {reader.fieldnames!r} do not match {list(COLUMNS)!r}"
                )
            rows = list(reader)
    except FileNotFoundError as exc:
        raise LabelError(f"labels file is missing: {path}") from exc
    if any(None in row or None in row.values() for row in rows):
        raise LabelError("labels file has a row with the wrong number of fields")
    return rows


def _expected_pairs(entrance_ids: Sequence[str]) -> list[tuple[str, str]]:
    return [
        (row["entrance_id"], row["criterion"])
        for row in template_rows(entrance_ids)
    ]


def read_labeling_sheet(
    path: Path, entrance_ids: Sequence[str]
) -> list[dict[str, str]]:
    """Read a sheet only when it contains exactly the eligible label rows."""
    rows = _read_sheet(path)
    actual = [(row["entrance_id"], row["criterion"]) for row in rows]
    expected = _expected_pairs(entrance_ids)
    if actual != expected:
        raise LabelError(
            "labels file must contain exactly one ordered row per eligible "
            "entrance and criterion"
        )
    # Reuse the evaluation boundary for truth, canonical-ID and date validation.
    load_labels(path)
    for line, row in enumerate(rows, start=2):
        has_provenance = bool(row["labeled_by"] or row["labeled_at"])
        if has_provenance and not (row["labeled_by"] and row["labeled_at"]):
            raise LabelError(
                f"line {line}: reviewed rows require both labeled_by and labeled_at"
            )
        if row["truth"] == "" and has_provenance:
            try:
                date.fromisoformat(row["labeled_at"])
            except ValueError as exc:
                raise LabelError(
                    f"line {line}: labeled_at {row['labeled_at']!r} is not an "
                    "ISO date (YYYY-MM-DD)"
                ) from exc
    return rows


def initialize_labeling_sheet(path: Path, entrance_ids: Sequence[str]) -> None:
    """Create the blank eligible sheet once; validate rather than replace it later."""
    if path.exists():
        read_labeling_sheet(path, entrance_ids)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    write_template(path, entrance_ids)


def _atomic_write_sheet(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            "w", encoding="utf-8", newline="", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_entrance_labels(
    path: Path,
    entrance_ids: Sequence[str],
    entrance_id: str,
    answers: Mapping[str, str],
    *,
    labeled_by: str,
    labeled_at: date,
) -> None:
    """Atomically save all four reviewed answers for one eligible entrance."""
    if entrance_id not in entrance_ids:
        raise LabelError(f"entrance {entrance_id!r} is not evaluation eligible")
    if set(answers) != set(CRITERIA_KEYS):
        raise LabelError("answers must contain each screening criterion exactly once")
    allowed = {*ALLOWED_TRUTHS, ""}
    for criterion, truth in answers.items():
        if truth not in allowed:
            raise LabelError(
                f"answer for {criterion!r} must be present, absent, or blank"
            )
    if not labeled_by.strip():
        raise LabelError("labeled_by must not be blank")

    rows = read_labeling_sheet(path, entrance_ids)
    updated = []
    for row in rows:
        if row["entrance_id"] == entrance_id:
            row = {
                **row,
                "truth": answers[row["criterion"]],
                "labeled_by": labeled_by.strip(),
                "labeled_at": labeled_at.isoformat(),
            }
        updated.append(row)
    _atomic_write_sheet(path, updated)


def append_future_entrance_labels(
    path: Path,
    entrance_id: str,
    answers: Mapping[str, str],
    *,
    labeled_by: str,
    labeled_at: date,
) -> bool:
    """Append one immutable four-row future-capture label atomically.

    Returns ``True`` for a new record and ``False`` for an identical retry.
    The process lock covers concurrent threads and the sibling lock file covers
    multiple server processes, serializing the complete read/compare/replace
    transaction rather than only the final write.
    """
    canonical = _require_canonical(entrance_id, "submission")
    if set(answers) != set(CRITERIA_KEYS):
        raise LabelError("answers must contain each screening criterion exactly once")
    allowed = {*ALLOWED_TRUTHS, ""}
    if any(truth not in allowed for truth in answers.values()):
        raise LabelError("answers must be present, absent, or blank")
    operator = labeled_by.strip()
    if not operator:
        raise LabelError("labeled_by must not be blank")

    with _future_label_write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.with_name(f"{path.name}.lock").open("w", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            rows = _read_sheet(path) if path.exists() else []
            if path.exists():
                load_labels(path)
            existing = [row for row in rows if row["entrance_id"] == canonical]
            if existing:
                by_criterion = {row["criterion"]: row for row in existing}
                complete = (
                    len(existing) == len(CRITERIA_KEYS)
                    and set(by_criterion) == set(CRITERIA_KEYS)
                    and all(row["labeled_at"] for row in existing)
                )
                identical = complete and all(
                    by_criterion[criterion]["truth"] == answers[criterion]
                    and by_criterion[criterion]["labeled_by"] == operator
                    for criterion in CRITERIA_KEYS
                )
                if identical:
                    return False
                raise LabelConflict(
                    f"entrance {canonical} already has a different label"
                )

            stamped = labeled_at.isoformat()
            rows.extend(
                {
                    "entrance_id": canonical,
                    "criterion": criterion,
                    "truth": answers[criterion],
                    "labeled_by": operator,
                    "labeled_at": stamped,
                }
                for criterion in CRITERIA_KEYS
            )
            _atomic_write_sheet(path, rows)
    return True


def labeling_progress(path: Path, entrance_ids: Sequence[str]) -> LabelingProgress:
    """Count entrances whose four choices have all been deliberately reviewed."""
    rows = read_labeling_sheet(path, entrance_ids)
    reviewed = {
        entrance_id
        for entrance_id in entrance_ids
        if all(
            row["labeled_by"] and row["labeled_at"]
            for row in rows
            if row["entrance_id"] == entrance_id
        )
    }
    return LabelingProgress(len(reviewed), len(entrance_ids))


def require_complete_labeling(path: Path, entrance_ids: Sequence[str]) -> None:
    """Validate the sheet and refuse until every eligible entrance was reviewed."""
    progress = labeling_progress(path, entrance_ids)
    if not progress.complete:
        raise LabelError(
            f"labeling is incomplete: {progress.reviewed_entrances} of "
            f"{progress.total_entrances} eligible entrances reviewed"
        )


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


#: What labels_for_eval needs to record a sealed unsealing. Re-exported from
#: seal_audit, which owns the contract (D-017): the keys are exactly
#: record_unsealing's keyword arguments, defined once, next to that signature,
#: so this module cannot drift from it.
AUDIT_KEYS = seal_audit.AUDIT_KEYS


def labels_for_eval(labels, *, split="dev", audited=False, audit=None, argv=None):
    """Filter labels to one split for eval use; sealed is audited, not flagged.

    Mirrors the screening engine's split discipline: the split is resolved
    here from each entrance ID, and sealed-split labels are handed back only
    through the deliberate, human-run results-freeze path. That path passes
    audited=True AND `audit`, a mapping with AUDIT_KEYS, and the labels are
    released only after seal_audit.record_unsealing has appended one line to
    the audit log (D-017) — same discipline as an audited `--include-sealed`
    run. audited=True alone never unseals; any SealAuditError (dirty tree,
    unwritable log, ...) propagates and no sealed label is returned. Day-to-day
    eval calls get the dev split by default.

    `argv` is the command line to record. An entrypoint passes the one the
    operator actually typed, so the freeze-day line names a runnable command.
    A library call that omits it is recorded as `["labels", "--split", "sealed"]`
    so the line is still well-formed.
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
        # seal_audit owns both halves of the doorway: it validates the audit
        # mapping against the keys record_unsealing actually takes, and it
        # appends the SEAL_AUDIT.log line. This module only translates an
        # incomplete mapping into the label-domain refusal type.
        try:
            seal_audit.validate_audit_mapping(audit)
        except seal_audit.SealAuditError as exc:
            raise SealedLabelError(str(exc)) from exc
        # Raises SealAuditError without writing if the run cannot be recorded;
        # sealed labels are handed back only after the line is on disk.
        seal_audit.record_unsealing(
            argv=["labels", "--split", "sealed"] if argv is None else list(argv),
            **{key: audit[key] for key in AUDIT_KEYS},
        )
    return [
        label for label in labels if assign_split(label["entrance_id"]) == split
    ]
