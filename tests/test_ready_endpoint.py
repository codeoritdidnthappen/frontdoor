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
import os

import pytest

from frontdoor_server import app as app_module
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


@pytest.fixture(autouse=True)
def _forget_disk_answers():
    """/ready remembers its last read per path, and the cache outlives a test.

    Every test here uses tmp_path, so nothing collides today; a later test that
    touches the DEFAULT dataset or scan path would inherit whatever an earlier
    one left, and inherit it silently.
    """
    app_module._READY_CACHE.clear()
    yield
    app_module._READY_CACHE.clear()


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
        "screening", "photo_storage", "map_dataset", "scan_store", "claims_store",
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
    if body["subsystems"]["map_dataset"] and body["subsystems"]["scan_store"] and body["subsystems"]["claims_store"]:
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


def test_claims_store_tracks_whether_the_volume_is_mounted(clean_env, tmp_path):
    """Claims are the second thing on the volume; losing them is a credential (#369)."""
    clean_env.setenv(
        "FRONTDOOR_CLAIMS", str(tmp_path / "not-mounted" / "claims.jsonl")
    )
    assert ready().get_json()["subsystems"]["claims_store"] is False

    mounted = tmp_path / "data"
    mounted.mkdir()
    clean_env.setenv("FRONTDOOR_CLAIMS", str(mounted / "claims.jsonl"))
    assert ready().get_json()["subsystems"]["claims_store"] is True


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


def test_a_corrupt_claim_line_makes_the_claims_store_not_ready(
        clean_env, reachable, tmp_path):
    store = tmp_path / "claims.jsonl"
    clean_env.setenv("FRONTDOOR_CLAIMS", str(store))
    assert ready().get_json()["subsystems"]["claims_store"] is True
    store.write_text('{"claim_id": "torn"\n', encoding="utf-8")
    body = ready().get_json()
    assert body["subsystems"]["claims_store"] is False
    assert "claims_store" in body["degraded"]


def test_an_unmounted_volume_still_makes_the_scan_store_not_ready(
        clean_env, reachable, tmp_path):
    """The case #353 did catch, kept pinned."""
    clean_env.setenv("FRONTDOOR_SCANS",
                     str(tmp_path / "not-mounted" / "scans.jsonl"))
    assert ready().get_json()["subsystems"]["scan_store"] is False


# --- /ready is a probe, not a parser anyone can call (#370) ------------------


def test_it_does_not_re_read_an_unchanged_dataset_on_every_request(
        clean_env, reachable, tmp_path, monkeypatch):
    """/ready is unauthenticated and both disk checks parse a whole file.

    The shipped pre-catalogue is 200 KB and the scan store grows with every
    publish, so re-reading both per request turns a health probe into a lever.
    The answer cannot change while the bytes do not.
    """
    dataset = tmp_path / "precatalogue.json"
    dataset.write_text(json.dumps(usable_dataset()), encoding="utf-8")
    clean_env.setenv("FRONTDOOR_MAP_DATASET", str(dataset))
    clean_env.setenv("FRONTDOOR_SCANS", str(tmp_path / "scans.jsonl"))

    reads = []
    real = app_module._map_dataset_ready
    monkeypatch.setattr(app_module, "_map_dataset_ready",
                        lambda path: (reads.append(path), real(path))[1])

    assert ready().get_json()["subsystems"]["map_dataset"] is True
    assert ready().get_json()["subsystems"]["map_dataset"] is True
    assert ready().get_json()["subsystems"]["map_dataset"] is True
    assert len(reads) == 1, "the dataset was parsed again for an unchanged file"


