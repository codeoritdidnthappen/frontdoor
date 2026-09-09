"""Kind of place, from OpenStreetMap (TICK-491, #491).

Fixture-based only — no test here touches the network. Pins the contracts that
would be expensive to discover on the map:

- a category needs IDENTITY (phone, website, or a name both sides carry), so an
  unnamed element beside a business can never type it;
- the four mis-types the distance-only rule produced on real demo data stay
  fixed, by name, because they are the exact regression;
- the ODbL side file stays segregated and attributed;
- a category never moves a state, a label, a checklist or a tier;
- an untyped place gets no "category" key rather than a wrong one;
- nothing here reads or writes a Google Places field (#242's posture).
"""

import json
import re

import pytest

from frontdoor.map_states import STATE_NEUTRAL, STATE_SCANNED, prepare_map_payload
from frontdoor.place_categories import (
    CATEGORIES,
    CATEGORY_LABELS,
    build_overpass_query,
    category_for_place,
    category_for_tags,
    load_category_records,
    match_category_record,
    parse_overpass_payload,
    phone_key,
    website_key,
    write_categories_dataset,
)
from frontdoor_server.app import create_app

FETCHED_AT = "2026-09-07T12:00:00Z"

# One block of the demo area, rebuilt from the shapes that actually broke.
# The bar, the bank and the salon are all within 40 m of street furniture or
# of a different business; only identity tells them apart.
PAYLOAD = {
    "elements": [
        # a bar that shares no name with the pin, but shares a website
        {"type": "node", "id": 101, "lat": 30.2650, "lon": -97.7460,
         "tags": {"name": "Group Therapy Bar", "amenity": "restaurant",
                  "website": "https://www.grouptherapyaustin.com/"}},
        # unnamed street furniture, 6 m from the bar — the thing that used to win
        {"type": "node", "id": 102, "lat": 30.26505, "lon": -97.74600,
         "tags": {"amenity": "parking_space"}},
        # a real restaurant 16 m from the bank pin, correctly named
        {"type": "node", "id": 103, "lat": 30.2660, "lon": -97.7470,
         "tags": {"name": "Red Ash", "amenity": "restaurant"}},
        # a hotel 29 m from the salon pin, matched to its own pin by phone
        {"type": "node", "id": 104, "lat": 30.2670, "lon": -97.7480,
         "tags": {"name": "Hotel ZaZa", "tourism": "hotel",
                  "phone": "+1-512-555-0142"}},
        # a way: coordinates arrive under "center"
        {"type": "way", "id": 105, "center": {"lat": 30.2680, "lon": -97.7440},
         "tags": {"name": "Hemline", "shop": "clothes"}},
        # named, but no tag this mapping covers -> not stored at all
        {"type": "node", "id": 106, "lat": 30.2690, "lon": -97.7430,
         "tags": {"name": "A Bench With A Name", "amenity": "bench"}},
        # junk
        {"type": "node", "id": 107, "tags": {"name": "No Coordinates", "shop": "gift"}},
        "not an element",
    ]
}


def records():
    return parse_overpass_payload(PAYLOAD, FETCHED_AT)


# --- the mapping ------------------------------------------------------------


def test_category_keys_and_labels_are_few_and_human():
    assert [key for key, _label, _tags in CATEGORIES] == [
        "food_drink", "shops", "services", "culture_nightlife", "stay"]
    assert list(CATEGORY_LABELS.values()) == [
        "Food and drink", "Shops", "Services", "Culture and nightlife",
        "Places to stay"]


@pytest.mark.parametrize("tags,expected", [
    ({"amenity": "restaurant"}, "food_drink"),
    ({"amenity": "cafe"}, "food_drink"),
    ({"shop": "bakery"}, "food_drink"),
    ({"shop": "clothes"}, "shops"),
    ({"shop": "hairdresser"}, "services"),
    ({"shop": "beauty"}, "services"),        # the owner's "spas"
    ({"office": "estate_agent"}, "services"),
    ({"office": "anything_at_all"}, "services"),   # office=* is a whole-key rule
    ({"healthcare": "physiotherapist"}, "services"),
    ({"amenity": "nightclub"}, "culture_nightlife"),
    ({"tourism": "museum"}, "culture_nightlife"),
    ({"tourism": "hotel"}, "stay"),
])
def test_tags_map_to_human_categories(tags, expected):
    key, tag = category_for_tags(tags)
    assert key == expected
    assert tag == f"{list(tags)[0]}={list(tags.values())[0]}"


