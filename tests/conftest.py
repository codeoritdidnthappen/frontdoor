"""Makes the repo root importable, so `from tests.x import y` works under bare `pytest`.

CI runs `pytest`, not `python -m pytest`. The `-m` form puts the working directory on `sys.path`;
the bare form does not, so cross-test imports resolved on a laptop and failed collection on CI —
which meant the tests guarding the seal never ran on a pull request. Adding the root here, rather
than a `tests/__init__.py`, keeps pytest's rootdir-based discovery unchanged.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


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
    from frontdoor import storage

    storage._load_dotenv_once()
