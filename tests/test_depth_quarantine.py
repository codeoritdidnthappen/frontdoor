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


# --- the import boundary (TICK-057, #55) --------------------------------------------------
#
# D-020's guarantee is that the metrology code path cannot READ depth. Until now that was true by
# accident -- nothing happened to import it -- and an accident is not a guarantee. These walk the
# real import graph and fail the build the moment someone adds the import.

import ast
from pathlib import Path as _Path

SRC = _Path(__file__).resolve().parents[1] / "src"

#: The module that can read depth. Importing it is the act D-020 governs.
DEPTH_READER = "frontdoor.depth_access"

#: Everyone allowed to reach it, and why. Anything else is a quarantine breach.
PERMITTED_IMPORTERS = {
    # The credential probe, which proves the loader credential is denied on depth. It reads depth
    # to do that, which is exactly why it is not part of `frontdoor.storage`.
    "frontdoor.storage_probe",
}


def _module_name(path):
    return ".".join(path.relative_to(SRC).with_suffix("").parts).removesuffix(".__init__")


def _imports_of(path):
    """Every module this file imports, from its AST rather than by running it.

    Static on purpose: an import inside a branch that never executes still puts the module within
    reach, and a runtime check would miss it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module)
            found.update(f"{node.module}.{a.name}" for a in node.names)
    return found


def _all_modules():
    return {_module_name(p): p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts}


def _reaches(start_prefix, target):
    """Transitive closure of imports from every module under `start_prefix`.

    Returns the chain that reaches `target`, or None. A chain rather than a bool because the
    failure message has to name the import that has to be removed.
    """
    modules = _all_modules()
    starts = [m for m in modules if m == start_prefix or m.startswith(start_prefix + ".")]
    assert starts, f"no modules under {start_prefix}; this guard would pass vacuously"

    seen, queue = set(), [(m, [m]) for m in starts]
    while queue:
        name, chain = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        path = modules.get(name)
        if path is None:
            continue
        for imported in _imports_of(path):
            candidate = imported if imported in modules else imported.rsplit(".", 1)[0]
            if imported == target or candidate == target:
                return chain + [target]
            if candidate in modules and candidate not in seen:
                queue.append((candidate, chain + [candidate]))
    return None


def test_the_metrology_library_cannot_reach_the_depth_reader():
    """The whole of D-020, as a property of the code rather than a promise about it."""
    chain = _reaches("frontdoor.metrology", DEPTH_READER)
    assert chain is None, "the metrology library now reaches depth: " + " -> ".join(chain or [])


def test_the_server_cannot_reach_the_depth_reader():
    """D-033 gives the server a WRITE-ONLY depth token so the request path cannot read depth.

    That guarantee is hollow if the server's import graph reaches the reader anyway -- the token
    is one barrier, this is the other, and #55 asks for two independent ones.
    """
    chain = _reaches("frontdoor_server", DEPTH_READER)
    assert chain is None, "the server now reaches depth: " + " -> ".join(chain or [])


def test_the_dataset_loader_cannot_reach_the_depth_reader():
    """The loader is what the metrology path is handed. It must not carry a route to depth."""
    chain = _reaches("frontdoor.loader", DEPTH_READER)
    assert chain is None, "the loader now reaches depth: " + " -> ".join(chain or [])


def test_only_the_permitted_modules_import_the_depth_reader():
    """Enumerated rather than asserted-about-one-package, so a NEW module cannot quietly gain it."""
    importers = {
        name for name, path in _all_modules().items()
        if name != DEPTH_READER and DEPTH_READER in _imports_of(path)
    }
    unexpected = importers - PERMITTED_IMPORTERS
    assert not unexpected, (
        f"these modules import the depth reader and are not permitted to: {sorted(unexpected)}. "
        "Depth is read by the evaluation harness only (D-020)."
    )


def test_storage_itself_has_no_route_to_depth_at_all():
    """`frontdoor.storage` is imported by the loader and by the server, for IMAGE access.

    Any route to depth from here -- module-level or buried inside a function -- is a route those
    callers inherit. A function-local import was tried first and is not good enough: the module is
    still reachable, `storage.verify()` would still read depth, and a static walker is right to
    call that a breach. The credential probe lives in `frontdoor.storage_probe` for this reason.
    """
    assert DEPTH_READER not in _imports_of(SRC / "frontdoor" / "storage.py"), (
        "storage can reach the depth reader; everything that imports storage for images now "
        "inherits a route to depth"
    )


def test_the_loader_exposes_no_depth_surface_at_all():
    """#55 AC1: depth is ABSENT from the type, not merely unset."""
    from frontdoor import loader

    # Checked as NAMES, not as the word. loader.py's docstring says "Depth is not loaded", which
    # is the guarantee being asserted -- a test that forbids the word would delete the sentence
    # documenting the very property it exists to protect.
    tree = ast.parse((SRC / "frontdoor" / "loader.py").read_text(encoding="utf-8"))
    named = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            named.add(node.name)
        elif isinstance(node, ast.Name):
            named.add(node.id)
        elif isinstance(node, ast.Attribute):
            named.add(node.attr)
        elif isinstance(node, ast.arg):
            named.add(node.arg)
    offenders = sorted(n for n in named if "depth" in n.lower())
    assert not offenders, f"loader.py has depth-named bindings: {offenders}"
    for name in dir(loader):
        assert "depth" not in name.lower(), f"loader exposes {name!r}"


def test_the_guard_would_notice_an_import_being_added():
    """The control. A guard that cannot fail is not a guard.

    Points the same walker at a module the metrology library genuinely does reach, so a broken
    walker shows up here rather than as a permanent green.
    """
    chain = _reaches("frontdoor.metrology", "frontdoor.metrology.result")
    assert chain is not None, "the import walker found nothing at all; it is broken"
