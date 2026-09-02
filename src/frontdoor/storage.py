"""Two-bucket object storage for capture bytes (TICK-012, D-018, D-020, D-026).

Images and depth maps live in separate buckets so credentials can be scoped
per bucket. The dataset loader and the server get the images credential only;
the evaluation harness gets both; the core metrology library gets neither.

The object key is `<partition>/<capture_id>` — `open/` or `sealed/` (D-007,
D-028). Build keys with `storage_key()`; `get`, `put` and `delete` all refuse a
key without a partition. Images and depth remain separated by BUCKET, not by
prefix: providers that cannot scope below bucket level cannot enforce D-020 with
a prefix alone (D-026), which is also why the sealed partition is a code-level
refusal here and not a credential scope.

Run as a tool:  python -m frontdoor.storage verify
Uploads a probe object with each credential, reads the image back with the
loader credential, and asserts that the same credential is denied on the
depth bucket.
"""

from __future__ import annotations

import os

from dotenv import find_dotenv, load_dotenv
import sys
from dataclasses import dataclass

#: Capture keys carry their partition (D-007, #182). Storage can then refuse a
#: sealed read on the key alone -- it never reads the manifest, never imports
#: `split`, and does not depend on `loader`, which already depends on it.
#: Chosen while zero objects existed; changing it later means migrating every
#: object and re-verifying each against its sidecar hash.
OPEN_PREFIX = "open/"
SEALED_PREFIX = "sealed/"

PROBE_KEY = OPEN_PREFIX + "_frontdoor_probe"


#: D-007's three splits. Duplicated from `loader.DatasetLoader.SPLITS` rather than
#: imported: `loader` imports this module, and that dependency must not invert.
#: `test_the_two_split_tuples_do_not_drift` pins them together.
SPLITS = ("dev", "calib", "sealed")


def _partition_of(key):
    """Which partition a key belongs to. Refuses rather than guessing.

    Fail closed. An unpartitioned key is one this module cannot classify, and
    guessing "probably open" is how a sealed object gets served.
    """
    if key.startswith(SEALED_PREFIX):
        return "sealed"
    if key.startswith(OPEN_PREFIX):
        return "open"
    raise StorageError(
        f"{key!r} has no partition prefix; keys must start with "
        f"{OPEN_PREFIX!r} or {SEALED_PREFIX!r} (D-007). Build them with storage_key()."
    )


def storage_key(capture_id, split):
    """The object key for a capture, with its partition in the key.

    The caller passes the split because the caller is the one that derived it.

    Fails CLOSED on anything that is not one of D-007's three splits, matching `get`.
    An earlier version treated every non-`sealed` value as open, so `"Sealed"`,
    `" sealed"`, `"SEALED"` and `None` all produced an open key -- the exact set
    `loader.is_sealed`'s docstring names as dangerous (QA B02).
    """
    if split == "sealed":
        return f"{SEALED_PREFIX}{capture_id}"
    if split in SPLITS:
        return f"{OPEN_PREFIX}{capture_id}"
    raise StorageError(
        f"unknown split {split!r}; expected one of {', '.join(SPLITS)}. Refusing to "
        "guess a partition: 'Sealed', ' sealed' and None are exactly the spellings that "
        "would otherwise be written to the open partition and served without an audit line."
    )


class StorageError(Exception):
    """Missing config, or the storage provider rejected the call."""


class StorageDenied(StorageError):
    """The credential was not allowed to read or write the object."""


class SealedObjectDenied(StorageDenied):
    """THIS CODE refused a sealed key (D-007) -- the provider was never asked.

    Distinct from the D-020 denial, which is the provider refusing a credential.
    `_raise_from_client` already keeps authentication failures from masquerading as
    the quarantine, on the grounds that a denial for the wrong reason is not evidence
    of the right policy; the same reasoning applies here (QA B05). Subclasses
    StorageDenied so existing handlers still work.
    """


@dataclass(frozen=True)
class BucketCreds:
    bucket: str
    access_key: str
    secret_key: str
    region: str
    endpoint: str | None


_dotenv_loaded = False


def _load_dotenv_once():
    """Load repo-root .env if present, without overriding a real environment variable.

    data/STORAGE.md tells the operator to put credentials in .env. Nothing read it, so following
    the runbook verbatim produced `missing FRONTDOOR_IMAGES_BUCKET`, which looks like a credential
    mistake rather than a missing loader (#158). Real environment variables still win, so CI and a
    shell export are unaffected.
    """
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _dotenv_loaded = True
    # Search upward from the working directory rather than deriving the repo root from __file__.
    # parents[2] is the repo root only for a source checkout or editable install; installed
    # normally it is site-packages' parent, so the runbook's promise would silently not hold --
    # and could pick up an unrelated .env.
    env_path = find_dotenv(usecwd=True)
    if env_path:
        load_dotenv(env_path, override=False)


