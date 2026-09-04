"""External accessibility data, round zero: the OSM seed (TICK-258, #242).

Round zero of the pre-catalogue seeds the map with license-clean external
accessibility data before any vision spend. This module ships the
OpenStreetMap slice of that: an Overpass ingest for the demo area's
wheelchair/entrance tags, a provenance-line model that renders matching
external records on pins, and the internal disagreement queue skeleton.

License and segregation (load-bearing):
- OSM data is ODbL. It is stored ONLY in a segregated side file
  (``data/external/osm_accessibility.json``) with the attribution embedded
  in the file header and ``source="openstreetmap"`` on every record. Per the
  ODbL Collective Database Guideline it never merges into our own dataset;
  our records stay ours, the OSM file stays OSM's.

Architecture rule (from #242, do not relax):
- External data NEVER feeds the vision model's input — the blind pass stays
  blind. External sources join AFTER assessment, as provenance lines.
- Never-negative: an external ``wheelchair=no`` or ``wheelchair=limited``
  tag never changes a public pin state and never renders publicly. It may
  only appear in the internal disagreement queue
  (``data/external/disagreements.json``), which is scan-priority data for
  the team, never rendered on the map.

Network calls happen ONLY in the CLI path (``python -m
frontdoor.external_data --refresh``); importing this module performs no
I/O, and tests use fixture payloads.

Round one adds open-licensed Wikimedia Commons imagery as a second
segregated source — see ``frontdoor.commons_imagery`` (refreshed via
``--refresh-commons`` on this module's CLI).

TABS (Texas Architectural Barriers System) is round-one scope: the public
TDLR registry search, its detail-page fields, and the PIA bulk-request path
are documented in docs/external-data.md (with a drafted PIA request
template); no TABS code ships in round zero. Google Places / Yelp
accessibility attributes are display-time-only under their ToS and are
never ingested here — see the same doc.
"""

from __future__ import annotations

import difflib
import json
import math
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

DEFAULT_CONFIG_PATH = Path(__file__).with_name("demo_area.json")
DEFAULT_OUT_DIR = Path("data/external")
OSM_FILENAME = "osm_accessibility.json"
DISAGREEMENTS_FILENAME = "disagreements.json"
DEFAULT_PRECATALOGUE_PATH = Path("data/precatalogue.json")

OSM_SOURCE = "openstreetmap"
ODBL_ATTRIBUTION = (
    "Contains data from OpenStreetMap (© OpenStreetMap contributors), "
    "licensed under the Open Database License (ODbL) 1.0. "
    "https://www.openstreetmap.org/copyright"
)
SEGREGATION_NOTE = (
    "ODbL-licensed data stored as a segregated side table per the ODbL "
    "Collective Database Guideline. Do not merge these records into any "
    "proprietary dataset."
)
DISAGREEMENTS_NOTE = (
    "INTERNAL scan-priority data (TICK-258). External-vs-AI conflicts are "
    "logged here so a real scan can settle them. Never rendered publicly, "
    "never a negative claim against a business."
)

# Public provenance only ever cites AGREEABLE external reports. Anything
# else — no, limited, unknown, junk — is internal-only (disagreement queue).
POSITIVE_WHEELCHAIR_VALUES = frozenset({"yes", "designated"})
NEGATIVE_WHEELCHAIR_VALUES = frozenset({"no", "limited"})

# Matching a place to an external record: close enough, and — when both
# sides have a name — the names must actually resemble each other.
DEFAULT_MATCH_DISTANCE_M = 40.0
NAME_MATCH_RATIO = 0.6


class ExternalDataError(Exception):
    """Missing config or a failed Overpass call (CLI path only)."""


# --- Overpass ingest --------------------------------------------------------


def load_demo_bbox(config_path=DEFAULT_CONFIG_PATH):
    """The demo area's bounding box {south, west, north, east}."""
    try:
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExternalDataError(f"demo-area config unreadable: {exc}") from exc
    bbox = config.get("bounding_box")
    if not isinstance(bbox, dict) or not all(
        isinstance(bbox.get(k), (int, float)) and not isinstance(bbox.get(k), bool)
        for k in ("south", "west", "north", "east")
    ):
        raise ExternalDataError(f"no usable bounding_box in {config_path}")
    return bbox


