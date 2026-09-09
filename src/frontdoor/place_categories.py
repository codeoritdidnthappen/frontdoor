"""What a place *is*, from OpenStreetMap (TICK-491, #491).

The map could already be filtered by what a visitor NEEDS. It could not be
filtered by what a place IS, which is backwards from how anyone looks for
somewhere to go: the query is "a coffee shop I can get into", not "every
door within 300 feet that has a ramp".

WHERE THE CATEGORY COMES FROM, AND WHERE IT MUST NOT
----------------------------------------------------
Not from the name. "Group Therapy" is a bar, "Hemline" is a clothing shop,
"Serenade" could be anything. A name-based classifier would guess, it would
be wrong on exactly the places most likely to be looked at, and it could not
say where its answer came from. Every other fact on this map cites a source;
a category does too.

**OpenStreetMap only.** ``amenity`` / ``shop`` / ``tourism`` / ``office`` /
``leisure`` / ``craft`` / ``healthcare`` tags, fetched by Overpass, free and
keyless, stored in a segregated ODbL side file exactly as
``frontdoor.external_data`` stores the wheelchair tags.

**Google Places is deliberately NOT a source here.** #242 records the
posture: the Places terms forbid storing anything but ``place_id``, and
#242's own audit has an unresolved, blocking violation open against that
criterion already. A cached ``types`` field would stack a second violation
on an unsettled first, so nothing in this module fetches from Places or
reads a Places field other than the identifiers the pre-catalogue already
holds.

LICENCE AND SEGREGATION (load-bearing, same rule as external_data)
------------------------------------------------------------------
OSM data is ODbL. It lives ONLY in ``data/external/osm_categories.json``
with the attribution in the file header and ``source="openstreetmap"`` on
every record. Per the ODbL Collective Database Guideline it never merges
into ``data/precatalogue.json``; it is joined at render time and dropped.

MATCHING, AND WHY IT IS STRICTER THAN PROVENANCE MATCHING
---------------------------------------------------------
``external_data.match_records`` falls back to distance alone when either
side is unnamed. That is defensible for a provenance line, which only ever
adds a second witness. It is *not* defensible for a category, because the
category becomes the pin's answer to "what is this place", and a wrong one
is a statement about a named real business.

Measured over the committed demo bbox: the distance-only rule types 173 of
186 pins, but 134 of those match more than one element, and 102 of the 234
category-bearing elements in the box are unnamed street furniture. It types
Group Therapy (a bar) from an ``amenity=parking_space`` 6 m away, First
Citizens Bank as ``amenity=restaurant``, Keen Salon as ``tourism=hotel``,
and Serenade as ``tourism=artwork``.

So a category match requires IDENTITY, in this order:

1. an exact last-10-digit phone match, or
2. an exact website host match, or
3. a fuzzy name match (external_data's own comparison), both sides named.

An unnamed OSM element can never supply a category. That takes coverage to
64 of 186 pins (34.4%) with no ambiguous match at all, and the honest
consequence is that **122 places have no category on record**. The interface
states that rather than hiding it; see the Filters sheet.

Network calls happen ONLY in the CLI path (``python -m
frontdoor.place_categories --refresh``); importing this module performs no
I/O, and tests use fixture payloads.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from frontdoor.external_data import (
    ODBL_ATTRIBUTION,
    OSM_SOURCE,
    OVERPASS_URL,
    SEGREGATION_NOTE,
    ExternalDataError,
    _haversine_m,
    _is_number,
    _names_match,
    fetch_overpass,
    load_demo_bbox,
    load_side_file,
)

DEFAULT_OUT_DIR = Path("data/external")
CATEGORIES_FILENAME = "osm_categories.json"

# The OSM keys that answer "what kind of place is this". Order matters: the
# first one an element carries decides its category, so the specific keys
# come before the catch-alls (an element tagged shop=bakery AND amenity=cafe
# is a bakery).
CATEGORY_KEYS = (
    "shop",
    "amenity",
    "tourism",
    "leisure",
    "craft",
    "healthcare",
    "office",
)

# Category match is an identity claim about a named business, so it is
# stricter than the 40 m provenance radius is loose: the same distance, but
# an identity signal is required on top of it.
DEFAULT_MATCH_DISTANCE_M = 40.0


# --- the mapping ------------------------------------------------------------
#
# Few, human categories -- what a person would say, not what OSM calls it.
# The lists are deliberately WIDER than the demo bbox happens to contain, so
# this is a mapping rather than a fit to 64 rows; tags outside them leave a
# place untyped rather than dropping it into a nearest-fit bucket.
#
# Anything not listed here is untyped ON PURPOSE. `amenity=bench`,
# `amenity=parking_space`, `amenity=waste_basket` and the rest of the street
# furniture are not places you go, and a bucket that swallowed them would be
# the distance-only bug wearing a different hat.

CATEGORIES = (
    (
        "food_drink",
        "Food and drink",
        {
            "amenity": (
                "restaurant", "cafe", "fast_food", "bar", "pub", "biergarten",
                "ice_cream", "food_court", "juice_bar",
            ),
            "shop": (
                "bakery", "coffee", "deli", "pastry", "confectionery",
                "chocolate", "alcohol", "wine", "beverages", "tea", "butcher",
                "greengrocer", "seafood", "cheese", "farm", "spices",
                "food", "frozen_food", "health_food",
            ),
        },
    ),
    (
        "shops",
        "Shops",
        {
            "shop": (
                "clothes", "shoes", "boutique", "bag", "jewelry", "watches",
                "gift", "books", "music", "musical_instrument", "art",
                "antiques", "convenience", "supermarket", "department_store",
                "variety_store", "second_hand", "charity", "chemist",
                "cosmetics", "perfumery", "electronics", "mobile_phone",
                "computer", "florist", "furniture", "houseware", "interior_decoration",
                "hardware", "doityourself", "garden_centre", "optician",
                "sports", "outdoor", "bicycle", "toys", "games", "pet",
                "stationery", "photo", "tobacco", "e-cigarette", "kiosk",
                "newsagent", "fabric", "leather", "video_games", "trade",
            ),
        },
    ),
    (
        "services",
        "Services",
        {
            "shop": (
                "hairdresser", "beauty", "massage", "nails", "tattoo",
                "dry_cleaning", "laundry", "tailor", "shoe_repair", "copyshop",
                "travel_agency", "estate_agent", "insurance", "funeral_directors",
                "car_repair", "car", "locksmith", "hearing_aids", "medical_supply",
            ),
            "amenity": (
                "bank", "bureau_de_change", "pharmacy", "doctors", "dentist",
                "clinic", "hospital", "veterinary", "post_office", "childcare",
                "kindergarten", "school", "college", "university", "driving_school",
                "coworking_space",
            ),
            "leisure": ("fitness_centre", "sports_centre", "sauna"),
            # Any office and any healthcare tag: the sub-values are a long
            # tail nobody would filter on individually, and "Services" is the
            # word a person would use for all of them.
            "office": ("*",),
            "healthcare": ("*",),
            "craft": ("*",),
        },
    ),
    (
        "culture_nightlife",
        "Culture and nightlife",
        {
            "amenity": (
                "nightclub", "theatre", "cinema", "arts_centre", "events_venue",
                "community_centre", "library", "casino", "music_venue",
                "conference_centre", "studio", "place_of_worship",
            ),
            "tourism": ("museum", "gallery", "aquarium", "zoo", "theme_park"),
            "shop": ("art_gallery",),
            "leisure": ("dance", "bowling_alley", "escape_game", "amusement_arcade"),
        },
    ),
    (
        "stay",
        "Places to stay",
        {
            "tourism": (
                "hotel", "hostel", "motel", "guest_house", "apartment",
                "chalet", "bed_and_breakfast",
            ),
        },
    ),
)

CATEGORY_LABELS = {key: label for key, label, _ in CATEGORIES}

# {osm_key: {osm_value: category_key}}, plus "*" for whole-key categories.
_TAG_INDEX: dict[str, dict[str, str]] = {}
for _key, _label, _tags in CATEGORIES:
    for _osm_key, _values in _tags.items():
        bucket = _TAG_INDEX.setdefault(_osm_key, {})
        for _value in _values:
            bucket.setdefault(_value, _key)


def category_for_tags(tags):
    """(category_key, "osm_key=osm_value") for OSM tags, or (None, None).

    Untyped is a real answer and the common one. Nothing is forced into a
    nearest-fit bucket: a tag this mapping does not name leaves the place
    without a category, and the interface says so.
    """
    if not isinstance(tags, dict):
        return None, None
    for osm_key in CATEGORY_KEYS:
        value = tags.get(osm_key)
        if not isinstance(value, str) or not value:
            continue
        bucket = _TAG_INDEX.get(osm_key)
        if not bucket:
            continue
        category = bucket.get(value) or bucket.get("*")
        if category:
            return category, f"{osm_key}={value}"
    return None, None


# --- identity ---------------------------------------------------------------


def phone_key(value):
    """The last 10 digits of a phone number, or "" — the comparable part.

    "+1-512-474-2212", "(512) 474-2212" and "512.474.2212" are one business.
    """
    digits = re.sub(r"\D", "", value or "")
    return digits[-10:] if len(digits) >= 10 else ""


def website_key(value):
    """A website's bare host, or "" — "https://www.foo.com/menu" -> "foo.com"."""
    match = re.search(r"^(?:https?://)?(?:www\.)?([^/?#\s]+)", (value or "").strip().lower())
    return match.group(1) if match else ""


