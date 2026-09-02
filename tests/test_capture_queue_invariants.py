"""Two TICK-029 rules that XCTest cannot reach, asserted against the source.

Both were found by mutation testing: reverting either left all 143 Swift tests green, because one
needs a filesystem deletion to fail on demand and the other is app-launch lifecycle. Rather than
leave them as prose in a comment, they are pinned here -- the same tactic as the ARKit guard and
the captured_at guard, and it runs in CI, which never builds Swift at all.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "ios" / "FrontdoorCapture" / "Persistence" / "CaptureQueue.swift"
CONTROLLER = ROOT / "ios" / "FrontdoorCapture" / "Capture" / "CaptureController.swift"


def code(path: Path) -> str:
    """Source with line comments stripped, so prose describing a rule cannot satisfy it."""
    return "\n".join(re.sub(r"//.*", "", line) for line in path.read_text(encoding="utf-8").splitlines())


def test_the_sidecar_is_deleted_after_the_files_it_describes():
    """Sidecar last, or a failure strands bytes nothing can see again.

    `pending()` enumerates `.json` files only. Removing the sidecar first and then failing on the
    image leaves an orphan: invisible to the count, never drained, never collected, on a phone
    taking 200+ full-resolution captures a day. Deleting it last means a failure leaves the capture
    whole and still queued -- draining twice is recoverable, silent orphans are not.
    """
    source = code(QUEUE)
    body = source.split("func remove(", 1)[1]
    loop = body.index("for url in [capture.imageURL")
    sidecar = body.index("removeItem(at: capture.sidecarURL)")
    assert loop < sidecar, (
        "the sidecar must be removed after the image and depth files, not with them"
    )
    assert "capture.sidecarURL" not in body[loop:body.index("guard leftBehind.isEmpty")], (
        "the sidecar must not be inside the loop that removes the image and depth"
    )


def test_the_pending_count_is_refreshed_at_launch():
    """A cold launch fires no scenePhase change.

    Without this the count reads zero after exactly the event AC2 is about -- termination or a
    device restart -- while the captures sit in Documents. It corrects itself on the next
    background-and-return, which makes it look imagined rather than wrong.
    """
    source = code(CONTROLLER)
    init_body = source.split("init() {", 1)[1].split("\n    }", 1)[0]
    assert "refreshPendingUploads()" in init_body, (
        "init must read the queue, or a relaunch shows nothing pending while captures exist"
    )
