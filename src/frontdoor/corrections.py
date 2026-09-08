"""Community corrections: the review queue behind "Send suggestion" (TICK-387, #387).

The app's correction sheet used to push the note into a JavaScript array in one
browser. The person saw it listed in their Contributions tab and reasonably
believed somebody would read it. Nobody would. This module is the store that
now receives it, and the rules that keep receiving it from becoming a way to
publish a negative claim about a named business.

WHAT A CORRECTION IS ALLOWED TO DO
----------------------------------
Exactly two things, and this module is written so a third is not expressible:

1. It joins an append-only queue a person works through (``review_queue``).
   Nothing in this module writes a verdict, a status, a source, or a criterion
   entry onto a map row. ``apply_relook`` -- the only function here that
   touches a dataset at all -- writes ``needs_relook`` and ``relook_since``
   and nothing else, and ``RELOOK_FIELDS`` is what
   tests/test_correct_endpoint.py asserts against, so wiring a verdict up
   later fails a test rather than shipping.

2. Once corroborated, it can say the world may have moved: the place needs a
   re-look. That is FRESHNESS, not a finding. It lowers nothing, contradicts
   nothing, and publishes no claim about what is at the door -- it surfaces
   the "Could you take another look?" nudge the app already has, on a place
   whose evidence is older than the corroborated reports about it. The map's
   Green-or-Gray rule (frontdoor.map_states) is untouched: states are
   computed before any of this runs, and no correction is an input to them.

CORROBORATION
-------------
A single anonymous note cannot mark a place stale, because a single anonymous
note is exactly what one motivated person can produce for a competitor's door.
``RELOOK_MIN_CONTRIBUTORS`` distinct contributor tokens must independently
report the same place, and only categories that assert the world CHANGED
(``RELOOK_CATEGORIES``) count -- a photo complaint is a queue item, not
evidence about the doorway. Contributor tokens are self-minted in the browser,
so this raises the cost of manufacturing corroboration rather than preventing
it; that is acceptable precisely because the entire consequence is a freshness
nudge that asks somebody to go and take a photograph.

A report about "a different entrance of this business" does not count either:
the nudge asks somebody to re-photograph THIS door, and a note about another
one is a queue item rather than evidence about this entrance's age.

A correction is also spent once the place is re-photographed: only corrections
NEWER than the row's own evidence date count, so a re-look request is answered
by a scan rather than sticking to the pin for good.

DISPUTES
--------
``/claim/<id>/dispute`` hangs off a claimed listing, so only an owner who has
been through the claim flow can say a verdict is wrong. A passer-by who can
see the answer is wrong had no route at all. The narrowest honest version of
one: a correction whose category is ``entrance_features`` against a place at
the scanned or owner-confirmed tier is a DISPUTE, flagged as such on the
record and sorted to the top of the queue. The tier is resolved server-side
from the same merged dataset /map/data serves, never taken from the client.

STORAGE
-------
JSONL on the volume beside the scan records (``FRONTDOOR_CORRECTIONS``,
default ``data/corrections.jsonl``), appended through
``frontdoor.scan_records.append_scan`` and read through ``load_scan_store`` --
the same functions, not a copy of them, so the torn-line recovery and the
"never invent the parent directory" rule are the ones already proven on the
scan store rather than a second implementation that drifts from it.

Attached photos are privacy-processed before anything is written
(frontdoor_server.correct_view), and the bytes live in object storage under
``corrections/<place-slug>/<uuid>.jpg`` in the open partition, keyed by the
same allowlist shape the scan images use.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import replace
from datetime import datetime, timezone

from frontdoor.map_states import STATE_SCANNED, state_for_row

# The append discipline and the store reader are the scan store's, imported
# rather than re-implemented: append_scan recovers a torn last line and
# refuses to create its own parent directory (a missing parent is a missing
# volume, and inventing it is how the /data incident hid), and load_scan_store
# reports unparseable lines instead of silently dropping them. Both are
# store-shape functions -- one JSON object per line -- and nothing in them is
# specific to a scan record.
from frontdoor.scan_records import (
    _place_key,
    append_scan as _append_jsonl,
    load_scan_store as _load_jsonl,
)

CORRECTIONS_ENV = "FRONTDOOR_CORRECTIONS"
DEFAULT_CORRECTIONS_PATH = "data/corrections.jsonl"

#: The sheet's four categories, in the sheet's order.
CATEGORY_ENTRANCE_FEATURES = "entrance_features"
CATEGORY_BUSINESS_IDENTITY = "business_identity"
CATEGORY_PHOTO_ISSUE = "photo_issue"
CATEGORY_OTHER = "other"
CATEGORIES = (
    CATEGORY_ENTRANCE_FEATURES,
    CATEGORY_BUSINESS_IDENTITY,
    CATEGORY_PHOTO_ISSUE,
    CATEGORY_OTHER,
)

#: Which entrance the note is about. The sheet asks; it is context for the
#: reviewer and never a verdict about either door.
SCOPE_THIS_ENTRANCE = "this_entrance"
SCOPE_OTHER_ENTRANCE = "other_entrance"
SCOPES = (SCOPE_THIS_ENTRANCE, SCOPE_OTHER_ENTRANCE)

#: The sheet caps the textarea at 300 characters; the server caps it too,
#: because a maxlength attribute is a courtesy to a browser, not a limit.
NOTE_MAX = 300

#: Queue statuses. "received" is what the endpoint writes; the rest are what a
#: reviewer moves a record to by hand. None of them is a verdict, and none of
#: them reaches a map row.
STATUS_RECEIVED = "received"
STATUS_REVIEWED = "reviewed"
STATUS_DECLINED = "declined"
STATUSES = (STATUS_RECEIVED, STATUS_REVIEWED, STATUS_DECLINED)

#: Public tiers a correction can be filed against, resolved server-side.
TIER_ESTIMATED = "estimated"
TIER_SCANNED = "scanned"
TIER_OWNER_CONFIRMED = "owner_confirmed"

#: A dispute is an entrance_features correction against a place somebody has
#: already stood in front of. Against an estimate it is just a note -- there is
#: no human finding to dispute yet.
DISPUTE_TIERS = (TIER_SCANNED, TIER_OWNER_CONFIRMED)

#: Categories that assert the doorway itself may have changed. A photo
#: complaint or a catch-all note is a queue item and nothing more.
RELOOK_CATEGORIES = (CATEGORY_ENTRANCE_FEATURES, CATEGORY_BUSINESS_IDENTITY)

#: How many DISTINCT contributors must independently report a place before it
#: is marked as needing a re-look. One is not corroboration.
RELOOK_MIN_CONTRIBUTORS = 2

#: The only keys apply_relook may ever add to a dataset row. Pinned by a test:
#: anything else appearing here is a correction changing what the map says
#: about a business, which is the thing this whole module exists not to do.
RELOOK_FIELDS = ("needs_relook", "relook_since")

SLUG_MAX = 64
_CORRECTION_IMAGE_KEY_RE = re.compile(
    r"^corrections/[A-Za-z0-9_-]{1,%d}/[0-9a-f]{32}\.jpg$" % SLUG_MAX
)
_PHYSICAL_PREFIX = "open/"

#: How many of a contributor's own corrections GET /correct/mine answers with.
#: A bound on the RESPONSE, and deliberately not a claim about the store: the
#: write path is unauthenticated, the contributor token is self-minted, and a
#: per-token write cap would be defeated by minting a second token. What bounds
#: the store is the same thing that bounds /screen/publish -- nothing yet. Said
#: plainly here because a comment that implies a cap is how a missing one stays
#: missing.
MAX_PER_CONTRIBUTOR = 50


class CorrectionError(ValueError):
    """Raised when a correction cannot be built or stored."""


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- image keys --------------------------------------------------------------


def _slug(place_ref):
    raw = ""
    if isinstance(place_ref, dict):
        for field in ("place_id", "name"):
            value = place_ref.get(field)
            if isinstance(value, str) and value.strip():
                raw = value.strip()
                break
    slug = re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9_-]", "-", raw)).strip("-")
    return slug[:SLUG_MAX] or "place"


def new_image_key(place_ref):
    """A fresh public image key for one processed correction photo."""
    return f"corrections/{_slug(place_ref)}/{uuid.uuid4().hex}.jpg"


def is_correction_image_key(key):
    """True only for a well-formed key under the corrections/ prefix.

    An allowlist for the same reason the scan keys use one: the slug charset
    has no dot and no slash, so ".." and nested paths cannot match, and no
    key outside corrections/ can be expressed at all.
    """
    return isinstance(key, str) and _CORRECTION_IMAGE_KEY_RE.fullmatch(key) is not None


def physical_key(image_key):
    """The object-storage key for a public correction image key."""
    if not is_correction_image_key(image_key):
        raise CorrectionError(f"not a correction image key: {image_key!r}")
    return _PHYSICAL_PREFIX + image_key


# --- records -----------------------------------------------------------------


def place_tier(row):
    """The public tier of a merged dataset row.

    Reads exactly what the map reads -- state_for_row plus the owner_confirmed
    flag -- so "is this a dispute" cannot drift from what the pin shows.
    """
    if isinstance(row, dict) and row.get("owner_confirmed") is True:
        return TIER_OWNER_CONFIRMED
    if state_for_row(row) == STATE_SCANNED:
        return TIER_SCANNED
    return TIER_ESTIMATED


#: Sentinel that makes _place_key's "matched nothing" answer recognisable. It
#: builds its fallback key from the record's own id, which for a correction
#: would be a fresh uuid every time -- so two people reporting the same
#: uncatalogued doorway would land on two different keys and could never
#: corroborate each other.
_UNMATCHED = "unmatched-place-reference"


def place_key_for_ref(dataset, place_ref):
    """Which dataset key this correction is about.

    The SAME resolution the scan merge uses (place_id, else distance plus
    fuzzy name), imported rather than re-derived: a correction that resolved
    to a different key than a scan of the same doorway would sit in the queue
    against a place nobody can find, and the re-look would attach to a pin
    that is not the one the reporter was looking at.

    One deliberate narrowing. _place_key's name guard only rejects a distance
    match when BOTH names are non-empty, so a reference carrying coordinates
    and no name matches whatever row happens to be within 40 m. For a scan
    that is a photograph landing on its nearest plausible pin; for a
    correction it is somebody's written complaint being filed against a
    business they never named -- with the dispute flag, and the tier, and
    (once corroborated) a public "Re-look requested" line on that business's
    pin. So a nameless reference does not get to match by distance at all: it
    resolves to its place_id, or to a stable key of its own.

    A reference that matches nothing on the map still gets a STABLE key, so
    the queue groups those reports together. It reaches no pin either way --
    apply_relook only ever writes onto a row that already exists.
    """
    ref = dict(place_ref) if isinstance(place_ref, dict) else {}
    name = ref.get("name")
    if not (isinstance(name, str) and name.strip()):
        ref.pop("lat", None)
        ref.pop("lng", None)
    key = _place_key(dataset if isinstance(dataset, dict) else {},
                     {"place_ref": ref, "scan_id": _UNMATCHED})
    if key == f"scan:{_UNMATCHED}":
        return "correction:" + _slug(place_ref)
    return key


def is_dispute(category, tier):
    """A public dispute: entrance_features against a place a human has seen."""
    return category == CATEGORY_ENTRANCE_FEATURES and tier in DISPUTE_TIERS


def new_correction_record(*, place_ref, place_key, tier, category, note,
                          created_at, scope=SCOPE_THIS_ENTRANCE,
                          entrance_id=None, contributor=None, image_key=None,
                          faces_blurred=0, blur_regions=None):
    """One correction, with a fresh correction_id.

    Deliberately carries no verdict field of any kind. `dispute` and
    `place_tier` are queue metadata: they say how a reviewer should read the
    note, not what is true about the door.
    """
    if category not in CATEGORIES:
        raise CorrectionError(f"unknown category: {category!r}")
    if scope not in SCOPES:
        raise CorrectionError(f"unknown scope: {scope!r}")
    record = {
        "correction_id": uuid.uuid4().hex,
        "place_ref": place_ref,
        "place_key": place_key,
        "place_tier": tier,
        "entrance_id": entrance_id,
        "category": category,
        "scope": scope,
        "note": note,
        "created_at": created_at,
        "contributor": contributor,
        "image_key": image_key,
        "faces_blurred": faces_blurred,
        "status": STATUS_RECEIVED,
        "dispute": is_dispute(category, tier),
    }
    if blur_regions is not None:
        record["blur_regions"] = list(blur_regions)
    return record


def append_correction(path, record):
    """Append one correction as one JSONL line (see the module docstring)."""
    _append_jsonl(path, record)


def load_correction_store(path):
    """A ScanStoreLoad over the corrections file: records, error, skipped.

    The reader is the scan store's, so its message says "scans unreadable".
    That is the one word an operator acts on -- it would send them to
    /data/scans.jsonl while /data/corrections.jsonl is the file in trouble --
    so the noun is corrected here rather than left to mislead.
    """
    load = _load_jsonl(path)
    if load.error:
        return replace(load, error=load.error.replace("scans", "corrections", 1))
    return load


def load_corrections(path):
    """Every parseable correction; [] when the store is missing or unreadable."""
    return _load_jsonl(path).records


def public_correction_view(record):
    """What the contributor who wrote it may read back.

    The real state of their own note -- sent, received, reviewed -- and
    nothing about anybody else's. `dispute` is queue metadata for the person
    working the queue and is deliberately not published back: a contributor
    being told their note is "a dispute" invites a negative reading of a
    named business that nothing has reviewed yet.
    """
    return {
        "correction_id": record.get("correction_id"),
        "place_name": (record.get("place_ref") or {}).get("name"),
        "category": record.get("category"),
        "scope": record.get("scope"),
        "note": record.get("note"),
        "created_at": record.get("created_at"),
        "status": record.get("status") if record.get("status") in STATUSES
        else STATUS_RECEIVED,
        "has_photo": bool(record.get("image_key")),
    }


def corrections_for_contributor(records, contributor, limit=MAX_PER_CONTRIBUTOR):
    """This contributor's own corrections, newest first, bounded."""
    if not isinstance(contributor, str) or not contributor:
        return []
    mine = [
        r for r in records
        if isinstance(r, dict) and r.get("contributor") == contributor
    ]
    mine.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return mine[:limit]


