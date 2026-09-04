"""Tests for POST /upload -- capture ingest from the phone (TICK-029, #33).

The threat model here is not a crash. It is a capture the app believes is safe and deletes,
which never reached the bucket; a depth map written into the image bucket, which is the D-020
quarantine failing silently; and an ingest path a stranger can write into.
"""

import hashlib
import io
import logging

import boto3
import pytest
from botocore.exceptions import EndpointConnectionError
from flask.testing import FlaskClient
from moto import mock_aws

from frontdoor_server.app import create_app
from frontdoor_server.depth_ingest import (
    DepthIngestConflict,
    DepthIngestError,
    DepthIngestRejected,
)

IMAGES = "frontdoor-image"
DEPTH = "frontdoor-depth"
KEY = "s3cret-upload-key"


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("FRONTDOOR_S3_REGION", "us-east-1")
    monkeypatch.delenv("FRONTDOOR_S3_ENDPOINT", raising=False)
    monkeypatch.setenv("FRONTDOOR_IMAGES_BUCKET", IMAGES)
    monkeypatch.setenv("FRONTDOOR_IMAGES_ACCESS_KEY", "img-key")
    monkeypatch.setenv("FRONTDOOR_IMAGES_SECRET_KEY", "img-secret")
    monkeypatch.setenv("FRONTDOOR_DEPTH_BUCKET", DEPTH)
    monkeypatch.setenv("FRONTDOOR_DEPTH_INGEST_URL", "https://depth.example")
    monkeypatch.setenv("FRONTDOOR_DEPTH_INGEST_KEY", "depth-service-key")
    monkeypatch.setenv("FRONTDOOR_UPLOAD_KEY", KEY)
    calls = []

    def put(stream, *, key, sha256, size, config):
        if any(call["key"] == key for call in calls):
            raise DepthIngestConflict("already exists")
        calls.append({"key": key, "sha256": sha256, "size": size, "body": stream.read()})

    monkeypatch.setattr("frontdoor_server.upload_view.put_depth", put)
    return calls


@pytest.fixture
def client(env):
    return create_app().test_client()


def _buckets():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=IMAGES)
    s3.create_bucket(Bucket=DEPTH)
    return s3


# The split is DERIVED from entrance_id server-side, never sent. These ids are what the committed
# seed assigns; if the seed changes these move, which is the point -- the server and the phone
# cannot disagree about a partition.
DEV_ENTRANCE = "E-001"
CALIB_ENTRANCE = "E-004"
SEALED_ENTRANCE = "E-002"

ENTRANCE_FOR = {"dev": DEV_ENTRANCE, "calib": CALIB_ENTRANCE, "sealed": SEALED_ENTRANCE}


def _post(client, payload=b"pretend-jpeg", *, kind="image", capture_id="cap-1",
          split="dev", entrance_id=None, sha256=None, key=KEY, omit_bytes=False):
    digest = sha256 if sha256 is not None else hashlib.sha256(payload).hexdigest()
    entrance = entrance_id if entrance_id is not None else ENTRANCE_FOR.get(split, split)
    data = {"kind": kind, "capture_id": capture_id, "entrance_id": entrance, "sha256": digest}
    if not omit_bytes:
        data["bytes"] = (io.BytesIO(payload), "shot.jpg")
    headers = {"X-Frontdoor-Upload-Key": key} if key is not None else {}
    return client.post("/upload", data=data, headers=headers,
                       content_type="multipart/form-data")


# --- authorisation -------------------------------------------------------------------

def test_an_upload_without_the_key_is_refused(client):
    assert _post(client, key=None).status_code == 401


def test_an_upload_with_the_wrong_key_is_refused(client):
    assert _post(client, key="not-the-key").status_code == 401


def test_the_endpoint_refuses_everything_when_no_key_is_configured(monkeypatch, env):
    """Unset must mean closed, not open.

    An ingest path that accepts anonymous writes into the dataset bucket because a deploy forgot
    an environment variable is worse than one that is switched off: nothing tells anyone.
    """
    monkeypatch.delenv("FRONTDOOR_UPLOAD_KEY", raising=False)
    client = create_app().test_client()
    assert _post(client, key="anything").status_code == 401


