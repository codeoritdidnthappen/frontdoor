"""External accessibility data round zero (TICK-258, #242).

Fixture-based only — no test here touches the network. Pins the load-bearing
contracts: OSM records live segregated with ODbL attribution; provenance
lines are positive-only, source+date, distance+name matched; a wheelchair=no
tag produces a disagreement record and NO public change of any kind
(the never-negative guarantee); and /map/data passes provenance through
without altering states.
"""

import json

import pytest

from frontdoor.external_data import (
    DISAGREEMENTS_NOTE,
    ODBL_ATTRIBUTION,
    ProvenanceLine,
    build_overpass_query,
    find_disagreements,
    load_demo_bbox,
    load_osm_records,
    match_records,
    parse_overpass_payload,
    provenance_for_place,
    read_osm_records,
    write_disagreements,
    write_osm_dataset,
)
from frontdoor.map_states import (
    STATE_NEUTRAL,
    STATE_VERIFIED,
    prepare_map_payload,
    state_for_row,
)
from frontdoor_server.app import create_app

FETCHED_AT = "2026-09-03T12:00:00Z"

# A representative Overpass response: a named positive node, a named
# negative node, a way (coords under "center") with limited access, an
# unnamed wheelchair-entrance node, and junk elements that must be skipped.
# Geometry: the cafe (1001) and the nameless entrance (1003) sit ~17m apart;
# the negative pair (1002, 2001) sits ~110m away from them and ~29m from
# each other, so 40m-radius matches never cross the two clusters.
OVERPASS_FIXTURE = {
    "version": 0.6,
    "elements": [
        {
            "type": "node", "id": 1001, "lat": 30.2500, "lon": -97.7490,
            "tags": {"name": "Example Cafe", "amenity": "cafe",
                     "wheelchair": "yes", "check_date:wheelchair": "2024-05-01"},
        },
        {
            "type": "node", "id": 1002, "lat": 30.2510, "lon": -97.7500,
            "tags": {"name": "Blocked Bar", "wheelchair": "no"},
        },
        {
            "type": "way", "id": 2001,
            "center": {"lat": 30.2508, "lon": -97.7502},
            "tags": {"name": "Limited Store", "wheelchair": "limited"},
        },
        {
            "type": "node", "id": 1003, "lat": 30.25015, "lon": -97.74895,
            "tags": {"entrance": "wheelchair"},
        },
        # Untagged and unplaceable elements: skipped.
        {"type": "node", "id": 1004, "lat": 30.25, "lon": -97.75},
        {"type": "way", "id": 2002, "tags": {"wheelchair": "yes"}},
        "not an element",
    ],
}


def records():
    return parse_overpass_payload(OVERPASS_FIXTURE, FETCHED_AT)


# --- ingest and segregation -------------------------------------------------


def test_demo_bbox_loads_from_packaged_config():
    bbox = load_demo_bbox()
    assert set(bbox) >= {"south", "west", "north", "east"}
    assert bbox["south"] < bbox["north"]
    assert bbox["west"] < bbox["east"]


def test_overpass_query_targets_wheelchair_and_entrance_tags():
    query = build_overpass_query(
        {"south": 1.0, "west": 2.0, "north": 3.0, "east": 4.0})
    assert '"wheelchair"' in query
    assert '"entrance"="wheelchair"' in query
    assert "(1.0,2.0,3.0,4.0)" in query
    assert "out center" in query


def test_parse_overpass_payload_records():
    parsed = records()
    assert len(parsed) == 4
    by_id = {r["osm_id"]: r for r in parsed}
    cafe = by_id[1001]
    assert cafe["source"] == "openstreetmap"
    assert cafe["fetched_at"] == FETCHED_AT
    assert cafe["name"] == "Example Cafe"
    assert cafe["lat"] == 30.2500 and cafe["lon"] == -97.7490
    assert cafe["tags"]["wheelchair"] == "yes"
    # A way takes its coordinate from "center"; a nameless node keeps None.
    assert by_id[2001]["lat"] == 30.2508
    assert by_id[1003]["name"] is None


def test_parse_is_total_over_junk_payloads():
    for payload in (None, [], "junk", {}, {"elements": None}, {"elements": 7}):
        assert parse_overpass_payload(payload, FETCHED_AT) == []


def test_written_dataset_is_segregated_and_attributed(tmp_path):
    path = tmp_path / "external" / "osm_accessibility.json"
    write_osm_dataset(records(), path, FETCHED_AT)
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["source"] == "openstreetmap"
    assert document["license"] == "ODbL-1.0"
    assert "OpenStreetMap contributors" in document["attribution"]
    assert document["attribution"] == ODBL_ATTRIBUTION
    assert "segregated" in document["segregation"].lower()
    assert document["record_count"] == 4
    assert all(r["source"] == "openstreetmap" for r in document["records"])
    assert load_osm_records(path) == document["records"]


def test_load_osm_records_total_over_missing_or_broken(tmp_path):
    assert load_osm_records(tmp_path / "nope.json") == []
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert load_osm_records(broken) == []
    weird = tmp_path / "weird.json"
    weird.write_text(json.dumps({"records": ["junk", 7]}), encoding="utf-8")
    assert load_osm_records(weird) == []


