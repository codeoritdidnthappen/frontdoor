"""POST /correct and GET /correct/mine: the correction queue (TICK-387, #387).

The place card's "Suggest a correction" sheet used to end at
``corrections.unshift({...})`` -- a JavaScript array in one browser. The note
appeared in the person's own Contributions tab, which made it look received,
and it died when they closed the tab. This is the endpoint behind the button.

The contract, stated precisely because the failure modes are the point:

  * ``POST /correct`` takes a place reference (place_id, or lat + lng + name --
    the same shape /screen/publish takes), a category from the sheet's four, a
    note capped where the sheet caps it, an optional photo, an optional
    entrance_id, and the same ``X-Frontdoor-Contributor`` header the scan path
    uses. It answers ``201 {received: true, correction_id, status}``.
  * A photo goes through ``frontdoor.faceblur.process_upload`` -- the module's
    one public entry point, unmodified -- BEFORE anything is written. Bytes
    that cannot be processed are not stored in a degraded form and are not
    quietly dropped either: the request fails and NOTHING persists, note
    included. Fail-closed, and the person is told, because a correction whose
    photo silently vanished is the same lie in a smaller font.
  * Storage or record-store failure is a 503 that says the correction was NOT
    received. A note is never written without the photo the person attached to
    it. The one asymmetry, the same one /screen/publish accepts: if the record
    append fails after the object was stored, the processed bytes are left in
    the bucket unreferenced. Unreferenced privacy-processed bytes are a tidying
    problem; a note in a queue whose photo was never kept would be a lie to the
    person who attached it.
  * Nothing here writes a verdict. The record is queue material; the only
    thing a correction can ever change on the map is freshness, and that
    happens in ``frontdoor.corrections.apply_relook`` under a corroboration
    rule, computed at read time by /map/data.
  * Sealed entrances are refused (403) before the photo is read or
    privacy-processed, and before anything is stored, exactly as
    /screen/publish refuses them.

``GET /correct/mine`` answers with the caller's OWN corrections and their real
status, so the app's Contributions tab shows what the server holds rather than
a local echo of a button press. The contributor token is the only identity
this service has for an anonymous reporter; it is required, and a record is
returned only to the token that wrote it.

No CORS: /correct is called by the page this same server serves at /app, so
the request is same-origin and the browser never asks. The screening routes
are cross-origin surfaces and are the only ones in the after_request hook's
scope; widening it for this route would open a public write path to origins
that have no reason to reach it.
"""

import json
import os
from pathlib import Path

from flask import Blueprint, current_app, request

from frontdoor.corrections import (
    CATEGORIES,
    CORRECTIONS_ENV,
    DEFAULT_CORRECTIONS_PATH,
    MAX_PER_CONTRIBUTOR,
    NOTE_MAX,
    SCOPE_OTHER_ENTRANCE,
    SCOPE_THIS_ENTRANCE,
    CorrectionError,
    append_correction,
    corrections_for_contributor,
    load_correction_store,
    new_correction_record,
    new_image_key,
    now_iso,
    physical_key,
    place_key_for_ref,
    place_tier,
    public_correction_view,
)
from frontdoor.faceblur import FaceDetectorError, InvalidImageError, process_upload
from frontdoor.scan_records import (
    DEFAULT_SCANS_PATH,
    SCANS_ENV,
    load_scan_records,
    merge_scans,
)
from frontdoor.split import InvalidEntranceId, assign_split, canonical_entrance_id
from frontdoor.storage import StorageError, image_store
from frontdoor_server.map_view import DATASET_ENV, DEFAULT_DATASET_PATH
from frontdoor_server.scan_view import CONTRIBUTOR_HEADER, _contributor
from frontdoor_server.screen_view import ALLOWED_IMAGE_TYPES, _error, _json_not_multipart

#: app.config key tests use to inject a fake object store, same shape as the
#: scan path's STORE_KEY; production leaves it unset and gets image_store().
STORE_KEY = "CORRECTION_STORE"

_PLACE_ID_MAX = 128
_NAME_MAX = 200

