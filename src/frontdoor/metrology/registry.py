"""One registry, so switching arms is a name and not a code path (TICK-040).

If callers branched on the arm instead, each branch could drift into doing slightly
different work, and the ablation would stop comparing arms and start comparing
call sites.
"""

from __future__ import annotations

from frontdoor.metrology.arm import Arm, PendingArm
from frontdoor.metrology.result import ResultError

#: The four arms ARCHITECTURE section 5 defines, in the order its table lists them.
#: `needs_camera_model` follows that table: Arm A alone does not need fx, fy, cx, cy.
#: It still needs the distortion table, as every arm does -- see `Arm.needs_camera_model`.
ARM_NAMES = ("A", "A_prime", "B", "C")

_ARMS = {
    "A": PendingArm("A", "TICK-043 (#37)", needs_camera_model=False),
    "A_prime": PendingArm("A_prime", "TICK-045 (#39)"),
    "B": PendingArm("B", "TICK-047 (#41)"),
    "C": PendingArm("C", "TICK-048 (#42)"),
}


class UnknownArm(LookupError):
    """Asked for an arm that does not exist."""


def register_arm(arm):
    """Replace a reserved name with a real implementation.

    Registration is by the arm's own `name`, so an arm cannot be filed under a
    selector it does not answer to.
    """
    if not isinstance(arm, Arm):
        # A class passed here registers successfully and then fails at call time with a
        # missing-argument TypeError, far from the mistake. Catch it where it is made.
        raise ResultError(
            f"register_arm expects an Arm instance, got {arm!r}; "
            "an unbound class registers fine and fails only when the harness calls it"
        )
    if arm.name not in ARM_NAMES:
        raise UnknownArm(
            f"{arm.name!r} is not one of the four arms: {', '.join(ARM_NAMES)}"
        )
    _ARMS[arm.name] = arm
    return arm


def get_arm(name):
    try:
        return _ARMS[name]
    except KeyError:
        raise UnknownArm(
            f"unknown arm {name!r}; expected one of {', '.join(ARM_NAMES)}"
        ) from None


def all_arms():
    """Every arm, in ARCHITECTURE's order. The harness runs the ablation over this."""
    return [_ARMS[name] for name in ARM_NAMES]
