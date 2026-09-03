"""Prove the two-bucket credential scoping actually holds (TICK-012, D-020).

Separate from `frontdoor.storage` on purpose, and the separation is load-bearing rather than
tidy. This module reads depth, so anything importing it can reach depth. `frontdoor.storage` is
imported by the dataset loader and by the server for IMAGE access -- if the probe lived there,
every one of them would carry a route to depth, and `tests/test_depth_quarantine.py` would be
unable to tell a module that reaches depth from one that merely stores an image.

Run it from a team Mac, or wherever the harness runs:

    python -m frontdoor.storage_probe verify

It must print `loader-denied-on-depth`. The denial is the requirement.
"""

import sys

from frontdoor.depth_access import depth_store
from frontdoor.storage import (
    PROBE_KEY,
    StorageDenied,
    StorageError,
    _client,
    _raise_from_client,
    image_store,
)

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
    """Upload, read back, and prove the loader credential cannot read depth.

    Lives in this module rather than in `frontdoor.storage` because it reads depth, and storage is
    what the loader and the server import for images. See this module's docstring.
    """
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
            "usage: python -m frontdoor.storage_probe verify",
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