# --- the review queue --------------------------------------------------------


def review_queue(records, include_resolved=False):
    """The queue a person works through: disputes first, then newest first.

    A dispute against a scanned or owner-confirmed place is the item that
    needs a human soonest -- somebody is saying a finding a person put there
    is wrong -- so it sorts above routine notes and carries the flag that
    says so. Everything else is a note.
    """
    queue = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if not include_resolved and record.get("status") not in (None, STATUS_RECEIVED):
            continue
        queue.append(record)
    # Two stable passes: newest first, then disputes lifted to the top with
    # that order preserved inside each group.
    queue.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    queue.sort(key=lambda r: 0 if r.get("dispute") is True else 1)
    return queue


def format_queue(records, include_resolved=False):
    """One readable line per queue item -- what a reviewer opens the file for."""
    lines = []
    for record in review_queue(records, include_resolved):
        ref = record.get("place_ref") if isinstance(record.get("place_ref"), dict) else {}
        note = (record.get("note") or "").replace("\n", " ")
        lines.append(
            "{flag} {when}  {place}  [{category}/{tier}]  {note}{photo}".format(
                flag="DISPUTE" if record.get("dispute") is True else "note   ",
                when=str(record.get("created_at") or "")[:19],
                place=ref.get("name") or ref.get("place_id") or record.get("place_key") or "?",
                category=record.get("category"),
                tier=record.get("place_tier"),
                note=note or "(photo only)",
                photo=" +photo" if record.get("image_key") else "",
            )
        )
    return lines


