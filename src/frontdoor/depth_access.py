"""The only way to READ depth. Importing this module is the act D-020 governs.

Depth is captured on every entrance (D-020, D-032) and quarantined from the metrology code path:
"if depth sits where the method can reach it, it eventually gets used to tune, and the comparison
stops meaning anything."

**Why this is its own module rather than two functions in `storage`.** It is not tidiness. While
`depth_store()` lived beside `image_store()`, "who can read depth" was unanswerable as a question
about the code: `frontdoor.storage` is imported by the loader, the server and the harness alike,
because they all need images. Nothing could distinguish a module that reaches depth from one that
reaches a bucket. Here the import is a separate, visible act, so `tests/test_depth_quarantine.py`
can enumerate exactly who performs it and fail the build when that set grows.

**Who may import this:** the evaluation harness, and the storage self-test that proves the loader
credential is denied. **Not** the metrology library (TICK-040 gives it no I/O at all), and **not**
the server — D-039 keeps the depth R2 binding behind a separate PUT-only Worker, and that boundary
would be hollow if the server's import graph reached this module.
"""

from frontdoor.storage import BucketCreds, ObjectStore, _env, _shared_location


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


def depth_store():
    """Store used by the evaluation harness -- depth only.

    The harness also holds `image_store()`; it is a second credential, not a combined client, so a
    bug cannot widen the loader's scope.
    """
    return ObjectStore(load_depth_creds())
