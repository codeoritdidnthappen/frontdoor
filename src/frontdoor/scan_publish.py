"""Publish on-site scan results for the non-sealed entrances (TICK-333, #333).

The operator stood at and photographed 64 entrances. Eighteen of them are the
sealed evaluation split and stay off the map until results freeze
(docs/unsealing-run.md); this module publishes the other 46 and cannot publish
those eighteen.

Sealed discipline, structural rather than remembered:

  * the publishable set is DERIVED, never supplied. ``publishable_entrances``
    walks the manifest and keeps an entrance only when
    ``frontdoor.split.assign_split`` says it is not sealed. No argument adds an
    entrance to that set, and there is no ``allow_sealed`` flag anywhere in
    this module.
  * ``assess_entrance`` is the only function here that reaches the screening
    engine, and it re-resolves the split with ``assign_split`` before the
    engine is touched. An entrance that reaches a model call has therefore
    passed the committed seed twice.
  * ``ScreeningEngine.screen_entrance_integrated`` resolves the split a third
    time and cannot be told otherwise.

  Publishing the sealed eighteen after the freeze is a separate change, against
  a doorway that does not exist yet -- which is what docs/unsealing-run.md
  describes and what this module deliberately does not provide.

Privacy: every view goes through ``frontdoor.faceblur.process_upload`` -- the
same ingest pass POST /screen runs on an upload -- before the engine sees it,
so the model is never sent an original, whatever a capture ID suggests has
already been processed. No image bytes are published either: the records carry
no image keys, so nothing written here can reference an original by accident.

Matching: an entrance becomes a record keyed to a place only when its surveyed
door coordinates land within ``DEFAULT_MATCH_DISTANCE_M`` of exactly one
pre-catalogue place whose name corresponds -- the same distance-plus-fuzzy-name
rule the external side files and the scan merge already use. No coordinates, no
candidate, or several candidates leave the entrance UNMATCHED and say so in the
matching report. A record on the wrong storefront is a worse failure than a
record on no storefront.

The surveyed coordinates and the entrance-to-business survey are repo-external
(D-018), so both the photo root and the survey file are arguments. Nothing here
has a default that points outside the repository.

Run as a tool:

    python -m frontdoor.scan_publish --photos <capture root> \\
        --entrance-locations <survey file> --cache <cache dir>
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import cv2
import numpy as np

# The map's own matching rule, imported rather than re-derived so this module
# cannot drift from the merge that will later key these records to a pin.
from frontdoor.external_data import (
    DEFAULT_MATCH_DISTANCE_M,
    _haversine_m,
    _names_match,
)
from frontdoor.faceblur import JPEG_QUALITY, process_upload
from frontdoor.manifest import read_manifest
from frontdoor.scan_records import (
    DEFAULT_SCANS_PATH,
    ScanRecordError,
    append_scan,
    load_scan_records,
    new_scan_record,
)
from frontdoor.screening import (
    CRITERIA_KEYS,
    ScreeningConfig,
    ScreeningEngine,
    SpendCapError,
)
from frontdoor.split import InvalidEntranceId, assign_split, canonical_entrance_id

logger = logging.getLogger(__name__)

#: What the contributor field says for a record this path writes: an on-site
#: capture by the project's own operator, not a community upload.
SCAN_CONTRIBUTOR = "on_site_capture"

#: Spend cap for the whole publication run, not the live /screen default of $1.
#: 46 entrances at 5-7 views each is around 245 images; at the conservative
#: $0.05-per-image estimate the engine books roughly $12.
PUBLISH_MAX_USD_PER_RUN = 20.0

#: The reviewable entrance-to-place matching report (AC4): one entry per
#: published entrance, naming the place it was matched to and how, or saying
#: why it was left unmatched.
DEFAULT_PUBLISHED_PATH = "data/published_scans.jsonl"
DEFAULT_MATCHES_PATH = "data/scan_matches.json"

#: Longest edge of a view as it is SENT to the model. The 2026-09-04 captures
#: are 24 MP (5712x4284); five of those in one integrated call is around 30 MB
#: of base64 against the request-size ceiling, and a run of them stalled for
#: minutes per entrance on upload alone. The vision API scales an image down to
#: about this before the model reads it, so the extra megabytes buy no detail --
#: and the pilot that measured the integrated mode's accuracy ran on 1536x2048
#: captures, which this leaves untouched. The privacy pass still runs at full
#: resolution; only the copy the model sees is reduced.
MODEL_VIEW_LONG_EDGE = 1568


class ScanPublishError(ValueError):
    """Raised when the publication cannot produce an honest record."""


class NotPublishableError(ScanPublishError):
    """Raised when an entrance may not be assessed by this path.

    Either it is in the sealed split, or it is not in the set derived from the
    manifest and the committed seed. Both are refusals, not filters: the caller
    gets an exception rather than a quietly skipped entrance.
    """


# --- the publishable set -----------------------------------------------------


def publishable_entrances(manifest_path):
    """Every manifest entrance this path may assess, canonical and sorted.

    The split comes from ``assign_split`` and the committed seed, never from
    the manifest's ``split`` cell (which is a cache) and never from a caller.
    An entrance ID the seed cannot classify is left out: an identifier whose
    split is ambiguous is treated as one that must not be assessed.
    """
    publishable = set()
    for row in read_manifest(manifest_path):
        raw = (row.get("entrance_id") or "").strip()
        try:
            entrance_id = canonical_entrance_id(raw)
        except InvalidEntranceId:
            logger.warning(
                "manifest row %r has an entrance ID the split seed cannot "
                "classify; excluded from the publishable set",
                row.get("capture_id"),
            )
            continue
        if assign_split(entrance_id) == "sealed":
            continue
        publishable.add(entrance_id)
    return sorted(publishable)


def entrance_captures(manifest_path):
    """Publishable entrance ID -> its capture IDs, sorted, from the manifest.

    The keys of this mapping ARE the publishable set, so the loop that assesses
    and the gate that refuses read the same derivation.
    """
    publishable = set(publishable_entrances(manifest_path))
    captures = {}
    for row in read_manifest(manifest_path):
        try:
            entrance_id = canonical_entrance_id(row["entrance_id"])
        except InvalidEntranceId:
            continue
        if entrance_id not in publishable:
            continue
        captures.setdefault(entrance_id, []).append(row["capture_id"])
    return {eid: sorted(ids) for eid, ids in sorted(captures.items())}


# --- assessment --------------------------------------------------------------


def assess_entrance(engine, entrance_id, images, *, publishable):
    """One integrated multi-view assessment. The only call into the engine here.

    Both refusals happen before the engine is reached, so a sealed identifier
    never becomes a model call, an image upload or a token of spend.
    """
    entrance_id = canonical_entrance_id(entrance_id)
    if assign_split(entrance_id) == "sealed":
        raise NotPublishableError(
            f"entrance {entrance_id} is in the sealed split; sealed entrances "
            "are published after results freeze, not by this path "
            "(docs/unsealing-run.md)"
        )
    if entrance_id not in publishable:
        raise NotPublishableError(
            f"entrance {entrance_id} is not in the publishable set derived "
            "from the manifest and the committed split seed"
        )
    return engine.screen_entrance_integrated(entrance_id, images)


def _assessment_result(entrance_id, screening, captures, faces_blurred):
    """The cacheable record of one entrance's assessment."""
    assessment = screening.assessments[0]
    criteria = assessment.criteria or {}
    verdicts, confidences = {}, {}
    for key in CRITERIA_KEYS:
        verdicts[key] = screening.summary[key].verdict
        confidence = (criteria.get(key) or {}).get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            confidence = None
        confidences[key] = confidence
    return {
        "entrance_id": entrance_id,
        # The capture date the card's freshness comes from: the latest moment
        # the operator was at this door, straight off the sidecars.
        "captured_at": max(capture.sidecar["captured_at"] for capture in captures),
        "view_count": len(captures),
        "faces_blurred": faces_blurred,
        "mode": screening.mode,
        "verdicts": verdicts,
        "confidences": confidences,
        "face_check": assessment.face_check,
        "error": assessment.error,
    }


