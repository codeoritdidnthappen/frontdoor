"""Owner claim HTTP surface (TICK-259, #248).

Public map data never reads this module. Submit is pending until a person with
the upload key reviews it. The workspace exists only after approval.
"""

import os

from flask import Blueprint, current_app, request

from frontdoor.claims import (
    CLAIMS_ENV,
    CODES_ENV,
    DEFAULT_CLAIMS_PATH,
    DEFAULT_CODES_PATH,
    INCENTIVES_TEXT,
    ClaimError,
    channels_for_row,
    get_claim,
    load_catalogue,
    load_codes,
    public_claim_view,
    search_places,
    set_dispute,
    set_status,
    submit_claim,
    token_matches,
)
from frontdoor.map_states import pin_for_row
from frontdoor.scan_records import (
    DEFAULT_SCANS_PATH,
    SCANS_ENV,
    load_scan_records,
    merge_scans,
)
from frontdoor_server.map_view import DATASET_ENV, DEFAULT_DATASET_PATH
from frontdoor_server.screen_view import _error
from frontdoor_server.upload_view import _authorised, _client_key

claim_page = Blueprint("claim_page", __name__)

_PLACE_ID_MAX = 128


def _claims_path():
    return os.environ.get(CLAIMS_ENV, DEFAULT_CLAIMS_PATH)


def _codes():
    return load_codes(os.environ.get(CODES_ENV, DEFAULT_CODES_PATH))


def _catalogue():
    return load_catalogue(os.environ.get(DATASET_ENV, DEFAULT_DATASET_PATH))


def _place_row(place_id):
    dataset = _catalogue()
    row = dataset.get(place_id)
    return row if isinstance(row, dict) else None


#: Where a claimant's bearer token is meant to travel.
#:
#: These handlers used to read it from `?token=`. That token is the SOLE credential for an
#: approved workspace, and a query string is written down along the way: the access log, the
#: proxy's log, and -- for any client that puts one in a DOCUMENT url rather than a fetch --
#: the browser's history and the Referer of everything that page then loads.
#:
#: Our own page keeps the token in storage rather than the address bar, so the live exposure
#: today is the two logs. Which of the rest apply is a property of the client, not of the
#: credential, and that is the reason the rule is "not in a URL at all" rather than a list of
#: clients to check. None of those places can be revoked.
#:
#: A header rather than only a body because two of these are GETs, and a browser cannot put a
#: body on a GET.
CLAIM_TOKEN_HEADER = "X-Frontdoor-Claim-Token"


def _presented_token():
    """The claimant's token, from the header, else the JSON body, else the query string.

    The query string is DEPRECATED and kept for exactly one release, so that the shipped
    `/app` page keeps working while its request is changed to send the header instead. Every
    use of it is logged -- without the token -- so the decision to delete this fallback can be
    made from evidence rather than from hope. Delete it, and this comment, once that log is
    quiet.
    """
    header = request.headers.get(CLAIM_TOKEN_HEADER, "").strip()
    if header:
        return header

    body = request.get_json(silent=True)
    if isinstance(body, dict) and isinstance(body.get("token"), str) and body["token"]:
        return body["token"]

    in_url = request.args.get("token")
    if in_url:
        # The token itself is never logged. What is worth recording is that one arrived in a URL
        # at all, and on which path, because that is what says whether the client has moved.
        current_app.logger.warning(
            "claim token presented in the query string on %s; "
            "send it as the %s header instead (deprecated, removed next release)",
            request.path,
            CLAIM_TOKEN_HEADER,
        )
    return in_url


def _claimant_record(claim_id, token):
    record = get_claim(_claims_path(), claim_id)
    if record is None or not token_matches(record, token):
        return None
    return record


def _public_pin(place_id):
    dataset = _catalogue()
    scans = load_scan_records(os.environ.get(SCANS_ENV, DEFAULT_SCANS_PATH))
    merged, _ = merge_scans(dataset, scans)
    row = merged.get(place_id)
    return pin_for_row(place_id, row)