def test_a_side_file_that_cannot_be_read_says_so_and_logs(tmp_path, caplog):
    """#353: total is not the same as silent.

    The side files are COPYed into the image. If one is dropped or truncated
    -- the dataset incident's exact class -- every provenance and attribution
    line disappears from every pin and the map looks entirely normal. The ODbL
    attribution these records carry is a licence obligation, so its silent
    disappearance is not only an observability problem. Fails against the old
    loader, which returned [] and said nothing.
    """
    with caplog.at_level("ERROR", logger="frontdoor.external_data"):
        records, error = read_osm_records(tmp_path / "nope.json")
    assert records == []
    assert error is not None
    assert caplog.records, "a missing side file left no trace"

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    caplog.clear()
    with caplog.at_level("ERROR", logger="frontdoor.external_data"):
        records, error = read_osm_records(broken)
    assert records == []
    assert error is not None
    assert caplog.records


def test_a_side_file_that_reads_cleanly_reports_no_error(tmp_path):
    """An empty records array is a real answer, not a failure: the sources
    matched nothing, and that stays distinguishable from a lost file."""
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"records": []}), encoding="utf-8")
    assert read_osm_records(path) == ([], None)


# --- provenance matching ----------------------------------------------------


def test_match_by_distance_threshold():
    # Only the cafe cluster (1001, and 1003 ~17m away) is within 40m of the
    # cafe's coordinates; the negative cluster is ~110m away. A faraway
    # point matches nothing.
    near = match_records(None, 30.2500, -97.7490, records(), max_distance_m=40)
    assert {r["osm_id"] for r in near} == {1001, 1003}
    far = match_records(None, 30.30, -97.80, records(), max_distance_m=40)
    assert far == []


def test_fuzzy_name_match_filters_disagreeing_names():
    matched = match_records("Example Cafe", 30.2500, -97.7490, records(),
                            max_distance_m=40)
    assert {r["osm_id"] for r in matched} == {1001, 1003}  # 1003: nameless
    # A disagreeing name filters a named record even at zero distance.
    different = match_records("Totally Different Deli", 30.2500, -97.7490,
                              records(), max_distance_m=40)
    assert {r["osm_id"] for r in different} == {1003}
    # Containment counts as a match ("Example Cafe" in "The Example Cafe ATX").
    assert 1001 in {r["osm_id"] for r in match_records(
        "The Example Cafe ATX", 30.2500, -97.7490, records(), max_distance_m=40)}


def test_provenance_line_shape_and_label():
    line = ProvenanceLine(source="openstreetmap", label="x", date="2024",
                          url="https://example.org", detail="d").as_dict()
    assert line == {"source": "openstreetmap", "label": "x", "date": "2024",
                    "url": "https://example.org", "detail": "d"}
    lines = provenance_for_place("Example Cafe", 30.2500, -97.7490, records())
    assert len(lines) == 2  # the positive cafe + the wheelchair entrance
    cafe = next(l for l in lines if l["url"].endswith("/node/1001"))
    # check_date:wheelchair wins over the fetch year.
    assert cafe["label"] == "Reported on OpenStreetMap - 2024"
    assert cafe["date"] == "2024"
    assert "OpenStreetMap contributors" in cafe["detail"]
    entrance = next(l for l in lines if l["url"].endswith("/node/1003"))
    assert entrance["label"] == "Reported on OpenStreetMap - 2026"


def test_provenance_never_emits_negative_lines():
    """The never-negative guarantee, public half: wheelchair=no/limited
    records produce NO provenance line for any place."""
    assert provenance_for_place("Blocked Bar", 30.2510, -97.7500,
                                records()) == []
    assert provenance_for_place("Limited Store", 30.2508, -97.7502,
                                records()) == []


# --- disagreement queue -----------------------------------------------------


def ai_row(name, lat, lng, verdict):
    return {
        "name": name,
        "location": {"lat": lat, "lng": lng},
        "source": "streetview",
        "status": "ai_estimated",
        "criteria": {"ramp_or_bevel": {"verdict": verdict, "confidence": 0.9}},
    }


def test_find_disagreements_both_directions():
    ai = {
        "p_bar": ai_row("Blocked Bar", 30.2510, -97.7500, "present"),
        "p_cafe": ai_row("Example Cafe", 30.2500, -97.7490, "absent"),
        "p_agree": ai_row("Example Cafe", 30.2500, -97.7490, "present"),
        "p_far": ai_row("Blocked Bar", 30.40, -97.90, "present"),
    }
    found = find_disagreements(ai, records())
    by_place = {d["place"]["place_id"]: d for d in found}
    # AI positive vs external negative.
    bar = by_place["p_bar"]
    assert bar["ai_says"] == "present"
    assert bar["external_says"] == "wheelchair=no"
    assert bar["field"] == "ramp_or_bevel"
    assert bar["external"]["source"] == "openstreetmap"
    assert bar["external"]["osm_id"] == 1002
    assert "wheelchair=no" in bar["reason"]
    # AI negative vs external positive.
    assert by_place["p_cafe"]["external_says"] == "wheelchair=yes"
    # Agreement and out-of-range places produce nothing.
    assert "p_agree" not in by_place
    assert "p_far" not in by_place


