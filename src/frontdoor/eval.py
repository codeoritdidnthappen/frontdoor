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

def _repo_root():
    """The checkout this run was launched from, not wherever the package happens to live.

    `Path(__file__).parents[2]` is the repo root only for a source checkout or editable install.
    Installed normally, or run from a different clone, it silently binds the manifest, the audit log
    and the dirty-tree check to another tree — so an unsealing run can read one checkout's sealed
    data and write the audit line into a different repository. The audit trail is the evidence the
    seal was opened once against a known state of the code; it has to describe the tree that was
    actually opened.
    """
    root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        or Path.cwd()
    )
    return root.resolve()


REPO_ROOT = _repo_root()
MANIFEST = REPO_ROOT / "data" / "manifest.csv"
SIDECARS = REPO_ROOT / "data" / "sidecars"
AUDIT_LOG = REPO_ROOT / "SEAL_AUDIT.log"


def _image_getter():
    from frontdoor.storage import image_store

    return image_store().get


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    include_sealed = "--include-sealed" in args
    # TICK-070 AC4: the unsealing run is a deliberate act at a terminal, not something a notebook or
    # an import can perform. Passing argv explicitly is how a library caller would reach it, so that
    # route is refused rather than audited.
    if include_sealed and argv is not None:
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
    loader = DatasetLoader(MANIFEST, SIDECARS, get_image=_image_getter())
    if include_sealed:
        cmdline = sys.argv if argv is None else [sys.argv[0], *args]
        try:
            record_unsealing(
                argv=cmdline,
                manifest_path=MANIFEST,
                audit_path=AUDIT_LOG,
                repo=REPO_ROOT,
            )
        except SealAuditError as exc:
            print(exc, file=sys.stderr)
            return 1
        for row in sorted(read_manifest(MANIFEST), key=lambda r: r["capture_id"]):
            loader._load_row(row, allow_sealed=True)
        return 0
    for capture_id in loader.list_captures():
        loader.load(capture_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
