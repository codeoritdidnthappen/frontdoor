"""The deployed image is recorded and checkable (TICK-062, #50).

D-016's fallback chain is a mitigation only if steps 1-3 run the SAME image. If the laptop runs a
locally built one, "the laptop version" is a different system being demoed under pressure, which
is the failure R-4 exists to prevent. These tests guard the check that says so.
"""

import json

import pytest

from frontdoor_server import deployment
from frontdoor_server.deployment import DeploymentError, check, load, main

HOST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64


def record(host=HOST, laptop=HOST):
    return {"host": {"digest": host}, "laptop": {"digest": laptop}}


def test_matching_digests_pass():
    assert "ok" in check(record())


def test_a_laptop_running_a_different_image_fails():
    """The whole point. A local `docker build` gives a different digest for the same source."""
    with pytest.raises(DeploymentError, match="NOT running the deployed image"):
        check(record(laptop=OTHER))


def test_an_uncached_laptop_fails_rather_than_passing_with_a_note():
    """Not-yet-pulled and pulled-and-matching must not look the same.

    A check that goes green while the image is absent reports that the fallback works when nobody
    has tried it -- and the point is to find out before Demo Day rather than on it.
    """
    with pytest.raises(DeploymentError, match="has not cached"):
        check(record(laptop=None))


@pytest.mark.parametrize("bad", [
    "", "sha256:", "a" * 64, "sha256:" + "a" * 63, "sha256:" + "a" * 65,
    "sha256:" + "A" * 64, "sha256:" + "g" * 64, "sha256:" + "a" * 64 + " ", 42, None,
])
def test_a_malformed_host_digest_is_refused(bad):
    with pytest.raises(DeploymentError):
        check(record(host=bad))


@pytest.mark.parametrize("bad", ["", "nonsense", "sha256:zz"])
def test_a_malformed_laptop_digest_is_refused(bad):
    with pytest.raises(DeploymentError):
        check(record(laptop=bad))


def test_a_digest_with_anything_around_it_is_refused():
    """Anchored, like the sidecar's sha256 pattern after TICK-228."""
    with pytest.raises(DeploymentError):
        check(record(host="prefix" + HOST))


def test_a_missing_section_is_reported_not_crashed():
    for broken in ({}, {"host": {"digest": HOST}}, {"host": None, "laptop": None}):
        with pytest.raises(DeploymentError):
            check(broken)


# --- the committed record itself ----------------------------------------------------------

def test_the_committed_record_names_the_live_app():
    committed = load()
    assert committed["app"] == "frontdoor-measure"
    assert committed["region"] == "sjc"


def test_the_committed_record_passes_its_own_check():
    """If this fails, the deployed image and the cached one have diverged, or one is unrecorded.

    Either way the fallback chain is not what D-016 says it is, and it fails here rather than in
    an atrium with no signal.
    """
    check(load())


def test_the_runbook_quotes_the_digest_that_is_actually_recorded():
    """Doc and record cannot drift: the runbook is what a person reads on the day."""
    from pathlib import Path

    runbook = (Path(__file__).resolve().parents[1] / "docs" / "server-deploy.md").read_text(
        encoding="utf-8")
    committed = load()
    assert committed["host"]["digest"] in runbook, "the runbook quotes a stale host digest"
    assert committed["host"]["release"] in runbook, "the runbook quotes a stale release"


# --- the CLI -----------------------------------------------------------------------------

def test_the_cli_reports_success(capsys):
    assert main(["verify"]) == 0
    assert "ok" in capsys.readouterr().out


def test_the_cli_refuses_an_unknown_command(capsys):
    assert main(["deploy"]) == 2


def test_the_cli_returns_one_on_a_mismatch(monkeypatch, capsys):
    monkeypatch.setattr(deployment, "load", lambda *a, **k: record(laptop=OTHER))
    assert main(["verify"]) == 1
    assert "NOT running the deployed image" in capsys.readouterr().err


def test_a_missing_record_file_is_reported(tmp_path):
    with pytest.raises(DeploymentError, match="missing"):
        load(tmp_path / "nope.json")


def test_an_unparseable_record_file_is_reported(tmp_path):
    bad = tmp_path / "deployment.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(DeploymentError, match="not valid JSON"):
        load(bad)


def test_a_record_that_is_not_an_object_is_reported(tmp_path):
    bad = tmp_path / "deployment.json"
    bad.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(DeploymentError, match="must hold an object"):
        load(bad)