def _env(name):
    _load_dotenv_once()
    value = os.environ.get(name, "").strip()
    if not value:
        raise StorageError(
            f"missing {name}. Copy .env.example to .env and fill it in, or export it; "
            "see data/STORAGE.md."
        )
    return value


def _optional_env(name):
    _load_dotenv_once()
    value = os.environ.get(name, "").strip()
    return value or None


def _shared_location():
    return {
        "region": os.environ.get("FRONTDOOR_S3_REGION", "auto").strip() or "auto",
        "endpoint": _optional_env("FRONTDOOR_S3_ENDPOINT"),
    }


def load_image_creds():
    """Credentials that can read images and must not read depth (D-020)."""
    loc = _shared_location()
    return BucketCreds(
        bucket=_env("FRONTDOOR_IMAGES_BUCKET"),
        access_key=_env("FRONTDOOR_IMAGES_ACCESS_KEY"),
        secret_key=_env("FRONTDOOR_IMAGES_SECRET_KEY"),
        region=loc["region"],
        endpoint=loc["endpoint"],
    )


def load_depth_creds():
    """Credentials that can read depth. Only the evaluation harness holds these."""
    loc = _shared_location()
    return BucketCreds(
        bucket=_env("FRONTDOOR_DEPTH_BUCKET"),
        access_key=_env("FRONTDOOR_DEPTH_ACCESS_KEY"),
        secret_key=_env("FRONTDOOR_DEPTH_SECRET_KEY"),
        region=loc["region"],
        endpoint=loc["endpoint"],
    )


def load_depth_write_creds():
    """Write-only credentials for the depth bucket, held by the server (D-033).

    Object Write only -- no read, no list. The server has to be able to STORE a depth map that a
    phone uploads, and must never be able to read one back: D-020's guarantee is that the metrology
    path cannot read depth, because depth it can reach is depth it eventually tunes on. A
    write-only token cannot tune, peek or load, so the invariant holds with the server on the write
    side of it. The evaluation harness keeps load_depth_creds() and stays the only reader.
    """
    loc = _shared_location()
    return BucketCreds(
        bucket=_env("FRONTDOOR_DEPTH_BUCKET"),
        access_key=_env("FRONTDOOR_DEPTH_WRITE_ACCESS_KEY"),
        secret_key=_env("FRONTDOOR_DEPTH_WRITE_SECRET_KEY"),
        region=loc["region"],
        endpoint=loc["endpoint"],
    )


