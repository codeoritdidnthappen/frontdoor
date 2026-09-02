"""Dataset loader: bytes in, hashes checked, or nothing out (TICK-014, TICK-070, D-017, D-018).

The metrology library and the evaluation harness both go through here. A
truncated or substituted file must raise, naming the capture, rather than
quietly changing a number in the error budget.

Sealed rows are absent from listings and refused on direct load. The only
way to read them is `python -m frontdoor.eval --include-sealed`, which
appends SEAL_AUDIT.log first (TICK-071).

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
from frontdoor.split import InvalidEntranceId, assign_split, canonical_entrance_id
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


def _same_entrance(left, right):
    """Compare entrance IDs in canonical form.

    A raw string comparison returns [] for `e-001` or ` E-001`, which is the same shape as "no such
    entrance" and as a working seal — the ambiguity this module argues against elsewhere.
    """
    try:
        return canonical_entrance_id(left) == canonical_entrance_id(right)
    except InvalidEntranceId:
        return str(left).strip() == str(right).strip()


class DatasetLoader:
    def __init__(self, manifest_path, sidecar_dir, get_image=None):
        self.manifest_path = Path(manifest_path)
        self.sidecar_dir = Path(sidecar_dir)
        self._get_image = get_image

    @staticmethod
    def derived_split(row):
        """The split this capture actually has, from the seed rather than the CSV cell.

        `is_sealed` re-derives because the column is a cache rather than an authority. Every other
        partition has to use the same source or the argument is only half made: a `calib` entrance
        whose cell reads `dev` would otherwise be handed to the dev evaluation set, which is a
        D-007 leak of a different kind.
        """
        entrance_id = (row.get("entrance_id") or "").strip()
        try:
            return assign_split(entrance_id)
        except InvalidEntranceId as exc:
            raise LoaderError(
                f"capture_id {row.get('capture_id')!r} has entrance_id {entrance_id!r}, "
                f"which the split seed cannot classify: {exc}. Refusing to treat it as unsealed."
            ) from exc

    @staticmethod
    def is_sealed(row):
        """Whether this capture is sealed, derived from the seed rather than read from the CSV.

        D-007 defines the split as a pure function of the entrance ID and the committed seed, and
        `assign_split` is that function. Comparing the manifest's `split` cell to the literal
        "sealed" instead makes the seal depend on a CSV string: a cell reading `dev`, `DEV`,
        `Sealed`, ` sealed` or empty would then read sealed bytes on a default run, with no flag,
        no error and no audit line. `manifest.py` already re-derives the split when it writes a
        row; this is the same check on the way back in, so the column is a cache rather than an
        authority.
        """
        return DatasetLoader.derived_split(row) == "sealed"

    def _row(self, capture_id):
        found = None
        for row in read_manifest(self.manifest_path):
            if row["capture_id"] != capture_id:
                continue
            # A duplicate id would let whichever row comes first decide the seal.
            if found is not None:
                raise LoaderError(
                    f"capture_id {capture_id!r} appears more than once in the manifest; "
                    "refusing to guess which row governs the seal"
                )
            found = row
        if found is None:
            raise LoaderError(
                f"capture_id {capture_id!r} is not in the manifest; "
                "refusing to load unverified bytes"
            )
        return found

    def _image_bytes(self, row, *, allow_sealed=False):
        capture_id = row["capture_id"]
        try:
            if self._get_image is not None:
                return self._get_image(capture_id)
            # Storage keys carry the partition, so the split has to be derived here --
            # this is the last point that still has the row. `storage.get` refuses a
            # sealed key on its own, without the manifest (#182).
            from frontdoor.storage import image_store, storage_key

            key = storage_key(capture_id, self.derived_split(row))
            return image_store().get(key, allow_sealed=allow_sealed)
        except LoaderError:
            raise
        except Exception as exc:
            raise LoaderError(
                f"capture_id {capture_id!r} image could not be read: {exc}"
            ) from exc

    def load(self, capture_id):
        return self._load_row(self._row(capture_id))

    def _load_row(self, row, *, allow_sealed=False):
        """Reads one capture. The seal is checked HERE, not in `load`.

        `eval.py` calls this method directly on the unsealing path, so a check living only in
        `load` was a check the production caller walked past. The only caller permitted to pass
        `allow_sealed=True` is the audited `--include-sealed` run.
        """
        if self.is_sealed(row) and not allow_sealed:
            raise LoaderError(
                f"capture_id {row['capture_id']!r} is sealed (split=sealed, derived from "
                f"entrance {row.get('entrance_id')!r} and the committed seed); "
                "refusing to load without an audited --include-sealed run"
            )
        capture_id = row["capture_id"]
        sidecar_path = self.sidecar_dir / f"{capture_id}.json"
        if not sidecar_path.is_file():
            raise LoaderError(
                f"capture_id {capture_id!r} sidecar file is missing: {sidecar_path}"
            )
        if sha256_file(sidecar_path) != row["sidecar_sha256"]:
            raise LoaderError(f"capture_id {capture_id!r} sidecar hash mismatch")
        image = self._image_bytes(row, allow_sealed=allow_sealed)
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
            split=self.derived_split(row),
            image=image,
            sidecar=record,
        )

    #: The three splits D-007 defines. Anything else is a typo, not an empty result.
    SPLITS = ("dev", "calib", "sealed")

    def list_captures(self, *, entrance_id=None, split=None):
        # Asking for the sealed split must refuse, not return []. An empty list is the same shape
        # as "no such split" and as "no captures yet", so a caller cannot tell a working seal from
        # a misspelled filter — and reading [] as "nothing is sealed" is the wrong lesson to learn.
        if split == "sealed":
            raise LoaderError(
                "the sealed split cannot be listed; it is opened once, by an audited "
                "`python -m frontdoor.eval --include-sealed` run (D-007, D-017)"
            )
        if split is not None and split not in self.SPLITS:
            raise LoaderError(
                f"unknown split {split!r}; expected one of {', '.join(self.SPLITS)}"
            )
        ids = []
        for row in read_manifest(self.manifest_path):
            if self.is_sealed(row):
                continue
            if entrance_id is not None and not _same_entrance(row["entrance_id"], entrance_id):
                continue
            if split is not None and self.derived_split(row) != split:
                continue
            ids.append(row["capture_id"])
        return sorted(ids)

    def __iter__(self):
        return iter(self.list_captures())

    def __len__(self):
        return len(self.list_captures())
