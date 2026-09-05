"""GET /ready: what this deployment can actually do (TICK-335).

/health answers "is the process alive", which is not the question anyone has.
The question is whether a scan will be assessed and whether its photograph
will be stored. A missing storage credential is invisible from outside -- the
endpoint answers, the assessment succeeds, and the image quietly does not
persist. That has already happened once on this project, which is why this
endpoint exists and why these tests are about what it refuses to reveal as
much as what it reports.
"""

import json

import pytest

from frontdoor_server.app import create_app

STORAGE_VARS = (
    "FRONTDOOR_IMAGES_BUCKET",
    "FRONTDOOR_IMAGES_ACCESS_KEY",
    "FRONTDOOR_IMAGES_SECRET_KEY",
)


@pytest.fixture
def clean_env(monkeypatch):
    """Strip the credentials, but only after the dotenv load has happened.

    frontdoor.storage loads .env exactly once and remembers that it did. If
    this fixture is the first thing to trigger that load, it happens inside a
    stripped environment and the once-flag then denies every later test in the
    session the values it was supposed to provide. Priming it first keeps the
    stripping local to these tests.
    """
    from frontdoor import storage

    storage._load_dotenv_once()
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", *STORAGE_VARS):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def ready(app=None):
    return (app or create_app()).test_client().get("/ready")


def test_it_reports_every_subsystem_and_answers_200_even_when_degraded(clean_env):
    """A degraded deployment must still answer, or the check cannot be read.

    Returning 503 here would make the endpoint useless behind a load balancer
    that hides the body, which is exactly when someone needs the body.
    """
    response = ready()
    assert response.status_code == 200
    body = response.get_json()
    assert set(body["subsystems"]) == {
        "screening", "photo_storage", "map_dataset", "scan_store",
    }
    assert body["ready"] is False
    assert "screening" in body["degraded"]
    assert "photo_storage" in body["degraded"]


def test_photo_storage_is_false_when_a_credential_is_missing(clean_env, monkeypatch):
    """The silent failure this endpoint exists to make loud.

    Storage that is configured except for one variable behaves, from outside,
    exactly like storage that works, right up until a published scan loses its
    photograph.
    """
    clean_env.setenv("FRONTDOOR_IMAGES_BUCKET", "images")
    clean_env.setenv("FRONTDOOR_IMAGES_ACCESS_KEY", "key")
    # secret deliberately absent
    assert ready().get_json()["subsystems"]["photo_storage"] is False

    clean_env.setenv("FRONTDOOR_IMAGES_SECRET_KEY", "secret")
    monkeypatch.setattr(
        "frontdoor_server.app.image_bucket_is_reachable", lambda: True
    )
    assert ready().get_json()["subsystems"]["photo_storage"] is True


def test_photo_storage_is_false_when_the_bucket_cannot_be_reached(
        clean_env, monkeypatch
):
    clean_env.setenv("FRONTDOOR_IMAGES_BUCKET", "images")
    clean_env.setenv("FRONTDOOR_IMAGES_ACCESS_KEY", "key")
    clean_env.setenv("FRONTDOOR_IMAGES_SECRET_KEY", "secret")
    monkeypatch.setattr(
        "frontdoor_server.app.image_bucket_is_reachable", lambda: False
    )
    assert ready().get_json()["subsystems"]["photo_storage"] is False


def test_screening_tracks_the_model_key(clean_env):
    assert ready().get_json()["subsystems"]["screening"] is False
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert ready().get_json()["subsystems"]["screening"] is True


def test_screening_accepts_the_auth_token(clean_env):
    clean_env.setenv("ANTHROPIC_AUTH_TOKEN", "tok-test")
    assert ready().get_json()["subsystems"]["screening"] is True


def test_it_never_reveals_a_value_or_names_a_variable(clean_env, monkeypatch):
    """The report is a status, not a map of the deployment.

    Naming the specific missing variable tells an anonymous caller how this
    deployment is wired. Booleans per subsystem are enough for the operator
    and useless to everyone else.
    """
    monkeypatch.setattr(
        "frontdoor_server.app.image_bucket_is_reachable", lambda: True
    )
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-secret-value")
    clean_env.setenv("FRONTDOOR_IMAGES_BUCKET", "private-bucket-name")
    clean_env.setenv("FRONTDOOR_IMAGES_ACCESS_KEY", "AKIAEXAMPLE")
    clean_env.setenv("FRONTDOOR_IMAGES_SECRET_KEY", "shhh")
    text = ready().get_data(as_text=True)
    for leaked in ("sk-secret-value", "private-bucket-name", "AKIAEXAMPLE", "shhh"):
        assert leaked not in text
    for variable in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", *STORAGE_VARS):
        assert variable not in text


