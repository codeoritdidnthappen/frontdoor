"""Community scan records: the store the map merges with the pre-catalogue (TICK-262, #270).

POST /screen assesses and deliberately retains nothing. The publish step
(frontdoor_server.scan_view) is the explicit-consent path that DOES retain:
privacy-processed image bytes go to object storage, and one record per scan is
appended here — an append-friendly JSONL file (one JSON object per line), path
from FRONTDOOR_SCANS, default data/scans.jsonl, the same env-plus-default shape
as the map dataset. JSONL because the write is one line: append_scan keeps the
manifest's newline invariant (frontdoor.manifest._require_newline_terminated)
so a torn earlier write can never silently concatenate two records into one
unparseable line — it terminates the torn line, loudly, and carries on, and
the torn remains are then counted and logged as a skipped record on every
read rather than disappearing. append_scan also refuses to create its own
parent directory, so an unmounted volume is a 503 and not a 200 over a store
that dies with the container.

The record is metadata only — verdicts, confidences, place reference, image
KEYS. The image bytes live in object storage under `scans/<place-slug>/<uuid>.jpg`
(public key shape). ObjectStore refuses keys without a D-007 partition prefix,
so the physical key is that public key under `open/` — community scans are, by
construction, never sealed material, and `physical_key` is the only place that
mapping exists. `SCAN_IMAGE_KEY_RE` is deliberately an allowlist (two segments,
bounded charsets with no dots in the slug, literal `.jpg`): a key that matches
it cannot traverse, alias `sealed/`, or name anything outside the scans prefix.

Never-negative (the map's legal shield, frontdoor.map_states): `merge_scans`
is written so it CANNOT downgrade a pin —
  * the only status it ever writes is "verified" (with source "community_scan",
    which is not imagery-only), and only onto a row that is not already in the
    verified state; an already-verified row's status and source are never
    touched;
  * a criterion entry is replaced only when the scan's entry ranks strictly
    higher in the public observation order (not_assessed < not_visible <
    visible), so an adversarial or all-absent scan can add neutral
    observations where nothing was assessed but can never displace a
    "present";
  * imagery_date only ever moves forward (freshness is monotone).
There is no code path that writes any other status, removes a row, or lowers
an observation; test_scan_records pins each property.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from frontdoor.external_data import (
    DEFAULT_MATCH_DISTANCE_M,
    _haversine_m,
    _names_match,
)

# The map's public observation semantics. The two private names are the exact
# functions /map/data itself renders through, imported rather than re-derived so
# the merge's "never lower an observation" rule cannot drift from what the map
# actually shows (test_scan_records pins the rank order against the public
# OBSERVATION_* vocabulary).
from frontdoor.map_states import (
    OBSERVATION_NOT_ASSESSED,
    OBSERVATION_NOT_VISIBLE,
    OBSERVATION_VISIBLE,
    STATE_VERIFIED,
    _observation,
    _valid_location,
    state_for_row,
)

logger = logging.getLogger(__name__)

SCANS_ENV = "FRONTDOOR_SCANS"
DEFAULT_SCANS_PATH = "data/scans.jsonl"

#: The one source string a community scan writes. On-site and human-present,
#: so it is deliberately NOT in map_states.IMAGERY_ONLY_SOURCES: a published
#: scan is exactly the "human, non-imagery confirmation" the Scanned tier
#: renders.
SCAN_SOURCE = "community_scan"

#: An attested in-app capture from an approved owner workspace. Still a
#: human, non-imagery confirmation (so the legal stamp can be verified); the
#: map's Owner-confirmed tier is the extra `owner_confirmed` flag, not a
#: third Green-or-Gray state.
OWNER_SCAN_SOURCE = "owner_attested"
CAPTURE_IN_APP = "in_app"
CAPTURE_CAMERA_ROLL = "camera_roll"

#: Public image-key shape: scans/<place-slug>/<uuid32>.jpg. An allowlist, not a
#: denylist — the slug charset has no dot and no slash, so ".." and nested
#: paths cannot match, and only keys under scans/ resolve at all.
SLUG_MAX = 64
SCAN_IMAGE_KEY_RE = re.compile(
    r"^scans/[A-Za-z0-9_-]{1,%d}/[0-9a-f]{32}\.jpg$" % SLUG_MAX
)

#: Community scan objects live in the open partition (D-007): they are made of
#: privacy-processed bytes the contributor explicitly published, never sealed
#: material. This prefix is what ObjectStore's partition check requires.
_PHYSICAL_PREFIX = "open/"

_append_lock = threading.Lock()


class ScanRecordError(ValueError):
    """Raised when an append would corrupt the store."""


def place_slug(place_ref):
    """A bounded, key-safe slug for a scan's place reference.

    Prefers place_id, falls back to name, then to "place". Only [A-Za-z0-9_-]
    survives; everything else becomes "-" (runs collapsed) so the slug can be
    embedded in SCAN_IMAGE_KEY_RE's charset by construction.
    """
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
    """A fresh public image key for one processed frame of a scan."""
    return f"scans/{place_slug(place_ref)}/{uuid.uuid4().hex}.jpg"


def is_scan_image_key(key):
    """True only for a well-formed key under the scans/ prefix."""
    return isinstance(key, str) and SCAN_IMAGE_KEY_RE.fullmatch(key) is not None


def physical_key(image_key):
    """The object-storage key for a public scan image key.

    Refuses anything is_scan_image_key refuses, so no caller can reach storage
    with a key outside the scans/ prefix through this function.
    """
    if not is_scan_image_key(image_key):
        raise ScanRecordError(f"not a scan image key: {image_key!r}")
    return _PHYSICAL_PREFIX + image_key


def new_scan_record(*, place_ref, created_at, verdicts, confidences,
                    faces_blurred, quarantined_count, image_keys,
                    contributor=None, entrance_id=None,
                    capture_kind=None, attested=False):
    """One scan record, with a fresh scan_id."""
    record = {
        "scan_id": uuid.uuid4().hex,
        "place_ref": place_ref,
        "entrance_id": entrance_id,
        "created_at": created_at,
        "verdicts": verdicts,
        "confidences": confidences,
        "faces_blurred": faces_blurred,
        "quarantined_count": quarantined_count,
        "image_keys": list(image_keys),
        "contributor": contributor,
    }
    if capture_kind:
        record["capture_kind"] = capture_kind
    if attested:
        record["attested"] = True
    return record


def is_owner_attested(scan):
    """True only for guided in-app capture the owner attested at the door."""
    return (
        isinstance(scan, dict)
        and scan.get("attested") is True
        and scan.get("capture_kind") == CAPTURE_IN_APP
    )


def append_scan(path, record):
    """Append one record as one JSONL line, newline-terminated.

    Two things this deliberately does NOT do, each because doing it hides a
    failure behind a 200:

    * It does not create the parent directory. The publish path does not own
      the storage location; the volume mount does (fly.toml mounts
      `frontdoor_data` at `/data`, and the image sets FRONTDOOR_SCANS to
      `/data/scans.jsonl`). `mkdir(parents=True)` on an unmounted volume
      creates the directory *inside the container*, the append succeeds, the
      contributor is told the scan published, and every scan dies with the
      container with nothing anywhere reporting it. Refusing is the only
      outcome anybody finds out about: scan_view turns a ScanRecordError into
      a 503 that names the store as unavailable.
    * It does not refuse forever over a torn last line. A worker killed
      mid-append (gunicorn runs --timeout 30, and the 512 MB machine has an
      OOM kill on record) leaves the file unterminated. Refusing every later
      append wedges the store for the life of the file while reads keep
      succeeding, so the map looks fine and each contributor is individually
      told "saved for later". Terminating the torn line is recoverable and
      keeps the property the newline discipline exists for -- two records can
      still never merge into one line, because the torn remains stay on their
      own line, where load counts and logs them as skipped.

    The check and the write happen under one lock so two threads in the same
    worker cannot interleave them.
    """
    path = Path(path)
    line = json.dumps(record, sort_keys=True, separators=(",", ":"))
    with _append_lock:
        if not path.parent.is_dir():
            logger.error(
                "scan store directory %s does not exist; refusing to create it "
                "and publish into a location that is not the mounted volume",
                path.parent,
            )
            raise ScanRecordError(
                f"{path.parent} is not an existing directory, so the scan "
                "store's volume is not mounted. Refusing to create it: a "
                "store written inside the container is lost with the container."
            )
        if path.exists() and path.stat().st_size and path.read_bytes()[-1:] != b"\n":
            logger.error(
                "scan store %s was left unterminated by an interrupted append; "
                "terminating the torn line so appends can resume. The torn "
                "remains stay on their own line and are reported as a skipped "
                "record on every read.",
                path,
            )
            with open(path, "ab") as handle:
                handle.write(b"\n")
        with open(path, "a", encoding="utf-8", newline="") as handle:
            handle.write(line + "\n")


@dataclass(frozen=True)
class ScanStoreRead:
    """One read of the scan store, including what it could not read.

    `error` is None only when the store itself was readable; `skipped` counts
    lines that were present and could not be turned into a record. Both are
    reported by /map/data, because "nobody has published yet", "the volume is
    not mounted" and "a line is corrupt" produce the same empty map and the
    caller could not previously tell them apart.
    """

    records: list
    skipped: int
    error: str | None


def read_scan_records(path):
    """Read the store and say what happened.

    Still total -- the map must render with or without scans, and one corrupt
    line must not take every other scan off the map with it -- but no longer
    silent. A missing FILE under an existing directory is the legitimate
    "nobody has published yet" and is not an error; a missing DIRECTORY is the
    unmounted volume and is.
    """
    try:
        store = Path(path)
        text = store.read_text(encoding="utf-8")
    except FileNotFoundError:
        if not store.parent.is_dir():
            error = f"scan store directory not found: {store.parent}"
            logger.error(
                "scan store directory %s does not exist; the map is showing no "
                "scans because the store is unreachable, not because none were "
                "published", store.parent,
            )
            return ScanStoreRead([], 0, error)
        return ScanStoreRead([], 0, None)
    except (OSError, TypeError, ValueError) as exc:
        error = f"scan store unreadable: {type(exc).__name__}: {exc}"
        logger.error("scan store %r unreadable: %s", path, exc)
        return ScanStoreRead([], 0, error)

    records = []
    skipped = 0
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            skipped += 1
            # The line itself is never logged: a scan record carries a place
            # reference and a contributor. Where it is and why is enough to
            # find it, and the store is on the volume.
            logger.warning(
                "scan store %s line %d is not JSON (%s); that scan is not on "
                "the map", store, number, exc.msg,
            )
            continue
        if not isinstance(record, dict):
            skipped += 1
            logger.warning(
                "scan store %s line %d is JSON but not an object; that scan is "
                "not on the map", store, number,
            )
            continue
        records.append(record)
    if skipped:
        logger.error(
            "scan store %s: %d of %d line(s) could not be read as a record and "
            "are missing from the map", store, skipped, skipped + len(records),
        )
    return ScanStoreRead(records, skipped, None)


def load_scan_records(path):
    """Every parseable record; [] when the store is missing or unreadable.

    The list-only view of read_scan_records, for callers that genuinely only
    need the records. /map/data is not one of them -- it reports the count and
    the error too.
    """
    return read_scan_records(path).records


# --- merging into the map dataset -------------------------------------------


def _scan_date(scan):
    """The scan's YYYY-MM-DD date, or None when created_at is unusable."""
    created = scan.get("created_at")
    if isinstance(created, str) and re.match(r"^\d{4}-\d{2}-\d{2}", created):
        return created[:10]
    return None


