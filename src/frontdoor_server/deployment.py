"""The deployed image, recorded so the fallback chain can be checked rather than assumed
(TICK-062, #50).

D-016's fallback chain is only a mitigation if steps 1-3 run the **same image**. Otherwise "the
laptop version" is a different system being demoed under pressure, which is the thing R-4 exists to
prevent. #50 asks for both digests to be recorded and for a check that confirms they match.

The check lives here rather than in the runbook because a procedure written in prose is one nobody
runs on the day. `python -m frontdoor_server.deployment verify` gives an answer, and it is
deliberately RED until the laptop has actually pulled the image: "not cached yet" and "cached and
matching" must not look the same, since the whole point is to find out before Demo Day rather than
on it.
"""

import json
import sys
from pathlib import Path

RECORD = Path(__file__).resolve().parents[2] / "data" / "deployment.json"

_HEX = set("0123456789abcdef")


class DeploymentError(Exception):
    """The record is unusable, or the two images are not the same image."""


def _is_digest(value):
    """A docker content digest: `sha256:` and 64 lowercase hex characters, anchored.

    Anchored on purpose. An unanchored check accepts a digest with anything around it, which is
    the shape of the bug TICK-228 fixed in the sidecar schema.
    """
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    body = value[len("sha256:"):]
    return len(body) == 64 and all(c in _HEX for c in body)


def load(path=RECORD):
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DeploymentError(f"{path} is missing; the deployed image is unrecorded") from exc
    except json.JSONDecodeError as exc:
        raise DeploymentError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(record, dict):
        raise DeploymentError(f"{path} must hold an object")
    return record


def _side(record, name):
    side = record.get(name)
    if not isinstance(side, dict):
        raise DeploymentError(f"the record has no {name!r} section")
    return side


def check(record):
    """Return a human-readable line, or raise. The host must be recorded; the laptop must match.

    A missing laptop digest is a FAILURE, not a pass with a note. The image has to be on the demo
    laptop before Demo Day, and a check that goes green while it is absent would be reporting that
    the fallback works when nobody has tried it.
    """
    host = _side(record, "host").get("digest")
    if not _is_digest(host):
        raise DeploymentError(
            f"the host digest is not a sha256 content digest: {host!r}. "
            "Record it with `fly image show`."
        )

    laptop = _side(record, "laptop").get("digest")
    if laptop is None:
        raise DeploymentError(
            "the demo laptop has not cached the deployed image yet, so step 3 of the D-016 "
            "fallback chain is untested. Pull it and record the digest before Demo Day -- see "
            "docs/server-deploy.md."
        )
    if not _is_digest(laptop):
        raise DeploymentError(
            f"the laptop digest is not a sha256 content digest: {laptop!r}"
        )
    if laptop != host:
        raise DeploymentError(
            "the laptop is NOT running the deployed image.\n"
            f"  host:   {host}\n"
            f"  laptop: {laptop}\n"
            "A local `docker build` produces a different image; the laptop must PULL the "
            "deployed one, or the fallback changes the system rather than the network path."
        )
    return f"ok  same image on host and laptop  {host}"


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args != ["verify"]:
        print("usage: python -m frontdoor_server.deployment verify", file=sys.stderr)
        return 2
    try:
        print(check(load()))
    except DeploymentError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