def build_overpass_query(bbox):
    """Overpass QL for wheelchair / entrance-accessibility tags in a bbox.

    Pulls nodes and ways carrying ``wheelchair=*``,
    ``wheelchair:description=*``, or ``entrance=wheelchair``. ``out center``
    prints full elements (tags included) plus a representative coordinate
    for ways; a tags-only print mode would drop node coordinates.
    """
    coords = "{south},{west},{north},{east}".format(**bbox)
    return (
        "[out:json][timeout:60];\n"
        "(\n"
        f'  node["wheelchair"]({coords});\n'
        f'  way["wheelchair"]({coords});\n'
        f'  node["wheelchair:description"]({coords});\n'
        f'  way["wheelchair:description"]({coords});\n'
        f'  node["entrance"="wheelchair"]({coords});\n'
        ");\n"
        "out center;\n"
    )


def fetch_overpass(query, url=OVERPASS_URL, urlopen=urllib.request.urlopen):
    """POST a query to the Overpass API. CLI path only — never at import,
    never from tests (tests parse fixture payloads instead)."""
    data = ("data=" + urllib.parse.quote(query)).encode("ascii")
    request = urllib.request.Request(
        url, data=data, headers={"User-Agent": "frontdoor-external-data/0.1"}
    )
    try:
        with urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise ExternalDataError(f"Overpass request failed: {exc}") from exc


