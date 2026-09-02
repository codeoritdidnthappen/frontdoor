"""POST /upload -- capture ingest from the phone (TICK-029, #33).

Bytes go phone -> server -> bucket, never phone -> bucket. No R2 credential ships inside the
capture app: a free-provisioning build is installed on several phones, and the images token can
also READ sealed captures (data/STORAGE.md), so a token in an IPA widens the seal's exposure to
anyone holding a build. The server holds read+write on the image bucket and, per D-033,
**write-only** on the depth bucket.

What this endpoint guarantees, stated precisely because the two halves differ:

- The bytes it stores hash to the value the client claimed. A mismatch is refused with 422 and
  nothing is written, so the client retries rather than recording a phantom upload (AC4).
- For **images** it then reads the object back and re-hashes it, so "stored" means verified as
  stored, which is what lets the app delete its local copy (AC5).
- For **depth** that read-back is impossible by construction: D-033 gives the server a write-only
  token precisely so it cannot read depth. Depth is therefore verified on receipt and trusted to
  the provider thereafter. This is a real difference in strength and is not papered over -- the
  response says which check ran, in `verified`.
"""

import hashlib
import hmac
import os

from flask import Blueprint, current_app, request

from frontdoor.storage import (
    SPLITS,
    StorageError,
    depth_write_store,
    image_store,
    storage_key,
)

upload_page = Blueprint("upload", __name__)

KINDS = ("image", "depth")

#: Hex SHA-256, lowercase. Anchored, so a value with anything around it is rejected rather than
#: partially matched -- the same anchoring bug TICK-228 fixed in the sidecar schema.
_SHA256_LEN = 64


def _client_key():
    """The shared secret, or None when unset.

    Unset means the endpoint refuses every request rather than running open. An ingest path that
    silently accepts anonymous writes into the dataset bucket is worse than one that is switched
    off, and a misconfigured deploy should fail loudly on the first upload, not quietly accept
    strangers' bytes.
    """
    value = os.environ.get("FRONTDOOR_UPLOAD_KEY", "").strip()
    return value or None


def _authorised(presented):
    expected = _client_key()
    if expected is None or not presented:
        return False
    # Constant-time: the comparison is against a shared secret, and a timing oracle on it would
    # hand out write access to the dataset bucket.
    return hmac.compare_digest(presented, expected)


def _is_sha256(value):
    if len(value) != _SHA256_LEN:
        return False
    return all(c in "0123456789abcdef" for c in value)


def register_upload(app, error):
    """Register POST /upload on `app`, reporting failures through the server's error contract.

    `error` is app.py's `_error`, passed in rather than imported, because importing it here would
    make app.py and this module import each other.
    """

    @app.post("/upload")
    def upload():
        if not _authorised(request.headers.get("X-Frontdoor-Upload-Key", "")):
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

        # Nothing below is coerced. Stripping or case-folding a field that decides WHERE bytes
        # land is a place where the value the client meant and the value stored can differ, and
        # `split` decides whether a capture is sealed. The client is our own app; sending the
        # exact spelling is free, so exactness costs nothing and removes the class.
        capture_id = request.form.get("capture_id", "")
        if not capture_id or capture_id != capture_id.strip():
            return error(
                "missing or padded capture_id",
                "capture_id is required, with no leading or trailing whitespace.",
                field="capture_id",
            )

        split = request.form.get("split", "")
        if split not in SPLITS:
            return error(
                "unknown split",
                f"split must be one of {', '.join(SPLITS)}; got {split!r}.",
                field="split",
            )

        # Lowercase required, not lowercased for you: the sidecar schema anchors hashes as
        # lowercase hex (TICK-228), so there is exactly one spelling of a digest in the system.
        claimed = request.form.get("sha256", "")
        if not _is_sha256(claimed):
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

        payload = request.files["bytes"].read()
        if not payload:
            return error("empty upload", "The 'bytes' part carried no data.", field="bytes")

        actual = hashlib.sha256(payload).hexdigest()
        if not hmac.compare_digest(actual, claimed):
            # Nothing is stored. A truncated or corrupted body must leave the bucket untouched, so
            # the client's retry is a first attempt rather than an overwrite of bad bytes.
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

        try:
            store = image_store() if kind == "image" else depth_write_store()
            store.put(key, payload)
        except StorageError as exc:
            # 503: the bytes were good and the client should retry. Reporting this as a client
            # error would make the app drop a capture it holds the only copy of.
            return error("could not store the object", str(exc), status=503)

        # Read-back is the stronger check, and it is available in exactly one case: an OPEN
        # image. Depth cannot be read back because D-033 deliberately gives the server a
        # write-only token. A SEALED image cannot be read back either -- ObjectStore.get refuses
        # anything under sealed/ without allow_sealed, and passing that flag here would write a
        # SEAL_AUDIT line for every upload and make unsealing a routine event, which is precisely
        # what D-007 and D-017 exist to prevent. Both fall back to verify-on-receipt, and the
        # response says which check ran rather than implying the stronger one.
        verified = "received"
        if kind == "image" and split != "sealed":
            try:
                stored = image_store().get(key)
            except StorageError as exc:
                return error("stored object could not be read back", str(exc), status=503)
            if not hmac.compare_digest(hashlib.sha256(stored).hexdigest(), claimed):
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
            "sha256": claimed,
            # Which guarantee actually ran. "read-back" means re-read and re-hashed; "received"
            # means verified on receipt only, which is all a write-only depth token permits (D-033).
            "verified": verified,
        }, 201
