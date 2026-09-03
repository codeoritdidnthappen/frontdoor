"""Removing the core library must break the server at import (EPIC-06 AC4, R-11).

The epic asks that the server hold no measurement arithmetic and that "removing the core library
breaks it at import time rather than silently changing a number". The first half was true; the
second was not. `frontdoor_server` imported nothing from `frontdoor.metrology` at all, so the
four arm names were spelled out independently in THREE places -- the library's `ARM_NAMES`, the
server's `STUB_ARMS`, and the frozen response schema -- and deleting the whole metrology package
left the server serving four arms as though nothing had happened.

That is R-11 in its quietest form: the demo and the error budget stop being the same system, and
nothing anywhere says so.
"""

import ast
import importlib
import json
from pathlib import Path

import pytest

import frontdoor.metrology as metrology
import frontdoor_server.app as app_module
from frontdoor.metrology import ARM_NAMES

SERVER = Path(__file__).resolve().parents[1] / "src" / "frontdoor_server"


def test_the_server_imports_the_metrology_package():
    """The coupling has to be a real import, not a comment promising one.

    A source scan rather than a call check: the point is that the module cannot LOAD without the
    library present, which is what "breaks at import time" means.
    """
    tree = ast.parse((SERVER / "app.py").read_text(encoding="utf-8"))
    imported = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "frontdoor.metrology" in imported, (
        "app.py does not import frontdoor.metrology, so deleting the core library would leave "
        "the server serving arms it can no longer measure"
    )


def test_the_servers_arms_are_the_librarys_arms():
    assert set(app_module.STUB_ARMS) == set(ARM_NAMES)


def test_the_frozen_schema_names_the_same_arms():
    """The third copy. The schema is frozen and must not be generated, but it must not drift
    either -- a response shape describing arms the library does not have is a contract nobody can
    satisfy."""
    schema = json.loads((SERVER / "measure_response.schema.json").read_text(encoding="utf-8"))
    arms = schema["properties"]["arms"]
    assert set(arms["properties"]) == set(ARM_NAMES)
    assert set(arms["required"]) == set(ARM_NAMES)


def test_an_arm_set_that_drifts_from_the_library_fails_at_import(monkeypatch):
    """The guard itself, exercised.

    Reloading with a patched `ARM_NAMES` is what a divergence would look like in practice -- the
    library gains or loses an arm and the server is not updated. It must refuse to start, in the
    process that was about to serve the wrong shape, rather than answer with arms nobody
    characterised.
    """
    monkeypatch.setattr(metrology, "ARM_NAMES", ("A", "A_prime", "B", "C", "D"))
    with pytest.raises(RuntimeError, match="disagree"):
        importlib.reload(app_module)


def test_ac_1_ac_2_duplicate_library_arm_fails_at_import(monkeypatch):
    """Set equality must not hide an extra harness run under an existing name."""
    monkeypatch.setattr(metrology, "ARM_NAMES", (*ARM_NAMES, "C"))
    with pytest.raises(RuntimeError, match="disagree"):
        importlib.reload(app_module)


@pytest.fixture(autouse=True)
def _restore_the_module():
    """Reloading app_module in one test must not leave a patched module behind for the rest of
    the suite -- the app object other tests import would be built from a mutated library."""
    yield
    importlib.reload(app_module)
