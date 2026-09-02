"""The app must actually write captures to disk (TICK-028, QA B02).

`CaptureWriter` landed complete and correct, with its own passing tests, and **nothing
called it**. `lastRecord` had one write and zero reads; the camera's encoded bytes were
consumed inline by `UIImage(data:)` and never retained, so even reconstructing them would
have meant a re-encode -- which AC2 forbids, because the hash must be over the bytes that
were written.

The commit was titled "Write the capture to disk". The app wrote nothing. A pilot session
(#66) would have ended with a full `photosTaken` counter and an empty directory, and the
Swift suite would have stayed green throughout, because every test called the writer
directly.

This is a source scan rather than a behavioural test on purpose: it runs in CI, where no
simulator exists, and it fails for the one reason that matters -- the production path
stopped reaching the writer.
"""

import re
from pathlib import Path

import pytest

IOS = Path(__file__).resolve().parents[1] / "ios"
APP = IOS / "FrontdoorCapture"
TESTS = IOS / "FrontdoorCaptureTests"


def _app_sources():
    files = [p for p in APP.rglob("*.swift")]
    assert files, f"no Swift sources under {APP}; this guard would pass vacuously"
    return files


def _body_of(source, signature):
    """The braced body of one function, found by matching braces rather than by a marker.

    An earlier version of this helper searched for the doc comment of the NEXT declaration,
    which `_strip_comments` had already deleted -- a locator that depended on text the same
    file removed two lines earlier.
    """
    start = source.index(signature)
    open_brace = source.index("{", start)
    depth, i = 0, open_brace
    while i < len(source):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
        i += 1
    raise AssertionError(f"unbalanced braces after {signature!r}")


def _strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))


def test_the_app_calls_the_capture_writer():
    """Not the tests -- the app."""
    callers = [
        p.relative_to(IOS)
        for p in _app_sources()
        if "CaptureWriter.write(" in _strip_comments(p.read_text(encoding="utf-8"))
    ]
    assert callers, (
        "no file under FrontdoorCapture/ calls CaptureWriter.write(). The writer is "
        "unreachable from the app, so captures exist only in memory."
    )


def test_the_camera_bytes_are_retained_for_writing():
    """AC2 hashes the WRITTEN bytes, so the camera's own encoding has to survive.

    `photo.fileDataRepresentation()` fed straight into `UIImage(data:)` discarded them at
    the delegate, leaving a re-encode as the only way to produce a file later.
    """
    source = _strip_comments(
        (APP / "Capture" / "CaptureController.swift").read_text(encoding="utf-8")
    )
    assert "fileDataRepresentation().flatMap(UIImage.init(data:))" not in source, (
        "the encoded bytes are consumed inline and never retained"
    )
    assert "imageData" in source, "the captured bytes must be carried to the writer"


#: The single function where a frame becomes a capture on disk. Both modes go through it: the
#: metrology path via confirmReview once ROI taps exist, the screening path straight from the
#: shutter, because the plain-photo protocol places no taps (D-034, TICK-027).
COMMIT = "func commit("


def test_the_writer_is_reached_from_the_commit():
    """The one place a frame becomes a capture (TICK-026) is the one place it must persist."""
    source = _strip_comments(
        (APP / "Capture" / "CaptureController.swift").read_text(encoding="utf-8")
    )
    body = _body_of(source, COMMIT)
    assert "CaptureWriter.write(" in body, "commit must write the capture"
    assert body.index("CaptureWriter.write(") < body.index("photosTaken += 1"), (
        "the counter must not advance before the bytes are on disk"
    )


def test_every_route_to_a_capture_reaches_the_commit():
    """The guard is only worth anything if nothing can become a capture around it.

    Splitting `confirmReview` into a thin caller is exactly the refactor that could leave a
    second, writer-less path behind -- which is the shape of QA B02 all over again.
    """
    source = _strip_comments(
        (APP / "Capture" / "CaptureController.swift").read_text(encoding="utf-8")
    )
    # The metrology route: taps confirmed, then commit.
    confirm = _body_of(source, "func confirmReview")
    assert "commit(" in confirm, "confirmReview must reach the commit"
    assert "CaptureWriter.write(" not in confirm, (
        "confirmReview must not write directly; one writer call, one guarded path"
    )
    # The screening route: no ROI step, so the shutter path commits for itself.
    assert source.count("commit(pending, taps:") == 2, (
        "expected exactly two routes into commit -- confirmReview and the screening shutter"
    )
    # And the invariant that actually matters: every way of creating a capture goes through the
    # writer, and each one advances the counter only after it. Asserting on `commit(` alone stopped
    # covering that the moment importPhoto began writing directly (D-034).
    calls = source.count("CaptureWriter.write(")
    assert calls == 2, (
        f"expected exactly two CaptureWriter.write call sites (commit and importPhoto), found "
        f"{calls}; a third is an unguarded way to create a capture"
    )
    imported = _body_of(source, "func importPhoto")
    assert "CaptureWriter.write(" in imported, "importPhoto must write the photo"
    assert imported.index("CaptureWriter.write(") < imported.index("photosTaken += 1"), (
        "the counter must not advance before the bytes are on disk"
    )
    # Scoped to the WRITE switch. importPhoto refuses unreadable files first, so partitioning the
    # whole body on the first `case .failure` splits at the wrong switch and the check passes or
    # fails for reasons that have nothing to do with the counter.
    write_switch = imported[imported.index("CaptureWriter.write("):]
    success, _, failure = write_switch.partition("case .failure")
    assert "photosTaken += 1" in success and "photosTaken += 1" not in failure, (
        "an import that failed to write must not be counted"
    )


@pytest.mark.parametrize("needle", ["photosTaken += 1", "lastRecord = record"])
def test_success_state_is_set_only_on_a_successful_write(needle):
    """A counter that advances on a failed write is a session that lies about its own size.

    Checked by SPLITTING the branches rather than by their order: an earlier version of this
    test asserted only that `case .success` came before the assignment and `case .failure`
    after it, which `case .success, .failure:` satisfies perfectly while doing the exact
    thing the test forbids.
    """
    source = _strip_comments(
        (APP / "Capture" / "CaptureController.swift").read_text(encoding="utf-8")
    )
    body = _body_of(source, COMMIT)
    # Matched as a rule rather than as one spelling. The branch may bind the write result --
    # `case .success(let written)` -- which TICK-063 needs in order to measure the file it just
    # wrote, and which is every bit as standalone as `case .success:`. What must never appear is a
    # combined case, which is the thing this test exists to forbid.
    assert re.search(r"case \.success[:(]", body), (
        "the success branch must exist and stand alone; a combined `case .success, .failure:` "
        "runs the success path on a write that failed"
    )
    for combined in ("case .success, .failure", "case .failure, .success"):
        assert combined not in body, (
            f"`{combined}:` runs the success path on a write that failed"
        )
    success, _, failure = body.partition("case .failure")
    assert needle in success, f"{needle!r} must sit in the success branch"
    assert needle not in failure, f"{needle!r} must not run when the write failed"


def test_the_failure_branch_reports_and_keeps_the_frame():
    """Complete-or-nothing (AC5): the operator can fix what is missing and re-confirm."""
    source = _strip_comments(
        (APP / "Capture" / "CaptureController.swift").read_text(encoding="utf-8")
    )
    _, _, failure = _body_of(source, COMMIT).partition("case .failure")
    assert "lastCaptureError" in failure, "a failed write must say why"
    assert "pendingReview = nil" not in failure, (
        "the frame must stay under review, or the operator loses it with no capture on disk"
    )
