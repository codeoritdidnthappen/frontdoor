"""Tests for two-bucket object storage (TICK-012, #20)."""

import os
from io import BytesIO
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from frontdoor import storage, storage_probe
from frontdoor.depth_access import depth_store, load_depth_creds
from frontdoor.storage import (
    OPEN_PREFIX,
    PROBE_KEY,
    SEALED_PREFIX,
    SPLITS,
    SealedObjectDenied,
    StorageDenied,
    StorageError,
    image_store,
    load_image_creds,
    storage_key,
)

# The credential probe moved to its own module (TICK-057): it READS depth, and `frontdoor.storage`
# is imported by the loader and the server for images, so a route to depth from there is a route
# they inherit. tests/test_depth_quarantine.py enforces the separation.
from frontdoor.storage_probe import main, probe_loader_denied_depth, verify

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
    assert "python -m frontdoor.storage_probe verify" in text


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


@pytest.mark.parametrize(("name", "value"), [
    ("FRONTDOOR_S3_ENDPOINT", "not a url"),
    ("FRONTDOOR_S3_ENDPOINT", "https://exa mple.com"),
    ("FRONTDOOR_S3_ENDPOINT", "https://_bad.example"),
    ("FRONTDOOR_S3_ENDPOINT", "https://-bad.example"),
    ("FRONTDOOR_S3_ENDPOINT", "https://bad-.example"),
    ("FRONTDOOR_S3_ENDPOINT", "https://example..com"),
    ("FRONTDOOR_S3_REGION", "bad region"),
])
def test_tick_b01_malformed_client_config_is_a_storage_error(
        monkeypatch, name, value):
    _image_env(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(StorageError, match="could not configure object storage"):
        image_store()


@pytest.mark.parametrize("endpoint", [
    "https://account.r2.cloudflarestorage.com",
    "http://127.0.0.1:9000",
    "http://[::1]:9000",
])
def test_tick_b01_valid_storage_endpoint_hosts_are_accepted(
        monkeypatch, endpoint):
    _image_env(monkeypatch)
    monkeypatch.setenv("FRONTDOOR_S3_ENDPOINT", endpoint)

    assert image_store().creds.endpoint == endpoint


@mock_aws
def test_image_put_and_get_round_trip(monkeypatch):
    _image_env(monkeypatch)
    _create_buckets()
    store = image_store()
    key = storage_key("cap-1", "dev")
    store.put(key, b"jpeg-bytes")
    assert store.get(key) == b"jpeg-bytes"


@mock_aws
def test_harness_reads_depth_that_the_loader_wrote_to_the_depth_bucket(monkeypatch):
    _both_env(monkeypatch)
    _create_buckets()
    key = storage_key("cap-1", "dev")
    depth_store().put(key, b"depth-bytes")
    assert depth_store().get(key) == b"depth-bytes"


@mock_aws
def test_unknown_capture_is_an_error(monkeypatch):
    _image_env(monkeypatch)
    _create_buckets()
    with pytest.raises(StorageError):
        image_store().get(storage_key("missing", "dev"))


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

import logging

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


def test_tick_263_ac_1_ac_2_ac_3_network_failure_is_safe_and_logged(
        caplog: pytest.LogCaptureFixture) -> None:
    """TICK-263: botocore names the endpoint URL; the server hands that message to the caller.

    upload_view returns a StorageError's text as the `detail` of a 503, so whatever is in it
    reaches anyone holding the upload key. The endpoint is our configuration and no client needs
    it, but the operator does -- so it belongs in the log and not in the exception.
    """
    # Fixture shape follows botocore's transport boundary, which raises
    # EndpointConnectionError(endpoint_url=request.url, error=exc).
    # https://github.com/boto/botocore/blob/develop/botocore/httpsession.py
    endpoint = "https://private-storage.example.test"
    exc = EndpointConnectionError(endpoint_url=endpoint)
    with caplog.at_level(logging.WARNING, logger="frontdoor.storage"):
        with pytest.raises(StorageError) as caught:
            _raise_from_client(exc, "put", "frontdoor-image", "open/cap-1")
    assert endpoint not in str(caught.value)
    # Still actionable from the client side: which operation, which object, and what kind of
    # failure -- enough to tell an outage from a refusal without retrying to find out.
    assert "put s3://frontdoor-image/open/cap-1 failed" in str(caught.value)
    assert "EndpointConnectionError" in str(caught.value)
    assert caught.value.__cause__ is exc
    assert "storage provider request failed" in caplog.text


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
    # Patched in BOTH modules. `_client` is resolved in whichever module's namespace the caller
    # lives in, and the probe moved to `storage_probe` (TICK-057) while `ObjectStore` stayed in
    # `storage` -- patching only one leaves the other talking to the real client.
    monkeypatch.setattr(storage, "_client", account.client)
    monkeypatch.setattr(storage_probe, "_client", account.client)
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
    monkeypatch.setattr(storage_probe, "_client", account.client)
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
    monkeypatch.setattr(storage_probe, "_client", account.client)
    with pytest.raises(StorageError, match="not denied on the depth bucket"):
        verify()


@mock_aws
def test_the_images_credential_cannot_fetch_a_sealed_capture(monkeypatch):
    """The attack from #182, which used to return the bytes.

    Before the key carried its partition, the seal lived only in `loader` and
    `eval`. Anyone holding the images credential -- everyone on the team, per
    `data/STORAGE.md` -- could fetch a sealed capture directly, and no audit line
    was written. What #166 established was that the harness would not read sealed
    data by accident, not that sealed data could not be read.
    """
    _image_env(monkeypatch)
    _create_buckets()
    store = image_store()
    key = storage_key("cap-sealed", "sealed")
    store.put(key, b"sealed-bytes")  # ingest must still be able to write it

    with pytest.raises(StorageDenied, match="sealed"):
        store.get(key)


@mock_aws
def test_the_audited_run_can_still_open_the_seal(monkeypatch):
    """Refusing everything would be a seal nobody can open on 2026-09-07."""
    _image_env(monkeypatch)
    _create_buckets()
    store = image_store()
    key = storage_key("cap-sealed", "sealed")
    store.put(key, b"sealed-bytes")

    assert store.get(key, allow_sealed=True) == b"sealed-bytes"


@mock_aws
def test_an_unpartitioned_key_is_refused_rather_than_assumed_open(monkeypatch):
    """Fail closed. Guessing 'probably open' is how a sealed object gets served."""
    _image_env(monkeypatch)
    _create_buckets()
    with pytest.raises(StorageError, match="no partition prefix"):
        image_store().get("cap-1")


@pytest.mark.parametrize(
    "split,expected",
    [("sealed", "sealed/cap-1"), ("dev", "open/cap-1"), ("calib", "open/cap-1")],
)
def test_only_the_sealed_split_gets_the_sealed_prefix(split, expected):
    assert storage_key("cap-1", split) == expected


@pytest.mark.parametrize(
    "split", ["Sealed", " sealed", "SEALED", "sealed ", "sealed\n", "", None, 0, "typo"]
)
def test_storage_key_fails_closed_on_anything_that_is_not_a_split(split):
    """Fail closed on write, the way `get` does on read (QA B02).

    This test previously asserted the opposite for `""` -- it pinned the fail-open
    behaviour as correct. Every spelling here other than the exact literal produced
    `open/cap-1`, and `loader.is_sealed`'s own docstring names this same set as the
    dangerous one: a sealed capture written to the open partition is served on a
    default run with no flag, no error and no audit line.
    """
    with pytest.raises(StorageError, match="unknown split"):
        storage_key("cap-1", split)


def test_storage_denied_on_a_sealed_key_is_not_the_d020_denial():
    """Both raise StorageDenied; they are different claims and must stay separable."""
    assert SEALED_PREFIX != OPEN_PREFIX
    assert PROBE_KEY.startswith(OPEN_PREFIX)


def test_the_two_split_tuples_do_not_drift():
    """`storage.SPLITS` is duplicated from the loader to keep the dependency one-way."""
    from frontdoor.loader import DatasetLoader

    assert SPLITS == DatasetLoader.SPLITS


@mock_aws
def test_put_writes_exactly_one_object_and_only_at_the_given_key(monkeypatch):
    """The mutation that defeated the seal invisibly (QA B01).

    Making `put` mirror every sealed object into the open partition left all 417
    tests green: `get("sealed/<id>")` still raised, so THE SEAL STILL LOOKED INTACT,
    while `get("open/<id>")` returned the sealed bytes with no refusal and no audit
    line. That is exactly the failure #182 was opened to close, reintroduced through
    the write side. Nothing asserted which key `put` writes to.
    """
    _image_env(monkeypatch)
    client = _create_buckets()
    sealed = storage_key("cap-s", "sealed")
    image_store().put(sealed, b"sealed-bytes")

    listed = client.list_objects_v2(Bucket=IMAGES).get("Contents", [])
    assert [o["Key"] for o in listed] == [sealed], "put wrote somewhere it was not asked to"


@mock_aws
def test_delete_removes_only_the_given_key(monkeypatch):
    """`delete` had zero coverage: a no-op and a wrong-key mutation both survived."""
    _image_env(monkeypatch)
    client = _create_buckets()
    store = image_store()
    keep, drop = storage_key("cap-keep", "dev"), storage_key("cap-drop", "dev")
    store.put(keep, b"keep")
    store.put(drop, b"drop")

    store.delete(drop)
    remaining = [o["Key"] for o in client.list_objects_v2(Bucket=IMAGES).get("Contents", [])]
    assert remaining == [keep]


@mock_aws
@pytest.mark.parametrize("method", ["put", "delete"])
def test_writes_also_refuse_an_unpartitioned_key(monkeypatch, method):
    """Nothing else tells the #66 ingest path to call storage_key() (QA B01, B04)."""
    _image_env(monkeypatch)
    _create_buckets()
    store = image_store()
    args = (b"bytes",) if method == "put" else ()
    with pytest.raises(StorageError, match="no partition prefix"):
        getattr(store, method)("cap-1", *args)


def test_the_sealed_refusal_is_distinguishable_from_the_d020_denial():
    """Both are StorageDenied; a caller must still be able to tell them apart (QA B05).

    `_raise_from_client` already keeps authentication failures from masquerading as
    the quarantine, because a denial for the wrong reason is not evidence of the right
    policy. The sealed refusal is a third claim -- this code refused, the provider was
    never asked -- and it needs the same separation.
    """
    assert issubclass(SealedObjectDenied, StorageDenied)
    assert not issubclass(StorageDenied, SealedObjectDenied)


@mock_aws
def test_opening_the_seal_must_be_spelled_out_at_the_call_site(monkeypatch):
    """`allow_sealed` is keyword-only, and that is load-bearing (QA B01).

    A positional flag lets a sealed read be authorised by a bare `True` -- easy to
    pass by accident, and invisible when reading the call site. Keyword-only means
    every unsealing in this repository is greppable as `allow_sealed=True`.
    """
    _image_env(monkeypatch)
    _create_buckets()
    store = image_store()
    key = storage_key("cap-s", "sealed")
    store.put(key, b"sealed-bytes")

    with pytest.raises(TypeError):
        store.get(key, True)


# --- existence, for the freeze-day preflight (#62) ---------------------------


@mock_aws
def test_exists_is_true_for_a_stored_object_and_false_for_a_missing_one(monkeypatch):
    _image_env(monkeypatch)
    _create_buckets()
    store = image_store()
    store.put(storage_key("cap-1", "dev"), b"jpeg-bytes")
    assert store.exists(storage_key("cap-1", "dev")) is True
    assert store.exists(storage_key("cap-2", "dev")) is False


@mock_aws
def test_a_missing_object_is_false_rather_than_an_error(monkeypatch):
    """`get` raises for a missing key; the preflight has to be able to ask without handling it.

    The whole point is to answer the question before the seal is opened, so a 404 is an answer,
    not a failure.
    """
    _image_env(monkeypatch)
    _create_buckets()
    assert image_store().exists(storage_key("never-uploaded", "calib")) is False


@mock_aws
def test_exists_answers_for_a_sealed_key_without_returning_bytes(monkeypatch):
    """Deliberate, and the reason is in the method's docstring.

    Existence is metadata, and the capture ids asked about come from the committed manifest, so
    nothing is revealed that the repository does not already state. `put` already writes sealed
    keys with no audit line because ingest must; a HEAD is strictly less than that. What it buys
    is that a sealed capture whose bytes were never uploaded refuses the run instead of costing
    the seal.
    """
    _image_env(monkeypatch)
    _create_buckets()
    store = image_store()
    sealed = storage_key("cap-9", "sealed")
    store.put(sealed, b"jpeg-bytes")
    assert store.exists(sealed) is True
    # ...and reading it still is not allowed.
    with pytest.raises(SealedObjectDenied):
        store.get(sealed)


# --- the /ready reachability probe (#370) ------------------------------------
#
# THIRD attempt at one defect: /ready reported photo_storage true for a bucket
# that did not exist. The first two were tested under moto and shipped anyway,
# so most of what is below is deliberately NOT moto -- moto answers a HEAD with
# an XML error body that S3, R2 and MinIO do not send, and that is precisely
# what hid the first bug: a guard reading the parsed error code looked correct
# under moto while being inert against every real provider. Where a case cannot
# be staged faithfully, the ClientError response is built by hand in the shape a
# real provider produces -- measured against botocore 1.43.86, whose parser
# yields {"Code": "404"} from a bodyless HEAD and the provider's own
# NoSuchKey / NoSuchBucket / AccessDenied from a GET's XML body.
#
# moto's GET is faithful -- NoSuchKey and NoSuchBucket, 404, in a body, the same
# as the three real providers -- so the two @mock_aws cases at the end drive the
# defect and the healthy path end to end through a real client and botocore's
# real parser. It is the HEAD that moto gets wrong, and this probe asks a GET.


def _get_error(status, code, message):
    """A ClientError as botocore builds one from a real provider's GET response.

    Separate from `_client_error` above, which sets Message to the code: these
    tests need the two to differ, because the message is the part that quotes
    the deployment back and must not reach the log.

    `code` is what survives parsing. For a GET that is the provider's own code,
    because the error body is there to parse; for a HEAD it is the status as a
    string, because there is no body at all (RFC 9110) and botocore synthesizes
    one. Passing a HEAD-shaped code here is how a test below states which wire
    shape it is standing in for.
    """
    return ClientError(
        {
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        "GetObject",
    )


def _head_error(status):
    """A HEAD error as botocore builds one: no body, so the CODE is the status.

    Measured, not assumed -- botocore 1.43.86's RestXMLParser on a bodyless 404
    yields exactly `{"Code": "404", "Message": "Not Found"}`. This is the shape
    moto does not produce, and the reason two probes read as correct in the
    suite while passing a deleted bucket in production.
    """
    return ClientError(
        {
            "Error": {"Code": str(status),
                      "Message": "Not Found" if status == 404 else "Forbidden"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        "HeadObject",
    )


class _FakeS3:
    """One deployment state, answering EVERY call the way that state answers it.

    Faithful on the calls the probe does not make as well as the one it does:
    a fake that refused HEAD would let this table pass against a HEAD-based
    probe for the wrong reason, and "these tests fail against the old code" is
    the only claim that distinguishes this attempt from the last two.
    """

    def __init__(self, head_bucket, head_object, get_object):
        self._outcomes = {
            "head_bucket": head_bucket,
            "head_object": head_object,
            "get_object": get_object,
        }
        self.calls = []

    def _answer(self, name, kwargs):
        self.calls.append((name, kwargs.get("Bucket"), kwargs.get("Key")))
        outcome = self._outcomes[name]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome or {}

    def head_bucket(self, **kwargs):
        return self._answer("head_bucket", kwargs)

    def head_object(self, **kwargs):
        return self._answer("head_object", kwargs)

    def get_object(self, **kwargs):
        return self._answer("get_object", kwargs)


def _one_answer(outcome):
    """A state that answers everything the same way, for the rows where only
    the GET matters."""
    return _FakeS3(head_bucket=outcome, head_object=outcome, get_object=outcome)


# The four states a deployment can actually be in. Each row says what every
# call answers in that state, so the table also records WHY the two HEAD-based
# probes could not work: to a HEAD, "healthy" and "bucket deleted" are the same
# two answers, and `test_the_two_states_no_head_can_separate` asserts that
# rather than leaving it as a comment.
#
# HeadBucket is 403 in three rows on purpose: this project's images token is
# scoped per bucket at the object level (D-020, D-026, D-033), and an
# object-scoped identity is refused bucket-level calls whatever became of the
# bucket -- so HeadBucket's 404 branch is dead here.
STATES = {
    "bucket healthy, objects readable": (
        _FakeS3(
            head_bucket=_head_error(403),
            head_object=_head_error(404),
            get_object=_get_error(404, "NoSuchKey",
                                  "The specified key does not exist."),
        ),
        True,
    ),
    "bucket healthy, objects NOT readable": (
        _FakeS3(
            head_bucket=None,  # 200: this credential can SEE the bucket
            head_object=_head_error(403),
            get_object=_get_error(403, "AccessDenied", "Access Denied"),
        ),
        False,
    ),
    "bucket deleted, object-scoped token": (
        _FakeS3(
            head_bucket=_head_error(403),
            head_object=_head_error(404),
            get_object=_get_error(404, "NoSuchBucket",
                                  "The specified bucket does not exist."),
        ),
        False,
    ),
    "credential expired or revoked": (
        _FakeS3(
            head_bucket=_head_error(403),
            head_object=_head_error(403),
            get_object=_get_error(400, "ExpiredToken",
                                  "The provided token has expired."),
        ),
        False,
    ),
}


def _probe_against(monkeypatch, fake):
    _image_env(monkeypatch)
    fake.calls.clear()
    monkeypatch.setattr(storage, "_client", lambda creds, timeout=None: fake)
    return fake


@pytest.mark.parametrize("state", list(STATES))
def test_the_probe_answers_each_deployment_state(monkeypatch, state):
    """Why a GET and not a HEAD, in one table.

    Verified against both earlier probes: the HeadObject one passed the deleted
    bucket, and the HeadBucket-first one passed the deleted bucket AND the
    credential that can see the bucket while reading nothing in it -- a green
    light over photographs that never persist. A GET error carries an XML body,
    so NoSuchKey and NoSuchBucket arrive as themselves and one call separates
    every row.
    """
    fake, expected = STATES[state]
    _probe_against(monkeypatch, fake)
    assert storage.image_bucket_is_reachable() is expected, state


def test_the_probe_costs_one_call_on_the_key_it_names(monkeypatch):
    """/ready is unauthenticated, so the probe stays one bounded round trip.

    Also the regression guard for the two calls it must NOT make: a HEAD here
    cannot answer the question, so asking one is the bug coming back.
    """
    fake, _ = STATES["bucket healthy, objects readable"]
    _probe_against(monkeypatch, fake)
    assert storage.image_bucket_is_reachable() is True
    assert fake.calls == [("get_object", IMAGES, PROBE_KEY)]


def test_a_404_that_carries_no_code_is_not_read_as_healthy(monkeypatch):
    """The ambiguity this change exists to remove, refused rather than guessed.

    S3, R2 and MinIO all answer a GET error with <Error><Code>; a 404 with no
    code came from something that stripped it, and cannot say whether the key
    or the bucket is missing. Accepting it would restore the first attempt's
    bug verbatim. The probe fails closed instead, which costs a warning on the
    deploy summary rather than photographs.
    """
    _probe_against(monkeypatch, _one_answer(_get_error(404, "404", "Not Found")))
    assert storage.image_bucket_is_reachable() is False


def test_a_provider_that_never_answers_is_not_read_as_healthy(monkeypatch):
    """No response attribute at all -- DNS, TLS, or the connect timeout."""
    _probe_against(
        monkeypatch,
        _one_answer(EndpointConnectionError(endpoint_url="https://example.invalid")),
    )
    assert storage.image_bucket_is_reachable() is False


def test_the_probe_says_which_code_it_saw_without_echoing_the_message(
        monkeypatch, caplog):
    """/ready is a boolean by design, so the log is the operator's only account.

    The provider's MESSAGE is not logged: several quote the configured endpoint
    back (TICK-263), and this line is written on every unauthenticated probe.
    """
    _probe_against(
        monkeypatch,
        _one_answer(_get_error(404, "NoSuchBucket", "no bucket named frontdoor-image")),
    )
    with caplog.at_level("WARNING", logger="frontdoor.storage"):
        assert storage.image_bucket_is_reachable() is False
    assert "NoSuchBucket" in caplog.text
    assert "frontdoor-image" not in caplog.text


def test_a_probe_that_cannot_be_configured_is_not_read_as_healthy(monkeypatch):
    """No credentials is the incident this endpoint was written for."""
    _image_env(monkeypatch)
    monkeypatch.delenv("FRONTDOOR_IMAGES_BUCKET", raising=False)
    monkeypatch.setattr(storage, "_load_dotenv_once", lambda: None)
    assert storage.image_bucket_is_reachable() is False


@mock_aws
def test_the_probe_reads_a_live_bucket_without_writing_to_it(monkeypatch):
    """The one thing moto is still good for: a real client, end to end.

    It proves the call is wired up and that a probe leaves no object behind.
    What it cannot settle is anything about a HEAD: moto answers one with a
    code no real HEAD carries, which is why the state table above is built by
    hand instead.
    """
    _image_env(monkeypatch)
    client = _create_buckets()
    assert storage.image_bucket_is_reachable() is True
    assert "Contents" not in client.list_objects_v2(Bucket=IMAGES)


@mock_aws
def test_the_probe_refuses_a_bucket_that_is_not_there(monkeypatch):
    """The defect itself, end to end through botocore's real XML parser.

    moto is the wrong instrument for a HEAD -- it answers one with an error
    body no real provider sends -- but this probe asks a GET, and moto's GET on
    a missing bucket returns exactly what S3, R2 and MinIO return:
    NoSuchBucket, 404, in a body. So the one case that shipped twice is worth
    driving through a real client and a real parser, not only through a
    ClientError this file built itself.
    """
    _image_env(monkeypatch)
    # deliberately no _create_buckets()
    assert storage.image_bucket_is_reachable() is False


@mock_aws
def test_the_probe_passes_when_the_probe_key_happens_to_exist(monkeypatch):
    """`frontdoor.storage_probe` writes this key, and can leave it behind.

    The bytes are not read: botocore hands back an unread stream, and the probe
    closes it rather than downloading an object on every /ready.
    """
    _image_env(monkeypatch)
    _create_buckets()
    image_store().put(PROBE_KEY, b"left over from storage_probe")
    assert storage.image_bucket_is_reachable() is True
