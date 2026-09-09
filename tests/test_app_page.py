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


def test_the_page_is_revalidated_rather_than_held_for_a_window():
    """The five-minute window fed the service worker a build older than the server (#483).

    It used to be `public, max-age=300`. Watched in Chromium across a deploy, the new
    worker's own fetch of /app was answered out of that window, so it filled its new,
    correctly commit-named cache with the PREVIOUS build -- and then served it, from a
    cache nothing was left to invalidate, for three consecutive loads. `no-cache` means
    revalidate before reuse, so no cache anywhere can answer with a build the server has
    replaced.
    """
    response = page()
    assert response.headers["Cache-Control"] == "no-cache"
    assert "max-age" not in response.headers["Cache-Control"]
    assert "Expires" not in response.headers


def test_an_unchanged_page_is_revalidated_without_sending_it_again():
    """`no-cache` without a validator would mean 1.6 MB on every navigation.

    The point of the header is correctness, and the point of the ETag is that
    correctness stays cheap: a phone that already has the current build pays a
    conditional request answered with no body at all.
    """
    client = create_app().test_client()
    first = client.get("/app")
    assert first.status_code == 200
    etag = first.headers["ETag"]
    assert etag

    again = client.get("/app", headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.get_data() == b""


def test_the_validator_is_taken_from_the_page_itself():
    """An ETag that cannot tell two builds apart is worse than none.

    It is a digest of the page's own bytes rather than of FRONTDOOR_COMMIT, because
    locally the commit is unset for every build -- which is exactly when a stale page
    is hardest to notice. Being a digest is what makes it change on, and only on, a
    change to the page.
    """
    from werkzeug.http import generate_etag

    served = page()
    assert served.headers["ETag"].strip('"') == generate_etag(served.get_data())
    assert generate_etag(served.get_data() + b"<!-- a later build -->") != generate_etag(
        served.get_data()
    )


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


def test_the_page_reloads_itself_once_when_a_new_build_takes_over():
    """The load right after a deploy renders the previous build, and says nothing (#483).

    /app is served cache-first, so the navigation is answered out of the old worker's
    cache before the browser has even looked at /app-sw.js. Cache-first is kept -- the
    page is 1.6 MB and has to open on one bar of signal -- so the page corrects itself:
    when the new worker claims it, it reloads, once.

    Watched in Chromium across two simulated deploys, the load after each deploy
    rendered twice (old, then new, ~2.8 s apart) and every other load rendered once.
    """
    html = page().get_data(as_text=True)
    assert 'navigator.serviceWorker.addEventListener("controllerchange"' in html
    assert "location.reload();" in html


def test_the_reload_cannot_loop():
    """A worker that reloads on activation is one unlucky race from reloading forever.

    Two guards, and both have to be here: a document that had no controller when it
    loaded came off the network and is already current, so claim() on a first-ever visit
    must not reload it; and no document may reload more than once whatever it is told.
    """
    html = page().get_data(as_text=True)
    guard = html.split('addEventListener("controllerchange"', 1)[1].split("});", 1)[0]
    assert "if (!swHadController || swReloaded) return;" in guard
    assert "swReloaded = true;" in guard
    # The flag has to be read from the controller at load time, not at event time: by the
    # time the event fires there is always a controller, and the guard would never hold.
    assert "var swHadController = !!navigator.serviceWorker.controller;" in html


def test_the_new_worker_takes_over_without_waiting_for_the_precache():
    """skipWaiting() used to be chained after cache.addAll(SHELL).

    That put a 1.6 MB download between the stale page appearing and the new worker
    claiming it -- and the page's reload cannot happen until the claim does. Measured
    on localhost the takeover is ~1.7 s; behind the precache it is the download as well.
    """
    worker = (
        resources.files("frontdoor_server").joinpath("app-sw.js").read_text(encoding="utf-8")
    )
    install = worker.split('addEventListener("install"', 1)[1].split("\n});", 1)[0]
    assert "self.skipWaiting();" in install
    before, after = install.split("self.skipWaiting();", 1)
    assert "addAll(SHELL)" in before, "the precache is assigned before the takeover"
    assert "await" not in before and ".then(() => self.skipWaiting())" not in install
    assert "skipWaiting" not in after, "skipWaiting must be called once, not chained again"


def test_the_previous_shell_is_only_dropped_once_this_one_is_in_place():
    """Claiming early is what makes the correction fast; deleting early would cost the
    offline promise.

    activate() claims immediately, then waits for the precache before dropping the old
    cache. Between the two there would otherwise be a window with the previous shell
    gone and this one still filling, and a phone that lost signal inside it would have
    no app to open -- the one failure this worker exists to prevent.
    """
    worker = (
        resources.files("frontdoor_server").joinpath("app-sw.js").read_text(encoding="utf-8")
    )
    activate = worker.split('addEventListener("activate"', 1)[1].split("\n});", 1)[0]
    assert activate.index("clients") < activate.index("precached") < activate.index(
        "caches.delete"
    ), activate


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


def test_the_manifest_offers_an_icon_ios_and_android_will_actually_use():
    """180 alone is not enough, and not only for Android.

    Chrome will not offer Add to Home Screen without a 192, and wants 512 for the
    splash. iOS 16.4 and later PREFERS the manifest's icons over apple-touch-icon
    when a manifest is present, and falls back to a SCREENSHOT of the page when it
    finds none it can use — which is what the product owner saw on 2026-09-08 with
    the head tag and /app-icon.png both correct and serving.
    """
    manifest = json.loads(
        create_app().test_client().get("/app-manifest.json").get_data(as_text=True)
    )
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert "192x192" in sizes, "Chrome will not offer the install prompt"
    assert "512x512" in sizes, "no splash icon, and iOS may fall back to a screenshot"


def test_the_maskable_icon_is_its_own_file():
    """Android crops a maskable icon to the launcher's shape.

    Pointing the maskable entry at the full-bleed artwork loses the mark's corners
    to a circular mask, so it is a separate drawing with the mark inside the centre
    80% and the ground bleeding to every edge — not the same bytes under a second
    purpose, which is what shipped before.
    """
    manifest = json.loads(
        create_app().test_client().get("/app-manifest.json").get_data(as_text=True)
    )
    maskable = [i for i in manifest["icons"] if "maskable" in i["purpose"]]
    assert maskable, "no maskable icon"
    any_srcs = {i["src"] for i in manifest["icons"] if i["purpose"] == "any"}
    for icon in maskable:
        assert icon["src"] not in any_srcs, (
            f"{icon['src']} is served as both maskable and any; a full-bleed icon "
            "loses its corners to a circular mask"
        )


def test_every_manifest_icon_is_actually_served():
    """A manifest naming an icon the server does not have is worse than no icon:
    the browser tries, fails, and falls back without saying why."""
    client = create_app().test_client()
    manifest = json.loads(client.get("/app-manifest.json").get_data(as_text=True))
    for icon in manifest["icons"]:
        response = client.get(icon["src"])
        assert response.status_code == 200, f"{icon['src']} is {response.status_code}"
        assert response.mimetype == "image/png", icon["src"]


def test_the_staged_review_chips_name_only_criteria_the_engine_assesses():
    """The staged fallback is the likeliest demo path, and it was making a claim.

    `reviewChipsHTML` falls back to STAGED whenever there is no live result --
    camera denied, no camera, endpoint unreachable. It read step_free with a
    confidence of 86, so the review screen asserted "Step-free entry" as something
    the scan found. The engine does not assess step-free (#368) and "clear approach"
    is not one of the four criteria either.

    The four the engine returns are ramp_or_bevel, handrails,
    accessible_door_hardware and accessibility_signage; through EST_KEYMAP those are
    the chip keys ramp, handrails, hardware and signage. Nothing else may appear in
    the staged arrays, in either direction: a chip that claims more than the engine
    reads, or a "not seen" line naming something never looked for.
    """
    page = create_app().test_client().get("/app").get_data(as_text=True)
    allowed = {"ramp", "handrails", "hardware", "signage"}

    staged = re.search(r"const STAGED = \[(.*?)\];", page)
    assert staged, "STAGED not found in the served page"
    committed = set(re.findall(r"\['([a-z_]+)'", staged.group(1)))
    assert committed <= allowed, (
        f"staged review chips claim {sorted(committed - allowed)}, which the engine "
        "does not assess"
    )

    notseen = re.search(r"const STAGED_NOTSEEN = \[(.*?)\];", page)
    assert notseen, "STAGED_NOTSEEN not found; the staged path must show abstention"
    absent = set(re.findall(r"'([a-z_]+)'", notseen.group(1)))
    assert absent <= allowed, (
        f"staged 'not seen' line names {sorted(absent - allowed)}, which was never "
        "looked for"
    )
    assert committed and absent, (
        "the staged path must show both what the photograph supported and what was "
        "not seen -- the abstention is the product's argument"
    )
    assert not (committed & absent), "a criterion cannot be both committed and not seen"


# ---------------------------------------------------------------------------
# TICK-474 / #476 / #477 / #478: the product's feature vocabulary is the
# engine's feature vocabulary.
#
# The served page used to carry eight entrance features and render all eight
# identically -- chip, confidence dots, `sr-only` "confidence high", pin
# accessible name, list row, owner workspace, public-listing preview. Four of
# them (step_free_entry, clear_approach, door_width_adequate, auto_door_button)
# are not in frontdoor.screening.CRITERIA_KEYS: nothing assesses them, so every
# one of those renderings was a finding the engine never produced, on named
# real businesses.
#
# These tests read the SERVED page, because that is what a person meets, and
# they derive the allowed vocabulary from CRITERIA_KEYS rather than from a
# copy of it, so adding a criterion to the engine is the only way to widen
# what the product may say.
# ---------------------------------------------------------------------------

# Feature names the product may not print or announce. Every one of them was on
# the deployed app when this was filed.
UNASSESSED_FEATURE_PROSE = (
    "step-free",
    "step free",
    "wide door",
    "clear approach",
    "auto-door",
    "auto door",
    "automatic door",
    "door button",
)


def _served_page():
    return create_app().test_client().get("/app").get_data(as_text=True)


def _decl(page, opening, closing="};"):
    """The body of a single declaration in the served page's script."""
    match = re.search(
        re.escape(opening) + r"(.*?)" + re.escape(closing), page, re.DOTALL
    )
    assert match, f"{opening!r} not found in the served page"
    return match.group(1)


def _chip_vocabulary(page):
    """The chip keys the four engine criteria map to, read off the page itself.

    EST_KEYMAP is the page's own translation of the /screen contract, so its
    keys must BE CRITERIA_KEYS and its values are the only feature keys any
    other structure on the page may name.
    """
    from frontdoor.screening import CRITERIA_KEYS

    pairs = re.findall(r"([a-z_]+):'([a-z_]+)'", _decl(page, "const EST_KEYMAP = {"))
    assert {key for key, _ in pairs} == set(CRITERIA_KEYS), (
        "EST_KEYMAP no longer covers exactly the criteria the engine assesses; "
        "the page and frontdoor.screening have diverged"
    )
    return {chip for _, chip in pairs}


def test_the_feature_vocabulary_is_exactly_the_criteria_the_engine_assesses():
    """DOOR_KEYMAP and FEATS are the choke points every feature rendering passes.

    `featsOf()` reads DOOR_KEYMAP, and every chip row, "not yet seen" list and
    accessible name is built from FEATS. Trimming both to the four is what makes
    the fix data-shaped: the next dataset can hold whatever it likes and still
    cannot surface a feature nothing assessed.
    """
    page = _served_page()
    chips = _chip_vocabulary(page)

    door = dict(re.findall(r"([a-z_]+):'([a-z_]+)'", _decl(page, "const DOOR_KEYMAP = {")))
    assert set(door.values()) == chips, (
        f"DOOR_KEYMAP maps to {sorted(set(door.values()) - chips)} beyond the "
        "criteria the engine assesses"
    )

    feats = set(re.findall(r"^\s*([a-z_]+):\{", _decl(page, "const FEATS = {"), re.M))
    assert feats == chips, (
        f"FEATS names {sorted(feats - chips)}, which the engine does not assess; "
        "every 'not yet seen' list on the product is built from Object.keys(FEATS)"
    )
    assert "const unknown = Object.keys(FEATS).filter(" in page, (
        "the card's 'not yet seen' list must stay derived from FEATS, so trimming "
        "FEATS is what keeps the invitation to scan honest (#478)"
    )


def test_no_seeded_place_carries_a_criterion_the_engine_does_not_assess():
    """The shipped map data itself, not only what is rendered from it.

    Twelve pilot doors carried eight criteria each and nine of them published a
    step-free finding with a confidence. The page does not carry those fields at
    all now, so no rendering path that is added later can reach them either.
    """
    from frontdoor.screening import CRITERIA_KEYS

    page = _served_page()
    door_keys = set(
        dict(re.findall(r"([a-z_]+):'([a-z_]+)'", _decl(page, "const DOOR_KEYMAP = {")))
    )
    data = json.loads(_decl(page, "const DATA = ", ";\n"))

    assert data["doors"], "the seeded pilot doors are missing from the page"
    for door in data["doors"]:
        extra = set(door["crit"]) - door_keys
        assert not extra, (
            f"{door['name']} ({door['id']}) publishes {sorted(extra)}, which the "
            "engine does not assess"
        )
    for place in data["est"]:
        extra = set(place["crit"]) - set(CRITERIA_KEYS)
        assert not extra, (
            f"{place['name']} publishes {sorted(extra)}, which the engine does "
            "not assess"
        )


def test_no_filter_persona_or_owner_row_names_an_unassessed_criterion():
    """The controls that say what the map can answer for every pin.

    Offering a filter is a stronger claim than naming a feature: it says the map
    holds this answer everywhere. The personas are stronger still -- they are the
    input to the match verdict -- so they are checked in both languages, the keys
    they score on and the prose they advertise.
    """
    page = _served_page()
    chips = _chip_vocabulary(page)

    filt = set(re.findall(r"\['([a-z_]+)',", _decl(page, "const FILT_FEATS=[", "];")))
    assert filt <= chips, (
        f"the Filters sheet offers {sorted(filt - chips)}, which the map cannot answer"
    )

    personas = _decl(page, "const PERSONAS = {")
    for name, sub, crit in re.findall(
        r"^\s*([a-z]+):\{label:.*?sub:'([^']*)'.*?crit:\[([^\]]*)\]", personas, re.M
    ):
        keys = set(re.findall(r"'([a-z_]+)'", crit))
        assert keys <= chips, (
            f"the {name} persona matches on {sorted(keys - chips)}, which the "
            "engine does not assess"
        )
        assert keys, f"the {name} persona scores on nothing at all"
        for word in UNASSESSED_FEATURE_PROSE:
            assert word not in sub.lower(), (
                f"the {name} persona advertises {word!r}, which the engine does "
                "not assess"
            )

    owner_keys = set(re.findall(r"\{k:'([a-z_]+)'", _decl(page, "const OW_FEATURES = [", "];")))
    assert owner_keys == chips, (
        f"the owner workspace edits {sorted(owner_keys - chips)}, and its rows "
        'carry an aria-label of "seen on-site"'
    )
    owner_crit = set(
        chip for _, chip in re.findall(r"([a-z_]+):'([a-z_]+)'", _decl(page, "const OW_CRIT = {"))
    )
    door_keys = set(
        dict(re.findall(r"([a-z_]+):'([a-z_]+)'", _decl(page, "const DOOR_KEYMAP = {")))
    )
    assert owner_crit <= door_keys, (
        f"publishing an owner update writes {sorted(owner_crit - door_keys)} onto "
        "the place record, where nothing can render it honestly"
    )


def test_the_needs_match_has_no_cross_criterion_substitution():
    """`satOf()` is the closest this product comes to saying a place is accessible.

    It carried one substitution -- a step-free observation satisfying the ramp
    need -- which could take a card to "Good match, 3 of 3 needs" for a
    wheelchair user on a field the engine never produced. A need is satisfied by
    the criterion it names or it is not satisfied; an unmet need already renders
    as "not yet seen".
    """
    page = _served_page()
    body = _decl(page, "function satOf(p, crit){", "\n}")
    assert "p.f.step_free" not in body, (
        "satOf() still lets a field outside the four satisfy a need"
    )
    assert not re.search(r"if\s*\(\s*ck\s*===", body), (
        "satOf() special-cases a criterion; a match must be over the four, with "
        "no substitution in either direction"
    )
    assert len(re.findall(r"\bok\b\s*=", body)) == 1, (
        "satOf() decides satisfaction more than once, which is how the "
        "substitution got in"
    )


def test_the_pages_own_prose_names_no_feature_the_engine_does_not_assess():
    """The hand-written sentences, which no data test and no render test reaches.

    Profile > Accessibility > Preview was static markup asserting that a scan saw
    step-free entry at a named real business (#476). It is prose typed into the
    page, so only reading the page finds it. Scripts, styles and comments are
    stripped: what is left is what a person can read on the screen.
    """
    page = _served_page()
    visible = re.sub(r"<script\b.*?</script>", " ", page, flags=re.DOTALL | re.IGNORECASE)
    visible = re.sub(r"<style\b.*?</style>", " ", visible, flags=re.DOTALL | re.IGNORECASE)
    visible = re.sub(r"<!--.*?-->", " ", visible, flags=re.DOTALL)
    lowered = visible.lower()
    for word in UNASSESSED_FEATURE_PROSE:
        assert word not in lowered, (
            f"the page's own markup says {word!r}; the engine assesses ramp or "
            "bevel, handrails, accessible door hardware and accessibility signage"
        )
def test_the_staged_review_path_renders_its_abstention_line():
    """Two confident chips and nothing else reads as a complete answer.

    #471 removed step_free from STAGED and added a "Not seen this time" line -- but
    only to the design source's copy of `reviewChipsHTML`, which the port replaces
    wholesale with `tools/app_wiring/review.js`. The constant travelled; the
    rendering did not. Production served two chips and stopped, and it took driving
    the deployed page to notice.

    The abstention is the product's argument, so the staged path has to show both
    halves the way the live branch does. This reads the SERVED page, because that is
    where the previous fix failed to arrive.
    """
    page = create_app().test_client().get("/app").get_data(as_text=True)
    branch = page[page.index("if(liveSimulated()){"):]
    branch = branch[:branch.index("if(chipsOnly) return '';")]
    assert "STAGED_NOTSEEN" in branch, (
        "the staged branch of reviewChipsHTML does not render STAGED_NOTSEEN; the "
        "review screen will show committed chips with no abstention beside them"
    )
    assert "vc-notseen" in branch, (
        "the staged abstention must use the same class as the live branch's, or it "
        "is a different object saying the same thing"
    )


def test_the_processing_screen_does_not_promise_eight_seconds_for_a_live_scan():
    """Eight seconds is this screen's animation, not a scan.

    `PROC_TOTAL` is 7,360ms and the caption was a rounding of it. Measured against
    production at the size `captureFrame()` uploads, the model call runs about 8
    seconds and the round trip a person watches runs about 19 -- so the screen
    promised eight and delivered nineteen, and the countdown beside it reached zero
    at second eight and sat there for the remaining eleven.

    A staged run really does take about eight seconds, because it waits for nothing.
    A live one does not. This pins that the screen says which it is:

    * nothing painted before JS runs names a duration, because at that moment the
      page cannot know which kind of run this is;
    * the caption is chosen from whether the request is still out;
    * the countdown stops claiming a number rather than displaying zero.

    Read off the SERVED page: the settle that drives the caption lives in a wiring
    fragment, and editing only the design source would have changed nothing a phone
    ever runs.
    """
    page = create_app().test_client().get("/app").get_data(as_text=True)

    markup = page[:page.index("<script")]
    assert "Usually under 8 seconds" not in markup, (
        "the pre-JS caption names a duration before the page can know whether this "
        "run is waiting on a server"
    )

    assert "function procCaption()" in page, "procCaption is not in the served page"
    caption = page[page.index("function procCaption()"):]
    caption = caption[:caption.index("function applyGate2()")]
    assert "liveUpload" in caption and "liveSettled" in caption, (
        "the caption does not branch on whether the request is still out, so it says "
        "the same thing for a staged run and a live one"
    )
    assert "half a minute" in caption, (
        "no live-scan wording found; the live branch must not promise eight seconds"
    )

    assert "if(typeof procCaption==='function') procCaption()" in page, (
        "nothing refreshes the caption when the request lands, so the screen keeps "
        "saying it is waiting after it has stopped"
    )


# --- the locate control asks the phone, and says what it was told ------------
#
# The design source's handler never called navigator.geolocation. It reset the pan,
# returned the frame to the pilot bbox, and raised a toast saying the map was now
# centred on you, naming a downtown Austin intersection -- to whoever pressed it,
# wherever they were. A control that does nothing and a false statement in one line.
#
# There is no JavaScript runner in this suite, so these read the SERVED page: the
# handler lives in a wiring fragment (tools/app_wiring/locate.js) and editing only the
# design source would change nothing a phone ever runs.


def locate_handler(html):
    """The body of locateMe(), which is where the asking is decided."""
    body = html.split("function locateMe(){", 1)[1]
    return body[: body.index("\n}")]


def test_the_locate_control_asks_the_browser_where_the_phone_is():
    html = page().get_data(as_text=True)
    assert "function locateMe(){" in html
    assert "navigator.geolocation.getCurrentPosition(onGeoFix, onGeoFail, GEO_OPTS);" in html
    assert "document.getElementById('locate-btn').addEventListener('click', locateMe);" in html
    # ...and the fixed-point claim is gone from the page, in either spelling
    assert "Centered on you \\u00b7 2nd & Colorado" not in html
    assert "Centered on you · 2nd & Colorado" not in html


def test_centred_on_you_is_said_only_where_the_map_is_centred_on_a_real_fix():
    """The one toast that claims a centre sits inside the one branch that has one."""
    html = page().get_data(as_text=True)
    claims = [i for i in range(len(html)) if html.startswith("toast('Centered on you", i)]
    assert len(claims) == 1, "more than one place claims the map is centred on you"
    branch = html.rindex("if(inPilot(youFix)){", 0, claims[0])
    assert "else" not in html[branch:claims[0]], (
        "the 'Centered on you' toast is not inside the in-the-pilot-area branch"
    )


def test_a_denied_permission_is_an_answer_and_is_not_asked_again():
    handler = locate_handler(page().get_data(as_text=True))
    denied = handler.index("if(geoState==='denied')")
    asks = handler.index("navigator.geolocation.getCurrentPosition")
    assert denied < asks, "a denied permission falls through and re-prompts on every tap"
    assert "return;" in handler[denied:asks]


def test_denied_unavailable_and_timed_out_are_three_different_answers():
    html = page().get_data(as_text=True)
    said = [
        "Location is off for this site, so the map has not moved",
        "Finding your location took too long, so the map has not moved.",
        "Your device could not work out where it is, so the map has not moved.",
        "This page is not on a secure connection, so the browser will not share",
        "This browser cannot share a location, so the map has not moved",
    ]
    for sentence in said:
        assert sentence in html, f"no wording for one of the outcomes: {sentence!r}"
    assert len(set(said)) == len(said)


def test_a_failed_attempt_is_announced_as_an_error_not_only_toasted():
    html = page().get_data(as_text=True)
    assert "el.setAttribute('role','alert');" in html
    stopped = html.split("function geoStopped(state, short, why){", 1)[1]
    stopped = stopped[: stopped.index("\n}")]
    assert "toast(short);" in stopped and "geoAlert(why);" in stopped, (
        "a failed attempt does not reach the alert region"
    )
    # ...and every failing branch goes through it rather than only raising a toast
    fail = html.split("function onGeoFail(err){", 1)[1]
    fail = fail[: fail.index("\n}")]
    assert fail.count("geoStopped(") + fail.count("sayDenied()") == 3
    assert "toast(" not in fail, "a failure branch toasts without announcing"


def test_a_failure_clears_what_the_last_fix_left_on_the_map():
    """The mark and the out-of-area invite outlive their fix unless this runs."""
    html = page().get_data(as_text=True)
    stopped = html.split("function geoStopped(state, short, why){", 1)[1]
    stopped = stopped[: stopped.index("\n}")]
    assert "youOutside=false;" in stopped
    assert "renderMap();" in stopped


def test_a_fix_outside_the_pilot_area_says_what_we_have_mapped_not_what_is_there():
    """The invite may say we have nothing here. It may never judge the places here."""
    html = page().get_data(as_text=True)
    assert "EntryMap has not mapped your area yet" in html
    invite = html.split("function paintEmptyInvite(noPins){", 1)[1]
    invite = invite[: invite.index("\n}")]
    assert "it says nothing about the places around you" in invite
    for verdict in ("not accessible", "no accessible", "inaccessible", "fails", "unsuitable"):
        assert verdict not in invite.lower(), f"the invite passes a verdict: {verdict!r}"


def test_the_you_are_here_mark_is_drawn_only_where_a_real_fix_is():
    html = page().get_data(as_text=True)
    assert "function placeYouHere(){" in html
    mark = html.split("function placeYouHere(){", 1)[1]
    mark = mark[: mark.index("\n}")]
    assert "geoState!=='ok'" in mark, "the mark does not check that a fix was granted"
    assert "el.hidden = !on;" in mark, "the mark is not hidden when the fix is off-frame"
    # every re-render re-places it, so a zoom or a pan cannot leave it on a stale point
    assert "  paintEmptyInvite(shown.length===0);\n  placeYouHere();" in html
    assert "#you-here{" in html


def test_the_locate_control_is_named_for_what_it_does_now():
    html = page().get_data(as_text=True)
    names = html.split("const LOCATE_NAME = {", 1)[1]
    names = names[: names.index("};")]
    assert "denied:" in names and "unavailable:" in names
    assert "Why your location is not shown" in names
    assert "locateBtn.setAttribute('aria-label'," in html
