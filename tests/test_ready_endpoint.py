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

from frontdoor.storage import StorageError
from frontdoor_server import app as app_module
from frontdoor_server.app import create_app

STORAGE_VARS = (
    "FRONTDOOR_IMAGES_BUCKET",
    "FRONTDOOR_IMAGES_ACCESS_KEY",
    "FRONTDOOR_IMAGES_SECRET_KEY",
)

SUBSYSTEMS = {"screening", "photo_storage", "map_dataset", "scan_store"}


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Strip the credentials, but only after the dotenv load has happened.

    frontdoor.storage loads .env exactly once and remembers that it did. If
    this fixture is the first thing to trigger that load, it happens inside a
    stripped environment and the once-flag then denies every later test in the
    session the values it was supposed to provide. Priming it first keeps the
    stripping local to these tests.

    It also points the scan store at an empty directory that exists. The
    scan_store subsystem is about the store, and inheriting the repo's data/
    directory would make these tests assert about whatever is on the laptop.
    """
    from frontdoor import storage

    storage._load_dotenv_once()
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", *STORAGE_VARS):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FRONTDOOR_SCANS", str(tmp_path / "scans.jsonl"))
    return monkeypatch


@pytest.fixture
def storage_reachable(monkeypatch):
    """Say what the network would have said.

    /ready now asks object storage whether the configured credentials actually
    reach the bucket, because a revoked key or a deleted bucket is otherwise
    indistinguishable from working storage -- symptomatically identical to the
    MISSING credential this endpoint was written for. That is a real request,
    so the tests below stub it and the tests about it drive it directly.
    """
    def _probe():
        from frontdoor.storage import load_image_creds

        load_image_creds()      # still raises StorageError when unconfigured
        return True

    monkeypatch.setattr(app_module, "probe_image_storage", _probe)
    return monkeypatch


def ready(app=None):
    return (app or create_app()).test_client().get("/ready")


def configure_storage(env):
    env.setenv("FRONTDOOR_IMAGES_BUCKET", "images")
    env.setenv("FRONTDOOR_IMAGES_ACCESS_KEY", "key")
    env.setenv("FRONTDOOR_IMAGES_SECRET_KEY", "secret")


def test_it_reports_every_subsystem_and_answers_200_even_when_degraded(
        clean_env, storage_reachable):
    """A degraded deployment must still answer, or the check cannot be read.

    Returning 503 here would make the endpoint useless behind a load balancer
    that hides the body, which is exactly when someone needs the body.
    """
    response = ready()
    assert response.status_code == 200
    body = response.get_json()
    assert set(body["subsystems"]) == SUBSYSTEMS
    assert body["ready"] is False
    assert "screening" in body["degraded"]
    assert "photo_storage" in body["degraded"]


def test_photo_storage_is_false_when_a_credential_is_missing(
        clean_env, storage_reachable):
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
    assert ready().get_json()["subsystems"]["photo_storage"] is True


def test_screening_tracks_the_model_key(clean_env, storage_reachable):
    assert ready().get_json()["subsystems"]["screening"] is False
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert ready().get_json()["subsystems"]["screening"] is True


def test_it_never_reveals_a_value_or_names_a_variable(
        clean_env, storage_reachable):
    """The report is a status, not a map of the deployment.

    Naming the specific missing variable tells an anonymous caller how this
    deployment is wired. Booleans per subsystem are enough for the operator
    and useless to everyone else.
    """
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-secret-value")
    clean_env.setenv("FRONTDOOR_IMAGES_BUCKET", "private-bucket-name")
    clean_env.setenv("FRONTDOOR_IMAGES_ACCESS_KEY", "AKIAEXAMPLE")
    clean_env.setenv("FRONTDOOR_IMAGES_SECRET_KEY", "shhh")
    text = ready().get_data(as_text=True)
    for leaked in ("sk-secret-value", "private-bucket-name", "AKIAEXAMPLE", "shhh"):
        assert leaked not in text
    for variable in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", *STORAGE_VARS):
        assert variable not in text


def test_ready_is_true_only_when_everything_is_configured(
        clean_env, storage_reachable):
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-test")
    configure_storage(clean_env)
    body = ready().get_json()
    if body["subsystems"]["map_dataset"]:
        assert body["ready"] is True
        assert body["degraded"] == []


# --- verified, not assumed (#353) --------------------------------------------
#
# The first cut of this endpoint checked the presence of exactly what had
# failed before. Every one-notch variant walked straight through it, and each
# test below fails against that code because each one goes green there.


def test_a_dataset_that_is_present_but_unparseable_is_not_ready(
        clean_env, storage_reachable, tmp_path):
    """The incident was "the file was not there". A file that IS there and
    does not parse serves zero pins from /map/data and reported ready, because
    the check was is_file()."""
    dataset = tmp_path / "precatalogue.json"
    dataset.write_text("{ this is not json", encoding="utf-8")
    clean_env.setenv("FRONTDOOR_MAP_DATASET", str(dataset))
    body = ready().get_json()
    assert body["subsystems"]["map_dataset"] is False
    assert "map_dataset" in body["degraded"]


def test_a_dataset_that_parses_to_no_rows_is_not_ready(
        clean_env, storage_reachable, tmp_path):
    """/map/data serves an empty pin list from this, which is the outcome the
    endpoint exists to warn about."""
    dataset = tmp_path / "precatalogue.json"
    dataset.write_text("{}", encoding="utf-8")
    clean_env.setenv("FRONTDOOR_MAP_DATASET", str(dataset))
    assert ready().get_json()["subsystems"]["map_dataset"] is False

    dataset.write_text(json.dumps({"ChIJexample": {"name": "Cafe"}}), encoding="utf-8")
    assert ready().get_json()["subsystems"]["map_dataset"] is True


def test_the_scan_store_is_a_subsystem(clean_env, storage_reachable, tmp_path):
    """There was an incident about this store and no check for it at all."""
    # Nobody has published yet, under a directory that exists: ready.
    assert ready().get_json()["subsystems"]["scan_store"] is True

    # The unmounted volume: the directory itself is not there.
    clean_env.setenv("FRONTDOOR_SCANS", str(tmp_path / "not-mounted" / "scans.jsonl"))
    body = ready().get_json()
    assert body["subsystems"]["scan_store"] is False
    assert "scan_store" in body["degraded"]


def test_a_corrupt_scan_line_makes_the_scan_store_not_ready(
        clean_env, storage_reachable, tmp_path):
    """A line that will not parse is a contributor's scan that is off the map
    for good, and reads still succeed, so nothing else notices."""
    store = tmp_path / "scans.jsonl"
    store.write_text('{"scan_id": "torn"\n', encoding="utf-8")
    clean_env.setenv("FRONTDOOR_SCANS", str(store))
    assert ready().get_json()["subsystems"]["scan_store"] is False


def test_storage_that_is_configured_but_unreachable_is_not_ready(
        clean_env, monkeypatch):
    """A revoked key and a deleted bucket are symptomatically identical to the
    missing credential this endpoint was written for. Reading the variables
    cannot tell them apart; only asking the bucket can."""
    configure_storage(clean_env)

    def _refused():
        raise StorageError("object storage did not answer: ClientError")

    monkeypatch.setattr(app_module, "probe_image_storage", _refused)
    body = ready().get_json()
    assert body["subsystems"]["photo_storage"] is False
    assert body["ready"] is False
    assert "photo_storage" in body["degraded"]


def test_a_revoked_credential_does_not_leak_through_the_probe(
        clean_env, monkeypatch):
    """The probe's failure message must not reach the body either: it is the
    one place a provider's error text could carry a bucket name."""
    configure_storage(clean_env)

    def _refused():
        raise StorageError(
            "AccessDenied for bucket private-bucket-name with key AKIAEXAMPLE"
        )

    monkeypatch.setattr(app_module, "probe_image_storage", _refused)
    text = ready().get_data(as_text=True)
    assert "private-bucket-name" not in text
    assert "AKIAEXAMPLE" not in text


def test_an_auth_token_deployment_does_not_report_itself_broken(
        clean_env, storage_reachable):
    """screen_view._get_engine accepts either variable, so a deployment
    authenticated by ANTHROPIC_AUTH_TOKEN works while /ready called it
    degraded -- a false alarm on the one endpoint whose job is alarms."""
    clean_env.setenv("ANTHROPIC_AUTH_TOKEN", "sk-ant-oat-example")
    assert ready().get_json()["subsystems"]["screening"] is True
