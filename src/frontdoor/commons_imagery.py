"""Wikimedia Commons imagery, external-data round one (TICK-258, #242).

Round one adds an open-licensed imagery source to the pre-catalogue's
external-data layer: geotagged Wikimedia Commons photos near a place become
provenance lines ("a photo of this block exists, here is who took it and
under what license"). This module ships the ingest and the provenance
matching ONLY — no Commons image is assessed by the screening engine in
this round; third-party imagery assessment is a follow-up with its own
matching QA.

License gate (load-bearing):
- Only records whose extmetadata license is CC0, CC BY, or CC BY-SA (any
  version) are kept. NC, ND, unknown, and fair-use records are dropped at
  ingest with a counted reason — they never touch disk.
- CC BY / CC BY-SA require attribution, so a record under those licenses
  with no artist is undisplayable and is dropped too.
- Kept data lives ONLY in the segregated side file
  (``data/external/commons_imagery.json``) whose header carries the
  required-attribution statement and the CC BY-SA share-alike note, with
  ``source="wikimedia_commons"`` on every record.

Matching note: Commons coordinates are PHOTO positions (where the camera
stood), not business positions, so the match radius here is tighter than
the OSM default (~35 m) and no name matching applies — file titles are not
business names.

Network calls happen ONLY in the CLI path (``python -m
frontdoor.external_data --refresh-commons``); importing this module
performs no I/O, and tests use fixture payloads.

API notes pinned by tests: the geosearch call MUST send ``gsnamespace=6``
(the File namespace) — the default namespace returns zero results for
imagery. A second batched call fetches ``imageinfo``/``extmetadata`` per
candidate for license, artist, dates, and URLs.
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from frontdoor.external_data import (
    ExternalDataError,
    ProvenanceLine,
    _haversine_m,
    _is_number,
)

COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
COMMONS_SOURCE = "wikimedia_commons"
COMMONS_FILENAME = "commons_imagery.json"
USER_AGENT = "frontdoor-external-data/0.1"

# imageinfo titles are batched; the API caps titles-per-query at 50.
IMAGEINFO_BATCH_SIZE = 50

COMMONS_ATTRIBUTION = (
    "Contains photo records from Wikimedia Commons. Every record is "
    "individually licensed (CC0, CC BY, or CC BY-SA) by the named artist; "
    "wherever an image or its metadata is displayed, the record's artist "
    "and license MUST be shown and the commons page linked. "
    "https://commons.wikimedia.org/"
)
SHARE_ALIKE_NOTE = (
    "CC BY-SA records are share-alike: any adaptation of those IMAGES must "
    "be distributed under the same license. Metadata-only display (title, "
    "artist, license, link) is attribution, not adaptation."
)
COMMONS_SEGREGATION_NOTE = (
    "Open-licensed third-party records stored as a segregated side table, "
    "mirroring the OSM side file. Do not merge these records into any "
    "proprietary dataset; each record keeps its own license and artist."
)

# Only these license families survive ingest, any version: CC0, CC BY,
# CC BY-SA. NC/ND/unknown/fair-use are dropped (counted, never stored).
_ALLOWED_LICENSE_RE = re.compile(
    r"^cc(?:0|[ -]by(?:[ -]sa)?)(?:[ -]\d[\w.\- ]*)?$", re.IGNORECASE
)

# Photo coordinates are camera positions, not business doors: tighter than
# the OSM place-matching default on purpose.
PHOTO_MATCH_DISTANCE_M = 35.0

_TAG_RE = re.compile(r"<[^>]*>")
_DROP_REASONS = (
    "license_disallowed",
    "license_unknown",
    "missing_artist",
    "no_imageinfo",
    "no_coordinates",
)


# --- Commons API requests (network only via the CLI path) -------------------


def build_geosearch_params(bbox, limit=500):
    """Query params for the Commons geosearch call over the demo bbox.

    ``gsnamespace=6`` is REQUIRED: File-namespace results (the images) are
    only returned when asked for; the default namespace yields zero.
    ``gsbbox`` order is top|left|bottom|right (north|west|south|east).
    """
    return {
        "action": "query",
        "list": "geosearch",
        "gsbbox": "{north}|{west}|{south}|{east}".format(**bbox),
        "gsnamespace": "6",
        "gslimit": str(limit),
        "format": "json",
        "formatversion": "2",
    }


def build_imageinfo_params(titles):
    """Query params for one batched imageinfo/extmetadata call."""
    return {
        "action": "query",
        "prop": "imageinfo",
        "iiprop": "extmetadata|url",
        "iiurlwidth": "640",
        "titles": "|".join(titles),
        "format": "json",
        "formatversion": "2",
    }


def fetch_commons(params, url=COMMONS_API_URL, urlopen=urllib.request.urlopen):
    """GET one Commons API call. CLI path only — never at import, never
    from tests (tests parse fixture payloads instead)."""
    request = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise ExternalDataError(f"Commons request failed: {exc}") from exc


def fetch_commons_imagery(bbox, url=COMMONS_API_URL,
                          urlopen=urllib.request.urlopen):
    """The full two-step fetch: geosearch, then batched imageinfo.

    Returns (geosearch_payload, [imageinfo_payload, ...]) for
    parse_commons_payloads. CLI path only.
    """
    geosearch_payload = fetch_commons(
        build_geosearch_params(bbox), url=url, urlopen=urlopen)
    titles = [
        hit["title"]
        for hit in _geosearch_hits(geosearch_payload)
        if isinstance(hit.get("title"), str)
    ]
    imageinfo_payloads = []
    for start in range(0, len(titles), IMAGEINFO_BATCH_SIZE):
        batch = titles[start:start + IMAGEINFO_BATCH_SIZE]
        imageinfo_payloads.append(fetch_commons(
            build_imageinfo_params(batch), url=url, urlopen=urlopen))
    return geosearch_payload, imageinfo_payloads


# --- parsing and the license gate -------------------------------------------


def _geosearch_hits(payload):
    query = payload.get("query") if isinstance(payload, dict) else None
    hits = query.get("geosearch") if isinstance(query, dict) else None
    if not isinstance(hits, list):
        return []
    return [h for h in hits if isinstance(h, dict)]


def _imageinfo_by_title(payloads):
    """Map File title -> its first imageinfo dict, across batched payloads."""
    by_title = {}
    for payload in payloads or []:
        query = payload.get("query") if isinstance(payload, dict) else None
        pages = query.get("pages") if isinstance(query, dict) else None
        if not isinstance(pages, list):
            continue
        for page in pages:
            if not isinstance(page, dict):
                continue
            title = page.get("title")
            infos = page.get("imageinfo")
            if not isinstance(title, str) or not isinstance(infos, list):
                continue
            info = next((i for i in infos if isinstance(i, dict)), None)
            if info is not None:
                by_title[title] = info
    return by_title


def _metadata_value(extmetadata, key):
    entry = extmetadata.get(key) if isinstance(extmetadata, dict) else None
    value = entry.get("value") if isinstance(entry, dict) else None
    return value if isinstance(value, str) and value.strip() else None


def strip_html(markup):
    """Visible text of an HTML fragment (Commons Artist values are HTML)."""
    text = html.unescape(_TAG_RE.sub(" ", markup))
    return " ".join(text.split())


def license_allowed(short_name):
    """The license gate: CC0 / CC BY / CC BY-SA, any version, nothing else."""
    if not isinstance(short_name, str):
        return False
    return bool(_ALLOWED_LICENSE_RE.match(short_name.strip()))


def _license_requires_attribution(short_name):
    return not short_name.strip().casefold().startswith("cc0")


def parse_commons_payloads(geosearch_payload, imageinfo_payloads, fetched_at):
    """(geosearch, imageinfo batches) -> (kept records, dropped counts).

    A record survives only with coordinates, an imageinfo entry, an allowed
    license, and — under attribution licenses — a named artist. Everything
    else increments a reason in ``dropped`` and is never stored.
    """
    records = []
    dropped = {reason: 0 for reason in _DROP_REASONS}
    info_by_title = _imageinfo_by_title(imageinfo_payloads)
    seen_titles = set()
    for hit in _geosearch_hits(geosearch_payload):
        title = hit.get("title")
        if not isinstance(title, str) or title in seen_titles:
            continue
        seen_titles.add(title)
        lat, lon = hit.get("lat"), hit.get("lon")
        if not _is_number(lat) or not _is_number(lon):
            dropped["no_coordinates"] += 1
            continue
        info = info_by_title.get(title)
        if info is None:
            dropped["no_imageinfo"] += 1
            continue
        extmetadata = info.get("extmetadata")
        license_name = _metadata_value(extmetadata, "LicenseShortName")
        if license_name is None:
            dropped["license_unknown"] += 1
            continue
        if not license_allowed(license_name):
            dropped["license_disallowed"] += 1
            continue
        artist_html = _metadata_value(extmetadata, "Artist")
        artist = strip_html(artist_html) if artist_html else None
        if not artist and _license_requires_attribution(license_name):
            dropped["missing_artist"] += 1
            continue
        page_url = info.get("descriptionurl")
        if not isinstance(page_url, str) or not page_url:
            page_url = ("https://commons.wikimedia.org/wiki/"
                        + urllib.parse.quote(title.replace(" ", "_")))
        image_url = info.get("url") if isinstance(info.get("url"), str) else None
        thumb_url = (info.get("thumburl")
                     if isinstance(info.get("thumburl"), str) else None)
        capture_date = _metadata_value(extmetadata, "DateTimeOriginal")
        upload_date = _metadata_value(extmetadata, "DateTime")
        records.append({
            "source": COMMONS_SOURCE,
            "fetched_at": fetched_at,
            "title": title,
            "page_url": page_url,
            "image_url": image_url,
            "thumb_url": thumb_url,
            "license": license_name.strip(),
            "artist": artist,
            "capture_date": capture_date,
            "upload_date": upload_date,
            "lat": float(lat),
            "lon": float(lon),
        })
    return records, {k: v for k, v in dropped.items() if v}


# --- the segregated side file -----------------------------------------------


def write_commons_dataset(records, path, fetched_at, dropped=None):
    """Write the segregated Commons side file, attribution in the header."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "source": COMMONS_SOURCE,
        "license_policy": ("CC0, CC BY, or CC BY-SA (any version) only; "
                           "NC/ND/unknown/fair-use dropped at ingest"),
        "attribution": COMMONS_ATTRIBUTION,
        "share_alike": SHARE_ALIKE_NOTE,
        "segregation": COMMONS_SEGREGATION_NOTE,
        "fetched_at": fetched_at,
        "record_count": len(records),
        "dropped_at_ingest": dropped or {},
        "records": records,
    }
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return document


