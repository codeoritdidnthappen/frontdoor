"""Build and run the TICK-062 image, then hit it as a client would.

Skipped when the Docker daemon is not running. CI does not start Docker, so the
flask test client in test_measure_endpoint.py is what always runs.
"""

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid

import pytest

from tests.test_measure_endpoint import architecture_example

IMAGE = "frontdoor-server:tick062"


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
pytestmark = pytest.mark.skipif(
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
def container_url():
    from tests.conftest import REPO_ROOT

    _run(["docker", "build", "-t", IMAGE, str(REPO_ROOT)], timeout=600)
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
                        yield url
                        return
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                last_error = exc
                time.sleep(0.25)
        raise AssertionError(f"container never answered /health: {last_error}")
    finally:
        subprocess.run(["docker", "stop", cid], capture_output=True, timeout=30)


def _post_measure(url, sidecar):
    boundary = uuid.uuid4().hex
    image = b"not-a-real-jpeg"
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


def test_container_health(container_url):
    with urllib.request.urlopen(f"{container_url}/health", timeout=5) as response:
        assert response.status == 200
        assert json.loads(response.read()) == {"status": "ok"}


def test_container_measure_matches_live_contract(container_url):
    status, body = _post_measure(container_url, architecture_example())
    assert status == 200
    assert body["stub"] is True
    assert body["arms"]["B"]["absent_reason"] == "unavailable"
    assert body["arms"]["C"]["absent_reason"] == "unavailable"
    assert "rise_in" in body["arms"]["A"]
    assert "rise_in" in body["arms"]["A_prime"]


def test_image_id_is_content_addressed():
    image_id = _run(["docker", "image", "inspect", "-f", "{{.Id}}", IMAGE]).stdout.strip()
    assert image_id.startswith("sha256:")
    assert len(image_id) > len("sha256:") + 16
