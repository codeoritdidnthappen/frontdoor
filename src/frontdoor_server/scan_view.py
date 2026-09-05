"""POST /screen/publish and GET /scan/photo/<key>: scan persistence (TICK-262, #270).

/screen stays the assess-only surface: it retains nothing, and a test pins
that no persistence facility is even importable from its module. Publishing is
therefore a SEPARATE endpoint in a separate module — the review-before-publish
gate is the user posting here, explicitly, after seeing the assessment. The
pipeline is the same one /screen runs (face blur -> integrated assessment ->
face_check audit); what differs is only what happens after:

  * Only a request whose face audit answers exactly "clear" persists anything.
    The audit is one answer over ALL the request's views (one integrated call
    cannot attribute a face to a single view — see screen_view), so
    "face_visible" and "unknown" quarantine the request's frames as a set:
    NOTHING is stored, and the response says so honestly
    (published: false, quarantine_reason: face_check, quarantined_count: N).
    The verdicts still stand — assessment already happened; retention is the
    privacy issue — so the caller keeps the assessment it consented to publish.
  * What is stored is the PROCESSED bytes only: faces irreversibly blurred,
    EXIF/GPS stripped, re-encoded JPEG. The raw upload dies with the request
    here exactly as it does on /screen (#243's guarantee, preserved on both
    paths).
  * Storage or record-store failure degrades to 503 assessed-but-not-published
    with the verdicts still in the body — never a silent drop, and never a
    stored image the caller was not told about without the record that would
    put it on the map (an orphaned object is unreferenced bytes; a silent
    "published" that wasn't is a lie on the map).

The scan record goes to the JSONL store (frontdoor.scan_records) that
GET /map/data merges with the pre-catalogue. Object storage reuses the /upload
R2 plumbing: the images bucket credential, ObjectStore, conditional writes.
Keys are scans/<place-slug>/<uuid>.jpg publicly, stored under the open/
partition (community scans are never sealed material). Tests inject a fake
store via app.config[STORE_KEY], the same shape as /screen's engine injection.

GET /scan/photo/<key> streams a stored processed image — the card's receipt
photo. No auth for now: every stored byte is privacy-processed by
construction. The key handling is traversal-proof by allowlist: only a string
matching scan_records.SCAN_IMAGE_KEY_RE (two bounded segments, no dots in the
slug, literal .jpg) resolves at all, so keys under any other prefix — open/
captures, sealed/ anything, ../ — cannot even be expressed.
"""

import os
import time
from datetime import datetime, timezone

from flask import Blueprint, Response, current_app, request

from frontdoor.faceblur import InvalidImageError, process_upload
from frontdoor.scan_records import (
    DEFAULT_SCANS_PATH,
    SCANS_ENV,
    ScanRecordError,
    append_scan,
    is_scan_image_key,
    new_image_key,
    new_scan_record,
    physical_key,
)
from frontdoor.screening import ScreeningError, integrated_summary
from frontdoor.split import InvalidEntranceId, assign_split, canonical_entrance_id
from frontdoor.storage import StorageError, image_store
from frontdoor_server.screen_view import (
    ALLOWED_IMAGE_TYPES,
    MAX_IMAGES,
    WORDING,
    _error,
    _get_engine,
    ada_screening_from_assessment,
)

#: app.config key tests use to inject a fake object store; production leaves
#: it unset and gets the /upload path's image_store() (R2, images credential).
STORE_KEY = "SCAN_STORE"

#: Anonymous contributor token, optional. Opaque and bounded — it is stored in
#: the scan record verbatim, so the charset is an allowlist.
CONTRIBUTOR_HEADER = "X-Frontdoor-Contributor"
_CONTRIBUTOR_MAX = 64

_PLACE_ID_MAX = 128
_NAME_MAX = 200

scan_page = Blueprint("scan_page", __name__)


def _get_store():
    """The injected store, or the real images-bucket store.

    Constructing the real one reads credentials from the environment and
    raises StorageError when missing — callers turn that into the 503
    assessed-but-not-published contract rather than a bare 500.
    """
    store = current_app.config.get(STORE_KEY)
    if store is not None:
        return store
    return image_store()


def _contributor():
    value = request.headers.get(CONTRIBUTOR_HEADER, "").strip()
    if value and len(value) <= _CONTRIBUTOR_MAX and all(
        c.isascii() and (c.isalnum() or c in "._-") for c in value
    ):
        return value
    return None


