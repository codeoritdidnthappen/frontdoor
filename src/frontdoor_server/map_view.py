"""GET /map and GET /map/data: the public stamp map (TICK-247, #169).

/map serves the static map page; /map/data serves the demo-area dataset with
each pin's stamp state pre-computed server-side by frontdoor.map_states, so
the Green-or-Gray rule is enforced (and tested) in Python — the page renders
states, it does not decide them.

The dataset is the TICK-248 pre-catalogue output (data-shape dependency
only). Its path comes from FRONTDOOR_MAP_DATASET, defaulting to
data/precatalogue.json. A missing or unreadable dataset degrades to an empty
pin list with the problem named in the payload, never an error page.

External provenance (TICK-258, #242): when the segregated OSM side file is
present (FRONTDOOR_EXTERNAL_OSM, default data/external/osm_accessibility.json),
pins with a matching positive external record gain an optional "provenance"
array of source+date lines. Round one adds open-licensed Wikimedia Commons
photos the same way (FRONTDOOR_EXTERNAL_COMMONS, default
data/external/commons_imagery.json): a nearby CC0/CC BY/CC BY-SA photo
becomes an attributed line. External data can never change a pin's state —
frontdoor.external_data only ever emits agreeable lines publicly, a Commons
line carries no accessibility claim at all, and the state is computed
before provenance is attached.

Community scans (TICK-262, #270): published scan records from the JSONL store
(FRONTDOOR_SCANS, default data/scans.jsonl) are merged into the dataset before
states are computed. The curated on-site publication (TICK-333,
FRONTDOOR_PUBLISHED_SCANS, default data/published_scans.jsonl) is merged in the
same pass and by the same rules — it is a committed dataset file that ships in
the image, where the community store is runtime state on a mounted volume, and
the map needs both. Records are keyed by place_id, falling back to the same
distance+name matching the external files use. The merge is never-negative by
construction (frontdoor.scan_records): a scan can add a pin, raise one to the verified
state (the page's Scanned tier), raise a criterion observation, or move
freshness forward — nothing else. A scanned pin also carries a
"Scanned on-site — <date>" provenance row.

Community corrections (TICK-387, #387): the correction store
(FRONTDOOR_CORRECTIONS, default data/corrections.jsonl) can mark a place as
needing a re-look, and that is the ONLY thing it can do to a pin. The rows
carry `needs_relook` and `relook_since` and nothing else -- frontdoor.corrections
holds the corroboration rule and the argument -- so a correction is not an
input to any state, label or checklist entry on this payload. It cannot turn a
green stamp neutral, cannot lower an observation, and cannot add a pin. What it
does is ask somebody to take a fresh photograph.

The Google Maps API key is supplied by the viewer as a ?key= query parameter
on /map; the server never sees, stores, or hardcodes it.
"""

import json
import os
from importlib import resources
from pathlib import Path

from flask import Blueprint, Response

from frontdoor.commons_imagery import commons_provenance_for_place
from frontdoor.corrections import (
    CORRECTIONS_ENV,
    DEFAULT_CORRECTIONS_PATH,
    apply_relook,
    load_correction_store,
)
from frontdoor.external_data import load_side_file, provenance_for_place
from frontdoor.map_states import prepare_map_payload
from frontdoor.scan_records import (
    DEFAULT_PUBLISHED_SCANS_PATH,
    DEFAULT_SCANS_PATH,
    PUBLISHED_SCANS_ENV,
    SCANS_ENV,
    load_scan_store,
    merge_scans,
)

DATASET_ENV = "FRONTDOOR_MAP_DATASET"
DEFAULT_DATASET_PATH = "data/precatalogue.json"
EXTERNAL_OSM_ENV = "FRONTDOOR_EXTERNAL_OSM"
DEFAULT_EXTERNAL_OSM_PATH = "data/external/osm_accessibility.json"
EXTERNAL_COMMONS_ENV = "FRONTDOOR_EXTERNAL_COMMONS"
DEFAULT_EXTERNAL_COMMONS_PATH = "data/external/commons_imagery.json"

map_page = Blueprint("map_page", __name__)


@map_page.get("/map")
def map_html():
    html = (
        resources.files("frontdoor_server")
        .joinpath("map.html")
        .read_text(encoding="utf-8")
    )
    return Response(html, mimetype="text/html")


