"""Community scan records: the store the map merges with the pre-catalogue (TICK-262, #270).

POST /screen assesses and deliberately retains nothing. The publish step
(frontdoor_server.scan_view) is the explicit-consent path that DOES retain:
privacy-processed image bytes go to object storage, and one record per scan is
appended here — an append-friendly JSONL file (one JSON object per line), path
from FRONTDOOR_SCANS, default data/scans.jsonl, the same env-plus-default shape
as the map dataset. JSONL because the write is one line: append_scan borrows the
manifest's newline discipline (frontdoor.manifest._require_newline_terminated)
so a torn earlier write is recovered (the incomplete last line is dropped)
rather than silently concatenating two records into one unparseable line.

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
    STATE_SCANNED,
    _observation,
    _valid_location,
    state_for_row,
)

SCANS_ENV = "FRONTDOOR_SCANS"
DEFAULT_SCANS_PATH = "data/scans.jsonl"

#: The curated on-site publication (TICK-333): the study's own operator-captured
#: entrances, written by `python -m frontdoor.scan_publish` and COMMITTED.
#:
#: Deliberately not the same file as the runtime store above. Since #339 the
#: server appends what a phone publishes to a mounted volume that is not the
#: repository at all, so one path for both would make an accidental local
#: publish indistinguishable from the study's own records -- and a deploy, which
#: replaces the container filesystem, would either lose the curated set or need
#: the volume seeded before first start. Two files: this one ships inside the
#: image and is reviewable in a diff, that one is runtime state on the volume,
#: and /map/data reads both.
PUBLISHED_SCANS_ENV = "FRONTDOOR_PUBLISHED_SCANS"
DEFAULT_PUBLISHED_SCANS_PATH = "data/published_scans.jsonl"

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
logger = logging.getLogger(__name__)


class ScanRecordError(ValueError):
    """Raised when an append would corrupt the store."""


@dataclass(frozen=True)
class ScanStoreLoad:
    """What a scan-store read actually did, including the lines it skipped."""

    records: list
    error: str | None
    skipped: int


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
                    capture_kind=None, attested=False, blur_regions=None,
                    verdict_failures=None, assessment_ref=None,
                    evidence_boxes=None, evidence_boxes_searched=False):
    """One scan record, with a fresh scan_id.

    blur_regions, when given, is one list per uploaded frame (upload order)
    of the {"x", "y", "w", "h"} rectangles the privacy pass pixelated in that
    frame (#350). Additive: records written before it carry no key.

    assessment_ref, when given, names the assessment these verdicts came
    from (TICK-435): the sha256 of the privacy-processed photograph, the
    engine version that answered, and the timestamp of that answer. Since one
    photograph has exactly one assessment, a publish can carry a verdict
    produced earlier, and without this the record could not say so. Additive:
    records written before it carry no key.

    verdict_failures maps a criterion to why the engine's answer for it was
    refused (TICK-399). A null verdict beside an entry here is an answer that
    was thrown away; a null verdict with no entry is a feature nobody could
    see. Also additive, and omitted entirely when nothing was refused, so a
    clean record is byte-identical to one written before this existed.

    evidence_boxes maps a criterion to the one rectangle a person can be
    pointed at for it (TICK-467): {"frame", "x", "y", "w", "h", "label",
    "score"}, with the geometry in the same frame blur_regions uses -- the
    pixels of the stored image, orientation applied and decode capped -- and
    "frame" the index into image_keys of the photograph it is on. Also
    additive and also omitted when empty.

    A criterion with nothing to point at is SIMPLY NOT IN THE MAPPING. It is
    never a null, never an empty box and never a zero score, because each of
    those is a shape a reader could mistake for a finding, and a missing box
    is not an absent feature -- it is a feature nothing could be pointed at.
    Verdicts are not consulted when these are produced and are not affected by
    them; see frontdoor.evidence_boxes.

    evidence_boxes_searched says the detector RAN on this entrance, and it is
    the only reason the sentence above can be said out loud. Every criterion
    is looked for on every entrance, so this one boolean carries the whole
    difference between "we looked here and could not point at one" and
    "nobody looked" -- a person at a door would hear those very differently,
    and the mapping alone says neither. Deliberately per record and not per
    criterion: a per-criterion "searched but empty" value would be exactly the
    shape that made this detector worse than useless as a scorer. Written only
    when true, so a record from a run with no detector is byte-identical to
    one written before any of this existed.
    """
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
    if blur_regions is not None:
        record["blur_regions"] = [list(regions) for regions in blur_regions]
    if verdict_failures:
        record["verdict_failures"] = dict(verdict_failures)
    if assessment_ref:
        record["assessment_ref"] = dict(assessment_ref)
    if evidence_boxes:
        record["evidence_boxes"] = {
            key: dict(box) for key, box in evidence_boxes.items()
        }
    if evidence_boxes_searched:
        record["evidence_boxes_searched"] = True
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

    Same discipline as the manifest: a store whose last line was never finished
    means an earlier write was interrupted. Truncate after the last complete
    line (logged) and then append, so one torn write cannot wedge the store.
    The parent directory must already exist: inventing it here would hide a
    missing volume the same way mkdir hid the /data incident.
    The check and the write happen under one lock so two threads in the same
    worker cannot interleave them.
    """
    path = Path(path)
    line = json.dumps(record, sort_keys=True, separators=(",", ":"))
    with _append_lock:
        if path.exists() and path.stat().st_size and path.read_bytes()[-1:] != b"\n":
            data = path.read_bytes()
            last_nl = data.rfind(b"\n")
            logger.warning(
                "scan store %s does not end with a newline; a previous append "
                "was interrupted. Truncating after the last complete line.",
                path,
            )
            path.write_bytes(b"" if last_nl < 0 else data[: last_nl + 1])
        with open(path, "a", encoding="utf-8", newline="") as handle:
            handle.write(line + "\n")


def load_scan_store(path):
    """Parseable records plus the error/skip counts a silent [] used to hide.

    Missing file with a present parent is the empty store (nobody published).
    A missing parent is a missing volume. Unparseable lines are skipped and
    logged, never silent; the rest of the store still loads.
    """
    try:
        store = Path(path)
    except TypeError:
        error = "scans unreadable: invalid path"
        logger.warning(error)
        return ScanStoreLoad([], error, 0)
    if not store.parent.exists():
        error = f"scans unreadable: parent directory missing ({store.parent})"
        logger.warning(error)
        return ScanStoreLoad([], error, 0)
    try:
        text = store.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ScanStoreLoad([], None, 0)
    except (OSError, ValueError) as exc:
        error = f"scans unreadable: {exc}"
        logger.warning(error)
        return ScanStoreLoad([], error, 0)
    records = []
    skipped = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            logger.warning("skipped unparseable scan line in %s", store)
            continue
        if isinstance(record, dict):
            records.append(record)
        else:
            skipped += 1
            logger.warning("skipped non-object scan line in %s", store)
    return ScanStoreLoad(records, None, skipped)


def load_scan_records(path):
    """Every parseable record; [] when the store is missing or unreadable.

    Total on purpose, like the map dataset and the external side files: the
    map must render with or without scans, and one corrupt line must not take
    every other scan off the map with it. Callers that need the skip/error
    counts use load_scan_store.
    """
    return load_scan_store(path).records


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

    Confidences arrive on the engine's 0-100 scale and STAY on it — the same
    scale map_states.CONFIDENCE_SCALE states publicly, and the same scale the
    pre-catalogue rows this merges into are already on. Non-numbers pass
    through as None.

    TICK-462, #462: this used to divide anything above 1 by 100, and it was
    the only producer on the endpoint that rescaled. Because the merge
    replaces a criterion entry only when the scan RAISES the observation, the
    rescaled values landed precisely on the observations the model was surest
    of: one pin served 20.0 beside 0.85, and anything rendering the field as
    a percentage showed that 0.85 as 1%. The producer is fixed here rather
    than at the edge, because a clamp at the edge makes a wrong number render
    correctly and leaves it wrong.
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
    if state_for_row(row) != STATE_SCANNED:
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
