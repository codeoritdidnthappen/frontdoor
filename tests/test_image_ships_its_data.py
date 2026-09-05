"""The image must carry the data the server reads at request time (TICK-337).

The failure this pins is silent by construction: the build succeeds, the server
starts, /map/data answers 200, and the pin list is empty because the dataset it
names was never copied in. Production served exactly that for days. A unit test
cannot see inside a built image, so these read the build inputs and assert that
the files the server names are not excluded from it.
"""

from pathlib import Path

import pytest

from frontdoor.claims import DEFAULT_CLAIMS_PATH
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


#: Every store the running server WRITES, and the variable that relocates it.
#:
#: The container filesystem is replaced on every deploy, so a default relative path means the
#: records live until the next deploy and then disappear -- and both loaders answer a missing
#: file with an empty result, so nothing reports the loss. The image must redirect each of
#: them, and the host must mount something at that place.
#:
#: Claims are worse than scans, not merely equal to them. A claim carries the only bearer token
#: for an approved workspace, so losing the file 404s every workspace that existed -- while the
#: `owner_confirmed` flag a claim authorised persists in the scan store on the volume, and the
#: map goes on showing Owner-confirmed pins backed by claims that no longer exist.
#:
#: `data/labels.csv` is deliberately absent from this list. `POST /labels` writes it inside the
#: container and those rows are lost on redeploy, which TICK-282 records as a known limitation
#: of that first version rather than a defect; docs/server-deploy.md says to download them
#: first. If it is ever given a volume, add it here.
RUNTIME_STORES = (
    ("FRONTDOOR_SCANS", DEFAULT_SCANS_PATH),
    ("FRONTDOOR_CLAIMS", DEFAULT_CLAIMS_PATH),
)


@pytest.mark.parametrize("variable, default", RUNTIME_STORES, ids=lambda value: str(value))
def test_every_store_written_at_run_time_is_pointed_at_a_mounted_volume(variable, default):
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert f"ENV {variable}=" in dockerfile, (
        f"the image leaves {variable} on the ephemeral container filesystem"
    )
    path = dockerfile.split(f"ENV {variable}=")[1].split()[0]
    assert path != default
    assert path.startswith("/"), f"{variable} must be an absolute path on a mount"

    fly = (ROOT / "fly.toml").read_text(encoding="utf-8")
    assert "[mounts]" in fly, "nothing is mounted, so the redirected path is still ephemeral"
    destination = fly.split("destination = ")[1].split("\n")[0].strip().strip('"')
    assert path.startswith(destination.rstrip("/") + "/"), (
        f"{variable} points at {path}, which is not inside the mount at {destination}"
    )


def test_the_build_files_do_not_claim_scans_are_the_only_state_written():
    """The sentence that made an ephemeral claims path look like nothing was missing.

    Both files said community scans were the only state this app writes. They were not -- owner
    claims and `POST /labels` rows are written too -- and that sentence is what a reader
    checking for a missing volume redirect would have believed.
    """
    for name in ("Dockerfile", "fly.toml"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "are the only state this app writes" not in text, (
            f"{name} still says scans are the only run-time state; they are not"
        )
