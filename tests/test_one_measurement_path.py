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


def _arm_family():
    """Every class in `frontdoor.metrology` whose base chain reaches `Arm`, by name.

    Matching only the literal name `Arm` was not enough: a class extending `PendingArm` is an
    arm and evaded every check here. That is a plausible accident -- "extend the pending stub for
    a quick demo" -- not only an adversarial one. Collected by fixpoint so a new base class added
    to the package is covered without anyone remembering to add it to a list.
    """
    definitions = {
        node.name: set(_base_names(node))
        for _, tree in _modules(METROLOGY)
        for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    family = {"Arm"}
    while True:
        grown = {n for n, bases in definitions.items() if bases & family} | family
        if grown == family:
            return family
        family = grown


def _arm_names_in(tree, family):
    """The names THIS module can spell an arm base with, aliases included.

    `from frontdoor.metrology import Arm as Base` is the other way a name-based match is evaded,
    and it looks entirely innocent at the class definition.
    """
    local = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("frontdoor.metrology"):
            local |= {a.asname or a.name for a in node.names if a.name in family}
    # Subclasses defined in this module become arm bases themselves, so a two-step chain inside
    # one file is caught as well.
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    reachable = family | local
    while True:
        grown = {c.name for c in classes if set(_base_names(c)) & reachable} | reachable
        if grown == reachable:
            return reachable
        reachable = grown


def _arm_definitions(root):
    """(class name, path) for every arm implementation under `root`."""
    family = _arm_family()
    found = []
    for path, tree in _modules(root):
        reachable = _arm_names_in(tree, family)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and set(_base_names(node)) & reachable:
                found.append((node.name, path))
    return found


def _called_name(node):
    f = node.func
    return f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")


def test_every_arm_implementation_lives_in_the_metrology_package():
    """The one rule that makes "one library" true rather than aspirational.

    An arm defined anywhere else is a second measurement path by construction, whatever it is
    called and however thin it looks.
    """
    found = _arm_definitions(SRC)
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
    server_arms = _arm_definitions(SERVER)
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


# --- the scanner's own reach --------------------------------------------------------------
#
# The guards above pass on a repo nobody has attacked, so what actually protects them is that
# the matching is wide enough. A first version matched only the literal name `Arm` and a class
# extending `PendingArm` sailed past all of it (found in review on #225). These pin the reach
# so a later simplification cannot quietly narrow it again.


def test_the_arm_family_includes_subclasses_not_just_the_base():
    family = _arm_family()
    assert "Arm" in family
    assert {"CutArm", "PendingArm"} <= family, (
        f"the family is {sorted(family)}; a class extending one of these IS an arm, and matching "
        "only the base name lets it through"
    )


def test_an_aliased_import_still_counts_as_an_arm_base():
    """`from frontdoor.metrology import Arm as Base` looks innocent at the class definition."""
    tree = ast.parse(
        "from frontdoor.metrology import Arm as Base\n"
        "class Quiet(Base):\n    pass\n"
    )
    assert "Base" in _arm_names_in(tree, _arm_family())


def test_a_subclass_chain_inside_one_module_is_followed():
    tree = ast.parse(
        "from frontdoor.metrology import Arm\n"
        "class Mid(Arm):\n    pass\n"
        "class Leaf(Mid):\n    pass\n"
    )
    reachable = _arm_names_in(tree, _arm_family())
    assert {"Mid", "Leaf"} <= reachable
