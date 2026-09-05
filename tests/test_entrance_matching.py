"""Entrance-to-place matching (TICK-346, #346).

No network: the anchors CLI's geocoder is injected, and every match runs
against an in-memory place list. What is pinned here is the ticket's own
refusals — a name on its own is never a match, a candidate past the map's
distance gate is refused rather than the gate widened, and anything ambiguous
stays unmatched rather than being guessed onto a neighbouring storefront.
"""

import json

import pytest

from frontdoor.entrance_matching import (
    DEFAULT_MATCH_DISTANCE_M,
    anchors_document,
    build_anchors,
    coverage,
    door_anchor,
    match_entrances,
    name_candidates,
    walk_days,
)

DAY = "2026-09-04"


def identified(name, address=None, place_id=None):
    return {"status": "identified", "name": name, "address": address,
            "place_id": place_id}


def unidentified(reason="nothing legible"):
    return {"status": "unidentified", "name": None, "address": None,
            "place_id": None, "reason": reason}


def catalogued(place_id, name, lat, lng):
    return {"place_id": place_id, "name": name,
            "location": {"lat": lat, "lng": lng}}


def anchor(lat, lng):
    return {"lat": lat, "lng": lng}


#: ~11 m of latitude, comfortably inside the 40 m gate.
NEAR = 0.0001
#: ~111 m of latitude, comfortably outside it.
FAR = 0.001


def test_a_name_and_a_close_catalogue_entry_match():
    entrances = {"E-020": identified("Swift's Attic", "315 Congress Ave")}
    places = [catalogued("p1", "Swift's Attic", 30.2656 + NEAR, -97.7433)]
    results = match_entrances(
        entrances, places, {"E-020": anchor(30.2656, -97.7433)},
        {"E-020": DAY})
    assert results["E-020"]["place_id"] == "p1"
    assert results["E-020"]["how"]["anchor"] == "address_geocode"
    assert results["E-020"]["how"]["distance_m"] < DEFAULT_MATCH_DISTANCE_M


def test_a_name_alone_is_never_a_match():
    """The ticket's hard gate: no location evidence, no place. The catalogue
    holds exactly one Velvet Taco and the door still does not get it."""
    entrances = {"E-051": identified("Velvet Taco")}
    places = [catalogued("p1", "Velvet Taco", 30.2678, -97.7434)]
    results = match_entrances(entrances, places, {}, {"E-051": DAY})
    assert results["E-051"]["place_id"] is None
    assert results["E-051"]["unmatched_reason"] == "no_location_evidence"


def test_a_candidate_past_the_gate_is_refused_not_widened():
    entrances = {"E-055": identified("Robinson-Rosner Building",
                                     "504 Congress Ave")}
    places = [catalogued("p1", "Robinson-Rosner Building",
                         30.2675 + FAR, -97.7435)]
    results = match_entrances(
        entrances, places, {"E-055": anchor(30.2675, -97.7435)},
        {"E-055": DAY})
    assert results["E-055"]["place_id"] is None
    assert results["E-055"]["unmatched_reason"] == "outside_match_distance"
    assert "over the 40 m gate" in results["E-055"]["detail"]


def test_two_candidates_through_both_gates_stay_unmatched():
    entrances = {"E-019": identified("Starbucks", "300 Congress Ave")}
    places = [catalogued("p1", "Starbucks", 30.2656 + NEAR, -97.7433),
              catalogued("p2", "Starbucks Reserve", 30.2656 - NEAR, -97.7433)]
    results = match_entrances(
        entrances, places, {"E-019": anchor(30.2656, -97.7433)},
        {"E-019": DAY})
    assert results["E-019"]["place_id"] is None
    assert results["E-019"]["unmatched_reason"] == "ambiguous_candidates"


def test_a_business_the_catalogue_does_not_hold_says_so():
    entrances = {"E-061": identified("Quik Print", "100 Congress Ave")}
    places = [catalogued("p1", "Velvet Taco", 30.2656, -97.7433)]
    results = match_entrances(
        entrances, places, {"E-061": anchor(30.2656, -97.7433)},
        {"E-061": DAY})
    assert results["E-061"]["unmatched_reason"] == "no_catalogue_entry"


