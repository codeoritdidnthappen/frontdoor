"""POST /upload -- capture ingest from the phone (TICK-029, #33).

Bytes go phone -> server -> storage, never phone -> bucket. No R2 credential ships inside the
capture app: a free-provisioning build is installed on several phones, and the images token can
also READ sealed captures (data/STORAGE.md), so a token in an IPA widens the seal's exposure to
anyone holding a build. The server holds read+write on the image bucket. Depth crosses a separate
authenticated Worker whose R2 binding never enters this process (TICK-250).

What this endpoint guarantees, stated precisely because the halves differ:

- The bytes it stores hash to the value the client claimed. A mismatch is refused with 422 and
  nothing is written, so the client retries rather than recording a phantom upload (AC4).
- **The partition is recomputed here, not trusted.** The client sends `entrance_id`; the split is
  derived from it with the committed seed. A phone carrying a drifted seed cannot land a sealed
  entrance in `open/`, which is a mislabelling no downstream artifact could detect.
- **Writes are conditional.** An object already at that key is not overwritten. Without that,
  anyone holding the ingest key could replace a sealed capture's bytes and the read-back would
  then confirm the replacement as correct.
- For **open images** it re-reads the stored object and hashes it, so "stored" means verified as
  stored, which is what lets the app delete its local copy (AC5).
- For **depth** that read-back is impossible by construction: D-039 keeps the R2 binding inside a
  PUT-only Worker boundary. A **sealed image** cannot be read back either --
  ObjectStore.get refuses sealed keys, and passing allow_sealed here would write a SEAL_AUDIT line
  on every upload and make unsealing routine, which is what D-007 and D-017 prevent. Both fall
  back to verify-on-receipt, and the response says which check ran in `verified`.
"""

import hashlib
import hmac
import os
from tempfile import SpooledTemporaryFile

from flask import current_app, request

from frontdoor.split import assign_split, canonical_entrance_id
from frontdoor.storage import (
    ObjectExists,
    StorageError,
    image_store,
    storage_key,
)
from frontdoor_server.depth_ingest import (
    DepthIngestConfig,
    DepthIngestConflict,
    DepthIngestError,
    DepthIngestRejected,
    put_depth,
)

KINDS = ("image", "depth")

#: Hex SHA-256, lowercase, exactly this long.
_SHA256_LEN = 64

#: Per-route ceiling, well under the app-wide MAX_CONTENT_LENGTH.
#:
#: #33 scopes this to "single-digit-megabyte files", and the host is one 256 MB machine running a
#: single gunicorn worker with two threads (Dockerfile). The app-wide 64 MB cap was sized for a
#: different route; two concurrent uploads at that size would put the process near its memory
#: limit, and an OOM kill reads to the phones as a dropped connection, which they retry -- a loop
#: that never drains.
UPLOAD_MAX_BYTES = 16 * 1024 * 1024

#: Streamed in chunks so neither hashing nor read-back holds a whole capture in memory.
_CHUNK = 1024 * 1024

#: capture_id goes straight into an object key, so it is constrained to characters that cannot
#: traverse or confuse one: no "/", no "..", no control characters, no whitespace.
_ID_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")


def _client_key():
    """The shared secret, or None when unset.

    Unset means the endpoint refuses every request rather than running open. An ingest path that
    silently accepts anonymous writes into the dataset bucket is worse than one that is switched
    off, and a misconfigured deploy should fail loudly on the first upload, not quietly accept
    strangers' bytes.
    """
    value = os.environ.get("FRONTDOOR_UPLOAD_KEY", "").strip()
    return value or None


def _authorised(presented, expected):
    if expected is None or not presented:
        return False
    # Compared as bytes: hmac.compare_digest raises TypeError on non-ASCII str, and Werkzeug
    # decodes headers as latin-1 -- so a single high byte in a header, or a non-ASCII character in
    # the configured key, would turn every request into a 500 that the app then retries forever.
    # Constant-time because a timing oracle here hands out write access to the dataset bucket.
    return hmac.compare_digest(presented.encode("utf-8", "surrogateescape"),
                               expected.encode("utf-8", "surrogateescape"))


def _is_sha256(value):
    return len(value) == _SHA256_LEN and all(c in "0123456789abcdef" for c in value)


def _valid_capture_id(value):
    return (
        bool(value)
        and len(value) <= 128
        and ".." not in value
        and all(c in _ID_ALLOWED for c in value)
    )


