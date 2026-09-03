"""There is exactly one place a measurement can come from (EPIC-06 AC4, R-11).

R-11 is the risk the whole architecture is shaped around: if the demo app and the evaluation
harness stop running the same library, Demo Day exhibits behaviour the error budget never
characterised, and both of them look fine. ARCHITECTURE section 1 answers it by allowing exactly
one implementation -- `frontdoor.metrology` -- with the server and the harness as thin
entrypoints over it.

Nothing enforced that. EPIC-06 AC4 asks for "no second, demo-only measurement path anywhere in
the repo", and it was the one criterion on that epic with no check behind it at all -- true today
by everyone's good intentions, which is exactly the kind of invariant that is discovered broken.

AST scans, not text searches, for the reason `test_metrology_scaffold.py` gives: a regex is
satisfied by a word in a docstring and fooled by one in a comment.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
METROLOGY = SRC / "frontdoor" / "metrology"
SERVER = SRC / "frontdoor_server"


def _modules(root):
    files = sorted(root.rglob("*.py"))
    assert files, f"no Python under {root}; this guard would pass vacuously"
    return [(f, ast.parse(f.read_text(encoding="utf-8"))) for f in files]


def _base_names(node):
    for b in node.bases:
        if isinstance(b, ast.Name):
            yield b.id
        elif isinstance(b, ast.Attribute):
            yield b.attr


def _called_name(node):
    f = node.func
    return f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")


def test_every_arm_implementation_lives_in_the_metrology_package():
    """The one rule that makes "one library" true rather than aspirational.

    An arm defined anywhere else is a second measurement path by construction, whatever it is
    called and however thin it looks.
    """
    found = []
    for path, tree in _modules(SRC):
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and "Arm" in set(_base_names(node)):
                found.append((node.name, path))

    assert found, "no Arm subclass found anywhere; the scan is not looking at the right thing"
    outside = [(n, p) for n, p in found if METROLOGY not in p.parents]
    assert not outside, f"Arm implementations outside frontdoor.metrology: {outside}"


def test_nothing_outside_the_metrology_package_registers_an_arm():
    """Registration is the other way a second path becomes reachable: an arm defined legally and
    registered from a module that has no business owning one."""
    offenders = [
        path for path, tree in _modules(SRC)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _called_name(node) == "register_arm"
        and METROLOGY not in path.parents
    ]
    assert not offenders, f"register_arm called outside frontdoor.metrology: {offenders}"


def test_the_server_defines_no_arm_of_its_own():
    """The server is a thin entrypoint (ARCHITECTURE section 6). An arm living here would be
    reachable on stage and invisible to the harness -- R-11 exactly."""
    server_arms = [
        (node.name, path) for path, tree in _modules(SERVER)
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and "Arm" in set(_base_names(node))
    ]
    assert not server_arms, f"the server defines its own arm(s): {server_arms}"


#: Copying a constant is not deriving a value. `dict(_CUT_ARM)` is how app.py avoids repeating
#: the same placeholder twice; the copy is followed to its source below, so the exemption cannot
#: be used to smuggle in a computed one.
_COPY_BUILTINS = {"dict", "list", "tuple"}


def _module_constants(tree):
    return {
        t.id: node.value
        for node in tree.body if isinstance(node, ast.Assign)
        for t in node.targets if isinstance(t, ast.Name)
    }


def _assert_literal_only(node, constants, seen=()):
    """No arithmetic, and no call except a container copy of another literal constant."""
    if isinstance(node, (ast.BinOp, ast.UnaryOp, ast.Compare, ast.IfExp)):
        raise AssertionError(
            f"the stub derives a value ({type(node).__name__}: {ast.unparse(node)[:60]}); "
            "the server must not compute a measurement"
        )
    if isinstance(node, ast.Call):
        name = _called_name(node)
        assert name in _COPY_BUILTINS, (
            f"the stub calls {name!r}; placeholder values must be literals or copies of them, "
            "so the server cannot derive a number"
        )
        # Only the arguments; `node.func` is the builtin's own Name and is not a value.
        for arg in [*node.args, *(kw.value for kw in node.keywords)]:
            _assert_literal_only(arg, constants, seen)
        return
    if isinstance(node, ast.Name):
        if node.id in seen:
            return
        assert node.id in constants, (
            f"the stub references {node.id!r}, which is not a module-level constant in app.py; "
            "it cannot be shown to be literal"
        )
        _assert_literal_only(constants[node.id], constants, seen + (node.id,))
        return
    for child in ast.iter_child_nodes(node):
        _assert_literal_only(child, constants, seen)


def test_the_servers_stub_arms_are_literals_and_not_computed():
    """`STUB_ARMS` is placeholder DATA, and it has to stay data.

    A number the server calculates is a measurement the metrology library did not make and the
    error budget never saw -- the second path arriving as a "temporary" convenience. Recomputing
    it here would satisfy every other test in the suite. When TICK-061 replaces the stub with the
    real library this test should be deleted deliberately, not quietly relaxed.
    """
    tree = ast.parse((SERVER / "app.py").read_text(encoding="utf-8"))
    constants = _module_constants(tree)
    value = constants.get("STUB_ARMS")
    assert value is not None, "STUB_ARMS is no longer a module-level assignment in app.py"
    _assert_literal_only(value, constants)


def test_the_stub_guard_would_notice_a_computed_value():
    """The guard above passes on code nobody has broken yet, so prove it can fail.

    Without this, a rewrite that stopped detecting arithmetic would leave the suite green and
    EPIC-06 AC4 unenforced again -- which is the state this file was written to end.
    """
    tree = ast.parse("A = 1\nSTUB_ARMS = {'A': {'rise_in': A * 2}}\n")
    constants = _module_constants(tree)
    with pytest.raises(AssertionError, match="derives a value"):
        _assert_literal_only(constants["STUB_ARMS"], constants)