def _place_key(dataset, scan):
    """Which dataset key this scan belongs to.

    place_id wins when it names an existing row; otherwise distance + fuzzy
    name against every row that has coordinates (the external_data matching
    rule); otherwise the scan's own place_id, or a synthetic scan:<id> key —
    a scan that matches nothing still ADDS a pin, it never disturbs one.
    """
    ref = scan.get("place_ref")
    ref = ref if isinstance(ref, dict) else {}
    place_id = ref.get("place_id")
    if isinstance(place_id, str) and place_id in dataset:
        return place_id
    location = _valid_location({"location": {"lat": ref.get("lat"), "lng": ref.get("lng")}})
    if location is not None:
        name = ref.get("name")
        for key, row in dataset.items():
            if not isinstance(row, dict):
                continue
            row_location = _valid_location(row)
            if row_location is None:
                continue
            if _haversine_m(location["lat"], location["lng"],
                            row_location["lat"], row_location["lng"]) > DEFAULT_MATCH_DISTANCE_M:
                continue
            row_name = row.get("name")
            if (isinstance(name, str) and name
                    and isinstance(row_name, str) and row_name
                    and not _names_match(name, row_name)):
                continue
            return key
    if isinstance(place_id, str) and place_id:
        return place_id
    return f"scan:{scan.get('scan_id')}"


