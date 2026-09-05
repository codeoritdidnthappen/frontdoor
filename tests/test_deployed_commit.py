"""The running server must be able to say which commit it is (#337).

On 2026-09-05 the host served the previous day's image for a full day while `main` moved on. A bug
that had been fixed and merged was still live, and got reported a second time, because nothing
could answer "what is actually running". `/health` says `{"status": "ok"}` and `data/deployment.json`
compares image digests between the host and the laptop -- neither answers this.
"""

import json
from urllib.error import URLError

import pytest

from frontdoor_server.app import create_app
from frontdoor_server.deployment import (
    DeploymentError,
    check_drift,
    deployed_commit,
)

SHA = "a" * 40
OTHER = "b" * 40


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("FRONTDOOR_COMMIT", raising=False)
    return create_app().test_client()


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return self._payload if isinstance(self._payload, bytes) else json.dumps(
            self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def opener_for(payload):
    return lambda url: _Response(payload)


# --- the endpoint -------------------------------------------------------------


def test_version_reports_the_baked_commit(monkeypatch):
    monkeypatch.setenv("FRONTDOOR_COMMIT", SHA)
    body = create_app().test_client().get("/version").get_json()
    assert body == {"commit": SHA}


def test_version_says_unknown_rather_than_guessing(client):
    """An image built without the build arg must not invent an answer.

    A wrong commit is worse than no commit: the whole value of this endpoint is being able to
    trust it when a live probe disagrees with the checkout.
    """
    assert client.get("/version").get_json() == {"commit": "unknown"}


def test_version_needs_no_credentials(client):
    """"Which commit is the demo running" should not require a Fly login."""
    assert client.get("/version").status_code == 200


def test_health_is_untouched(client):
    """The fallback chain's liveness probe stays exactly what it was (TICK-064)."""
    assert client.get("/health").get_json() == {"status": "ok"}


# --- the drift check ----------------------------------------------------------


def test_matching_commit_is_ok():
    message = check_drift(
        ref="HEAD", opener=opener_for({"commit": SHA}), run=lambda cmd: SHA + "\n")
    assert "ok" in message and SHA[:12] in message


def test_drift_is_an_error_naming_both_sides():
    with pytest.raises(DeploymentError) as caught:
        check_drift(ref="HEAD", opener=opener_for({"commit": SHA}),
                    run=lambda cmd: OTHER + "\n")
    text = str(caught.value)
    assert "DRIFT" in text and SHA[:12] in text and OTHER[:12] in text


def test_an_unidentifiable_server_is_an_error_not_a_pass():
    """"unknown" must never compare equal to anything -- that would hide the drift."""
    with pytest.raises(DeploymentError, match="unknown"):
        deployed_commit(opener=opener_for({"commit": "unknown"}))


def test_a_server_that_answers_without_a_commit_is_an_error():
    with pytest.raises(DeploymentError, match="without a commit"):
        deployed_commit(opener=opener_for({}))


def test_an_unreachable_server_says_so_rather_than_passing():
    def boom(url):
        raise URLError("connection refused")

    with pytest.raises(DeploymentError, match="could not reach"):
        deployed_commit(opener=boom)


def test_a_non_json_answer_is_an_error():
    """A captive portal answering with HTML must not read as a matching deploy."""
    with pytest.raises(DeploymentError, match="did not answer with JSON"):
        deployed_commit(opener=opener_for(b"<html>nope</html>"))


def test_a_404_is_named_as_a_stale_image_not_as_unreachable():
    """The likeliest failure for a while, and the wrong diagnosis sends someone to the network.

    A server that answers 404 is up; it just predates /version. That IS drift.
    """
    from urllib.error import HTTPError

    def missing(url):
        raise HTTPError(url, 404, "NOT FOUND", {}, None)

    with pytest.raises(DeploymentError, match="predates it"):
        deployed_commit(opener=missing)


def test_another_http_error_is_reported_with_its_status():
    from urllib.error import HTTPError

    def broken(url):
        raise HTTPError(url, 502, "Bad Gateway", {}, None)

    with pytest.raises(DeploymentError, match="502"):
        deployed_commit(opener=broken)
