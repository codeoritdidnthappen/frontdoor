"""GET /app: the served EntryMap app page (TICK-247).

The page is the phone-web scanner. It is served by the same image that answers its
POSTs, so every call it makes is same-origin; these tests pin that wiring on the
served bytes, not on a copy elsewhere.
"""

import json
import re
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
    shell = worker.split("const SHELL =", 1)[1].split("];", 1)[0]
    cached = set(re.findall(r'"([^"]+)"', shell))
    # Pinned as a set rather than a literal line, because the self-hosted faces joined it
    # and the string match made that look like a safety regression when it is not. Adding
    # anything still means changing this test on purpose, which is the point.
    assert cached == {
        "/app",
        "/app-icon.png",
        "/app-manifest.json",
        "/app-fonts/AtkinsonHyperlegibleNext-Variable.woff2",
        "/app-fonts/AtkinsonHyperlegibleNext-Italic-Variable.woff2",
        "/app-fonts/NunitoSans-ExtraBold.ttf",
    }, cached
    # The property the set above exists to protect: nothing that answers about a real
    # doorway may be served from a cache, however the shell is spelled.
    for never_cached in ("/screen", "/screen/publish", "/map/data", "/scan/photo"):
        assert never_cached not in cached


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


# --- a missing scan is not silent (TICK-370, #370) ---------------------------
#
# /map/data reports scans_error and scans_skipped. This page is the surface a
# contributor uses to see the scan they just published. Until now neither field
# was read here, so an unreachable store or a torn record took their scan off
# the map with no word. The map page already banners both; this page did not.
# These read the served source the same way the rest of this file does: there
# is no JS runtime, and the claim that can be stated in the source is which
# fields are read and how they are shown.


def test_the_app_page_tells_a_contributor_when_published_scans_could_not_be_loaded():
    """An unreachable scan store must not look like an empty publish.

    dataset_error is console.info because this page still has embedded pins to
    draw. scans_error is not that case: the scan they published is gone, and
    they will not open a console. The toast names the subsystem; the server's
    string quotes a filesystem path and this page is public.
    """
    live = _block(page().get_data(as_text=True), "function loadLiveMap(){")
    line = next(ln for ln in live.splitlines() if "j.scans_error" in ln)
    assert "toast(" in line
    assert "console." not in line
    assert "+ j.scans_error" not in live
    assert "j.scans_error +" not in live
    assert "+j.scans_error" not in live
    assert "j.scans_error+" not in live


def test_the_app_page_tells_a_contributor_when_a_published_scan_could_not_be_read():
    """A torn JSONL line is skipped and the rest of the store still loads.

    scans_skipped is a count, not a message: load_scan_store carries on, so this
    is the only place that loss ever surfaces. A contributor whose scan was the
    torn line sees every other pin and not theirs. Toast the count; do not wait
    for scans_error, which is null on a store that otherwise opened.
    """
    live = _block(page().get_data(as_text=True), "function loadLiveMap(){")
    assert "j.scans_skipped" in live
    assert "toast(" in live.split("j.scans_skipped", 1)[1]


# --------------------------------------------------------------------------- self-hosted type


FONTS = [
    "AtkinsonHyperlegibleNext-Variable.woff2",
    "AtkinsonHyperlegibleNext-Italic-Variable.woff2",
    "NunitoSans-ExtraBold.ttf",
]


def test_the_page_fetches_no_typeface_from_another_origin():
    """The page used to pull its faces from fonts.googleapis.com.

    Its fallback chain ends in system-ui, so a venue with slow, captive-portalled or
    filtered wifi silently dropped the whole type system with nothing to say it had
    happened -- and an installable page meant to launch with no signal cannot depend on a
    font it can only fetch from someone else. It also stopped disclosing every visitor to
    Google, which on a product where people state disability-related needs is a decision
    rather than a default.

    Comments may still name the domain -- one explains why it is gone. What may not appear
    is a request: a stylesheet link, an @import, or a font source anywhere but this origin.
    """
    html = page().get_data(as_text=True)
    without_comments = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    for host in ("fonts.googleapis.com", "fonts.gstatic.com"):
        assert host not in without_comments, f"the page still reaches {host} for type"
    sources = re.findall(r"@font-face\s*\{[^}]*?url\(\s*['\"]?([^'\")]+)", html)
    assert sources, "no @font-face rule found; the page declares no type of its own"
    for source in sources:
        assert source.startswith("/app-fonts/"), f"font served from off-origin: {source}"


def test_every_face_the_page_asks_for_is_actually_served():
    """Page and route have to agree. A renamed file is a silent fallback to system-ui."""
    client = create_app().test_client()
    html = client.get("/app").get_data(as_text=True)
    asked = set(re.findall(r"/app-fonts/([\w\-.\[\]]+)", html))
    assert asked, "the page references no self-hosted font"
    for name in sorted(asked):
        response = client.get(f"/app-fonts/{name}")
        assert response.status_code == 200, f"the page asks for {name} and it 404s"
        assert response.headers["Content-Type"].startswith("font/")


def test_the_fonts_are_served_immutable_so_the_worker_can_hold_them():
    client = create_app().test_client()
    for name in FONTS:
        response = client.get(f"/app-fonts/{name}")
        assert response.status_code == 200
        assert len(response.data) > 10_000, f"{name} looks truncated"
        assert "immutable" in response.headers["Cache-Control"]


def test_an_unknown_font_name_is_refused_rather_than_joined_to_a_path():
    client = create_app().test_client()
    for name in ("nope.woff2", "..%2fapp.py", "../app.py"):
        assert client.get(f"/app-fonts/{name}").status_code == 404


def test_the_installed_app_carries_its_own_type_offline():
    """Without the faces in the shell, the installed app launches with no signal in the
    system font -- which is the failure self-hosting them exists to prevent."""
    worker = (
        resources.files("frontdoor_server").joinpath("app-sw.js").read_text(encoding="utf-8")
    )
    shell = worker.split("const SHELL =", 1)[1].split("];", 1)[0]
    for name in FONTS:
        assert f"/app-fonts/{name}" in shell, f"{name} is not in the service worker shell"
