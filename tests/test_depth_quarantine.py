"""Depth is captured and forgotten — never read by the app (D-020, TICK-023).

Depth is recorded on every entrance because it is free once capture is instrumented and it
strengthens deliverable #5. Its value depends entirely on staying out of the method: if depth sits
where the metrology can reach it, it eventually gets used to tune, and the monocular-versus-LiDAR
comparison stops meaning anything.

TICK-023 states the rule as "no code in the app branches on a depth value". That is a property of
the source, so it is asserted from the source rather than left to review. One file is allowed to
touch the pixels — the one that converts and hashes the map on its way out — and nothing else may.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
IOS_SOURCES = REPO_ROOT / "ios" / "FrontdoorCapture"

#: The only file permitted to touch depth pixels: it converts the map to the documented format and
#: hashes it. It reads bytes; it never compares one to another.
WRITER = "DepthRecord.swift"

#: Reading the map, or sampling it, is how depth would leak into the method.
PIXEL_ACCESS = re.compile(
    r"\b(depthDataMap|CVPixelBufferGetBaseAddress|CVPixelBufferLockBaseAddress)\b"
)


def swift_sources():
    return sorted(IOS_SOURCES.rglob("*.swift"))


def test_there_are_sources_to_check():
    """Guards the guard: an empty glob would make every assertion below vacuously true."""
    assert swift_sources(), f"no Swift sources under {IOS_SOURCES}"


def test_the_permitted_writer_still_exists():
    """If DepthRecord.swift is renamed, the allowance below must move with it deliberately."""
    assert (IOS_SOURCES / "Capture" / WRITER).is_file(), (
        f"{WRITER} not found; update this guard's allowance rather than deleting it"
    )


@pytest.mark.parametrize(
    "source", [p for p in swift_sources() if p.name != WRITER], ids=lambda p: p.name
)
def test_no_depth_pixel_access_outside_the_writer(source):
    offending = [
        f"{source.relative_to(REPO_ROOT)}:{n}: {line.strip()}"
        for n, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1)
        if PIXEL_ACCESS.search(line)
    ]
    assert not offending, (
        "depth pixels are read outside "
        f"{WRITER}, which breaks the D-020 quarantine:\n" + "\n".join(offending)
    )
