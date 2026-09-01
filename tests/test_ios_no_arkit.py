"""The capture app must never reach ARKit (D-015, TICK-021).

ARKit's visual-inertial odometry recovers metric scale from motion. The method under test may
consume one RGB still, intrinsics and gravity — nothing motion-derived — so if no AR session is
ever started, motion-derived scale is not merely forbidden, it is unavailable.

Xcode enforces this at build time via ios/Scripts/assert-no-arkit.sh. That guard only runs on a
Mac. This test asserts the same rule from CI, which runs on Linux with no Xcode, so the boundary
holds on every pull request rather than only when someone happens to build the app.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
IOS_SOURCES = REPO_ROOT / "ios" / "FrontdoorCapture"
GUARD = REPO_ROOT / "ios" / "Scripts" / "assert-no-arkit.sh"

# Matches code, not prose. The codebase has to be able to name ARKit in comments explaining why
# it is excluded; what must never appear is an import or an AR* symbol.
FORBIDDEN = re.compile(
    r"^\s*(@_exported\s+)?import\s+(ARKit|RealityKit)\b"
    r"|\b(ARSession|ARConfiguration|ARWorldTrackingConfiguration|ARFrame|ARAnchor|ARSCNView|ARView)\b"
)


def swift_sources():
    return sorted(IOS_SOURCES.rglob("*.swift"))


def test_the_capture_app_has_sources_to_check():
    """Guards the guard: an empty glob would make every assertion below vacuously true."""
    assert swift_sources(), f"no Swift sources under {IOS_SOURCES}"


@pytest.mark.parametrize("source", swift_sources(), ids=lambda p: p.name)
def test_no_arkit_reference_in_capture_app(source):
    offending = [
        f"{source.relative_to(REPO_ROOT)}:{n}: {line.strip()}"
        for n, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1)
        if FORBIDDEN.search(line)
    ]
    assert not offending, "ARKit reached the capture app (D-015):\n" + "\n".join(offending)


def test_the_app_links_avfoundation_and_coremotion():
    """D-014 names the stack positively, not just by what it excludes.

    Checks linked frameworks rather than the whole file: project.yml mentions ARKit by name in the
    guard build phase, which is the opposite of a violation.
    """
    spec = (REPO_ROOT / "ios" / "project.yml").read_text(encoding="utf-8")
    linked = set(re.findall(r"- sdk:\s*(\S+)", spec))
    assert "AVFoundation.framework" in linked
    assert "CoreMotion.framework" in linked
    forbidden_frameworks = re.compile(r"\b(ARKit|RealityKit)\b")
    assert not {f for f in linked if forbidden_frameworks.search(f)}, (
        f"forbidden framework linked: {linked}"
    )


def test_the_xcode_guard_script_agrees_with_this_test(tmp_path):
    """The build-time guard and the CI guard must not drift apart.

    Runs the shell script against a scratch directory containing a forbidden symbol and asserts it
    fails, then against a clean one and asserts it passes. Without this, the two could disagree and
    only the weaker one would be enforced.
    """
    if not GUARD.exists():
        pytest.skip("guard script not present")

    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "Fine.swift").write_text("import AVFoundation\n", encoding="utf-8")
    assert subprocess.run([str(GUARD), str(clean)], capture_output=True).returncode == 0

    dirty = tmp_path / "dirty"
    dirty.mkdir()
    (dirty / "Bad.swift").write_text("import ARKit\n", encoding="utf-8")
    result = subprocess.run([str(GUARD), str(dirty)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "ARKit" in result.stderr


def test_the_xcode_guard_also_catches_a_linked_framework(tmp_path):
    """Importing ARKit is not the only way to link it.

    A `- sdk: ARKit.framework` dependency links the framework with no import anywhere, so a guard
    that only greps Swift would pass while ARKit is in the target.
    """
    if not GUARD.exists():
        pytest.skip("guard script not present")

    scratch = tmp_path / "yml"
    scratch.mkdir()
    (scratch / "Fine.swift").write_text("import AVFoundation\n", encoding="utf-8")
    (scratch / "project.yml").write_text(
        "targets:\n  X:\n    dependencies:\n      - sdk: ARKit.framework\n", encoding="utf-8"
    )
    result = subprocess.run([str(GUARD), str(scratch)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "project.yml" in result.stderr


def test_the_guard_allows_prose_that_names_arkit(tmp_path):
    """The codebase must be able to explain its own boundary.

    An earlier guard matched the bare word and failed the build on a comment saying why ARKit is
    excluded. A rule that punishes documenting the rule gets deleted, so it has to match code.

    The residual limitation is deliberate: symbol tokens still match anywhere, so prose writes
    "AR session" rather than "ARSession". That is the convention the sources already follow, and
    it keeps one rule instead of a comment-stripping parser that the shell guard could not share.
    """
    if not GUARD.exists():
        pytest.skip("guard script not present")

    scratch = tmp_path / "prose"
    scratch.mkdir()
    (scratch / "Doc.swift").write_text(
        "// D-014 rejects ARKit precisely for frame size; no AR session is ever started.\n"
        "import AVFoundation\n",
        encoding="utf-8",
    )
    result = subprocess.run([str(GUARD), str(scratch)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
