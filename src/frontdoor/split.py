"""Deterministic split assignment from the committed seed (TICK-011, D-007).

An entrance's split is a pure function of its canonical ID and the seed in split_seed.json:

    digest = sha256(utf8(canonical_entrance_id + seed))
    bucket = first 8 bytes of digest, as a big-endian unsigned integer, mod 100
    bucket < 30  -> "sealed"
    bucket < 50  -> "calib"
    otherwise    -> "dev"

Nothing else feeds in: no clock, no random source, no dependence on other entrances or
on ordering. Anyone can reproduce every assignment from the seed file and this description.

Canonical entrance ID (TICK-217, #105): NFC, strip surrounding whitespace, uppercase,
then it must match E- followed by exactly three digits (e.g. E-014). Spellings a human
would call the same entrance therefore hash to the same split; anything else is rejected.

Run as a tool:  python -m frontdoor.split E-001 E-002 ...   (or entrance IDs on stdin)
Prints one "entrance_id,split" line per ID, using the canonical form.
"""

import hashlib
import json
import re
import sys
import unicodedata
from importlib import resources

SEED = json.loads(
    resources.files("frontdoor").joinpath("split_seed.json").read_text(encoding="utf-8")
)["seed"]

SEALED_PERCENT = 30
CALIB_PERCENT = 20

ENTRANCE_ID_RE = re.compile(r"^E-[0-9]{3}$")


class InvalidEntranceId(ValueError):
    """Raised when an entrance ID cannot be reduced to the canonical form."""


def canonical_entrance_id(entrance_id):
    """Return the canonical entrance ID, or raise InvalidEntranceId.

    Applied on every entry point into this module so argv, stdin and the Python
    API cannot disagree about which string is hashed.
    """
    if not isinstance(entrance_id, str):
        raise InvalidEntranceId(
            f"invalid entrance ID {entrance_id!r}; "
            "canonical form is E- followed by exactly three digits (e.g. E-014)"
        )
    canonical = unicodedata.normalize("NFC", entrance_id).strip().upper()
    if not ENTRANCE_ID_RE.fullmatch(canonical):
        raise InvalidEntranceId(
            f"invalid entrance ID {entrance_id!r}; "
            "canonical form is E- followed by exactly three digits (e.g. E-014)"
        )
    return canonical


def _assign_split_with_seed(entrance_id, seed):
    """Test-only: assign a split with an arbitrary seed.

    Not a supported public API. Production and CLI callers use assign_split,
    which can only hash against the committed seed.
    """
    entrance_id = canonical_entrance_id(entrance_id)
    digest = hashlib.sha256((entrance_id + seed).encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") % 100
    if bucket < SEALED_PERCENT:
        return "sealed"
    if bucket < SEALED_PERCENT + CALIB_PERCENT:
        return "calib"
    return "dev"


def assign_split(entrance_id):
    return _assign_split_with_seed(entrance_id, SEED)


def main(argv=None):
    ids = sys.argv[1:] if argv is None else argv
    if not ids:
        ids = [line for line in sys.stdin if line.strip()]
    for raw in ids:
        entrance_id = canonical_entrance_id(raw)
        print(f"{entrance_id},{assign_split(entrance_id)}")


if __name__ == "__main__":
    main()
