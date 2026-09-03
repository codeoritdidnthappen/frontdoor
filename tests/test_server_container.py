"""Build and run the TICK-062 image, then hit it as a client would.

The tests that build are skipped when the Docker daemon is not running, and CI does not
start one. So the properties that must not regress unwatched -- nothing in the build
context that could carry a credential, and a fit check against the size we actually
deploy -- are also asserted at the bottom of this file by reading the files themselves.
"""

import contextlib
import json
import os
import sys
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import PurePosixPath

import pytest

from frontdoor_server.app import validate_measure_response
from tests.conftest import REPO_ROOT
from tests.test_measure_endpoint import architecture_example

IMAGE = "frontdoor-server:tick062"

# The size of the machine actually deployed -- Fly `shared-cpu-1x`, 256 MB (D-031). A fit
# check against the real instance, not a ceiling probe: the server still serves on 24 MiB
# and is OOM-killed at 16 MiB. What it would catch is the change that matters -- pulling
# the depth model into the image, or buffering an upload in memory instead of letting
# werkzeug spool it to disk.
MEMORY_CAP = "256m"

# A full-resolution still is a few megabytes, well above what the other tests send.
FULL_RESOLUTION_STILL = b"\xff\xd8\xff\xe0" + b"x" * (12 * 1024 * 1024)

# Every credential this project holds is FRONTDOOR_*_ACCESS_KEY / _SECRET_KEY (.env.example).
# Matching the prefix rather than "KEY" keeps the base image's own GPG_KEY out of it.
CREDENTIAL_PREFIX = "FRONTDOOR_"


def _docker_running():
    if not shutil.which("docker"):
        return False
    try:
        subprocess.run(
            ["docker", "info"],
            check=True,
            capture_output=True,
            timeout=15,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False


# CI's pytest job is a 5-minute runner without a warm build cache. The flask
# client tests already cover the contract; this module is the local proof the
# image builds and answers.
requires_docker = pytest.mark.skipif(
    bool(os.environ.get("CI")) or not _docker_running(),
    reason="docker image tests run locally, not on the 5-minute CI job",
)


def _run(args, **kwargs):
    return subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )


@pytest.fixture(scope="module")
def built_image():
    _run(["docker", "build", "-t", IMAGE, str(REPO_ROOT)], timeout=600)
    return IMAGE


@contextlib.contextmanager
def _serve(*extra_run_args):
    """Run the built image and yield (base URL, container id) once /health answers."""
    cid = _run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "-p",
            "127.0.0.1:0:8080",
            "-e",
            "PORT=8080",
            *extra_run_args,
            IMAGE,
        ]
    ).stdout.strip()
    try:
        published = _run(["docker", "port", cid, "8080"]).stdout.strip()
        # "127.0.0.1:49152" or "0.0.0.0:49152"
        host_port = published.rsplit(":", 1)[-1]
        url = f"http://127.0.0.1:{host_port}"
        deadline = time.time() + 30
        last_error = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{url}/health", timeout=2) as response:
                    if response.status == 200:
                        yield url, cid
                        return
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                last_error = exc
                time.sleep(0.25)
        raise AssertionError(f"container never answered /health: {last_error}")
    finally:
        subprocess.run(["docker", "stop", cid], capture_output=True, timeout=30)


@pytest.fixture(scope="module")
def container_url(built_image):
    with _serve() as (url, _):
        yield url


@pytest.fixture(scope="module")
def capped_container_url(built_image):
    with _serve("-m", MEMORY_CAP) as (url, _):
        yield url