def load_commons_records(path):
    """Records from the segregated Commons side file; [] when missing or
    unreadable. Total on purpose: the map renders with or without it."""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    records = document.get("records") if isinstance(document, dict) else None
    return [r for r in records or [] if isinstance(r, dict)]


# --- provenance lines -------------------------------------------------------


def _record_year(record):
    for key in ("capture_date", "upload_date"):
        value = record.get(key)
        if isinstance(value, str):
            match = re.search(r"(\d{4})", value)
            if match:
                return match.group(1)
    fetched = record.get("fetched_at")
    if isinstance(fetched, str) and re.match(r"\d{4}", fetched):
        return fetched[:4]
    return "date unknown"


def commons_provenance_for_place(lat, lon, records,
                                 max_distance_m=PHOTO_MATCH_DISTANCE_M):
    """Public provenance lines for nearby open-licensed Commons photos.

    Distance-only matching (photo coordinates, not business coordinates —
    hence the tighter default radius) and no name matching: a file title is
    not a business name. A photo's existence is a neutral fact, so there is
    no positive/negative split here; the never-negative rule is untouched
    because no line ever carries an accessibility claim.
    """
    lines = []
    if not _is_number(lat) or not _is_number(lon):
        return lines
    for record in records:
        if record.get("source") != COMMONS_SOURCE:
            continue
        if not _is_number(record.get("lat")) or not _is_number(record.get("lon")):
            continue
        if _haversine_m(lat, lon, record["lat"], record["lon"]) > max_distance_m:
            continue
        license_name = record.get("license")
        if not license_allowed(license_name):
            continue  # belt and braces: never render an unvetted license
        year = _record_year(record)
        artist = record.get("artist")
        label = f"Photo on Wikimedia Commons - {year} - {license_name.strip()}"
        if isinstance(artist, str) and artist:
            label += f" - {artist}"
        page_url = record.get("page_url")
        lines.append(ProvenanceLine(
            source=COMMONS_SOURCE,
            label=label,
            date=year,
            url=page_url if isinstance(page_url, str) else None,
        ).as_dict())
    return lines
