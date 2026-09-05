"""POST /screen: photo-upload ADA feature screening (TICK-245).

A thin entrypoint over frontdoor.screening: upload 1-6 photos of one
entrance, get back one integrated per-criterion screening result. All views
go into a single model call that weighs them together (offline eval on the
12-entrance pilot set: more accurate than per-image majority voting, and one
call is faster than N). The honesty rule carries through to the response
wording: verdicts are statements about what is visible in the photos, never
measurements and never compliance determinations.

Split discipline (D-007) is mirrored here: an entrance_id, when supplied, is
canonicalized and its split resolved before the engine is touched; a
sealed-split entrance is refused with 403, the HTTP twin of SealedSplitError.

The engine is constructed lazily on first use, so the server boots (and every
other endpoint works) without an API key; a keyless /screen request gets a
clear 503 rather than a crash. Tests inject a fake engine via app.config.

Uploads pass through the face-blur ingest step (frontdoor.faceblur, TICK-257)
before the engine sees them: faces irreversibly blurred, EXIF GPS stripped,
and the response reports the total under "faces_blurred".

The model then audits the blur itself (face_check, the TICK-257 follow-up):
the integrated call answers one privacy question over all its views, and a
face_visible answer QUARANTINES the request's views as a set - one call over
all views cannot attribute the face to a single view. The response reports
the audit's answer verbatim under "face_check": "clear" (the model checked
and saw no face), "face_visible", or "unknown" (the model never produced an
answer - PR #243 review: "checked, clear" and "never answered" are different
facts and a consumer must be able to tell them apart). Anything except an
explicit clear quarantines. The verdicts still
stand - the model has already seen the blurred images, so the privacy issue
is retention, not assessment - but the response marks the result
{"quarantined": true, "quarantine_reason": "face_check"}. Retention
guarantee: this endpoint holds image bytes in request-scoped locals only.
Nothing here writes them to disk, object storage, or any other store (pinned
by test_screen_endpoint), so a quarantined image needs no deletion step - its
bytes die with the request.
"""

import os
import time
from importlib import resources

from flask import Blueprint, Response, current_app, request

from frontdoor.faceblur import InvalidImageError, process_upload
from frontdoor.screening import ScreeningEngine, integrated_summary
from frontdoor.split import InvalidEntranceId, assign_split, canonical_entrance_id

ALLOWED_IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")
MAX_IMAGES = 6

#: app.config key tests use to inject a fake engine; production leaves it unset.
ENGINE_KEY = "SCREEN_ENGINE"

WORDING = (
    "Screening statements about accessibility features visible in the "
    "submitted photos. Not measurements, and not compliance or legal "
    "determinations of any kind."
)

DETAIL_MAX_LENGTH = 256
_DETAIL_ELLIPSIS = "..."

screen_page = Blueprint("screen_page", __name__)


def _error(message, detail, status=400, *, latency_ms=None):
    """Same error shape as the rest of the service: stable token + bounded detail."""
    text = detail if isinstance(detail, str) else str(detail)
    if len(text) > DETAIL_MAX_LENGTH:
        text = text[: DETAIL_MAX_LENGTH - len(_DETAIL_ELLIPSIS)] + _DETAIL_ELLIPSIS
    body = {"error": message, "detail": text}
    if latency_ms is not None:
        body["latency_ms"] = latency_ms
    return body, status


def _get_engine():
    """Return the injected engine, a fresh real one, or None when keyless.

    A fresh engine per request keeps the spend cap per-run semantics honest:
    one upload is one run.
    """
    engine = current_app.config.get(ENGINE_KEY)
    if engine is not None:
        return engine
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return None
    return ScreeningEngine()


@screen_page.get("/screen")
def screen_html():
    """The laptop surface for the Demo Day technical demo (deck-outline.md section 6).

    Served by the same image that answers the POST, so the page on stage is the page
    that was tested -- and so D-016's fallback steps, which run this container on a
    laptop, carry the demo UI with them. The page holds no logic: the integrated
    verdicts are computed here in Python and rendered there.
    """
    html = (
        resources.files("frontdoor_server")
        .joinpath("screen.html")
        .read_text(encoding="utf-8")
    )
    return Response(html, mimetype="text/html")


