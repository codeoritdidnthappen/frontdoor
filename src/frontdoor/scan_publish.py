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

Matching: which business a door belongs to is #341's field work, and which
catalogued place that business is was decided by #346's ``entrance_matching
match`` pass against the map's own 40 m distance gate, with an audit trail and
its own tests. This module READS that decision out of
``data/entrance_identification.json`` and never re-derives it -- two matchers
would give one door two answers, and the one with less evidence would win half
the time. It adds exactly two rules of its own, both refusals: a
low-confidence identification is published with no place, because a pin states
the business as fact; and a matched place the published catalogue does not
carry is keyed but draws no pin, rather than being handed display fields the
catalogue is not allowed to keep (#242). Every entrance appears in the
matching report with the basis it was decided on. A record on the wrong
storefront is a worse failure than a record on no storefront.

The captures are repo-external (D-018), so the photo root is an argument.
Nothing here has a default that points outside the repository.

Run as a tool:

    python -m frontdoor.scan_publish --photos <capture root> --cache <cache dir>
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

from frontdoor.faceblur import JPEG_QUALITY, process_upload
from frontdoor.manifest import read_manifest
from frontdoor.scan_records import (
    DEFAULT_PUBLISHED_SCANS_PATH,
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
    rejected_criteria,
)
from frontdoor.split import InvalidEntranceId, assign_split, canonical_entrance_id

logger = logging.getLogger(__name__)

#: What the contributor field says for a record this path writes: an on-site
#: capture by the project's own operator, not a community upload.
SCAN_CONTRIBUTOR = "on_site_capture"

#: Spend cap for the whole publication run, not the live /screen default of $1.
#: 46 entrances at 5-7 views each is around 245 images; at the conservative
#: $0.05-per-image estimate the engine books roughly $12. Retries (see
#: ASSESSMENT_ATTEMPTS) book against the same cap, so a run where every
#: entrance needed all three attempts would book about $37 and would be stopped
#: by this cap part-way -- which is the intent: the cap is a ceiling on what
#: one run may spend without a person looking at it again, and the real
#: measured cost of a clean run is a few dollars.
PUBLISH_MAX_USD_PER_RUN = 25.0

#: The reviewable entrance-to-place matching report (AC4): one entry per
#: published entrance, naming the place it was matched to and how, or saying
#: why it was left unmatched.
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


#: What a criterion the assessment never produced is written as.
#:
#: The engine's summary carries None for every criterion when the response was
#: refused, and a null in a published record is a verdict nobody can read: it
#: is not `absent`, not `not_visible`, and a consumer has to guess which. This
#: is the word the map already renders for exactly this case
#: (map_states.OBSERVATION_NOT_ASSESSED), so the record says what the map shows.
NOT_ASSESSED = "not_assessed"


def _assessment_result(entrance_id, screening, captures, faces_blurred):
    """The cacheable record of one entrance's assessment."""
    assessment = screening.assessments[0]
    criteria = assessment.criteria or {}
    verdicts, confidences = {}, {}
    for key in CRITERIA_KEYS:
        verdict = screening.summary[key].verdict
        verdicts[key] = verdict if isinstance(verdict, str) else NOT_ASSESSED
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
        # TICK-399: a rejected reply is a failure of the call, not the model
        # abstaining, and a published record has to be able to say which. A
        # verdict of NOT_ASSESSED beside failure "rejected" is an answer this
        # engine threw away; the same word beside failure null is an entrance
        # nobody could see.
        "failure": assessment.failure,
        "attempts": assessment.attempts,
        "rejected_attempts": assessment.rejected_attempts,
        # Which criteria carry NOT_ASSESSED because their answer was refused,
        # as opposed to never having been seen. Published on the record.
        "verdict_failures": rejected_criteria(assessment),
    }


def verdict_count(result):
    """How many criteria this assessment actually produced a verdict for."""
    verdicts = result.get("verdicts") or {}
    return sum(
        1 for key in CRITERIA_KEYS
        if verdicts.get(key) not in (None, NOT_ASSESSED)
    )


