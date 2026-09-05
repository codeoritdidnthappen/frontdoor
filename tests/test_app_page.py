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
    assert "const CLAIM_API = '/claim';" in html
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


def test_the_home_screen_icon_is_served_from_this_origin():
    """iOS ignores a data: URI in apple-touch-icon and falls back to the favicon.

    An installed shortcut then carries the wrong image, which is exactly what
    happened before TICK-325. The icon has to come from a real URL on this
    origin, so both the route and the page's reference to it are pinned here.
    """
    response = create_app().test_client().get("/app-icon.png")
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    body = response.get_data()
    assert body.startswith(b"\x89PNG\r\n\x1a\n")
    assert body == (
        resources.files("frontdoor_server").joinpath("app-icon.png").read_bytes()
    )


def test_the_page_points_at_the_served_icon_and_not_a_data_uri():
    html = page().get_data(as_text=True)
    assert 'rel="apple-touch-icon" sizes="180x180" href="/app-icon.png"' in html
    assert 'apple-touch-icon" href="data:' not in html
    assert '<meta name="apple-mobile-web-app-title" content="EntryMap">' in html


def test_the_manifest_makes_the_page_installable():
    """TICK-327: manifest plus service worker is what turns the page into an app.

    There is no paid Apple account on this project, so TestFlight and the App
    Store are both closed. Installing from the browser is the only route to a
    phone, and it needs these two files served correctly.
    """
    import json

    response = create_app().test_client().get("/app-manifest.json")
    assert response.status_code == 200
    assert response.mimetype == "application/manifest+json"
    manifest = json.loads(response.get_data(as_text=True))
    assert manifest["name"] == "EntryMap"
    assert manifest["start_url"] == "/app"
    assert manifest["display"] == "standalone"
    # Every icon the manifest names has to actually be served, or the install
    # silently falls back to a screenshot of the page.
    client = create_app().test_client()
    for icon in manifest["icons"]:
        assert client.get(icon["src"]).status_code == 200


def test_the_service_worker_is_served_uncached_with_root_scope():
    """A cached worker cannot be replaced, so a deploy could never reach an
    already-installed phone. Scope has to cover /app, which is not its own path."""
    response = create_app().test_client().get("/app-sw.js")
    assert response.status_code == 200
    assert "javascript" in response.mimetype
    assert response.headers["Cache-Control"] == "no-cache"
    assert response.headers["Service-Worker-Allowed"] == "/"


def test_the_worker_never_caches_an_answer_about_a_real_doorway():
    """Screening, map and photo responses must not be served from a cache.

    A stale verdict is a wrong answer about somebody's front door, which is
    worse than no answer. The worker's allowlist is the whole defence, so it
    is pinned here rather than left to review.
    """
    worker = (
        resources.files("frontdoor_server").joinpath("app-sw.js").read_text(encoding="utf-8")
    )
    assert 'const SHELL = ["/app", "/app-icon.png", "/app-manifest.json"];' in worker
    for never_cached in ("/screen", "/screen/publish", "/map/data", "/scan/photo"):
        assert f'"{never_cached}"' not in worker.split("const SHELL")[1].split("]")[0]


def test_the_page_registers_the_worker_and_links_the_manifest():
    html = page().get_data(as_text=True)
    assert '<link rel="manifest" href="/app-manifest.json">' in html
    assert 'navigator.serviceWorker.register("/app-sw.js")' in html
