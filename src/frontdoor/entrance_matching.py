"""Match each identified entrance to a catalogued place (TICK-346, #346).

#341 read the storefront signage and named the business behind 29 of the 46
non-sealed entrances. Only 6 of them resolved to a ``place_id``, because the
committed pre-catalogue had been swept over the Second Street district while
the 2026-09-04 walk went up Congress Avenue. A scan record with a name and no
place cannot become a pin, so #333 could publish 6. This module is the other
half: given a catalogue that now covers the walked blocks, decide which
catalogued place each identified door belongs to.

The gates are the map's own, and they are deliberately hard to pass:

* **Name.** ``frontdoor.external_data._names_match`` — the same comparison
  ``/map/data`` merges scan records with. Both sides must actually carry a
  name; the "nothing to compare, fall back to distance" branch is refused
  here, because for an entrance there is no independent location to fall
  back to.
* **Distance.** ``DEFAULT_MATCH_DISTANCE_M`` (40 m), unchanged. A candidate
  further than that from where the door is known to be is refused, never
  widened — putting an accessibility claim on the wrong front door is worse
  than leaving the door off the map.
* **Uniqueness.** Two candidates through both gates is an ambiguity, and an
  ambiguity stays unmatched. So is one place that two entrances both reach:
  a place cannot be two front doors.

**Where a door is** is the part #341 left open — no capture carries GPS and no
surveyed coordinate was ever persisted. Two kinds of evidence stand in, and
every match records which one it used:

* ``address_geocode`` — the street number recorded on foot or read off the
  transom, geocoded through OSM/Nominatim (``data/external/entrance_anchors``,
  a segregated ODbL side file). A point; distance is measured straight to it.
* ``walk_order_bracket`` — for a door with no readable number, the two nearest
  anchored doors either side of it *in the same day's walk*. The door is
  somewhere on the stretch of street between them, so distance is measured to
  that segment. Weaker evidence, and named as such in the output.

A door with neither — before the day's first anchor, or after its last — has
no location evidence at all, and a name on its own is not a match. It stays
unmatched with that reason recorded.

Two CLI paths reach the network; importing this module performs no I/O.
``anchors`` geocodes the read street numbers through Nominatim (free, no key,
one request a second). ``match`` runs the walked-blocks sweep through
``frontdoor.precatalogue`` and matches against its result in the same pass —
that is not an optimisation but the licensing posture: the catalogue rows this
ticket added hold the place_id alone, so the names they match on are resolved
at run time and never written down. See #242.
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from frontdoor.external_data import (
    DEFAULT_MATCH_DISTANCE_M,
    _haversine_m,
    _names_match,
    _normalize_name,
)

IDENTIFICATION_PATH = Path("data/entrance_identification.json")
ANCHORS_PATH = Path("data/external/entrance_anchors.json")
SIDECAR_DIR = Path("data/sidecars")
WALK_AREA_CONFIG = Path(__file__).with_name("walk_area.json")

#: "Ste 200", "Suite 100", "Unit 3", "#4" — a floor, not a front door.
SUITE_RE = re.compile(r"^(ste|suite|unit|#)\b", re.IGNORECASE)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_DELAY_S = 1.1  # the service's published one-request-a-second rule
NOMINATIM_USER_AGENT = "frontdoor-precatalogue (entrance address geocoding)"

OSM_ATTRIBUTION = (
    "Geocodes from OpenStreetMap via Nominatim (© OpenStreetMap "
    "contributors), licensed under the Open Database License (ODbL) 1.0. "
    "https://www.openstreetmap.org/copyright"
)
OSM_SEGREGATION = (
    "ODbL-licensed data stored as a segregated side table per the ODbL "
    "Collective Database Guideline. Do not merge these records into any "
    "proprietary dataset."
)

#: Every reason a door can end up with no place. Each names what was missing,
#: so "no catalogue entry" is never confused with "the catalogue has it and
#: the door is too far away" — those want different follow-up work.
UNMATCHED_REASONS = {
    "not_identified": "the entrance was never identified, so there is no name to match",
    "no_location_evidence": "no street number was read and no anchored door brackets this one in the day's walk; a name on its own is not a match",
    "no_catalogue_entry": "no catalogued place carries this business name",
    "outside_match_distance": "no catalogued place carrying this business name is within the map's match distance of the door",
    "ambiguous_candidates": "more than one catalogued place passes both gates",
    "place_claimed_by_another_entrance": "another entrance matched the same place, and a place cannot be two front doors",
}


# --- door locations ---------------------------------------------------------


def walk_days(sidecar_dir=SIDECAR_DIR):
    """{entrance_id: capture date}, from the sidecars' own timestamps.

    The bracket may only span doors from one day. E-001..E-012 were surveyed
    on 2026-08-31 in the Second Street district and E-013..E-064 walked on
    2026-09-04 up Congress; a bracket across the two would draw a line between
    streets nobody walked between.
    """
    days = {}
    for path in sorted(Path(sidecar_dir).glob("*.json")):
        sidecar = json.loads(path.read_text(encoding="utf-8"))
        entrance_id = sidecar["entrance_id"]
        day = sidecar["captured_at"][:10]
        days[entrance_id] = min(days.get(entrance_id, day), day)
    return days


def _enu_m(lat, lng, lat0, lng0):
    """Local east/north metres relative to (lat0, lng0). Over the couple of
    hundred metres a bracket spans, the flat-earth error is centimetres."""
    east = math.radians(lng - lng0) * 6_371_000 * math.cos(math.radians(lat0))
    north = math.radians(lat - lat0) * 6_371_000
    return east, north


def _point_to_segment_m(lat, lng, end_a, end_b):
    """Distance from a point to the segment between two lat/lng ends."""
    lat0, lng0 = end_a
    px, py = _enu_m(lat, lng, lat0, lng0)
    bx, by = _enu_m(end_b[0], end_b[1], lat0, lng0)
    length_sq = bx * bx + by * by
    if length_sq == 0:
        return math.hypot(px, py)
    t = max(0.0, min(1.0, (px * bx + py * by) / length_sq))
    return math.hypot(px - t * bx, py - t * by)


def anchored_locations(anchors):
    """{entrance_id: (lat, lng)} for every door whose street number was read.

    Deliberately the only source of a door position. A place's own location
    would place the door from the identification the distance gate exists to
    test, and the gate would stop testing anything.
    """
    return {entrance_id: (anchor["lat"], anchor["lng"])
            for entrance_id, anchor in anchors.items()}


def door_anchor(entrance_id, located, days):
    """How far a candidate may be from this door, and from what.

    Returns None when no evidence places the door at all.
    """
    if entrance_id in located:
        lat, lng = located[entrance_id]
        return {"kind": "address_geocode", "ends": [(lat, lng)],
                "between": None}
    day = days.get(entrance_id)
    if day is None:
        return None
    # Entrance ids run in capture order, so "before" and "after" on the id is
    # before and after on the walk (test_the_entrance_ids_run_in_walk_order).
    same_day = sorted(e for e in located if days.get(e) == day)
    before = [e for e in same_day if e < entrance_id]
    after = [e for e in same_day if e > entrance_id]
    if not before or not after:
        # One-sided is not a bracket: the door could be any distance beyond
        # the last anchor, and widening the gate is exactly what AC-4 forbids.
        return None
    end_a, end_b = before[-1], after[0]
    return {"kind": "walk_order_bracket",
            "ends": [located[end_a], located[end_b]],
            "between": [end_a, end_b]}


def anchor_distance_m(anchor, lat, lng):
    ends = anchor["ends"]
    if len(ends) == 1:
        return _haversine_m(lat, lng, ends[0][0], ends[0][1])
    return _point_to_segment_m(lat, lng, ends[0], ends[1])


# --- matching ---------------------------------------------------------------


def _place_location(place):
    location = place.get("location") or {}
    lat, lng = location.get("lat"), location.get("lng")
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        return float(lat), float(lng)
    return None


def name_candidates(name, places):
    """Catalogued places whose name matches, with the empty-name branch shut.

    ``_names_match`` answers True when either side has no comparable name so
    that a scan with coordinates can fall back to distance alone. An entrance
    has no independent coordinates, so here that branch would be a match on
    nothing at all.
    """
    if not _normalize_name(name):
        return []
    return [p for p in places
            if _normalize_name(p.get("name") or "")
            and _names_match(name, p["name"])]


def match_entrances(entrances, places, anchors, days,
                    max_distance_m=DEFAULT_MATCH_DISTANCE_M):
    """Decide a place for every entrance. Returns {entrance_id: result}.

    A result is either ``{"place_id": ..., "how": {...}}`` or
    ``{"place_id": None, "unmatched_reason": <key>, "detail": ...}``.
    Entrances that #341 already resolved keep their place_id untouched: this
    ticket adds places, it does not re-decide a door.
    """
    located = anchored_locations(anchors)
    results = {}
    for entrance_id, record in sorted(entrances.items()):
        results[entrance_id] = _match_one(
            entrance_id, record, places, located, days, max_distance_m)
    return _drop_places_two_doors_claim(results)


def _match_one(entrance_id, record, places, located, days, max_distance_m):
    if record.get("place_id"):
        return {"place_id": record["place_id"],
                "how": {"anchor": "identification", "detail":
                        "resolved by #341 against the committed catalogue"}}
    if record.get("status") != "identified":
        return _unmatched("not_identified")
    candidates = name_candidates(record["name"], places)
    if not candidates:
        return _unmatched("no_catalogue_entry")
    anchor = door_anchor(entrance_id, located, days)
    if anchor is None:
        return _unmatched("no_location_evidence",
                          f"{len(candidates)} name candidate(s) in the "
                          "catalogue, none of them testable")
    measured = []
    for place in candidates:
        location = _place_location(place)
        if location is None:
            continue
        measured.append((anchor_distance_m(anchor, *location), place))
    if not measured:
        return _unmatched("no_catalogue_entry",
                          "name candidates carry no usable location")
    measured.sort(key=lambda pair: pair[0])
    near = [pair for pair in measured if pair[0] <= max_distance_m]
    if not near:
        return _unmatched(
            "outside_match_distance",
            f"nearest candidate {measured[0][1]['name']!r} is "
            f"{measured[0][0]:.0f} m away, over the {max_distance_m:.0f} m gate")
    if len(near) > 1:
        return _unmatched(
            "ambiguous_candidates",
            "; ".join(f"{p['name']!r} at {d:.0f} m" for d, p in near))
    distance_m, place = near[0]
    return {
        "place_id": place["place_id"],
        "how": {
            "anchor": anchor["kind"],
            "anchor_between": anchor["between"],
            "distance_m": round(distance_m, 1),
            "matched_name": place["name"],
        },
    }


def _unmatched(reason, detail=None):
    return {"place_id": None, "unmatched_reason": reason,
            "detail": detail or UNMATCHED_REASONS[reason]}


def _drop_places_two_doors_claim(results):
    """A place cannot be two front doors, so neither door gets it.

    Two entrances reading the same business name — E-062 and E-063 both read
    "Speakeasy" — is exactly the ambiguity the ticket says to leave unmatched
    rather than guess onto one of the two storefronts.
    """
    claims = {}
    for entrance_id, result in results.items():
        if result["place_id"]:
            claims.setdefault(result["place_id"], []).append(entrance_id)
    for place_id, entrance_ids in claims.items():
        if len(entrance_ids) < 2:
            continue
        for entrance_id in entrance_ids:
            results[entrance_id] = _unmatched(
                "place_claimed_by_another_entrance",
                f"{', '.join(sorted(entrance_ids))} all reach {place_id}")
    return results


def coverage(results):
    """The count the ticket verifies against, plus why the rest failed."""
    reasons = {}
    for result in results.values():
        if result["place_id"]:
            continue
        reasons[result["unmatched_reason"]] = (
            reasons.get(result["unmatched_reason"], 0) + 1)
    return {
        "entrances": len(results),
        "resolved_to_a_place": sum(
            1 for r in results.values() if r["place_id"]),
        "unmatched": len(results) - sum(
            1 for r in results.values() if r["place_id"]),
        "unmatched_by_reason": dict(sorted(reasons.items())),
    }


# --- anchors CLI (the only network path) ------------------------------------


def _geocode(query, fetch_json):
    params = {"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "us"}
    results = fetch_json(NOMINATIM_URL, params)
    return results[0] if results else None


def _nominatim_get(url, params):
    request = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": NOMINATIM_USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _geocodable(address):
    """The address as a street-level query.

    A suite number names a floor inside the building, not a doorway on the
    street, and Nominatim answers nothing at all for an address carrying one.
    """
    parts = [part.strip() for part in address.split(",")]
    parts = [part for part in parts
             if not SUITE_RE.match(part)]
    query = ", ".join(parts)
    return query if "Austin" in query else f"{query}, Austin, TX"


def build_anchors(entrances, fetch_json=_nominatim_get, sleep=time.sleep):
    """Geocode every address an entrance actually recorded.

    Only an address that was read counts. Geocoding the *business name*
    instead would derive the door's location from the very identification the
    distance gate exists to test, which is no test at all.
    """
    records = {}
    cache = {}
    for entrance_id, record in sorted(entrances.items()):
        address = record.get("address")
        if not address:
            continue
        query = _geocodable(address)
        if query not in cache:
            sleep(NOMINATIM_DELAY_S)
            cache[query] = _geocode(query, fetch_json)
        result = cache[query]
        if result is None:
            continue
        records[entrance_id] = {
            "entrance_id": entrance_id,
            "address": address,
            "query": query,
            "lat": float(result["lat"]),
            "lng": float(result["lon"]),
            "osm_type": result.get("osm_type"),
            "osm_id": result.get("osm_id"),
            "display_name": result.get("display_name"),
        }
    return records


def anchors_document(records, fetched_at=None):
    return {
        "source": "openstreetmap_nominatim",
        "license": "ODbL-1.0",
        "attribution": OSM_ATTRIBUTION,
        "segregation": OSM_SEGREGATION,
        "purpose": (
            "Door positions for the entrance-to-place distance gate (#346). "
            "Derived from the street numbers recorded on foot or read off the "
            "transom in data/entrance_identification.json — never from a "
            "business name, which would make the gate circular."
        ),
        "fetched_at": fetched_at or datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "record_count": len(records),
        "anchors": records,
    }


def load_anchors(path=ANCHORS_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))["anchors"]


def catalogue_places(census, enumerated):
    """The candidate set: catalogued rows that can actually be compared.

    Two halves, because the catalogue deliberately stores two kinds of row.
    The Second Street district rows still carry the Places `name` and
    `location` #242 is open on; the rows this ticket added carry the
    place_id alone, so their display fields are resolved live by the sweep
    that runs alongside the match. A row with neither is not a candidate --
    there is nothing to match it on.
    """
    by_id = {}
    for row in census.get("places", []):
        if row.get("name") and row.get("location"):
            by_id[row["place_id"]] = row
    for place in enumerated:
        by_id[place["place_id"]] = place
    return list(by_id.values())


def apply_matches(entrances, results):
    """Write the decision onto each entrance record, in place.

    Only `place_id` and the new `place_match` audit trail move. The business
    a door belongs to is #341's call and this ticket does not revisit it.
    """
    for entrance_id, record in entrances.items():
        result = results[entrance_id]
        record["place_id"] = result["place_id"]
        record["place_match"] = {
            "how": result.get("how"),
            "unmatched_reason": result.get("unmatched_reason"),
            "detail": result.get("detail"),
        }
    return entrances


def _run_match(out_path):
    from frontdoor.precatalogue import (
        CENSUS_FILENAME, MapsCallCounter, _merged_census, _write_json,
        enumerate_places, load_api_key, load_demo_area,
    )

    document = json.loads(IDENTIFICATION_PATH.read_text(encoding="utf-8"))
    entrances = document["entrances"]
    census_path = Path("data") / CENSUS_FILENAME
    census = json.loads(census_path.read_text(encoding="utf-8"))

    area = load_demo_area(WALK_AREA_CONFIG)
    counter = MapsCallCounter(area.max_maps_calls)
    enumeration = enumerate_places(area, load_api_key(), counter)
    # Keep the committed catalogue a superset of what this pass matched
    # against, still identifier-only.
    merged = _merged_census(census, enumeration.places)
    if merged["added"]:
        census = {
            "summary": {
                "area": area.name,
                "census": True,
                "match_pass": True,
                "businesses_enumerated": len(enumeration.places),
                "maps_api_calls": counter.total,
                "merged_into_existing": {
                    "places_added": len(merged["added"]),
                    "places_already_listed": merged["already_listed"],
                    "places_total": len(merged["places"]),
                },
            },
            "previous_summaries": merged["previous_summaries"],
            "places": merged["places"],
        }
        _write_json(census_path, census)

    results = match_entrances(
        entrances, catalogue_places(census, enumeration.places),
        load_anchors(), walk_days())
    document["entrances"] = apply_matches(entrances, results)
    out_path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    report = coverage(results)
    report["maps_api_calls"] = counter.total
    report["catalogue_rows_added"] = len(merged["added"])
    print(json.dumps(report, indent=2))
    return 0


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["anchors"] and len(args) <= 2:
        out_path = Path(args[1]) if len(args) == 2 else ANCHORS_PATH
        entrances = json.loads(
            IDENTIFICATION_PATH.read_text(encoding="utf-8"))["entrances"]
        document = anchors_document(build_anchors(entrances))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        print(f"{document['record_count']} anchors -> {out_path}")
        return 0
    if args[:1] == ["match"] and len(args) <= 2:
        return _run_match(
            Path(args[1]) if len(args) == 2 else IDENTIFICATION_PATH)
    print("usage: python -m frontdoor.entrance_matching anchors [out_path]\n"
          "       python -m frontdoor.entrance_matching match [out_path]",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
