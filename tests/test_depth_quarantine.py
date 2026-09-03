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


def _module_name(path, root=None):
    return ".".join(path.relative_to(root or SRC).with_suffix("").parts).removesuffix(".__init__")


def _package_of(module_name, is_package):
    """The package a relative import inside this module resolves against."""
    parts = module_name.split(".")
    return parts if is_package else parts[:-1]


def _imports_of(path, module_name=None):
    """Every module this file imports, from its AST rather than by running it.

    Static on purpose: an import inside a branch that never executes still puts the module within
    reach, and a runtime check would miss it.

    **Relative imports are resolved, not skipped.** An earlier version required `not node.level`,
    so `from .depth_access import depth_store` inside the loader was invisible while the whole
    suite stayed green and the loader read depth at runtime. The repo happens to use no relative
    imports today, which is exactly why nothing else would have warned us.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    if module_name is None:
        module_name = _module_name(path)
    base = _package_of(module_name, path.name == "__init__.py")

    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                prefix = ".".join(anchor + ([node.module] if node.module else []))
            elif node.module:
                prefix = node.module
            else:
                continue
            if prefix:
                found.add(prefix)
                # `from . import depth_access` carries the name in `names`, not in `module`.
                found.update(f"{prefix}.{a.name}" for a in node.names)
    return found


def _all_modules(root=None):
    root = root or SRC
    return {_module_name(p, root): p for p in root.rglob("*.py")
            if "__pycache__" not in p.parts}


def _reaches(start_prefix, target, root=None, exact=False):
    """Transitive closure of imports from every module under `start_prefix`.

    Returns the chain that reaches `target`, or None. A chain rather than a bool because the
    failure message has to name the import that has to be removed.
    """
    modules = _all_modules(root)
    if exact:
        # One module, not a package prefix. Checking a PACKAGE name expands to every module under
        # it, which for `frontdoor` includes the permitted probe -- so a per-module sweep has to
        # ask about each module alone. Ancestors are still seeded: importing a module runs its
        # package __init__.
        starts = [start_prefix] if start_prefix in modules else []
    else:
        starts = [m for m in modules if m == start_prefix or m.startswith(start_prefix + ".")]
    assert starts, f"no modules under {start_prefix}; this guard would pass vacuously"

    # Importing `frontdoor.storage` executes `frontdoor/__init__.py` first, so a package's own
    # __init__ is part of every descendant's reach. Leaving ancestors out let an import placed in
    # `frontdoor/__init__.py` pass every test while every module under it gained the route.
    def ancestors(name):
        parts = name.split(".")
        return [".".join(parts[:i]) for i in range(1, len(parts))
                if ".".join(parts[:i]) in modules]

    seeded = list(starts)
    for m in starts:
        seeded.extend(ancestors(m))

    seen, queue = set(), [(m, [m]) for m in dict.fromkeys(seeded)]
    while queue:
        name, chain = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        path = modules.get(name)
        if path is None:
            continue
        for imported in _imports_of(path, name):
            candidate = imported if imported in modules else imported.rsplit(".", 1)[0]
            if imported == target or candidate == target:
                return chain + [target]
            if candidate not in modules:
                continue
            for nxt in [candidate] + ancestors(candidate):
                if nxt == target:
                    return chain + [nxt]
                if nxt not in seen:
                    queue.append((nxt, chain + [nxt]))
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


NL = chr(10)


# --- controls: a guard that cannot fail is not a guard --------------------------------------
#
# The first version of this control asserted only that the walker found SOMETHING, one hop away.
# Deleting the walker's transitive traversal entirely left it green. These exercise the parts that
# do the work, against a synthetic tree so they cannot drift with the real one.


def _tree(root, files):
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def test_the_walker_follows_a_chain_it_cannot_see_in_one_hop(tmp_path):
    """Transitive traversal. `a` never mentions `d`; it is three hops away."""
    _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/a.py": "from pkg import b" + NL,
        "pkg/b.py": "from pkg import c" + NL,
        "pkg/c.py": "from pkg import d" + NL,
        "pkg/d.py": "",
    })
    chain = _reaches("pkg.a", "pkg.d", root=tmp_path)
    assert chain is not None, "the walker does not traverse transitively"
    assert len(chain) >= 4, "chain too short to prove traversal: " + str(chain)


def test_the_walker_resolves_relative_imports(tmp_path):
    """The blind spot that let `from .depth_access import depth_store` through the loader."""
    _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/a.py": "from .secret import thing" + NL,
        "pkg/secret.py": "",
    })
    assert _reaches("pkg.a", "pkg.secret", root=tmp_path) is not None, (
        "relative imports are invisible to the walker")


def test_the_walker_resolves_a_bare_relative_package_import(tmp_path):
    """`from . import secret` carries the name in `names`, not in `module`."""
    _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/a.py": "from . import secret" + NL,
        "pkg/secret.py": "",
    })
    assert _reaches("pkg.a", "pkg.secret", root=tmp_path) is not None


def test_the_walker_resolves_a_parent_relative_import(tmp_path):
    """`from ..secret import thing` climbs a level."""
    _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/secret.py": "",
        "pkg/sub/__init__.py": "",
        "pkg/sub/a.py": "from ..secret import thing" + NL,
    })
    assert _reaches("pkg.sub.a", "pkg.secret", root=tmp_path) is not None


def test_the_walker_counts_a_packages_own_init(tmp_path):
    """Importing `pkg.a` executes `pkg/__init__.py`, so what it imports is within reach."""
    _tree(tmp_path, {
        "pkg/__init__.py": "from pkg import secret" + NL,
        "pkg/a.py": "",
        "pkg/secret.py": "",
    })
    assert _reaches("pkg.a", "pkg.secret", root=tmp_path) is not None, (
        "an import in a package __init__ is invisible to the walker")


def test_the_walker_does_not_invent_edges(tmp_path):
    """The other half of the control: no false positives, or every test above is meaningless."""
    _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/a.py": "import os" + NL,
        "pkg/secret.py": "",
    })
    assert _reaches("pkg.a", "pkg.secret", root=tmp_path) is None


def test_no_module_outside_the_permitted_set_can_reach_depth():
    """Generalises the three named guards.

    Those cover the metrology library, the loader and the server. `screening`, `split`, `sidecar`,
    `manifest`, `precatalogue` and `seal_audit` were unguarded and could have gained a route
    through the permitted probe with nothing noticing. D-020's wording is about the metrology
    path; nothing in this repository has a reason to read depth except the harness, so the guard
    is the wider one.
    """
    modules = _all_modules()
    exempt = PERMITTED_IMPORTERS | {DEPTH_READER}
    breaches = {}
    for name in modules:
        if name in exempt or any(name.startswith(p + ".") for p in exempt):
            continue
        chain = _reaches(name, DEPTH_READER, exact=True)
        if chain:
            breaches[name] = " -> ".join(chain)
    assert not breaches, "modules that can reach depth and should not: " + str(sorted(breaches))


def test_a_dynamic_import_of_the_depth_reader_is_flagged():
    """`importlib.import_module("frontdoor.depth_access")` is invisible to an AST import walk.

    Cheaper than modelling dynamic imports: the module name has to appear as a string somewhere,
    so look for it. The repo already uses `importlib` in several modules, so the idiom is present.
    """
    offenders = []
    for name, path in _all_modules().items():
        if name in PERMITTED_IMPORTERS or name == DEPTH_READER:
            continue
        text = path.read_text(encoding="utf-8")
        if '"' + DEPTH_READER + '"' in text or "'" + DEPTH_READER + "'" in text:
            offenders.append(name)
    assert not offenders, (
        "these modules name the depth reader as a string, which an import walk cannot see: "
        + str(sorted(offenders)))


def test_no_document_still_names_the_moved_probe_command():
    """`python -m frontdoor.storage verify` now refuses loudly rather than running.

    It used to exit 0 in silence, because storage lost its `__main__` when the probe moved --
    so an operator following a stale runbook to check the D-033 write-only token got a clean exit
    and concluded it passed. A silent success is the worst answer a verification command can give.
    This keeps the pointers correct as well as the behaviour.
    """
    repo = SRC.parent
    stale = []
    for name in ("data/STORAGE.md", "docs/server-deploy.md", "docs/ticket-summaries.md",
                 ".env.example", "README.md", "ARCHITECTURE.md"):
        path = repo / name
        if path.exists() and "frontdoor.storage verify" in path.read_text(encoding="utf-8"):
            stale.append(name)
    assert not stale, f"these still name the moved command: {stale}"
