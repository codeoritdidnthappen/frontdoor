"""Every identified entrance either has a place_id or says why not (TICK-346, #346).

A scan record with a business name and no place cannot become a pin, which is the problem #333
started with. This pins the two halves of the fix: the catalogue actually covers the walked blocks,
and every identified door has been put to the gate and its outcome recorded.

The gate itself is the map's, not a new one: <= DEFAULT_MATCH_DISTANCE_M and a name match. A door
that cannot be placed inside it is refused rather than placed by widening it.
"""

import json
from pathlib import Path

from frontdoor.external_data import DEFAULT_MATCH_DISTANCE_M, _haversine_m, _names_match

ROOT = Path(__file__).resolve().parents[1]
IDENT = json.loads((ROOT / "data" / "entrance_identification.json").read_text())["entrances"]
CENSUS = json.loads((ROOT / "data" / "precatalogue_census.json").read_text())
PLACES = {p["place_id"]: p for p in CENSUS["places"]}


def identified():
    return {e: v for e, v in IDENT.items() if v.get("status") == "identified"}


def test_every_identified_entrance_resolves_or_says_why_not():
    """AC-2. Silence is the failure mode: a door with neither is one nobody will chase."""
    silent = [
        eid for eid, v in identified().items()
        if not v.get("place_id") and not v.get("place_reason")
    ]
    assert silent == [], f"identified but neither placed nor explained: {silent}"


def test_the_placed_count_rose_above_six():
    """AC verification. Six was the count before the catalogue was extended."""
    placed = [eid for eid, v in identified().items() if v.get("place_id")]
    assert len(placed) > 6, f"only {len(placed)} placed; the sweep bought nothing"


def test_every_place_id_names_a_place_the_catalogue_actually_holds():
    """A place_id the map cannot look up is the same as no place_id, but harder to notice."""
    missing = [
        (eid, v["place_id"]) for eid, v in identified().items()
        if v.get("place_id") and v["place_id"] not in PLACES
    ]
    assert missing == [], f"place_id not in the census: {missing}"


def test_matches_made_by_this_ticket_are_inside_the_map_gate():
    """AC-3 and AC-4, re-derived from the data rather than trusted.

    Recomputed from the recorded distance against the map's own threshold, so a later edit that
    widens a match to make a door fit shows up here.
    """
    for eid, v in identified().items():
        match = v.get("place_match")
        if not match:
            continue
        assert match["distance_m"] <= DEFAULT_MATCH_DISTANCE_M, (
            f"{eid} was placed {match['distance_m']} m away, beyond the {DEFAULT_MATCH_DISTANCE_M} m gate"
        )
        assert _names_match(v["name"], match["matched_name"]), (
            f"{eid} was placed on {match['matched_name']!r}, which does not match {v['name']!r}"
        )


def test_the_catalogue_covers_the_walked_corridor():
    """AC-1. The Second Street box only clipped the southern end of the 2026-09-04 walk."""
    assert "corridor_sweep" in CENSUS["summary"], "no record of the corridor sweep"
    lats = [p["location"]["lat"] for p in CENSUS["places"] if p.get("location")]
    lngs = [p["location"]["lng"] for p in CENSUS["places"] if p.get("location")]
    # The old sweep stopped at 30.267748 N and -97.743692 E; the walked doors reach past both.
    assert max(lats) > 30.2700, "the catalogue still stops short of the northern blocks"
    assert max(lngs) > -97.7425, "the catalogue still stops short of the Congress blocks"


def test_the_unresolved_are_not_quietly_dropped():
    """Their reason has to say something, not merely exist."""
    for eid, v in identified().items():
        if v.get("place_id"):
            continue
        reason = v.get("place_reason", "")
        assert len(reason) > 40, f"{eid}'s reason is too thin to act on: {reason!r}"
