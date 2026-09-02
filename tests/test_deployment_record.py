"""The D-016 fallback must actually run the deployed image (TICK-062, #50).

The chain is a mitigation only if steps 1-3 run the SAME image. If the laptop runs a locally built
one, "the laptop version" is a different system being demoed under pressure -- the failure R-4
exists to prevent.

The check these tests guard queries the live host and this machine's docker cache. An earlier
revision compared two strings inside the committed record and called that a check, which passes
green in precisely the case that matters: a redeploy mints a new release, nobody edits the file,
and the laptop still holds last week's image. `test_a_stale_record_after_a_redeploy_is_caught`
is that case.
"""

import json
import re
from pathlib import Path

import pytest

from frontdoor_server import deployment
from frontdoor_server.deployment import (
    DeploymentError,
    cached_laptop,
    check_live,
    check_recorded,
    live_host,
    load,
    main,
)

HOST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64
APP = "frontdoor-measure"
RELEASE = "deployment-TEST"


def record(host=HOST, laptop=HOST, release=RELEASE):
    return {"app": APP, "host": {"digest": host, "release": release},
            "laptop": {"digest": laptop}}


def runner(host_digest=HOST, host_tag=RELEASE, cached=HOST, fail=None):
    """A fake `fly`/`docker`, so every branch runs in CI where neither exists."""
    def run(command):
        if fail == command[0]:
            raise DeploymentError(f"{command[0]} is not installed")
        if command[0] == "fly":
            return json.dumps([{"Digest": host_digest, "Tag": host_tag,
                                "Registry": "registry.fly.io", "Repository": APP}])
        if command[0] == "docker":
            if cached is None:
                return "[]"
            return json.dumps([f"registry.fly.io/{APP}@{cached}"])
        raise AssertionError(f"unexpected command {command}")
    return run


# --- the live check: what it is actually for ---------------------------------------------

def test_everything_agreeing_passes():
    assert "ok" in check_live(record(), run=runner())


def test_a_stale_record_after_a_redeploy_is_caught():
    """THE case. A deploy mints a new release; nobody edits data/deployment.json.

    The record stays internally consistent -- a human updating one field would update both -- so
    a file-against-itself check reports success while the laptop holds the previous image.
    """
    stale = record(host=OTHER, laptop=OTHER)
    check_recorded(stale)  # internally consistent, so the weak check is happy
    with pytest.raises(DeploymentError, match="does not record"):
        check_live(stale, run=runner(host_digest=HOST))


def test_a_laptop_holding_the_previous_image_is_caught():
    with pytest.raises(DeploymentError, match="cached image is not what the host is running"):
        check_live(record(), run=runner(cached=OTHER))


def test_an_uncached_laptop_is_caught_even_when_the_record_claims_otherwise():
    """The record says the laptop has it; the docker cache says it does not. The cache wins."""
    with pytest.raises(DeploymentError, match="not in this machine's docker cache"):
        check_live(record(), run=runner(cached=None))


def test_a_host_midway_through_a_rollout_is_reported_not_guessed_at():
    def run(command):
        if command[0] == "fly":
            return json.dumps([{"Digest": HOST, "Tag": RELEASE},
                               {"Digest": OTHER, "Tag": "deployment-OLD"}])
        return json.dumps([f"registry.fly.io/{APP}@{HOST}"])
    with pytest.raises(DeploymentError, match="different images at once"):
        check_live(record(), run=run)


def test_a_missing_tool_is_named_rather_than_silently_skipped():
    for tool in ("fly", "docker"):
        with pytest.raises(DeploymentError, match=tool):
            check_live(record(), run=runner(fail=tool))


def test_the_fly_digest_is_selected_by_repository_not_by_position():
    """An image can carry digests for several repositories; RepoDigests[0] need not be ours."""
    def run(command):
        if command[0] == "fly":
            return json.dumps([{"Digest": HOST, "Tag": RELEASE}])
        return json.dumps([f"docker.io/someone/else@{OTHER}",
                           f"registry.fly.io/{APP}@{HOST}"])
    assert cached_laptop(record(), run=run) == HOST


def test_a_host_reporting_no_image_is_reported():
    def run(command):
        return "[]" if command[0] == "fly" else json.dumps([f"registry.fly.io/{APP}@{HOST}"])
    with pytest.raises(DeploymentError, match="no image"):
        live_host(record(), run=run)


def test_unreadable_tool_output_is_reported_not_crashed():
    with pytest.raises(DeploymentError):
        live_host(record(), run=lambda c: "not json")
    with pytest.raises(DeploymentError):
        cached_laptop(record(), run=lambda c: "not json")


