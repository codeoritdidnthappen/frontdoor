"""POST /labels: one entrance's four human presence labels, from the phone (TICK-282, #309).

Ground truth for entrances captured after the 2026-09-04 closeout. The frozen 53 belong to #302
and its Mac workflow; nothing here touches them.

Two properties matter more than the plumbing.

**The labels are recorded once.** A repeat of the identical submission is a success -- a phone
whose acknowledgement was lost must be able to stop -- but a submission that disagrees with what
is already recorded is refused as locked, and refused permanently rather than retried. Human
ground truth that can be revised after the model's verdicts are known is not ground truth, which
is also why the labeling screen on the phone never shows a verdict.

**The server owns `labeled_at`.** A phone's clock is settable, and a date the phone chose would be
a claim about when the operator looked at a doorway that nobody could check.

v1 storage is the CSV inside the application container. That is deliberate and it is ephemeral:
replacing or redeploying the container loses runtime rows. Persistent storage is out of scope for
this ticket and is stated in the docs rather than implied by silence.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import request

from frontdoor.labels import (
    ALLOWED_TRUTHS,
    APPEND_IDENTICAL,
    CRITERIA_KEYS,
    LABELED_BY_MAX,
    LabelError,
    LabelsLocked,
    append_entrance_labels,
)
from frontdoor.split import InvalidEntranceId

#: Refused above this. Four criteria and a name is a few hundred bytes; anything larger is a
#: client bug or someone probing, and neither should reach the CSV.
MAX_BODY_BYTES = 8 * 1024

#: Where the runtime CSV lives. Overridable so tests do not write into the repository, and so a
#: deployment can point it at a mounted path the day one exists.
PATH_ENV = "FRONTDOOR_LABELS_PATH"
DEFAULT_PATH = Path("data/labels.csv")


def labels_path():
    configured = os.environ.get(PATH_ENV, "").strip()
    return Path(configured) if configured else DEFAULT_PATH


def _today():
    """UTC, so the recorded date does not depend on the container's timezone."""
    return datetime.now(timezone.utc).date()


def register_labels(app, error, authorised, client_key):
    """Register POST /labels on `app`.

    `authorised` and `client_key` come from the upload view rather than being re-derived, so the
    two write endpoints cannot drift into different notions of who may write -- and so there is
    one constant-time comparison, not a second one someone might implement with `==`.
    """

    @app.post("/labels")
    def submit_labels():
        if not authorised(request.headers.get("X-Frontdoor-Upload-Key", ""), client_key):
            return error(
                "labels not authorised",
                "POST /labels requires the X-Frontdoor-Upload-Key header.",
                status=401,
            )

        # Read once, then parse what was read. `cache=False` here consumed the stream and left
        # `get_json` with nothing, so every well-formed submission came back "not valid JSON".
        raw = request.get_data(cache=True)
        if len(raw) > MAX_BODY_BYTES:
            return error(
                "request body too large",
                f"POST /labels accepts at most {MAX_BODY_BYTES} bytes; got {len(raw)}.",
                status=413,
            )
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            body = None
        if not isinstance(body, dict):
            return error(
                "labels are not valid JSON",
                "POST /labels expects a JSON object with entrance_id, labeled_by and answers.",
            )

        answers = body.get("answers")
        if not isinstance(answers, dict):
            return error(
                "labels failed validation",
                f"answers must be an object with one truth for each of "
                f"{', '.join(CRITERIA_KEYS)}.",
                field="answers",
            )

        try:
            outcome = append_entrance_labels(
                labels_path(),
                body.get("entrance_id", ""),
                answers,
                labeled_by=body.get("labeled_by", ""),
                labeled_at=_today(),
            )
        except InvalidEntranceId as exc:
            return error("invalid entrance_id", str(exc), field="entrance_id")
        except LabelsLocked as exc:
            # 409, and named so the phone can stop rather than retrying forever. This is the one
            # failure on this endpoint that a retry can never clear.
            return error("labels already recorded", str(exc), status=409)
        except LabelError as exc:
            return error("labels failed validation", str(exc))

        return {
            "entrance_id": body.get("entrance_id", "").strip().upper(),
            "criteria": list(CRITERIA_KEYS),
            "accepted": True,
            # Stated so a client can tell a first acceptance from a replayed one without
            # comparing rows it cannot see.
            "idempotent": outcome == APPEND_IDENTICAL,
            "allowed_truths": [*ALLOWED_TRUTHS, ""],
            "labeled_by_max": LABELED_BY_MAX,
        }, 200
