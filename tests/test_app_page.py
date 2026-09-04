"""GET /app: the served EntryMap app page (TICK-247).

The page is the phone-web scanner. It is served by the same image that answers its
POSTs, so every call it makes is same-origin; these tests pin that wiring on the
served bytes, not on a copy elsewhere.
"""

from importlib import resources

from frontdoor_server.app import MAX_REQUEST_BYTES, create_app


def page(app=None):
    return (app or create_app()).test_client().get("/app")


def test_the_page_is_served_as_html_with_the_entrymap_title():
    response = page()
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert "<title>EntryMap</title>" in response.get_data(as_text=True)


def test_the_page_matches_the_packaged_file():
    packaged = (
        resources.files("frontdoor_server")
        .joinpath("app.html")
        .read_text(encoding="utf-8")
    )
    assert page().get_data(as_text=True) == packaged


def test_the_page_is_not_capped_by_the_request_size_limit():
    """MAX_CONTENT_LENGTH bounds what a client may SEND; the ~1 MB page is a response.

    Pinned because the two are easy to confuse when the limit is tightened: a ceiling that
    also truncated responses would ship a page whose script never closes.
    """
    app = create_app()
    app.config["MAX_CONTENT_LENGTH"] = 1024
    response = page(app)
    assert response.status_code == 200
    body = response.get_data()
    assert len(body) > 1024
    assert len(body) > MAX_REQUEST_BYTES // 100  # well over the tightened cap, not a stub page
    assert body.rstrip().endswith(b"</html>")


def test_the_page_is_served_without_an_api_key(monkeypatch):
    """The page must load on a host without the screening key; only publishing needs it."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert page().status_code == 200


def test_the_page_targets_this_origin_only():
    """Relative URLs to this service's own endpoints, and no other host for the scan path."""
    html = page().get_data(as_text=True)
    assert "const SCREEN_API = '/screen';" in html
    assert "const PUBLISH_API = '/screen/publish';" in html
    assert "const PHOTO_API = '/scan/photo/';" in html
    assert "fetch('/map/data'" in html
    assert "X-Frontdoor-Contributor" in html
    assert "fly.dev" not in html


def test_the_page_carries_a_short_max_age_and_nothing_else_about_caching():
    response = page()
    assert response.headers["Cache-Control"] == "public, max-age=300"
    assert "Expires" not in response.headers
    assert "ETag" not in response.headers


def test_the_page_is_outside_the_cors_scope():
    """The wildcard CORS header is scoped to the screening routes; the page is same-origin."""
    assert "Access-Control-Allow-Origin" not in page().headers
