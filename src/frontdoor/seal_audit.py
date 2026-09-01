"""Append-only unsealing audit log (TICK-071, D-017).

Every `python -m frontdoor.eval --include-sealed` run appends one line to
SEAL_AUDIT.log before any sealed byte is read. The file is never truncated,
rewritten, or deleted by this module.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from getpass import getuser
from pathlib import Path

from frontdoor.manifest import manifest_sha256


class SealAuditError(Exception):
    """The unsealing run cannot be recorded, so it must not proceed."""


def _git_commit(repo):
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _working_tree_dirty(repo):
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def _operator():
    return getuser()


def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_unsealing(argv, manifest_path, *, audit_path, repo):
    """Append one audit line, or raise without writing.

    Line fields, tab-separated: UTC timestamp, commit SHA, manifest SHA-256,
    operator, JSON argv.
    """
    if _working_tree_dirty(repo):
        raise SealAuditError(
            "working tree is dirty; refusing to unseal so the recorded "
            "commit SHA would not describe the code that ran"
        )
    line = "\t".join(
        [
            _utc_now(),
            _git_commit(repo),
            manifest_sha256(manifest_path),
            _operator(),
            json.dumps(list(argv)),
        ]
    )
    path = Path(audit_path)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")
        handle.flush()