# --- freshness: the ONLY thing a correction may change on a map row ----------


def _date(value):
    if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}", value):
        return value[:10]
    return None


def _row_evidence_date(row):
    """The most recent date the row itself claims. None when it claims none."""
    if not isinstance(row, dict):
        return None
    dates = [
        _date(row.get("imagery_date")),
        _date(row.get("last_scanned")),
    ]
    dates = [d for d in dates if d]
    return max(dates) if dates else None


def relook_requests(dataset, corrections):
    """{place key: {"since", "reports", "contributors"}} for corroborated places.

    A place qualifies when RELOOK_MIN_CONTRIBUTORS distinct contributors have
    filed a world-may-have-moved correction against it that is NEWER than the
    row's own evidence date. Anonymous corrections (no contributor token)
    never corroborate: they are all one unidentified reporter, so counting
    them as many would be counting nothing.
    """
    dataset = dataset if isinstance(dataset, dict) else {}
    by_place = {}
    for record in corrections if isinstance(corrections, list) else []:
        if not isinstance(record, dict):
            continue
        if record.get("category") not in RELOOK_CATEGORIES:
            continue
        # "a different entrance of this business" is a report about a door
        # this pin is not. The nudge asks somebody to re-photograph THIS one,
        # so it is a queue item and not evidence about this entrance's age.
        if record.get("scope") not in (None, SCOPE_THIS_ENTRANCE):
            continue
        when = _date(record.get("created_at"))
        if when is None:
            continue
        key = record.get("place_key")
        if not isinstance(key, str) or not key:
            continue
        contributor = record.get("contributor")
        if not isinstance(contributor, str) or not contributor:
            continue
        evidence = _row_evidence_date(dataset.get(key))
        if evidence is not None and when <= evidence:
            continue  # already answered by a photograph taken since
        entry = by_place.setdefault(key, {"since": when, "contributors": set()})
        entry["contributors"].add(contributor)
        entry["since"] = min(entry["since"], when)
    return {
        key: {"since": entry["since"], "contributors": len(entry["contributors"])}
        for key, entry in by_place.items()
        if len(entry["contributors"]) >= RELOOK_MIN_CONTRIBUTORS
    }


