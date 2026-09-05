"""Reading capture images from a local directory instead of the bucket (#342).

The dataset's bytes are on the operator's Mac and the bucket holds 13 objects against 338
committed captures. Uploading is still the committed design; this removes the upload from the
EVALUATION's critical path so freeze day does not depend on a bulk transfer that has not started.

The seal is the part that has to be right. `DatasetLoader._image_bytes` hands an injected getter
the bytes before it ever reaches `storage.get`, so if this reader does not refuse a sealed
capture, nothing does.
"""

import hashlib
import json
from pathlib import Path

import pytest

from frontdoor.loader import DatasetLoader, LoaderError
from frontdoor.local_images import LocalImages
from frontdoor.storage import SealedObjectDenied

PIXELS = b"\xff\xd8\xff-not-really-a-jpeg"


def dataset(tmp_path, entrance="E-001", capture="E-001-0001", split_hint=None):
    """A one-capture dataset on disk: manifest, sidecar, and the image where the sidecar says."""
    sidecars = tmp_path / "sidecars"
    sidecars.mkdir(exist_ok=True)
    images = tmp_path / "images"
    (images / entrance).mkdir(parents=True, exist_ok=True)
    (images / entrance / "shot.jpg").write_bytes(PIXELS)
    digest = hashlib.sha256(PIXELS).hexdigest()
    # Built from a committed sidecar rather than hand-rolled: the loader validates against the
    # full schema, and a minimal stub would only ever test the validator.
    template = json.loads(
        (Path(__file__).resolve().parents[1] / "data" / "sidecars"
         / "E-001-3217.json").read_text(encoding="utf-8"))
    template["capture_id"] = capture
    template["entrance_id"] = entrance
    template["image"] = {
        **template["image"], "path": f"{entrance}/shot.jpg", "sha256": digest}
    sidecar_path = sidecars / f"{capture}.json"
    sidecar_path.write_text(json.dumps(template), encoding="utf-8")
    # The real sidecar digest, not a placeholder: the loader checks it, and a fake one made the
    # image-hash test below pass on the wrong assertion.
    sidecar_digest = hashlib.sha256(sidecar_path.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.csv"
    if not manifest.exists():
        manifest.write_text(
            "capture_id,entrance_id,image_sha256,depth_sha256,sidecar_sha256,split\n",
            encoding="utf-8")
    with manifest.open("a", encoding="utf-8") as handle:
        handle.write(
            f"{capture},{entrance},{digest},,{sidecar_digest},{split_hint or 'dev'}\n")
    return manifest, sidecars, images


def test_the_image_is_found_by_the_sidecars_own_path(tmp_path):
    """Not guessed from the capture id: a layout this code has never seen still resolves."""
    _, sidecars, images = dataset(tmp_path)
    reader = LocalImages(images, sidecars)
    assert reader.read("E-001-0001", "dev") == PIXELS


def test_a_missing_file_is_named_rather_than_silently_skipped(tmp_path):
    _, sidecars, images = dataset(tmp_path)
    (images / "E-001" / "shot.jpg").unlink()
    with pytest.raises(LoaderError, match="not in the local directory"):
        LocalImages(images, sidecars).read("E-001-0001", "dev")
    assert LocalImages(images, sidecars).missing(["E-001-0001"], "dev") == ["E-001-0001"]


def test_a_complete_directory_reports_nothing_missing(tmp_path):
    _, sidecars, images = dataset(tmp_path)
    assert LocalImages(images, sidecars).missing(["E-001-0001"], "dev") == []


# --- the seal ------------------------------------------------------------------


def test_a_sealed_capture_is_refused_on_an_ordinary_run(tmp_path):
    """The hole this reader has to close itself.

    The loader's injection seam skips `storage.get`, so a dev run pointed at a directory that
    happens to contain sealed images would otherwise read one straight off the disk.
    """
    _, sidecars, images = dataset(tmp_path)
    reader = LocalImages(images, sidecars, allow_sealed=False)
    with pytest.raises(SealedObjectDenied):
        reader.read("E-001-0001", "sealed")


def test_the_audited_run_may_read_a_sealed_capture(tmp_path):
    _, sidecars, images = dataset(tmp_path)
    reader = LocalImages(images, sidecars, allow_sealed=True)
    assert reader.read("E-001-0001", "sealed") == PIXELS


def test_the_preflight_refuses_sealed_captures_too(tmp_path):
    """Otherwise the check itself becomes the way to learn what is in the sealed split."""
    _, sidecars, images = dataset(tmp_path)
    with pytest.raises(SealedObjectDenied):
        LocalImages(images, sidecars).missing(["E-001-0001"], "sealed")


# --- the manifest still decides what the bytes must be -------------------------


def test_different_bytes_on_disk_fail_the_hash_check(tmp_path):
    """A local directory must not be a way to feed the evaluation something else."""
    manifest, sidecars, images = dataset(tmp_path)
    (images / "E-001" / "shot.jpg").write_bytes(b"different pixels entirely")
    reader = LocalImages(images, sidecars)
    plain = DatasetLoader(manifest, sidecars)
    loader = DatasetLoader(manifest, sidecars, get_image=reader.getter(plain))
    with pytest.raises(LoaderError, match="image hash mismatch"):
        loader.load("E-001-0001")


def test_matching_bytes_load_through_the_loader(tmp_path):
    manifest, sidecars, images = dataset(tmp_path)
    reader = LocalImages(images, sidecars)
    plain = DatasetLoader(manifest, sidecars)
    loader = DatasetLoader(manifest, sidecars, get_image=reader.getter(plain))
    assert loader.load("E-001-0001").image == PIXELS


# --- the sidecar is data, not an instruction -----------------------------------


@pytest.mark.parametrize("escape", ["../outside.jpg", "/etc/passwd"])
def test_a_path_that_leaves_the_directory_is_refused(tmp_path, escape):
    """A committed sidecar is still data; an absolute or climbing path would read elsewhere."""
    _, sidecars, images = dataset(tmp_path)
    sidecar = sidecars / "E-001-0001.json"
    body = json.loads(sidecar.read_text())
    body["image"]["path"] = escape
    sidecar.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(LoaderError, match="outside"):
        LocalImages(images, sidecars).read("E-001-0001", "dev")


def test_a_sidecar_naming_no_image_is_an_error(tmp_path):
    _, sidecars, images = dataset(tmp_path)
    sidecar = sidecars / "E-001-0001.json"
    sidecar.write_text(json.dumps({"capture_id": "E-001-0001", "image": {}}), encoding="utf-8")
    with pytest.raises(LoaderError, match="names no image.path"):
        LocalImages(images, sidecars).read("E-001-0001", "dev")


# --- the refusal must name the source it actually checked ----------------------


def test_a_local_run_is_not_told_the_bytes_were_never_uploaded(tmp_path, monkeypatch):
    """The bucket wording sends an operator with a mistyped directory to chase someone else's task.

    This is the same misleading-diagnosis defect that #313 fixed for the bucket path, arriving
    from the other side: two sources, one message.
    """
    from frontdoor.screening_eval import MissingCaptureObjects

    local = MissingCaptureObjects(
        ["E-001-0001"], 1, "dev",
        source="the local directory /tmp/nowhere",
        remedy="Check that /tmp/nowhere is the directory holding the capture photographs.")
    assert "local directory /tmp/nowhere" in str(local)
    assert "never uploaded" not in str(local)

    bucket = MissingCaptureObjects(["E-001-0001"], 1, "dev")
    assert "the image bucket" in str(bucket)
    assert "never uploaded" in str(bucket)