@map_page.get("/map/data")
def map_data():
    path = Path(os.environ.get(DATASET_ENV, DEFAULT_DATASET_PATH))
    dataset = None
    dataset_error = None
    try:
        dataset = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        dataset_error = f"dataset not found: {path}"
    except (OSError, json.JSONDecodeError) as exc:
        dataset_error = f"dataset unreadable: {exc}"
    # Community scans (TICK-262): merged into the dataset BEFORE states are
    # computed, so a scanned place carries its upgraded row through the same
    # Green-or-Gray gate as every other row. merge_scans can only ever add a
    # pin or raise one — never lower a state, an observation, or a date
    # (frontdoor.scan_records' never-negative contract) — and no scan store,
    # or an unreadable one, changes nothing at all.
    #
    # Two stores, read in this order (TICK-333): the curated on-site
    # publication that ships in the image, then the runtime store on the
    # mounted volume. Order is presentational only -- merge_scans is
    # never-negative and monotone, so neither store can undo the other, and a
    # place carrying both simply ends up with the later capture date and the
    # higher observation. Either store missing or unreadable is not an error;
    # the map renders on whichever it has, and says which one failed.
    published = load_scan_store(
        os.environ.get(PUBLISHED_SCANS_ENV, DEFAULT_PUBLISHED_SCANS_PATH)
    )
    scans = load_scan_store(os.environ.get(SCANS_ENV, DEFAULT_SCANS_PATH))
    dataset, scan_meta = merge_scans(
        dataset, published.records + scans.records
    )
    # Community corrections (TICK-387): freshness ONLY. apply_relook writes
    # exactly `needs_relook` and `relook_since` onto rows that corroborated
    # reports say may have moved on since the evidence was taken -- never a
    # status, a source, a criterion, or a row that did not already exist. The
    # states above and below are therefore computed from inputs no correction
    # is part of, and a correction cannot make a pin say anything negative
    # about a business; the most it can do is ask somebody to go and look
    # again.
    corrections = load_correction_store(
        os.environ.get(CORRECTIONS_ENV, DEFAULT_CORRECTIONS_PATH)
    )
    dataset, relook = apply_relook(dataset, corrections.records)
    payload = prepare_map_payload(dataset)
    payload["dataset_error"] = dataset_error
    payload["scans_error"] = scans.error
    payload["scans_loaded"] = len(scans.records)
    payload["scans_skipped"] = scans.skipped
    payload["published_scans_error"] = published.error
    payload["published_scans_loaded"] = len(published.records)
    payload["published_scans_skipped"] = published.skipped
    payload["corrections_error"] = corrections.error
    osm_error, commons_error = _attach_provenance(payload["pins"])
    payload["osm_error"] = osm_error
    payload["commons_error"] = commons_error
    _attach_scan_provenance(payload["pins"], scan_meta)
    _attach_relook(payload["pins"], dataset, relook)
    return payload


def _attach_provenance(pins):
    """Add the optional "provenance" array to pins with external matches.

    States and labels are already computed; this only ever appends
    source+date lines (positive-only by frontdoor.external_data's
    never-negative rule) and touches nothing else. Load failures are
    returned so /map/data can name them the way it names a missing
    dataset; an empty successful file is not a failure.
    """
    osm_records, osm_error = load_side_file(
        os.environ.get(EXTERNAL_OSM_ENV, DEFAULT_EXTERNAL_OSM_PATH), "osm"
    )
    commons_records, commons_error = load_side_file(
        os.environ.get(EXTERNAL_COMMONS_ENV, DEFAULT_EXTERNAL_COMMONS_PATH),
        "commons",
    )
    if osm_records or commons_records:
        for pin in pins:
            location = pin["location"]
            lines = provenance_for_place(
                pin.get("name"), location["lat"], location["lng"], osm_records
            )
            lines += commons_provenance_for_place(
                location["lat"], location["lng"], commons_records
            )
            if lines:
                pin["provenance"] = lines
    return osm_error, commons_error


def _attach_scan_provenance(pins, scan_meta):
    """Prepend the on-site scan receipt row to every scanned pin.

    Runs after _attach_provenance so the scan line composes with (and leads)
    the external lines rather than being overwritten by them. Like every
    provenance line, it only ever appends information; the pin's state was
    already computed from the merged row.
    """
    if not scan_meta:
        return
    for pin in pins:
        meta = scan_meta.get(pin["place_id"])
        if not meta:
            continue
        date = meta["last_scanned"]
        line = {
            "source": "community_scan",
            "label": f"Scanned on-site — {date}",
            "date": date,
        }
        pin["provenance"] = [line] + pin.get("provenance", [])
        pin["last_scanned"] = date
        pin["scan_count"] = meta["scan_count"]


def _attach_relook(pins, dataset, relook):
    """Surface the re-look request on the pins it applies to.

    Freshness and nothing else: `needs_relook` and `relook_since`, plus one
    provenance line that says a re-look was asked for and when. The pin's
    state, label, checklist and owner_confirmed flag were all decided before
    this ran, from a row apply_relook did not touch, so this cannot turn a
    green stamp neutral or an observation negative -- it is the input to the
    app's existing "Could you take another look?" nudge, which asks for a
    photograph rather than making a claim.
    """
    if not relook:
        return
    for pin in pins:
        row = dataset.get(pin["place_id"])
        if not isinstance(row, dict) or row.get("needs_relook") is not True:
            continue
        since = row.get("relook_since")
        pin["needs_relook"] = True
        pin["relook_since"] = since
        line = {
            "source": "community_correction",
            "label": f"Re-look requested — {since}",
            "date": since,
        }
        pin["provenance"] = pin.get("provenance", []) + [line]
