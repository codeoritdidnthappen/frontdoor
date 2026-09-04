"""Append-only unsealing audit log (TICK-071, D-017).

Every `python -m frontdoor.eval --include-sealed` run appends one line to
SEAL_AUDIT.log before any sealed byte is read. The file is never truncated,
rewritten, or deleted by this module.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from getpass import getuser
from pathlib import Path

from frontdoor.manifest import manifest_sha256


class SealAuditError(Exception):
    """The unsealing run cannot be recorded, so it must not proceed."""


def _git(repo, *args, failure):
    """Run git, turning any failure into a SealAuditError.

    A traceback is a bad way to refuse an unsealing run: the operator has one chance at this on
    2026-09-07 and needs to know what to fix, not where the exception came from.
    """
    if not Path(repo).is_dir():
        # cwd= raises FileNotFoundError for a missing directory, indistinguishable from a missing
        # git binary. On the single 2026-09-07 run, telling the operator to install git when the
        # real problem is a typo'd path costs time nobody has.
        raise SealAuditError(f"{failure}: {repo} is not a directory")
    try:
        result = subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True
        )
    except FileNotFoundError as exc:
        raise SealAuditError(f"{failure}: git is not installed or not on PATH") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip().splitlines()
        raise SealAuditError(
            f"{failure}: {detail[0] if detail else f'git {args[0]} failed'}. "
            f"The unsealing run must be launched from inside the checkout it is auditing."
        ) from exc
    return result.stdout


def _git_commit(repo):
    return _git(repo, "rev-parse", "HEAD", failure="cannot record the commit SHA").strip()


def _working_tree_dirty(repo):
    """Tracked changes, plus untracked files that are not ignored.

    --porcelain already reports untracked files, so the remaining hole is deliberately ignored
    ones. Those are not listed here because calling every .env edit "dirty" would make the tool
    unusable -- the operator always has one. Instead the resolved configuration that ignored files
    actually control is recorded in the audit line by the caller, which is what knows how images
    are fetched. See `record_unsealing`'s `config` argument.
    """
    return bool(_git(repo, "status", "--porcelain", failure="cannot inspect the working tree").strip())


def _operator():
    return getuser()


def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


#: Tab-separated field order, matching ARCHITECTURE.md section 7. Written here as data so the
#: documentation and the log cannot disagree about which column is which.
AUDIT_FIELDS = (
    "utc_timestamp",
    "commit_sha",
    "manifest_sha256",
    "command_line",
    "operator",
    "resolved_config",
)


#: The mapping form of record_unsealing's arguments, for callers that carry the audit context
#: around as one mapping (labels.labels_for_eval's `audit=`). Keys are exactly record_unsealing's
#: parameters after argv; this module owns the contract so a caller-side copy cannot drift from
#: the signature it mirrors. Validate with validate_audit_mapping before unpacking.
AUDIT_KEYS = ("manifest_path", "audit_path", "repo", "config")


def validate_audit_mapping(audit):
    """Check a mapping against AUDIT_KEYS; raise SealAuditError naming what is missing.

    The one validation of "is this audit context complete", shared by every doorway that accepts
    the mapping form, so the refusal names the same keys record_unsealing actually takes.
    """
    missing = [key for key in AUDIT_KEYS if key not in audit]
    if missing:
        raise SealAuditError(
            f"audit is missing {missing}; record_unsealing needs all of "
            f"{AUDIT_KEYS} to append the audit line"
        )
    return audit


def record_unsealing(argv, manifest_path, *, audit_path, repo, config):
    """Append one audit line, or raise without writing.

    Fields are AUDIT_FIELDS, tab-separated. The command line is reconstructable: argv[0] is
    normalised to the module invocation actually supported, because an absolute path to eval.py is
    not a command anyone can re-run.

    `config` is what the run will actually read from -- bucket and endpoint, never credentials.
    The caller resolves it, because the caller is what knows how images are fetched; this module
    only records it. .env is gitignored and selects those values, so a clean working tree alone
    does not mean two runs read the same bytes.
    """
    if _working_tree_dirty(repo):
        raise SealAuditError(
            "working tree is dirty; refusing to unseal so the recorded "
            "commit SHA would not describe the code that ran"
        )
    command = list(argv)
    if command and command[0].endswith("eval.py"):
        command[0] = "python -m frontdoor.eval"
    line = "\t".join(
        [
            _utc_now(),
            _git_commit(repo),
            manifest_sha256(manifest_path),
            json.dumps(command),
            _operator(),
            json.dumps(config, sort_keys=True),
        ]
    )
    path = Path(audit_path)
    try:
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        # Nothing sealed has been read yet. Refusing here is the whole point: an unsealing run
        # that cannot be recorded must not happen.
        raise SealAuditError(
            f"cannot append to the audit log at {path}: {exc}. "
            "The unsealing run is not permitted without a record of it."
        ) from exc