@screen_page.post("/screen")
def screen():
    files = [f for key in request.files for f in request.files.getlist(key)]
    if not files:
        return _error(
            "missing image",
            "POST /screen expects multipart/form-data with 1-6 image file "
            "parts (image/jpeg, image/png, or image/webp).",
        )
    if len(files) > MAX_IMAGES:
        return _error(
            "too many images",
            f"POST /screen accepts at most {MAX_IMAGES} image parts per "
            f"request; got {len(files)}.",
        )
    for part in files:
        if part.mimetype not in ALLOWED_IMAGE_TYPES:
            return _error(
                "unsupported content type",
                f"file part {part.name!r} has content type {part.mimetype!r}; "
                "/screen accepts image/jpeg, image/png, and image/webp.",
                status=415,
            )

    entrance_id = request.form.get("entrance_id")
    if entrance_id is not None:
        try:
            entrance_id = canonical_entrance_id(entrance_id)
        except InvalidEntranceId as exc:
            return _error("invalid entrance_id", str(exc))
        if assign_split(entrance_id) == "sealed":
            return _error(
                "sealed entrance",
                f"entrance {entrance_id} is in the sealed split; the sealed "
                "split is evaluated exactly once at results freeze, not "
                "through this endpoint.",
                status=403,
            )

    engine = _get_engine()
    if engine is None:
        return _error(
            "screening unavailable",
            "ANTHROPIC_API_KEY is not set on the server, so the screening "
            "engine cannot call the model. Set the key and retry.",
            status=503,
        )

    # Read on this thread, before dispatching: the bytes are what the model call needs, and
    # pulling them here keeps the worker threads to one job each.
    #
    # Every image passes through the face-blur ingest step (TICK-257, #232) BEFORE anything
    # sees it - faces irreversibly blurred, EXIF/GPS stripped - so the model call and any
    # later storage only ever handle the processed bytes; the raw upload is dropped here.
    # Processed images are re-encoded JPEG, so their media type is image/jpeg regardless of
    # what was posted. Invalid image bytes are a request error. An unexpected detector error
    # becomes the service's bounded 500. Both outcomes fail closed: neither can cross the
    # model boundary as an unblurred original (TICK-257 AC1/AC2, QA TICK-B01).
    payloads = []
    faces_blurred = 0
    for part in files:
        raw = part.read()
        try:
            processed = process_upload(raw)
        except InvalidImageError:
            return _error(
                "invalid image",
                f"file part {part.name!r} could not be decoded and privacy-processed.",
                status=422,
            )
        else:
            payloads.append((processed.image_bytes, "image/jpeg"))
            faces_blurred += processed.face_count

    t0 = time.perf_counter()
    try:
        # One integrated model call over ALL views of the entrance, replacing one call per
        # view. Offline eval on the 12-entrance pilot set showed per-image majority voting
        # amplifies shared camera-position blind spots (a frontal frame hides the ground
        # plane), while the integrated call lets the one view that shows the relevant area
        # settle the verdict -- and it is faster than N calls, which the timed demo cares
        # about. `assess_images_integrated` records refusals and parse failures in the
        # returned assessment itself; anything that still escapes (spend cap, an injected
        # engine blowing up) is an upstream engine failure, named, not a bare 500.
        assessment = engine.assess_images_integrated(
            [image for image, _ in payloads],
            media_types=[media_type for _, media_type in payloads],
        )
    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000)
        return _error(
            "screening engine failure",
            f"{type(exc).__name__}: {exc}",
            status=502,
            latency_ms=latency_ms,
        )
    latency_ms = round((time.perf_counter() - t0) * 1000)

    if assessment.criteria is None:
        return _error(
            "screening engine failure",
            f"the integrated assessment failed: {assessment.error or 'unknown error'}",
            status=502,
            latency_ms=latency_ms,
        )

    # face_check quarantine (TICK-257 follow-up, #232): the model has audited its
    # own (already blurred) input inside the same integrated call. A face_visible
    # answer quarantines the request's views as a set - one call over all views
    # cannot attribute the face to a single view. The verdicts still stand
    # (assessment already happened - retention is the privacy issue), and because
    # this endpoint never persists image bytes anywhere (see the module
    # docstring), marking the response is the whole quarantine. The answer
    # itself is reported below: "unknown" (the audit never produced an answer)
    # is a different fact from "clear" and fails closed into quarantine.
    quarantined = assessment.face_check != "clear"

    body = {
        "entrance_id": entrance_id,
        # The mode is stated so a consumer can tell "the views agreed" from "no
        # cross-view comparison was made".
        "mode": "integrated",
        # Filenames only: the assessment is integrated across the views, so there are no
        # per-image verdicts to attach here.
        "images": [{"filename": part.filename} for part in files],
        "assessment": {
            "criteria": assessment.criteria,
            "latency_ms": None if assessment.latency_s is None
            else round(assessment.latency_s * 1000),
            "error": assessment.error,
        },
        "latency_ms": latency_ms,
        "faces_blurred": faces_blurred,
        # The privacy audit's answer as validated: clear, face_visible, or
        # unknown - so a consumer can tell a checked-clear from a check that
        # never produced an answer (PR #243 review).
        "face_check": assessment.face_check,
        "quarantined": quarantined,
        "model": engine.config.model,
        "status": "ai_estimated",
        "wording": WORDING,
    }
    if quarantined:
        body["quarantine_reason"] = "face_check"
    if len(files) > 1:
        # Kept for consumers that read the entrance-level verdict here: the integrated
        # verdicts. flip_rate and counts are null in integrated mode -- one call over
        # all views makes no cross-view comparison, and reporting a fabricated 0.0 (or
        # counts of 1 for a 6-view entrance) would dress up "no measurement was made"
        # as "all views agreed".
        body["aggregate"] = {
            key: {
                "verdict": summary.verdict,
                "flip_rate": summary.flip_rate,
                "counts": summary.counts,
            }
            for key, summary in integrated_summary(assessment).items()
        }
    return body, 200
