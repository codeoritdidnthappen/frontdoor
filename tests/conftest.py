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



@pytest.fixture(autouse=True)
def _each_test_gets_an_empty_assessment_store(tmp_path_factory):
    """Point FRONTDOOR_ASSESSMENTS at a fresh empty file for every test (TICK-435).

    /screen and /screen/publish now serve one assessment per photograph, keyed
    by the sha256 of the processed bytes. Every endpoint test posts the SAME
    fixture JPEG, so without this the first test to run would have its verdicts
    served to every later one -- a fake engine returning `absent` would be
    ignored in favour of the `present` a previous test stored, and the failure
    would depend on collection order. It would also write the store into the
    working tree.

    Fresh per test rather than per session: a test that wants a hit sets its
    own path (or posts twice), and a test that wants a miss must not inherit
    another test's answer. Same os.environ-with-restore shape as the fixture
    below, and for the same ordering reason.
    """
    import os

    store = tmp_path_factory.mktemp("assessment-store") / "assessments.jsonl"
    previous = os.environ.get("FRONTDOOR_ASSESSMENTS")
    os.environ["FRONTDOOR_ASSESSMENTS"] = str(store)
    yield
    if previous is None:
        os.environ.pop("FRONTDOOR_ASSESSMENTS", None)
    else:
        os.environ["FRONTDOOR_ASSESSMENTS"] = previous


@pytest.fixture(autouse=True)
def _curated_publication_off_by_default(tmp_path_factory):
    """Point FRONTDOOR_PUBLISHED_SCANS at nothing unless a test says otherwise.

    `data/published_scans.jsonl` is a COMMITTED dataset (TICK-333), unlike
    `data/scans.jsonl`, which is runtime state and normally absent from a
    checkout. So the moment it landed, every test that asks /map/data what it
    serves started seeing 46 real scan records it never set up -- five pins
    silently green in tests about a missing dataset, an empty store, or one
    published record. A test must not depend on which datasets happen to be in
    the tree.

    The tests that DO care set the variable themselves and win, because an
    autouse fixture is applied before the test body runs: `test_scan_publish`
    points it at the real file and pins what the publication serves, and
    `test_map_states` points it at fixtures and pins the two-store merge.

    Deliberately NOT `monkeypatch`: an autouse fixture in this file is set up
    before a test module's own autouse fixtures, so requesting `monkeypatch`
    here would build it first and tear it down LAST -- reversing the order two
    tests in test_server_needs_the_library depend on, where a module reload has
    to run after monkeypatch has put `ARM_NAMES` back. os.environ with an
    explicit restore keeps this fixture out of that ordering entirely.
    """
    import os

    absent = tmp_path_factory.mktemp("no-curated-publication") / "absent.jsonl"
    previous = os.environ.get("FRONTDOOR_PUBLISHED_SCANS")
    os.environ["FRONTDOOR_PUBLISHED_SCANS"] = str(absent)
    yield
    if previous is None:
        os.environ.pop("FRONTDOOR_PUBLISHED_SCANS", None)
    else:
        os.environ["FRONTDOOR_PUBLISHED_SCANS"] = previous
