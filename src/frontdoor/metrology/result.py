"""What a measurement run returns (TICK-040).

Shaped against the ALREADY-FROZEN wire contract in
`src/frontdoor_server/measure_response.schema.json`, not invented here. An earlier
version of this module carried a single `decision` per measurement; the schema
requires two independent verdicts per arm, one per ADA line, and the committed stub
for Arm A-prime is exactly the case that breaks a single field -- `abstain` at the
half-inch line and `fail` at the quarter-inch line in the same result. TICK-052
would have had to change this type's public shape to serialize a real measurement.

Three outcomes exist, and the schema keeps them apart, so this module does too:

  Measurement   the arm measured, and gives a verdict at each line
  Abstention    a verdict AT ONE LINE -- the interval straddles it. The capture was
                still measured, and `rise_in` is still reported. Not a type here:
                it is a `Verdict.ABSTAIN` inside a `LineDecision`.
  ArmAbsent     the arm produced no measurement at all, and says why

Collapsing the last two is the mistake this module exists to prevent. A caller that
reads them uniformly emits an abstain verdict with no measurement, which the schema
rejects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite


class ResultError(ValueError):
    """A result was constructed that cannot mean anything."""


class ADALine(Enum):
    """The two lines a rise is judged against (PRD section 2).

    Half-inch is the pre-registered primary, quarter-inch the secondary. They are
    computed independently, so one may abstain while the other does not.
    """

    HALF_INCH = "half_inch"
    QUARTER_INCH = "quarter_inch"


class Verdict(Enum):
    """pass -- clears the line. fail -- exceeds it. abstain -- the interval straddles it.

    Abstain is a first-class outcome (D-009), never a missing or null measurement.
    """

    PASS = "pass"
    FAIL = "fail"
    ABSTAIN = "abstain"


class AbsentReason(Enum):
    """Why an arm produced nothing. The client renders the three differently."""

    CUT = "cut"                  # dropped by a project decision, e.g. Arm C (D-013)
    FAILED = "failed"            # this arm could not measure THIS capture
    UNAVAILABLE = "unavailable"  # not served by THIS deployment (TICK-062)


@dataclass(frozen=True)
class Interval:
    """A closed interval on the same scale as the measurement it accompanies."""

    low: float
    high: float

    def __post_init__(self):
        for name, bound in (("low", self.low), ("high", self.high)):
            if not isfinite(bound):
                raise ResultError(
                    f"interval {name} is {bound}; a non-finite bound straddles every line, "
                    "so it would abstain everywhere while looking like a measurement"
                )
        if self.low > self.high:
            raise ResultError(f"interval is inverted: low={self.low} > high={self.high}")

    @property
    def width(self):
        return self.high - self.low

    def contains(self, value):
        return self.low <= value <= self.high


@dataclass(frozen=True)
class LineDecision:
    """One verdict at one ADA line, with the reason when there is no verdict to give."""

    verdict: Verdict
    explanation: str = ""

    def __post_init__(self):
        if not isinstance(self.verdict, Verdict):
            raise ResultError(f"verdict must be a Verdict, got {self.verdict!r}")
        # The schema constrains this by pattern rather than length: a whitespace-only
        # string satisfies minLength and still renders as a blank on screen.
        if self.verdict is Verdict.ABSTAIN and not self.explanation.strip():
            raise ResultError(
                "an abstain verdict requires an explanation; an abstention that renders "
                "blank is indistinguishable from a broken client (D-009)"
            )


@dataclass(frozen=True)
class Measurement:
    """A metric rise, the interval that says how much to trust it, and a verdict per line.

    The interval is required. A point estimate cannot be JUDGED against a line
    (D-008) -- only compared to it, which is the mistake the error budget exists to
    prevent, and it is the interval straddling a line that produces an abstain.
    """

    value: float
    interval: Interval
    arm: str
    #: Populated by TICK-052. Empty means "not yet compared to the ADA lines", which
    #: is NOT an abstention: abstain is a verdict this arm reached, and reporting an
    #: un-reasoned measurement as one would inflate the abstention rate the PRD grades.
    decisions: dict = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.interval, Interval):
            raise ResultError(
                f"measurement from arm {self.arm!r} has no interval "
                f"(got {type(self.interval).__name__}); a point estimate cannot be "
                "judged against the compliance lines"
            )
        if not self.interval.contains(self.value):
            raise ResultError(
                f"measurement {self.value} from arm {self.arm!r} lies outside its own "
                f"interval [{self.interval.low}, {self.interval.high}]"
            )
        for line, decision in self.decisions.items():
            if not isinstance(line, ADALine):
                raise ResultError(f"decision key must be an ADALine, got {line!r}")
            if not isinstance(decision, LineDecision):
                raise ResultError(f"decision at {line.value} must be a LineDecision")
        if self.decisions and set(self.decisions) != set(ADALine):
            raise ResultError(
                "a reasoned measurement carries a verdict at BOTH lines; the schema "
                f"requires half_inch and quarter_inch, got {sorted(l.value for l in self.decisions)}"
            )


@dataclass(frozen=True)
class ArmAbsent:
    """This arm produced no measurement at all, and says why.

    Distinct from an abstain verdict, which is a judgement about a capture that WAS
    measured and still reports its rise. Carries no value and no interval, so there
    is nothing here for a caller to read as a number by mistake.
    """

    reason: AbsentReason
    arm: str
    detail: str = ""

    def __post_init__(self):
        if not isinstance(self.reason, AbsentReason):
            raise ResultError(
                f"absent reason must be an AbsentReason, got {self.reason!r}; the client "
                "branches on the three, rendering a cut arm differently from a failed one"
            )
