"""The server entrypoint reads .env (#158's failure, one layer up).

`/screen` reads ANTHROPIC_API_KEY straight from the environment and `/upload` reads the upload
key and bucket credentials. Nothing loaded .env for the server process, so a key sitting
correctly in .env produced a 503 from the endpoint -- indistinguishable from a bad key, and it
cost a real debugging detour on 2026-09-03 before the cause turned out to be the loader rather
than the credential.

Run in a subprocess, because the loader is process-global (`_dotenv_loaded`) and because
import-time behaviour is exactly what is under test: asserting it in-process would prove only
that a already-imported module stayed imported.
"""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

PROBE = textwrap.dedent(
    """
    import json, os, sys
    sys.path.insert(0, {src!r})
    import frontdoor_server.wsgi as wsgi
    health = wsgi.app.test_client().get("/health")
    print(json.dumps({{
        "from_dotenv": os.environ.get("FRONTDOOR_TEST_MARKER"),
        "real_env_wins": os.environ.get("FRONTDOOR_TEST_PRESET"),
        "health_status": health.status_code,
        "health_body": health.get_json(),
    }}))
    """
)


def run_probe(tmp_path, env_text, extra_env=None):
    (tmp_path / ".env").write_text(env_text, encoding="utf-8")
    # Inherit the real environment and then STRIP it, rather than building a minimal one from
    # scratch. The scratch version hardcoded PATH=/usr/bin:/bin, which is not a path on Windows --
    # so these three tests failed for the one teammate who runs Windows, and he was excluding them
    # by hand as though they were a known platform exception. They were not; they were wrong.
    #
    # Inheriting keeps the interpreter launchable everywhere. Stripping keeps the intent: the
    # probe must not reach the developer's real credentials, or it would prove nothing about
    # loading them from the temporary .env this test writes.
    env = {
        k: v for k, v in os.environ.items()
        if not k.startswith(("FRONTDOOR_", "ANTHROPIC_"))
    }
    env["HOME"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)  # HOME's counterpart on Windows
    env["FRONTDOOR_MAP_DATASET"] = str(tmp_path / "nothing.json")
    env.update(extra_env or {})
    result = subprocess.run(
        [sys.executable, "-c", PROBE.format(src=str(REPO_ROOT / "src"))],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_importing_the_entrypoint_loads_dotenv(tmp_path):
    out = run_probe(tmp_path, "FRONTDOOR_TEST_MARKER=from-the-dotenv-file\n")
    assert out["from_dotenv"] == "from-the-dotenv-file"


def test_a_real_environment_variable_still_wins(tmp_path):
    """override=False. The container gets its secrets from Fly, and a stray .env baked into an
    image must never quietly replace them."""
    out = run_probe(
        tmp_path,
        "FRONTDOOR_TEST_MARKER=x\nFRONTDOOR_TEST_PRESET=from-the-dotenv-file\n",
        extra_env={"FRONTDOOR_TEST_PRESET": "from-the-real-environment"},
    )
    assert out["real_env_wins"] == "from-the-real-environment"


def test_no_dotenv_is_not_an_error(tmp_path):
    """A container has no .env at all; importing the entrypoint must still work."""
    out = run_probe(tmp_path, "")
    assert out["from_dotenv"] is None


@pytest.mark.parametrize(
    "depth_url",
    [None, "", "not a url"],
    ids=["absent", "empty", "malformed"],
)
def test_tick_262_ac_1_ac_6_wsgi_imports_with_bad_depth_config(
        tmp_path: Path, depth_url: str | None) -> None:
    extra_env = {
        "FRONTDOOR_UPLOAD_KEY": "configured-upload-key",
        "FRONTDOOR_DEPTH_INGEST_KEY": "configured-depth-key",
    }
    if depth_url is not None:
        extra_env["FRONTDOOR_DEPTH_INGEST_URL"] = depth_url

    out = run_probe(tmp_path, "", extra_env=extra_env)

    assert out["health_status"] == 200


def test_tick_262_ac_2_health_answers_with_bad_depth_config(tmp_path: Path) -> None:
    out = run_probe(
        tmp_path,
        "",
        extra_env={"FRONTDOOR_UPLOAD_KEY": "configured-upload-key"},
    )

    assert out["health_status"] == 200
    assert out["health_body"] == {"status": "ok"}