@pytest.mark.parametrize("tags", [
    {"amenity": "bench"}, {"amenity": "waste_basket"},
    {"amenity": "parking_space"}, {"amenity": "parking_entrance"},
    {"amenity": "bicycle_parking"}, {"amenity": "vending_machine"},
    {"leisure": "swimming_pool"}, {"tourism": "artwork"},
    {"amenity": "shelter"}, {"amenity": "drinking_water"},
    {}, None, "nonsense",
])
def test_street_furniture_is_untyped_not_bucketed(tags):
    """102 of 234 elements in the demo box are furniture. None is a place you go."""
    assert category_for_tags(tags) == (None, None)


def test_a_specific_shop_tag_beats_a_general_amenity_tag():
    key, tag = category_for_tags({"shop": "bakery", "amenity": "cafe"})
    assert (key, tag) == ("food_drink", "shop=bakery")


# --- identity ---------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("+1-512-474-2212", "5124742212"),
    ("(512) 474-2212", "5124742212"),
    ("512.474.2212", "5124742212"),
    ("474-2212", ""), ("", ""), (None, ""),
])
def test_phone_key_normalizes_to_the_comparable_part(raw, expected):
    assert phone_key(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("https://www.foxtrotco.com/", "foxtrotco.com"),
    ("http://foxtrotco.com/menu?x=1", "foxtrotco.com"),
    ("foxtrotco.com", "foxtrotco.com"),
    ("", ""), (None, ""),
])
def test_website_key_reduces_to_the_host(raw, expected):
    assert website_key(raw) == expected


def test_an_unnamed_element_can_never_supply_a_category():
    """The whole reason this matcher is stricter than provenance matching.

    The parking space is 6 m away; the bar it would have typed is 40 m of
    nothing. Distance alone must not be enough.
    """
    furniture = [r for r in records() if r.get("osm_id") == 102]
    assert furniture == []  # it is not even stored
    near_only = [{"source": "openstreetmap", "osm_type": "node", "osm_id": 102,
                  "name": None, "lat": 30.26505, "lon": -97.74600,
                  "tags": {"amenity": "parking_space"}}]
    assert match_category_record("Group Therapy", 30.2650, -97.7460,
                                 None, None, near_only) is None


def test_a_different_business_next_door_does_not_type_this_one():
    """First Citizens Bank sat 16 m from Red Ash and was typed as a restaurant."""
    assert category_for_place("First Citizens Bank - Corporate Office",
                              30.2660, -97.74705, None, None, records()) is None


def test_a_salon_is_not_typed_from_the_hotel_beside_it():
    """Keen Salon sat 29 m from Hotel ZaZa and was typed tourism=hotel."""
    assert category_for_place("Keen Salon", 30.26722, -97.7480,
                              None, None, records()) is None


def test_website_identity_types_a_place_whose_name_does_not_match():
    """"Group Therapy" is a bar. The name says nothing; the website is proof."""
    category = category_for_place("Group Therapy", 30.2650, -97.7460,
                                  None, "http://grouptherapyaustin.com",
                                  records())
    assert category["key"] == "food_drink"
    assert category["label"] == "Food and drink"
    assert category["matched_on"] == "website"
    assert category["tag"] == "amenity=restaurant"


def test_phone_identity_types_a_place_whose_name_says_nothing():
    """"Serenade" could be anything. The phone number says it is a hotel."""
    category = category_for_place("Serenade", 30.26702, -97.7480,
                                  "(512) 555-0142", None, records())
    assert category["key"] == "stay"
    assert category["matched_on"] == "phone"


