"""Check that the D-016 fallback actually runs the deployed image (TICK-062, #50).

The chain is a mitigation only if steps 1-3 run the SAME image. Otherwise "the laptop version" is
a different system being demoed under pressure, which is what R-4 exists to prevent.

**This queries the live host and the laptop's own docker cache.** An earlier revision compared two
strings inside `data/deployment.json` and called that a check -- which passes green in exactly the
case that matters: a redeploy mints a new release, nobody edits the file, and the laptop is still
holding last week's image. Comparing a record to itself proves that someone typed carefully once.

So `verify` asks the two systems. `verify --recorded-only` is the weaker file-shape check, kept
because CI has neither flyctl nor docker, and it says out loud that it proves nothing about what is
actually deployed or cached.
"""

import json
import subprocess
import sys
from pathlib import Path

RECORD = Path(__file__).resolve().parents[2] / "data" / "deployment.json"

_HEX = set("0123456789abcdef")


class DeploymentError(Exception):
    """The record is unusable, or the running images are not the same image."""


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


def _run(command):
    """Run a command and return stdout, or raise DeploymentError naming what was unavailable."""
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except FileNotFoundError as exc:
        raise DeploymentError(
            f"{command[0]} is not installed, so the live check cannot run. "
            "Install it, or use --recorded-only and understand that it checks nothing live."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise DeploymentError(f"{' '.join(command)} timed out") from exc
    if done.returncode != 0:
        raise DeploymentError(
            f"{' '.join(command)} failed ({done.returncode}): {done.stderr.strip()[:300]}")
    return done.stdout


def live_host(record, run=_run):
    """What the host is running right now, from `fly image show`."""
    app = record.get("app")
    if not app:
        raise DeploymentError("the record does not name an app")
    raw = run(["fly", "image", "show", "--app", app, "--json"])
    try:
        images = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeploymentError(f"could not read `fly image show --json`: {exc}") from exc
    if not isinstance(images, list) or not images:
        raise DeploymentError(f"`fly image show` reported no image for {app}")
    # More than one machine means more than one row; they must agree, or the host is midway
    # through a rollout and there is no single answer to give.
    digests = {img.get("Digest") for img in images}
    if len(digests) > 1:
        raise DeploymentError(
            f"the host is running {len(digests)} different images at once: {sorted(digests)}. "
            "A rollout is in progress, or a machine did not update.")
    first = images[0]
    return first.get("Digest"), first.get("Tag")


def cached_laptop(record, run=_run):
    """What this machine has in its docker cache for the recorded release."""
    app = record.get("app")
    release = _side(record, "host").get("release")
    if not release:
        raise DeploymentError("the record does not name a release to look for")
    reference = f"registry.fly.io/{app}:{release}"
    raw = run(["docker", "inspect", "--format", "{{json .RepoDigests}}", reference])
    try:
        entries = json.loads(raw.strip() or "[]")
    except json.JSONDecodeError as exc:
        raise DeploymentError(f"could not read `docker inspect` output: {exc}") from exc
    # Selected by repository rather than by position: an image can carry digests for several
    # repositories, and RepoDigests[0] is not guaranteed to be the fly.io one.
    wanted = f"registry.fly.io/{app}@"
    for entry in entries or []:
        if isinstance(entry, str) and entry.startswith(wanted):
            return entry.split("@", 1)[1]
    raise DeploymentError(
        f"{reference} is not in this machine's docker cache with a {wanted}... digest. "
        f"Pull it: `fly auth docker && docker pull {reference}`")


def check_recorded(record):
    """The file-shape check. Says nothing about what is deployed or cached -- see check_live."""
    host = _side(record, "host").get("digest")
    if not _is_digest(host):
        raise DeploymentError(
            f"the host digest is not a sha256 content digest: {host!r}. "
            "Record it with `fly image show`.")

    laptop = _side(record, "laptop").get("digest")
    if laptop is None:
        raise DeploymentError(
            "the demo laptop has not cached the deployed image yet, so step 3 of the D-016 "
            "fallback chain is untested. Pull it and record the digest before Demo Day -- see "
            "docs/server-deploy.md.")
    if not _is_digest(laptop):
        raise DeploymentError(f"the laptop digest is not a sha256 content digest: {laptop!r}")
    if laptop != host:
        raise DeploymentError(
            "the laptop is NOT running the deployed image.\n"
            f"  host:   {host}\n"
            f"  laptop: {laptop}\n"
            "A local `docker build` produces a different image; the laptop must PULL the "
            "deployed one, or the fallback changes the system rather than the network path.")
    return host


def check_live(record, run=_run):
    """Ask the host and the docker cache, and hold the record to both.

    Three things have to agree: what the host serves, what this machine has cached, and what the
    repository claims. A redeploy breaks the first two against the third, which is the case the
    recorded-only check cannot see.
    """
    recorded = check_recorded(record)
    host_digest, host_release = live_host(record, run=run)
    if not _is_digest(host_digest):
        raise DeploymentError(f"the host reported no usable digest: {host_digest!r}")

    if host_digest != recorded:
        raise DeploymentError(
            "the host is running an image the repository does not record.\n"
            f"  host now:  {host_digest} ({host_release})\n"
            f"  recorded:  {recorded} ({_side(record, 'host').get('release')})\n"
            "A deploy happened and data/deployment.json was not updated, so the cached laptop "
            "image is stale too. Re-record both -- see docs/server-deploy.md.")

    cached = cached_laptop(record, run=run)
    if cached != host_digest:
        raise DeploymentError(
            "this machine's cached image is not what the host is running.\n"
            f"  host:   {host_digest}\n"
            f"  cached: {cached}\n"
            "Pull the deployed release rather than rebuilding it.")
    return f"ok  host, laptop cache and record all agree  {host_digest} ({host_release})"


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args == ["verify"]:
        live = True
    elif args == ["verify", "--recorded-only"]:
        live = False
    else:
        print("usage: python -m frontdoor_server.deployment verify [--recorded-only]",
              file=sys.stderr)
        return 2
    try:
        record = load()
        if live:
            print(check_live(record))
        else:
            digest = check_recorded(record)
            print(f"ok  the record is internally consistent  {digest}")
            print("NOT a live check: nothing here asked the host or the docker cache. "
                  "Run `verify` without --recorded-only before Demo Day.", file=sys.stderr)
    except DeploymentError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
