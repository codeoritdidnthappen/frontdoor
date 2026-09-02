"""Core metrology library (TICK-040, EPIC-02).

The only place metrology exists. The server and the evaluation harness are thin
entrypoints over this package and neither reimplements a measurement, which is what
guarantees Demo Day exhibits the exact system the error budget characterises
(ARCHITECTURE section 1, R-11).

Pure Python. No network, no I/O beyond what it is handed: input is one decoded image
plus one parsed sidecar, output is a `Measurement` or an `ArmAbsent`.
`test_metrology_scaffold.py` enforces both structurally -- by an allow-list of
imports, not a deny-list -- and D-020 depth is unreachable from here by the same test.

Result types are shaped against `src/frontdoor_server/measure_response.schema.json`,
which was frozen before this package existed.
"""

from frontdoor.metrology.arm import Arm, ArmNotImplemented, PendingArm
from frontdoor.metrology.registry import (
    ARM_NAMES,
    UnknownArm,
    all_arms,
    get_arm,
    register_arm,
)
from frontdoor.metrology.result import (
    ADALine,
    AbsentReason,
    ArmAbsent,
    Interval,
    LineDecision,
    Measurement,
    ResultError,
    Verdict,
)

__all__ = [
    "ADALine",
    "ARM_NAMES",
    "AbsentReason",
    "Arm",
    "ArmAbsent",
    "ArmNotImplemented",
    "Interval",
    "LineDecision",
    "Measurement",
    "PendingArm",
    "ResultError",
    "UnknownArm",
    "Verdict",
    "all_arms",
    "get_arm",
    "register_arm",
]
