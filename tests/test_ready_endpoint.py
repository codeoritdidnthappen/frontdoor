"""GET /ready: what this deployment can actually do (TICK-335).

/health answers "is the process alive", which is not the question anyone has.
The question is whether a scan will be assessed and whether its photograph
will be stored. A missing storage credential is invisible from outside -- the
endpoint answers, the assessment succeeds, and the image quietly does not
persist. That has already happened once on this project, which is why this
endpoint exists and why these tests are about what it refuses to reveal as
much as what it reports.
"""

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
    for name in ("ANTHROPIC_API_KEY", *STORAGE_VARS):
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
    assert set(body["subsystems"]) == {"screening", "photo_storage", "map_dataset"}
    assert body["ready"] is False
    assert "screening" in body["degraded"]
    assert "photo_storage" in body["degraded"]


def test_photo_storage_is_false_when_a_credential_is_missing(clean_env):
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


def test_screening_tracks_the_model_key(clean_env):
    assert ready().get_json()["subsystems"]["screening"] is False
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert ready().get_json()["subsystems"]["screening"] is True


def test_it_never_reveals_a_value_or_names_a_variable(clean_env):
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
    for variable in ("ANTHROPIC_API_KEY", *STORAGE_VARS):
        assert variable not in text


def test_ready_is_true_only_when_everything_is_configured(clean_env):
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-test")
    clean_env.setenv("FRONTDOOR_IMAGES_BUCKET", "images")
    clean_env.setenv("FRONTDOOR_IMAGES_ACCESS_KEY", "key")
    clean_env.setenv("FRONTDOOR_IMAGES_SECRET_KEY", "secret")
    body = ready().get_json()
    if body["subsystems"]["map_dataset"]:
        assert body["ready"] is True
        assert body["degraded"] == []
