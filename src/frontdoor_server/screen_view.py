"""POST /screen: photo-upload ADA feature screening (TICK-245).

A thin entrypoint over frontdoor.screening: upload 1-6 entrance photos, get
back per-image, per-criterion screening verdicts and (for multiple views) the
majority aggregate with its flip-rate. The honesty rule carries through to the
response wording: verdicts are statements about what is visible in the photos,
never measurements and never compliance determinations.

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
an image the model says still shows an identifiable face is QUARANTINED. Its
verdicts still count toward the aggregate - the model has already seen the
blurred image, so the privacy issue is retention, not assessment - but the
response marks it {"quarantined": true, "reason": "face_check"} and reports
the total under "quarantined_views". Retention guarantee: this endpoint holds
image bytes in request-scoped locals only. Nothing here writes them to disk,
object storage, or any other store (pinned by test_screen_endpoint), so a
quarantined image needs no deletion step - its bytes die with the request.
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from importlib import resources

from flask import Blueprint, Response, current_app, request

from frontdoor.faceblur import process_upload
from frontdoor.screening import ScreeningEngine, aggregate_assessments
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


def _error(message, detail, status=400):
    """Same error shape as the rest of the service: stable token + bounded detail."""
    text = detail if isinstance(detail, str) else str(detail)
    if len(text) > DETAIL_MAX_LENGTH:
        text = text[: DETAIL_MAX_LENGTH - len(_DETAIL_ELLIPSIS)] + _DETAIL_ELLIPSIS
    return {"error": message, "detail": text}, status


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
    laptop, carry the demo UI with them. The page holds no logic: verdicts, the
    aggregate and the flip rate are computed here in Python and rendered there.
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
    # what was posted. Bytes no decoder accepts pass through unchanged: they hold no
    # renderable face, and the engine will name the failure on that image itself.
    payloads = []
    faces_blurred = 0
    for part in files:
        raw = part.read()
        try:
            processed = process_upload(raw)
        except ValueError:
            payloads.append((raw, part.mimetype))
        else:
            payloads.append((processed.image_bytes, "image/jpeg"))
            faces_blurred += processed.face_count

    t0 = time.perf_counter()
    try:
        # Concurrently, because these are independent network calls and the demo is timed.
        # One view took 13.5s against the live model, so a six-view entrance run in series is
        # over a minute of dead air against the 2.5-minute technical-demo budget in
        # docs/deck-outline.md. Nothing about the verdicts or the aggregate changes; only the
        # waiting overlaps.
        #
        # `.map` preserves input order, which the response depends on: `images[i]` must be
        # `files[i]`, and zip below pairs them positionally. The engine books its spend under
        # a lock so the cap still holds with several calls in flight.
        with ThreadPoolExecutor(max_workers=min(len(payloads), MAX_IMAGES)) as pool:
            assessments = list(pool.map(
                lambda payload: engine.assess_image(payload[0], media_type=payload[1]),
                payloads,
            ))
    except Exception as exc:
        # assess_image records per-image failures itself; anything that still
        # escapes (spend cap, an injected engine blowing up) is an upstream
        # engine failure, named, not a bare 500.
        return _error(
            "screening engine failure", f"{type(exc).__name__}: {exc}", status=502
        )
    latency_ms = round((time.perf_counter() - t0) * 1000)

    if all(a.criteria is None for a in assessments):
        named = "; ".join(a.error or "unknown error" for a in assessments)
        return _error(
            "screening engine failure",
            f"every image assessment failed: {named}",
            status=502,
        )

    # face_check quarantine (TICK-257 follow-up, #232): the model has audited its
    # own (already blurred) input. A face_visible image is marked quarantined; its
    # verdicts still aggregate (assessment already happened - retention is the
    # privacy issue), and because this endpoint never persists image bytes anywhere
    # (see the module docstring), marking it is the whole quarantine.
    images = []
    for part, a in zip(files, assessments):
        entry = {
            "filename": part.filename,
            "criteria": a.criteria,
            "latency_ms": None if a.latency_s is None else round(a.latency_s * 1000),
            "error": a.error,
            "quarantined": a.face_check == "face_visible",
        }
        if entry["quarantined"]:
            entry["reason"] = "face_check"
        images.append(entry)

    body = {
        "entrance_id": entrance_id,
        "images": images,
        "latency_ms": latency_ms,
        "faces_blurred": faces_blurred,
        "quarantined_views": sum(1 for entry in images if entry["quarantined"]),
        "model": engine.config.model,
        "status": "ai_estimated",
        "wording": WORDING,
    }
    if len(assessments) > 1:
        body["aggregate"] = {
            key: {
                "verdict": summary.verdict,
                "flip_rate": summary.flip_rate,
                "counts": summary.counts,
            }
            for key, summary in aggregate_assessments(assessments).items()
        }
    return body, 200
