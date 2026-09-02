"""The one interface every arm sits behind (TICK-040, ARCHITECTURE section 5).

Four arms measure the same thing by different routes. They share this signature so
the harness can run any of them over identical input -- which is what makes the
deliverable 4 ablation an apples-to-apples comparison rather than four differently
shaped experiments (D-013).

The arm is HANDED a decoded image and a parsed sidecar. It does not load either.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ArmNotImplemented(NotImplementedError):
    """A registered arm exists by name but its geometry has not landed yet."""


class ArmCut(NotImplementedError):
    """A registered arm was dropped by a decision. Distinct from not-yet-built."""


class Arm(ABC):
    """Measure threshold rise from one image and its sidecar, or abstain."""

    #: Selector used by the registry and by `--arm` on the harness.
    name = None

    #: Whether this arm needs the CAMERA MODEL -- fx, fy, cx, cy. Arm A does not: a
    #: homography from a known rectangle already absorbs the projection, so any length
    #: inside that plane is metric (ARCHITECTURE section 5, D-012).
    #:
    #: Not the same as needing nothing from `intrinsics`. Every arm undistorts its ROI
    #: taps first (TICK-042), which reads `intrinsics.distortion_table` and
    #: `distortion_center` -- so an arm with this False still fails without them.
    #: TICK-043 AC3 draws exactly this line: "a sidecar with intrinsics removed
    #: (distortion table retained)". Named for the camera model rather than for the
    #: whole block so nobody strips the block to satisfy the flag.
    needs_camera_model = True

    @abstractmethod
    def measure(self, image, sidecar):
        """Return a `Measurement` or an `ArmAbsent`. Never None.

        There is no `Abstention` type to return, deliberately. Abstaining is a verdict
        this arm REACHED about a capture it did measure, so it rides inside the
        `Measurement` as a `Verdict.ABSTAIN` in a `LineDecision`, and `rise_in` is still
        reported. `ArmAbsent` is the other thing entirely: no measurement happened at
        all. Collapsing the two emits an abstain verdict with no measurement behind it,
        which the frozen wire schema rejects -- see the module docstring in `result.py`.
        """


class CutArm(Arm):
    """An arm dropped by a project decision. Not pending -- nobody is coming back to it.

    Kept registered rather than deleted so the ablation can report it as cut with its reason
    (`absent_reason: "cut"` in measure_response.schema.json), and so a caller asking for it
    gets an explanation instead of an unknown-arm error.
    """

    def __init__(self, name, decision, reason):
        self.name = name
        self.decision = decision
        self.reason = reason

    def measure(self, image, sidecar):
        raise ArmCut(f"arm {self.name!r} was cut by {self.decision}: {self.reason}")


class PendingArm(Arm):
    """A name reserved by ARCHITECTURE section 5 whose geometry is a later ticket.

    Registered so `A`, `A_prime`, `B` and `C` all resolve today and callers can be
    written against the real selectors. Calling one fails loudly and names the
    ticket, rather than returning a plausible zero.
    """

    def __init__(self, name, ticket, *, needs_camera_model=True):
        self.name = name
        self.ticket = ticket
        self.needs_camera_model = needs_camera_model

    def measure(self, image, sidecar):
        raise ArmNotImplemented(
            f"arm {self.name!r} is registered but its geometry lands in {self.ticket}"
        )
