"""Makes the repo root importable, so `from tests.x import y` works under bare `pytest`.

CI runs `pytest`, not `python -m pytest`. The `-m` form puts the working directory on `sys.path`;
the bare form does not, so cross-test imports resolved on a laptop and failed collection on CI —
which meant the tests guarding the seal never ran on a pull request. Adding the root here, rather
than a `tests/__init__.py`, keeps pytest's rootdir-based discovery unchanged.

`src` goes on the path for the same reason, one layer down. The editable install resolves
`frontdoor` to whichever checkout ran `pip install -e`, so a suite run inside a git worktree
imported the *main* checkout's modules and reported green on Python the branch had changed --
the branch's own source was never executed. Both entries are derived from this file's location,
so every checkout tests itself.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
for _path in (REPO_ROOT / "src", REPO_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


#: Read by `test_no_server_config_leaks_from_dotenv`, and by the fixture above, so the list
#: cannot drift between the thing that clears and the thing that checks.
SERVER_CONFIG_NOT_FROM_DOTENV = (
    "FRONTDOOR_UPLOAD_KEY",
    "FRONTDOOR_DEPTH_INGEST_URL",
    "FRONTDOOR_DEPTH_INGEST_KEY",
)


@pytest.fixture(scope="session", autouse=True)
def _load_dotenv_before_any_test():
    """Load `.env` once, up front, so which test runs first stops mattering.

    `frontdoor.storage._load_dotenv_once` caches on a module global, so the file was read
    inside whichever test touched storage first. That was invisible while nobody had a
    `.env`. With a real one present it breaks the suite two ways, and neither reproduces
    in CI, which has no `.env`:

      * a test that deletes `FRONTDOOR_DEPTH_*` and expects a missing-variable error gets
        those variables put BACK by the dotenv load its own call triggers, so the error
        never comes and the test fails;
      * every later test sees `_dotenv_loaded = True` and an environment already stripped
        by an earlier `monkeypatch` teardown, so the live storage tests cannot find
        credentials that are sitting in `.env`.

    Loading here makes the order deterministic: real values are present before the first
    test, and `monkeypatch.delenv` inside a test now stays deleted for that test.
    """
    import os

    from frontdoor import storage

    storage._load_dotenv_once()

    # ...and then take back the variables that are application CONFIG rather than storage
    # credentials.
    #
    # The load above exists so the opt-in live storage tests can find real credentials. It also,
    # unavoidably, hands the suite whatever else is in the operator's .env -- and
    # `create_app()` now reads FRONTDOOR_UPLOAD_KEY at CONSTRUCTION time and builds the
    # depth-ingest config from it, raising when the ingest URL is absent. So a developer who
    # follows data/STORAGE.md and fills in an upload key gets 38 failures and 68 collection
    # errors, while CI -- which has no .env -- stays green. Measured on 2026-09-03: 831 pass
    # without .env, 725 with it, and removing this one variable accounts for all 106.
    #
    # A test must not depend on the machine's server configuration. Every test that needs these
    # sets them with monkeypatch (test_upload_endpoint, test_depth_ingest), so clearing them here
    # costs nothing and makes the result the same everywhere.
    #
    # ANTHROPIC_API_KEY is deliberately NOT cleared: it is read per request rather than at
    # construction, so it cannot break collection, and the tests that care about the keyless path
    # delete it themselves.
    for name in SERVER_CONFIG_NOT_FROM_DOTENV:
        os.environ.pop(name, None)