#: What the sheet's <select> sends, mapped to the stored vocabulary. The wire
#: accepts the stored tokens too, so a non-browser client is not forced to
#: know the sheet's wording.
_CATEGORY_ALIASES = {
    "entrance features": "entrance_features",
    "business name or location": "business_identity",
    "photo issue": "photo_issue",
    "something else": "other",
}
_SCOPE_ALIASES = {
    "this entrance": SCOPE_THIS_ENTRANCE,
    "a different entrance of this business": SCOPE_OTHER_ENTRANCE,
}

correct_page = Blueprint("correct_page", __name__)


def _get_store():
    store = current_app.config.get(STORE_KEY)
    if store is not None:
        return store
    return image_store()


def _corrections_path():
    return os.environ.get(CORRECTIONS_ENV, DEFAULT_CORRECTIONS_PATH)


def _merged_dataset():
    """The dataset /map/data serves: the pre-catalogue merged with scans.

    Read here so the tier a correction is filed against -- and therefore
    whether it is a dispute -- is the server's own answer about the pin, not
    a claim the caller made about it.
    """
    path = Path(os.environ.get(DATASET_ENV, DEFAULT_DATASET_PATH))
    try:
        dataset = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        dataset = {}
    scans = load_scan_records(os.environ.get(SCANS_ENV, DEFAULT_SCANS_PATH))
    merged, _ = merge_scans(dataset, scans)
    return merged


def _parse_place_ref(form):
    """(place_ref, error). Exactly one is None. Same contract as the publish path."""
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
            "POST /correct needs a place to correct: either a place_id field, "
            "or lat + lng + name fields.",
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


def _normalise(value, aliases, allowed):
    text = (value or "").strip()
    key = text.lower()
    if key in aliases:
        return aliases[key]
    return text if text in allowed else None