def _record_keys(record):
    tags = record.get("tags") or {}
    phones = {phone_key(tags.get(k)) for k in ("phone", "contact:phone")}
    hosts = {website_key(tags.get(k)) for k in ("website", "contact:website", "url")}
    return phones - {""}, hosts - {""}


def match_category_record(name, lat, lon, phone, website, records,
                          max_distance_m=DEFAULT_MATCH_DISTANCE_M):
    """The one OSM record that IS this place, or None.

    Identity, not proximity: a phone or website that matches exactly, or a
    name both sides carry and that resembles the other. An unnamed OSM
    element can never supply a category, whatever the distance -- that is
    the rule that keeps a bar from being typed as the parking space beside
    it. Returns (record, how) so the payload can say which signal matched.
    """
    if not _is_number(lat) or not _is_number(lon):
        return None
    want_phone, want_host = phone_key(phone), website_key(website)
    fallback = None
    for record in records:
        if not _is_number(record.get("lat")) or not _is_number(record.get("lon")):
            continue
        if _haversine_m(lat, lon, record["lat"], record["lon"]) > max_distance_m:
            continue
        phones, hosts = _record_keys(record)
        if want_phone and want_phone in phones:
            return record, "phone"
        if want_host and want_host in hosts:
            return record, "website"
        record_name = record.get("name")
        if (fallback is None and isinstance(name, str) and name
                and isinstance(record_name, str) and record_name
                and _names_match(name, record_name)):
            fallback = (record, "name")
    return fallback