def test_one_place_cannot_be_two_front_doors():
    """E-062 and E-063 both read "Speakeasy". Guessing one of them onto the
    place is exactly the wrong-storefront failure the ticket forbids, so
    neither gets it."""
    entrances = {"E-062": identified("Speakeasy", "412 Congress Ave"),
                 "E-063": identified("Speakeasy", "412 Congress Ave")}
    places = [catalogued("p1", "Speakeasy", 30.2668 + NEAR, -97.7437)]
    anchors = {"E-062": anchor(30.2668, -97.7437),
               "E-063": anchor(30.2668, -97.7437)}
    results = match_entrances(entrances, places, anchors,
                              {"E-062": DAY, "E-063": DAY})
    assert results["E-062"]["place_id"] is None
    assert results["E-063"]["place_id"] is None
    assert results["E-062"]["unmatched_reason"] == (
        "place_claimed_by_another_entrance")


def test_a_collision_with_a_standing_identification_loses_to_it():
    """This ticket adds places; it may not take one away. A new match that
    lands on a place #341 already resolved is evidence against the new
    match, not against the standing one."""
    entrances = {"E-013": identified("JoS. A. Bank", place_id="p1"),
                 "E-040": identified("JoS A Bank", "700 Congress Ave")}
    places = [catalogued("p1", "JoS. A. Bank", 30.2660 + NEAR, -97.7440)]
    results = match_entrances(
        entrances, places, {"E-040": anchor(30.2660, -97.7440)},
        {"E-013": DAY, "E-040": DAY})
    assert results["E-013"]["place_id"] == "p1"
    assert results["E-040"]["place_id"] is None
    assert results["E-040"]["unmatched_reason"] == (
        "place_claimed_by_another_entrance")


def test_an_unidentified_entrance_is_never_matched():
    entrances = {"E-027": unidentified()}
    places = [catalogued("p1", "Anything", 30.2656, -97.7433)]
    results = match_entrances(
        entrances, places, {"E-027": anchor(30.2656, -97.7433)},
        {"E-027": DAY})
    assert results["E-027"]["unmatched_reason"] == "not_identified"


def test_an_identification_already_resolved_is_left_alone():
    """This ticket adds places; it does not re-decide a door."""
    entrances = {"E-013": identified("JoS. A. Bank", place_id="kept")}
    results = match_entrances(entrances, [], {}, {"E-013": DAY})
    assert results["E-013"]["place_id"] == "kept"
    assert results["E-013"]["how"]["anchor"] == "identification"


# --- walk-order brackets ----------------------------------------------------


def test_a_door_between_two_anchored_doors_is_measured_to_that_stretch():
    located = {"E-030": (30.2677, -97.7425), "E-033": (30.2683, -97.7423)}
    got = door_anchor("E-031", located, {"E-030": DAY, "E-031": DAY,
                                         "E-033": DAY})
    assert got["kind"] == "walk_order_bracket"
    assert got["between"] == ["E-030", "E-033"]
    assert got["ends"] == [(30.2677, -97.7425), (30.2683, -97.7423)]


def test_a_bracket_never_spans_two_days_of_walking():
    """E-012 was surveyed on 2026-08-31 in the Second Street district and
    E-020 walked on 2026-09-04 on Congress; a line between them crosses
    streets nobody walked."""
    located = {"E-012": (30.2638, -97.7453), "E-020": (30.2655, -97.7432)}
    days = {"E-012": "2026-08-31", "E-018": "2026-09-04",
            "E-020": "2026-09-04"}
    assert door_anchor("E-018", located, days) is None


def test_a_door_past_the_days_last_anchor_gets_no_bracket():
    located = {"E-058": (30.2670, -97.7442)}
    days = {"E-058": DAY, "E-061": DAY}
    assert door_anchor("E-061", located, days) is None


