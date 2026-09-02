"""Tests for POST /upload -- capture ingest from the phone (TICK-029, #33).

The threat model here is not a crash. It is a capture the app believes is safe and deletes,
which never reached the bucket; a depth map written into the image bucket, which is the D-020
quarantine failing silently; and an ingest path a stranger can write into.
"""

import hashlib
import io

import boto3
import pytest
from moto import mock_aws

from frontdoor_server.app import create_app

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
    monkeypatch.setenv("FRONTDOOR_DEPTH_WRITE_ACCESS_KEY", "dep-write-key")
    monkeypatch.setenv("FRONTDOOR_DEPTH_WRITE_SECRET_KEY", "dep-write-secret")
    monkeypatch.setenv("FRONTDOOR_UPLOAD_KEY", KEY)


@pytest.fixture
def client(env):
    return create_app().test_client()


def _buckets():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=IMAGES)
    s3.create_bucket(Bucket=DEPTH)
    return s3


def _post(client, payload=b"pretend-jpeg", *, kind="image", capture_id="cap-1",
          split="dev", sha256=None, key=KEY, omit_bytes=False):
    digest = sha256 if sha256 is not None else hashlib.sha256(payload).hexdigest()
    data = {"kind": kind, "capture_id": capture_id, "split": split, "sha256": digest}
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


@pytest.mark.parametrize("split", ["", "prod", "Dev", "sealed "])
def test_an_unknown_split_is_refused(client, split):
    assert _post(client, split=split).status_code == 400


def test_a_missing_capture_id_is_refused(client):
    assert _post(client, capture_id="   ").status_code == 400


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
def test_depth_goes_to_the_depth_bucket_and_never_the_image_bucket(client):
    """AC3, and the D-020 quarantine: a depth map in the image bucket is the silent failure."""
    s3 = _buckets()
    resp = _post(client, b"pretend-depth", kind="depth")
    assert resp.status_code == 201
    assert s3.get_object(Bucket=DEPTH, Key="open/cap-1")["Body"].read() == b"pretend-depth"
    assert s3.list_objects_v2(Bucket=IMAGES).get("KeyCount", 0) == 0


@mock_aws
def test_depth_is_verified_on_receipt_not_read_back(client):
    """D-033 gives the server a write-only depth token, so read-back is impossible by design.

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
