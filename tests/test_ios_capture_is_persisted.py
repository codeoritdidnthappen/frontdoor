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


def _write_switch(body):
    """The part of `commit` from the write onwards.

    #328 put a privacy step in front of the write, which has a `case .failure` of its own. These
    guards are about what happens when the WRITE fails, so they start where the write does --
    otherwise they partition on the wrong branch and report a rule that is still being kept.
    """
    return body[body.index("CaptureWriter.write("):]


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
    body = _write_switch(_body_of(source, COMMIT))
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
    _, _, failure = _write_switch(_body_of(source, COMMIT)).partition("case .failure")
    assert "lastCaptureError" in failure, "a failed write must say why"
    assert "pendingReview = nil" not in failure, (
        "the frame must stay under review, or the operator loses it with no capture on disk"
    )


# --- the stored orientation reaches the sidecar (found on the #51 device round trip) ---------


def test_the_sidecar_records_the_stored_orientation():
    """The writer must carry the record's EXIF orientation into the image object.

    A source scan because CI is Linux and never builds Swift: the committed golden fixtures pin
    the field, but a writer that stopped emitting it would leave those fixtures stale and green
    here while every capture in the field lost the one fact that says whether the pixel grid the
    intrinsics describe is the grid a reader will decode.
    """
    source = _strip_comments(
        (APP / "Persistence" / "CaptureWriter.swift").read_text(encoding="utf-8"))
    assert "exifOrientation: record.imageExifOrientation" in source


@pytest.mark.parametrize(
    "site,needle",
    [
        ("Capture/CaptureController.swift", "imageExifOrientation: captured.exifOrientation"),
        ("Capture/CaptureController.swift", "imageExifOrientation: 1"),
    ],
)
def test_both_capture_routes_supply_an_orientation(site, needle):
    """Camera and import both. The import path is the one that would silently default: an
    imported photo's orientation comes from a file this app did not write.
    """
    source = _strip_comments((APP / site).read_text(encoding="utf-8"))
    assert needle in source


def test_ac_1_ac_2_ac_3_import_privacy_processing_precedes_the_only_write():
    """Camera-roll originals may supply truthful record metadata, but only the processed JPEG
    may cross CaptureWriter's persistence boundary.
    """
    source = _strip_comments(
        (APP / "Capture" / "CaptureController.swift").read_text(encoding="utf-8"))
    body = _body_of(source, "func importPhoto(")
    processing = body.index("ImportedPhotoPrivacy.process(data)")
    writing = body.index("CaptureWriter.write(")
    assert processing < writing
    assert "imageData: processed.data" in body
    assert 'imageExtension: "jpg"' in body
    assert "imageData: data" not in body


def test_the_orientation_map_covers_all_eight_exif_values():
    """UIImage.Orientation and CGImagePropertyOrientation are not in the same order, so bridging
    by rawValue is wrong for six of the eight. The table is written out; this checks it stayed
    written out, and that nothing was dropped from it.
    """
    source = _strip_comments(
        (APP / "Capture" / "CaptureController.swift").read_text(encoding="utf-8"))
    body = _body_of(source, "func exifOrientation(of orientation: UIImage.Orientation) -> Int")
    for case in ("up", "upMirrored", "down", "downMirrored",
                 "leftMirrored", "right", "rightMirrored", "left"):
        assert f"case .{case}:" in body, f"{case} is not mapped"
    assert "rawValue" not in body, "the mapping must not be derived from rawValue"


# --- the review-before-publish consent gate (#275) -------------------------------------------
#
# A community scan is a photograph of someone's premises. Screening frames used to become
# captures AT THE SHUTTER -- `commit(pending, taps: nil)` ran straight from the capture callback
# -- so there was no moment at which the operator could be asked whether to publish one.
#
# What makes the gate real is not the screen; it is that `commit` has no other caller. A
# shutter-time commit added back later would bypass the consent question while every screen still
# looked right.


def _commit_callers():
    """Every function in CaptureController whose body calls `commit(`."""
    source = _strip_comments(
        (APP / "Capture" / "CaptureController.swift").read_text(encoding="utf-8"))
    callers = []
    for match in re.finditer(r"\n    (?:private )?func (\w+)\(", source):
        name = match.group(1)
        body = source[match.start():]
        end = body.find("\n    }")
        if "commit(" in body[:end]:
            callers.append(name)
    return callers


def test_a_screening_frame_waits_for_review_instead_of_committing_at_the_shutter():
    source = _strip_comments(
        (APP / "Capture" / "CaptureController.swift").read_text(encoding="utf-8"))
    assert "func confirmScreeningReview()" in source, (
        "the screening consent gate has no confirm path")
    # The capture callback sets pendingReview for BOTH modes; a mode-conditional commit here is
    # the shape the gate replaced.
    callback = _body_of(source, "private func accept(")  # the capture completion path
    assert "commit(" not in callback, (
        "the capture callback commits directly, so a frame becomes a capture before anyone is "
        "asked whether to publish it")


def test_commit_is_reachable_only_from_the_confirm_paths():
    """The invariant the gate rests on.

    Note `importPhoto` does not appear: it writes through `CaptureWriter` directly rather than
    through `commit`, so it is not gated by this and is not claimed to be. An imported photo was
    taken deliberately and then chosen from the library, which is a different act from pointing a
    camera at a stranger's shopfront -- but if the canon wants imports gated too, that is a
    separate change and this test will not notice it.
    """
    callers = set(_commit_callers())
    allowed = {"commit", "confirmReview", "confirmScreeningReview"}
    assert callers <= allowed, (
        f"commit() is called from {sorted(callers - allowed)}; every route to a capture must pass "
        "through a confirm path or the consent gate is bypassable")


def test_discarding_writes_nothing():
    """Declining must leave no trace -- not a file, not a tally, not a queue entry.

    The privacy-safe reading of "review before publish": an unconsented photo kept on the phone is
    one a later drain can still upload.
    """
    source = _strip_comments(
        (APP / "Capture" / "CaptureController.swift").read_text(encoding="utf-8"))
    body = _body_of(source, "func discardReview(")
    assert "pendingReview = nil" in body
    for forbidden in ("CaptureWriter.write(", "tally.increment(", "commit("):
        assert forbidden not in body, f"discardReview calls {forbidden}"