def test_an_empty_configured_key_does_not_authorise_an_empty_header(monkeypatch, env):
    monkeypatch.setenv("FRONTDOOR_UPLOAD_KEY", "   ")
    client = create_app().test_client()
    assert _post(client, key="").status_code == 401


# --- request validation --------------------------------------------------------------

@pytest.mark.parametrize("kind", ["", "sidecar", "IMAGE", "depth-map"])
def test_an_unknown_kind_is_refused(client, kind):
    assert _post(client, kind=kind).status_code == 400


@pytest.mark.parametrize("entrance", ["", "E-14", "e14", "E-0001", "not-an-id", "E-001 x"])
def test_a_non_canonical_entrance_id_is_refused(client, entrance):
    assert _post(client, entrance_id=entrance).status_code == 400


@mock_aws
def test_the_split_is_derived_from_the_entrance_not_taken_from_the_client(client):
    """A phone carrying a drifted seed must not be able to place a sealed entrance in open/."""
    _buckets()
    # The client sends no split at all; the server works it out.
    body = _post(client, entrance_id=SEALED_ENTRANCE).get_json()
    assert body["split"] == "sealed"
    assert body["key"] == "sealed/cap-1"


@mock_aws
def test_a_client_supplied_split_is_ignored(client):
    """Even if a future client sends one, it cannot override the derived value."""
    _buckets()
    resp = client.post(
        "/upload",
        data={"kind": "image", "capture_id": "cap-1", "entrance_id": SEALED_ENTRANCE,
              "split": "dev", "sha256": hashlib.sha256(b"x").hexdigest(),
              "bytes": (io.BytesIO(b"x"), "shot.jpg")},
        headers={"X-Frontdoor-Upload-Key": KEY},
        content_type="multipart/form-data")
    assert resp.get_json()["split"] == "sealed"


@pytest.mark.parametrize("bad", ["", "   ", "a/b", "../etc/passwd", "cap\u0000", "cap 1",
                                 "a" * 129, "..", "x/../y"])
def test_a_capture_id_that_could_confuse_a_key_is_refused(client, bad):
    """capture_id is interpolated into the object key, so it cannot contain a path."""
    assert _post(client, capture_id=bad).status_code == 400


@pytest.mark.parametrize("bad", ["", "abc", "g" * 64, "A" * 64, "0" * 63, "0" * 65])
def test_a_malformed_sha256_is_refused(client, bad):
    assert _post(client, sha256=bad).status_code == 400


def test_a_missing_bytes_part_is_refused(client):
    assert _post(client, omit_bytes=True).status_code == 400


def test_an_empty_body_is_refused(client):
    assert _post(client, payload=b"").status_code == 400


# --- the hash contract (AC4) ---------------------------------------------------------

@mock_aws
def test_a_hash_mismatch_is_refused_and_stores_nothing(client):
    s3 = _buckets()
    resp = _post(client, b"real-bytes", sha256=hashlib.sha256(b"other").hexdigest())
    assert resp.status_code == 422
    listed = s3.list_objects_v2(Bucket=IMAGES)
    assert listed.get("KeyCount", 0) == 0, "a mismatched upload must leave the bucket untouched"


@mock_aws
def test_a_truncated_body_is_caught(client):
    """The realistic field failure: the connection drops mid-upload."""
    s3 = _buckets()
    whole = b"x" * 4096
    resp = _post(client, whole[:2048], sha256=hashlib.sha256(whole).hexdigest())
    assert resp.status_code == 422
    assert s3.list_objects_v2(Bucket=IMAGES).get("KeyCount", 0) == 0


# --- happy paths and the quarantine (AC3) --------------------------------------------

@mock_aws
def test_an_image_is_stored_and_read_back(client):
    s3 = _buckets()
    payload = b"pretend-jpeg"
    resp = _post(client, payload)
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["stored"] is True
    assert body["key"] == "open/cap-1"
    assert body["verified"] == "read-back"
    stored = s3.get_object(Bucket=IMAGES, Key="open/cap-1")["Body"].read()
    assert stored == payload


@mock_aws
def test_ac_1_depth_goes_to_the_ingest_worker_and_never_the_image_bucket(client, env):
    """AC3, and the D-020 quarantine: a depth map in the image bucket is the silent failure."""
    s3 = _buckets()
    resp = _post(client, b"pretend-depth", kind="depth")
    assert resp.status_code == 201
    assert env == [{
        "key": "open/cap-1",
        "sha256": hashlib.sha256(b"pretend-depth").hexdigest(),
        "size": len(b"pretend-depth"),
        "body": b"pretend-depth",
    }]
    assert s3.list_objects_v2(Bucket=IMAGES).get("KeyCount", 0) == 0


