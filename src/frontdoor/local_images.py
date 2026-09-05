"""Read a capture's image bytes from a local directory instead of the bucket (#342).

The dataset's bytes live on the operator's Mac. Uploading them to R2 is the committed design and
should still happen -- `data/STORAGE.md` says so and #23's release artifact needs it -- but the
evaluation should not be unable to run until it does. This is the second path: point the eval at
the directory the photographs are already in.

Two things make it safe rather than a shortcut.

**The manifest still decides what the bytes must be.** `DatasetLoader.load` hashes what it read and
compares it to `image_sha256`; a directory holding different pixels fails there, exactly as a
tampered object in the bucket would.

**The seal is enforced here, not inherited.** `DatasetLoader._image_bytes` returns an injected
getter's bytes BEFORE it reaches the sealed check -- that seam exists for tests, and handing it a
real reader would let an ordinary dev run read sealed captures straight off the disk. So this
reader refuses them itself, in the same shape and with the same exception type the storage layer
uses, and only the audited run may pass `allow_sealed`.
"""

import json
from pathlib import Path

from frontdoor.loader import DatasetLoader, LoaderError
from frontdoor.storage import SealedObjectDenied


class LocalImages:
    """Capture bytes from `directory`, located by each sidecar's own `image.path`.

    The path is read from the committed sidecar rather than guessed from the capture id, so a
    layout this code has never seen still resolves, and a renamed file is a loud miss instead of a
    silent one.
    """

    def __init__(self, directory, sidecar_dir, *, allow_sealed=False):
        self.directory = Path(directory)
        self.sidecar_dir = Path(sidecar_dir)
        self.allow_sealed = allow_sealed

    def _sidecar(self, capture_id):
        path = self.sidecar_dir / f"{capture_id}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise LoaderError(f"capture_id {capture_id!r} has no sidecar at {path}") from exc
        except ValueError as exc:
            raise LoaderError(f"sidecar {path} is not valid JSON: {exc}") from exc

    def path_for(self, capture_id):
        """Where this capture's file should be. Relative paths only, and inside the directory."""
        sidecar = self._sidecar(capture_id)
        relative = str((sidecar.get("image") or {}).get("path", "")).strip()
        if not relative:
            raise LoaderError(f"sidecar for {capture_id!r} names no image.path")
        candidate = (self.directory / relative).resolve()
        root = self.directory.resolve()
        # A sidecar is committed data, but it is still data: an absolute or climbing path would
        # read a file the operator never pointed us at.
        if root != candidate and root not in candidate.parents:
            raise LoaderError(
                f"sidecar for {capture_id!r} names {relative!r}, which is outside {root}"
            )
        return candidate

    def guard_split(self, capture_id, split):
        """Refuse a sealed capture unless this is the audited run.

        The loader's injection seam skips `storage.get`, so if this does not say no, nothing does.
        """
        if split == "sealed" and not self.allow_sealed:
            raise SealedObjectDenied(
                f"{capture_id!r} is sealed; it is opened once, by an audited "
                "`--include-sealed` run (D-007, D-017)"
            )

    def read(self, capture_id, split):
        self.guard_split(capture_id, split)
        path = self.path_for(capture_id)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise LoaderError(
                f"capture_id {capture_id!r} image is not in the local directory: {path}"
            ) from exc

    def getter(self, loader: DatasetLoader):
        """A `get_image` for `DatasetLoader`, deriving each capture's split from the manifest."""

        def get_image(capture_id):
            row = loader._row(capture_id)
            return self.read(capture_id, DatasetLoader.derived_split(row))

        return get_image

    def missing(self, capture_ids, split):
        """Which of these have no file. Same contract as the bucket pre-flight (#337, #306)."""
        absent = []
        for capture_id in capture_ids:
            self.guard_split(capture_id, split)
            try:
                if not self.path_for(capture_id).is_file():
                    absent.append(capture_id)
            except LoaderError:
                absent.append(capture_id)
        return absent