def _spool_and_hash(stream, limit):
    """Copy the upload into a spooled temp file, hashing as it goes.

    Returns (file, digest, size) with the file rewound, or (None, None, size) past the limit.
    Spooled rather than `.read()`: small captures stay in memory, large ones go to disk, and the
    process never holds the whole body plus a second copy for the read-back.
    """
    digest = hashlib.sha256()
    size = 0
    spool = SpooledTemporaryFile(max_size=2 * 1024 * 1024)
    while True:
        chunk = stream.read(_CHUNK)
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            spool.close()
            return None, None, size
        digest.update(chunk)
        spool.write(chunk)
    spool.seek(0)
    return spool, digest.hexdigest(), size


def register_upload(app, error):
    """Register POST /upload on `app`, reporting failures through the server's error contract.

    `error` is app.py's `_error`, passed in rather than imported, because importing it here would
    make app.py and this module import each other.
    """

    client_key = _client_key()
    depth_config = None
    depth_config_failure = None
    if client_key is not None:
        try:
            depth_config = DepthIngestConfig.from_environment()
        except DepthIngestError as exc:
            # Keep liveness and image ingest available when only depth ingest is misconfigured.
            # The depth path reports the named variable below, where the capture remains retryable.
            depth_config_failure = str(exc)

    @app.post("/upload")
    def upload():
        if not _authorised(request.headers.get("X-Frontdoor-Upload-Key", ""), client_key):
            # Deliberately does not distinguish "no key configured" from "wrong key": the client
            # can do nothing useful with the difference, and the distinction tells a stranger
            # whether they found a live-but-misconfigured deployment.
            return error(
                "upload not authorised",
                "POST /upload requires the X-Frontdoor-Upload-Key header.",
                status=401,
            )

        kind = request.form.get("kind", "")
        if kind not in KINDS:
            return error(
                "unknown upload kind",
                f"kind must be one of {', '.join(KINDS)}; got {kind!r}.",
                field="kind",
            )

        # Nothing below is coerced. Stripping or case-folding a field that decides WHERE bytes land
        # is a place where the value the client meant and the value stored can differ. The client
        # is our own app; sending the exact spelling is free.
        capture_id = request.form.get("capture_id", "")
        if not _valid_capture_id(capture_id):
            return error(
                "invalid capture_id",
                "capture_id must be non-empty, at most 128 characters, contain only letters, "
                "digits, dash, underscore or dot, and must not contain '..'.",
                field="capture_id",
            )

        # The split is DERIVED, not accepted. A build carrying a drifted seed -- the drift
        # SplitAssignment.swift exists to warn about -- would otherwise land sealed entrances in
        # the open partition, and nothing downstream could tell.
        entrance_id = request.form.get("entrance_id", "")
        try:
            split = assign_split(canonical_entrance_id(entrance_id))
        except Exception as exc:
            return error(
                "entrance_id is not a canonical entrance id",
                f"{exc}",
                field="entrance_id",
            )

        claimed = request.form.get("sha256", "")
        if not _is_sha256(claimed):
            # Lowercase required, not lowercased for you: the sidecar schema anchors hashes as
            # lowercase hex (TICK-228), so there is one spelling of a digest in the system.
            return error(
                "sha256 is not a hex digest",
                "sha256 must be 64 lowercase hex characters.",
                field="sha256",
            )

        if "bytes" not in request.files:
            return error(
                "missing bytes",
                "POST /upload expects multipart/form-data with a file part named 'bytes'.",
                field="bytes",
            )

        spool, actual, size = _spool_and_hash(request.files["bytes"].stream, UPLOAD_MAX_BYTES)
        if spool is None:
            return error(
                "upload too large",
                f"this endpoint accepts at most {UPLOAD_MAX_BYTES} bytes; got at least {size}.",
                field="bytes",
                status=413,
            )
        try:
            if size == 0:
                return error("empty upload", "The 'bytes' part carried no data.", field="bytes")

            if not hmac.compare_digest(actual, claimed):
                # Nothing is stored. A truncated or corrupted body must leave the bucket untouched,
                # so the client's retry is a first attempt rather than an overwrite of bad bytes.
                return error(
                    "sha256 mismatch",
                    f"claimed {claimed}, received bytes hash to {actual}; nothing was stored.",
                    field="sha256",
                    status=422,
                )

            try:
                key = storage_key(capture_id, split)
            except StorageError as exc:
                return error("could not build a storage key", str(exc), field="capture_id")

            if kind == "depth":
                if depth_config_failure is not None:
                    return error("could not store the object", depth_config_failure, status=503)
                assert depth_config is not None
                try:
                    put_depth(spool, key=key, sha256=claimed, size=size, config=depth_config)
                except DepthIngestConflict:
                    return error(
                        "an object is already stored under this capture id",
                        f"{key} exists and cannot be compared from here; it was not overwritten.",
                        status=409,
                    )
                except DepthIngestRejected as exc:
                    # Permanent, so it must not be reported as an outage: these bytes will never
                    # hash to the declared digest, and 503 would keep the phone retrying them
                    # forever. Same 422 the local digest check above returns.
                    return error("sha256 mismatch", str(exc), field="sha256", status=422)
                except DepthIngestError as exc:
                    # 503 keeps the only copy queued on the phone while an internal credential or
                    # Worker outage is repaired; its details expose no service credential.
                    return error("could not store the object", str(exc), status=503)
                store = None
            else:
                try:
                    # Constructing the store reads credentials from the environment, so a
                    # misconfigured deploy raises HERE rather than in put() below. That was
                    # outside the try, so a missing variable escaped as an unhandled 500 with a
                    # traceback instead of the JSON contract every response is supposed to carry
                    # (TICK-225). Seen for real on 2026-09-04: a stale release asked for
                    # FRONTDOOR_DEPTH_BUCKET, which is obsolete and deliberately unset, and the
                    # phone got a bare 500 -- the actual cause was only findable in server logs.
                    #
                    # 503, like a failed put: the bytes are good, the capture is the only copy,
                    # and the client must keep it and retry rather than treat it as rejected.
                    store = image_store()
                except StorageError as exc:
                    return error("could not store the object", str(exc), status=503)
                try:
                    store.put(key, spool, if_absent=True)
                except ObjectExists:
                    return _already_there(error, store, kind, key, split, claimed)
                except StorageError as exc:
                    # 503: the bytes were good and the client should retry. Reporting this as a client
                    # error would make the app drop a capture it holds the only copy of.
                    return error("could not store the object", str(exc), status=503)
        finally:
            spool.close()

        # Read-back is the stronger check and is available in exactly one case: an OPEN image.
        verified = "received"
        if kind == "image" and split != "sealed":
            assert store is not None
            confirmed, failure = _read_back_matches(store, key, claimed)
            if failure is not None:
                return error(failure[0], failure[1], status=503)
            if not confirmed:
                return error(
                    "stored object does not match its hash",
                    "the object was written but reads back with a different digest; retry.",
                    status=503,
                )
            verified = "read-back"

        current_app.logger.info("stored %s %s (%s)", kind, key, verified)
        return {
            "stored": True,
            "kind": kind,
            "key": key,
            "split": split,
            "sha256": claimed,
            # Which guarantee actually ran. "read-back" means re-read and re-hashed; "received"
            # means verified on receipt and by the Worker/R2 checksum, without a read path on Fly.
            "verified": verified,
        }, 201