@mock_aws
def test_ac_2_depth_is_verified_on_receipt_not_read_back(client):
    """D-039 gives Fly no R2 depth credential, so read-back is impossible by design.

    The response has to say so rather than claim a check it did not run.
    """
    _buckets()
    assert _post(client, b"d", kind="depth").get_json()["verified"] == "received"


@mock_aws
def test_a_sealed_capture_is_stored_under_the_sealed_prefix(client):
    """Capture uploads must be able to store sealed rows -- writes are not what the seal refuses."""
    s3 = _buckets()
    resp = _post(client, split="sealed")
    assert resp.status_code == 201
    assert resp.get_json()["key"] == "sealed/cap-1"
    s3.get_object(Bucket=IMAGES, Key="sealed/cap-1")


@mock_aws
def test_a_sealed_image_is_verified_on_receipt_not_read_back(client):
    """Reading a sealed object back would write a SEAL_AUDIT line on every upload.

    ObjectStore.get refuses anything under sealed/ without allow_sealed, and routinely passing
    that flag would make unsealing an ordinary event -- exactly what D-007 and D-017 prevent. So
    a sealed image gets the same verify-on-receipt guarantee as depth, and says so.
    """
    _buckets()
    assert _post(client, split="sealed").get_json()["verified"] == "received"


@mock_aws
def test_an_open_image_really_is_read_back(client):
    """The control for the test above: the stronger check does run where it is available."""
    _buckets()
    assert _post(client, split="dev").get_json()["verified"] == "read-back"


@mock_aws
@pytest.mark.parametrize("split", ["dev", "calib"])
def test_unsealed_splits_share_the_open_partition(client, split):
    _buckets()
    assert _post(client, split=split).get_json()["key"] == "open/cap-1"


# --- storage failures ----------------------------------------------------------------

@mock_aws
def test_a_storage_failure_is_a_503_so_the_app_retries(client):
    """The app holds the only copy. A 4xx here would tell it to give up on real data."""
    _buckets()
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.delete_bucket(Bucket=IMAGES)
    assert _post(client).status_code == 503


# --- conditional writes: no silent replacement ---------------------------------------

@mock_aws
def test_re_uploading_identical_bytes_succeeds_so_a_lost_ack_is_not_fatal(client):
    """The common field case: the upload landed, the reply did not, the phone retries."""
    _buckets()
    assert _post(client, b"same").status_code == 201
    again = _post(client, b"same")
    assert again.status_code == 200
    assert again.get_json()["stored"] is True


@mock_aws
def test_different_bytes_under_the_same_capture_id_are_refused_not_overwritten(client):
    """The dangerous case. Anyone holding the ingest key must not be able to replace a capture."""
    s3 = _buckets()
    assert _post(client, b"original").status_code == 201
    resp = _post(client, b"substitute")
    assert resp.status_code == 409
    assert s3.get_object(Bucket=IMAGES, Key="open/cap-1")["Body"].read() == b"original"


@mock_aws
def test_a_sealed_capture_is_never_overwritten_even_by_identical_bytes(client):
    """Sealed objects cannot be read to compare, so the answer is a 409 a person looks at.

    The bytes stay on the phone, so refusing costs nothing and a substitution under the seal is
    exactly the event that must not pass quietly.
    """
    s3 = _buckets()
    assert _post(client, b"sealed-bytes", split="sealed").status_code == 201
    assert _post(client, b"sealed-bytes", split="sealed").status_code == 409
    assert s3.get_object(Bucket=IMAGES, Key="sealed/cap-1")["Body"].read() == b"sealed-bytes"


@mock_aws
def test_depth_is_never_overwritten_because_it_cannot_be_compared(client):
    _buckets()
    assert _post(client, b"d", kind="depth").status_code == 201
    assert _post(client, b"d", kind="depth").status_code == 409


@pytest.mark.parametrize("failure", [
    DepthIngestError("unavailable"),
    DepthIngestError("authentication refused"),
])
def test_ac_3_worker_failures_are_retryable_and_leave_the_capture_queued(
        client, monkeypatch, failure):
    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr("frontdoor_server.upload_view.put_depth", fail)
    assert _post(client, b"d", kind="depth").status_code == 503


