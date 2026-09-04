"""A 503 and a 500 must not mean the same thing to the capture app (#265).

#258 made a misconfigured or still-booting deploy answer a named **503** instead of a bare 500,
on the argument that the client should keep the capture and retry. That reasoning only pays off if
the client can tell the two apart -- and it could not: `outcome(status:body:expecting:)` had no 5xx
case, so both fell through to `default` and produced "the server answered <status>". Same message,
same behaviour, and no way for an operator to tell an outage from a bug.

XCTest covers the behaviour, but XCTest runs only when someone opens Xcode: CI is one Linux job
running pytest, and `assert-no-arkit.sh` compiles nothing. So the branch itself is asserted here,
where a revert in either direction is actually caught.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPLOADER = ROOT / "ios" / "FrontdoorCapture" / "Upload" / "ServerUploader.swift"


def outcome_body():
    source = UPLOADER.read_text(encoding="utf-8")
    start = source.index("static func outcome(")
    return source[start : source.index("\n    private func send(", start)]


def test_503_has_its_own_branch():
    assert re.search(r"^\s*case 503:", outcome_body(), re.MULTILINE), (
        "503 has no branch of its own, so it falls through with every other 5xx -- which is the "
        "state #258's server-side change was made to escape"
    )


def test_the_other_5xx_are_still_handled_separately():
    body = outcome_body()
    assert re.search(r"^\s*case 500\.\.\.599:", body, re.MULTILINE)
    assert body.index("case 503:") < body.index("case 500...599:"), (
        "the range must come after the specific case, or 503 never matches"
    )


def test_a_503_message_does_not_quote_the_bare_status():
    """AC-2: it says the server is unavailable, not a number the operator cannot act on."""
    body = outcome_body()
    branch = body[body.index("case 503:") : body.index("case 500...599:")]
    assert "unavailable" in branch
    assert "\\(status)" not in branch


def test_no_5xx_is_treated_as_this_captures_own_fault():
    """A 5xx is a fact about the server. Marking one per-capture would let the drain skip past it
    and, worse, invite deleting bytes the server never stored."""
    body = outcome_body()
    fifth = body[body.index("case 503:") : body.index("default:")]
    assert "refusePermanently" not in fifth
