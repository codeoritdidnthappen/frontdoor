"""Wikimedia Commons imagery, external-data round one (TICK-258, #242).

Fixture-based only — no test here touches the network. Pins the load-bearing
contracts: the geosearch call encodes gsnamespace=6 (the File namespace;
the default namespace returns zero imagery); the license gate keeps ONLY
CC0 / CC BY / CC BY-SA (any version) and drops NC/ND/unknown with counted
reasons; attribution fields are mandatory on every kept record; artist HTML
is stripped; provenance matches on photo distance (~35 m, tighter than the
OSM place radius) with no name filter; and /map/data passes Commons lines
through without altering states.
"""

import json

import pytest

from frontdoor.commons_imagery import (
    COMMONS_ATTRIBUTION,
    COMMONS_SOURCE,
    PHOTO_MATCH_DISTANCE_M,
    SHARE_ALIKE_NOTE,
    build_geosearch_params,
    build_imageinfo_params,
    commons_provenance_for_place,
    license_allowed,
    load_commons_records,
    parse_commons_payloads,
    strip_html,
    write_commons_dataset,
)
from frontdoor.map_states import STATE_NEUTRAL
from frontdoor_server.app import create_app

FETCHED_AT = "2026-09-03T12:00:00Z"

# Geometry: photos A and B sit at the reference corner; photo C is ~55m
# east of it (past the 35m radius); the NC/ND/unknown candidates share A's
# coordinates so only the license gate can drop them.
REF_LAT, REF_LON = 30.2650, -97.7460


def geosearch_hit(title, lat=REF_LAT, lon=REF_LON):
    return {"pageid": abs(hash(title)) % 10**6, "ns": 6, "title": title,
            "lat": lat, "lon": lon, "dist": 1.0}


GEOSEARCH_FIXTURE = {
    "batchcomplete": True,
    "query": {"geosearch": [
        geosearch_hit("File:Storefront ramp.jpg"),
        geosearch_hit("File:Street corner.jpg"),
        geosearch_hit("File:Far away mural.jpg", lat=30.2650, lon=-97.74543),
        geosearch_hit("File:Festival crowd.jpg"),
        geosearch_hit("File:No derivatives door.jpg"),
        geosearch_hit("File:Mystery license.jpg"),
        geosearch_hit("File:No metadata at all.jpg"),
        geosearch_hit("File:Anonymous BY-SA.jpg"),
        geosearch_hit("File:Public domain mark.jpg"),
        {"pageid": 1, "ns": 6, "title": "File:Unplaceable.jpg"},
        "junk entry",
    ]},
}


def imageinfo_page(title, license_name, artist_html, *, capture=None,
                   upload=None, omit_artist=False, omit_license=False):
    extmetadata = {}
    if not omit_license:
        extmetadata["LicenseShortName"] = {"value": license_name}
    if not omit_artist:
        extmetadata["Artist"] = {"value": artist_html}
    if capture:
        extmetadata["DateTimeOriginal"] = {"value": capture}
    if upload:
        extmetadata["DateTime"] = {"value": upload}
    slug = title.replace(" ", "_")
    return {
        "pageid": abs(hash(title)) % 10**6, "ns": 6, "title": title,
        "imageinfo": [{
            "url": f"https://upload.wikimedia.org/commons/{slug}",
            "thumburl": f"https://upload.wikimedia.org/commons/thumb/{slug}",
            "descriptionurl": f"https://commons.wikimedia.org/wiki/{slug}",
            "extmetadata": extmetadata,
        }],
    }