def test_name_identity_types_a_place_the_two_sources_agree_on():
    category = category_for_place("Hemline Austin", 30.2680, -97.7440,
                                  None, None, records())
    assert (category["key"], category["matched_on"]) == ("shops", "name")


def test_the_category_cites_the_element_that_said_it():
    category = category_for_place("Hemline Austin", 30.2680, -97.7440,
                                  None, None, records())
    assert category["source"] == "openstreetmap"
    assert category["osm_type"] == "way"
    assert category["url"] == "https://www.openstreetmap.org/way/105"
    assert category["detail"] == "© OpenStreetMap contributors (ODbL)"


def test_distance_still_bounds_an_identity_match():
    """An exact website is not enough from a block away."""
    assert category_for_place("Group Therapy", 30.2750, -97.7460,
                              None, "http://grouptherapyaustin.com",
                              records()) is None


# --- ingest and segregation -------------------------------------------------


def test_ingest_keeps_only_named_category_bearing_elements():
    stored = records()
    assert {r["osm_id"] for r in stored} == {101, 103, 104, 105}
    assert all(r["name"] and r["source"] == "openstreetmap" for r in stored)
    # the way's centre coordinate survived
    (way,) = [r for r in stored if r["osm_type"] == "way"]
    assert (way["lat"], way["lon"]) == (30.2680, -97.7440)


def test_side_file_is_segregated_and_attributed(tmp_path):
    path = tmp_path / "osm_categories.json"
    document = write_categories_dataset(records(), path, FETCHED_AT)
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk == document
    assert on_disk["license"] == "ODbL-1.0"
    assert "OpenStreetMap" in on_disk["attribution"]
    assert "Collective Database" in on_disk["segregation"]
    assert on_disk["record_count"] == len(on_disk["records"])


def test_committed_side_file_is_attributed_and_holds_only_named_records():
    records_on_disk, error = load_category_records("data/external/osm_categories.json")
    assert error is None
    assert records_on_disk
    assert all(r["name"] and r["category"] in CATEGORY_LABELS
               for r in records_on_disk)


def test_the_overpass_query_asks_for_the_category_keys_only():
    query = build_overpass_query({"south": 1.0, "west": 2.0,
                                  "north": 3.0, "east": 4.0})
    for key in ("amenity", "shop", "tourism", "office", "leisure",
                "craft", "healthcare"):
        assert f'nwr["{key}"](1.0,2.0,3.0,4.0);' in query
    assert "out center tags;" in query


def test_no_google_places_field_is_read_or_written():
    """#242's posture, enforced rather than remembered.

    Places terms forbid storing anything but place_id, and #242's own audit
    has an unresolved violation open on that criterion. This module must not
    become the second one.
    """
    source = open("src/frontdoor/place_categories.py", encoding="utf-8").read()
    code = "\n".join(line for line in source.splitlines()
                     if not line.lstrip().startswith("#"))
    body = code.split('"""', 2)[-1]  # drop the module docstring, which discusses it
    for forbidden in ("places.googleapis", "maps.googleapis", "accessibilityOptions",
                      "primaryType", "GOOGLE_MAPS_API_KEY"):
        assert forbidden not in body
    assert "types" not in {t.strip() for t in body.split()}


# --- /map/data --------------------------------------------------------------


@pytest.fixture
def client():
    return create_app().test_client()


def row(name, lat, lng, **extra):
    return dict({
        "name": name,
        "location": {"lat": lat, "lng": lng},
        "status": "ai_estimated",
        "source": "streetview",
        "imagery_date": "2024-05",
        "criteria": {"ramp_or_bevel": {"verdict": "present", "confidence": 80.0}},
    }, **extra)


def make_env(tmp_path, monkeypatch, dataset):
    dataset_path = tmp_path / "precatalogue.json"
    dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
    monkeypatch.setenv("FRONTDOOR_MAP_DATASET", str(dataset_path))
    categories_path = tmp_path / "osm_categories.json"
    write_categories_dataset(records(), categories_path, FETCHED_AT)
    monkeypatch.setenv("FRONTDOOR_EXTERNAL_CATEGORIES", str(categories_path))
    return dataset_path


