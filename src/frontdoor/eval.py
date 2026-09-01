"""Evaluation harness entrypoint (TICK-070, TICK-071, D-017).

Loads every capture the dataset loader will give you. Sealed rows are
included only when this process is started with --include-sealed, which
appends SEAL_AUDIT.log before the first sealed read. There is no library
flag, environment variable, or default argument that turns that on.
"""

from __future__ import annotations

import sys
from pathlib import Path

from frontdoor.loader import DatasetLoader
from frontdoor.manifest import read_manifest
from frontdoor.seal_audit import SealAuditError, record_unsealing

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "data" / "manifest.csv"
SIDECARS = REPO_ROOT / "data" / "sidecars"
AUDIT_LOG = REPO_ROOT / "SEAL_AUDIT.log"


def _image_getter():
    from frontdoor.storage import image_store

    return image_store().get


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    include_sealed = "--include-sealed" in args
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
            loader._load_row(row)
        return 0
    for capture_id in loader.list_captures():
        loader.load(capture_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
