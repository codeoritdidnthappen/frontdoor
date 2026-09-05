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
    LabelsUnreadable,
    append_entrance_labels,
)
from frontdoor.split import InvalidEntranceId, canonical_entrance_id

#: Refused above this. Four criteria and a name is a few hundred bytes; anything larger is a
#: client bug or someone probing, and neither should reach the CSV.
MAX_BODY_BYTES = 8 * 1024

#: Where the runtime CSV lives. Overridable so tests do not write into the repository, and so a
#: deployment can point it at a mounted path the day one exists.
PATH_ENV = "FRONTDOOR_LABELS_PATH"
DEFAULT_PATH = Path("data/labels.csv")


class LabelsPathRefused(Exception):
    """The default path resolves inside a git checkout, so writing it would dirty the tree."""


def _inside_a_git_checkout(path):
    """Is this path within a working tree? Walks up looking for `.git`.

    The container copies only `pyproject.toml` and `src`, so there `data/labels.csv` is a fresh
    file and this never fires. It fires exactly where the hazard is: a server started from a
    checkout, where `data/labels.csv` is the committed 212-row template.
    """
    for parent in [path.resolve(), *path.resolve().parents]:
        if (parent / ".git").exists():
            return True
    return False


def labels_path():
    """The sheet to append to, refusing the one case that costs more than it looks.

    An append rewrites the whole sheet, so a single request against a server started from a
    checkout modifies a tracked file. Nothing breaks immediately -- and then the freeze-day run
    refuses to start, because `record_unsealing` aborts on a dirty working tree, and the reason is
    a file nobody remembers touching.
    """
    configured = os.environ.get(PATH_ENV, "").strip()
    if configured:
        return Path(configured)
    if _inside_a_git_checkout(DEFAULT_PATH):
        raise LabelsPathRefused(
            f"{DEFAULT_PATH} is inside a git checkout, and appending rewrites the whole sheet -- "
            f"which would modify a tracked file and abort the sealed run on a dirty tree. Set "
            f"{PATH_ENV} to a path outside the repository."
        )
    return DEFAULT_PATH


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

        # Checked on the declared length FIRST, before anything is buffered. The app's
        # MAX_CONTENT_LENGTH is 64 MB, so reading and then measuring let a single request
        # allocate 64 MB on a 512 MB machine that #233 already measured OOM-killing at 186 MB.
        declared = request.content_length
        if declared is not None and declared > MAX_BODY_BYTES:
            return error(
                "request body too large",
                f"POST /labels accepts at most {MAX_BODY_BYTES} bytes; got {declared}.",
                status=413,
            )
        # Read once, then parse what was read. `cache=False` here consumed the stream and left
        # `get_json` with nothing, so every well-formed submission came back "not valid JSON".
        # The length check repeats for a chunked body, which declares nothing.
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
            # Canonicalised here so the response can echo the id that was actually written,
            # rather than a second spelling of the rule that agrees with it most of the time.
            entrance_id = canonical_entrance_id(body.get("entrance_id", ""))
        except InvalidEntranceId as exc:
            return error("invalid entrance_id", str(exc), field="entrance_id")

        try:
            path = labels_path()
        except LabelsPathRefused as exc:
            return error("internal error", str(exc), status=500)

        try:
            outcome = append_entrance_labels(
                path,
                entrance_id,
                answers,
                labeled_by=body.get("labeled_by", ""),
                labeled_at=_today(),
            )
        except LabelsUnreadable as exc:
            # The server's own sheet is malformed. Reporting that as failed validation would tell
            # the phone its answers were bad and invite it to throw them away.
            return error("internal error", str(exc), status=500)
        except LabelsLocked as exc:
            # 409, and named so the phone can stop rather than retrying forever. This is the one
            # failure on this endpoint that a retry can never clear.
            return error("labels already recorded", str(exc), status=409)
        except LabelError as exc:
            return error("labels failed validation", str(exc))

        return {
            "entrance_id": entrance_id,
            "criteria": list(CRITERIA_KEYS),
            "accepted": True,
            # Stated so a client can tell a first acceptance from a replayed one without
            # comparing rows it cannot see.
            "idempotent": outcome == APPEND_IDENTICAL,
            "allowed_truths": [*ALLOWED_TRUTHS, ""],
            "labeled_by_max": LABELED_BY_MAX,
        }, 200
