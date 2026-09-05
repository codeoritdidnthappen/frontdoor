"""AGENTS.md and CLAUDE.md are one document with two names (#307).

They drifted once, silently, and the missing part was §5 rules 6-8 -- including rule 7, the
closing-keyword trap. On 2026-09-05 a commit body reading "This does not close #62" closed #62,
which is exactly what rule 7 warns about; an agent reading AGENTS.md had no warning at all,
because AGENTS.md did not have the rule.

Checked here rather than by eye, because "by eye" is how it diverged.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
CLAUDE = ROOT / "CLAUDE.md"


def bodies():
    """Both files with their title line removed -- the one line allowed to differ."""
    return tuple(
        path.read_text(encoding="utf-8").split("\n", 1)[1] for path in (AGENTS, CLAUDE)
    )


def test_the_two_files_differ_only_in_their_title():
    agents, claude = bodies()
    assert agents == claude, (
        "AGENTS.md and CLAUDE.md have diverged. They are the same instructions under two "
        "names: whatever one of them says, the other must say too, or an agent's behaviour "
        "depends on which file its harness happens to read."
    )


def test_each_file_keeps_its_own_title():
    assert AGENTS.read_text(encoding="utf-8").startswith("# AGENTS.md")
    assert CLAUDE.read_text(encoding="utf-8").startswith("# CLAUDE.md")


def test_the_rules_that_went_missing_are_present_in_both():
    """Named explicitly, so a future sync that drops them again fails on the reason, not the diff."""
    for path in (AGENTS, CLAUDE):
        text = path.read_text(encoding="utf-8")
        assert "Land the whole ticket, or split it" in text, path.name
        assert "Never put a ticket number after a closing keyword" in text, path.name
        assert "Say the ticket state on the ticket" in text, path.name
