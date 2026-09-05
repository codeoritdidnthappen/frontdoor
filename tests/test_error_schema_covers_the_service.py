"""Every error token this service emits is a token the committed schema allows (TICK-264, #264).

measure_error.schema.json describes the error body of every path on this service — TICK-225 made
that true of the shape — and it pins `error` to an enum. Nothing ever checked that claim against
the handlers, so /upload and /screen shipped tokens the enum never listed: a client validating a
real response against the committed contract would reject it. Growing the enum fixes today. This
guard is what stops it rotting again.

The token set is derived FROM THE SOURCE, never repeated here. A guard that hardcodes the list it
asserts against passes by construction and catches nothing, which is what #151 and #154 cost.

A token reaches the wire in one of three shapes, all of them in the tree today:

    error("missing image", ...)                            a literal at the call site
    _error(_HTTP_ERROR_MESSAGES.get(code, "..."), ...)     a lookup in a module-level table
    error(failure[0], ...)                                 the first half of a (token, detail) pair

The scan resolves all three, and a call site it cannot resolve FAILS the suite rather than being
skipped — so a fourth shape has to be taught to this guard instead of quietly slipping past it.
"""

import ast
from pathlib import Path

import pytest

from frontdoor_server.app import ERROR_SCHEMA

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PACKAGE = REPO_ROOT / "src" / "frontdoor_server"

#: The helpers that build an error body: app.py's `_error`, screen_view.py's own, and the name
#: upload_view.py receives it under. Matched as bare names, so `logger.error(...)` is not one.
ERROR_HELPERS = {"error", "_error"}

#: The modules that emit error tokens today. Named so that renaming one fails this guard loudly
#: rather than silently shrinking what it covers; a NEW view is picked up by the glob for free.
KNOWN_EMITTERS = {
    "app.py", "claim_view.py", "label_view.py", "scan_view.py", "screen_view.py", "upload_view.py"
}


def server_sources():
    return sorted(SERVER_PACKAGE.rglob("*.py"))


def _string_constants(node):
    return {
        n.value
        for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }


def _module_tables(tree):
    """Module-level dicts holding string values, by name — the `_HTTP_ERROR_MESSAGES` shape."""
    tables = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        values = {
            v.value
            for v in node.value.values
            if isinstance(v, ast.Constant) and isinstance(v.value, str)
        }
        for target in node.targets:
            if isinstance(target, ast.Name) and values:
                tables[target.id] = values
    return tables


def _returned_pair_tokens(tree):
    """Tokens carried back to a view as the first half of a literal (token, detail) pair.

    Scoped to `return` statements: a module-level pair of strings is a constant like
    `KINDS = ("image", "depth")`, not a failure being handed to a caller.
    """
    tokens = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        for inner in ast.walk(node.value):
            if not isinstance(inner, ast.Tuple) or len(inner.elts) != 2:
                continue
            first = inner.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                tokens.add(first.value)
    return tokens


def _tokens_at_call_site(arg, tables, pair_tokens):
    """Every token this first argument can carry; empty when the scan cannot tell.

    Over-approximating on purpose: a subscript is resolved to every pair token in the module
    rather than to the one branch it came from. Naming a token the handler cannot actually reach
    is harmless — it only widens the enum — while missing one is the defect this guard exists for.
    """
    tokens = _string_constants(arg)
    for name in {n.id for n in ast.walk(arg) if isinstance(n, ast.Name)}:
        tokens |= tables.get(name, set())
    if any(isinstance(n, ast.Subscript) for n in ast.walk(arg)):
        tokens |= pair_tokens
    return tokens


def emitted_tokens(source):
    """Read one module's source. Returns (tokens, unresolved call sites)."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    tables = _module_tables(tree)
    pair_tokens = _returned_pair_tokens(tree)
    tokens = set()
    unresolved = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in ERROR_HELPERS:
            continue
        found = _tokens_at_call_site(node.args[0], tables, pair_tokens) if node.args else set()
        if found:
            tokens |= found
        else:
            argument = ast.unparse(node.args[0]) if node.args else "<no positional token>"
            unresolved.append(f"{source.name}:{node.lineno}: {argument}")
    return tokens, unresolved


def test_there_are_sources_to_check():
    """Guards the guard: an empty glob would make every assertion below vacuously true."""
    assert server_sources(), f"no Python sources under {SERVER_PACKAGE}"


@pytest.mark.parametrize("name", sorted(KNOWN_EMITTERS))
def test_the_scan_still_finds_the_modules_that_emit_errors(name):
    """A renamed or restructured view must break this guard, not silently leave it covering less."""
    tokens, _ = emitted_tokens(SERVER_PACKAGE / name)
    assert tokens, f"{name} emits no error tokens the scan can see; has it moved or been renamed?"


@pytest.mark.parametrize("source", server_sources(), ids=lambda p: p.name)
def test_every_error_call_site_names_a_token_the_scan_can_see(source):
    """An unreadable call site is a hole in the guard, so it fails rather than being skipped."""
    _, unresolved = emitted_tokens(source)
    assert not unresolved, (
        "this guard cannot tell which token these call sites emit, so it cannot check them "
        "against the schema. Spell the token at the call site, or teach the scan the new "
        "shape:\n" + "\n".join(unresolved)
    )


@pytest.mark.parametrize("source", server_sources(), ids=lambda p: p.name)
def test_every_token_the_service_emits_is_in_the_schema_enum(source):
    allowed = set(ERROR_SCHEMA["properties"]["error"]["enum"])
    tokens, _ = emitted_tokens(source)
    missing = sorted(tokens - allowed)
    assert not missing, (
        f"{source.name} emits error tokens that measure_error.schema.json does not allow, "
        "so a client validating against the committed contract would reject a real response. "
        "Add them to the enum, or stop emitting them:\n" + "\n".join(missing)
    )


def test_the_enum_lists_every_token_once():
    """Duplicates are invisible to `check_schema` and hide a token counted twice by review."""
    enum = ERROR_SCHEMA["properties"]["error"]["enum"]
    duplicates = sorted({token for token in enum if enum.count(token) > 1})
    assert not duplicates, "measure_error.schema.json repeats: " + ", ".join(duplicates)


#: One module per shape a token can take, each smuggling in a token the enum does not list. If the
#: scan cannot see it here, it cannot see it in a view either, and this whole file passes on
#: nothing. Mutation testing is what proved the previous generation of source guards hollow (#154).
NEW_TOKEN_SHAPES = {
    "literal at the call site": 'def view(error):\n    return error("brand new token", "detail")\n',
    "module-level table": (
        '_TABLE = {418: "brand new token"}\n\n'
        'def view():\n    return _error(_TABLE.get(code, "internal error"), "detail")\n'
    ),
    "(token, detail) pair": (
        'def helper():\n    return False, ("brand new token", "why")\n\n'
        'def view(error):\n    return error(failure[0], "detail")\n'
    ),
}


@pytest.mark.parametrize("shape", sorted(NEW_TOKEN_SHAPES))
def test_the_scan_sees_a_token_written_in_any_shape_the_service_uses(shape, tmp_path):
    source = tmp_path / "subject_view.py"
    source.write_text(NEW_TOKEN_SHAPES[shape], encoding="utf-8")
    tokens, unresolved = emitted_tokens(source)
    assert "brand new token" in tokens, f"the scan is blind to a token written as a {shape}"
    assert not unresolved
