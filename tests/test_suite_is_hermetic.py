"""The suite's result must not depend on the developer's `.env` (found 2026-09-03).

`tests/conftest.py` loads `.env` on purpose, so the opt-in live storage tests can find real
credentials. That also hands the suite everything else in the file -- and `create_app()` reads
`FRONTDOOR_UPLOAD_KEY` at CONSTRUCTION time, building the depth-ingest config from it and raising
when the ingest URL is absent.

So a developer who follows `data/STORAGE.md` and fills in an upload key saw **38 failures and 68
collection errors**, while CI stayed green because CI has no `.env`. Removing that one variable
accounted for all 106.

This is the check CI structurally cannot make for itself, so it skips there and means something
on the machines where the bug actually appears.
"""

import os
from pathlib import Path

import pytest

from tests.conftest import SERVER_CONFIG_NOT_FROM_DOTENV

DOTENV = Path(__file__).resolve().parents[1] / ".env"


@pytest.mark.skipif(not DOTENV.exists(), reason="no .env on this machine; nothing could leak")
@pytest.mark.parametrize("name", SERVER_CONFIG_NOT_FROM_DOTENV)
def test_no_server_config_leaks_from_dotenv(name):
    """These are application configuration, not storage credentials.

    A test that needs one sets it with monkeypatch -- test_upload_endpoint and test_depth_ingest
    both do -- so nothing legitimate depends on inheriting it from the machine.
    """
    assert name not in os.environ, (
        f"{name} leaked from .env into the test session. It changes what create_app() does, so "
        "the suite would pass or fail depending on whose laptop it runs on."
    )


def test_the_dotenv_variables_actually_appear_in_the_operators_env_example():
    """Guards the list from drifting: if a new server-config variable is added to .env.example
    and not to SERVER_CONFIG_NOT_FROM_DOTENV, the next person hits the same trap."""
    example = (Path(__file__).resolve().parents[1] / ".env.example")
    if not example.exists():
        pytest.skip("no .env.example committed")
    text = example.read_text(encoding="utf-8")
    for name in SERVER_CONFIG_NOT_FROM_DOTENV:
        assert name in text, (
            f"{name} is cleared by conftest but is not in .env.example; either it is obsolete or "
            "the example is missing a variable operators are expected to set"
        )
