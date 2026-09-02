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


def confirm_review_body() -> str:
    return code().split("func confirmReview(", 1)[1].split("\n    }", 1)[0]


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
