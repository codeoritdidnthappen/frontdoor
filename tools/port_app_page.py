#!/usr/bin/env python
"""Port the EntryMap design source into the page this service serves at GET /app.

WHY THIS EXISTS
---------------
The app page has two authors. Its look, copy and interaction come from a design source
that is worked on separately and changes every design round. Its *wiring* -- the calls
to this service's own endpoints, and the honest handling of what they answer -- belongs
to this repository, is covered by tests here, and must survive every one of those
rounds. Hand-copying between the two lost rounds 2 to 7 of design work and, in the other
direction, keeps putting a critical defect back (see WIRING_REQUIRED below).

So the page is not edited. It is *built*:

    design-source/entrymap-app.html          the design, verbatim, as committed here
  + tools/app_wiring/*                       this service's wiring, as fragments
  = src/frontdoor_server/app.html            the served page

Run it with no arguments to rebuild the page from the committed design source:

    python tools/port_app_page.py

When a new design round lands, replace the committed design source and rebuild in one
step:

    python tools/port_app_page.py --design-source <the new design source> --update-source

WHY THE DESIGN SOURCE IS COMMITTED HERE
---------------------------------------
The design source is produced elsewhere, so the alternative was to take its path as a
required argument. A committed copy was chosen instead because it makes the build
*reproducible*: CI, this repository's tests, and anyone cloning it can rebuild the page
byte-for-byte and see the port's tests exercise the real ops against the real design,
not a synthetic fixture. `--design-source` still accepts a fresh copy, and
`--update-source` refreshes the committed one, so nothing has to be copied by hand.

HOW THE TRANSFORMATION IS DEFINED
---------------------------------
OPS below is an ordered list of anchored edits. Each names the wiring it applies and why
that wiring cannot simply live in the design. Anchors are chosen to be the least
design-volatile text available -- structural section comments and element ids rather
than prose or styling -- and every anchor must match EXACTLY ONCE. A design change that
moves an anchor fails the port loudly instead of silently dropping the wiring behind it.
After the ops run, WIRING_REQUIRED and WIRING_FORBIDDEN are checked against the output,
so no op can quietly stop doing its job.

The build is a pure function of (design source, fragments): running it twice produces
identical bytes, and a change in the design source flows through with no hand editing.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DESIGN_SOURCE = REPO_ROOT / "design-source" / "entrymap-app.html"
WIRING_DIR = REPO_ROOT / "tools" / "app_wiring"
SERVED_PAGE = REPO_ROOT / "src" / "frontdoor_server" / "app.html"

# Kinds:
#   "insert_before" / "insert_after"  put the fragment beside a unique anchor
#   "replace"                         swap a unique anchor for the fragment
#   "replace_region"                  swap everything from `anchor` up to (not including)
#                                     `until` -- for wiring that owns a whole section
@dataclass(frozen=True)
class Op:
    name: str
    why: str
    kind: str
    anchor: str
    fragment: str | None = None
    until: str | None = None
    replacement: str | None = None  # inline replacement, for one-line edits


OPS: list[Op] = [
    Op(
        name="banner",
        why="the served page is generated; say so at the top so nobody hand-edits it",
        kind="insert_after",
        anchor="<!DOCTYPE html>\n",
        fragment="banner.html",
    ),
    Op(
        name="head",
        why=(
            "the installable-app head: the icon served from this origin (iOS ignores a "
            "data: URI and a cross-origin icon is not ours to depend on), the web app "
            "manifest, the Apple standalone meta tags, and the page title the tests pin"
        ),
        kind="replace_region",
        anchor='<link rel="apple-touch-icon"',
        # The region ends at the type comment, so the two CDN preconnects the design
        # source carries between the title and that comment are inside it and go. The
        # stylesheet link that follows the comment is the self_hosted_type op below.
        until='<!-- Round 4 type.',
        fragment="head.html",
    ),
    Op(
        name="self_hosted_type",
        why=(
            "the two families are served from this origin, not from a CDN. The design "
            "source is worked on in a browser with a network and links the CDN "
            "stylesheet; this page is installable, is meant to launch with no signal, "
            "and may not disclose a visitor to a third party on every load. This was a "
            "hand edit to the committed design source until Rounds 10-11 -- which a "
            "refresh from a new design round silently reverts -- so it is an op now"
        ),
        kind="replace",
        anchor=(
            '<link href="https://fonts.googleapis.com/css2?'
            "family=Atkinson+Hyperlegible+Next:ital,wght@0,200..800;1,200..800"
            '&family=Nunito+Sans:wght@700..900&display=swap" rel="stylesheet">\n'
            "<style>\n"
        ),
        fragment="type-self-hosted.html",
    ),
    Op(
        name="wiring_css",
        why="styles for the two elements the wiring adds: the entrance field and the simulated tag",
        kind="insert_before",
        # The anchor is the close of the one stylesheet, not `</style>\n</head>`: Round 8
        # put a script between the two (the reduced-motion floor, which has to run before
        # first paint and so cannot move down the document). The wiring's styles belong at
        # the end of the stylesheet either way, and `</style>` is the structural mark for
        # that -- there is exactly one of it in the design source.
        anchor="\n</style>\n",
        fragment="wiring.css",
    ),
    Op(
        name="scan_target",
        why=(
            "POST /screen/publish needs to know which entrance a scan is for, so the "
            "primer says what this run will publish against rather than a fixed street"
        ),
        kind="replace",
        anchor='        <div class="scan-target">Scanning near W 3rd St &middot; <b id="scan-target-name"></b></div>\n',
        fragment="scan-target.html",
    ),
    Op(
        name="entrance_field",
        why=(
            "the publish contract wants place_id, or lat + lng + name; a scan started "
            "from the map has no card to take a name from, so the review screen asks"
        ),
        kind="insert_after",
        anchor='        <div class="quarantine-note" id="quarantine-note"></div>\n',
        fragment="entrance-field.html",
    ),
    Op(
        name="claim_no_typed_phone",
        why=(
            "a typed number is input, never authority: /claim verifies on the phone the "
            "listing itself carries, so the form must not collect one (tests/test_claims.py)"
        ),
        kind="replace",
        anchor=(
            '        <div class="field">\n'
            '          <label for="claim-phone">Business phone</label>\n'
            '          <input type="tel" id="claim-phone" placeholder="(512) 555-0137" autocomplete="off">\n'
            "        </div>\n"
        ),
        replacement="",
    ),
    Op(
        name="incentives_wording",
        why=(
            "this service never offers tax advice, in any sentence, negated or not "
            "(the incentives guardrail pinned by tests/test_claims.py)"
        ),
        kind="replace",
        anchor="toast('Section 44 / 190 explainer \\u2014 not tax advice')",
        replacement="toast('Section 44 / 190 explainer \\u2014 ask your accountant')",
    ),
    Op(
        name="claim_workspace",
        why=(
            "the screen GET /claim/<id>/workspace fills, and the two controls that write "
            "back to it; the design source's owner screens are not wired to the service"
        ),
        kind="insert_before",
        anchor="    <!-- ================= OWNER WORKSPACE (39-44) ================= -->",
        fragment="claim-workspace.html",
    ),
    Op(
        name="live_screening",
        why=(
            "the whole same-origin screening block: relative /screen, /screen/publish, "
            "/scan/photo/ and /claim URLs, the anonymous contributor token, the place "
            "reference, and the rule that only the absence of a server -- never a failed "
            "request -- selects the simulated pipeline"
        ),
        kind="replace_region",
        anchor="/* ===================== live camera + live screening (demo insurance) =====================",
        until="/* ===================== scan flow ===================== */",
        fragment="live-screening.js",
    ),
    Op(
        name="scan_entry",
        why=(
            "startScan carries where the scan will publish (from a card, or from the "
            "phone's fix), asks for that fix, and marks an owner's attested capture"
        ),
        kind="replace_region",
        anchor="function startScan(){",
        # TICK-490 rewrote the paragraph this used to point at, which is exactly the
        # failure this file's docstring warns about. The anchor is now the one line of
        # it that is a heading rather than a description, so re-describing the beats
        # below it cannot break the build again.
        until="/* ---- processing.\n",
        fragment="scan-entry.js",
    ),
    Op(
        name="card_scan_from_card",
        why="a scan launched from a place card publishes against that place's id",
        kind="replace",
        anchor=(
            "  act('scan-this',()=>{scanTarget=p; closeSheets(); startScan();});\n"
            "  act('recheck',()=>{scanTarget=p; closeSheets(); startScan();});"
        ),
        replacement=(
            "  act('scan-this',()=>{scanTarget=p; closeSheets(); startScan(true);});\n"
            "  act('recheck',()=>{scanTarget=p; closeSheets(); startScan(true);});"
        ),
    ),
    Op(
        name="review",
        why=(
            "the review screen reports what actually happened: server verdicts, staged "
            "examples where there is no server, or -- for a real request that failed -- "
            "a scan that could not be completed, with nothing claimed about the photo"
        ),
        kind="replace_region",
        anchor="function reviewChipsHTML(chipsOnly){",
        until="/* /screen criteria keys -> the door-scan crit vocabulary featsOf() reads */",
        fragment="review.js",
    ),
    Op(
        name="publish",
        why=(
            "POST /screen/publish and its four outcomes (published, quarantined, the 503 "
            "assessed-but-not-stored hold, and an honest failure), the pin upgrade that "
            "only a run the server read may reach, and a done screen told its outcome"
        ),
        kind="replace_region",
        anchor="document.getElementById('btn-publish').addEventListener('click',()=>{",
        until="/* ===================== onboarding (guest-first; every step skippable) ===================== */",
        fragment="publish.js",
    ),
    Op(
        name="claim",
        why="the real /claim endpoints behind the design source's stubbed claim flow",
        kind="replace_region",
        anchor="/* ===================== owner claim flow (stub; entrance-level, proof-of-control honest) ===================== */",
        until="/* ===================== owner workspace (39-44) =====================",
        fragment="claim.js",
    ),
    Op(
        name="camera_roll_attest",
        why="a camera-roll photo is published as such; it can never carry an owner's attestation",
        kind="replace",
        anchor=(
            "  const file=libInput.files && libInput.files[0];\n"
            "  if(!file) return;\n"
        ),
        replacement=(
            "  const file=libInput.files && libInput.files[0];\n"
            "  if(!file) return;\n"
            "  fromLibrary=true;\n"
        ),
    ),
    Op(
        name="quiet_console",
        why=(
            "the design source times the processing beats to its console; the served page "
            "is the product, and a console that only carries real problems is one a "
            "problem can be seen in"
        ),
        kind="replace",
        anchor="function procLog(t0,label){ console.log(`[proc] ${label} @ ${((performance.now()-t0)/1000).toFixed(2)}s`); }",
        replacement="function procLog(t0,label){}   /* the design source's beat timing; not for the served page */",
    ),
    Op(
        name="corrections_from_server",
        why=(
            "the Contributions tab must show what the server holds, not a local echo: the "
            "design seeds three worked examples and the send button pushed a fourth into "
            "the same array, which is exactly what made an unsent note look received "
            "(TICK-387). The list is read from GET /correct/mine instead"
        ),
        kind="replace_region",
        anchor=(
            "/* session-local, seeded with three worked examples so the Corrections tab "
            "has history to show */\n"
        ),
        until=(
            "cNote.addEventListener('input',()=>document.getElementById('correct-count')"
            ".textContent=cNote.value.length);"
        ),
        fragment="corrections.js",
    ),
    Op(
        name="correct_send",
        why=(
            "'Send suggestion' posts to POST /correct and a failure says so rather than "
            "reaching the confirmation screen; the design's handler pushed the note into "
            "a JavaScript array and always succeeded"
        ),
        kind="replace_region",
        anchor="document.getElementById('btn-correct-send').addEventListener('click',()=>{",
        until="document.getElementById('corr-done-back').addEventListener('click',()=>{",
        fragment="correct-send.js",
    ),
    Op(
        name="corr_done_promises_what_the_server_does",
        why=(
            "the confirmation screen promised the note becomes a dated source on the "
            "receipt. It does not: a correction reaches a review queue and changes no "
            "verdict. Same rule as the scan path -- a screen may only claim what the "
            "server actually does"
        ),
        kind="replace",
        anchor=(
            '            <li><span class="nl-dot"><span class="ic" data-icon="clock" '
            'data-size="12" aria-hidden="true"></span></span><span>Your note becomes a '
            "<b>dated source</b> on this entrance's receipt &mdash; \"Neighbor "
            'correction &middot; today.\"</span></li>\n'
        ),
        replacement=(
            '            <li><span class="nl-dot"><span class="ic" data-icon="clock" '
            'data-size="12" aria-hidden="true"></span></span><span>Your note joins a '
            '<b>review queue</b> a person works through. Nothing on the map changes until '
            "it has been read.</span></li>\n"
        ),
    ),
    Op(
        name="corr_done_no_notification_promise",
        why=(
            "nothing notifies a contributor yet (#387 puts it out of scope), so the "
            "screen says where to look instead of promising a message that never comes"
        ),
        kind="replace",
        anchor=(
            '            <li><span class="nl-dot"><span class="ic" data-icon="bell" '
            "data-size=\"12\" aria-hidden=\"true\"></span></span><span>You'll hear back only "
            'if <b>"A correction of yours gets a response"</b> is on in Notifications.'
            "</span></li>\n"
        ),
        replacement=(
            '            <li><span class="nl-dot"><span class="ic" data-icon="bell" '
            'data-size="12" aria-hidden="true"></span></span><span>Its status is under '
            "<b>My corrections</b> &mdash; in review, then reviewed. We do not send a "
            "message about it yet.</span></li>\n"
        ),
    ),
    Op(
        name="corr_row_says_what_happens",
        why=(
            "tapping a correction said it stays on the receipt as its own dated source. It "
            "does not: it reaches a review queue and changes nothing until a person reads "
            "it. Same rule as the confirmation screen above"
        ),
        kind="replace",
        anchor="toast('Each correction stays on the receipt as its own dated source')",
        replacement=(
            "toast('Corrections stay human \u2014 a person reads every note before "
            "anything changes')"
        ),
    ),
    Op(
        name="contrib_tab_reads_the_server",
        why="opening My contributions asks the server for the real status of each note",
        kind="replace",
        anchor=(
            "  if(id==='screen-profile'){ renderSaved(); renderCorrections(); renderYourScans(); }\n"
            "  if(id==='screen-contrib') renderYourScans();\n"
        ),
        replacement=(
            "  if(id==='screen-profile'){ renderSaved(); renderCorrections(); renderYourScans(); loadMyCorrections(); }\n"
            "  if(id==='screen-contrib'){ renderYourScans(); loadMyCorrections(); }\n"
        ),
    ),
    Op(
        name="relook_nudge",
        why=(
            "the ONE thing a corroborated correction may change is freshness: /map/data "
            "carries needs_relook, and the card's existing 'Could you take another look?' "
            "nudge is where it surfaces. Never a verdict, never a negative -- the nudge "
            "asks for a photograph and says nothing about the door"
        ),
        kind="replace",
        anchor=(
            "  /* re-check nudge: stale estimates ask gently -- age is context, not failure */\n"
            "  let nudge='';\n"
            "  if(p.tier==='est' && aged){\n"
            '    nudge = `<div class="nudge">\n'
            '      <div class="n-h">Could you take another look?</div>\n'
            "      <span class=\"n-age\">${iconSVG('clock',13,'var(--amber-ink)')} Estimated ${ageLabel(p.date)}</span>\n"
        ),
        replacement=(
            "  /* re-check nudge: stale estimates ask gently -- age is context, not failure.\n"
            "     TICK-387: a corroborated correction can ask for one too. Freshness only --\n"
            "     the pin, its tier and every check on it are exactly what they were. */\n"
            "  let nudge='';\n"
            "  if((p.tier==='est' && aged) || p.relook){\n"
            '    nudge = `<div class="nudge">\n'
            '      <div class="n-h">Could you take another look?</div>\n'
            "      <span class=\"n-age\">${iconSVG('clock',13,'var(--amber-ink)')} ${p.relook?'Neighbors asked for a fresh look':'Estimated '+ageLabel(p.date)}</span>\n"
        ),
    ),
    Op(
        name="locate_real_fix",
        why=(
            "the locate control asks navigator.geolocation where the phone is, instead "
            "of panning to the pilot frame and asserting 'Centered on you' to whoever "
            "pressed it. Granted, denied, unavailable, timed out and a fix outside the "
            "pilot area are five different answers and are reported as five different "
            "things; the map is only ever claimed to be centred on a real fix. The "
            "region reaches the empty-area invite because that invite now has two "
            "causes -- an emptying filter and a fix we have mapped nothing near -- and "
            "its copy and its second button have to say which. This is wiring rather "
            "than design because the permission is granted to this origin, its four "
            "failure modes are conditions this repository has to report honestly, and "
            "the false one-liner is still in the prototype the design source is "
            "refreshed from: as an op a refresh either carries this or fails loudly"
        ),
        kind="replace_region",
        anchor=(
            "document.getElementById('locate-btn').addEventListener('click',()=>{ "
            "panMap(0); setZoom(false, null); "
            "toast('Centered on you \\u00b7 2nd & Colorado'); });\n"
        ),
        until="/* ===================== trust sheet ===================== */",
        fragment="locate.js",
    ),
    Op(
        name="map_empty_cause",
        why=(
            "renderMap decided the invite's visibility from one fact (no pins) and the "
            "invite now has two causes, so the choice moves to paintEmptyInvite, which "
            "says which one is open. The same call re-places the 'you are here' mark: "
            "every zoom, pan, filter and re-render moves the ground under it, and a "
            "mark left at a stale point is the same class of defect as the toast this "
            "change removes"
        ),
        kind="replace",
        anchor=(
            "  /* empty-area invite: filtering (or panning) to zero pins invites, never shames */\n"
            "  const me=document.getElementById('map-empty');\n"
            "  if(me) me.classList.toggle('on', shown.length===0);\n"
        ),
        replacement=(
            "  /* empty-area invite: filtering (or panning) to zero pins invites, never\n"
            "     shames -- and a real location fix outside the pilot area opens the same\n"
            "     invite with its own words (tools/app_wiring/locate.js). */\n"
            "  paintEmptyInvite(shown.length===0);\n"
            "  placeYouHere();\n"
        ),
    ),
    Op(
        name="loc_toggle_real",
        why=(
            "TICK-488, the locate button's defect on the Settings switch. #loc-toggle "
            "ships as `class=\"toggle on\" aria-checked=\"true\"` and its handler flipped "
            "it on tap and toasted 'Location on while using' -- so the app claimed a "
            "permission, visually and to a screen reader, that nothing had asked for. "
            "The switch is a claim about a permission, so its state is now a function "
            "of the permission: paintLocToggle() in locate.js paints it from what the "
            "browser actually said, repaints it away from the markup's opening claim as "
            "soon as the page runs, and tapping it asks through the shared askGeo() "
            "instead of asserting. Dropping the design source's listener here is what "
            "stops two handlers writing the same switch"
        ),
        kind="replace",
        anchor=(
            "const loct=document.getElementById('loc-toggle');\n"
            "loct.addEventListener('click',()=>{\n"
            "  const on=!loct.classList.contains('on');\n"
            "  loct.classList.toggle('on',on); loct.setAttribute('aria-checked',on);\n"
            "  toast(on?'Location on while using':'No problem \\u2014 search the map instead');\n"
            "});\n"
        ),
        replacement=(
            "/* The Location switch is painted and handled by paintLocToggle() and the\n"
            "   listener beside it in tools/app_wiring/locate.js, from the permission the\n"
            "   browser actually granted. The design source's handler flipped it on tap and\n"
            "   said location was on without asking, which is TICK-488 on this element. */\n"
        ),
    ),
    Op(
        name="onboarding_location_real",
        why=(
            "TICK-488. Onboarding's 'Allow location' flipped #loc-toggle on, set "
            "aria-checked='true' and advanced, without ever calling "
            "navigator.geolocation: nothing asked, no permission granted, and the "
            "interface then told a new user -- visually and to a screen reader -- that "
            "location was allowed. It is #487's defect one step earlier and about a "
            "permission rather than a place. The step now asks through the SHARED "
            "askGeo() in locate.js, so the eight outcomes are branched on in one place "
            "and only the wording differs, and the switch is never written by the tap. "
            "Onboarding is skippable, so no answer blocks the step: each says what will "
            "be different without a location and names the way onward, and a denial is "
            "accepted rather than asked again. Wiring rather than design for the same "
            "reason as locate: the false two-liner is still in the prototype the design "
            "source is refreshed from, so as an op a refresh either carries this or "
            "fails the port loudly"
        ),
        kind="replace_region",
        anchor="document.getElementById('ob-allow-loc').addEventListener('click',()=>{\n",
        until=(
            "document.getElementById('ob-needs-back')"
            ".addEventListener('click',()=>showScreen('ob-location'));"
        ),
        fragment="onboarding-location.js",
    ),
    Op(
        name="map_data",
        why="GET /map/data merged into the embedded pins, so the map shows published scans",
        kind="insert_before",
        anchor="/* ===================== boot ===================== */",
        fragment="map-data.js",
    ),
    Op(
        name="boot_live_map",
        why="ask the server for the live map once the embedded pins are drawn",
        kind="replace",
        anchor="\nrenderMap();\napplyPrefs();\n",
        replacement="\nrenderMap();\nloadLiveMap();\napplyPrefs();\n",
    ),
    Op(
        name="service_worker",
        why="registering the worker is what makes the page installable to a home screen",
        kind="insert_before",
        anchor="</body>\n</html>",
        fragment="service-worker.html",
    ),
]

# Every one of these must be in the built page. They are the wiring the port exists to
# carry, expressed as the exact text this repository's tests and the server contract
# depend on. A silent regression in any op fails the build here, not in review.
WIRING_REQUIRED: list[str] = [
    "<title>EntryMap</title>",
    'rel="apple-touch-icon" sizes="180x180" href="/app-icon.png"',
    '<meta name="apple-mobile-web-app-title" content="EntryMap">',
    '<meta name="apple-mobile-web-app-capable" content="yes">',
    '<link rel="manifest" href="/app-manifest.json">',
    'navigator.serviceWorker.register("/app-sw.js")',
    "const SCREEN_API = '/screen';",
    "const PUBLISH_API = '/screen/publish';",
    "const PHOTO_API = '/scan/photo/';",
    "const CLAIM_API = '/claim';",
    "fetch('/map/data'",
    "X-Frontdoor-Contributor",
    "localStorage.getItem(KEY)",
    "fd.append('images', liveFrame.blob, 'scan.jpg');",
    "fd.append('capture_kind'",
    "const HAS_SERVER = location.protocol.startsWith('http');",
    "const liveSimulated = ()=> !HAS_SERVER || !liveFrame;",
    "The simulated pipeline runs only where there is no server to talk to",
    "The scan could not be completed",
    "publish to try again, or retake",
    "the scan timed out",
    "could not reach the server",
    "Not checked — this photo has not left your phone",
    "function doneHeading(p, simulated){",
    "function runDone(p, simulated){",
    "runDone(p, simulated);",
    "{kind:'quarantined', body:j}",
    "r.status===503 && assessed",
    "function loadLiveMap(){",
    # TICK-370: a contributor looks here after publish. Losing these two puts an
    # unreachable store or a torn record in front of them as an empty map.
    "if(j.scans_error) toast('Published scans could not be loaded')",
    "else if(j.scans_skipped) toast(j.scans_skipped===1",
    "PHOTO_API+b.image_keys[0]",
    "const CORRECT_API = '/correct';",
    "fetch(CORRECT_API+'/mine'",
    "fetch(CORRECT_API,{method:'POST'",
    "function loadMyCorrections(){",
    "Opened without a server \u2014 a correction cannot be sent from here",
    "Couldn't send \u2014 ",
    "Your note joins a <b>review queue</b> a person works through",
    "if((p.tier==='est' && aged) || p.relook){",
    "Corrections stay human \u2014 a person reads every note before anything changes",
    "p.relook = pin.needs_relook===true",
    "function fetchMyCorrections(){",
    # TICK-399: a criterion the server refused an answer for is not a feature
    # that was looked for and not found. Losing this line puts a rejected
    # response in front of a person at a door as an observation.
    "Not assessed this time:",
    # The type, served from this origin. Without these the page falls back to
    # system-ui the moment the network is slow, and the installed app launches
    # in the system face with nothing to say it happened.
    "url('/app-fonts/AtkinsonHyperlegibleNext-Variable.woff2')",
    "url('/app-fonts/AtkinsonHyperlegibleNext-Italic-Variable.woff2')",
    "url('/app-fonts/NunitoSans-ExtraBold.ttf')",
    # Round 10, and the reason this file's replace_region ops are dangerous: both
    # lines are the design source's and both fall inside scan_entry's region, so
    # they reach the page only through the fragment. Losing stopCoach() leaves the
    # 5 Hz frame readback and the devicemotion listener running after the shutter.
    "ackCapture();",
    "stopCoach();",
    # Round 11's provenance row, likewise inside publish's region. It is the first
    # thing a contributor is shown about their scan, and -- the wiring's part -- it
    # says a receipt was joined only for a run that actually published.
    "document.getElementById('done-prov').innerHTML = provRow(",
    "function doneProvenance(p, simulated){",
    "Added to this entrance's receipt as a dated source",
    "Nothing was published, so nothing joined this entrance's receipt.",
    # TICK-467. The evidence box lives in the design source, so a refresh from a
    # design round that does not carry it drops the whole feature silently --
    # which is TICK-474 again, in the other direction. Four lines, one per thing
    # that cannot be lost without the feature becoming a lie:
    #   the chips exist and are gated on the detector having RUN, not on which
    #   criteria came back with a box (gating on the boxes turns the row of
    #   chips itself into a verdict);
    "if(photos && p.evbox && p.f){",
    #   the sentence for a criterion nothing could be pointed at, which is the
    #   whole reason this ticket exists and the one thing a bare photograph
    #   must never be left to say;
    "we looked for this and couldn't point at it in these photos. "
    "That doesn't change the answer above.",
    #   the standing note that the outline is the finder's and the answer is
    #   the model's;
    "The outline shows where our finder pointed. It never changes the answer.",
    #   and the cover-fit inverse, without which a box lands in the wrong place,
    #   which is worse than drawing none.
    "const s = Math.max(cw/nw, ch/nh);",
    # The locate control. The design source's handler never called geolocation at
    # all, so every one of these lines is the difference between a control that
    # works and one that pans to a fixed point and says it found you.
    "function locateMe(){",
    "geoState='denied';",
    "function placeYouHere(){",
    "function paintEmptyInvite(noPins){",
    "  paintEmptyInvite(shown.length===0);\n  placeYouHere();",
    "Centered on you — you are marked on the map",
    "EntryMap has not mapped your area yet",
    "Location is off for this site, so the map has not moved",
    "el.setAttribute('aria-label','You are here');",
    "el.setAttribute('role','alert');",
    # TICK-488. Three controls ask or claim the same permission -- the map's locate
    # button, onboarding's "Allow location" and the Settings switch -- and the eight
    # outcomes are branched on in exactly one of them. askGeo() is that one place and
    # the only caller of getCurrentPosition; losing it is how a second copy of the
    # branching comes back, and a second copy is how one of them drifts into claiming
    # an outcome it never reached.
    "function askGeo(say){",
    "function geoPrecheck(){",
    "function geoFixOutcome(pos){",
    "function geoFailOutcome(err){",
    "function recordGeoOutcome(o){",
    "navigator.geolocation.getCurrentPosition(",
    # The onboarding step asks, and the switch it used to assert is painted from the
    # answer instead of from the tap.
    "function obAllowTap(){",
    "if(askGeo(obLocSays)==='busy') obLocBusy(false);",
    "function paintLocToggle(){",
    "const on = geoPermission==='granted';",
    "locToggle.setAttribute('aria-checked', on ? 'true' : 'false');",
    # ...and each outcome's own wording on the step, which is not the map's wording,
    # because on this step nothing has been shown yet and what is said is what will be
    # different.
    "Location is off for this site, so nothing was shared and the map will",
    "Finding your location took too long, so nothing was shared.",
    "Your device could not work out where it is, so nothing was shared.",
    "This browser cannot share a location, so the map will open on the few",
    "location. The map will open on the few blocks of downtown Austin this pilot ",
    "Location is on — the map will center on you",
    "Location is on — you are just outside the mapped blocks, so the map will open ",
    # ...and the grant MOVES the frame rather than promising it. finishOnboarding()
    # only renders, so without this line the map opens on the pilot bbox and the
    # sentence above is staged rather than produced -- this ticket's own defect.
    "    setZoom(false, youFix);",
]

# ...and none of these. The design source is worked on against a deployed host and a
# public icon URL; neither may reach the page this service serves from its own origin.
WIRING_FORBIDDEN: list[str] = [
    "fly.dev",
    "raw.githubusercontent.com",
    "phone prototype",
    # The design seeded "My corrections" with worked examples, and the send button
    # appended to the same array. Either one puts a note in front of a person that
    # the server has never heard of, which is TICK-387 in a single line.
    "corrections.unshift(",
    "seeded with three worked examples",
    "stays on the receipt as its own dated source",
    # The type comes from this origin. Not a preconnect, not a stylesheet link, not
    # a font source -- and not a comment either, so this can never quietly come back
    # as "the domain is only mentioned". tests/test_app_page.py enforces the weaker
    # form (no request); the port enforces the absolute one.
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    # TICK-474. The engine assesses four criteria (frontdoor.screening,
    # CRITERIA_KEYS). The design source carried eight entrance features and
    # rendered all eight identically -- chip, confidence dots, sr-only
    # "confidence high", pin accessible name, list row, owner workspace,
    # public-listing preview -- so four of them published findings nothing had
    # produced, on named real businesses. tests/test_app_page.py pins the built
    # page's structures; these four forms are the exact lines a refresh from a
    # new design round would put back, and they fail the build rather than the
    # review. They are code, never prose, so a comment explaining the fix is
    # still allowed to name the feature it removed.
    "step_free_entry:'step_free'",
    "p.f.step_free",
    "['step_free','Step-free']",
    "crit:['step_free'",
    # The locate button's original handler. It asked the phone nothing, panned to a
    # fixed point and told whoever pressed it -- in Austin or a thousand miles from
    # it -- that the map was centred on them. It is a broken control and a false
    # statement in one line, it is still in the prototype the design source is
    # refreshed from, and it may never reach a page a person at a door reads.
    "Centered on you \\u00b7 2nd & Colorado",
    "setZoom(false, null); toast('Centered on you",
    # TICK-488. Onboarding's "Allow location" flipped the switch on, set
    # aria-checked="true" and advanced -- without ever calling navigator.geolocation.
    # Nothing was asked and no permission was granted, and the interface then stated
    # that location was allowed, visually and to a screen reader, as the first thing a
    # new user is told. It is the locate button's defect about a permission instead of
    # a place, and it is on the path every new user walks. Both spellings of the lie
    # are here: the two-line body, and the anonymous listener the design source hangs
    # it from, so a refresh that rewrites one still fails on the other.
    "lt.classList.add('on'); lt.setAttribute('aria-checked','true');",
    "document.getElementById('ob-allow-loc').addEventListener('click',()=>{",
    # ...and the same defect on the Settings switch, which flipped on tap and said so.
    "toast(on?'Location on while using'",
    "loct.classList.toggle('on',on); loct.setAttribute('aria-checked',on);",
    "No problem \\u2014 search the map instead",
    "No problem — search the map instead",
]


class PortError(RuntimeError):
    """A design change moved an anchor, or an op stopped doing its job."""


def _require_once(text: str, needle: str, op: Op, label: str) -> int:
    count = text.count(needle)
    if count != 1:
        raise PortError(
            f"op {op.name!r}: {label} matches {count} times, expected exactly 1.\n"
            f"  {label}: {needle[:120]!r}\n"
            f"  The design source moved. Re-point this op's anchor, or fix the wiring it carries."
        )
    return text.index(needle)


def apply_op(text: str, op: Op, fragments: dict[str, str]) -> tuple[str, int]:
    """Return the transformed text and the number of design-source bytes it displaced."""
    body = fragments[op.fragment] if op.fragment else (op.replacement or "")
    start = _require_once(text, op.anchor, op, "anchor")
    if op.kind == "insert_before":
        return text[:start] + body + text[start:], 0
    if op.kind == "insert_after":
        end = start + len(op.anchor)
        return text[:end] + body + text[end:], 0
    if op.kind == "replace":
        end = start + len(op.anchor)
        return text[:start] + body + text[end:], len(op.anchor)
    if op.kind == "replace_region":
        assert op.until is not None
        _require_once(text, op.until, op, "until")
        try:
            end = text.index(op.until, start)
        except ValueError:
            raise PortError(
                f"op {op.name!r}: 'until' appears before 'anchor', so there is no region "
                f"to replace. The design source reordered these two sections."
            ) from None
        return text[:start] + body + text[end:], end - start
    raise PortError(f"op {op.name!r}: unknown kind {op.kind!r}")


def port(design_source: str) -> tuple[str, list[tuple[str, int]]]:
    """Apply every op to the design source and return the served page.

    Pure: the same input always produces the same output, so re-running the port is
    always safe and always idempotent with respect to its inputs.
    """
    fragments = {
        op.fragment: (WIRING_DIR / op.fragment).read_text(encoding="utf-8")
        for op in OPS
        if op.fragment
    }
    text = design_source.replace("\r\n", "\n")
    displaced: list[tuple[str, int]] = []
    for op in OPS:
        text, n = apply_op(text, op, fragments)
        displaced.append((op.name, n))
    check(text)
    return text, displaced


def check(page: str) -> None:
    missing = [needle for needle in WIRING_REQUIRED if needle not in page]
    present = [needle for needle in WIRING_FORBIDDEN if needle in page]
    if missing or present:
        report = ""
        if missing:
            report += "wiring missing from the ported page:\n" + "".join(
                f"  - {m!r}\n" for m in missing
            )
        if present:
            report += "the ported page still carries design-only wiring:\n" + "".join(
                f"  - {p!r}\n" for p in present
            )
        raise PortError(report.rstrip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--design-source",
        type=Path,
        default=None,
        help="a fresh design source to port from (default: the copy committed under design-source/)",
    )
    parser.add_argument(
        "--update-source",
        action="store_true",
        help="also refresh the committed design source from --design-source",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=SERVED_PAGE,
        help="where to write the ported page (default: the served app.html)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; fail if the ported page differs from what is on disk",
    )
    args = parser.parse_args(argv)

    source_path = args.design_source or DESIGN_SOURCE
    if args.update_source and args.design_source is None:
        parser.error("--update-source needs --design-source")
    source = source_path.read_text(encoding="utf-8").replace("\r\n", "\n")

    try:
        page, displaced = port(source)
    except PortError as exc:
        print(f"port failed:\n{exc}", file=sys.stderr)
        return 1

    if args.check:
        current = args.out.read_text(encoding="utf-8").replace("\r\n", "\n")
        if current != page:
            print(
                f"{args.out} is not what the port produces from {source_path}; "
                "re-run tools/port_app_page.py",
                file=sys.stderr,
            )
            return 1
        print(f"{args.out} is up to date with {source_path}")
        return 0

    if args.update_source:
        DESIGN_SOURCE.write_text(source, encoding="utf-8", newline="\n")
        print(f"design source refreshed: {DESIGN_SOURCE.relative_to(REPO_ROOT)}")
    args.out.write_text(page, encoding="utf-8", newline="\n")
    print(f"ported {source_path} -> {args.out}")
    for name, n in displaced:
        print(f"  {name:22} {'wiring owns ' + str(n) + ' bytes of the design source' if n else 'added'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