def parse_overpass_payload(payload, fetched_at):
    """Overpass JSON -> segregated OSM records.

    Each record carries source="openstreetmap", fetched_at, osm_type,
    osm_id, name (may be None), lat/lon, and the raw OSM tags. Elements
    without coordinates (or without tags) are skipped — a record that
    cannot be placed cannot match a pin.
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
        lat, lon = element.get("lat"), element.get("lon")
        if lat is None or lon is None:
            center = element.get("center")
            if isinstance(center, dict):
                lat, lon = center.get("lat"), center.get("lon")
        if not _is_number(lat) or not _is_number(lon):
            continue
        name = tags.get("name")
        records.append({
            "source": OSM_SOURCE,
            "fetched_at": fetched_at,
            "osm_type": element.get("type"),
            "osm_id": element.get("id"),
            "name": name if isinstance(name, str) else None,
            "lat": float(lat),
            "lon": float(lon),
            "tags": tags,
        })
    return records


def write_osm_dataset(records, path, fetched_at):
    """Write the segregated OSM side file, attribution in the header."""
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


def load_osm_records(path):
    """Records from a segregated OSM side file; [] when missing/unreadable.

    Total on purpose: the map must render with or without external data.
    """
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    records = document.get("records") if isinstance(document, dict) else None
    return [r for r in records or [] if isinstance(r, dict)]


# --- provenance lines -------------------------------------------------------


@dataclass(frozen=True)
class ProvenanceLine:
    """One public provenance line on a pin: source + label + date, always."""

    source: str
    label: str
    date: str
    url: str | None = None
    detail: str | None = None

    def as_dict(self):
        line = {"source": self.source, "label": self.label, "date": self.date}
        if self.url is not None:
            line["url"] = self.url
        if self.detail is not None:
            line["detail"] = self.detail
        return line


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _haversine_m(lat1, lon1, lat2, lon2):
    radius_m = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
    return 2 * radius_m * math.asin(math.sqrt(a))


def _normalize_name(name):
    return re.sub(r"[^a-z0-9 ]+", " ", name.casefold()).split()


def _names_match(a, b):
    """Fuzzy name comparison; permissive on containment, ratio otherwise."""
    words_a, words_b = _normalize_name(a), _normalize_name(b)
    if not words_a or not words_b:
        return True  # nothing to compare — fall back to distance alone
    norm_a, norm_b = " ".join(words_a), " ".join(words_b)
    if norm_a in norm_b or norm_b in norm_a:
        return True
    return difflib.SequenceMatcher(None, norm_a, norm_b).ratio() >= NAME_MATCH_RATIO


def match_records(name, lat, lon, records, max_distance_m=DEFAULT_MATCH_DISTANCE_M):
    """External records matching a place, by distance + fuzzy name.

    A record within ``max_distance_m`` matches unless both sides carry a
    name and the names disagree.
    """
    matches = []
    if not _is_number(lat) or not _is_number(lon):
        return matches
    for record in records:
        if not _is_number(record.get("lat")) or not _is_number(record.get("lon")):
            continue
        if _haversine_m(lat, lon, record["lat"], record["lon"]) > max_distance_m:
            continue
        record_name = record.get("name")
        if (isinstance(name, str) and name and isinstance(record_name, str)
                and record_name and not _names_match(name, record_name)):
            continue
        matches.append(record)
    return matches


def _record_year(record):
    """Best public year for a record: an OSM check/survey date, else fetch."""
    tags = record.get("tags") or {}
    for key in ("check_date", "check_date:wheelchair", "survey:date"):
        value = tags.get(key)
        if isinstance(value, str):
            match = re.match(r"(\d{4})", value)
            if match:
                return match.group(1)
    fetched = record.get("fetched_at")
    if isinstance(fetched, str) and re.match(r"\d{4}", fetched):
        return fetched[:4]
    return "date unknown"


def _is_publicly_positive(record):
    """Only agreeable external reports ever render publicly (never-negative)."""
    tags = record.get("tags") or {}
    wheelchair = tags.get("wheelchair")
    if wheelchair in POSITIVE_WHEELCHAIR_VALUES:
        return True
    return wheelchair is None and tags.get("entrance") == "wheelchair"


def provenance_for_place(name, lat, lon, records,
                         max_distance_m=DEFAULT_MATCH_DISTANCE_M):
    """Public provenance lines for a place, as JSON-ready dicts.

    Only positive external reports produce lines; a matching wheelchair=no
    or =limited record produces NOTHING here (it belongs to the
    disagreement queue). Every line names its source and date and carries
    the ODbL attribution.
    """
    lines = []
    for record in match_records(name, lat, lon, records, max_distance_m):
        if record.get("source") != OSM_SOURCE or not _is_publicly_positive(record):
            continue
        year = _record_year(record)
        osm_type, osm_id = record.get("osm_type"), record.get("osm_id")
        url = None
        if osm_type in ("node", "way", "relation") and isinstance(osm_id, int):
            url = f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
        lines.append(ProvenanceLine(
            source=OSM_SOURCE,
            label=f"Reported on OpenStreetMap - {year}",
            date=year,
            url=url,
            detail="© OpenStreetMap contributors (ODbL)",
        ).as_dict())
    return lines


# --- disagreement queue (internal only) -------------------------------------


def find_disagreements(ai_estimates, external_records,
                       max_distance_m=DEFAULT_MATCH_DISTANCE_M):
    """External-vs-AI conflicts, as INTERNAL scan-priority records.

    Compares each AI-estimated row's ramp_or_bevel verdict (the closest
    criterion to entrance wheelchair access) with matched external
    wheelchair tags. Output shape per conflict:
    {place, field, ai_says, external_says, external, reason}.

    These records are written to data/external/disagreements.json by the
    CLI and are never rendered — a conflict is a reason to scan, not a
    public verdict. This function only reads; it can never change a pin.
    """
    disagreements = []
    if not isinstance(ai_estimates, dict):
        return disagreements
    for place_id in sorted(ai_estimates):
        row = ai_estimates[place_id]
        if not isinstance(row, dict):
            continue
        location = row.get("location")
        if not isinstance(location, dict):
            continue
        lat, lon = location.get("lat"), location.get("lng")
        criteria = row.get("criteria")
        entry = criteria.get("ramp_or_bevel") if isinstance(criteria, dict) else None
        verdict = entry.get("verdict") if isinstance(entry, dict) else None
        if verdict not in ("present", "absent"):
            continue
        name = row.get("name")
        for record in match_records(name, lat, lon, external_records,
                                    max_distance_m):
            wheelchair = (record.get("tags") or {}).get("wheelchair")
            if wheelchair in NEGATIVE_WHEELCHAIR_VALUES and verdict == "present":
                reason = (
                    "AI estimate found a ramp or beveled threshold, but "
                    f"OpenStreetMap reports wheelchair={wheelchair}"
                )
            elif wheelchair in POSITIVE_WHEELCHAIR_VALUES and verdict == "absent":
                reason = (
                    "AI estimate found no ramp or beveled threshold, but "
                    f"OpenStreetMap reports wheelchair={wheelchair}"
                )
            else:
                continue
            disagreements.append({
                "place": {
                    "place_id": str(place_id),
                    "name": name if isinstance(name, str) else None,
                    "lat": lat,
                    "lng": lon,
                },
                "field": "ramp_or_bevel",
                "ai_says": verdict,
                "external_says": f"wheelchair={wheelchair}",
                "external": {
                    "source": record.get("source"),
                    "osm_type": record.get("osm_type"),
                    "osm_id": record.get("osm_id"),
                },
                "reason": reason,
            })
    return disagreements


def write_disagreements(disagreements, path):
    """Write the internal disagreement queue file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "note": DISAGREEMENTS_NOTE,
        "count": len(disagreements),
        "disagreements": disagreements,
    }
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return document


