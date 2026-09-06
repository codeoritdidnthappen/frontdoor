"""GET /app: the served EntryMap app page (TICK-247).

The page is the phone-web scanner. It is served by the same image that answers its
POSTs, so every call it makes is same-origin; these tests pin that wiring on the
served bytes, not on a copy elsewhere.
"""

import json
import shutil
import subprocess
from importlib import resources

import pytest

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


# --- a failed scan is a failed scan (TICK-351, #351) -------------------------
#
# The scan flow is client-side JavaScript with no runner in this suite, so these read
# the served source. They are deliberately pinned to the few expressions that decide
# whether a person is shown a verdict or a failure, because that decision is the whole
# defect: any rejection of the /screen POST — including the 30 s client abort that
# collides exactly with gunicorn's --timeout 30 — used to select the simulated
# pipeline, whose staged verdicts then took the Scanned tier, the scanned count, and a
# first-person sentence about a photograph nothing had read.


def simulated_predicate(html):
    return html.split("const liveSimulated =", 1)[1].split("\n", 1)[0]


def test_only_the_absence_of_a_server_selects_the_simulated_pipeline():
    html = page().get_data(as_text=True)
    predicate = simulated_predicate(html)
    assert "liveNetFail" not in predicate  # a failed request is not "there is no server"
    assert "HAS_SERVER" in predicate
    assert "const HAS_SERVER = location.protocol.startsWith('http');" in html


def test_a_failed_or_timed_out_scan_says_so_and_offers_a_retry():
    html = page().get_data(as_text=True)
    assert "The scan could not be completed" in html
    assert "publish to try again, or retake" in html
    assert "the scan timed out" in html
    assert "could not reach the server" in html
    # ...and it does not reassure the user about an upload that never happened
    failed = html.split("The scan could not be completed", 1)[0].rsplit("} else {", 1)[1]
    assert "Not checked — this photo has not left your phone" in failed
    assert "Faces blurred at upload" not in failed


def test_a_simulated_run_writes_nothing_to_the_map():
    """No tier, no verdicts, no date, no outcome stamp — and no new pin either.

    upgradePin is what moves a pin to Scanned on-site and so what the "N of M entrances
    scanned" count counts. The simulated branch must not reach it, must not reach
    placeForRef (which pushes a pin onto the map), and must not invent a verdict.
    """
    html = page().get_data(as_text=True)
    simulated = html.split("\n  if(simulated){", 1)[1].split("\n  } else {", 1)[0]
    assert "upgradePin(" not in simulated
    assert "placeForRef(" not in simulated
    assert "present" not in simulated  # no fabricated verdict survives here at all
    assert "riser shadow" not in simulated
    assert "p=ref.place || {" in simulated  # an existing pin is reused, untouched
    # ...and nothing anywhere in the page speaks about the user's own photograph in the
    # first person, which only fabricated evidence ever did.
    assert "in your photo" not in html


def test_the_done_screen_is_told_the_outcome_rather_than_reading_it_off_the_pin():
    """A simulated run must not relabel an earlier real publish on the same pin."""
    html = page().get_data(as_text=True)
    assert "function doneHeading(p, simulated){" in html
    assert "function runDone(p, simulated){" in html
    assert "runDone(p, simulated);" in html
    done = html.split("function runDone(p, simulated){", 1)[1].split("\n}", 1)[0]
    assert "p.publish" not in done  # the outcome comes from the run, not from the pin


def test_the_scan_docstring_matches_what_the_code_does():
    html = page().get_data(as_text=True)
    assert "Only an outright network failure" not in html  # the claim that was untrue
    assert "The simulated pipeline runs only where there is no server to talk to" in html


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


def test_the_worker_cache_name_carries_the_deployed_commit(monkeypatch):
    """A fixed cache name means a deploy never reaches a phone that already
    opened the app.

    The worker's own comment claimed "a new deploy changes CACHE", but CACHE
    was the literal "entrymap-v1" and nothing changed it. A design port then
    shipped and a phone that had opened /app before was served the previous
    release out of its own cache, showing the old artwork while the server
    answered correctly. The name now carries the commit.
    """
    monkeypatch.setenv("FRONTDOOR_COMMIT", "0321be0cb620b33a2309febac8f09e6812fc00d4")
    body = create_app().test_client().get("/app-sw.js").get_data(as_text=True)
    assert 'const CACHE = "entrymap-0321be0cb620b33a2309febac8f09e6812fc00d4";' in body
    assert "__COMMIT__" not in body


def test_two_commits_produce_two_cache_names(monkeypatch):
    """The point is the difference, not the format: same worker source, two
    deploys, two names, so activate drops the older shell."""
    names = []
    for commit in ("aaaaaaa1", "bbbbbbb2"):
        monkeypatch.setenv("FRONTDOOR_COMMIT", commit)
        body = create_app().test_client().get("/app-sw.js").get_data(as_text=True)
        names.append(body.split('const CACHE = "')[1].split('"')[0])
    assert names[0] != names[1]


