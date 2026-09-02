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


class Arm(ABC):
    """Measure threshold rise from one image and its sidecar, or abstain."""

    #: Selector used by the registry and by `--arm` on the harness.
    name = None

    #: Whether this arm needs the camera model. Arm A does not: a homography from a
    #: known rectangle already absorbs the projection, so any length inside that
    #: plane is metric (ARCHITECTURE section 5, D-012).
    needs_intrinsics = True

    @abstractmethod
    def measure(self, image, sidecar):
        """Return a `Measurement` or an `Abstention`. Never None."""


class PendingArm(Arm):
    """A name reserved by ARCHITECTURE section 5 whose geometry is a later ticket.

    Registered so `A`, `A_prime`, `B` and `C` all resolve today and callers can be
    written against the real selectors. Calling one fails loudly and names the
    ticket, rather than returning a plausible zero.
    """

    def __init__(self, name, ticket, *, needs_intrinsics=True):
        self.name = name
        self.ticket = ticket
        self.needs_intrinsics = needs_intrinsics

    def measure(self, image, sidecar):
        raise ArmNotImplemented(
            f"arm {self.name!r} is registered but its geometry lands in {self.ticket}"
        )
