"""Tests for two-bucket object storage (TICK-012, #20)."""

import os
from io import BytesIO
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from frontdoor import storage
from frontdoor.storage import (
    PROBE_KEY,
    StorageDenied,
    StorageError,
    depth_store,
    image_store,
    load_depth_creds,
    load_image_creds,
    main,
    probe_loader_denied_depth,
    verify,
)

REPO = Path(__file__).resolve().parents[1]

IMAGES = "frontdoor-image"
DEPTH = "frontdoor-depth"


def _image_env(monkeypatch):
    monkeypatch.setenv("FRONTDOOR_S3_REGION", "us-east-1")
    monkeypatch.delenv("FRONTDOOR_S3_ENDPOINT", raising=False)
    monkeypatch.setenv("FRONTDOOR_IMAGES_BUCKET", IMAGES)
    monkeypatch.setenv("FRONTDOOR_IMAGES_ACCESS_KEY", "img-key")
    monkeypatch.setenv("FRONTDOOR_IMAGES_SECRET_KEY", "img-secret")


def _depth_env(monkeypatch):
    monkeypatch.setenv("FRONTDOOR_DEPTH_BUCKET", DEPTH)
    monkeypatch.setenv("FRONTDOOR_DEPTH_ACCESS_KEY", "dep-key")
    monkeypatch.setenv("FRONTDOOR_DEPTH_SECRET_KEY", "dep-secret")


def _both_env(monkeypatch):
    _image_env(monkeypatch)
    _depth_env(monkeypatch)


def _create_buckets():
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket=IMAGES)
    client.create_bucket(Bucket=DEPTH)
    return client


def test_env_example_lists_both_credential_sets_and_no_secrets():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    for key in (
        "FRONTDOOR_S3_ENDPOINT",
        "FRONTDOOR_IMAGES_BUCKET",
        "FRONTDOOR_IMAGES_ACCESS_KEY",
        "FRONTDOOR_IMAGES_SECRET_KEY",
        "FRONTDOOR_DEPTH_BUCKET",
        "FRONTDOOR_DEPTH_ACCESS_KEY",
        "FRONTDOOR_DEPTH_SECRET_KEY",
    ):
        assert key in text
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        if name.endswith("_KEY"):
            assert value == ""


def test_storage_layout_doc_names_two_buckets():
    text = (REPO / "data" / "STORAGE.md").read_text(encoding="utf-8")
    assert "frontdoor-image" in text
    assert "frontdoor-depth" in text
    assert "10 GB" in text
    assert "python -m frontdoor.storage verify" in text


def test_changes_log_records_the_provider():
    text = (REPO / "CHANGES.log").read_text(encoding="utf-8")
    assert "TICK-012" in text
    assert "Cloudflare R2" in text
    assert "frontdoor-image" in text
    assert "frontdoor-depth" in text


def test_loader_config_does_not_require_depth_credentials(monkeypatch):
    _image_env(monkeypatch)
    monkeypatch.delenv("FRONTDOOR_DEPTH_BUCKET", raising=False)
    monkeypatch.delenv("FRONTDOOR_DEPTH_ACCESS_KEY", raising=False)
    monkeypatch.delenv("FRONTDOOR_DEPTH_SECRET_KEY", raising=False)
    creds = load_image_creds()
    assert creds.bucket == IMAGES
    with pytest.raises(StorageError, match="FRONTDOOR_DEPTH_BUCKET"):
        load_depth_creds()


def test_missing_image_credential_is_an_error(monkeypatch):
    monkeypatch.delenv("FRONTDOOR_IMAGES_BUCKET", raising=False)
    with pytest.raises(StorageError, match="FRONTDOOR_IMAGES_BUCKET"):
        load_image_creds()


@mock_aws
def test_image_put_and_get_round_trip(monkeypatch):
    _image_env(monkeypatch)
    _create_buckets()
    store = image_store()
    store.put("cap-1", b"jpeg-bytes")
    assert store.get("cap-1") == b"jpeg-bytes"


@mock_aws
def test_harness_reads_depth_that_the_loader_wrote_to_the_depth_bucket(monkeypatch):
    _both_env(monkeypatch)
    _create_buckets()
    depth_store().put("cap-1", b"depth-bytes")
    assert depth_store().get("cap-1") == b"depth-bytes"


