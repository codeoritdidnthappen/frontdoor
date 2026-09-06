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
        until='<link rel="preconnect" href="https://fonts.googleapis.com">',
        fragment="head.html",
    ),
    Op(
        name="wiring_css",
        why="styles for the two elements the wiring adds: the entrance field and the simulated tag",
        kind="insert_before",
        anchor="\n</style>\n</head>",
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
        until="/* ---- processing: the ring draws itself as one marigold stroke; the named checks surface",
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
    "PHOTO_API+b.image_keys[0]",
]

# ...and none of these. The design source is worked on against a deployed host and a
# public icon URL; neither may reach the page this service serves from its own origin.
WIRING_FORBIDDEN: list[str] = [
    "fly.dev",
    "raw.githubusercontent.com",
    "phone prototype",
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