def _result_rank(result):
    """How good an attempt is; bigger is better, compared as a tuple.

    Verdicts first, then a clean reply over a refused one. The second term is
    not a tie-break nicety: an attempt that recovered all four criteria out of
    a reply whose ADA half was refused still carries an error, and a result
    carrying an error is never cached -- so preferring it over a later clean
    attempt with the same four verdicts costs the next run the whole entrance
    again, and publishes a record that says it failed when a clean answer was
    in hand.
    """
    return (verdict_count(result), 0 if result.get("error") else 1)


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


#: How many times one entrance's assessment is attempted before it is recorded
#: as having produced nothing.
#:
#: The failures this absorbs are the model answering off-vocabulary rather than
#: anything about the door: about a third of the first pass came back with
#: `not_applicable` on the `handrails` criterion, which is the eight-check ADA
#: vocabulary bleeding into the four-criterion block the same prompt restricts
#: to present/absent/not_visible, or with a criteria object that was not
#: exactly the four. The engine is right to refuse both -- guessing what an
#: off-vocabulary answer meant is exactly the collapsing of `not_visible` into
#: `absent` this project forbids -- so the fix here is to ask again rather than
#: to reinterpret, and to publish nothing for the door if it keeps happening.
#:
#: TICK-399 moved that idea into the engine, where `/screen` and the eval get
#: it too: `ScreeningConfig.response_attempts` retries a rejected reply, and
#: the engine now keeps the criteria a rejected reply DID validate instead of
#: discarding all four. This loop stays as the outer net -- it re-runs the
#: whole entrance, privacy pass included, and re-enters the sealed guard each
#: time -- but it now has much less to catch, and it keeps the best attempt
#: rather than the last.
ASSESSMENT_ATTEMPTS = 3


def assess_publishable(entrances, *, get_capture, engine, cache_dir=None,
                       attempts=ASSESSMENT_ATTEMPTS):
    """Assess each publishable entrance exactly once, caching as it goes.

    A cached entrance is not re-assessed, so a run interrupted part-way costs
    nothing to resume. A failed assessment is deliberately NOT cached: it has
    no verdicts to publish, and the next run should retry it rather than
    inherit the failure.

    Every attempt goes through ``assess_entrance``, so the sealed refusal is
    re-run on each one; a retry is a new call into the same guard, never a way
    around it.
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
        best = None
        for attempt in range(1, max(1, attempts) + 1):
            screening = assess_entrance(
                engine, entrance_id, images, publishable=publishable
            )
            result = _assessment_result(
                entrance_id, screening, captures, faces_blurred)
            # Keep the best attempt, not the last one (TICK-399). Since the
            # engine recovers the criteria a rejected reply did validate, a
            # later attempt can carry FEWER verdicts than an earlier one, and
            # publishing the last would throw away ground the first held.
            if best is None or _result_rank(result) > _result_rank(best):
                best = result
            # A run over 46 entrances takes tens of minutes; without this the
            # only sign of a failing assessment is a cache entry that never
            # appears.
            logger.info(
                "assessed %s over %d view(s), attempt %d/%d: %s (%d/%d verdicts)",
                entrance_id, len(images), attempt, max(1, attempts),
                result["error"] or "ok",
                verdict_count(result), len(CRITERIA_KEYS),
            )
            if result["error"] is None:
                break
        result = best
        results[entrance_id] = result
        if result["error"] is None:
            _write_cache(cache_dir, entrance_id, result)
    return results


# --- entrance-to-place matching ----------------------------------------------

#: The committed identification file (#341) and the match decisions #346's
#: `entrance_matching match` pass wrote onto it. This module CONSUMES that
#: decision, it does not re-decide it: which business a door belongs to is
#: field work, and which catalogued place that business is was decided by a
#: pass with the map's own distance gate, an audit trail and its own tests.
#: Re-deriving either here would give the same door two answers.
DEFAULT_IDENTIFICATION_PATH = "data/entrance_identification.json"

#: Identification confidences a pin may be built on. #341 grades a reading
#: `high` (surveyed on foot, or the name read unambiguously), `medium`, or
#: `low` (a single partly redacted source, or a name assembled from
#: corroborating text). A `low` reading is a real possibility, not a fact, and
#: a pin does not render possibilities: the map would show the business named
#: and scanned on-site with nothing on the card saying the name was a guess.
#: So a low-confidence identification is published as an unmatched record --
#: the scan is kept, the claim about whose door it is, is not.
PINNABLE_CONFIDENCES = frozenset({"high", "medium"})


def _place_location(row):
    """A catalogue row's coordinates, or None when it carries none."""
    location = row.get("location") if isinstance(row, dict) else None
    if not isinstance(location, dict):
        return None
    lat, lng = location.get("lat"), location.get("lng")
    for value in (lat, lng):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
    return {"lat": float(lat), "lng": float(lng)}