def _post_measure(url, sidecar, image=b"not-a-real-jpeg"):
    boundary = uuid.uuid4().hex
    payload = json.dumps(sidecar).encode()
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="sidecar"\r\n\r\n'.encode()
        + payload
        + b"\r\n"
        + f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="image"; filename="c.jpg"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n".encode()
        + image
        + b"\r\n"
        + f"--{boundary}--\r\n".encode()
    )
    request = urllib.request.Request(
        f"{url}/measure",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, json.loads(response.read())


@requires_docker
def test_container_health(container_url):
    with urllib.request.urlopen(f"{container_url}/health", timeout=5) as response:
        assert response.status == 200
        assert json.loads(response.read()) == {"status": "ok"}


@requires_docker
def test_container_measure_matches_live_contract(container_url):
    status, body = _post_measure(container_url, architecture_example())
    assert status == 200
    # The committed contract, checked against what the container actually put on the wire
    # rather than against the source tree the flask-client tests import.
    validate_measure_response(body)
    assert body["stub"] is True
    assert body["arms"]["B"]["absent_reason"] == "unavailable"
    # Arm C is cut, not unavailable (D-030). The container must carry the same
    # distinction as the in-process app, or the demo would show a different answer
    # from the one the tests check.
    assert body["arms"]["C"]["absent_reason"] == "cut"
    assert "rise_in" in body["arms"]["A"]
    assert "rise_in" in body["arms"]["A_prime"]


@requires_docker
def test_image_id_is_content_addressed(built_image):
    image_id = _run(["docker", "image", "inspect", "-f", "{{.Id}}", IMAGE]).stdout.strip()
    assert image_id.startswith("sha256:")
    assert len(image_id) > len("sha256:") + 16


@requires_docker
def test_serves_a_full_resolution_still_under_the_memory_cap(capped_container_url):
    """The deployed machine has to hold a real capture, not a token one."""
    status, body = _post_measure(
        capped_container_url, architecture_example(), image=FULL_RESOLUTION_STILL
    )
    assert status == 200
    validate_measure_response(body)
    assert body["capture_id"] == architecture_example()["capture_id"]

    with urllib.request.urlopen(f"{capped_container_url}/health", timeout=5) as response:
        assert response.status == 200


@requires_docker
def test_the_memory_cap_holds_under_concurrent_uploads(capped_container_url):
    """Four clients uploading full-resolution stills at once, against two worker threads.

    The cap is a cgroup limit, so exceeding it means the OOM killer takes the process and
    these requests fail -- which makes four 200s the assertion, with no need to scrape
    `docker stats`. What keeps the footprint flat is werkzeug spooling a large file part to
    disk rather than holding it in memory.
    """
    statuses = []
    lock = threading.Lock()

    def upload():
        status, _ = _post_measure(
            capped_container_url, architecture_example(), image=FULL_RESOLUTION_STILL
        )
        with lock:
            statuses.append(status)

    uploads = [threading.Thread(target=upload) for _ in range(4)]
    for upload_thread in uploads:
        upload_thread.start()
    for upload_thread in uploads:
        upload_thread.join(timeout=120)

    assert statuses == [200, 200, 200, 200]

    with urllib.request.urlopen(f"{capped_container_url}/health", timeout=5) as response:
        assert response.status == 200


@requires_docker
def test_the_server_runs_as_pid_one(built_image):
    """A stop signal has to reach gunicorn, not a shell that dies holding the door.

    Under a shell-form CMD, PID 1 is `sh`: it takes the SIGTERM, exits, and the container
    goes down with in-flight requests still open. Delivering signals to the process being
    packaged is part of packaging it.
    """
    with _serve() as (_, cid):
        pid_one = _run(["docker", "exec", cid, "cat", "/proc/1/comm"]).stdout.strip()

    assert pid_one.startswith("gunicorn")


@requires_docker
def test_image_carries_no_credentials(built_image):
    """R2 keys reach the container from the environment at run time, never in the layers.

    A real `.env` sits in the working tree, so this is what stands between a loosened
    `.dockerignore` and live bucket keys inside an image pushed to a public host.
    """
    env = json.loads(
        _run(["docker", "image", "inspect", "-f", "{{json .Config.Env}}", IMAGE]).stdout
    )
    assert [value for value in env if value.startswith(CREDENTIAL_PREFIX)] == []

    # python-dotenv is a runtime dependency, so a stray .env in a layer would be read and
    # believed. The base image's public CA bundle is not credential material and is ignored.
    found = _run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "sh",
            IMAGE,
            "-c",
            "find / -xdev -name '.env*' 2>/dev/null; true",
        ]
    ).stdout
    assert found.strip() == ""


