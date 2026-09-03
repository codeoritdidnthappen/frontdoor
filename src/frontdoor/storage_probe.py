"""Prove the two-bucket credential scoping actually holds (TICK-012, D-020, D-033).

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
    ObjectStore,
    StorageDenied,
    StorageError,
    _client,
    _raise_from_client,
    image_store,
    load_depth_write_creds,
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