#: The public observation order the merge is monotone over. not_visible and
#: absent both render as "not visible in photos", so replacing one with the
#: other is not a public change; only a strict rank increase replaces.
_OBSERVATION_RANK = {
    OBSERVATION_NOT_ASSESSED: 0,
    OBSERVATION_NOT_VISIBLE: 1,
    OBSERVATION_VISIBLE: 2,
}


def _rank(entry):
    return _OBSERVATION_RANK[_observation(entry)]


def _scan_criteria(scan):
    """The scan's verdicts as pre-catalogue-shaped criterion entries.

    Confidences arrive on the engine's 0-100 scale; the map reads 0-1, so
    values above 1 are scaled down. Non-numbers pass through as None.
    """
    verdicts = scan.get("verdicts")
    confidences = scan.get("confidences")
    if not isinstance(verdicts, dict):
        return {}
    confidences = confidences if isinstance(confidences, dict) else {}
    entries = {}
    for key, verdict in verdicts.items():
        if not isinstance(key, str):
            continue
        confidence = confidences.get(key)
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            confidence = None
        elif confidence > 1:
            confidence = confidence / 100.0
        entries[key] = {"verdict": verdict, "confidence": confidence}
    return entries


def _upgrade_row(base, scan):
    """One row with this scan merged in. Only ever adds or raises — see the
    module docstring for the property-by-property argument."""
    row = dict(base) if isinstance(base, dict) else {}
    ref = scan.get("place_ref")
    ref = ref if isinstance(ref, dict) else {}

    # Fill identity fields only where the row has none.
    if not isinstance(row.get("name"), str) or not row["name"]:
        name = ref.get("name")
        if isinstance(name, str):
            row["name"] = name
    if _valid_location(row) is None:
        location = _valid_location({"location": {"lat": ref.get("lat"), "lng": ref.get("lng")}})
        if location is not None:
            row["location"] = location

    # Criteria: strict rank increase only.
    criteria = row.get("criteria")
    criteria = dict(criteria) if isinstance(criteria, dict) else {}
    for key, entry in _scan_criteria(scan).items():
        if _rank(entry) > _rank(criteria.get(key)):
            criteria[key] = entry
    row["criteria"] = criteria

    # State: the only write is the upgrade to verified. A row already in the
    # verified state is left exactly as it is. Owner-confirmed is an extra
    # flag, never a third legal stamp, and only an attested in-app capture
    # can set it — a later community scan cannot clear it.
    if is_owner_attested(scan):
        row["owner_confirmed"] = True
    if state_for_row(row) != STATE_VERIFIED:
        row["status"] = "verified"
        row["source"] = OWNER_SCAN_SOURCE if is_owner_attested(scan) else SCAN_SOURCE

    # Freshness: monotone. ISO dates compare lexicographically.
    date = _scan_date(scan)
    if date is not None:
        existing = row.get("imagery_date")
        if not isinstance(existing, str) or date > existing:
            row["imagery_date"] = date
    return row


def merge_scans(dataset, scans):
    """(merged dataset, scan meta by place key).

    The merged dataset is the pre-catalogue rows plus every scan's upgrades;
    meta carries {"scan_count", "last_scanned"} for each scanned place so the
    map can attach the provenance line. Total: a malformed dataset or scan
    list merges to whatever is usable, never an error.
    """
    merged = dict(dataset) if isinstance(dataset, dict) else {}
    meta = {}
    if not isinstance(scans, list):
        return merged, meta
    for scan in scans:
        if not isinstance(scan, dict) or _scan_date(scan) is None:
            continue
        if not isinstance(scan.get("verdicts"), dict):
            continue
        key = _place_key(merged, scan)
        merged[key] = _upgrade_row(merged.get(key), scan)
        entry = meta.setdefault(str(key), {"scan_count": 0, "last_scanned": ""})
        entry["scan_count"] += 1
        entry["last_scanned"] = max(entry["last_scanned"], _scan_date(scan))
    return merged, meta