def category_for_place(name, lat, lon, phone, website, records,
                       max_distance_m=DEFAULT_MATCH_DISTANCE_M):
    """The pin's category as a JSON-ready dict, or None when untyped.

    The source travels WITH the fact, the way every other fact on this map
    does: which OSM element said it, its URL, the raw tag, how it was
    matched, and the ODbL attribution.

    This is a statement about what the place is. It carries no accessibility
    claim, it is not one of the engine's criteria (#481), and it can never
    change a pin's tier, state or checklist -- /map/data attaches it after
    those are computed, and nothing downstream reads it.
    """
    matched = match_category_record(name, lat, lon, phone, website, records,
                                    max_distance_m)
    if not matched:
        return None
    record, how = matched
    key, tag = category_for_tags(record.get("tags"))
    if not key:
        return None
    osm_type, osm_id = record.get("osm_type"), record.get("osm_id")
    url = None
    if osm_type in ("node", "way", "relation") and isinstance(osm_id, int):
        url = f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
    return {
        "key": key,
        "label": CATEGORY_LABELS[key],
        "source": OSM_SOURCE,
        "tag": tag,
        "matched_on": how,
        "osm_type": osm_type,
        "osm_id": osm_id,
        "url": url,
        "detail": "© OpenStreetMap contributors (ODbL)",
    }