class MatchBasis:
    """Why an entrance did or did not become a pin. Report vocabulary only."""

    LOW_CONFIDENCE = "low_confidence_identification"
    NO_IDENTIFICATION_RECORD = "no_identification_record"
    NOT_IN_CATALOGUE = "place_not_in_published_catalogue"
    NO_VERDICTS = "assessment_produced_no_verdicts"


def load_identifications(path=DEFAULT_IDENTIFICATION_PATH):
    """Entrance ID -> its identification record, from the committed file."""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScanPublishError(f"entrance identifications unreadable: {exc}") from exc
    entrances = document.get("entrances") if isinstance(document, dict) else None
    if not isinstance(entrances, dict):
        raise ScanPublishError(
            "entrance identifications must be an object with an 'entrances' map"
        )
    records = {}
    for entrance_id, record in entrances.items():
        if not isinstance(record, dict):
            continue
        try:
            records[canonical_entrance_id(entrance_id)] = record
        except InvalidEntranceId:
            continue
    return records


def _catalogue_row(catalogue, place_id):
    row = (catalogue or {}).get(place_id)
    return row if isinstance(row, dict) else None


def match_entrance(entrance_id, identification, catalogue, *, assessed=True):
    """One matching decision, with the provenance it was decided on (AC4).

    The decision is read, never re-made. Five outcomes, and every one of them
    records the basis so a reviewer can tell them apart:

    * the assessment produced no verdicts -- unmatched, because the tier a
      matched record carries says a scan of this door is what upgraded the
      pin, and there is no scan;
    * no identification record at all -- the entrance is not in #341's file;
    * an identification the match pass could not resolve to a place -- the
      pass's own recorded reason is carried through verbatim;
    * a resolved place whose identification is low confidence -- unmatched,
      because a pin states the business as fact (see PINNABLE_CONFIDENCES);
    * a resolved place -- matched, carrying the pass's ``how`` unchanged.

    ``place_ref`` names the place and, ONLY where the committed catalogue
    already carries them, its name and coordinates. Nothing is invented and no
    display field is copied out of a live sweep: a matched place the published
    catalogue does not carry yet is matched and says so in ``renderable``,
    rather than being given a name and a location from somewhere the
    catalogue is not allowed to keep them (#242).
    """
    entry = {
        "entrance_id": entrance_id,
        "matched": False,
        "place_ref": None,
        "renderable": False,
        "identification": None,
        "how": None,
        # Why this entrance is not a pin, in every case that is not one --
        # including a match whose place the published catalogue cannot render.
        # `matched` says whether a place was decided; this says why the map
        # shows nothing, and they are different questions.
        "not_pinnable_reason": None,
        "basis": "",
    }
    if not assessed:
        entry["not_pinnable_reason"] = MatchBasis.NO_VERDICTS
        entry["basis"] = (
            "the assessment of this entrance produced no verdicts, so there "
            "is nothing a pin could report; the record is published with no "
            "place rather than stamping a business scanned on no observation"
        )
        return entry
    if identification is None:
        entry["basis"] = (
            "no record for this entrance in the committed identification file, "
            "so there is no business and no place to key a record to"
        )
        entry["not_pinnable_reason"] = MatchBasis.NO_IDENTIFICATION_RECORD
        return entry

    confidence = identification.get("confidence")
    entry["identification"] = {
        "status": identification.get("status"),
        "name": identification.get("name"),
        "confidence": confidence,
    }
    place_match = identification.get("place_match") or {}
    place_id = identification.get("place_id")

    if not place_id:
        reason = place_match.get("unmatched_reason") or "not_matched"
        entry["not_pinnable_reason"] = reason
        entry["basis"] = (
            "the match pass left this entrance without a place "
            f"({reason}): {place_match.get('detail') or 'no detail recorded'}"
        )
        return entry

    entry["how"] = place_match.get("how")
    if confidence not in PINNABLE_CONFIDENCES:
        entry["not_pinnable_reason"] = MatchBasis.LOW_CONFIDENCE
        entry["basis"] = (
            f"identified as {identification.get('name')!r} at confidence "
            f"{confidence!r} and matched to {place_id} by the match pass, but a "
            "pin states the business as fact, so the scan is published with no "
            "place rather than as a confident claim about whose door it is"
        )
        return entry

    row = _catalogue_row(catalogue, place_id)
    location = _place_location(row) if row else None
    name = row.get("name") if row else None
    place_ref = {"place_id": place_id}
    if isinstance(name, str) and name.strip():
        place_ref["name"] = name
    if location is not None:
        place_ref.update(location)
    entry.update({
        "matched": True,
        "place_ref": place_ref,
        "renderable": bool(location),
        "basis": _matched_basis(identification, place_id, place_match, location),
    })
    if location is None:
        entry["not_pinnable_reason"] = MatchBasis.NOT_IN_CATALOGUE
    return entry


