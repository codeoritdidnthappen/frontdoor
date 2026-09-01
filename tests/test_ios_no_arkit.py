"""The capture app must never reach ARKit (D-015, TICK-021).

ARKit's visual-inertial odometry recovers metric scale from motion. The method under test may
consume one RGB still, intrinsics and gravity — nothing motion-derived — so if no AR session is
ever started, motion-derived scale is not merely forbidden, it is unavailable.

**These tests invoke `ios/Scripts/assert-no-arkit.sh` rather than reimplementing its rule.** An
earlier version kept a Python copy of the regex; mutation testing showed the shell guard could be
broken while the suite stayed green, because the tests were asserting against the copy (#154). The
script is POSIX sh and plain grep, so it runs on a Linux CI runner with no Xcode — there is no
reason to have two implementations, and #151 is the record of what having two cost.
"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
IOS_TREE = REPO_ROOT / "ios"
GUARD = REPO_ROOT / "ios" / "Scripts" / "assert-no-arkit.sh"


def guard(target: Path) -> subprocess.CompletedProcess:
    return subprocess.run([str(GUARD), str(target)], capture_output=True, text=True)


def swift_tree(tmp_path: Path, source: str) -> Path:
    """A scratch tree holding one Swift file, so the guard is exercised the way Xcode runs it."""
    (tmp_path / "Sources").mkdir(parents=True, exist_ok=True)
    (tmp_path / "Sources" / "Subject.swift").write_text(source, encoding="utf-8")
    return tmp_path


def test_the_guard_exists_and_is_executable():
    """Guards the guard: every assertion below is vacuous if the script cannot run."""
    assert GUARD.is_file(), f"{GUARD} is missing"
    result = guard(IOS_TREE)
    assert result.returncode in (0, 1), f"guard did not run: {result.stderr}"


def test_the_real_tree_passes():
    """The shipped app must satisfy its own boundary, or nothing below means anything."""
    result = guard(IOS_TREE)
    assert result.returncode == 0, f"ios/ tree fails its own ARKit guard:\n{result.stderr}"


#: Every way ARKit has actually reached, or could reach, a Swift file. Each of the attribute forms
#: was a live bypass at some point: bare imports, then @_exported only (#148), then attributes
#: without arguments (#153).
FORBIDDEN_SOURCES = [
    "import ARKit",
    "    import ARKit",
    "import RealityKit",
    "@testable import ARKit",
    "@_exported import ARKit",
    "@preconcurrency import ARKit",
    "@_implementationOnly import ARKit",
    "@_spi(Internal) import ARKit",
    "@_documentation(visibility: internal) import ARKit",
    "@testable @_exported import ARKit",
    "let session = ARSession()",
    "let config = ARWorldTrackingConfiguration()",
    "let anchor: ARAnchor? = nil",
    "let camera: ARCamera? = nil",
    "let view = ARSCNView()",
    "let mesh: ARMeshAnchor? = nil",
    "let geo: ARGeoTrackingConfiguration.Type? = nil",
    "let frame: ARFrame? = nil",
]


@pytest.mark.parametrize("source", FORBIDDEN_SOURCES, ids=lambda s: s.strip()[:44])
def test_forbidden_forms_fail_the_guard(source, tmp_path):
    result = guard(swift_tree(tmp_path, source + "\n"))
    assert result.returncode == 1, (
        f"the guard accepted a forbidden form, so D-015 is not enforced:\n  {source}"
    )


#: The guard must let the codebase describe its own boundary. It failed the build on a comment
#: once (#152), and a rule that punishes documenting the rule is a rule someone deletes.
ALLOWED_SOURCES = [
    "// D-015 forbids ARKit; see ARCHITECTURE.md section 2.\nimport AVFoundation\n",
    "/*\n D-015 excludes ARKit. Forms such as\n@testable import ARKit\n are forbidden.\n*/\nimport AVFoundation\n",
    "// Not allowed: import ARKit, ARSession, ARGeoTrackingConfiguration.\nimport CoreMotion\n",
    'let note = "see ARCHITECTURE.md"\n',
    "import AVFoundation\nimport CoreMotion\n",
]


@pytest.mark.parametrize("source", ALLOWED_SOURCES, ids=lambda s: s.strip().splitlines()[0][:44])
def test_prose_and_ordinary_imports_pass_the_guard(source, tmp_path):
    result = guard(swift_tree(tmp_path, source))
    assert result.returncode == 0, (
        f"the guard rejected legitimate code or prose:\n{source}\n{result.stderr}"
    )


def test_a_linked_framework_in_project_yml_fails(tmp_path):
    """Importing is not the only way to link a framework."""
    (tmp_path / "Sources").mkdir()
    (tmp_path / "Sources" / "Subject.swift").write_text("import AVFoundation\n")
    (tmp_path / "project.yml").write_text(
        "targets:\n  App:\n    dependencies:\n      - sdk: ARKit.framework\n"
    )
    assert guard(tmp_path).returncode == 1


def test_an_empty_tree_does_not_pass_vacuously(tmp_path):
    """A guard reporting success over nothing would hide a renamed or moved source tree.

    Without this, `test_the_real_tree_passes` goes green over zero files if ios/FrontdoorCapture
    is ever moved, and D-015 is unenforced with a green check.
    """
    assert guard(tmp_path / "does-not-exist").returncode == 1
    assert guard(tmp_path).returncode == 1


def test_the_guard_reports_how_many_files_it_scanned(tmp_path):
    """The count is what makes a vacuous pass visible to a human reading CI output."""
    result = guard(IOS_TREE)
    assert result.returncode == 0
    assert "swift files scanned" in result.stdout, result.stdout


def test_a_source_in_a_path_with_spaces_is_still_scanned(tmp_path):
    """Word-splitting find(1) skipped these silently, which is a bypass of the only D-015 rule."""
    spaced = tmp_path / "My Sources"
    spaced.mkdir(parents=True)
    (spaced / "Leak.swift").write_text("import ARKit\n", encoding="utf-8")
    assert guard(tmp_path).returncode == 1