@mock_aws
def test_unknown_capture_is_an_error(monkeypatch):
    _image_env(monkeypatch)
    _create_buckets()
    with pytest.raises(StorageError):
        image_store().get("missing")


@mock_aws
def test_verify_fails_when_loader_can_read_depth(monkeypatch):
    """moto does not enforce per-token bucket scope, so verify must go red here.

    The live check (FRONTDOOR_STORAGE_LIVE=1) is the one that proves the
    provider denies the loader. This test proves verify does not silently
    pass when the deny is missing.
    """
    _both_env(monkeypatch)
    _create_buckets()
    with pytest.raises(StorageError, match="not denied on the depth bucket"):
        verify()


def test_cli_usage(capsys):
    assert main([]) == 2
    assert "verify" in capsys.readouterr().err


def test_cli_reports_missing_env(monkeypatch, capsys):
    for name in list(os.environ):
        if name.startswith("FRONTDOOR_"):
            monkeypatch.delenv(name, raising=False)
    assert main(["verify"]) == 1
    assert "missing" in capsys.readouterr().err


@pytest.mark.skipif(
    not os.environ.get("FRONTDOOR_STORAGE_LIVE"),
    reason="live storage not configured",
)
def test_live_loader_credential_is_denied_on_depth():
    images = image_store()
    depth = depth_store()
    depth.put(PROBE_KEY, b"secret-depth")
    try:
        with pytest.raises(StorageDenied):
            probe_loader_denied_depth(images.creds, depth.creds.bucket)
        images.put(PROBE_KEY, b"public-image")
        assert images.get(PROBE_KEY) == b"public-image"
    finally:
        try:
            images.delete(PROBE_KEY)
        except StorageError:
            pass
        try:
            depth.delete(PROBE_KEY)
        except StorageError:
            pass


# --- TICK-242 (#157): the D-020 denial classifier, exercised offline -----------------------------
#
# StorageDenied is what carries D-020: it is raised when the loader credential is refused on the
# depth bucket, and verify() fails unless that happens. Before these tests it was raised zero times
# by the running suite, so a change widening it would have shipped green.

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from frontdoor.storage import StorageDenied, StorageError, _raise_from_client


def _client_error(code, status=403):
    return ClientError(
        {"Error": {"Code": code, "Message": code}, "ResponseMetadata": {"HTTPStatusCode": status}},
        "GetObject",
    )


@pytest.mark.parametrize("code", ["AccessDenied", "403", "AllAccessDisabled", "AccessDeniedException"])
def test_authorization_refusal_is_the_d020_denial(code):
    """These, and only these, mean the storage policy refused a permitted-looking request."""
    with pytest.raises(StorageDenied):
        _raise_from_client(_client_error(code), "get", "frontdoor-depth", "k")


@pytest.mark.parametrize(
    "code", ["InvalidAccessKeyId", "SignatureDoesNotMatch", "ExpiredToken", "InvalidToken"]
)
def test_authentication_failure_is_not_the_denial(code):
    """A wrong or expired key also cannot read depth — for a reason that proves nothing.

    Counting these as the denial would let a broken credential masquerade as a working quarantine,
    which is the one thing this check exists to rule out.
    """
    with pytest.raises(StorageError) as caught:
        _raise_from_client(_client_error(code, status=403), "get", "frontdoor-depth", "k")
    assert not isinstance(caught.value, StorageDenied), (
        f"{code} is an authentication failure, not proof of the D-020 quarantine"
    )
    assert "credential problem" in str(caught.value)


@pytest.mark.parametrize("code", ["NoSuchBucket", "NoSuchKey", "InternalError", "SlowDown", ""])
def test_other_client_errors_are_not_the_denial(code):
    """A missing bucket or object is the commonest way a quarantine check passes vacuously."""
    with pytest.raises(StorageError) as caught:
        _raise_from_client(_client_error(code, status=404), "get", "frontdoor-depth", "k")
    assert not isinstance(caught.value, StorageDenied)


