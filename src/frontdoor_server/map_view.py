"""GET /map and GET /map/data: the public stamp map (TICK-247, #169).

/map serves the static map page; /map/data serves the demo-area dataset with
each pin's stamp state pre-computed server-side by frontdoor.map_states, so
the Green-or-Gray rule is enforced (and tested) in Python — the page renders
states, it does not decide them.

The dataset is the TICK-248 pre-catalogue output (data-shape dependency
only). Its path comes from FRONTDOOR_MAP_DATASET, defaulting to
data/precatalogue.json. A missing or unreadable dataset degrades to an empty
pin list with the problem named in the payload, never an error page.

The Google Maps API key is supplied by the viewer as a ?key= query parameter
on /map; the server never sees, stores, or hardcodes it.
"""

import json
import os
from importlib import resources
from pathlib import Path

from flask import Blueprint, Response

from frontdoor.map_states import prepare_map_payload

DATASET_ENV = "FRONTDOOR_MAP_DATASET"
DEFAULT_DATASET_PATH = "data/precatalogue.json"

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
    return payload