IMAGEINFO_FIXTURE = [{
    "batchcomplete": True,
    "query": {"pages": [
        imageinfo_page("File:Storefront ramp.jpg", "CC BY-SA 4.0",
                       '<a href="//commons.wikimedia.org/wiki/User:JD">'
                       "Jane&nbsp;Doe</a>",
                       capture="2019-03-02 14:22:11",
                       upload="2019-03-05T09:00:00Z"),
        imageinfo_page("File:Street corner.jpg", "CC0",
                       "ignored", omit_artist=True,
                       upload="2021-07-01T00:00:00Z"),
        imageinfo_page("File:Far away mural.jpg", "CC BY 2.0",
                       "<b>Sam Roe</b>", capture="2020-01-15"),
        imageinfo_page("File:Festival crowd.jpg", "CC BY-NC-SA 2.0",
                       "NC Artist"),
        imageinfo_page("File:No derivatives door.jpg", "CC BY-ND 3.0",
                       "ND Artist"),
        imageinfo_page("File:Mystery license.jpg", "unused",
                       "Someone", omit_license=True),
        imageinfo_page("File:Anonymous BY-SA.jpg", "CC BY-SA 3.0",
                       "unused", omit_artist=True),
        imageinfo_page("File:Public domain mark.jpg", "Public domain",
                       "PD Uploader"),
        # File:No metadata at all.jpg has no imageinfo page on purpose.
    ]},
}]


def parsed():
    return parse_commons_payloads(GEOSEARCH_FIXTURE, IMAGEINFO_FIXTURE,
                                  FETCHED_AT)


# --- the API contract -------------------------------------------------------


def test_geosearch_requires_file_namespace():
    """gsnamespace=6 is load-bearing: without the File namespace the
    geosearch returns zero imagery results."""
    params = build_geosearch_params(
        {"south": 30.262382, "west": -97.747630,
         "north": 30.267748, "east": -97.743692})
    assert params["gsnamespace"] == "6"
    assert params["list"] == "geosearch"
    # gsbbox order is top|left|bottom|right (north|west|south|east).
    assert params["gsbbox"] == "30.267748|-97.74763|30.262382|-97.743692"


def test_imageinfo_params_carry_extmetadata_and_urls():
    params = build_imageinfo_params(["File:A.jpg", "File:B.jpg"])
    assert params["prop"] == "imageinfo"
    assert "extmetadata" in params["iiprop"] and "url" in params["iiprop"]
    assert params["titles"] == "File:A.jpg|File:B.jpg"


# --- the license gate -------------------------------------------------------


def test_tick_b01_license_gate_families_and_versions():
    for name in ("CC0", "CC0 1.0", "CC BY 2.0", "CC BY-SA 4.0",
                 "CC BY-SA 2.5", "cc by-sa 3.0", "CC BY"):
        assert license_allowed(name), name
    for name in ("CC BY-NC-SA 2.0", "CC BY-NC 4.0", "CC BY-ND 3.0",
                 "CC BY 4.0 NC", "CC BY-SA 4.0 ND",
                 "CC0 1.0 fair-use", "Public domain", "Fair use", "",
                 None, 7):
        assert not license_allowed(name), name

    geosearch = {"query": {"geosearch": [geosearch_hit("File:Sneaky.jpg")]}}
    imageinfo = {"query": {"pages": [imageinfo_page(
        "File:Sneaky.jpg", "CC BY 4.0 NC", "Restricted Artist")]}}
    records, dropped = parse_commons_payloads(
        geosearch, [imageinfo], FETCHED_AT)
    assert records == []
    assert dropped == {"license_disallowed": 1}


def test_parse_keeps_only_open_licenses_and_counts_drops():
    records, dropped = parsed()
    kept = {r["title"] for r in records}
    assert kept == {"File:Storefront ramp.jpg", "File:Street corner.jpg",
                    "File:Far away mural.jpg"}
    # Every drop is counted under a reason; nothing vanishes silently.
    assert dropped == {
        "license_disallowed": 3,   # NC, ND, and the Public domain mark
        "license_unknown": 1,      # File:Mystery license.jpg
        "missing_artist": 1,       # BY-SA with no artist is undisplayable
        "no_imageinfo": 1,         # File:No metadata at all.jpg
        "no_coordinates": 1,       # File:Unplaceable.jpg
    }


