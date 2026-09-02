"""The core library's shape and its structural guarantees (TICK-040, #34).

There is no geometry here yet. What is tested is the contract every arm will sit
behind, and the two structural claims ARCHITECTURE section 5 makes about this
package: it performs no I/O of its own, and depth is unreachable from it (D-020).

The guards are AST scans rather than text searches. A regex over source would be
satisfied by the word `open` in a docstring and fooled by it in a comment -- the
same failure the iOS ARKit guard had to be rewritten to avoid (#146, #151).
"""

import ast
from pathlib import Path

import pytest

from frontdoor.metrology import (
    ADALine,
    ARM_NAMES,
    AbsentReason,
    PendingArm,
    Arm,
    ArmAbsent,
    ArmNotImplemented,
    Interval,
    LineDecision,
    Measurement,
    ResultError,
    UnknownArm,
    Verdict,
    all_arms,
    get_arm,
    register_arm,
)

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "frontdoor" / "metrology"

#: ARCHITECTURE section 5: no network, no I/O beyond what the library is handed.
#:
#: An ALLOW-LIST, not a deny-list. A deny-list of stdlib names let every in-repo I/O
#: module straight through: `from frontdoor.loader import ...` splits to "frontdoor"
#: and passed, while `loader.py` reads the disk and `storage.py` talks to S3 over the
#: network. The guard's own claim was contradicted by a module it permitted.
ALLOWED_IMPORT_ROOTS = {
    "__future__",
    "abc",
    "dataclasses",
    "enum",
    "math",
    "typing",
    "frontdoor.metrology",
}
FORBIDDEN_CALLS = {"open", "eval", "exec", "__import__"}