def test_map_data_attaches_a_category_only_where_identity_matched(
        client, tmp_path, monkeypatch):
    dataset = {
        "typed": row("Hemline Austin", 30.2680, -97.7440),
        "by_phone": row("Serenade", 30.26702, -97.7480, phone="(512) 555-0142"),
        "next_door": row("First Citizens Bank - Corporate Office",
                         30.2660, -97.74705),
        "far": row("Far Away Diner", 30.40, -97.90),
    }
    make_env(tmp_path, monkeypatch, dataset)
    pins = {p["place_id"]: p for p in client.get("/map/data").get_json()["pins"]}

    assert pins["typed"]["category"]["key"] == "shops"
    assert pins["by_phone"]["category"]["key"] == "stay"
    # No category is the honest answer, and it is an ABSENT key rather than a
    # wrong value or a "none" that reads as a verdict about the business.
    assert "category" not in pins["next_door"]
    assert "category" not in pins["far"]


def test_a_category_never_moves_a_state_label_or_checklist(
        client, tmp_path, monkeypatch):
    dataset = {
        "estimated": row("Hemline Austin", 30.2680, -97.7440),
        "scanned": row("Group Therapy", 30.2650, -97.7460,
                       website="https://grouptherapyaustin.com",
                       status="verified", source="onsite_visit"),
    }
    make_env(tmp_path, monkeypatch, dataset)
    payload = client.get("/map/data").get_json()
    pins = {p["place_id"]: p for p in payload["pins"]}

    assert pins["estimated"]["state"] == STATE_NEUTRAL
    assert pins["scanned"]["state"] == STATE_SCANNED
    assert pins["scanned"]["category"]["key"] == "food_drink"

    # And the payload the state machine produced, before any category was
    # attached, is byte-identical apart from the added key.
    baseline = prepare_map_payload(dataset)
    for pin in payload["pins"]:
        pin.pop("category", None)
    assert {p["place_id"]: (p["state"], p["label"], p["checklist"])
            for p in payload["pins"]} == {
        p["place_id"]: (p["state"], p["label"], p["checklist"])
        for p in baseline["pins"]}


def test_the_phone_and_website_matched_on_never_reach_the_payload(
        client, tmp_path, monkeypatch):
    """The match happens server-side; the contact fields stay in the dataset."""
    dataset = {"p": row("Serenade", 30.26702, -97.7480,
                        phone="(512) 555-0142",
                        website="https://serenade.example")}
    make_env(tmp_path, monkeypatch, dataset)
    (pin,) = client.get("/map/data").get_json()["pins"]
    assert pin["category"]["matched_on"] == "phone"
    assert "phone" not in pin and "website" not in pin
    assert "555" not in json.dumps(pin)


def test_map_data_renders_without_a_category_file(client, tmp_path, monkeypatch):
    dataset_path = tmp_path / "precatalogue.json"
    dataset_path.write_text(
        json.dumps({"p": row("Hemline Austin", 30.2680, -97.7440)}),
        encoding="utf-8")
    monkeypatch.setenv("FRONTDOOR_MAP_DATASET", str(dataset_path))
    monkeypatch.setenv("FRONTDOOR_EXTERNAL_CATEGORIES", str(tmp_path / "absent.json"))
    payload = client.get("/map/data").get_json()
    (pin,) = payload["pins"]
    assert "category" not in pin
    assert pin["state"] == STATE_NEUTRAL
    assert "absent.json" in payload["categories_error"]


# --- the served page --------------------------------------------------------


def served_page():
    return create_app().test_client().get("/app").get_data(as_text=True)