# --- the same properties, without a docker daemon -----------------------------------------
#
# Everything above is skipped on CI, which is where a pull request is actually checked. These
# read the files the image is built from, so a change that would ship a credential -- or that
# would quietly stop testing the machine we deploy -- fails there too.

DOCKERIGNORE = REPO_ROOT / ".dockerignore"
DOCKERFILE = REPO_ROOT / "Dockerfile"
FLY_TOML = REPO_ROOT / "fly.toml"

# Names that would put a secret in a layer. Broader than the FRONTDOOR_ prefix the run-time
# check uses, because a build-time ARG is as likely to be called API_KEY as anything.
_CREDENTIAL_NAME = re.compile(r"KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL", re.IGNORECASE)


def _context_leaks(dockerignore_text):
    """Reasons the build context could carry a `.env`, or [] if it cannot.

    A real `.env` sits in the working tree and python-dotenv is a runtime dependency, so one
    in a layer would be read and believed. What stands between that and an image on a public
    registry is this file denying everything and re-admitting the package by name.
    """
    rules = [
        line.strip()
        for line in dockerignore_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    reasons = []
    if not rules or rules[0] != "*":
        reasons.append("the context is not deny-by-default: the first rule is not `*`")
    reasons += [
        f"`{rule}` re-admits a dotfile"
        for rule in rules
        if rule.startswith("!") and PurePosixPath(rule[1:]).name.startswith(".")
    ]
    # A rule ending in a wildcard re-admits whatever is under it, dotfiles included: `!src/**`
    # would ship `src/.env` while naming no dotfile itself. Reading the rules cannot settle
    # that, so ask the tree what is actually there.
    for rule in rules:
        if not rule.startswith("!") or not PurePosixPath(rule[1:]).name.endswith("*"):
            continue
        root = REPO_ROOT / PurePosixPath(rule[1:]).parent
        if not root.is_dir():
            continue
        reasons += [
            f"`{rule}` re-admits {found.relative_to(REPO_ROOT).as_posix()}"
            for found in sorted(root.rglob(".env*"))
        ]
    return reasons


def test_the_build_context_cannot_carry_a_credential_file():
    assert _context_leaks(DOCKERIGNORE.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    "leaky",
    [
        "# the allowlist is gone, so everything not named here is in\n.git\n__pycache__\n",
        "*\n!pyproject.toml\n!src\n!src/**\n!.env\n",
    ],
)
def test_a_loosened_ignore_file_is_caught(leaky):
    """The check above passes against a file nobody has touched; this is what makes it one."""
    assert _context_leaks(leaky)


def test_a_wildcard_negation_over_a_tree_holding_a_dotenv_is_caught(tmp_path, monkeypatch):
    """`!src/**` names no dotfile of its own, and would still ship one sitting under `src/`."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / ".env").write_text("FRONTDOOR_IMAGE_SECRET_KEY=live", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)
    assert _context_leaks("*\n!src\n!src/**\n")


def test_the_dockerfile_bakes_in_no_credential():
    """R2 keys reach the container as Fly secrets at run time, never through the build."""
    declared = re.findall(
        r"^\s*(?:ENV|ARG)\s+([A-Za-z_][A-Za-z0-9_]*)",
        DOCKERFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    # PORT is declared, so an empty list means the pattern stopped matching rather than that
    # the Dockerfile stopped declaring secrets.
    assert declared
    assert [name for name in declared if _CREDENTIAL_NAME.search(name)] == []


def test_the_memory_cap_under_test_is_the_deployed_machines_size():
    """MEMORY_CAP is a copy of fly.toml's number, and a copy goes stale silently.

    Resize the machine without resizing this and the fit check above keeps passing while
    holding the image to a machine we no longer run.
    """
    declared = re.search(
        r'^\s*memory\s*=\s*"(\d+)mb"',
        FLY_TOML.read_text(encoding="utf-8"),
        re.MULTILINE | re.IGNORECASE,
    )
    assert declared, "fly.toml declares no machine memory size"
    assert MEMORY_CAP == f"{declared.group(1)}m"