def _read_back_matches(store, key, claimed):
    """Hash the stored object in chunks. Returns (matched, failure) with one of them meaningful."""
    digest = hashlib.sha256()
    try:
        body = store.get_stream(key)
        while True:
            chunk = body.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    except StorageError as exc:
        return False, ("stored object could not be read back", str(exc))
    return hmac.compare_digest(digest.hexdigest(), claimed), None


def _already_there(error, store, kind, key, split, claimed):
    """Something is already stored under this key. Decide whether that is this same capture.

    A retry after a lost acknowledgement is the common case on a field link, and it must succeed
    rather than stranding a capture. A different object under the same id is the dangerous case and
    must not be waved through -- for a sealed capture that would be a substitution.

    Only an open image can be told apart, because only an open image can be read. For depth and for
    sealed captures the answer is a 409 a person has to look at: the bytes stay on the phone, so
    nothing is lost by refusing.
    """
    if split != "sealed":
        matched, failure = _read_back_matches(store, key, claimed)
        if failure is not None:
            return error(failure[0], failure[1], status=503)
        if matched:
            # Idempotent: the earlier upload landed and only its acknowledgement was lost.
            return {
                "stored": True, "kind": kind, "key": key, "split": split,
                "sha256": claimed, "verified": "read-back",
            }, 200
        return error(
            "a different object is already stored under this capture id",
            f"{key} exists with a different digest; it was not overwritten.",
            status=409,
        )
    return error(
        "an object is already stored under this capture id",
        f"{key} exists and cannot be compared from here (sealed captures are not read); "
        "it was not overwritten.",
        status=409,
    )