def test_tick_254_a_worker_digest_rejection_answers_422_not_503(client, monkeypatch):
    """A permanent rejection must not be dressed as an outage, or the phone requeues forever."""
    def reject(*args, **kwargs):
        raise DepthIngestRejected("the bytes did not hash to the declared sha256")

    monkeypatch.setattr("frontdoor_server.upload_view.put_depth", reject)
    assert _post(client, b"d", kind="depth").status_code == 422


@mock_aws
def test_ac_4_image_upload_does_not_call_the_depth_worker(client, monkeypatch):
    _buckets()

    def fail(*args, **kwargs):
        raise AssertionError("image upload reached the depth Worker")

    monkeypatch.setattr("frontdoor_server.upload_view.put_depth", fail)
    assert _post(client, b"image", kind="image").status_code == 201


# --- size ceiling --------------------------------------------------------------------

@mock_aws
def test_an_upload_over_the_route_ceiling_is_refused_with_413(client, monkeypatch):
    """One 256 MB machine, one worker, two threads: the app-wide 64 MB cap is too generous here."""
    from frontdoor_server import upload_view

    monkeypatch.setattr(upload_view, "UPLOAD_MAX_BYTES", 1024)
    s3 = _buckets()
    resp = _post(client, b"x" * 4096)
    assert resp.status_code == 413
    assert s3.list_objects_v2(Bucket=IMAGES).get("KeyCount", 0) == 0


# --- the auth comparison -------------------------------------------------------------

def test_a_non_ascii_key_header_is_a_401_not_a_500(client):
    """Werkzeug decodes headers as latin-1, and compare_digest raises TypeError on non-ASCII str.

    Left unhandled this is a 500, which the app classifies as retryable and repeats forever.
    """
    resp = client.post(
        "/upload",
        data={"kind": "image", "capture_id": "cap-1", "entrance_id": DEV_ENTRANCE,
              "sha256": hashlib.sha256(b"x").hexdigest(),
              "bytes": (io.BytesIO(b"x"), "shot.jpg")},
        headers={"X-Frontdoor-Upload-Key": "kéy"},
        content_type="multipart/form-data")
    assert resp.status_code == 401


def test_a_non_ascii_configured_key_still_authorises_its_own_value(monkeypatch, env):
    monkeypatch.setenv("FRONTDOOR_UPLOAD_KEY", "kéy")
    c = create_app().test_client()
    with mock_aws():
        _buckets()
        assert _post(c, key="kéy").status_code == 201


# --- a misconfigured deploy answers with the contract, not a traceback (TICK-225) ---------------
#
# Seen for real on 2026-09-04. A stale release asked for FRONTDOOR_DEPTH_BUCKET -- obsolete since
# depth moved to the Worker, and deliberately unset -- and the store was CONSTRUCTED outside the
# try that handles StorageError.
#
# The JSON shape held: app.py's catch-all still answered valid JSON, so TICK-225's guarantee was
# not broken. What the phone actually got was
#
#     500 {"error": "internal error",
#          "detail": "The server failed to handle the request. Nothing was measured."}
#
# which is wrong three ways. 500 rather than 503, so the client cannot tell a retryable outage
# from a bug. "internal error" names nothing, so the real cause -- a stale release, not a bad key
# -- was findable only in fly logs. And "Nothing was measured" is the /measure wording arriving on
# /upload, where nothing was being measured at all.


@mock_aws
def test_a_missing_image_credential_is_a_named_503_not_a_500(monkeypatch, env):
    """503, like a failed put: the bytes are good and the capture is the only copy.

    A 4xx would tell the app the capture is rejected and stop it retrying something that is
    perfectly fine; a 500 tells it nothing at all.
    """
    _buckets()
    monkeypatch.delenv("FRONTDOOR_IMAGES_BUCKET", raising=False)
    client = create_app().test_client()

    response = _post(client, kind="image")

    assert response.status_code == 503, response.get_data(as_text=True)[:200]
    body = response.get_json()
    assert body["error"] == "could not store the object"
    assert "FRONTDOOR_IMAGES_BUCKET" in body["detail"], body["detail"]


