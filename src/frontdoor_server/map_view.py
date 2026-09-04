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

The Google Maps API key is supplied by the viewer as a ?key= query parameter
on /map; the server never sees, stores, or hardcodes it.
"""

import json
import os
from importlib import resources
from pathlib import Path

from flask import Blueprint, Response

from frontdoor.commons_imagery import (
    commons_provenance_for_place,
    load_commons_records,
)
from frontdoor.external_data import load_osm_records, provenance_for_place
from frontdoor.map_states import prepare_map_payload

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
    payload = prepare_map_payload(dataset)
    payload["dataset_error"] = dataset_error
    _attach_provenance(payload["pins"])
    return payload


def _attach_provenance(pins):
    """Add the optional "provenance" array to pins with external matches.

    States and labels are already computed; this only ever appends
    source+date lines (positive-only by frontdoor.external_data's
    never-negative rule) and touches nothing else. No external file, no
    change at all.
    """
    osm_records = load_osm_records(
        os.environ.get(EXTERNAL_OSM_ENV, DEFAULT_EXTERNAL_OSM_PATH))
    commons_records = load_commons_records(
        os.environ.get(EXTERNAL_COMMONS_ENV, DEFAULT_EXTERNAL_COMMONS_PATH))
    if not osm_records and not commons_records:
        return
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