def test_a_changed_dataset_is_read_again(clean_env, reachable, tmp_path):
    """A cache that cannot go green again would be worse than the parse.

    The whole point of the endpoint is that an operator fixes the deployment
    and asks it whether the fix took.
    """
    dataset = tmp_path / "precatalogue.json"
    dataset.write_text("{ not json", encoding="utf-8")
    clean_env.setenv("FRONTDOOR_MAP_DATASET", str(dataset))
    clean_env.setenv("FRONTDOOR_SCANS", str(tmp_path / "scans.jsonl"))
    assert ready().get_json()["subsystems"]["map_dataset"] is False

    dataset.write_text(json.dumps(usable_dataset()), encoding="utf-8")
    assert ready().get_json()["subsystems"]["map_dataset"] is True

    dataset.unlink()
    assert ready().get_json()["subsystems"]["map_dataset"] is False


def test_a_volume_that_goes_away_under_an_absent_store_is_noticed(
        clean_env, reachable, tmp_path):
    """The case a cache keyed on the FILE alone would get wrong.

    An empty scan store is a file that legitimately does not exist, so "absent"
    is the same stat before and after the volume disappears -- and the answer
    is not the same. The parent is stamped for exactly this.
    """
    volume = tmp_path / "data"
    volume.mkdir()
    clean_env.setenv("FRONTDOOR_SCANS", str(volume / "scans.jsonl"))
    assert ready().get_json()["subsystems"]["scan_store"] is True

    volume.rmdir()
    assert ready().get_json()["subsystems"]["scan_store"] is False


def test_a_dataset_swapped_in_under_the_same_mtime_and_size_is_read_again(
        clean_env, reachable, tmp_path):
    """An atomic replace is how a dataset is deployed, and it can preserve both.

    os.replace onto the same name keeps whatever mtime and length the incoming
    file has, so the two obvious fields do not move. Two things in the stamp
    catch it -- the new inode, and the parent directory, whose own mtime a
    rename bumps -- and only the pair makes this deterministic across
    filesystems, which is why the parent is stamped for more than the
    unmounted-volume case above.
    """
    good = json.dumps(usable_dataset())
    broken = json.dumps({"ChIJexample": {"name": "Cafe"}})
    broken += " " * (len(good) - len(broken))  # trailing space: still valid JSON
    assert len(good) == len(broken)

    dataset = tmp_path / "precatalogue.json"
    dataset.write_text(good, encoding="utf-8")
    clean_env.setenv("FRONTDOOR_MAP_DATASET", str(dataset))
    clean_env.setenv("FRONTDOOR_SCANS", str(tmp_path / "scans.jsonl"))
    assert ready().get_json()["subsystems"]["map_dataset"] is True

    incoming = tmp_path / "incoming.json"
    incoming.write_text(broken, encoding="utf-8")
    stat = dataset.stat()
    os.utime(incoming, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    os.replace(incoming, dataset)
    assert dataset.stat().st_mtime_ns == stat.st_mtime_ns
    assert dataset.stat().st_size == stat.st_size

    assert ready().get_json()["subsystems"]["map_dataset"] is False


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows spells st_ctime as the creation time, so a chmod moves "
           "nothing in the stamp; the deploy target is Linux and CI runs it",
)
def test_a_dataset_that_loses_read_permission_is_noticed(
        clean_env, reachable, tmp_path):
    """Permission-denied is one of the five states these checks separate, and
    a chmod moves neither mtime nor size nor the parent directory. Without the
    inode-change time in the stamp, a dataset whose read access was just
    revoked goes on reporting healthy for the life of the process -- and the
    operator who fixes it is told it is still broken."""
    dataset = tmp_path / "precatalogue.json"
    dataset.write_text(json.dumps(usable_dataset()), encoding="utf-8")
    clean_env.setenv("FRONTDOOR_MAP_DATASET", str(dataset))
    clean_env.setenv("FRONTDOOR_SCANS", str(tmp_path / "scans.jsonl"))
    assert ready().get_json()["subsystems"]["map_dataset"] is True

    os.chmod(dataset, 0o000)
    try:
        dataset.read_text(encoding="utf-8")
    except PermissionError:
        pass
    else:
        pytest.skip("this user can read a 0o000 file; nothing to observe")

    assert ready().get_json()["subsystems"]["map_dataset"] is False
