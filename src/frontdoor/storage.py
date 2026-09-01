"""Two-bucket object storage for capture bytes (TICK-012, D-018, D-020, D-026).

Images and depth maps live in separate buckets so credentials can be scoped
per bucket. The dataset loader and the server get the images credential only;
the evaluation harness gets both; the core metrology library gets neither.

The object key is the capture_id. Separation is the bucket, not a prefix —
providers that cannot scope below bucket level cannot enforce D-020 with a
prefix alone.

Run as a tool:  python -m frontdoor.storage verify
Uploads a probe object with each credential, reads the image back with the
loader credential, and asserts that the same credential is denied on the
depth bucket.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

PROBE_KEY = "_frontdoor_probe"


class StorageError(Exception):
    """Missing config, or the storage provider rejected the call."""


class StorageDenied(StorageError):
    """The credential was not allowed to read or write the object."""


@dataclass(frozen=True)
class BucketCreds:
    bucket: str
    access_key: str
    secret_key: str
    region: str
    endpoint: str | None


def _env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise StorageError(f"missing {name}")
    return value


def _optional_env(name):
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
    if code in {
        "AccessDenied",
        "403",
        "AllAccessDisabled",
        "AccessDeniedException",
        "InvalidAccessKeyId",
        "SignatureDoesNotMatch",
    }:
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

    def put(self, capture_id, body):
        try:
            self._client.put_object(
                Bucket=self.creds.bucket, Key=capture_id, Body=body
            )
        except Exception as exc:
            _raise_from_client(exc, "put", self.creds.bucket, capture_id)

    def get(self, capture_id):
        try:
            response = self._client.get_object(
                Bucket=self.creds.bucket, Key=capture_id
            )
        except Exception as exc:
            _raise_from_client(exc, "get", self.creds.bucket, capture_id)
        return response["Body"].read()

    def delete(self, capture_id):
        try:
            self._client.delete_object(Bucket=self.creds.bucket, Key=capture_id)
        except Exception as exc:
            _raise_from_client(exc, "delete", self.creds.bucket, capture_id)


def image_store():
    """Store used by the dataset loader and the server — images only."""
    return ObjectStore(load_image_creds())


def depth_store():
    """Store used by the evaluation harness — depth only.

    The harness also holds image_store(); it is a second credential, not a
    combined client, so a bug cannot widen the loader's scope.
    """
    return ObjectStore(load_depth_creds())


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
    finally:
        try:
            images.delete(PROBE_KEY)
        except StorageError:
            pass
        try:
            depth.delete(PROBE_KEY)
        except StorageError:
            pass
    print(
        f"ok  images={images.creds.bucket}  depth={depth.creds.bucket}  "
        "loader-denied-on-depth"
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