def test_a_bracketed_door_matches_a_place_beside_the_stretch():
    entrances = {"E-026": identified("Mexic-Arte Museum")}
    # the bracket runs up Congress; the museum sits on it, a few metres off
    anchors = {"E-024": anchor(30.2659, -97.74315),
               "E-030": anchor(30.26768, -97.74249)}
    entrances["E-024"] = identified("Corner", "327 Congress Ave")
    entrances["E-030"] = unidentified()
    places = [catalogued("p1", "Mexic-Arte Museum", 30.26690, -97.74285)]
    days = {"E-024": DAY, "E-026": DAY, "E-030": DAY}
    results = match_entrances(entrances, places, anchors, days)
    assert results["E-026"]["place_id"] == "p1"
    assert results["E-026"]["how"]["anchor"] == "walk_order_bracket"
    assert results["E-026"]["how"]["anchor_between"] == ["E-024", "E-030"]


def test_a_bracketed_door_still_refuses_a_place_off_the_stretch():
    entrances = {"E-026": identified("Mexic-Arte Museum"),
                 "E-024": identified("Corner", "327 Congress Ave"),
                 "E-030": unidentified()}
    anchors = {"E-024": anchor(30.2659, -97.74315),
               "E-030": anchor(30.26768, -97.74249)}
    # two blocks west of the walked stretch
    places = [catalogued("p1", "Mexic-Arte Museum", 30.26690, -97.74600)]
    days = {"E-024": DAY, "E-026": DAY, "E-030": DAY}
    results = match_entrances(entrances, places, anchors, days)
    assert results["E-026"]["unmatched_reason"] == "outside_match_distance"


# --- name gate --------------------------------------------------------------


def test_a_place_with_no_name_is_not_a_candidate():
    """_names_match answers True when either side has nothing to compare, so
    a scan with coordinates can fall back to distance. An entrance has no
    independent coordinates, so that branch would match on nothing at all."""
    assert name_candidates("CVS", [catalogued("p1", "", 30.0, -97.0)]) == []
    assert name_candidates("", [catalogued("p1", "CVS", 30.0, -97.0)]) == []


def test_the_name_gate_is_the_maps_own_comparison():
    places = [catalogued("p1", "CVS Pharmacy", 30.0, -97.0),
              catalogued("p2", "Torchy's Tacos", 30.0, -97.0)]
    assert [p["place_id"] for p in name_candidates("CVS", places)] == ["p1"]


# --- reporting --------------------------------------------------------------


def test_coverage_counts_the_resolved_and_says_why_the_rest_failed():
    results = {
        "E-001": {"place_id": "p1", "how": {}},
        "E-002": {"place_id": None, "unmatched_reason": "no_catalogue_entry",
                  "detail": "x"},
        "E-003": {"place_id": None, "unmatched_reason": "no_catalogue_entry",
                  "detail": "x"},
    }
    assert coverage(results) == {
        "entrances": 3,
        "resolved_to_a_place": 1,
        "unmatched": 2,
        "unmatched_by_reason": {"no_catalogue_entry": 2},
    }


# --- anchors ----------------------------------------------------------------


class FakeGeocoder:
    def __init__(self, answers):
        self.answers = answers
        self.queries = []

    def __call__(self, url, params):
        self.queries.append(params["q"])
        hit = self.answers.get(params["q"])
        return [hit] if hit else []


def result(lat, lng, name="somewhere"):
    return {"lat": str(lat), "lon": str(lng), "osm_type": "node",
            "osm_id": 1, "display_name": name}


def test_a_suite_number_is_dropped_before_geocoding():
    """A suite is a floor inside the building, not a doorway on the street,
    and Nominatim answers nothing at all for an address carrying one."""
    geocoder = FakeGeocoder({
        "301 Lavaca St, Austin, TX 78701": result(30.2661, -97.7459)})
    anchors = build_anchors(
        {"E-001": identified("DeSano", "301 Lavaca St, Ste 200, Austin, TX 78701")},
        fetch_json=geocoder, sleep=lambda _: None)
    assert geocoder.queries == ["301 Lavaca St, Austin, TX 78701"]
    assert anchors["E-001"]["lat"] == 30.2661


