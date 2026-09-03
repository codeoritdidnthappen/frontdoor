"""The tracker has to cover everyone on the roster (TICK-116, #82).

The four X floors are graded **per person**, so a tracker that silently omits someone does not
under-report by a little -- it hides one whole failing scorecard, and the omission surfaces when
the grade does. The roster is the source of truth for who exists, and it has already changed once
during the project.

A doc test rather than a code test, because the tracker is a document and the failure is a
document drifting from another document.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEAM = ROOT / "TEAM.md"
TRACKER = ROOT / "docs" / "build-in-public-tracker.md"


def roster_handles() -> set[str]:
    """Every X handle in TEAM.md's roster table."""
    handles = set()
    for line in TEAM.read_text(encoding="utf-8").splitlines():
        # Roster rows are pipe tables carrying a GitHub login and an @handle.
        if line.startswith("|") and "@" in line:
            handles.update(re.findall(r"@[A-Za-z0-9_]{2,15}\b", line))
    return handles


def test_the_roster_is_not_empty():
    """Guards the extraction: an empty set would make the real test below vacuous."""
    assert len(roster_handles()) >= 4, roster_handles()


def test_every_person_on_the_roster_has_a_scorecard():
    tracker = TRACKER.read_text(encoding="utf-8")
    missing = sorted(h for h in roster_handles() if h not in tracker)
    assert not missing, (
        f"no scorecard in the build-in-public tracker for {missing}. The X floors are graded per "
        "person, so an untracked teammate is an unseen failing scorecard, not a rounding error"
    )


def test_all_four_floors_are_tracked():
    """Named explicitly, because F4 is the one that depends on someone outside the team."""
    tracker = TRACKER.read_text(encoding="utf-8")
    for floor in ("150", "25", "5+", "outside"):
        assert floor in tracker, f"floor {floor!r} is not tracked"
