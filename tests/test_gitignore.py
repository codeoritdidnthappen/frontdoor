"""Committed artefacts named in ARCHITECTURE.md must stay trackable (TICK-220, #108)."""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Paths ARCHITECTURE.md §7–§8 requires to be committed. Transient runner
# output belongs under logs/; these must not match a blanket *.log rule.
COMMITTED_ARTEFACTS = [
    "SEAL_AUDIT.log",
    "CHANGES.log",
    "data/manifest.csv",
    # The curated on-site publication /map/data merges (TICK-333, #333).
    "data/published_scans.jsonl",
    "src/frontdoor/split_seed.json",
    "src/frontdoor/capture_sidecar.schema.json",
    "config/abstention.yaml",
]


@pytest.mark.parametrize("path", sorted(set(COMMITTED_ARTEFACTS)))
def test_architecture_committed_path_is_not_gitignored(path):
    result = subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 1, f"{path} is ignored and would never be committed"
