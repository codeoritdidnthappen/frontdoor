"""Deterministic split assignment from the committed seed (TICK-011, D-007).

An entrance's split is a pure function of its ID and the seed in split_seed.json:

    digest = sha256(utf8(entrance_id + seed))
    bucket = first 8 bytes of digest, as a big-endian unsigned integer, mod 100
    bucket < 30  -> "sealed"
    bucket < 50  -> "calib"
    otherwise    -> "dev"

Nothing else feeds in: no clock, no random source, no dependence on other entrances or
on ordering. Anyone can reproduce every assignment from the seed file and this description.

Run as a tool:  python -m frontdoor.split E-001 E-002 ...   (or entrance IDs on stdin)
Prints one "entrance_id,split" line per ID.
"""

import hashlib
import json
import sys
from importlib import resources

SEED = json.loads(
    resources.files("frontdoor").joinpath("split_seed.json").read_text(encoding="utf-8")
)["seed"]

SEALED_PERCENT = 30
CALIB_PERCENT = 20


def assign_split(entrance_id, seed=SEED):
    digest = hashlib.sha256((entrance_id + seed).encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") % 100
    if bucket < SEALED_PERCENT:
        return "sealed"
    if bucket < SEALED_PERCENT + CALIB_PERCENT:
        return "calib"
    return "dev"


def main(argv=None):
    ids = sys.argv[1:] if argv is None else argv
    if not ids:
        ids = [line.strip() for line in sys.stdin if line.strip()]
    for entrance_id in ids:
        print(f"{entrance_id},{assign_split(entrance_id)}")


if __name__ == "__main__":
    main()
