"""Owner claim records: JSONL store that the public map never reads (TICK-259).

A claim is a request to manage a place-backed listing. Status is pending until
a person with the upload key approves or rejects it; the claimant can abandon.
Self-asserted ownership is refused: every submit names a verifiable channel
whose authority is the public listing (listed phone, business-domain email) or
a team-issued in-store code. The claimant does not supply the listing contact.

This module does not touch pin state. Approval opens a workspace; Owner-confirmed
on the map is a later attested in-app capture, written by scan_records.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

CLAIMS_ENV = "FRONTDOOR_CLAIMS"
DEFAULT_CLAIMS_PATH = "data/claims.jsonl"
CODES_ENV = "FRONTDOOR_CLAIM_CODES"
DEFAULT_CODES_PATH = "data/claim_codes.json"

STATUSES = frozenset({"pending", "approved", "rejected", "abandoned"})
CHANNELS = frozenset({"listed_phone", "business_email", "in_store_code"})

INCENTIVES_TEXT = (
    "Accessibility fixes may qualify for federal tax credits — ask your accountant."
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_append_lock = threading.Lock()


class ClaimError(ValueError):
    """Raised when a claim cannot be created or moved."""


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_claims(path):
    """Every parseable claim dict; [] when the store is missing or unreadable."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, TypeError, ValueError):
        return []
    records = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and isinstance(record.get("claim_id"), str):
            records.append(record)
    return records


def load_codes(path):
    """place_id -> in-store code. Missing or junk is an empty map."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    codes = {}
    for place_id, code in raw.items():
        if isinstance(place_id, str) and isinstance(code, str) and code.strip():
            codes[place_id] = code.strip()
    return codes


def load_catalogue(path):
    """place_id-keyed catalogue dict; {} when missing or unreadable."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def listing_host(website):
    """Hostname of a listing website, www. stripped. None when unusable."""
    if not isinstance(website, str) or not website.strip():
        return None
    raw = website.strip()
    if "://" not in raw:
        raw = "https://" + raw
    host = urlparse(raw).hostname
    if not isinstance(host, str) or not host:
        return None
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def email_matches_listing(email, website):
    if not isinstance(email, str) or not _EMAIL_RE.match(email.strip()):
        return False
    domain = email.strip().rsplit("@", 1)[1].lower()
    host = listing_host(website)
    return host is not None and domain == host


