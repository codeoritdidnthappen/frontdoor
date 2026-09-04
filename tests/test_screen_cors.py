"""Cross-origin access to the screening surface (fix/screen-cors).

Browser scan clients POST multipart to /screen and /screen/publish and fetch
/scan/photo/<key> from another origin. A multipart POST is a CORS "simple
request": without Access-Control-Allow-Origin the browser SENDS the request --
burning the model call -- and then discards the response it is not allowed to
read. So the header must ride on error responses as much as on 200s: a browser
client that cannot read the 400, the 502 or the 503 sees only "CORS failure"
where the service wrote a precise message.

The scope is closed. Only /screen, /screen/publish and /scan/photo/<key> carry
the header -- they serve public, privacy-processed content and verdicts with no
cookies and no auth, so `*` exposes no credentials. /upload, /measure and
/map/data are asserted NOT to carry it: /map/data is intentionally out of
scope, and the other two are not browser surfaces.
"""

import pytest

from frontdoor.storage import StorageError
from tests.test_scan_publish_endpoint import (
    FakeStore,
    make_client,
    post_publish,
)
from tests.test_screen_endpoint import FakeEngine, image_part, post_screen

ACAO = "Access-Control-Allow-Origin"


@pytest.fixture
def scans_path(tmp_path, monkeypatch):
    path = tmp_path / "scans.jsonl"
    monkeypatch.setenv("FRONTDOOR_SCANS", str(path))
    return path


def assert_cors(response):
    assert response.headers.get(ACAO) == "*", (
        f"{response.status_code} response is missing {ACAO}: a browser would "
        "discard this exact body"
    )


# --- POST /screen -------------------------------------------------------------


def test_screen_success_carries_the_header():
    response = post_screen(make_client(), [image_part()])
    assert response.status_code == 200
    assert_cors(response)


def test_screen_request_error_carries_the_header():
    # No image parts: 400. The browser needs to read this error, not a CORS wall.
    response = post_screen(make_client(), [])
    assert response.status_code == 400
    assert_cors(response)


def test_screen_engine_failure_carries_the_header():
    engine = FakeEngine(raises=RuntimeError("spend cap breached"))
    response = post_screen(make_client(engine=engine), [image_part()])
    assert response.status_code == 502
    assert_cors(response)


def test_screen_unsupported_type_carries_the_header():
    part = image_part("notes.txt", content_type="text/plain", data=b"hi")
    response = post_screen(make_client(), [part])
    assert response.status_code == 415
    assert_cors(response)


def test_screen_demo_page_carries_the_header():
    response = make_client().get("/screen")
    assert response.status_code == 200
    assert_cors(response)


def test_wrong_method_on_screen_carries_the_header():
    """405 is raised by routing and JSON-ified by the app-level errorhandler --
    the path that never enters a view. The hook must cover it anyway."""
    response = make_client().put("/screen")
    assert response.status_code == 405
    assert_cors(response)


# --- POST /screen/publish -----------------------------------------------------


def test_publish_success_carries_the_header(scans_path):
    response = post_publish(make_client(store=FakeStore()), [image_part()])
    assert response.status_code == 200
    assert response.get_json()["published"] is True
    assert_cors(response)


def test_publish_request_error_carries_the_header():
    # Image but no place reference: 400.
    response = post_publish(make_client(), [image_part()], form={})
    assert response.status_code == 400
    assert_cors(response)


def test_publish_storage_failure_carries_the_header(scans_path):
    store = FakeStore(put_raises=StorageError("put failed (500)"))
    response = post_publish(make_client(store=store), [image_part()])
    assert response.status_code == 503
    assert_cors(response)


# --- GET /scan/photo/<key> ----------------------------------------------------


def test_scan_photo_success_carries_the_header():
    key = "scans/example/0123456789abcdef0123456789abcdef.jpg"
    store = FakeStore(objects={"open/" + key: b"\xff\xd8jpeg"})
    response = make_client(store=store).get(f"/scan/photo/{key}")
    assert response.status_code == 200
    assert_cors(response)


def test_scan_photo_404_carries_the_header():
    response = make_client(store=FakeStore()).get("/scan/photo/not-a-key")
    assert response.status_code == 404
    assert_cors(response)


# --- OPTIONS ------------------------------------------------------------------
#
# The multipart POST itself never preflights, but a publish carrying the
# optional X-Frontdoor-Contributor header does (a non-safelisted request header
# makes the request non-simple), so OPTIONS must answer with the method and
# header allowances the browser asks about.


@pytest.mark.parametrize("path", ["/screen", "/screen/publish"])
def test_options_answers_as_a_valid_preflight(path):
    response = make_client().open(path, method="OPTIONS")
    assert response.status_code == 200
    assert_cors(response)
    assert "POST" in response.headers["Access-Control-Allow-Methods"]
    allowed = response.headers["Access-Control-Allow-Headers"].lower()
    assert "content-type" in allowed
    assert "x-frontdoor-contributor" in allowed


# --- the scope stays closed ---------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/upload"),
        ("POST", "/measure"),
        ("GET", "/map/data"),
        ("GET", "/health"),
    ],
)
def test_uncovered_routes_do_not_carry_the_header(method, path):
    response = make_client().open(path, method=method)
    assert ACAO not in response.headers, (
        f"{path} must not serve cross-origin: CORS is scoped to the screening "
        "surface only"
    )
