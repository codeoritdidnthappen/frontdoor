"""Dataset loader: bytes in, hashes checked, or nothing out (TICK-014, D-017, D-018).

The metrology library and the evaluation harness both go through here. A
truncated or substituted file must raise, naming the capture, rather than
quietly changing a number in the error budget.

Sidecars live in git at data/sidecars/<capture_id>.json. Images are fetched
by capture_id from the image bucket (TICK-012). Depth is not loaded.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from jsonschema import ValidationError

from frontdoor.manifest import read_manifest, sha256_file
from frontdoor.sidecar import validate_sidecar


class LoaderError(ValueError):
    """Raised when a capture cannot be returned with a verified hash."""


@dataclass(frozen=True)
class Capture:
    capture_id: str
    entrance_id: str
    split: str
    image: bytes
    sidecar: dict


class DatasetLoader:
    def __init__(self, manifest_path, sidecar_dir, get_image=None):
        self.manifest_path = Path(manifest_path)
        self.sidecar_dir = Path(sidecar_dir)
        self._get_image = get_image

    def _row(self, capture_id):
        for row in read_manifest(self.manifest_path):
            if row["capture_id"] == capture_id:
                return row
        raise LoaderError(
            f"capture_id {capture_id!r} is not in the manifest; "
            "refusing to load unverified bytes"
        )

    def _image_bytes(self, capture_id):
        getter = self._get_image
        if getter is None:
            from frontdoor.storage import image_store

            getter = image_store().get
        try:
            return getter(capture_id)
        except LoaderError:
            raise
        except Exception as exc:
            raise LoaderError(
                f"capture_id {capture_id!r} image could not be read: {exc}"
            ) from exc

    def load(self, capture_id):
        row = self._row(capture_id)
        sidecar_path = self.sidecar_dir / f"{capture_id}.json"
        if not sidecar_path.is_file():
            raise LoaderError(
                f"capture_id {capture_id!r} sidecar file is missing: {sidecar_path}"
            )
        if sha256_file(sidecar_path) != row["sidecar_sha256"]:
            raise LoaderError(f"capture_id {capture_id!r} sidecar hash mismatch")
        image = self._image_bytes(capture_id)
        if hashlib.sha256(image).hexdigest() != row["image_sha256"]:
            raise LoaderError(f"capture_id {capture_id!r} image hash mismatch")
        try:
            record = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise LoaderError(
                f"capture_id {capture_id!r} sidecar is not JSON: {exc}"
            ) from exc
        try:
            validate_sidecar(record)
        except ValidationError as exc:
            raise LoaderError(
                f"capture_id {capture_id!r} sidecar failed validation: {exc.message}"
            ) from exc
        return Capture(
            capture_id=row["capture_id"],
            entrance_id=row["entrance_id"],
            split=row["split"],
            image=image,
            sidecar=record,
        )

    def list_captures(self, *, entrance_id=None, split=None):
        ids = []
        for row in read_manifest(self.manifest_path):
            if entrance_id is not None and row["entrance_id"] != entrance_id:
                continue
            if split is not None and row["split"] != split:
                continue
            ids.append(row["capture_id"])
        return sorted(ids)
