"""Street View batch pre-catalogue for the demo area (TICK-248, #170).

Enumerates the demo area's storefront businesses with the Google Places API,
retrieves 2-4 storefront-facing Street View Static images per business where
coverage exists, and runs the screening engine (TICK-245) over the imagery in
an offline batch. Output is a place_id-keyed dataset in the shape TICK-247's
map consumes.

Honesty rules (load-bearing, do not relax):
- Everything here is imagery-derived. Every row is flagged
  source="streetview", status="ai_estimated" — per TICK-247's rule the
  pre-catalogue never turns a business green.
- Businesses without usable Street View coverage are recorded as uncovered,
  never silently dropped.
- The Street View imagery date is preserved per row: stale imagery is the
  main honest caveat for this dataset.

Cost discipline: the screening engine's own spend cap governs model spend;
a separate maps-API call cap lives in this module's config. Hitting either
cap stops the run cleanly — the dataset is keyed by place_id and rows already
present are skipped on re-run, so a stopped run resumes rather than
duplicating.

Listing contact (phone, website) is not in Nearby Search. A Place Details
call per place copies those fields onto the row so owner-claim channels can
use the listing as authority. They are catalogue-private: the public map pin
is a separately constructed object and does not copy them.

The API key comes from the GOOGLE_MAPS_API_KEY environment variable and is
never hardcoded. All network calls go through small injectable fetch
functions so tests mock them; no test hits the network.

Run as a tool:  python -m frontdoor.precatalogue run [out_dir]
                 python -m frontdoor.precatalogue enrich [out_dir]
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from frontdoor.screening import (
    CRITERIA_KEYS,
    ScreeningEngine,
    SpendCapError,
    aggregate_assessments,
)

PLACES_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
PLACES_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
STREETVIEW_METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
STREETVIEW_IMAGE_URL = "https://maps.googleapis.com/maps/api/streetview"
# Contact only. Nearby Search cannot return these; asking for anything else
# here would bill a higher Place Details SKU without helping the claim flow.
DETAILS_FIELDS = "formatted_phone_number,international_phone_number,website"

IMAGE_SIZE = "640x640"
IMAGE_FOV = 90

# A next_page_token is not valid the instant it is issued: requesting with it
# too soon returns INVALID_REQUEST. Undocumented in length, universally ~2s.
PAGE_TOKEN_DELAY_S = 2.0
PAGE_TOKEN_ATTEMPTS = 4

# Nearby Search never returns more than three pages of 20. A block that comes
# back full was not necessarily finished -- it was cut off, and the difference
# is invisible from the response.
NEARBY_SEARCH_MAX_RESULTS = 60

# Storefront-relevant Places types for targeted sweeps (TICK-248 round two).
#
# One type=establishment sweep per block hits the 60-result cap long before it
# runs out of businesses in the demo area: the blocks contain office towers
# where every suite is an establishment, so the cap fills with lawyers and
# consultancies on the 14th floor and street-level storefronts drown. Measured:
# even a 12x12 subdivision of the demo box (~33 m cells) still truncated in 4
# sub-blocks. Sweeping per *type* changes what competes for the 60 slots --
# a restaurant only competes with restaurants -- and the storefront types below
# are the businesses that have a street entrance to screen, which is the whole
# point of the pre-catalogue.
#
# Curation rationale, by group:
# - Food and drink (restaurant, cafe, bar, bakery, meal_takeaway): street
#   entrances near-universally, the densest storefront category downtown.
# - Retail ("store" plus specific subtypes): "store" is the umbrella type the
#   API attaches to most retail, so it catches shops with no finer type -- but
#   as an umbrella it can itself truncate at 60, and the specific subtypes
#   (clothing_store, shoe_store, jewelry_store, book_store, convenience_store,
#   liquor_store, florist) recover what the umbrella's cap drops.
# - Street-level services (pharmacy, gym, hair_care, beauty_salon, spa,
#   laundry, bank): walk-in premises with a door to assess.
# - lodging and art_gallery: hotels and galleries have public street entrances
#   worth screening even though they are not shops.
# Deliberately excluded: establishment/point_of_interest (the umbrella noise
# this list exists to avoid) and the office-suite types that were crowding out
# the cap -- lawyer, doctor, dentist, accounting, insurance_agency,
# real_estate_agency -- which have suites, not storefronts.
STOREFRONT_PLACE_TYPES = (
    "restaurant", "cafe", "bar", "bakery", "meal_takeaway",
    "store", "clothing_store", "shoe_store", "jewelry_store", "book_store",
    "convenience_store", "liquor_store", "florist",
    "pharmacy", "gym", "hair_care", "beauty_salon", "spa", "laundry", "bank",
    "lodging", "art_gallery",
)

DATASET_FILENAME = "precatalogue.json"
SUMMARY_FILENAME = "precatalogue_summary.json"
CENSUS_FILENAME = "precatalogue_census.json"

DEFAULT_CONFIG_PATH = Path(__file__).with_name("demo_area.json")

# Storefront-facing headings: symmetric offsets (degrees) around the bearing
# from the Street View panorama to the business location.
HEADING_OFFSETS = {
    2: (-20.0, 20.0),
    3: (-30.0, 0.0, 30.0),
    4: (-45.0, -15.0, 15.0, 45.0),
}


class PrecatalogueError(Exception):
    """Missing config or key, or a maps API call failed."""


class ConfigError(PrecatalogueError):
    """The demo-area config is missing or invalid."""


class MapsCallCapError(PrecatalogueError):
    """The next maps API call would exceed the configured call cap."""


@dataclass(frozen=True)
class DemoArea:
    name: str
    blocks: tuple  # of {"name", "lat", "lng", "radius_m"}
    headings_per_business: int
    max_maps_calls: int
    # The declared area, when the config gave one. The search circle that
    # covers a box is much larger than the box, so results are filtered back
    # to this. None when the config defined blocks directly -- a circle is
    # then the area itself and there is nothing to filter against.
    bounds: dict | None = None
    # Targeted per-type sweeps (TICK-248 round two). Empty means the original
    # single type=establishment sweep -- existing configs keep behaving exactly
    # as they did. include_establishment_sweep adds the establishment sweep on
    # top of the typed ones: it catches oddballs the type list misses, at the
    # cost of re-admitting the office-suite noise that fills its own 60 cap.
    place_types: tuple = ()
    include_establishment_sweep: bool = False

    @property
    def sweep_types(self):
        """The Nearby Search type sweeps to run per block, in order."""
        if not self.place_types:
            return ("establishment",)
        if self.include_establishment_sweep:
            return self.place_types + ("establishment",)
        return self.place_types

    def contains(self, location):
        """Is this location inside the declared area?

        True when no box was declared: the blocks are then the area. False for
        a location the API returned without usable coordinates -- it cannot be
        placed on a map or coverage-checked, and passing it on would send
        "None,None" to the metadata endpoint.
        """
        lat, lng = location.get("lat"), location.get("lng")
        if not isinstance(lat, (int, float)) or isinstance(lat, bool):
            return False
        if not isinstance(lng, (int, float)) or isinstance(lng, bool):
            return False
        if self.bounds is None:
            return True
        return (self.bounds["south"] <= lat <= self.bounds["north"]
                and self.bounds["west"] <= lng <= self.bounds["east"])


@dataclass(frozen=True)
class Enumeration:
    """Businesses found, and where the API may have cut the list short.
    Truncation is reported rather than inferred from a count that looks
    complete.

    truncated_types names each (block, type) sweep that returned the API
    maximum; truncated_blocks keeps its original meaning -- a block where any
    sweep was cut short -- so existing consumers still get their answer.
    """

    places: tuple
    truncated_blocks: tuple
    truncated_types: tuple = ()


def load_api_key(env=None):
    env = os.environ if env is None else env
    key = env.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not key:
        raise PrecatalogueError(
            "GOOGLE_MAPS_API_KEY is not set; the pre-catalogue needs a Google "
            "Maps API key (Places + Street View Static) in the environment"
        )
    return key


def _require_number(config, key, context):
    value = config.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigError(f"{context}: {key!r} must be a number, got {value!r}")
    return float(value)


def _haversine_m(lat1, lng1, lat2, lng2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
    return 6_371_000 * 2 * math.asin(math.sqrt(a))


def _require_bounding_box(box):
    for key in ("south", "west", "north", "east"):
        _require_number(box, key, "bounding_box")
    if box["south"] >= box["north"]:
        raise ConfigError("bounding_box: south must be less than north")
    if box["west"] >= box["east"]:
        raise ConfigError("bounding_box: west must be less than east")


def _block_from_bounding_box(box, name):
    _require_bounding_box(box)
    lat = (box["south"] + box["north"]) / 2
    lng = (box["west"] + box["east"]) / 2
    radius_m = math.ceil(_haversine_m(lat, lng, box["north"], box["east"]))
    return {"name": name, "lat": lat, "lng": lng, "radius_m": radius_m}


def _validated_grid(raw):
    """Optional 'grid': how many sub-boxes to cut a bounding_box into.

    Absent means one covering circle, exactly as before. #259 left this open:
    the 60-result cap is per query, so once a per-type sweep still truncates,
    the only remaining lever is a smaller search circle. Subdividing keeps the
    declared box as the filter -- only the search geometry changes.
    """
    if "grid" not in raw:
        return (1, 1)
    grid = raw["grid"]
    if not isinstance(grid, dict):
        raise ConfigError("grid must be an object with 'rows' and 'cols'")
    values = []
    for key in ("rows", "cols"):
        value = grid.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ConfigError(
                f"grid: {key!r} must be a positive integer, got {value!r}")
        values.append(value)
    if "bounding_box" not in raw:
        # 'blocks' already says where to search; a grid over it means nothing.
        raise ConfigError("grid applies to 'bounding_box', not to 'blocks'")
    return tuple(values)


def _blocks_from_bounding_box(box, name, rows, cols):
    """One covering circle per grid cell of the declared box."""
    _require_bounding_box(box)
    blocks = []
    lat_step = (box["north"] - box["south"]) / rows
    lng_step = (box["east"] - box["west"]) / cols
    for row in range(rows):
        for col in range(cols):
            cell = {
                "south": box["south"] + row * lat_step,
                "north": box["south"] + (row + 1) * lat_step,
                "west": box["west"] + col * lng_step,
                "east": box["west"] + (col + 1) * lng_step,
            }
            cell_name = name if rows == cols == 1 else f"{name}-r{row}c{col}"
            blocks.append(_block_from_bounding_box(cell, cell_name))
    return tuple(blocks)


def _validated_block(block, index):
    context = f"blocks[{index}]"
    if not isinstance(block, dict):
        raise ConfigError(f"{context}: each block must be an object")
    lat = _require_number(block, "lat", context)
    lng = _require_number(block, "lng", context)
    radius_m = _require_number(block, "radius_m", context)
    if not -90 <= lat <= 90 or not -180 <= lng <= 180:
        raise ConfigError(f"{context}: lat/lng out of range: {lat}, {lng}")
    if radius_m <= 0:
        raise ConfigError(f"{context}: radius_m must be positive")
    return {
        "name": str(block.get("name", f"block-{index}")),
        "lat": lat,
        "lng": lng,
        "radius_m": radius_m,
    }


def load_demo_area(path=None):
    """Load and validate the committed demo-area config.

    The config defines the area exactly once: either a bounding_box (normalized
    to one covering search circle) or a blocks list of search circles.
    """
    path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"demo-area config not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"demo-area config is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("demo-area config must be a JSON object")

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("demo-area config needs a non-empty 'name'")

    has_box = "bounding_box" in raw
    has_blocks = "blocks" in raw
    if has_box == has_blocks:
        raise ConfigError(
            "demo-area config must define exactly one of 'bounding_box' or "
            "'blocks'"
        )
    bounds = None
    grid = _validated_grid(raw)
    if has_box:
        if not isinstance(raw["bounding_box"], dict):
            raise ConfigError("bounding_box must be an object")
        blocks = _blocks_from_bounding_box(raw["bounding_box"], name, *grid)
        bounds = {key: float(raw["bounding_box"][key])
                  for key in ("south", "west", "north", "east")}
    else:
        if not isinstance(raw["blocks"], list) or not raw["blocks"]:
            raise ConfigError("blocks must be a non-empty list")
        blocks = tuple(
            _validated_block(block, i) for i, block in enumerate(raw["blocks"])
        )

    headings = raw.get("headings_per_business")
    if headings not in HEADING_OFFSETS:
        raise ConfigError(
            f"headings_per_business must be one of "
            f"{sorted(HEADING_OFFSETS)}, got {headings!r}"
        )

    cap = raw.get("max_maps_calls")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0:
        raise ConfigError(
            f"max_maps_calls must be a positive integer, got {cap!r}"
        )

    place_types = _validated_place_types(raw)
    include_establishment = raw.get("include_establishment_sweep", False)
    if not isinstance(include_establishment, bool):
        raise ConfigError(
            f"include_establishment_sweep must be a boolean, got "
            f"{include_establishment!r}"
        )
    if include_establishment and not place_types:
        # Without place_types the establishment sweep already is the sweep;
        # the flag would be a silent no-op hiding a config mistake.
        raise ConfigError(
            "include_establishment_sweep needs 'place_types': without them "
            "the establishment sweep is already the only sweep"
        )

    return DemoArea(
        name=name,
        blocks=blocks,
        headings_per_business=headings,
        max_maps_calls=cap,
        bounds=bounds,
        place_types=place_types,
        include_establishment_sweep=include_establishment,
    )


def _validated_place_types(raw):
    """Optional 'place_types': the per-type sweep list. Absent means the
    original establishment-only sweep, so existing configs are untouched."""
    if "place_types" not in raw:
        return ()
    types = raw["place_types"]
    if not isinstance(types, list) or not types:
        raise ConfigError("place_types must be a non-empty list of type names")
    seen = []
    for entry in types:
        if not isinstance(entry, str) or not entry.strip():
            raise ConfigError(
                f"place_types entries must be non-empty strings, got {entry!r}"
            )
        if entry in seen:
            # A duplicate is a paid-for sweep that can find nothing new.
            raise ConfigError(f"place_types lists {entry!r} twice")
        seen.append(entry)
    return tuple(seen)


def _http_get_json(url, params):
    full = url + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(full, timeout=30) as response:
        return json.load(response)


def _http_get_bytes(url, params):
    full = url + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(full, timeout=30) as response:
        return response.read()


class MapsCallCounter:
    """Counts maps API calls and refuses to exceed the configured cap."""

    def __init__(self, cap):
        self.cap = cap
        self.counts = {"places": 0, "details": 0, "metadata": 0, "image": 0}

    @property
    def total(self):
        return sum(self.counts.values())

    def tick(self, kind):
        if self.total + 1 > self.cap:
            raise MapsCallCapError(
                f"next {kind} call would be maps API call {self.total + 1}, "
                f"over the configured cap of {self.cap}; stopping — re-run to "
                "resume (existing rows are skipped)"
            )
        self.counts[kind] += 1


def enumerate_places(area, api_key, counter, fetch_json=_http_get_json,
                     sleep=time.sleep):
    """Enumerate the demo area's businesses, deduplicated by place_id.

    Returns an Enumeration: the places, and the blocks whose result list came
    back full and may therefore have been cut short by the API.

    Results are filtered back to the declared bounding box. The search circle
    that covers a box is close to twice its area, so roughly half of what the
    API returns for a box can sit outside the area the team actually declared
    -- and those results also consume the 60 the API is willing to give.

    With place_types configured, each block gets one sweep per type instead of
    a single type=establishment sweep, unioned by place_id. The 60-result cap
    is per query, so what a type filter changes is what competes for the 60
    slots: in an office tower every suite is an establishment and the untyped
    sweep's cap fills with them, while a restaurant sweep's cap can only fill
    with restaurants -- and the storefront types are the businesses with a
    street entrance to screen. Each place records which sweeps returned it.
    """
    places = {}
    truncated = []  # (block name, sweep type) pairs, in discovery order
    for block in area.blocks:
        for sweep_type in area.sweep_types:
            params = {
                "location": f"{block['lat']},{block['lng']}",
                "radius": int(block["radius_m"]),
                "type": sweep_type,
                "key": api_key,
            }
            returned = 0
            while True:
                page = _fetch_places_page(
                    params, block, counter, fetch_json, sleep)
                for result in page.get("results", []):
                    returned += 1
                    place_id = result.get("place_id")
                    if not place_id:
                        continue
                    if place_id in places:
                        sweeps = places[place_id]["sweeps"]
                        if sweep_type not in sweeps:
                            sweeps.append(sweep_type)
                        continue
                    location = {
                        "lat": result.get("geometry", {})
                                     .get("location", {}).get("lat"),
                        "lng": result.get("geometry", {})
                                     .get("location", {}).get("lng"),
                    }
                    if not area.contains(location):
                        continue
                    places[place_id] = {
                        "place_id": place_id,
                        "name": result.get("name", ""),
                        "location": location,
                        "sweeps": [sweep_type],
                    }
                token = page.get("next_page_token")
                if not token:
                    break
                params = {"pagetoken": token, "key": api_key}
            if returned >= NEARBY_SEARCH_MAX_RESULTS:
                truncated.append((block["name"], sweep_type))
    # A block is truncated when any of its sweeps was; preserve first-seen
    # order without duplicates for a block cut short in several sweeps.
    truncated_blocks = list(dict.fromkeys(name for name, _ in truncated))
    return Enumeration(places=tuple(places.values()),
                       truncated_blocks=tuple(truncated_blocks),
                       truncated_types=tuple(truncated))


def _fetch_places_page(params, block, counter, fetch_json, sleep):
    """One page of Nearby Search, waiting out the next_page_token delay.

    A token is not valid the moment it is handed over; asking with it straight
    away answers INVALID_REQUEST. Without the wait every area holding more than
    one page of businesses fails on its second request, which is every area
    worth pre-cataloguing.
    """
    paged = "pagetoken" in params
    for attempt in range(PAGE_TOKEN_ATTEMPTS):
        if paged:
            sleep(PAGE_TOKEN_DELAY_S)
        counter.tick("places")
        page = fetch_json(PLACES_SEARCH_URL, params)
        status = page.get("status")
        if status in ("OK", "ZERO_RESULTS"):
            return page
        # Only a paged request can be waiting on a token; an unpaged
        # INVALID_REQUEST is a malformed query and retrying cannot fix it.
        if status == "INVALID_REQUEST" and paged \
                and attempt < PAGE_TOKEN_ATTEMPTS - 1:
            continue
        raise PrecatalogueError(
            f"Places search failed for block {block['name']!r}: "
            f"status {status!r}"
        )


def streetview_metadata(location, api_key, counter, fetch_json=_http_get_json):
    """Coverage check first: the metadata endpoint is free and returns the
    imagery date, so no image is paid for at an uncovered location."""
    counter.tick("metadata")
    return fetch_json(STREETVIEW_METADATA_URL, {
        "location": f"{location['lat']},{location['lng']}",
        "source": "outdoor",
        "key": api_key,
    })


def bearing_deg(from_lat, from_lng, to_lat, to_lng):
    """Initial bearing in degrees from one point toward another."""
    phi1, phi2 = math.radians(from_lat), math.radians(to_lat)
    dlam = math.radians(to_lng - from_lng)
    x = math.sin(dlam) * math.cos(phi2)
    y = (math.cos(phi1) * math.sin(phi2)
         - math.sin(phi1) * math.cos(phi2) * math.cos(dlam))
    return math.degrees(math.atan2(x, y)) % 360.0


def storefront_headings(pano_location, place_location, count):
    """Headings facing the storefront: offsets around the pano-to-business
    bearing. Falls back to due north when the two points coincide."""
    if (pano_location["lat"], pano_location["lng"]) == (
            place_location["lat"], place_location["lng"]):
        base = 0.0
    else:
        base = bearing_deg(
            pano_location["lat"], pano_location["lng"],
            place_location["lat"], place_location["lng"],
        )
    return [round((base + offset) % 360.0, 1)
            for offset in HEADING_OFFSETS[count]]


def fetch_streetview_image(pano_id, heading, api_key, counter,
                           fetch_bytes=_http_get_bytes):
    counter.tick("image")
    return fetch_bytes(STREETVIEW_IMAGE_URL, {
        "pano": pano_id,
        "size": IMAGE_SIZE,
        "heading": heading,
        "fov": IMAGE_FOV,
        "key": api_key,
    })


def _nonempty_str(value):
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def contact_from_details(result):
    """Phone and website from a Place Details `result` object.

    Missing or blank fields become None. The claimant never supplies these.
    """
    if not isinstance(result, dict):
        return None, None
    phone = (_nonempty_str(result.get("formatted_phone_number"))
             or _nonempty_str(result.get("international_phone_number")))
    website = _nonempty_str(result.get("website"))
    return phone, website


def row_needs_contact(row):
    """True when a Details call could still fill phone or website."""
    if not isinstance(row, dict):
        return False
    has_phone = (
        _nonempty_str(row.get("phone")) is not None
        or contact_from_details(row)[0] is not None
    )
    has_website = _nonempty_str(row.get("website")) is not None
    return not (has_phone and has_website)


def apply_contact(row, phone, website):
    """Write listing contact onto a row; do not overwrite a value already there."""
    if phone and _nonempty_str(row.get("phone")) is None:
        row["phone"] = phone
    if website and _nonempty_str(row.get("website")) is None:
        row["website"] = website
    return row


def fetch_place_contact(place_id, api_key, counter, fetch_json=_http_get_json):
    """One Place Details call for listing phone and website.

    NOT_FOUND / ZERO_RESULTS mean Google has no listing contact; that is a
    missing channel, not a failed run. Any other status stops the batch.
    """
    counter.tick("details")
    page = fetch_json(PLACES_DETAILS_URL, {
        "place_id": place_id,
        "fields": DETAILS_FIELDS,
        "key": api_key,
    })
    status = page.get("status")
    if status == "OK":
        return contact_from_details(page.get("result"))
    if status in ("NOT_FOUND", "ZERO_RESULTS"):
        return None, None
    raise PrecatalogueError(
        f"Place Details failed for {place_id!r}: status {status!r}"
    )


def _criterion_confidence(assessments, key, verdict):
    """Mean model confidence among the views that voted for the majority
    verdict; None when no view produced a usable number."""
    values = []
    for assessment in assessments:
        if assessment.criteria is None:
            continue
        entry = assessment.criteria[key]
        confidence = entry.get("confidence")
        if entry["verdict"] == verdict and isinstance(confidence, (int, float)):
            values.append(confidence)
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _row_base(place, phone=None, website=None):
    row = {
        "place_id": place["place_id"],
        "name": place["name"],
        "location": place["location"],
        "source": "streetview",
        "status": "ai_estimated",
    }
    return apply_contact(row, phone, website)


def _uncovered_row(place, coverage_status, phone=None, website=None):
    row = _row_base(place, phone, website)
    row.update({
        "covered": False,
        "coverage_status": coverage_status,
        "imagery_date": None,
        "headings": [],
        "criteria": None,
    })
    return row


def _screened_row(place, metadata, headings, assessments,
                  phone=None, website=None):
    summary = aggregate_assessments(assessments)
    criteria = {}
    for key in CRITERIA_KEYS:
        criterion = summary[key]
        criteria[key] = {
            "verdict": criterion.verdict,
            "confidence": _criterion_confidence(
                assessments, key, criterion.verdict),
            "flip_rate": criterion.flip_rate,
        }
    row = _row_base(place, phone, website)
    row.update({
        "covered": True,
        "coverage_status": "OK",
        "imagery_date": metadata.get("date"),
        "headings": headings,
        "criteria": criteria,
        "assessment_errors": [a.error for a in assessments if a.error],
    })
    return row


def _write_json(path, payload):
    """Write via a temporary file in the same directory, then rename.

    The dataset is rewritten after every completed row, so a plain write_text
    gives one truncate-then-write window per business. An interrupt inside any
    of them would leave invalid JSON, and the next run reads this file to know
    what it already has -- losing it discards every row already paid for.
    os.replace is atomic on the same filesystem.
    """
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def _truncated_types_by_block(truncated_types):
    """Summary shape for per-sweep truncation: {block name: [types]}."""
    by_block = {}
    for block_name, sweep_type in truncated_types:
        by_block.setdefault(block_name, []).append(sweep_type)
    return by_block


def _merged_census(existing, places):
    """Add the places this sweep found to a census already on disk (#346).

    One catalogue, swept in more than one pass: a second area's sweep extends
    the list rather than replacing it. Rows already present are left exactly as
    they are -- a later sweep re-finding a place is not new information about
    it, and rewriting rows would put this pass's fingerprints on the earlier
    pass's evidence.

    Added rows carry the place_id and which sweeps returned it, and nothing
    else. #242's acceptance criterion is that nothing from Places is persisted
    except the place_id; the existing rows' `name` and `location` are the
    violation that ticket is open on, and this pass deliberately does not add
    to their number. Display fields resolve at render time from the identifier.
    """
    known = {row["place_id"] for row in existing.get("places", [])}
    added = [{"place_id": p["place_id"], "sweeps": list(p["sweeps"])}
             for p in places if p["place_id"] not in known]
    previous = list(existing.get("previous_summaries", []))
    if existing.get("summary") is not None:
        previous.append(existing["summary"])
    return {
        "places": list(existing.get("places", [])) + added,
        "previous_summaries": previous,
        "added": added,
        "already_listed": len(places) - len(added),
    }


def run_census(area=None, out_dir="data", *, env=None, merge=False,
               fetch_json=_http_get_json, sleep=time.sleep):
    """Enumerate only: list the area's places and stop before any imagery.

    The cheap first half of the batch, for answering "what would a full run
    screen, and where does the API still cut us short?" before spending on
    Street View images or the model. No metadata, image, or engine call is
    made and the dataset file is never written. The existing dataset (if any)
    is read to report how many of the enumerated places are new -- the same
    place_id keying the resumable run uses.

    Writes the census (summary plus the full place list) next to where the
    dataset would go, and returns the summary.

    With merge=True the census on disk is extended instead of replaced: this
    area's places are added to it, identifier-only, and the census it replaced
    keeps its summary under `previous_summaries`. See _merged_census.
    """
    t0 = time.perf_counter()
    if area is None:
        area = load_demo_area()
    api_key = load_api_key(env)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = out_dir / DATASET_FILENAME
    existing_ids = set()
    if dataset_path.exists():
        existing_ids = set(
            json.loads(dataset_path.read_text(encoding="utf-8")))

    counter = MapsCallCounter(area.max_maps_calls)
    stopped = None
    stopped_is_error = False
    places = ()
    truncated_blocks = ()
    truncated_types = ()
    try:
        enumeration = enumerate_places(
            area, api_key, counter, fetch_json, sleep)
        places = enumeration.places
        truncated_blocks = enumeration.truncated_blocks
        truncated_types = enumeration.truncated_types
    except MapsCallCapError as exc:
        stopped = f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001 - report what the calls cost
        stopped = f"{type(exc).__name__}: {exc}"
        stopped_is_error = True

    census_path = out_dir / CENSUS_FILENAME
    merged = None
    if merge and census_path.exists():
        merged = _merged_census(
            json.loads(census_path.read_text(encoding="utf-8")), places)

    already = sum(1 for p in places if p["place_id"] in existing_ids)
    summary = {
        "area": area.name,
        "census": True,
        "sweep_types": list(area.sweep_types),
        "businesses_enumerated": len(places),
        "already_catalogued": already,
        "new_businesses": len(places) - already,
        "maps_api_calls": {**counter.counts, "total": counter.total},
        "maps_call_cap": area.max_maps_calls,
        "truncated_blocks": list(truncated_blocks),
        "truncated_types": _truncated_types_by_block(truncated_types),
        "wall_clock_s": round(time.perf_counter() - t0, 3),
        "stopped": stopped,
        "stopped_is_error": stopped_is_error,
    }
    if merged is None:
        payload = {"summary": summary, "places": list(places)}
    else:
        summary["merged_into_existing"] = {
            "places_added": len(merged["added"]),
            "places_already_listed": merged["already_listed"],
            "places_total": len(merged["places"]),
        }
        payload = {"summary": summary,
                   "previous_summaries": merged["previous_summaries"],
                   "places": merged["places"]}
    _write_json(census_path, payload)
    return summary


def run_precatalogue(area=None, out_dir="data", *, engine=None, env=None,
                     fetch_json=_http_get_json, fetch_bytes=_http_get_bytes,
                     sleep=time.sleep):
    """Run the batch: enumerate, coverage-check, retrieve, screen, write.

    Idempotent and resumable: the dataset is keyed by place_id, existing rows
    are skipped, and the dataset file is rewritten after every completed row —
    a run stopped by either cap (maps calls or model spend) resumes on re-run.
    Returns the run summary, also written next to the dataset.
    """
    t0 = time.perf_counter()
    if area is None:
        area = load_demo_area()
    api_key = load_api_key(env)
    if engine is None:
        engine = ScreeningEngine()

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = out_dir / DATASET_FILENAME
    dataset = {}
    if dataset_path.exists():
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))

    counter = MapsCallCounter(area.max_maps_calls)
    stopped = None
    stopped_is_error = False
    skipped_existing = 0
    enumerated = []
    truncated_blocks = ()
    truncated_types = ()
    try:
        enumeration = enumerate_places(
            area, api_key, counter, fetch_json, sleep)
        enumerated = list(enumeration.places)
        truncated_blocks = enumeration.truncated_blocks
        truncated_types = enumeration.truncated_types
        for place in enumerated:
            place_id = place["place_id"]
            if place_id in dataset:
                skipped_existing += 1
                continue
            phone, website = fetch_place_contact(
                place_id, api_key, counter, fetch_json)
            metadata = streetview_metadata(
                place["location"], api_key, counter, fetch_json)
            if metadata.get("status") != "OK":
                row = _uncovered_row(
                    place, metadata.get("status", "UNKNOWN"),
                    phone, website)
            elif not metadata.get("pano_id"):
                # Status said OK but there is no panorama to request. Sending
                # an empty pano is a 400 that would end the whole batch; the
                # honest reading is that this business has nothing to look at.
                row = _uncovered_row(place, "NO_PANO_ID", phone, website)
            else:
                pano_location = metadata.get("location", place["location"])
                headings = storefront_headings(
                    pano_location, place["location"],
                    area.headings_per_business)
                assessments = []
                for heading in headings:
                    image = fetch_streetview_image(
                        metadata["pano_id"], heading, api_key,
                        counter, fetch_bytes)
                    assessments.append(engine.assess_image(image))
                row = _screened_row(
                    place, metadata, headings, assessments, phone, website)
            dataset[place_id] = row
            _write_json(dataset_path, dataset)
    except (MapsCallCapError, SpendCapError) as exc:
        # Expected, and the point of the caps. Resumable.
        stopped = f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001 - the summary is the whole point
        # A timeout, a 500, OVER_QUERY_LIMIT. The rows already written survive
        # because the dataset is flushed per row, but the accounting for what
        # they cost only exists here -- letting this propagate would throw away
        # the call counts and spend for work already paid for.
        stopped = f"{type(exc).__name__}: {exc}"
        stopped_is_error = True

    enumerated_ids = {place["place_id"] for place in enumerated}
    rows = [dataset[pid] for pid in enumerated_ids if pid in dataset]
    covered = sum(1 for row in rows if row["covered"])
    summary = {
        "area": area.name,
        "businesses_enumerated": len(enumerated),
        "covered": covered,
        "screened": sum(
            1 for row in rows if row["covered"] and row["criteria"]),
        "uncovered": len(rows) - covered,
        "skipped_existing": skipped_existing,
        "maps_api_calls": {**counter.counts, "total": counter.total},
        "maps_call_cap": area.max_maps_calls,
        # Named, not inferred: a block that returned the API's maximum was cut
        # off there, and a count that looks complete cannot show it. With
        # per-type sweeps the useful grain is which sweep hit the cap: a block
        # truncated only in its establishment sweep lost office suites, one
        # truncated in "restaurant" is still missing storefronts.
        "truncated_blocks": list(truncated_blocks),
        "truncated_types": _truncated_types_by_block(truncated_types),
        "model_spend_usd_estimate": round(engine.spent_usd, 4),
        "wall_clock_s": round(time.perf_counter() - t0, 3),
        "stopped": stopped,
        "stopped_is_error": stopped_is_error,
    }
    _write_json(out_dir / SUMMARY_FILENAME, summary)
    return summary


def enrich_contacts(out_dir="data", *, area=None, env=None,
                    fetch_json=_http_get_json):
    """Fill phone/website on existing rows from Place Details.

    Does not re-screen. Rows that already have both fields are skipped, so a
    cap stop resumes. Google having no listing contact is recorded as a skip
    after the call, not as an error.
    """
    t0 = time.perf_counter()
    if area is None:
        area = load_demo_area()
    api_key = load_api_key(env)
    out_dir = Path(out_dir)
    dataset_path = out_dir / DATASET_FILENAME
    try:
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PrecatalogueError(f"dataset not found: {dataset_path}") from None
    except (OSError, json.JSONDecodeError) as exc:
        raise PrecatalogueError(f"dataset unreadable: {exc}") from exc
    if not isinstance(dataset, dict):
        raise PrecatalogueError(
            f"dataset is not a place_id map: {dataset_path}")

    counter = MapsCallCounter(area.max_maps_calls)
    stopped = None
    stopped_is_error = False
    skipped_complete = 0
    updated = 0
    unchanged = 0
    try:
        for place_id, row in list(dataset.items()):
            if not isinstance(place_id, str) or not isinstance(row, dict):
                continue
            if not row_needs_contact(row):
                skipped_complete += 1
                continue
            phone, website = fetch_place_contact(
                place_id, api_key, counter, fetch_json)
            before = (row.get("phone"), row.get("website"))
            apply_contact(row, phone, website)
            if (row.get("phone"), row.get("website")) != before:
                updated += 1
            else:
                unchanged += 1
            dataset[place_id] = row
            _write_json(dataset_path, dataset)
    except MapsCallCapError as exc:
        stopped = f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001 - same as run: keep the summary
        stopped = f"{type(exc).__name__}: {exc}"
        stopped_is_error = True

    summary = {
        "area": area.name,
        "enrich": True,
        "rows": sum(1 for row in dataset.values() if isinstance(row, dict)),
        "skipped_complete": skipped_complete,
        "updated": updated,
        "unchanged_after_details": unchanged,
        "maps_api_calls": {**counter.counts, "total": counter.total},
        "maps_call_cap": area.max_maps_calls,
        "wall_clock_s": round(time.perf_counter() - t0, 3),
        "stopped": stopped,
        "stopped_is_error": stopped_is_error,
    }
    return summary


def main(argv=None):
    from frontdoor.storage import _load_dotenv_once
    _load_dotenv_once()
    args = sys.argv[1:] if argv is None else argv
    census = "--census" in args
    merge = "--merge" in args
    config = None
    for arg in args:
        if arg.startswith("--config="):
            config = arg.split("=", 1)[1]
    args = [a for a in args
            if a not in ("--census", "--merge") and not a.startswith("--config=")]
    if (not args or args[0] not in ("run", "enrich") or len(args) > 2
            or (args[0] == "enrich" and (census or merge or config))
            or (merge and not census)):
        print("usage: python -m frontdoor.precatalogue run [--census] "
              "[--config=PATH] [--merge] [out_dir]\n"
              "       python -m frontdoor.precatalogue enrich [out_dir]\n"
              "  --merge extends the census on disk instead of replacing it, "
              "and needs --census",
              file=sys.stderr)
        return 2
    out_dir = args[1] if len(args) == 2 else "data"
    try:
        area = load_demo_area(config) if config else None
        if args[0] == "enrich":
            summary = enrich_contacts(out_dir=out_dir)
        elif census:
            # Enumeration only: no Street View, no model, no dataset writes.
            summary = run_census(area=area, out_dir=out_dir, merge=merge)
        else:
            summary = run_precatalogue(out_dir=out_dir)
    except PrecatalogueError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    # A cap stop is a clean, resumable finish. A crash is not, and a run that
    # died partway through must not report success to whatever called it.
    return 1 if summary["stopped_is_error"] else 0


if __name__ == "__main__":
    sys.exit(main())
