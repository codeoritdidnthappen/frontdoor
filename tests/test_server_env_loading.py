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
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

PROBE = textwrap.dedent(
    """
    import json, os, sys
    sys.path.insert(0, {src!r})
    import frontdoor_server.wsgi  # noqa: F401  -- the import IS the thing under test
    print(json.dumps({{
        "from_dotenv": os.environ.get("FRONTDOOR_TEST_MARKER"),
        "real_env_wins": os.environ.get("FRONTDOOR_TEST_PRESET"),
    }}))
    """
)


def run_probe(tmp_path, env_text, extra_env=None):
    (tmp_path / ".env").write_text(env_text, encoding="utf-8")
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        # Keep the probe from reaching the developer's own credentials.
        "FRONTDOOR_MAP_DATASET": str(tmp_path / "nothing.json"),
    }
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
