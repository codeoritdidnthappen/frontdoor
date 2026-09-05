"""POST /labels -- future-capture human ground truth from the phone (TICK-282)."""

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
    app.config.setdefault("LABELS_PATH", LABELS_PATH)

    @app.post("/labels")
    def labels() -> tuple[dict[str, object], int]:
        if not _authorised(request.headers.get("X-Frontdoor-Upload-Key", ""), client_key):
            return error(
                "label submission not authorised",
                "POST /labels requires the X-Frontdoor-Upload-Key header.",
                status=401,
            )
        if not request.is_json:
            return error(
                "invalid label submission",
                "POST /labels requires an application/json body.",
                status=415,
            )
        try:
            submission = LabelSubmission.parse(request.get_json(silent=True))
        except LabelError as exc:
            return error("invalid label submission", str(exc), status=422)

        try:
            created = append_future_entrance_labels(
                Path(current_app.config["LABELS_PATH"]),
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