@claim_page.get("/claim/places")
def claim_places():
    query = request.args.get("q", "")
    hits = search_places(_catalogue(), query, _codes())
    return {"places": hits}


@claim_page.post("/claim")
def claim_submit():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error(
            "invalid claim",
            "POST /claim requires an application/json body.",
            status=415,
        )
    place_id = body.get("place_id")
    if not isinstance(place_id, str) or not place_id.strip() or len(place_id) > _PLACE_ID_MAX:
        return _error("invalid claim", "place_id is required.", status=422)
    if body.get("phone"):
        return _error(
            "invalid claim",
            "the claimant does not supply the listing contact; use a listed channel.",
            status=422,
        )
    row = _place_row(place_id)
    if row is None:
        return _error("unknown place", "that place_id is not in the catalogue.", status=404)
    try:
        record = submit_claim(
            _claims_path(),
            place_id=place_id,
            channel=body.get("channel"),
            row=row,
            codes=_codes(),
            email=body.get("email"),
            code=body.get("code"),
            role=body.get("role"),
        )
    except ClaimError as exc:
        return _error("invalid claim", str(exc), status=422)
    view = public_claim_view(record)
    view["token"] = record["token"]
    view["channels"] = channels_for_row(place_id, row, _codes())
    return view, 201


@claim_page.get("/claim/<claim_id>")
def claim_get(claim_id):
    record = _claimant_record(claim_id, _presented_token())
    if record is None:
        return _error("claim not found", "no claim matches that id and token.", status=404)
    return public_claim_view(record)


@claim_page.post("/claim/<claim_id>/review")
def claim_review(claim_id):
    expected = _client_key()
    if not _authorised(request.headers.get("X-Frontdoor-Upload-Key", ""), expected):
        return _error(
            "claim review not authorised",
            "POST /claim/<id>/review requires the X-Frontdoor-Upload-Key header.",
            status=401,
        )
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error(
            "invalid review",
            "POST /claim/<id>/review requires an application/json body.",
            status=415,
        )
    action = body.get("action")
    if action not in ("approve", "reject"):
        return _error("invalid review", "action must be approve or reject.", status=422)
    try:
        record = set_status(_claims_path(), claim_id, "approved" if action == "approve" else "rejected")
    except ClaimError as exc:
        status = 404 if str(exc) == "claim not found" else 409
        return _error("invalid review", str(exc), status=status)
    return public_claim_view(record)


@claim_page.post("/claim/<claim_id>/abandon")
def claim_abandon(claim_id):
    record = _claimant_record(claim_id, _presented_token())
    if record is None:
        return _error("claim not found", "no claim matches that id and token.", status=404)
    try:
        updated = set_status(_claims_path(), claim_id, "abandoned")
    except ClaimError as exc:
        return _error("invalid claim", str(exc), status=409)
    return public_claim_view(updated)


@claim_page.get("/claim/<claim_id>/workspace")
def claim_workspace(claim_id):
    record = _claimant_record(claim_id, _presented_token())
    if record is None or record.get("status") != "approved":
        return _error("workspace not found", "no approved workspace for that claim.", status=404)
    pin = _public_pin(record["place_id"])
    return {
        "claim": public_claim_view(record),
        "pin": pin,
        "incentives": INCENTIVES_TEXT,
        "guided_capture": {
            "capture_kind": "in_app",
            "attested": True,
            "camera_roll": False,
        },
    }


@claim_page.post("/claim/<claim_id>/dispute")
def claim_dispute(claim_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error(
            "invalid dispute",
            "POST /claim/<id>/dispute requires an application/json body.",
            status=415,
        )
    record = _claimant_record(claim_id, _presented_token())
    if record is None:
        return _error("claim not found", "no claim matches that id and token.", status=404)
    try:
        updated = set_dispute(_claims_path(), claim_id, body.get("note"))
    except ClaimError as exc:
        return _error("invalid dispute", str(exc), status=422)
    return public_claim_view(updated)