def test_the_filter_sheet_holds_the_kind_of_place_section():
    """In the Filters sheet, and nowhere near the map surface.

    Rounds 15 and 16 cut the floating chrome hard. A category filter is a
    filter; it does not get a control over the map.
    """
    html = served_page()
    assert '<div id="filt-cats-block" hidden>' in html
    assert '<div class="chips-title">Kind of place</div>' in html
    assert '<div class="chips" id="filt-cats"></div>' in html
    # the block sits inside the Filters sheet, between My Needs and the criteria
    sheet = html.split('id="sheet-filters"', 1)[1].split("</div>\n    </div>", 1)[0]
    assert "filt-cats-block" in sheet
    assert sheet.index('id="filt-needs"') < sheet.index("filt-cats-block")
    assert sheet.index("filt-cats-block") < sheet.index('id="filt-feats"')
    # The coverage sentence comes BEFORE the chips. Measured on the served page:
    # underneath them it was cut mid-line by the sticky apply bar while the chips
    # stayed fully selectable, so the half saying what filtering leaves out could
    # be missed by anyone who did not scroll.
    assert sheet.index('id="filt-cats-note"') < sheet.index('id="filt-cats"')
    # and no new FAB, control or chrome over the map
    assert "fab-cats" not in html and "cat-toggle" not in html


def test_the_sheet_states_the_coverage_before_anything_is_selected():
    """A filter that silently hides what it has no type for is worse than none."""
    html = served_page()
    assert "Kind of place comes from OpenStreetMap." in html
    assert "places have one on record; the other" in html
    assert "are left out when you filter by kind" in html


def test_category_is_a_separate_vocabulary_from_the_engines_criteria():
    """#481 cut FILT_FEATS to the four criteria. This is not a fifth."""
    html = served_page()
    (feats_line,) = [line for line in html.splitlines()
                     if line.startswith("const FILT_FEATS=")]
    assert feats_line == (
        "const FILT_FEATS=[['ramp','Ramp or bevel'],['handrails','Handrails'],"
        "['hardware','Easy-grip'],['signage','Access signage']];")
    assert "const CAT_ORDER=" in html
    # the two sets never touch: no category key appears in the criteria row and
    # no criterion key appears in the category order
    (order_line,) = [line for line in html.splitlines()
                     if line.startswith("const CAT_ORDER=")]
    for criterion in ("ramp", "handrails", "hardware", "signage"):
        assert f"'{criterion}'" not in order_line
    for category in CATEGORY_LABELS:
        assert category not in feats_line


def test_the_combined_result_never_claims_accessible_places_of_a_kind():
    """THE forbidden claim, and it is reached by combination rather than by sentence.

    Category plus a needs profile must never render as "the accessible
    restaurants". The two facts stay in separate clauses: what the places ARE,
    then the operation we ran against what the person said they need, then the
    app's existing disclaimer, word for word.
    """
    html = served_page()
    assert ("'Showing '+n+' places in '+catPhrase()+', matched against what you "
            "said you need — halos show fit, not certainty'") in html
    assert ("'Showing '+n+' places in '+catPhrase()+' — kind of place comes "
            "from OpenStreetMap'") in html
    # no accessibility adjective is ever attached to a category noun
    lowered = html.lower()
    for label in CATEGORY_LABELS.values():
        for adjective in ("accessible ", "step-free ", "wheelchair "):
            assert adjective + label.lower() not in lowered
            assert label.lower() + " that are accessible" not in lowered


def without_comments(html):
    """The page minus its HTML and block comments.

    Copy tests read what a person is shown, not what the source explains to
    the next maintainer -- a comment saying "the map has no category for this
    place" is exactly the reasoning we want kept, and it must not read as the
    page saying it.
    """
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    return re.sub(r"/\*.*?\*/", " ", html, flags=re.S)


def test_an_untyped_place_is_never_shown_as_failing_anything():
    """It recedes, exactly as a place that does not match a needs profile does."""
    shown = without_comments(served_page()).lower()
    for phrase in ("no category", "uncategorised", "uncategorized",
                   "unknown kind", "not a restaurant", "no kind",
                   "missing category", "untyped"):
        assert phrase not in shown
    # the sheet's sentence is about OUR data, not about the business
    assert "places have one on record" in shown


def test_the_kind_selection_clears_with_every_other_filter():
    """Two reset paths, and a category left set in either empties the map."""
    html = served_page()
    assert html.count(
        "filtFeats.clear(); filtCats.clear(); filtFresh='any'") == 2