@correct_page.post("/correct")
def correct():
    refused = _json_not_multipart(
        "POST /correct",
        "the optional photo travels in the same request as the place reference.",
    )
    if refused is not None:
        return refused

    place_ref, ref_error = _parse_place_ref(request.form)
    if ref_error is not None:
        return ref_error

    category = _normalise(request.form.get("category"), _CATEGORY_ALIASES, CATEGORIES)
    if category is None:
        return _error(
            "invalid category",
            "category must be one of " + ", ".join(CATEGORIES) + ".",
            status=422,
        )
    scope = _normalise(
        request.form.get("scope") or SCOPE_THIS_ENTRANCE,
        _SCOPE_ALIASES,
        (SCOPE_THIS_ENTRANCE, SCOPE_OTHER_ENTRANCE),
    )
    if scope is None:
        return _error(
            "invalid scope",
            f"scope must be {SCOPE_THIS_ENTRANCE} or {SCOPE_OTHER_ENTRANCE}.",
            status=422,
        )

    note = (request.form.get("note") or "").strip()
    if len(note) > NOTE_MAX:
        return _error(
            "note too long",
            f"a correction note is at most {NOTE_MAX} characters; got {len(note)}.",
            status=422,
        )

    files = [f for key in request.files for f in request.files.getlist(key)]
    if len(files) > 1:
        return _error(
            "too many images",
            "a correction carries at most one photo.",
        )
    photo = files[0] if files else None
    if photo is not None and photo.mimetype not in ALLOWED_IMAGE_TYPES:
        return _error(
            "unsupported content type",
            f"file part {photo.name!r} has content type {photo.mimetype!r}; "
            "/correct accepts image/jpeg, image/png, and image/webp.",
            status=415,
        )

    # The same gate the sheet applies, applied where it counts: a correction
    # with neither an observation nor a photograph is a category and nothing
    # to review, and every correction becomes a line on somebody's evidence
    # receipt.
    if not note and photo is None:
        return _error(
            "empty correction",
            "a correction needs a note or a photo, so there is something to review.",
            status=422,
        )

    entrance_id = request.form.get("entrance_id")
    if entrance_id is not None and entrance_id.strip():
        try:
            entrance_id = canonical_entrance_id(entrance_id)
        except InvalidEntranceId as exc:
            return _error("invalid entrance_id", str(exc))
        if assign_split(entrance_id) == "sealed":
            # Refused before the photo is read or processed, for the same
            # reason the publish path refuses it: the sealed split is evaluated
            # once,
            # at results freeze, and a correction against it is a channel for
            # information about a sealed doorway to reach the project early.
            return _error(
                "sealed entrance",
                f"entrance {entrance_id} is in the sealed split; the sealed "
                "split is evaluated exactly once at results freeze, not "
                "through this endpoint.",
                status=403,
            )
    else:
        entrance_id = None

    # Privacy first: faces blurred, EXIF/GPS stripped, re-encoded, BEFORE
    # anything is written anywhere. The raw upload dies with the request.
    image_bytes = None
    faces_blurred = 0
    blur_regions = None
    if photo is not None:
        raw = photo.read()
        try:
            processed = process_upload(raw)
        except InvalidImageError:
            return _error(
                "invalid image",
                f"file part {photo.name!r} could not be decoded and "
                "privacy-processed, so nothing was stored and the correction "
                "was not received. Retake or attach a different photo.",
                status=422,
            )
        except FaceDetectorError:
            # Fail-closed: the detector did not answer, so nobody can say the
            # faces are blurred. Nothing is stored and nothing is recorded.
            return _error(
                "internal error",
                "face detection did not return a result, so the photo could "
                "not be privacy-processed. Nothing was stored and the "
                "correction was not received.",
                status=500,
            )
        image_bytes = processed.image_bytes
        faces_blurred = processed.face_count
        blur_regions = list(processed.blur_regions)

    dataset = _merged_dataset()
    place_key = place_key_for_ref(dataset, place_ref)
    tier = place_tier(dataset.get(place_key))

    image_key = None
    if image_bytes is not None:
        try:
            store = _get_store()
        except StorageError as exc:
            return _error(
                "correction not received",
                f"object storage is not available ({exc}), so the photo could "
                "not be kept and nothing was written. Retry.",
                status=503,
            )
        image_key = new_image_key(place_ref)
        try:
            store.put(physical_key(image_key), image_bytes, if_absent=True)
        except (StorageError, CorrectionError) as exc:
            return _error(
                "correction not received",
                f"the photo could not be stored ({exc}); no correction was "
                "written. Retry.",
                status=503,
            )

    record = new_correction_record(
        place_ref=place_ref,
        place_key=place_key,
        tier=tier,
        category=category,
        scope=scope,
        note=note,
        created_at=now_iso(),
        entrance_id=entrance_id,
        contributor=_contributor(),
        image_key=image_key,
        faces_blurred=faces_blurred,
        blur_regions=blur_regions,
    )
    try:
        append_correction(_corrections_path(), record)
    except (CorrectionError, OSError) as exc:
        return _error(
            "correction not received",
            f"the correction could not be written ({exc}); nothing reached the "
            "review queue. Retry.",
            status=503,
        )

    current_app.logger.info(
        "correction %s received (%s%s) for %s",
        record["correction_id"], category,
        ", dispute" if record["dispute"] else "", place_key,
    )
    return {
        "received": True,
        "correction_id": record["correction_id"],
        "status": record["status"],
        "created_at": record["created_at"],
        "faces_blurred": faces_blurred,
        "has_photo": image_key is not None,
        # What the sheet promises, kept literally: a person reads this before
        # anything about the place changes, and a correction never changes a
        # verdict at all.
        "review": "corrections stay human; nothing changes without review",
    }, 201


@correct_page.get("/correct/mine")
def my_corrections():
    """The caller's own corrections and their real status.

    The contributor token is required and is the whole of the identity: a
    record is returned only to the token that wrote it, so the Contributions
    tab reads the server's state rather than echoing a button press.
    """
    contributor = _contributor()
    if contributor is None:
        return _error(
            "missing contributor",
            f"GET /correct/mine needs the {CONTRIBUTOR_HEADER} header that the "
            "correction was sent with.",
        )
    store = load_correction_store(_corrections_path())
    if store.error is not None:
        # An unreadable store answered as an empty list is #387 inverted: a
        # note the server DID receive is drawn in the tab as one that was
        # never sent, which is the exact belief this endpoint exists to stop
        # being false. Say the list could not be read instead.
        return _error(
            "correction not received",
            f"the correction store could not be read ({store.error}); this "
            "list is not what the server holds. Retry.",
            status=503,
        )
    mine = corrections_for_contributor(
        store.records, contributor, MAX_PER_CONTRIBUTOR
    )
    return {"corrections": [public_correction_view(r) for r in mine]}, 200