def test_find_disagreements_total_over_junk():
    for ai in (None, [], "junk", {"x": None}, {"x": {"location": "nope"}}):
        assert find_disagreements(ai, records()) == []
    assert find_disagreements({"x": ai_row("A", 30.25, -97.749, "present")},
                              []) == []


def test_disagreements_file_is_marked_internal(tmp_path):
    path = tmp_path / "disagreements.json"
    ai = {"p_bar": ai_row("Blocked Bar", 30.2510, -97.7500, "present")}
    write_disagreements(find_disagreements(ai, records()), path)
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["note"] == DISAGREEMENTS_NOTE
    assert "INTERNAL" in document["note"]
    assert document["count"] == 1


def test_never_negative_guarantee_no_pin_change():
    """The never-negative guarantee, state half: a wheelchair=no external
    record produces a disagreement record and changes NO pin state."""
    row = ai_row("Blocked Bar", 30.2510, -97.7500, "present")
    verified = dict(ai_row("Blocked Bar", 30.2510, -97.7500, "present"),
                    status="verified", source="onsite_visit")
    dataset = {"estimated": row, "verified": verified}

    before = prepare_map_payload(dataset)
    disagreements = find_disagreements(dataset, records())
    after = prepare_map_payload(dataset)

    assert len(disagreements) == 2  # both rows conflict with wheelchair=no
    assert before == after
    states = {pin["place_id"]: pin["state"] for pin in after["pins"]}
    assert states == {"estimated": STATE_NEUTRAL, "verified": STATE_VERIFIED}
    # And state_for_row itself has no external-data input at all.
    assert state_for_row(row) == STATE_NEUTRAL
    assert state_for_row(verified) == STATE_VERIFIED


# --- /map/data passthrough --------------------------------------------------


@pytest.fixture
def client():
    return create_app().test_client()


def make_dataset_env(tmp_path, monkeypatch, dataset):
    dataset_path = tmp_path / "precatalogue.json"
    dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
    monkeypatch.setenv("FRONTDOOR_MAP_DATASET", str(dataset_path))
    external_path = tmp_path / "osm_accessibility.json"
    write_osm_dataset(records(), external_path, FETCHED_AT)
    monkeypatch.setenv("FRONTDOOR_EXTERNAL_OSM", str(external_path))


def test_map_data_attaches_provenance_only_where_matched(
        client, tmp_path, monkeypatch):
    dataset = {
        "matched": ai_row("Example Cafe", 30.2500, -97.7490, "present"),
        "negative_only": ai_row("Blocked Bar", 30.2510, -97.7500, "present"),
        "unmatched": ai_row("Far Away Diner", 30.40, -97.90, "present"),
    }
    make_dataset_env(tmp_path, monkeypatch, dataset)
    payload = client.get("/map/data").get_json()
    pins = {pin["place_id"]: pin for pin in payload["pins"]}

    matched = pins["matched"]
    assert any(line["label"] == "Reported on OpenStreetMap - 2024"
               for line in matched["provenance"])
    assert all(line["source"] == "openstreetmap" and line["date"]
               for line in matched["provenance"])
    # A pin whose only external matches are negative gets NO provenance key
    # and keeps its neutral state; so does an unmatched pin.
    assert "provenance" not in pins["negative_only"]
    assert "provenance" not in pins["unmatched"]
    assert all(pin["state"] == STATE_NEUTRAL for pin in pins.values())


def test_map_data_provenance_does_not_alter_states_or_shape(
        client, tmp_path, monkeypatch):
    dataset = {"green": dict(ai_row("Example Cafe", 30.2500, -97.7490,
                                    "present"),
                             status="verified", source="onsite_visit")}
    make_dataset_env(tmp_path, monkeypatch, dataset)
    payload = client.get("/map/data").get_json()
    (pin,) = payload["pins"]
    assert pin["state"] == STATE_VERIFIED
    assert pin["label"] == "Verified Accessible"
    assert pin["provenance"]  # provenance stacks ON the state, never sets it
    assert payload["dataset_error"] is None


def test_map_data_unchanged_without_external_file(client, tmp_path, monkeypatch):
    dataset_path = tmp_path / "precatalogue.json"
    dataset_path.write_text(
        json.dumps({"p": ai_row("Example Cafe", 30.2500, -97.7490, "present")}),
        encoding="utf-8")
    monkeypatch.setenv("FRONTDOOR_MAP_DATASET", str(dataset_path))
    monkeypatch.setenv("FRONTDOOR_EXTERNAL_OSM", str(tmp_path / "absent.json"))
    payload = client.get("/map/data").get_json()
    (pin,) = payload["pins"]
    assert "provenance" not in pin
    assert pin["state"] == STATE_NEUTRAL