def test_only_an_address_is_ever_geocoded_never_a_business_name():
    """Geocoding the name would place the door from the identification the
    distance gate exists to test, and the gate would test nothing."""
    geocoder = FakeGeocoder({})
    build_anchors({"E-056": identified("CVS")},
                  fetch_json=geocoder, sleep=lambda _: None)
    assert geocoder.queries == []


def test_one_query_per_distinct_address():
    geocoder = FakeGeocoder({
        "522 Congress Ave, Austin, TX": result(30.2678, -97.7434)})
    anchors = build_anchors(
        {"E-050": identified("Scarbrough Building", "522 Congress Ave"),
         "E-051": identified("Velvet Taco", "522 Congress Ave")},
        fetch_json=geocoder, sleep=lambda _: None)
    assert geocoder.queries == ["522 Congress Ave, Austin, TX"]
    assert set(anchors) == {"E-050", "E-051"}


def test_an_address_that_does_not_geocode_is_simply_absent():
    geocoder = FakeGeocoder({})
    assert build_anchors({"E-024": identified("?", "327 Congress Ave")},
                         fetch_json=geocoder, sleep=lambda _: None) == {}


def test_the_anchors_document_carries_its_odbl_attribution():
    document = anchors_document({}, fetched_at="2026-09-05T00:00:00Z")
    assert document["license"] == "ODbL-1.0"
    assert "OpenStreetMap" in document["attribution"]
    assert "segregated" in document["segregation"]


# --- the committed artefacts ------------------------------------------------


def test_the_committed_anchors_only_place_doors_that_read_an_address(
        repo_anchors, repo_entrances):
    for entrance_id, anchor_record in repo_anchors.items():
        assert repo_entrances[entrance_id]["address"], entrance_id
        assert anchor_record["address"] in (
            repo_entrances[entrance_id]["address"]), entrance_id


def test_every_identified_entrance_either_has_a_place_or_says_why(
        repo_entrances):
    """AC-2, pinned on the committed file."""
    for entrance_id, record in sorted(repo_entrances.items()):
        if record["status"] != "identified":
            continue
        match = record["place_match"]
        if record["place_id"]:
            assert match["unmatched_reason"] is None, entrance_id
            assert match["how"], entrance_id
        else:
            assert match["unmatched_reason"], entrance_id
            assert match["detail"], entrance_id


def test_a_recorded_match_stayed_inside_the_distance_gate(repo_entrances):
    for entrance_id, record in sorted(repo_entrances.items()):
        how = (record.get("place_match") or {}).get("how")
        if not how or how.get("distance_m") is None:
            continue
        assert how["distance_m"] <= DEFAULT_MATCH_DISTANCE_M, entrance_id


def test_the_walk_days_come_from_the_captures_themselves():
    days = walk_days()
    assert days["E-001"] == "2026-08-31"
    assert days["E-013"] == "2026-09-04"


def test_the_entrance_ids_run_in_walk_order():
    """The bracket takes the anchored ids either side of a door, which is only
    the walk's own before-and-after while the ids sort the way the captures
    do. A dataset that broke that would silently bracket the wrong stretch."""
    import csv
    import json as _json
    from pathlib import Path as _Path

    repo = _Path(__file__).resolve().parents[1]
    first = {}
    with (repo / "data" / "manifest.csv").open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            sidecar = _json.loads(
                (repo / "data" / "sidecars" / f"{row['capture_id']}.json")
                .read_text(encoding="utf-8"))
            taken = sidecar["captured_at"]
            entrance = row["entrance_id"]
            first[entrance] = min(first.get(entrance, taken), taken)
    by_id = sorted(first)
    assert by_id == sorted(first, key=lambda e: first[e])


@pytest.fixture(scope="module")
def repo_anchors():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "data" / "external" / \
        "entrance_anchors.json"
    return json.loads(path.read_text(encoding="utf-8"))["anchors"]


@pytest.fixture(scope="module")
def repo_entrances():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "data" / \
        "entrance_identification.json"
    return json.loads(path.read_text(encoding="utf-8"))["entrances"]