# --- CLI (the only network path) --------------------------------------------


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m frontdoor.external_data",
        description="Refresh the segregated external accessibility data "
                    "(OSM via Overpass) and the internal disagreement queue.",
    )
    parser.add_argument("--refresh", action="store_true",
                        help="fetch OSM data from Overpass for the demo bbox")
    parser.add_argument("--refresh-commons", action="store_true",
                        help="fetch open-licensed Wikimedia Commons imagery "
                             "records for the demo bbox (round one)")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH),
                        help="demo-area config with the bounding_box")
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR),
                        help="output directory for the segregated files")
    parser.add_argument("--dataset", default=str(DEFAULT_PRECATALOGUE_PATH),
                        help="pre-catalogue dataset for the disagreement scan")
    parser.add_argument("--overpass-url", default=OVERPASS_URL)
    parser.add_argument("--commons-url", default=None,
                        help="override the Commons API endpoint")
    args = parser.parse_args(argv)

    if not args.refresh and not args.refresh_commons:
        parser.print_help()
        return 2

    bbox = load_demo_bbox(args.config)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out_dir = Path(args.out)

    if args.refresh_commons:
        from frontdoor import commons_imagery

        commons_url = args.commons_url or commons_imagery.COMMONS_API_URL
        geosearch, imageinfo = commons_imagery.fetch_commons_imagery(
            bbox, url=commons_url)
        commons_records, dropped = commons_imagery.parse_commons_payloads(
            geosearch, imageinfo, fetched_at)
        commons_path = out_dir / commons_imagery.COMMONS_FILENAME
        commons_imagery.write_commons_dataset(
            commons_records, commons_path, fetched_at, dropped)
        print(f"wrote {len(commons_records)} Commons imagery records to "
              f"{commons_path} (dropped at ingest: "
              f"{dropped if dropped else 'none'})")

    if not args.refresh:
        return 0

    payload = fetch_overpass(build_overpass_query(bbox), url=args.overpass_url)
    records = parse_overpass_payload(payload, fetched_at)
    osm_path = out_dir / OSM_FILENAME
    write_osm_dataset(records, osm_path, fetched_at)
    print(f"wrote {len(records)} OSM records to {osm_path}")

    try:
        ai_estimates = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(f"no pre-catalogue dataset at {args.dataset}; "
              "skipping disagreement scan")
        return 0
    disagreements = find_disagreements(ai_estimates, records)
    disagreements_path = out_dir / DISAGREEMENTS_FILENAME
    write_disagreements(disagreements, disagreements_path)
    print(f"wrote {len(disagreements)} disagreements to {disagreements_path} "
          "(internal scan priorities, never rendered)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