def test_ready_is_true_only_when_everything_is_configured(clean_env, monkeypatch):
    monkeypatch.setattr(
        "frontdoor_server.app.image_bucket_is_reachable", lambda: True
    )
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-test")
    clean_env.setenv("FRONTDOOR_IMAGES_BUCKET", "images")
    clean_env.setenv("FRONTDOOR_IMAGES_ACCESS_KEY", "key")
    clean_env.setenv("FRONTDOOR_IMAGES_SECRET_KEY", "secret")
    body = ready().get_json()
    if body["subsystems"]["map_dataset"] and body["subsystems"]["scan_store"]:
        assert body["ready"] is True
        assert body["degraded"] == []


def test_map_dataset_is_false_when_empty_or_unparseable(clean_env, tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    clean_env.setenv("FRONTDOOR_MAP_DATASET", str(empty))
    assert ready().get_json()["subsystems"]["map_dataset"] is False

    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    clean_env.setenv("FRONTDOOR_MAP_DATASET", str(broken))
    assert ready().get_json()["subsystems"]["map_dataset"] is False


def test_scan_store_tracks_whether_the_volume_is_mounted(clean_env, tmp_path):
    clean_env.setenv(
        "FRONTDOOR_SCANS", str(tmp_path / "not-mounted" / "scans.jsonl")
    )
    assert ready().get_json()["subsystems"]["scan_store"] is False

    mounted = tmp_path / "data"
    mounted.mkdir()
    clean_env.setenv("FRONTDOOR_SCANS", str(mounted / "scans.jsonl"))
    assert ready().get_json()["subsystems"]["scan_store"] is True


# --- verified, not assumed: the notch past #353 (#370) -----------------------


@pytest.fixture
def reachable(monkeypatch):
    monkeypatch.setattr(
        "frontdoor_server.app.image_bucket_is_reachable", lambda: True)
    return monkeypatch


def usable_dataset():
    return {"ChIJexample": {"name": "Cafe",
                            "location": {"lat": 30.26, "lng": -97.74}}}


def test_a_dataset_full_of_rows_that_yield_no_pins_is_not_ready(
        clean_env, reachable, tmp_path, caplog):
    """#353 accepted any non-empty dict. prepare_map_payload drops every row
    without a numeric, in-range location, so a refresh that renames or nulls
    the coordinate keys serves an empty map while /ready says it is fine --
    which is verbatim the case the parse was added to catch."""
    dataset = tmp_path / "precatalogue.json"
    clean_env.setenv("FRONTDOOR_MAP_DATASET", str(dataset))

    dataset.write_text(json.dumps({"ChIJexample": {"name": "Cafe"}}),
                       encoding="utf-8")
    with caplog.at_level("ERROR", logger="frontdoor_server.app"):
        assert ready().get_json()["subsystems"]["map_dataset"] is False
    assert caplog.records, "a degraded subsystem reported false and logged nothing"

    dataset.write_text(json.dumps(usable_dataset()), encoding="utf-8")
    assert ready().get_json()["subsystems"]["map_dataset"] is True


def test_an_unparseable_dataset_says_why_in_the_log(
        clean_env, reachable, tmp_path, caplog):
    """The body says WHICH, the log says why. docs/server-deploy.md sends the
    operator to the log for the reason, and five causes needing five different
    fixes arrive here as one bit."""
    dataset = tmp_path / "precatalogue.json"
    dataset.write_text("{ not json", encoding="utf-8")
    clean_env.setenv("FRONTDOOR_MAP_DATASET", str(dataset))
    with caplog.at_level("ERROR", logger="frontdoor_server.app"):
        assert ready().get_json()["subsystems"]["map_dataset"] is False
    assert caplog.records


def test_a_corrupt_scan_line_makes_the_scan_store_not_ready(
        clean_env, reachable, tmp_path):
    """#353 checked the parent directory and stopped. A line that will not
    parse is a contributor's scan that is off the map for good, and reads keep
    succeeding, so nothing else notices."""
    store = tmp_path / "scans.jsonl"
    clean_env.setenv("FRONTDOOR_SCANS", str(store))

    # Nobody has published yet, under a directory that exists: ready.
    assert ready().get_json()["subsystems"]["scan_store"] is True

    store.write_text('{"scan_id": "torn"\n', encoding="utf-8")
    body = ready().get_json()
    assert body["subsystems"]["scan_store"] is False
    assert "scan_store" in body["degraded"]


def test_an_unmounted_volume_still_makes_the_scan_store_not_ready(
        clean_env, reachable, tmp_path):
    """The case #353 did catch, kept pinned."""
    clean_env.setenv("FRONTDOOR_SCANS",
                     str(tmp_path / "not-mounted" / "scans.jsonl"))
    assert ready().get_json()["subsystems"]["scan_store"] is False
