"""POST /labels -- future-capture human ground truth from the phone (TICK-282)."""

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping

from flask import Flask, current_app, request

from frontdoor.labels import (
    ALLOWED_TRUTHS,
    CRITERIA_KEYS,
    LabelConflict,
    LabelError,
    append_future_entrance_labels,
)
from frontdoor.split import InvalidEntranceId, canonical_entrance_id
from frontdoor_server.upload_view import _authorised, _client_key

LABELS_PATH = Path("data/labels.csv")
MAX_OPERATOR_LENGTH = 100

#: Four criteria and a name is a few hundred bytes. The app allows 64 MB (MAX_CONTENT_LENGTH), and
#: the worker has 512 MB on a machine #233 already measured OOM-killing at 186 MB -- and an OOM kill
#: answers with no status code at all, so the phone sees a dropped connection rather than a refusal.
MAX_BODY_BYTES = 8 * 1024

#: Set this to write somewhere other than the default. Required when the default resolves inside a
#: git checkout; see `resolve_labels_path`.
PATH_ENV = "FRONTDOOR_LABELS_PATH"


class LabelsPathRefused(Exception):
    """The sheet to write resolves inside a git checkout, so writing it would dirty the tree."""


def _inside_a_git_checkout(path: Path) -> bool:
    for parent in [path.resolve(), *path.resolve().parents]:
        if (parent / ".git").exists():
            return True
    return False


def resolve_labels_path(configured: Path) -> Path:
    """The sheet to append to, refusing the one case that costs more than it looks.

    An append rewrites the whole sheet, so one submission against a server started from a checkout
    modifies the tracked `data/labels.csv` -- measured: 212 rows in, 216 out. Nothing breaks that
    day. It breaks on freeze day, when `record_unsealing` aborts on a dirty working tree and the
    cause is a data file nobody remembers touching.

    The container copies only `pyproject.toml` and `src`, so there the default is a fresh file and
    this never fires. It fires where the hazard is: a laptop, which is exactly what #52's fallback
    rehearsal and any pre-install test of this flow use.
    """
    configured = Path(configured)
    if configured != LABELS_PATH:
        # Someone said where to write. That is the answer, wherever it points.
        return configured
    if _inside_a_git_checkout(configured):
        raise LabelsPathRefused(
            f"{configured} is inside a git checkout, and appending rewrites the whole sheet -- "
            f"which would modify a tracked file and abort the sealed run on a dirty tree. "
            f"Set {PATH_ENV} (or LABELS_PATH in the app config) to a path outside the repository."
        )
    return configured


@dataclass(frozen=True)
class LabelSubmission:
    """A fully parsed phone label submission."""

    entrance_id: str
    labeled_by: str
    answers: Mapping[str, str]

    @classmethod
    def parse(cls, raw: object) -> "LabelSubmission":
        if not isinstance(raw, dict) or set(raw) != {"entrance_id", "labeled_by", "answers"}:
            raise LabelError("body must contain exactly entrance_id, labeled_by, and answers")

        raw_id = raw["entrance_id"]
        if not isinstance(raw_id, str):
            raise LabelError("entrance_id must be a canonical entrance id")
        try:
            entrance_id = canonical_entrance_id(raw_id)
        except InvalidEntranceId as exc:
            raise LabelError("entrance_id must be a canonical entrance id") from exc
        if entrance_id != raw_id:
            raise LabelError("entrance_id must be a canonical entrance id")

        raw_operator = raw["labeled_by"]
        if not isinstance(raw_operator, str):
            raise LabelError("labeled_by must be text")
        operator = raw_operator.strip()
        if not operator or len(operator) > MAX_OPERATOR_LENGTH:
            raise LabelError(
                f"labeled_by must be 1-{MAX_OPERATOR_LENGTH} non-whitespace characters"
            )

        raw_answers = raw["answers"]
        if not isinstance(raw_answers, dict) or set(raw_answers) != set(CRITERIA_KEYS):
            raise LabelError("answers must contain exactly the four screening criteria")
        allowed = {*ALLOWED_TRUTHS, ""}
        answers: dict[str, str] = {}
        for criterion in CRITERIA_KEYS:
            truth = raw_answers[criterion]
            if not isinstance(truth, str) or truth not in allowed:
                raise LabelError(
                    f"answers.{criterion} must be present, absent, or blank"
                )
            answers[criterion] = truth
        return cls(entrance_id=entrance_id, labeled_by=operator, answers=answers)


def register_labels(
    app: Flask,
    error: Callable[..., tuple[dict[str, object], int]],
) -> None:
    """Register authenticated future-capture label submission on ``app``."""

    client_key = _client_key()
    configured = os.environ.get(PATH_ENV, "").strip()
    app.config.setdefault("LABELS_PATH", Path(configured) if configured else LABELS_PATH)

    @app.post("/labels")
    def labels() -> tuple[dict[str, object], int]:
        if not _authorised(request.headers.get("X-Frontdoor-Upload-Key", ""), client_key):
            return error(
                "label submission not authorised",
                "POST /labels requires the X-Frontdoor-Upload-Key header.",
                status=401,
            )
        # On the DECLARED length, before anything is buffered. Measuring after get_json is
        # measuring an allocation that already happened.
        declared = request.content_length
        if declared is not None and declared > MAX_BODY_BYTES:
            return error(
                "invalid label submission",
                f"POST /labels accepts at most {MAX_BODY_BYTES} bytes; got {declared}.",
                status=413,
            )
        if not request.is_json:
            return error(
                "invalid label submission",
                "POST /labels requires an application/json body.",
                status=415,
            )
        # Repeated on the read, for a chunked body that declares no length.
        raw = request.get_data(cache=True)
        if len(raw) > MAX_BODY_BYTES:
            return error(
                "invalid label submission",
                f"POST /labels accepts at most {MAX_BODY_BYTES} bytes; got {len(raw)}.",
                status=413,
            )
        try:
            submission = LabelSubmission.parse(request.get_json(silent=True))
        except LabelError as exc:
            return error("invalid label submission", str(exc), status=422)

        try:
            sheet = resolve_labels_path(Path(current_app.config["LABELS_PATH"]))
        except LabelsPathRefused as exc:
            current_app.logger.error("refusing to write labels into a checkout: %s", exc)
            return error("could not store labels", str(exc), status=503)

        try:
            created = append_future_entrance_labels(
                sheet,
                submission.entrance_id,
                submission.answers,
                labeled_by=submission.labeled_by,
                labeled_at=date.today(),
            )
        except LabelConflict as exc:
            return error("label already locked", str(exc), status=409)
        except (LabelError, OSError) as exc:
            current_app.logger.exception("could not persist phone labels")
            return error(
                "could not store labels",
                "the label record could not be stored; retry later.",
                status=503,
            )

        return {
            "accepted": True,
            "entrance_id": submission.entrance_id,
            "created": created,
        }, 201 if created else 200