def test_a_network_failure_is_not_the_denial():
    """An unreachable endpoint must not read as a refusal."""
    exc = EndpointConnectionError(endpoint_url="https://example.invalid")
    with pytest.raises(StorageError) as caught:
        _raise_from_client(exc, "get", "frontdoor-depth", "k")
    assert not isinstance(caught.value, StorageDenied)


def test_storage_denied_is_a_storage_error():
    """Callers that catch StorageError must still see a denial; verify() depends on the ordering."""
    assert issubclass(StorageDenied, StorageError)


class _StubS3:
    """S3 stand-in that can refuse by credential, unlike moto.

    Salvaged from Ruben's #161. moto authorises every request, so under moto
    `verify()` fails no matter how the buckets are configured -- which is why
    nothing in this file proved it could pass. This models an ACL per access
    key, so a correct D-020 setup and a broken one look different.
    """

    def __init__(self):
        self.buckets = set()
        self.objects = {}
        self.acl = {}
        self.get_error = {}

    def client(self, creds):
        return _StubClient(self, creds)


class _StubClient:
    def __init__(self, account, creds):
        self._account = account
        self._creds = creds

    def put_object(self, Bucket, Key, Body):
        self._authorize(Bucket)
        self._account.objects[(Bucket, Key)] = bytes(Body)

    def get_object(self, Bucket, Key):
        forced = self._account.get_error.get((self._creds.access_key, Bucket))
        if forced is not None:
            raise forced
        self._authorize(Bucket)
        if Bucket not in self._account.buckets:
            raise _client_error("NoSuchBucket", 404)
        data = self._account.objects.get((Bucket, Key))
        if data is None:
            raise _client_error("NoSuchKey", 404)
        return {"Body": BytesIO(data)}

    def delete_object(self, Bucket, Key):
        self._account.objects.pop((Bucket, Key), None)

    def _authorize(self, bucket):
        allowed = self._account.acl.get(self._creds.access_key)
        if allowed is None or bucket not in allowed:
            raise _client_error("AccessDenied", 403)


def _scoped_stub(monkeypatch):
    """A correctly configured account: each token reaches only its own bucket."""
    _both_env(monkeypatch)
    account = _StubS3()
    account.buckets = {IMAGES, DEPTH}
    account.acl = {"img-key": {IMAGES}, "dep-key": {DEPTH}}
    monkeypatch.setattr(storage, "_client", account.client)
    return account


def test_verify_passes_when_the_loader_is_denied_on_depth(monkeypatch, capsys):
    """The success path, which no other test reaches.

    Every other offline test runs under moto, which authorises everything, so
    they all assert `verify()` fails. Without this one, deleting the branch that
    accepts a valid denial leaves the suite green -- the D-020 check could be
    permanently broken and CI would not say so.
    """
    _scoped_stub(monkeypatch)
    verify()
    assert "loader-denied-on-depth" in capsys.readouterr().out


def test_verify_fails_when_both_buckets_are_the_same_bucket(monkeypatch):
    """The quarantine is gone but the config still reads plausibly (D-020)."""
    _both_env(monkeypatch)
    monkeypatch.setenv("FRONTDOOR_DEPTH_BUCKET", IMAGES)
    account = _StubS3()
    account.buckets = {IMAGES}
    account.acl = {"img-key": {IMAGES}, "dep-key": {IMAGES}}
    monkeypatch.setattr(storage, "_client", account.client)
    with pytest.raises(StorageError, match="not denied on the depth bucket"):
        verify()


def test_verify_fails_when_one_token_is_used_for_both_credential_sets(monkeypatch):
    """Two bucket names, one token: the images key can read depth (D-020)."""
    _both_env(monkeypatch)
    monkeypatch.setenv("FRONTDOOR_DEPTH_ACCESS_KEY", "img-key")
    monkeypatch.setenv("FRONTDOOR_DEPTH_SECRET_KEY", "img-secret")
    account = _StubS3()
    account.buckets = {IMAGES, DEPTH}
    account.acl = {"img-key": {IMAGES, DEPTH}}
    monkeypatch.setattr(storage, "_client", account.client)
    with pytest.raises(StorageError, match="not denied on the depth bucket"):
        verify()
