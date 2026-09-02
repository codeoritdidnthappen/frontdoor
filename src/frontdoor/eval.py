"""Evaluation harness entrypoint (TICK-070, TICK-071, D-017).

Loads every capture the dataset loader will give you. Sealed rows are
included only when this process is started with --include-sealed, which
appends SEAL_AUDIT.log before the first sealed read. There is no library
flag, environment variable, or default argument that turns that on.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from frontdoor.loader import DatasetLoader
from frontdoor.manifest import read_manifest
from frontdoor.seal_audit import SealAuditError, record_unsealing

class EvalError(Exception):
    """The harness cannot establish where it is running, so it must not run."""


def _repo_root():
    """The checkout this run was launched from, not wherever the package happens to live.

    `Path(__file__).parents[2]` is the repo root only for a source checkout or editable install.
    Installed normally, or run from a different clone, it silently binds the manifest, the audit log
    and the dirty-tree check to another tree — so an unsealing run can read one checkout's sealed
    data and write the audit line into a different repository. The audit trail is the evidence the
    seal was opened once against a known state of the code; it has to describe the tree that was
    actually opened.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=False,
    )
    root = result.stdout.strip()
    if not root:
        # Falling back to the working directory is the failure this function exists to prevent:
        # it would silently bind the manifest and the audit log to whatever tree happened to be
        # current. Raising is the only honest option, and it happens at import so it cannot be
        # discovered halfway through the one unsealing run.
        raise EvalError(
            "frontdoor.eval must be run from inside a git checkout: "
            f"`git rev-parse --show-toplevel` failed in {Path.cwd()}. "
            "The audit trail has to describe the tree that was actually opened."
        )
    return Path(root).resolve()


REPO_ROOT = _repo_root()
MANIFEST = REPO_ROOT / "data" / "manifest.csv"
SIDECARS = REPO_ROOT / "data" / "sidecars"
AUDIT_LOG = REPO_ROOT / "SEAL_AUDIT.log"


def _storage_config():
    """What this run will read from, for the audit line. Never credentials.

    Resolved here because this module is what decides how images are fetched. Failing to resolve
    refuses the run: an audit line that cannot say which bucket was read does not record the one
    property it exists for.
    """
    from frontdoor.storage import load_image_creds

    try:
        creds = load_image_creds()
    except Exception as exc:
        raise SealAuditError(
            f"cannot resolve the storage configuration to record it: {exc}. "
            "The audit line has to say which bucket the run read; see data/STORAGE.md."
        ) from exc
    return {"images_bucket": creds.bucket, "endpoint": creds.endpoint or "default"}


def main(argv=None, *, from_cli=False):
    args = sys.argv[1:] if argv is None else list(argv)
    include_sealed = "--include-sealed" in args
    # TICK-070 AC4: the unsealing run is a deliberate act at a terminal, not something a notebook or
    # an import can perform.
    #
    # Keying that on `argv is not None` did not enforce it: any in-process caller can set sys.argv
    # and call main(), which is precisely what a notebook would do -- and what this module's own
    # tests were doing. The permission is now a private argument only the __main__ block passes, so
    # it cannot be reached by shaping the call.
    if include_sealed and not from_cli:
        print(
            "--include-sealed is only accepted from the command line. "
            "Run `python -m frontdoor.eval --include-sealed` in a terminal; the unsealing run is "
            "audited and happens once (D-017).",
            file=sys.stderr,
        )
        return 2
    leftover = [item for item in args if item != "--include-sealed"]
    if leftover:
        print(
            "usage: python -m frontdoor.eval [--include-sealed]",
            file=sys.stderr,
        )
        return 2
    # Resolved per call rather than eagerly: constructing the loader must not turn an unconfigured
    # .env into a traceback before the arguments have even been checked. The loader wraps read
    # failures in LoaderError naming the capture; that contract is preserved.
    loader = DatasetLoader(MANIFEST, SIDECARS)
    if include_sealed:
        cmdline = sys.argv if argv is None else [sys.argv[0], *args]
        try:
            record_unsealing(
                argv=cmdline,
                manifest_path=MANIFEST,
                audit_path=AUDIT_LOG,
                repo=REPO_ROOT,
                config=_storage_config(),
            )
        except SealAuditError as exc:
            print(exc, file=sys.stderr)
            return 1
        # Through _row(), so the one run that cannot be repeated gets the duplicate-capture_id
        # guard rather than loading a doubled row twice and failing later on a hash mismatch.
        capture_ids = sorted({row["capture_id"] for row in read_manifest(MANIFEST)})
        for capture_id in capture_ids:
            loader._load_row(loader._row(capture_id), allow_sealed=True)
        return 0
    for capture_id in loader.list_captures():
        loader.load(capture_id)
    return 0


if __name__ == "__main__":
    # The only place from_cli is True. Everything else -- imports, notebooks, tests -- reaches
    # main() without it and cannot unseal, however sys.argv is arranged.
    sys.exit(main(from_cli=True))