# --- ingest -----------------------------------------------------------------


def build_overpass_query(bbox):
    """Overpass QL for every category-bearing element in a bbox.

    ``nwr`` covers nodes, ways and relations in one clause per key, and
    ``out center`` gives ways a representative coordinate. One query rather
    than fourteen keeps this inside a single Overpass call.
    """
    box = "{south},{west},{north},{east}".format(**bbox)
    clauses = "\n".join(f'  nwr["{key}"]({box});' for key in CATEGORY_KEYS)
    return f"[out:json][timeout:180];\n(\n{clauses}\n);\nout center tags;"


def parse_overpass_payload(payload, fetched_at):
    """Overpass JSON -> segregated category records.

    Elements without coordinates, without a name, or whose tags this
    mapping does not name are dropped at ingest: an unnamed element can
    never match anyway (see match_category_record), and storing it would
    only invite a later change to start using it.
    """
    records = []
    elements = payload.get("elements") if isinstance(payload, dict) else None
    if not isinstance(elements, list):
        elements = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        tags = element.get("tags")
        if not isinstance(tags, dict) or not tags:
            continue
        name = tags.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        key, _tag = category_for_tags(tags)
        if not key:
            continue
        lat, lon = element.get("lat"), element.get("lon")
        if lat is None or lon is None:
            center = element.get("center")
            if isinstance(center, dict):
                lat, lon = center.get("lat"), center.get("lon")
        if not _is_number(lat) or not _is_number(lon):
            continue
        records.append({
            "source": OSM_SOURCE,
            "fetched_at": fetched_at,
            "osm_type": element.get("type"),
            "osm_id": element.get("id"),
            "name": name,
            "lat": float(lat),
            "lon": float(lon),
            "category": key,
            "tags": tags,
        })
    return records


def write_categories_dataset(records, path, fetched_at):
    """Write the segregated ODbL side file, attribution in the header."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "source": OSM_SOURCE,
        "license": "ODbL-1.0",
        "attribution": ODBL_ATTRIBUTION,
        "segregation": SEGREGATION_NOTE,
        "fetched_at": fetched_at,
        "record_count": len(records),
        "records": records,
    }
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return document


def load_category_records(path):
    """Records from the side file; ([], error) when missing or unreadable.

    Total on purpose: the map renders with or without categories, and a
    missing file simply means no pin carries one and the Filters sheet does
    not offer the section.
    """
    return load_side_file(path, "osm categories")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--refresh" not in argv:
        print(__doc__.splitlines()[0])
        print("\nusage: python -m frontdoor.place_categories --refresh [--out DIR]")
        return 0
    out_dir = Path(DEFAULT_OUT_DIR)
    if "--out" in argv:
        out_dir = Path(argv[argv.index("--out") + 1])
    bbox = load_demo_bbox()
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = fetch_overpass(build_overpass_query(bbox), url=OVERPASS_URL)
    records = parse_overpass_payload(payload, fetched_at)
    path = out_dir / CATEGORIES_FILENAME
    write_categories_dataset(records, path, fetched_at)
    counts = {}
    for record in records:
        counts[record["category"]] = counts.get(record["category"], 0) + 1
    print(f"wrote {len(records)} category records to {path}")
    for key, label, _tags in CATEGORIES:
        print(f"  {label:<24} {counts.get(key, 0)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
