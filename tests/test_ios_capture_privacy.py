"""No capture path may write unprocessed bytes (#328).

#232 blurred at ingest on `/screen` and on camera-roll import. The device-camera path — the one
that fills the actual dataset — still wrote the raw frame, and `/upload` stored it verbatim.
Server-side processing is structurally impossible there: the upload's hash contract is computed
over what the phone sent, so anything the server changed would fail its own check. It has to
happen before the write.

CI never builds Swift, so the rules that must hold are read out of the sources, in the shape of
the `/screen` no-persistence test.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ios" / "FrontdoorCapture"
CONTROLLER = APP / "Capture" / "CaptureController.swift"
PRIVACY = APP / "Capture" / "CapturePrivacy.swift"


def controller():
    return "\n".join(
        re.sub(r"//.*", "", line)
        for line in CONTROLLER.read_text(encoding="utf-8").splitlines()
    )


def body_of(source, signature):
    return source.split(signature, 1)[1].split("\n    }", 1)[0]


def test_every_write_is_given_processed_bytes():
    """The one rule. Both writers must hand the writer something a privacy step produced."""
    source = controller()
    calls = re.findall(r"CaptureWriter\.write\((.{0,220})", source, re.S)
    assert calls, "no CaptureWriter.write call found; this guard is pinning nothing"
    for call in calls:
        assert "processed.data" in call, (
            f"a capture is written with bytes no privacy step produced: {call[:120]!r}"
        )


def test_the_raw_frame_only_ever_goes_to_the_review_holder_and_the_processor():
    """Where the unprocessed bytes are allowed to travel, stated exactly.

    They legitimately exist in memory: the review gate shows the operator the photo before it
    becomes a capture. What they may never do is reach disk or the network. So the camera's bytes
    go to `PendingReview` and nowhere else, and the held bytes go to `CapturePrivacy` and nowhere
    else -- anything further is a path this guard has not seen.

    Matched over a window rather than a line, because both call sites wrap.
    """
    source = controller()
    allowed = {
        "captured.imageData": "PendingReview(",
        "pending.imageData": "CapturePrivacy.process(",
    }
    for raw, destination in allowed.items():
        uses = [m.start() for m in re.finditer(re.escape(raw), source)]
        assert uses, f"{raw} is gone; this guard is pinning nothing"
        for at in uses:
            window = source[max(0, at - 220):at]
            assert destination in window, (
                f"unprocessed bytes travel somewhere new: "
                f"...{source[max(0, at - 90):at + 40].strip()!r}"
            )


def test_the_camera_path_processes_before_it_writes():
    body = body_of(controller(), "private func commit(")
    assert "CapturePrivacy.process(" in body
    assert body.index("CapturePrivacy.process(") < body.index("CaptureWriter.write(")


def test_a_capture_that_cannot_be_processed_is_not_written():
    """Fails closed. An unblurred frame on disk is the thing this exists to prevent."""
    body = body_of(controller(), "private func commit(")
    failure = body.split("case .failure(let failure):", 1)[1].split("}", 1)[0]
    assert "return" in failure, "processing failure must abandon the capture, not fall through"
    assert body.index("case .failure(let failure):") < body.index("CaptureWriter.write(")


# --- the design decision that keeps intrinsics honest -------------------------


def test_the_camera_processor_does_not_rotate_the_stored_grid():
    """The importer bakes rotation into the pixels. This one must not, and the reason is D-037.

    The sidecar says width, height, intrinsics fx/fy/cx/cy, distortion_center and the roi points
    are all expressed in the grid the file's pixels are STORED in. Rotate here and every one of
    them describes a grid that no longer exists, with nothing to detect it.
    """
    source = PRIVACY.read_text(encoding="utf-8")
    assert "kCGImageSourceCreateThumbnailWithTransform" not in source, (
        "the camera processor rotates the stored pixels; the sidecar's intrinsics would be wrong"
    )
    assert "CGImageSourceCreateImageAtIndex" in source, "it must decode the stored grid as-is"


def test_the_orientation_tag_is_written_back():
    """Dropping it would make the stored image decode sideways for the screening model."""
    source = PRIVACY.read_text(encoding="utf-8")
    destination = source.split("CGImageDestinationAddImage(", 1)[1].split("]", 1)[0]
    assert "kCGImagePropertyOrientation" in destination


def test_nothing_else_is_carried_over_from_the_original_metadata():
    """GPS goes because a fresh dictionary is written, not because the camera omitted it."""
    source = PRIVACY.read_text(encoding="utf-8")
    destination = source.split("CGImageDestinationAddImage(", 1)[1].split("]", 1)[0]
    for tag in ("kCGImagePropertyGPSDictionary", "CGImageSourceCopyPropertiesAtIndex"):
        assert tag not in destination, f"{tag} suggests original metadata is being reused"
