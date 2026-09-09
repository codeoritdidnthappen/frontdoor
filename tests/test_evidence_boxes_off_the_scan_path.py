"""Boxes are a publish-time cost, and the live scan never pays it (TICK-467).

Locating the evidence costs about a minute of CPU per entrance. A live scan is
already about nineteen seconds from shutter to verdict, which is the product's
worst measured number, and a minute on top of it would not be a slower feature
-- it would be a different product.

So the cost is confined structurally rather than by intention. Three claims,
each pinned separately:

1. The publish path calls it. If someone deletes the call, this fails.
2. Neither endpoint mentions it, in any spelling.
3. Serving a scan does not even LOAD it. The detector, torch and transformers
   are absent from the module table of a process that has imported the app --
   the strongest available form of "this cannot run here", because a module
   that was never imported cannot be called by any code path in the request.

Latency itself is not asserted here. There is no wall-clock budget anywhere in
this suite, and inventing one that a slow CI box would fail is worse than
useless; what is enforceable is that the expensive thing is not reachable.
"""

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import pytest

from frontdoor import evidence_boxes, scan_publish

REPO = Path(__file__).resolve().parents[1]

#: Every spelling of the detector that would matter if it appeared on a request
#: path. The bare module name is not enough: an endpoint could import the
#: pipeline itself and pay the same minute.
DETECTOR_SPELLINGS = (
    "evidence_boxes", "locate_evidence", "load_detector", "owlvit", "OwlViT",
    "zero-shot-object-detection", "transformers", "torch",
)

#: The two request handlers a photograph reaches. POST /screen assesses and
#: retains nothing; POST /screen/publish assesses and stores.
LIVE_PATH_MODULES = (
    REPO / "src" / "frontdoor_server" / "scan_view.py",
    REPO / "src" / "frontdoor_server" / "screen_view.py",
)


def _code_only(path):
    """The module's source with comments and docstrings removed.

    Prose describing a rule must not be able to satisfy or violate it -- the
    same discipline tests/test_capture_queue_invariants.py applies.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            if ast.get_docstring(node) is not None:
                node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


# --- 1. the publish path calls it --------------------------------------------


def test_the_publish_path_is_where_the_boxes_are_made():
    source = _code_only(REPO / "src" / "frontdoor" / "scan_publish.py")
    assert "locate_evidence" in source
    assert "load_detector" in source
    assert "evidence_boxes" in source


def test_the_publish_run_does_no_detection_unless_it_is_asked_to():
    """Opt-in: --evidence-boxes, and a detector of None does nothing at all.

    A publish run that only wants the verdicts must not silently acquire an
    hour of CPU, so the default is off and the off state is a no-op rather
    than a detector that returns nothing.
    """
    assert inspect.signature(
        scan_publish.assess_publishable).parameters["detector"].default is None
    # (searched, boxes). Nothing ran, and the record will say nothing ran --
    # which is not the same claim as "we looked and found nothing".
    assert scan_publish._locate_boxes("E-001", [b"frame"], None) == (False, {})


# --- 2. neither endpoint mentions it -----------------------------------------


@pytest.mark.parametrize("path", LIVE_PATH_MODULES, ids=lambda p: p.name)
@pytest.mark.parametrize("spelling", DETECTOR_SPELLINGS)
def test_no_live_scan_endpoint_names_the_detector(path, spelling):
    source = _code_only(path)
    assert spelling not in source, (
        f"{path.name} references {spelling!r}; locating evidence costs about a "
        "minute per entrance and a live scan is already ~19s shutter to verdict"
    )


def test_the_live_publish_endpoint_writes_a_record_without_boxes():
    """The record constructor is shared; the argument is not passed here.

    POST /screen/publish stores the photograph and writes the scan record. It
    must not also locate evidence, so it must not hand new_scan_record an
    evidence_boxes argument -- there would be nothing to hand it that had not
    cost the user a minute.
    """
    tree = ast.parse((REPO / "src" / "frontdoor_server" / "scan_view.py")
                     .read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name)
             and node.func.id == "new_scan_record"]
    assert calls, "scan_view no longer builds a scan record; this test is stale"
    for call in calls:
        assert "evidence_boxes" not in {kw.arg for kw in call.keywords}


# --- 3. serving a scan does not load it --------------------------------------


def test_importing_the_server_does_not_load_the_detector():
    probe = (
        "import sys;"
        "import frontdoor_server.app as app;"
        "app.create_app();"
        "leaked=[m for m in ('frontdoor.evidence_boxes','transformers','torch')"
        " if m in sys.modules];"
        "print(','.join(leaked))"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True, text=True, cwd=REPO,
        env={**__import__("os").environ, "PYTHONPATH": str(REPO / "src")},
    )
    assert done.returncode == 0, done.stderr
    leaked = done.stdout.strip()
    assert leaked == "", (
        f"a server process loads {leaked}; the detector must not be reachable "
        "from a request, and torch alone is hundreds of megabytes of RSS in a "
        "worker sized for image decoding"
    )


def test_the_detector_is_an_optional_extra_the_server_does_not_install():
    """It is not in the runtime dependencies, and that is deliberate.

    frontdoor.evidence_boxes imports transformers lazily, inside the function
    that needs it, so the publish tool is the only thing that ever pays for the
    import and a machine without it publishes verdicts and no boxes.
    """
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    runtime = pyproject.split("dependencies = [", 1)[1].split("]", 1)[0]
    assert "torch" not in runtime and "transformers" not in runtime
    assert "boxes = [" in pyproject

    tree = ast.parse(inspect.getsource(evidence_boxes))
    top_level = {
        alias.name.split(".")[0]
        for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in tree.body if isinstance(node, ast.ImportFrom)
    }
    assert "transformers" not in top_level and "torch" not in top_level