def _matched_basis(identification, place_id, place_match, location):
    """The sentence a reviewer reads for a matched entrance."""
    how = place_match.get("how") or {}
    anchor = how.get("anchor") or "identification"
    if anchor == "identification":
        evidence = how.get("detail") or "resolved against the committed catalogue"
    elif anchor == "address_geocode":
        evidence = (
            f"the geocoded street number is {how.get('distance_m')} m from "
            f"{how.get('matched_name')!r}"
        )
    elif anchor == "walk_order_bracket":
        between = " and ".join(how.get("anchor_between") or [])
        evidence = (
            f"bracketed by {between} over {how.get('bracket_span_m')} m and "
            f"{how.get('distance_m')} m from {how.get('matched_name')!r}"
        )
    else:
        evidence = f"matched by {anchor}"
    tail = (
        "" if location is not None else
        "; the published catalogue does not carry this place's name and "
        "location, so the record is keyed to it but draws no pin yet"
    )
    return (
        f"identified as {identification.get('name')!r} "
        f"({identification.get('confidence')} confidence, "
        f"{', '.join(identification.get('basis') or ['unrecorded'])}) and "
        f"matched to {place_id} by the match pass: {evidence}{tail}"
    )


def match_entrances(entrance_ids, identifications, catalogue, *, unassessed=()):
    """One matching entry for EVERY entrance, matched or not (AC4)."""
    unassessed = frozenset(unassessed)
    return [
        match_entrance(
            entrance_id, (identifications or {}).get(entrance_id), catalogue,
            assessed=entrance_id not in unassessed,
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
            verdict_failures=result.get("verdict_failures"),
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
        "--identifications",
        default=DEFAULT_IDENTIFICATION_PATH,
        help="the committed entrance identification file whose match "
             "decisions this publication keys its records to (#341, #346)",
    )
    parser.add_argument("--dataset", default="data/precatalogue.json")
    parser.add_argument("--out", default=DEFAULT_PUBLISHED_SCANS_PATH)
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

    try:
        identifications = load_identifications(args.identifications)
    except ScanPublishError as exc:
        print(exc, file=sys.stderr)
        return 1
    try:
        catalogue = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"place catalogue unreadable: {exc}", file=sys.stderr)
        return 1
    # Unassessed means NO verdicts, not "the reply had something wrong with
    # it" (TICK-399): an entrance whose reply lost one criterion and kept
    # three has been assessed, and dropping it out of matching would take the
    # whole door off the map over one refused field.
    failed = sorted(e for e, r in assessments.items() if not verdict_count(r))
    matches = match_entrances(
        assessments, identifications, catalogue, unassessed=failed
    )
    records = build_records(assessments, matches)
    write_store(args.out, records, replace=args.replace)
    write_matches(args.matches, matches)

    matched = sum(1 for entry in matches if entry["matched"])
    renderable = sum(1 for entry in matches if entry.get("renderable"))
    print(
        f"published {len(records)} scan records ({matched} matched to a place, "
        f"{renderable} of them pinnable on the published catalogue, "
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