def _parse_place_ref(form):
    """(place_ref dict, error response). Exactly one of them is None.

    A publish must say WHERE: either a place_id, or coordinates plus a name
    (the same distance+name matching the map's external data uses). Anything
    stored here ends up in a public dataset, so every field is bounded.
    """
    place_id = form.get("place_id", "").strip() or None
    name = form.get("name", "").strip() or None
    lat_raw, lng_raw = form.get("lat"), form.get("lng")

    if place_id is not None and (
        len(place_id) > _PLACE_ID_MAX
        or not all(c.isascii() and (c.isalnum() or c in "._-:") for c in place_id)
    ):
        return None, _error(
            "invalid place_id",
            f"place_id must be at most {_PLACE_ID_MAX} ASCII letters, digits, "
            "or . _ - : characters.",
        )
    if name is not None and len(name) > _NAME_MAX:
        return None, _error(
            "invalid name", f"name must be at most {_NAME_MAX} characters."
        )

    lat = lng = None
    if lat_raw is not None or lng_raw is not None:
        try:
            lat, lng = float(lat_raw), float(lng_raw)
        except (TypeError, ValueError):
            return None, _error(
                "invalid location", "lat and lng must both be decimal degrees."
            )
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return None, _error(
                "invalid location",
                "lat must be within [-90, 90] and lng within [-180, 180].",
            )

    if place_id is None and (lat is None or name is None):
        return None, _error(
            "missing place reference",
            "POST /screen/publish needs a place to publish against: either a "
            "place_id field, or lat + lng + name fields.",
        )

    place_ref = {}
    if place_id is not None:
        place_ref["place_id"] = place_id
    if name is not None:
        place_ref["name"] = name
    if lat is not None:
        place_ref["lat"] = lat
        place_ref["lng"] = lng
    return place_ref, None


def _not_published(body, reason, detail, status=200):
    """The assessed-but-not-published shape: the verdicts stay in the body,
    the reason is named, and non-2xx responses still carry the service's
    error/detail contract for consumers that read nothing else."""
    body["published"] = False
    body["publish_reason"] = reason
    body["publish_detail"] = detail
    if status != 200:
        body["error"] = "scan not published"
        body["detail"] = detail
    return body, status