def listing_phone(row):
    if not isinstance(row, dict):
        return None
    for key in ("phone", "formatted_phone_number", "international_phone_number"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _codes_match(presented, expected):
    if not isinstance(presented, str) or not isinstance(expected, str):
        return False
    left, right = presented.strip().encode("utf-8"), expected.strip().encode("utf-8")
    if len(left) != len(right) or not left:
        return False
    # Constant-time: a timing oracle on an in-store code is write access to a claim.
    return hmac.compare_digest(left, right)


def channels_for_row(place_id, row, codes):
    return {
        "listed_phone": listing_phone(row) is not None,
        "business_email": listing_host((row or {}).get("website")) is not None,
        "in_store_code": isinstance(place_id, str) and place_id in codes,
    }


def search_places(dataset, query, codes, limit=20):
    q = query.strip().lower() if isinstance(query, str) else ""
    if len(q) < 2:
        return []
    hits = []
    if not isinstance(dataset, dict):
        return []
    for place_id, row in dataset.items():
        if not isinstance(place_id, str) or not isinstance(row, dict):
            continue
        name = row.get("name") if isinstance(row.get("name"), str) else ""
        if q not in name.lower() and q not in place_id.lower():
            continue
        location = row.get("location") if isinstance(row.get("location"), dict) else {}
        hits.append({
            "place_id": place_id,
            "name": name,
            "location": location,
            "channels": channels_for_row(place_id, row, codes),
        })
    hits.sort(key=lambda hit: (hit["name"].lower(), hit["place_id"]))
    return hits[:limit]


def _append(path, record):
    path = Path(path)
    line = json.dumps(record, sort_keys=True, separators=(",", ":"))
    with _append_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size and path.read_bytes()[-1:] != b"\n":
            raise ClaimError(
                f"{path} does not end with a newline; a previous write was "
                "interrupted. Refusing to append onto a partial record."
            )
        with open(path, "a", encoding="utf-8", newline="") as handle:
            handle.write(line + "\n")


def _rewrite(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    body = "".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    )
    tmp.write_text(body, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def submit_claim(path, *, place_id, channel, row, codes, email=None, code=None, role=None):
    """Create a pending claim. Refuses self-asserted or unverifiable channels."""
    if not isinstance(place_id, str) or not place_id.strip():
        raise ClaimError("place_id is required")
    if not isinstance(row, dict):
        raise ClaimError("unknown place")
    if channel not in CHANNELS:
        raise ClaimError("self-asserted ownership is not sufficient")

    listed_contact = None
    claimant_email = None
    if channel == "listed_phone":
        listed_contact = listing_phone(row)
        if listed_contact is None:
            raise ClaimError("listed_phone is not available for this place")
    elif channel == "business_email":
        host = listing_host(row.get("website"))
        if host is None:
            raise ClaimError("business_email is not available for this place")
        if not email_matches_listing(email, row.get("website")):
            raise ClaimError("email must use the listing's business domain")
        listed_contact = host
        claimant_email = email.strip()
    else:
        expected = codes.get(place_id)
        if expected is None:
            raise ClaimError("in_store_code is not available for this place")
        if not _codes_match(code, expected):
            raise ClaimError("in-store code does not match")

    if role is not None:
        if not isinstance(role, str) or not role.strip() or len(role) > 40:
            raise ClaimError("role must be 1-40 characters")
        role = role.strip()

    record = {
        "claim_id": uuid.uuid4().hex,
        "place_id": place_id,
        "status": "pending",
        "channel": channel,
        "listed_contact_used": listed_contact,
        "claimant_email": claimant_email,
        "role": role,
        "token": secrets.token_urlsafe(32),
        "created_at": now_iso(),
        "reviewed_at": None,
        "dispute": None,
    }
    _append(path, record)
    return record


def get_claim(path, claim_id):
    for record in load_claims(path):
        if record.get("claim_id") == claim_id:
            return record
    return None


def token_matches(record, token):
    presented = token if isinstance(token, str) else ""
    expected = record.get("token") if isinstance(record, dict) else None
    if not isinstance(expected, str) or not expected or not presented:
        return False
    left, right = presented.encode("utf-8"), expected.encode("utf-8")
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def has_approved_claim(path, place_id):
    if not isinstance(place_id, str) or not place_id:
        return False
    return any(
        record.get("place_id") == place_id and record.get("status") == "approved"
        for record in load_claims(path)
    )


def set_status(path, claim_id, status):
    if status not in STATUSES:
        raise ClaimError("unknown claim status")
    with _append_lock:
        records = load_claims(path)
        found = None
        for index, record in enumerate(records):
            if record.get("claim_id") == claim_id:
                found = index
                break
        if found is None:
            raise ClaimError("claim not found")
        current = records[found]
        current_status = current.get("status")
        if current_status == status:
            return current
        if current_status in ("rejected", "abandoned") and status != current_status:
            raise ClaimError("claim is closed")
        if current_status == "approved" and status not in ("approved", "abandoned"):
            raise ClaimError("approved claims can only be abandoned")
        if status in ("approved", "rejected") and current_status != "pending":
            raise ClaimError("only a pending claim can be reviewed")
        updated = dict(current)
        updated["status"] = status
        if status in ("approved", "rejected"):
            updated["reviewed_at"] = now_iso()
        records[found] = updated
        _rewrite(path, records)
        return updated


def set_dispute(path, claim_id, note):
    if not isinstance(note, str) or not note.strip() or len(note) > 500:
        raise ClaimError("dispute note must be 1-500 characters")
    with _append_lock:
        records = load_claims(path)
        found = None
        for index, record in enumerate(records):
            if record.get("claim_id") == claim_id:
                found = index
                break
        if found is None:
            raise ClaimError("claim not found")
        if records[found].get("status") != "approved":
            raise ClaimError("only an approved claim can dispute a pin")
        updated = dict(records[found])
        updated["dispute"] = note.strip()
        records[found] = updated
        _rewrite(path, records)
        return updated


def public_claim_view(record):
    """Claimant-facing fields. Never the listing contact, never the token."""
    if not isinstance(record, dict):
        return None
    return {
        "claim_id": record.get("claim_id"),
        "place_id": record.get("place_id"),
        "status": record.get("status"),
        "channel": record.get("channel"),
        "role": record.get("role"),
        "created_at": record.get("created_at"),
        "incentives": INCENTIVES_TEXT,
        "dispute": record.get("dispute"),
    }