def apply_relook(dataset, corrections):
    """(dataset, relook meta) with needs_relook set on corroborated rows.

    The ONLY mutation in this module, and it writes exactly RELOOK_FIELDS.
    Not touched, by construction: status, source, criteria, owner_confirmed,
    imagery_date, location, name. So the row's public state and its whole
    checklist are byte-for-byte what they were, and Green-or-Gray is decided
    by inputs no correction is part of. A row that does not already exist is
    not created either -- a correction cannot put a business on the map.
    """
    merged = dict(dataset) if isinstance(dataset, dict) else {}
    requests = relook_requests(merged, corrections)
    for key, meta in requests.items():
        row = merged.get(key)
        if not isinstance(row, dict):
            continue
        updated = dict(row)
        updated["needs_relook"] = True
        updated["relook_since"] = meta["since"]
        merged[key] = updated
    return merged, requests


def main(argv=None):  # pragma: no cover - operator convenience
    """Print the review queue. `python -m frontdoor.corrections [path]`."""
    import argparse
    import os

    parser = argparse.ArgumentParser(description=main.__doc__.splitlines()[0])
    parser.add_argument(
        "path", nargs="?",
        default=os.environ.get(CORRECTIONS_ENV, DEFAULT_CORRECTIONS_PATH),
        help="the corrections JSONL store",
    )
    parser.add_argument("--all", action="store_true",
                        help="include records a reviewer has already moved on")
    args = parser.parse_args(argv)
    load = load_correction_store(args.path)
    if load.error:
        print(load.error)
        return 1
    lines = format_queue(load.records, include_resolved=args.all)
    for line in lines:
        print(line)
    print(f"-- {len(lines)} open item(s); {load.skipped} unreadable line(s)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