@scan_page.post("/screen/publish")
def publish():
    files = [f for key in request.files for f in request.files.getlist(key)]
    if not files:
        return _error(
            "missing image",
            "POST /screen/publish expects multipart/form-data with 1-6 image "
            "file parts (image/jpeg, image/png, or image/webp) plus a place "
            "reference (place_id, or lat + lng + name).",
        )
    if len(files) > MAX_IMAGES:
        return _error(
            "too many images",
            f"POST /screen/publish accepts at most {MAX_IMAGES} image parts "
            f"per request; got {len(files)}.",
        )
    for part in files:
        if part.mimetype not in ALLOWED_IMAGE_TYPES:
            return _error(
                "unsupported content type",
                f"file part {part.name!r} has content type {part.mimetype!r}; "
                "/screen/publish accepts image/jpeg, image/png, and image/webp.",
                status=415,
            )

    place_ref, ref_error = _parse_place_ref(request.form)
    if ref_error is not None:
        return ref_error

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

    # Same ingest as /screen: every frame is blurred and EXIF-stripped before
    # anything else touches it; the raw upload is dropped here, on the publish
    # path exactly as on the assess-only path.
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
            payloads.append(processed.image_bytes)
            faces_blurred += processed.face_count

    t0 = time.perf_counter()
    try:
        assessment = engine.assess_images_integrated(
            payloads, media_types=["image/jpeg"] * len(payloads)
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

    try:
        ada_screening = ada_screening_from_assessment(assessment)
    except ScreeningError as exc:
        return _error(
            "screening engine failure",
            str(exc),
            status=502,
            latency_ms=latency_ms,
        )

    # Only an explicit "clear" may persist. The audit answers once for the
    # whole set of views, so anything else quarantines every frame: the
    # request stays assessed (the verdicts below still stand) but nothing is
    # stored — face_visible and unknown frames are NEVER persisted.
    quarantined = assessment.face_check != "clear"
    quarantined_count = len(files) if quarantined else 0

    body = {
        "entrance_id": entrance_id,
        "place_ref": place_ref,
        "mode": "integrated",
        "images": [{"filename": part.filename} for part in files],
        "assessment": {
            "criteria": assessment.criteria,
            "latency_ms": None if assessment.latency_s is None
            else round(assessment.latency_s * 1000),
            "error": assessment.error,
        },
        "latency_ms": latency_ms,
        "faces_blurred": faces_blurred,
        "face_check": assessment.face_check,
        "quarantined": quarantined,
        "quarantined_count": quarantined_count,
        "model": engine.config.model,
        "status": "ai_estimated",
        "wording": WORDING,
        "ada_screening": ada_screening,
    }
    if len(files) > 1:
        body["aggregate"] = {
            key: {
                "verdict": summary.verdict,
                "flip_rate": summary.flip_rate,
                "counts": summary.counts,
            }
            for key, summary in integrated_summary(assessment).items()
        }

    if quarantined:
        body["quarantine_reason"] = "face_check"
        body["image_keys"] = []
        return _not_published(
            body, "face_check",
            "every view was quarantined by the privacy audit "
            f"(face_check: {assessment.face_check}); nothing was stored.",
        )

    # Persist the processed bytes. Conditional writes (if_absent) for the same
    # reason /upload uses them: a uuid key never collides, so an existing
    # object at one of these keys means something is wrong, not something to
    # overwrite.
    try:
        store = _get_store()
    except StorageError as exc:
        body["image_keys"] = []
        return _not_published(
            body, "storage_unavailable",
            f"object storage is not available ({exc}); the assessment stands "
            "but nothing was published. Retry once storage is configured.",
            status=503,
        )
    image_keys = []
    for processed_bytes in payloads:
        key = new_image_key(place_ref)
        try:
            store.put(physical_key(key), processed_bytes, if_absent=True)
        except StorageError as exc:
            body["image_keys"] = []
            return _not_published(
                body, "storage_unavailable",
                f"storing image {len(image_keys) + 1} of {len(payloads)} "
                f"failed ({exc}); no scan record was written, so nothing was "
                "published. The assessment stands; retry to publish.",
                status=503,
            )
        image_keys.append(key)

    record = new_scan_record(
        place_ref=place_ref,
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        verdicts={
            key: entry.get("verdict")
            for key, entry in assessment.criteria.items()
        },
        confidences={
            key: entry.get("confidence")
            for key, entry in assessment.criteria.items()
        },
        faces_blurred=faces_blurred,
        quarantined_count=0,
        image_keys=image_keys,
        contributor=_contributor(),
        entrance_id=entrance_id,
    )
    try:
        append_scan(os.environ.get(SCANS_ENV, DEFAULT_SCANS_PATH), record)
    except (ScanRecordError, OSError) as exc:
        body["image_keys"] = []
        return _not_published(
            body, "record_store_unavailable",
            f"the scan record could not be written ({exc}); the stored images "
            "are unreferenced and nothing reached the map. The assessment "
            "stands; retry to publish.",
            status=503,
        )

    current_app.logger.info(
        "published scan %s (%d images) for %s",
        record["scan_id"], len(image_keys), place_ref,
    )
    body["published"] = True
    body["scan_id"] = record["scan_id"]
    body["created_at"] = record["created_at"]
    body["image_keys"] = image_keys
    return body, 200


@scan_page.get("/scan/photo/<path:image_key>")
def scan_photo(image_key):
    """The receipt photo: stream one stored processed image.

    Only a key matching the scans/ allowlist resolves; everything else — a
    capture key, a sealed key, any traversal spelling — is the same 404, and
    storage is never asked about it.
    """
    if not is_scan_image_key(image_key):
        return _error(
            "no such scan photo",
            "scan photo keys look like scans/<place>/<id>.jpg.",
            status=404,
        )
    try:
        store = _get_store()
    except StorageError as exc:
        return _error("scan photos unavailable", str(exc), status=503)
    try:
        image_bytes = store.get(physical_key(image_key))
    except StorageError as exc:
        if "NoSuchKey" in str(exc) or "404" in str(exc):
            return _error(
                "no such scan photo", f"nothing is stored at {image_key}.",
                status=404,
            )
        return _error("scan photos unavailable", str(exc), status=503)
    response = Response(image_bytes, mimetype="image/jpeg")
    # Immutable by construction: the key embeds a uuid and writes are
    # conditional, so a stored photo never changes under its key.
    response.headers["Cache-Control"] = "public, max-age=86400, immutable"
    return response
