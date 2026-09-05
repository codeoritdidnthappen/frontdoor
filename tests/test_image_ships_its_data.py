"""The image must carry the data the server reads at request time (TICK-337).

The failure this pins is silent by construction: the build succeeds, the server
starts, /map/data answers 200, and the pin list is empty because the dataset it
names was never copied in. Production served exactly that for days. A unit test
cannot see inside a built image, so these read the build inputs and assert that
the files the server names are not excluded from it.
"""

from pathlib import Path

import pytest

from frontdoor.scan_records import DEFAULT_SCANS_PATH
from frontdoor_server.map_view import (
    DEFAULT_DATASET_PATH,
    DEFAULT_EXTERNAL_COMMONS_PATH,
    DEFAULT_EXTERNAL_OSM_PATH,
)

ROOT = Path(__file__).resolve().parents[1]
SERVER_READS = (
    DEFAULT_DATASET_PATH,
    DEFAULT_EXTERNAL_OSM_PATH,
    DEFAULT_EXTERNAL_COMMONS_PATH,
)


@pytest.mark.parametrize("relative", SERVER_READS)
def test_every_path_the_server_reads_exists_in_the_repository(relative):
    assert (ROOT / relative).is_file(), (
        f"{relative} is named by the server as a default path but is not in the tree"
    )


@pytest.mark.parametrize("relative", SERVER_READS)
def test_the_dockerignore_does_not_exclude_it(relative):
    """.dockerignore starts with `*`, so anything not re-included is silently absent."""
    patterns = [
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    negations = {pattern.lstrip("!").rstrip("/*").rstrip("/") for pattern in patterns if pattern.startswith("!")}
    parts = Path(relative).parts
    covered = any(
        "/".join(parts[: index + 1]) in negations or relative in negations
        for index in range(len(parts))
    )
    assert covered, f"{relative} is not re-included in .dockerignore and will not ship"


@pytest.mark.parametrize("relative", SERVER_READS)
def test_the_dockerfile_copies_it(relative):
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    parts = Path(relative).parts
    copied = any(
        f"COPY {'/'.join(parts[: index + 1])} " in dockerfile
        for index in range(len(parts))
    )
    assert copied, f"{relative} is never COPYied into the image"


def test_the_scan_store_is_pointed_at_a_mounted_volume():
    """Scans are the only state written at run time.

    The container filesystem is replaced on every deploy, so the default relative
    path means a published scan lives until the next deploy and then disappears.
    The image must redirect it, and the host must mount something at that place.
    """
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "ENV FRONTDOOR_SCANS=" in dockerfile, (
        "the image leaves the scan store on the ephemeral container filesystem"
    )
    scans_path = dockerfile.split("ENV FRONTDOOR_SCANS=")[1].split()[0]
    assert scans_path != DEFAULT_SCANS_PATH
    assert scans_path.startswith("/"), "the scan store must be an absolute path on a mount"

    fly = (ROOT / "fly.toml").read_text(encoding="utf-8")
    assert "[mounts]" in fly, "nothing is mounted, so the redirected path is still ephemeral"
    destination = fly.split("destination = ")[1].split("\n")[0].strip().strip('"')
    assert scans_path.startswith(destination.rstrip("/") + "/"), (
        f"the scan store {scans_path} is not inside the mount at {destination}"
    )