@pytest.mark.parametrize(("name", "value"), [
    ("FRONTDOOR_S3_ENDPOINT", "not a url"),
    ("FRONTDOOR_S3_ENDPOINT", "https://exa mple.com"),
    ("FRONTDOOR_S3_ENDPOINT", "https://_bad.example"),
    ("FRONTDOOR_S3_ENDPOINT", "https://-bad.example"),
    ("FRONTDOOR_S3_ENDPOINT", "https://bad-.example"),
    ("FRONTDOOR_S3_ENDPOINT", "https://example..com"),
    ("FRONTDOOR_S3_REGION", "bad region"),
])
def test_tick_b01_malformed_image_config_is_a_named_503(
        monkeypatch, env, name, value):
    monkeypatch.setenv(name, value)
    client = create_app().test_client()

    response = _post(client, kind="image")

    assert response.status_code == 503, response.get_data(as_text=True)[:200]
    body = response.get_json()
    assert body["error"] == "could not store the object"
    assert "could not configure object storage" in body["detail"]


def test_tick_b01_programmer_error_inside_boto_client_remains_a_500(
        monkeypatch, env):
    def fail(*args, **kwargs):
        raise ValueError("internal invariant failed")

    monkeypatch.setattr("boto3.client", fail)
    response = _post(create_app().test_client(), kind="image")

    assert response.status_code == 500
    assert response.get_json()["error"] == "internal error"


@pytest.mark.parametrize(
    "depth_url",
    [None, "", "not a url"],
    ids=["absent", "empty", "malformed"],
)
def test_tick_262_ac_3_bad_depth_config_is_a_named_503(
        monkeypatch: pytest.MonkeyPatch,
        env: list[dict[str, object]],
        depth_url: str | None) -> None:
    if depth_url is None:
        monkeypatch.delenv("FRONTDOOR_DEPTH_INGEST_URL", raising=False)
    else:
        monkeypatch.setenv("FRONTDOOR_DEPTH_INGEST_URL", depth_url)
    client = create_app().test_client()

    response = _post(client, b"depth", kind="depth")

    assert response.status_code == 503
    body = response.get_json()
    assert body["error"] == "could not store the object"
    assert "FRONTDOOR_DEPTH_INGEST_URL" in body["detail"]


@mock_aws
def test_tick_262_ac_4_image_upload_is_unaffected_by_bad_depth_config(
        monkeypatch: pytest.MonkeyPatch, env: list[dict[str, object]]) -> None:
    monkeypatch.delenv("FRONTDOOR_DEPTH_INGEST_URL", raising=False)
    client = create_app().test_client()
    _buckets()

    response = _post(client, b"image", kind="image")

    assert response.status_code == 201
    assert response.get_json()["verified"] == "read-back"


def test_tick_262_ac_5_valid_depth_config_behaves_unchanged(
        client: FlaskClient, env: list[dict[str, object]]) -> None:
    response = _post(client, b"depth", kind="depth")

    assert response.status_code == 201
    assert response.get_json()["verified"] == "received"
    assert env[0]["body"] == b"depth"


class _EndpointFailingS3:
    def put_object(self, **kwargs: object) -> None:
        # Fixture shape follows botocore's transport boundary, which raises
        # EndpointConnectionError(endpoint_url=request.url, error=exc).
        # https://github.com/boto/botocore/blob/develop/botocore/httpsession.py
        raise EndpointConnectionError(
            endpoint_url="https://private-storage.example.test")


def test_tick_263_ac_1_ac_2_ac_3_ac_4_redacted_503_keeps_server_diagnosis(
        monkeypatch: pytest.MonkeyPatch,
        env: list[dict[str, object]],
        caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv(
        "FRONTDOOR_S3_ENDPOINT", "https://private-storage.example.test")

    def failing_client(*args: object, **kwargs: object) -> _EndpointFailingS3:
        return _EndpointFailingS3()

    monkeypatch.setattr("boto3.client", failing_client)
    with caplog.at_level(logging.ERROR):
        response = _post(create_app().test_client(), kind="image")

    assert response.status_code == 503
    body = response.get_json()
    assert body["error"] == "could not store the object"
    assert body["detail"] == (
        "put s3://frontdoor-image/open/cap-1 failed (EndpointConnectionError)")
    assert "private-storage.example.test" not in response.get_data(as_text=True)
    assert "private-storage.example.test" in caplog.text
