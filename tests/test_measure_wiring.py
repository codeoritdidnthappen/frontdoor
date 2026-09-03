"""TICK-063's wiring rules, asserted against the source.

The rendering layer and its response model are covered by XCTest. What is not reachable there is
the ORDER of the capture path and the conditions under which measurement happens at all -- both
need a camera, and CI never builds Swift. Both were deferred when the layer landed, so they have
never been checked.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "ios" / "FrontdoorCapture" / "Capture" / "CaptureController.swift"


def code() -> str:
    return "\n".join(
        re.sub(r"//.*", "", line)
        for line in CONTROLLER.read_text(encoding="utf-8").splitlines()
    )


def body_of(signature: str) -> str:
    """One function body, by signature.

    Targeted at `commit(` rather than `confirmReview(`: main split the write path in #31 so
    screening and metrology share it, leaving confirmReview a two-line delegator. A guard left
    pointing at the delegator asserts nothing about the code that actually writes -- it raised
    here on rebase rather than passing quietly, which is the only reason it was caught.
    """
    return code().split(signature, 1)[1].split("\n    }", 1)[0]


def confirm_review_body() -> str:
    return body_of("private func commit(")


def test_the_capture_is_written_and_queued_before_it_is_measured():
    """AC4: a failed measurement never costs a dataset record.

    Every MeasureClient failure message ends "The capture is saved." That is only true if the
    write and the queue refresh happen first. Measuring before writing would make the app promise
    something it had not yet done.
    """
    body = confirm_review_body()
    write = body.index("CaptureWriter.write(")
    refresh = body.index("refreshPendingUploads()")
    measured = body.index("measure(written")
    assert write < measured, "the capture must be on disk before it is measured"
    assert refresh < measured, "it must be counted as pending before it is measured"


def test_measuring_does_not_block_the_shutter():
    """A venue network that hangs must not hold the capture path.

    The operator has to be able to take the next frame while a measurement is in flight, and the
    capture is already safe whatever the server does.
    """
    source = code()
    body = source.split("private func measure(", 1)[1].split("\n    }", 1)[0]
    assert "Task {" in body, "the request must not be awaited inline in the capture path"
    assert "await measureClient.measure" in body


def test_rendering_is_additive_and_off_without_a_server():
    """AC6: with rendering disabled the capture flow is unchanged.

    `measureClient` is nil when the build carries no server, and `measure` returns immediately --
    so nothing in the capture path behaves differently.
    """
    source = code()
    body = source.split("private func measure(", 1)[1].split("\n    }", 1)[0]
    assert "guard let measureClient else { return }" in body, (
        "with no server configured, measurement must be a no-op"
    )


def test_the_server_is_configured_in_exactly_one_place():
    """One host or none.

    Two sources would let a build upload captures to one server and measure against another, and
    the mismatch would only show as results that do not correspond to the dataset.
    """
    source = code()
    assert source.count("UploadSettings.fromBundle()") == 2, (
        "uploader and measure client must both come from UploadSettings, and nothing else should"
    )
    assert "MeasureClient(baseURL:" in source
    assert re.search(r'MeasureClient\(baseURL: URL\(string: "', source) is None, (
        "no hardcoded server URL"
    )


def test_every_path_that_enqueues_a_capture_retires_the_last_drain_verdict():
    """A queue that just grew is not described by the drain that ran before it grew.

    `lastDrainMessage` is rendered whenever it is non-nil, deliberately -- a successful drain used
    to set the count to zero and hide its own confirmation. The cost of that fix is that a verdict
    from an empty-queue drain outlives the emptiness: observed on the 15 Pro Max on 2026-09-02,
    Home showing "3 captures on this phone only" directly above "Nothing to upload. Everything
    here is already safe."

    Asserted over BOTH writers rather than the shutter alone. #31 added photo import, which
    enqueues a capture by a second path and carried the same bug -- found only because this rebase
    put the two side by side. A guard naming one of them would go on passing while the other lied.
    """
    for signature in ("private func commit(", "func importPhoto("):
        body = body_of(signature)
        assert "CaptureWriter.write(" in body, f"{signature} is no longer a write path"
        # Anchored past the write. importPhoto matches `case .success(let read)` first, for the
        # file it is reading in -- asserting against that branch would pass while the branch that
        # actually enqueues went unchecked.
        after_write = body.split("CaptureWriter.write(", 1)[1]
        success = after_write.split("case .success", 1)[1].split("case .failure", 1)[0]
        assert "lastDrainMessage = nil" in success, (
            f"{signature} enqueues a capture without retiring the previous drain's verdict; "
            "the app then tells an operator their unsent captures are safe"
        )


RESULT_VIEW = ROOT / "ios" / "FrontdoorCapture" / "UI" / "ResultView.swift"


def test_an_absent_instrument_reading_renders_as_nothing_not_as_zero():
    """D-036 superseded D-003: no caliper, so there is no reading to show beside the result.

    The failure this forbids is silent and lands on a projector. If the reading defaults to zero,
    ResultView prints "caliper 0.00 in - difference 0.11 in" and the room reads a fabricated
    agreement between a measurement and an instrument nobody used. Absent truth must render as
    nothing at all.
    """
    controller = CONTROLLER.read_text(encoding="utf-8")
    assert re.search(r"var measurementCaliperInches: Double\?", controller), (
        "the caliper reading must be optional; a non-optional one has to invent a value for "
        "every capture in this study, none of which has an instrument reading"
    )
    assert not re.search(r"measurementCaliperInches: Double\s*=", controller), (
        "a default reading is a reading nobody took"
    )

    view = RESULT_VIEW.read_text(encoding="utf-8")
    assert "let caliperInches: Double?" in view, "ResultView must accept an absent reading"
    comparison = view.split("private func caliperComparison(", 1)[1].split("\n    }", 1)[0]
    assert "if let caliperInches" in comparison, (
        "the comparison must be withheld when there is no reading, not rendered against zero"
    )


CAPTURE_VIEW = ROOT / "ios" / "FrontdoorCapture" / "UI" / "CaptureView.swift"


def test_every_path_that_writes_a_capture_counts_it_against_its_entrance():
    """#4 AC5: the operator has to be able to see an under-shot entrance at the door.

    `docs/capture-protocol.md` asks for 5-6 views of every entrance, and nothing enforces it --
    D-021 put the plan in the instrument and the 2026-09-01 pivot moved it to the document. Under
    D-036 one operator shoots 40-60 entrances with no second phone covering the same doorway, so a
    view missed at the door is found during analysis, a drive away.

    Both writers must count, for the reason the import path already broke once here: a photo
    imported for E-014 is a view of E-014, and a count that ignores it under-reports coverage.
    EntranceTally's own behaviour is covered by XCTest; what needs asserting from here is that the
    capture paths actually call it, which needs a camera.
    """
    for signature in ("private func commit(", "func importPhoto("):
        after_write = body_of(signature).split("CaptureWriter.write(", 1)[1]
        success = after_write.split("case .success", 1)[1].split("case .failure", 1)[0]
        assert "tally.increment(" in success, (
            f"{signature} writes a capture without counting it against its entrance"
        )


def test_the_count_is_on_the_viewfinder_where_it_can_still_be_acted_on():
    """A coverage number on the home screen is read after walking away from the doorway."""
    view = CAPTURE_VIEW.read_text(encoding="utf-8")
    bar = view.split("private var conditionsBar", 1)[1].split("\n    }", 1)[0]
    # Split at the accessibility label and assert against what is DRAWN. Checking the whole bar
    # passed with the visible count deleted, because the label mentions it too -- a guard that
    # would have let the number vanish from the screen while still reading it to VoiceOver.
    drawn, _, spoken = bar.partition(".accessibilityLabel")
    assert "capturesForSubject" in drawn, (
        "the per-entrance count must be drawn on the viewfinder's conditions bar, beside the "
        "entrance id it belongs to"
    )
    assert "capturesForSubject" in spoken, "and spoken, so the bar reads the same either way"