def _client(creds):
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise StorageError("boto3 is required to talk to object storage") from exc
    # boto3 1.36+ sends CRC32 checksums by default; R2 rejects them as AccessDenied.
    kwargs = {
        "aws_access_key_id": creds.access_key,
        "aws_secret_access_key": creds.secret_key,
        "region_name": creds.region,
        "config": Config(
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    }
    if creds.endpoint:
        kwargs["endpoint_url"] = creds.endpoint
    return boto3.client("s3", **kwargs)


def _raise_from_client(exc, action, bucket, key):
    from botocore.exceptions import ClientError

    if not isinstance(exc, ClientError):
        raise StorageError(f"{action} s3://{bucket}/{key} failed: {exc}") from exc
    code = exc.response.get("Error", {}).get("Code", "")
    # Authentication failures are NOT the D-020 denial. A wrong or expired key also cannot read
    # depth, but for a reason that says nothing about the quarantine — treating it as proof would
    # let a broken credential masquerade as a working policy.
    if code in {"InvalidAccessKeyId", "SignatureDoesNotMatch", "ExpiredToken", "InvalidToken"}:
        raise StorageError(
            f"{action} s3://{bucket}/{key} failed to authenticate ({code}). "
            "This is a credential problem, not proof of the depth quarantine."
        ) from exc
    if code in {"AccessDenied", "403", "AllAccessDisabled", "AccessDeniedException"}:
        raise StorageDenied(
            f"{action} s3://{bucket}/{key} denied ({code})"
        ) from exc
    raise StorageError(
        f"{action} s3://{bucket}/{key} failed ({code or exc})"
    ) from exc


class ObjectStore:
    """Put and get capture bytes in one bucket."""

    def __init__(self, creds):
        self.creds = creds
        self._client = _client(creds)

    def put(self, key, body):
        """Write one object. Sealed keys ARE allowed -- capture upload has to store them.

        The key is still classified, so an ingest path that forgets `storage_key()`
        fails here rather than writing an object no reader can classify (QA B01).
        """
        _partition_of(key)
        try:
            self._client.put_object(Bucket=self.creds.bucket, Key=key, Body=body)
        except Exception as exc:
            _raise_from_client(exc, "put", self.creds.bucket, key)

    def get(self, key, *, allow_sealed=False):
        """Read one object. Sealed keys are refused (D-007).

        Before this check the seal lived only in `loader` and `eval`, so anyone
        holding the images credential could fetch a sealed capture's bytes
        directly and no audit line was written (#182). The guarantee was that
        the harness would not read sealed data by accident, not that sealed data
        could not be read.

        Only the audited `--include-sealed` run passes `allow_sealed=True`, the
        same shape as `DatasetLoader._load_row`.
        """
        if _partition_of(key) == "sealed" and not allow_sealed:
            raise SealedObjectDenied(
                f"{key!r} is sealed; it is opened once, by an audited "
                "`python -m frontdoor.eval --include-sealed` run (D-007, D-017)"
            )
        try:
            response = self._client.get_object(Bucket=self.creds.bucket, Key=key)
        except Exception as exc:
            _raise_from_client(exc, "get", self.creds.bucket, key)
        return response["Body"].read()

    def delete(self, key):
        _partition_of(key)
        try:
            self._client.delete_object(Bucket=self.creds.bucket, Key=key)
        except Exception as exc:
            _raise_from_client(exc, "delete", self.creds.bucket, key)


def image_store():
    """Store used by the dataset loader and the server — images only."""
    return ObjectStore(load_image_creds())


def depth_store():
    """Store used by the evaluation harness — depth only.

    The harness also holds image_store(); it is a second credential, not a
    combined client, so a bug cannot widen the loader's scope.
    """
    return ObjectStore(load_depth_creds())


def depth_write_store():
    """Store the server uses to accept depth uploads -- write-only (D-033).

    Separate factory rather than a flag on depth_store(), so that a caller wanting to read depth
    cannot get there by passing an argument. The two credentials are different tokens.
    """
    return ObjectStore(load_depth_write_creds())


def probe_loader_denied_depth(image_creds, depth_bucket, key=PROBE_KEY):
    """GET depth with the loader credential. Must be denied by the provider.

    This is the D-020 check: the denial is the storage policy, not us skipping
    the call. TICK-072 (library-level refusal) is a separate defence.
    """
    client = _client(image_creds)
    try:
        client.get_object(Bucket=depth_bucket, Key=key)
    except Exception as exc:
        _raise_from_client(exc, "get", depth_bucket, key)
        raise
    raise StorageError(
        f"loader credential was not denied on the depth bucket "
        f"(read s3://{depth_bucket}/{key})"
    )


DEPTH_WRITE_PROBE_KEY = PROBE_KEY + ".write-probe"


def probe_depth_write_is_write_only(write_creds, key=DEPTH_WRITE_PROBE_KEY):
    """PUT with the server's depth token must succeed; GET with it must be denied (D-033).

    This is the check that makes D-033's guarantee testable rather than asserted. The token is
    supposed to be Object Write only: if a read succeeds, the scope leaked when the token was
    created, the server can see depth, and the D-020 quarantine is void from the server outward.
    Failing loudly here is the difference between finding that in a dashboard and finding it after
    the comparison has been tuned on data it should never have reached.
    """
    store = ObjectStore(write_creds)
    store.put(key, b"frontdoor-depth-write-probe")
    try:
        store.get(key)
    except StorageDenied:
        return
    except StorageError:
        # Any other failure is not proof of the scope; report it rather than passing.
        raise
    raise StorageError(
        f"the server's depth token was NOT denied on read (s3://{write_creds.bucket}/{key}); "
        "it is not write-only, so D-033's guarantee does not hold"
    )


def verify():
    """Upload, read back, and prove the loader credential cannot read depth."""
    images = image_store()
    depth = depth_store()
    payload = b"frontdoor-storage-probe"
    images.put(PROBE_KEY, payload)
    depth.put(PROBE_KEY, payload)
    try:
        got = images.get(PROBE_KEY)
        if got != payload:
            raise StorageError("image probe round-trip mismatch")
        try:
            probe_loader_denied_depth(images.creds, depth.creds.bucket)
        except StorageDenied:
            pass
        got_depth = depth.get(PROBE_KEY)
        if got_depth != payload:
            raise StorageError("depth probe round-trip mismatch")
        # D-033: the server's depth token must be able to write and unable to read. Skipped only
        # when it is not configured at all, so a laptop without it still runs the D-020 check.
        write_creds = None
        try:
            write_creds = load_depth_write_creds()
        except StorageError:
            write_note = "  depth-write-token=unset"
        if write_creds is not None:
            probe_depth_write_is_write_only(write_creds)
            write_note = "  depth-write-denied-on-read"
    finally:
        try:
            images.delete(PROBE_KEY)
        except StorageError:
            pass
        try:
            depth.delete(PROBE_KEY)
        except StorageError:
            pass
        try:
            depth.delete(DEPTH_WRITE_PROBE_KEY)
        except StorageError:
            pass
    print(
        f"ok  images={images.creds.bucket}  depth={depth.creds.bucket}  "
        "loader-denied-on-depth" + write_note
    )


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args != ["verify"]:
        print(
            "usage: python -m frontdoor.storage verify",
            file=sys.stderr,
        )
        return 2
    try:
        verify()
    except StorageError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