def _fit_for_the_model(image_bytes):
    """One privacy-processed view, reduced to the size the model reads.

    Runs AFTER the privacy pass, never instead of it: faces are detected and
    blurred at capture resolution, and this only shrinks the copy that goes
    over the wire.
    """
    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ScanPublishError("a privacy-processed view could not be decoded")
    scale = MODEL_VIEW_LONG_EDGE / max(image.shape[:2])
    if scale >= 1.0:
        return image_bytes
    resized = cv2.resize(image, None, fx=scale, fy=scale,
                         interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", resized,
                               [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise ScanPublishError("a privacy-processed view could not be re-encoded")
    return encoded.tobytes()


def _cache_path(cache_dir, entrance_id):
    return None if cache_dir is None else Path(cache_dir) / f"{entrance_id}.json"


def _read_cache(cache_dir, entrance_id):
    path = _cache_path(cache_dir, entrance_id)
    if path is None or not path.is_file():
        return None
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return cached if isinstance(cached, dict) else None


def _write_cache(cache_dir, entrance_id, result):
    path = _cache_path(cache_dir, entrance_id)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def assess_publishable(entrances, *, get_capture, engine, cache_dir=None):
    """Assess each publishable entrance exactly once, caching as it goes.

    A cached entrance is not re-assessed, so a run interrupted part-way costs
    nothing to resume. A failed assessment is deliberately NOT cached: it has
    no verdicts to publish, and the next run should retry it rather than
    inherit the failure.
    """
    publishable = frozenset(entrances)
    results = {}
    for entrance_id, capture_ids in entrances.items():
        cached = _read_cache(cache_dir, entrance_id)
        if cached is not None:
            results[entrance_id] = cached
            continue
        captures = [get_capture(capture_id) for capture_id in capture_ids]
        images, faces_blurred = [], 0
        for capture in captures:
            # Unconditional: the engine is never handed a byte that has not
            # been through the privacy pass, whatever the capture ID says.
            processed = process_upload(capture.image)
            images.append(_fit_for_the_model(processed.image_bytes))
            faces_blurred += processed.face_count
        screening = assess_entrance(
            engine, entrance_id, images, publishable=publishable
        )
        result = _assessment_result(entrance_id, screening, captures, faces_blurred)
        results[entrance_id] = result
        if result["error"] is None:
            _write_cache(cache_dir, entrance_id, result)
        # A run over 46 entrances takes tens of minutes; without this the only
        # sign of a failing assessment is a cache entry that never appears.
        logger.info(
            "assessed %s over %d view(s): %s",
            entrance_id, len(images), result["error"] or "ok",
        )
    return results


# --- entrance-to-place matching ----------------------------------------------


def load_entrance_locations(path):
    """Surveyed door coordinates: entrance ID -> {"name", "lat", "lng"}.

    The survey file is repo-external (D-018). Entries without usable
    coordinates are dropped, which leaves the entrance unmatched rather than
    matched on a guess.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScanPublishError(f"entrance locations unreadable: {exc}") from exc
    if not isinstance(raw, dict):
        raise ScanPublishError("entrance locations must be a JSON object")
    locations = {}
    for entrance_id, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        lat, lng = entry.get("lat"), entry.get("lng", entry.get("lon"))
        if not _is_number(lat) or not _is_number(lng):
            continue
        try:
            entrance_id = canonical_entrance_id(entrance_id)
        except InvalidEntranceId:
            continue
        name = entry.get("name", entry.get("business"))
        locations[entrance_id] = {
            "name": name if isinstance(name, str) else "",
            "lat": float(lat),
            "lng": float(lng),
        }
    return locations


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _place_location(row):
    location = row.get("location") if isinstance(row, dict) else None
    if not isinstance(location, dict):
        return None
    lat, lng = location.get("lat"), location.get("lng")
    if not _is_number(lat) or not _is_number(lng):
        return None
    return {"lat": float(lat), "lng": float(lng)}


def match_entrance(entrance_id, location, catalogue,
                   *, max_distance_m=DEFAULT_MATCH_DISTANCE_M):
    """One matching decision, with the basis it was decided on.

    Accepts only an unambiguous match: exactly one catalogue place inside
    ``max_distance_m`` whose name corresponds. Zero candidates, several
    candidates, or no surveyed coordinates all return ``matched: False`` with
    the reason recorded in ``basis``.
    """
    entry = {
        "entrance_id": entrance_id,
        "matched": False,
        "place_ref": None,
        "distance_m": None,
        "basis": "",
    }
    if location is None:
        entry["basis"] = (
            "no surveyed door coordinates are recorded for this entrance, so "
            "there is nothing to match on"
        )
        return entry
    candidates = []
    for place_id, row in (catalogue or {}).items():
        place_location = _place_location(row)
        if place_location is None:
            continue
        distance = _haversine_m(
            location["lat"], location["lng"],
            place_location["lat"], place_location["lng"],
        )
        if distance > max_distance_m:
            continue
        name = row.get("name") if isinstance(row, dict) else None
        if not isinstance(name, str) or not name.strip():
            continue
        if location["name"] and not _names_match(location["name"], name):
            continue
        candidates.append((round(distance, 1), str(place_id), name, place_location))
    candidates.sort()
    if not candidates:
        entry["basis"] = (
            f"no catalogue place within {max_distance_m:.0f} m of the surveyed "
            "door whose name corresponds"
        )
        return entry
    if len(candidates) > 1:
        entry["basis"] = (
            f"{len(candidates)} catalogue places within {max_distance_m:.0f} m "
            "correspond by name, so the match is ambiguous and was not made"
        )
        return entry
    distance, place_id, name, place_location = candidates[0]
    entry.update({
        "matched": True,
        "distance_m": distance,
        # The place's own public identity and coordinates, never the surveyed
        # door's: the record names a catalogue place, it does not republish
        # the repo-external survey.
        "place_ref": {
            "place_id": place_id,
            "name": name,
            "lat": place_location["lat"],
            "lng": place_location["lng"],
        },
        "basis": (
            f"surveyed door is {distance:.1f} m from the catalogue place and "
            "the names correspond"
        ),
    })
    return entry


def match_entrances(entrance_ids, locations, catalogue,
                    *, max_distance_m=DEFAULT_MATCH_DISTANCE_M):
    """One matching entry for EVERY entrance, matched or not (AC4)."""
    return [
        match_entrance(
            entrance_id,
            (locations or {}).get(entrance_id),
            catalogue,
            max_distance_m=max_distance_m,
        )
        for entrance_id in sorted(entrance_ids)
    ]


# --- records -----------------------------------------------------------------


def build_records(assessments, matches):
    """One scan record per assessed entrance, in the existing record shape.

    ``image_keys`` is empty by design: this path publishes verdicts and dates,
    never bytes, so no original can be referenced and nothing needs
    quarantining.
    """
    by_entrance = {entry["entrance_id"]: entry for entry in matches}
    records = []
    for entrance_id in sorted(assessments):
        result = assessments[entrance_id]
        match = by_entrance.get(entrance_id) or {}
        records.append(new_scan_record(
            place_ref=match.get("place_ref"),
            created_at=result["captured_at"],
            verdicts=result["verdicts"],
            confidences=result["confidences"],
            faces_blurred=result["faces_blurred"],
            quarantined_count=0,
            image_keys=[],
            contributor=SCAN_CONTRIBUTOR,
            entrance_id=entrance_id,
        ))
    return records


def write_store(path, records, *, replace=False):
    """Write these records to the scan store, one JSONL line each.

    Refuses a store that already holds records unless ``replace`` says the
    curated publication is meant to supersede them -- appending a second
    publication onto the first would double every pin's scan count.
    """
    path = Path(path)
    if not replace and load_scan_records(path):
        raise ScanRecordError(
            f"{path} already holds scan records; pass --replace to supersede "
            "them, or point --out somewhere else"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    for record in records:
        append_scan(path, record)


def write_matches(path, matches):
    """Write the reviewable matching report."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(matches, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


# --- CLI ---------------------------------------------------------------------


def local_image_reader(photo_root, sidecar_dir):
    """Read capture bytes from a local mirror of the repo-external store.

    The sidecar names the file; the loader then verifies its hash against the
    manifest, so a substituted or truncated file raises rather than being
    screened.
    """
    photo_root, sidecar_dir = Path(photo_root), Path(sidecar_dir)

    def get_image(capture_id):
        sidecar = json.loads(
            (sidecar_dir / f"{capture_id}.json").read_text(encoding="utf-8")
        )
        return (photo_root / sidecar["image"]["path"]).read_bytes()

    return get_image


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m frontdoor.scan_publish",
        description=(
            "Assess every non-sealed entrance's on-site captures and write the "
            "scan records /map/data merges. Sealed entrances cannot be reached "
            "by this command."
        ),
    )
    parser.add_argument("--manifest", default="data/manifest.csv")
    parser.add_argument("--sidecars", default=None)
    parser.add_argument(
        "--photos",
        required=True,
        help="root of the repo-external capture store (D-018)",
    )
    parser.add_argument(
        "--entrance-locations",
        default=None,
        help="repo-external surveyed door coordinates; without it every "
             "entrance is published unmatched",
    )
    parser.add_argument("--dataset", default="data/precatalogue.json")
    parser.add_argument("--out", default=DEFAULT_PUBLISHED_PATH)
    parser.add_argument("--matches", default=DEFAULT_MATCHES_PATH)
    parser.add_argument("--cache", default=None)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    from frontdoor import storage

    storage._load_dotenv_once()
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print(
            "no ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) in the environment "
            "or .env; publishing makes live model calls and will not start "
            "without one. Nothing was read or written.",
            file=sys.stderr,
        )
        return 2

    from frontdoor.loader import DatasetLoader

    manifest_path = Path(args.manifest)
    sidecar_dir = (
        Path(args.sidecars) if args.sidecars else manifest_path.parent / "sidecars"
    )
    loader = DatasetLoader(
        manifest_path, sidecar_dir, get_image=local_image_reader(args.photos, sidecar_dir)
    )
    entrances = entrance_captures(manifest_path)
    engine = ScreeningEngine(
        config=ScreeningConfig(max_usd_per_run=PUBLISH_MAX_USD_PER_RUN)
    )
    try:
        assessments = assess_publishable(
            entrances,
            get_capture=loader.load,
            engine=engine,
            cache_dir=args.cache,
        )
    except SpendCapError as exc:
        print(exc, file=sys.stderr)
        return 1

    locations = (
        load_entrance_locations(args.entrance_locations)
        if args.entrance_locations else {}
    )
    try:
        catalogue = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"place catalogue unreadable: {exc}", file=sys.stderr)
        return 1
    matches = match_entrances(assessments, locations, catalogue)
    records = build_records(assessments, matches)
    write_store(args.out, records, replace=args.replace)
    write_matches(args.matches, matches)

    matched = sum(1 for entry in matches if entry["matched"])
    failed = sorted(e for e, r in assessments.items() if r["error"] is not None)
    print(
        f"published {len(records)} scan records ({matched} matched to a place, "
        f"{len(records) - matched} unmatched) from "
        f"{sum(r['view_count'] for r in assessments.values())} views; "
        f"estimated spend ${engine.spent_usd:.2f}; store {args.out}, "
        f"matching report {args.matches}"
    )
    if failed:
        print(
            f"{len(failed)} entrance(s) produced no verdicts and were not "
            f"cached: {', '.join(failed)}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