def test_attribution_fields_are_mandatory_on_kept_records():
    records, _ = parsed()
    for record in records:
        assert record["source"] == COMMONS_SOURCE
        assert record["fetched_at"] == FETCHED_AT
        assert record["title"].startswith("File:")
        assert record["page_url"].startswith("https://commons.wikimedia.org/")
        assert record["image_url"].startswith("https://upload.wikimedia.org/")
        assert record["license"]
        assert isinstance(record["lat"], float)
        assert isinstance(record["lon"], float)
    by_title = {r["title"]: r for r in records}
    # Attribution licenses carry a named artist, HTML stripped.
    assert by_title["File:Storefront ramp.jpg"]["artist"] == "Jane Doe"
    assert by_title["File:Far away mural.jpg"]["artist"] == "Sam Roe"
    # CC0 needs no attribution, so a missing artist is allowed there.
    assert by_title["File:Street corner.jpg"]["artist"] is None
    # Capture date wins where present; upload date is kept alongside.
    ramp = by_title["File:Storefront ramp.jpg"]
    assert ramp["capture_date"] == "2019-03-02 14:22:11"
    assert ramp["upload_date"] == "2019-03-05T09:00:00Z"


def test_strip_html_removes_tags_and_entities():
    assert strip_html('<a href="/wiki/User:JD">Jane&nbsp;Doe</a>') == "Jane Doe"
    assert strip_html("<b>Sam</b> <i>Roe</i>") == "Sam Roe"
    assert strip_html("plain name") == "plain name"


def test_parse_is_total_over_junk_payloads():
    for geosearch in (None, [], "junk", {}, {"query": None},
                      {"query": {"geosearch": 7}}):
        records, dropped = parse_commons_payloads(geosearch, [], FETCHED_AT)
        assert records == [] and dropped == {}
    records, _ = parse_commons_payloads(
        GEOSEARCH_FIXTURE, [None, "junk", {}, {"query": {"pages": None}}],
        FETCHED_AT)
    assert records == []


# --- the segregated side file -----------------------------------------------


def test_written_dataset_is_segregated_and_attributed(tmp_path):
    path = tmp_path / "external" / "commons_imagery.json"
    records, dropped = parsed()
    write_commons_dataset(records, path, FETCHED_AT, dropped)
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["source"] == COMMONS_SOURCE
    assert document["attribution"] == COMMONS_ATTRIBUTION
    assert "MUST be shown" in document["attribution"]
    assert document["share_alike"] == SHARE_ALIKE_NOTE
    assert "share-alike" in document["share_alike"]
    assert "CC0" in document["license_policy"]
    assert "segregated" in document["segregation"].lower()
    assert document["record_count"] == 3
    assert document["dropped_at_ingest"]["license_disallowed"] == 3
    assert all(r["source"] == COMMONS_SOURCE for r in document["records"])
    assert load_commons_records(path) == document["records"]


def test_load_commons_records_total_over_missing_or_broken(tmp_path):
    assert load_commons_records(tmp_path / "nope.json") == []
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert load_commons_records(broken) == []
    weird = tmp_path / "weird.json"
    weird.write_text(json.dumps({"records": ["junk", 7]}), encoding="utf-8")
    assert load_commons_records(weird) == []


# --- provenance matching ----------------------------------------------------


def test_provenance_matches_on_photo_distance_only():
    records, _ = parsed()
    # At the reference corner: the two photos there match; the mural ~55m
    # east does not — photo coordinates get the tighter ~35m radius.
    assert PHOTO_MATCH_DISTANCE_M == 35.0
    lines = commons_provenance_for_place(REF_LAT, REF_LON, records)
    assert {l["url"].rsplit("/", 1)[-1] for l in lines} == {
        "File:Storefront_ramp.jpg", "File:Street_corner.jpg"}
    # A wider radius pulls the mural in; a faraway point matches nothing.
    wide = commons_provenance_for_place(REF_LAT, REF_LON, records,
                                        max_distance_m=80)
    assert len(wide) == 3
    assert commons_provenance_for_place(30.30, -97.80, records) == []
    # Junk coordinates are total, not fatal.
    assert commons_provenance_for_place(None, "x", records) == []