def _import_roots(node):
    """Every module name an import node brings into scope."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        if node.level:  # a relative import cannot leave the package
            return []
        return [node.module or ""]
    return []


def _is_allowed(module):
    return any(
        module == allowed or module.startswith(allowed + ".")
        for allowed in ALLOWED_IMPORT_ROOTS
    )


def _sources(package=None):
    # rglob, not glob. ARCHITECTURE section 5 puts four arms behind this interface and
    # the natural home is `metrology/arms/`; with glob every guard here would silently
    # stop covering exactly the files most likely to violate it -- arms B and C are the
    # depth consumers.
    package = PACKAGE if package is None else package
    files = sorted(package.rglob("*.py"))
    assert files, f"no source files found under {package}; the guard would pass vacuously"
    for path in files:
        yield path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


# --- the interface -------------------------------------------------------------


def test_every_architecture_arm_resolves_by_name():
    """A caller switches arms by name, never by switching code path."""
    assert [arm.name for arm in all_arms()] == list(ARM_NAMES)
    for name in ARM_NAMES:
        assert get_arm(name).name == name


def test_an_unknown_arm_refuses_rather_than_returning_none():
    with pytest.raises(UnknownArm, match="unknown arm"):
        get_arm("D")


def test_a_reserved_arm_fails_loudly_instead_of_returning_a_plausible_zero():
    """The four names resolve today; their geometry is later tickets."""
    with pytest.raises(ArmNotImplemented, match="TICK-043"):
        get_arm("A").measure(object(), {})


def test_only_arm_a_is_free_of_the_camera_model():
    """ARCHITECTURE section 5: a homography from a known rectangle absorbs the projection."""
    assert get_arm("A").needs_intrinsics is False
    for name in ("A_prime", "B", "C"):
        assert get_arm(name).needs_intrinsics is True, name


def test_a_stub_arm_round_trips_through_the_interface():
    """Proves the contract before any geometry is written."""

    class _Stub(Arm):
        name = "C"
        needs_intrinsics = True

        def measure(self, image, sidecar):
            return Measurement(value=1.5, interval=Interval(1.0, 2.0), arm=self.name)

    original = get_arm("C")
    try:
        register_arm(_Stub())
        result = get_arm("C").measure(object(), {"capture_id": "cap-1"})
        assert isinstance(result, Measurement)
        assert result.value == 1.5 and result.arm == "C"
    finally:
        register_arm(original)
    assert isinstance(get_arm("C"), type(original))


def test_an_arm_cannot_be_registered_under_a_name_it_does_not_answer_to():
    class _Rogue(Arm):
        name = "Z"

        def measure(self, image, sidecar):
            raise AssertionError

    with pytest.raises(UnknownArm):
        register_arm(_Rogue())


def test_registering_a_class_instead_of_an_instance_is_caught_at_registration():
    """`register_arm` returns its argument, so it reads like a decorator.

    Used as one -- `@register_arm class ArmA(Arm): ...` -- the unbound CLASS registers
    successfully, and the mistake only surfaces later as
    `TypeError: measure() missing 1 required positional argument` from deep inside the
    harness, far from the line that caused it (review finding 3).
    """

    class _Unbound(Arm):
        name = "C"

        def measure(self, image, sidecar):
            raise AssertionError("never called")

    with pytest.raises(ResultError, match="expects an Arm instance"):
        register_arm(_Unbound)
    assert isinstance(get_arm("C"), PendingArm), "registry must be untouched"


def test_an_arm_cannot_be_instantiated_without_implementing_measure():
    class _Empty(Arm):
        name = "A"

    with pytest.raises(TypeError):
        _Empty()


# --- the three outcomes the wire contract keeps apart --------------------------


def test_a_measurement_cannot_exist_without_an_interval():
    """A point estimate cannot be judged against a line, only compared to it."""
    with pytest.raises(ResultError, match="no interval"):
        Measurement(value=1.5, interval=None, arm="A")


def test_a_measurement_must_lie_inside_its_own_interval():
    with pytest.raises(ResultError, match="outside its own interval"):
        Measurement(value=9.0, interval=Interval(1.0, 2.0), arm="A")


def test_an_inverted_interval_is_refused():
    with pytest.raises(ResultError, match="inverted"):
        Interval(low=2.0, high=1.0)


@pytest.mark.parametrize("low,high", [(float("-inf"), float("inf")), (float("nan"), 1.0), (0.0, float("inf"))])
def test_a_non_finite_interval_is_refused(low, high):
    """An unbounded interval straddles every line, so it abstains everywhere.

    It is precisely the "measurement with a very wide interval" this module splits its
    types to stop being read as an abstention -- and `Interval(nan, 1.0)` passed the
    inversion check, because `nan > 1.0` is False, then poisoned every aggregate over
    interval widths in the error budget.
    """
    with pytest.raises(ResultError, match="non-finite|inverted"):
        Interval(low=low, high=high)


def test_the_arm_a_prime_stub_from_the_frozen_schema_is_representable():
    """The case a single decision field could not express (review finding 1).

    `src/frontdoor_server/measure_response.schema.json` requires two independent
    verdicts per arm, and the committed `STUB_ARMS["A_prime"]` in the server abstains
    at the half-inch line while failing at the quarter-inch line. A `Measurement`
    carrying one `decision` could not be serialized into the frozen response at all.
    """
    m = Measurement(
        value=0.6,
        interval=Interval(0.4, 0.8),
        arm="A_prime",
        decisions={
            ADALine.HALF_INCH: LineDecision(Verdict.ABSTAIN, "the interval straddles the line"),
            ADALine.QUARTER_INCH: LineDecision(Verdict.FAIL),
        },
    )
    assert m.decisions[ADALine.HALF_INCH].verdict is Verdict.ABSTAIN
    assert m.decisions[ADALine.QUARTER_INCH].verdict is Verdict.FAIL


def test_an_abstain_verdict_must_carry_an_explanation():
    """An abstention that renders blank is indistinguishable from a broken client."""
    with pytest.raises(ResultError, match="requires an explanation"):
        LineDecision(Verdict.ABSTAIN)


def test_a_whitespace_explanation_does_not_count():
    """The schema constrains by pattern, not minLength, for exactly this reason."""
    with pytest.raises(ResultError, match="requires an explanation"):
        LineDecision(Verdict.ABSTAIN, "   ")


def test_a_reasoned_measurement_carries_both_lines_or_neither():
    """One line reasoned and the other missing cannot be serialized."""
    with pytest.raises(ResultError, match="BOTH lines"):
        Measurement(
            value=0.6, interval=Interval(0.4, 0.8), arm="A",
            decisions={ADALine.HALF_INCH: LineDecision(Verdict.PASS)},
        )


def test_an_unreasoned_measurement_is_not_an_abstention():
    """Empty means "not yet compared to the lines" -- a third state.

    Reporting it as an abstention would inflate the abstention rate the PRD grades.
    """
    m = Measurement(value=1.5, interval=Interval(1.0, 2.0), arm="A")
    assert m.decisions == {}


def test_an_absent_arm_is_not_an_abstain_verdict():
    """The distinction the schema draws, and the one worth getting right.

    `abstain` is a verdict on a capture that WAS measured -- the response still carries
    its rise. `arm_absent` means no measurement exists. A caller that reads them
    uniformly emits an abstain verdict with no rise, which the schema rejects.
    """
    absent = ArmAbsent(reason=AbsentReason.CUT, arm="C")
    assert not hasattr(absent, "value")
    assert not hasattr(absent, "interval")
    assert not isinstance(absent, Measurement)


@pytest.mark.parametrize("reason", list(AbsentReason))
def test_every_absent_reason_the_client_branches_on_is_available(reason):
    """cut, failed and unavailable render differently (TICK-063)."""
    assert ArmAbsent(reason=reason, arm="C").reason is reason


def test_an_absent_reason_must_come_from_the_enum():
    with pytest.raises(ResultError, match="must be an AbsentReason"):
        ArmAbsent(reason="cut", arm="C")


def test_a_verdict_must_be_a_verdict_not_a_string():
    with pytest.raises(ResultError, match="must be a Verdict"):
        LineDecision("pass")


# --- structural guarantees (attacked independently by TICK-206) ----------------


def test_the_library_imports_only_from_the_allow_list():
    """The library must be HANDED its input, not fetch it (ARCHITECTURE section 5)."""
    offenders = []
    for path, tree in _sources():
        for node in ast.walk(tree):
            for module in _import_roots(node):
                if not _is_allowed(module):
                    offenders.append(f"{path.name}:{node.lineno} imports {module}")
    assert not offenders, (
        "not on the allow-list: " + "; ".join(offenders)
        + f" -- permitted: {', '.join(sorted(ALLOWED_IMPORT_ROOTS))}"
    )


def test_the_allow_list_would_reject_the_repos_own_io_modules():
    """The guard's teeth, checked directly rather than assumed.

    `frontdoor.loader` reads the disk and `frontdoor.storage` talks to S3. A deny-list
    of stdlib names permitted both.
    """
    for module in ("frontdoor.loader", "frontdoor.storage", "frontdoor.eval", "boto3"):
        assert not _is_allowed(module), module
    for module in ("frontdoor.metrology.arm", "dataclasses", "enum"):
        assert _is_allowed(module), module


def test_the_library_opens_no_files_of_its_own():
    offenders = []
    for path, tree in _sources():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            # `builtins.open(...)` is an Attribute callee, not a Name, and slipped past
            # the earlier check entirely.
            called = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if called in FORBIDDEN_CALLS:
                offenders.append(f"{path.name}:{node.lineno} calls {called}()")
    assert not offenders, "; ".join(offenders)


def test_depth_is_structurally_unreachable_from_the_metrology_library():
    """D-020. Depth is quarantined from the metrology path, not merely unused.

    Arms B and C consume depth, but they are HANDED it. Nothing here may import or
    name a depth loader, because a library that can reach depth is one bug away from
    an arm that reads it when it should not.
    """
    offenders = []
    for path, tree in _sources():
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = " ".join(
                    [a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module or ""] + [a.name for a in node.names]
                )
                if "depth" in mod.lower():
                    offenders.append(f"{path.name}:{node.lineno} imports {mod}")
            elif isinstance(node, ast.Attribute) and "depth" in node.attr.lower():
                offenders.append(f"{path.name}:{node.lineno} reads .{node.attr}")
            elif isinstance(node, ast.Subscript):
                # The arm is handed a PARSED SIDECAR DICT, and
                # capture_sidecar.schema.json has a required top-level "depth" key. So
                # `sidecar["depth"]` is the most likely real leak path, and it is a
                # Subscript over a Constant -- invisible to the two checks above.
                key = getattr(node.slice, "value", None)
                if isinstance(key, str) and "depth" in key.lower():
                    offenders.append(f'{path.name}:{node.lineno} subscripts ["{key}"]')
            elif isinstance(node, ast.Name) and "depth" in node.id.lower():
                offenders.append(f"{path.name}:{node.lineno} names {node.id}")
            elif isinstance(node, ast.arg) and "depth" in node.arg.lower():
                offenders.append(f"{path.name}:{node.lineno} takes a {node.arg} parameter")
    assert not offenders, "D-020: " + "; ".join(offenders)


def test_the_guard_refuses_to_scan_nothing(tmp_path):
    """A scan over zero files passes vacuously, so `_sources` must refuse it.

    The previous version of this test only re-asserted that the package exists. It
    never called `_sources`, so deleting the vacuity assert left it green -- a guard
    test that could not fail, which is the thing this file exists to prevent.
    """
    with pytest.raises(AssertionError, match="would pass vacuously"):
        list(_sources(tmp_path))


def test_the_guard_reaches_into_subpackages(tmp_path):
    """`rglob`, not `glob`: arms will land in `metrology/arms/` and must stay covered."""
    (tmp_path / "arms").mkdir()
    (tmp_path / "arms" / "arm_b.py").write_text("import socket\n", encoding="utf-8")
    scanned = [path.name for path, _ in _sources(tmp_path)]
    assert "arm_b.py" in scanned, "a nested arm would escape every guard in this file"