# --- the record's own shape --------------------------------------------------------------

def test_matching_digests_pass_the_recorded_check():
    assert check_recorded(record()) == HOST


def test_a_laptop_running_a_different_image_fails():
    with pytest.raises(DeploymentError, match="NOT running the deployed image"):
        check_recorded(record(laptop=OTHER))


def test_an_uncached_laptop_fails_rather_than_passing_with_a_note():
    with pytest.raises(DeploymentError, match="has not cached"):
        check_recorded(record(laptop=None))


@pytest.mark.parametrize("bad", [
    "", "sha256:", "a" * 64, "sha256:" + "a" * 63, "sha256:" + "a" * 65,
    "sha256:" + "A" * 64, "sha256:" + "g" * 64, "sha256:" + "a" * 64 + " ",
    " sha256:" + "a" * 64, "prefix sha256:" + "a" * 64, 42, None, ["sha256:"],
])
def test_a_malformed_host_digest_is_refused(bad):
    with pytest.raises(DeploymentError):
        check_recorded(record(host=bad))


def test_a_missing_section_is_reported_not_crashed():
    for broken in ({}, {"host": {"digest": HOST}}, {"host": None, "laptop": None}):
        with pytest.raises(DeploymentError):
            check_recorded(broken)


# --- the committed record and the runbook ------------------------------------------------

REPO = Path(__file__).resolve().parents[1]
RUNBOOK = REPO / "docs" / "server-deploy.md"


def test_the_committed_record_is_internally_consistent():
    """Weak by construction -- it cannot see a redeploy. The live check is what proves that."""
    check_recorded(load())


def test_the_committed_record_names_the_live_app():
    committed = load()
    assert committed["app"] == APP
    assert committed["region"] == "sjc"


def test_the_runbook_mentions_no_digest_other_than_the_recorded_one():
    """Presence is not enough: a stale digest elsewhere in the file is what an operator pastes.

    An earlier version of this test asserted only that the recorded digest APPEARS. After a
    redeploy where someone updated the record and the digest line but not the `docker run`
    example, it stayed green while the runbook told the operator to run the previous image.
    """
    text = RUNBOOK.read_text(encoding="utf-8")
    recorded = load()["host"]["digest"]
    found = set(re.findall(r"sha256:[0-9a-f]{64}", text))
    assert found <= {recorded}, f"the runbook names digests that are not deployed: {found - {recorded}}"
    assert recorded in found, "the runbook does not name the deployed digest at all"


def test_the_runbook_mentions_no_release_other_than_the_recorded_one():
    text = RUNBOOK.read_text(encoding="utf-8")
    recorded = load()["host"]["release"]
    found = set(re.findall(r"deployment-[0-9A-Z]{20,}", text))
    assert found <= {recorded}, f"the runbook names stale releases: {found - {recorded}}"


@pytest.mark.parametrize("name", ["ARCHITECTURE.md", "README.md", "docs/server-deploy.md"])
def test_every_document_showing_docker_build_warns_it_is_not_the_fallback(name):
    """Step 3 must PULL.

    A local build is a different image that came from the same source -- the thing D-016's step 3
    exists to rule out. ARCHITECTURE's build block sat three lines above the fallback chain with
    nothing between them, so a reader following it to stand up step 3 built locally.
    """
    text = (REPO / name).read_text(encoding="utf-8")
    if "docker build" not in text:
        return
    assert "pull" in text.lower(), f"{name} shows docker build and never mentions pulling"
    assert re.search(r"(different image|not for step 3|must \*\*pull\*\*)", text, re.I), (
        f"{name} shows docker build without warning that the fallback must pull the deployed image"
    )


# --- the CLI -----------------------------------------------------------------------------

def test_the_cli_refuses_an_unknown_command(capsys):
    assert main(["deploy"]) == 2


def test_the_recorded_only_mode_says_it_is_not_a_live_check(monkeypatch, capsys):
    monkeypatch.setattr(deployment, "load", lambda *a, **k: record())
    assert main(["verify", "--recorded-only"]) == 0
    out = capsys.readouterr()
    assert "NOT a live check" in out.err


def test_the_cli_returns_one_when_the_host_has_moved_on(monkeypatch, capsys):
    monkeypatch.setattr(deployment, "load", lambda *a, **k: record())
    monkeypatch.setattr(deployment, "_run", runner(host_digest=OTHER))
    assert main(["verify"]) == 1
    assert "does not record" in capsys.readouterr().err


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