def test_provenance_label_carries_year_license_artist_and_url():
    records, _ = parsed()
    lines = commons_provenance_for_place(REF_LAT, REF_LON, records)
    by_url = {l["url"].rsplit("/", 1)[-1]: l for l in lines}
    ramp = by_url["File:Storefront_ramp.jpg"]
    # Capture year (2019), not upload or fetch year.
    assert ramp["label"] == ("Photo on Wikimedia Commons - 2019 - "
                             "CC BY-SA 4.0 - Jane Doe")
    assert ramp["date"] == "2019"
    assert ramp["source"] == COMMONS_SOURCE
    corner = by_url["File:Street_corner.jpg"]
    # CC0, no artist: the label ends at the license.
    assert corner["label"] == "Photo on Wikimedia Commons - 2021 - CC0"


def test_provenance_never_renders_an_unvetted_license():
    smuggled = [{
        "source": COMMONS_SOURCE, "title": "File:Sneaky.jpg",
        "page_url": "https://commons.wikimedia.org/wiki/File:Sneaky.jpg",
        "license": "CC BY-NC 2.0", "artist": "X",
        "lat": REF_LAT, "lon": REF_LON,
    }]
    assert commons_provenance_for_place(REF_LAT, REF_LON, smuggled) == []


def test_tick_b02_provenance_requires_stored_attribution_artist():
    missing_artist = [{
        "source": COMMONS_SOURCE, "title": "File:Anonymous.jpg",
        "page_url": "https://commons.wikimedia.org/wiki/File:Anonymous.jpg",
        "license": "CC BY 4.0", "artist": None,
        "lat": REF_LAT, "lon": REF_LON,
    }]
    blank_artist = [{**missing_artist[0], "artist": "  "}]
    assert commons_provenance_for_place(
        REF_LAT, REF_LON, missing_artist) == []
    assert commons_provenance_for_place(REF_LAT, REF_LON, blank_artist) == []


# --- /map/data passthrough --------------------------------------------------


@pytest.fixture
def client():
    return create_app().test_client()


def ai_row(name, lat, lng):
    return {
        "name": name,
        "location": {"lat": lat, "lng": lng},
        "source": "streetview",
        "status": "ai_estimated",
        "criteria": {"ramp_or_bevel": {"verdict": "present",
                                       "confidence": 0.9}},
    }


def test_map_data_attaches_commons_lines_without_touching_states(
        client, tmp_path, monkeypatch):
    dataset = {
        "near_photo": ai_row("Corner Cafe", REF_LAT, REF_LON),
        "far_from_photos": ai_row("Distant Deli", 30.30, -97.80),
    }
    dataset_path = tmp_path / "precatalogue.json"
    dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
    monkeypatch.setenv("FRONTDOOR_MAP_DATASET", str(dataset_path))
    monkeypatch.setenv("FRONTDOOR_EXTERNAL_OSM", str(tmp_path / "no-osm.json"))
    commons_path = tmp_path / "commons_imagery.json"
    records, dropped = parsed()
    write_commons_dataset(records, commons_path, FETCHED_AT, dropped)
    monkeypatch.setenv("FRONTDOOR_EXTERNAL_COMMONS", str(commons_path))

    payload = client.get("/map/data").get_json()
    pins = {pin["place_id"]: pin for pin in payload["pins"]}
    near = pins["near_photo"]
    assert any(line["source"] == COMMONS_SOURCE
               and line["label"].startswith("Photo on Wikimedia Commons - ")
               for line in near["provenance"])
    # A photo line is a neutral fact: no state ever derives from it.
    assert "provenance" not in pins["far_from_photos"]
    assert all(pin["state"] == STATE_NEUTRAL for pin in pins.values())


def test_map_data_unchanged_without_commons_file(client, tmp_path, monkeypatch):
    dataset_path = tmp_path / "precatalogue.json"
    dataset_path.write_text(
        json.dumps({"p": ai_row("Corner Cafe", REF_LAT, REF_LON)}),
        encoding="utf-8")
    monkeypatch.setenv("FRONTDOOR_MAP_DATASET", str(dataset_path))
    monkeypatch.setenv("FRONTDOOR_EXTERNAL_OSM", str(tmp_path / "no-osm.json"))
    monkeypatch.setenv("FRONTDOOR_EXTERNAL_COMMONS",
                       str(tmp_path / "absent.json"))
    payload = client.get("/map/data").get_json()
    (pin,) = payload["pins"]
    assert "provenance" not in pin
    assert pin["state"] == STATE_NEUTRAL