def test_an_unknown_commit_still_yields_a_usable_cache_name(monkeypatch):
    """Locally, and in any environment that does not set the variable, the
    worker must still install. A missing commit falls back to a constant,
    which is exactly the behaviour that shipped before and no worse."""
    monkeypatch.delenv("FRONTDOOR_COMMIT", raising=False)
    body = create_app().test_client().get("/app-sw.js").get_data(as_text=True)
    assert 'const CACHE = "entrymap-unversioned";' in body
    assert "__COMMIT__" not in body


def test_a_hostile_commit_value_cannot_break_out_of_the_string(monkeypatch):
    """The value arrives from the environment, so it is stripped to letters
    and digits before it reaches a JavaScript string literal."""
    monkeypatch.setenv("FRONTDOOR_COMMIT", 'x"; caches.delete("entrymap-v1"); //')
    body = create_app().test_client().get("/app-sw.js").get_data(as_text=True)
    name = body.split('const CACHE = "')[1].split('"')[0]
    assert name.startswith("entrymap-")
    assert name.removeprefix("entrymap-").isalnum()
    assert "caches.delete" not in name


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


def _block(html, start, end="\n}"):
    """One named block of the page's script, from `start` up to and including `end`."""
    assert start in html, f"the page no longer contains {start!r}"
    body = html.split(start, 1)[1]
    assert end in body, f"{start!r} has no {end!r} terminator"
    return start + body.split(end, 1)[0] + end


def _run_review_chips(html, criteria):
    """Run the page's own reviewChipsHTML over a /screen body, in node.

    Source-text assertions pass a rewrite that reintroduces the defect, so the
    real function is executed. It returns an HTML string and touches no DOM,
    so only its own dependencies have to be lifted out of the page.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not on PATH")
    prelude = "\n".join([
        _block(html, "const FEATS = {", "\n};"),
        _block(html, "const EST_KEYMAP = {", "};"),
        _block(html, "const LIVE_CRITERIA = [", "];"),
        _block(html, "function dotTriple(conf, cls){"),
        _block(html, "function esc(s){", "}"),
        "const liveSimulated = () => false;",
        "const STAGED = [];",
        "function liveFailure(){ return 'unused'; }",
        "const liveResult = " + json.dumps(
            {"assessment": {"criteria": criteria}}) + ";",
        _block(html, "function reviewChipsHTML(chipsOnly){"),
        "console.log(reviewChipsHTML(false));",
    ])
    result = subprocess.run(
        [node, "-e", prelude], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_tick_399_a_criterion_with_no_verdict_is_not_reported_as_not_seen():
    """A refused answer is never presented to the person at the door as an observation.

    Since TICK-399 the server keeps the criteria a rejected reply DID validate
    and refuses only the field it got wrong, so a 200 response can carry a
    criterion with a null verdict. The chips used to say "not seen this time"
    for anything that was not `present`, which would tell somebody standing at
    a door that a feature was not there when the engine never got an answer
    about it -- a rejected response presented as an observation, which is the
    one thing this product's rules forbid.
    """
    html = page().get_data(as_text=True)
    chips = html.split("function reviewChipsHTML(chipsOnly){", 1)[1].split(
        "\n}", 1)[0]
    assert "Not assessed this time:" in chips
    assert "Not seen this time:" in chips

    rendered = _run_review_chips(html, {
        "ramp_or_bevel": {"verdict": "present", "confidence": 80,
                          "evidence": "ramp visible"},
        "handrails": {
            "verdict": None, "confidence": None, "evidence": None,
            "rejected": "ada_check_value", "rejected_value": "not_applicable",
        },
        "accessible_door_hardware": {"verdict": "absent", "confidence": 70,
                                     "evidence": "round knob"},
        "accessibility_signage": {"verdict": "not_visible", "confidence": 40,
                                  "evidence": "not in frame"},
    })
    assert "Not assessed this time:" in rendered, (
        "the refused criterion produced no 'not assessed' line; it was bucketed "
        "somewhere else, and the only other bucket says a feature was not seen"
    )
    not_seen = rendered.split("Not seen this time:", 1)[1].split("<", 1)[0]
    not_assessed = rendered.split("Not assessed this time:", 1)[1].split("<", 1)[0]
    # The refused criterion is in its own sentence, and in neither of the others.
    assert "Handrails" in not_assessed
    assert "Handrails" not in not_seen
    # The two the model did answer are still reported as answers it gave.
    assert "Easy-grip handle" in not_seen and "Access signage" in not_seen
    # ...and the one it committed to is still a chip.
    assert "Ramp or bevel" in rendered.split("Not seen this time:", 1)[0]
    # Nothing anywhere turns the refused word into a verdict.
    assert "not_applicable" not in rendered
