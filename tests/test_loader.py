"""Tests for the hash-verifying dataset loader (TICK-014, #22)."""

import json
import os
from pathlib import Path

import pytest
from jsonschema import ValidationError

from frontdoor.loader import Capture, LoaderError, DatasetLoader
from frontdoor.manifest import COLUMNS, append_capture
from frontdoor.split import assign_split
from test_sidecar_schema import architecture_example

HEADER = ",".join(COLUMNS) + "\n"
REPO = Path(__file__).resolve().parents[1]


def _sidecar_record(capture_id, entrance_id):
    record = architecture_example()
    record["capture_id"] = capture_id
    record["entrance_id"] = entrance_id
    record["split"] = assign_split(entrance_id)
    return record


def _write_capture(
    tmp_path,
    *,
    capture_id="cap-1",
    entrance_id="E-001",
    image=b"image-bytes",
    sidecar=None,
):
    manifest = tmp_path / "manifest.csv"
    if not manifest.exists():
        manifest.write_bytes(HEADER.encode("utf-8"))
    sidecar_dir = tmp_path / "sidecars"
    sidecar_dir.mkdir(exist_ok=True)
    record = sidecar if sidecar is not None else _sidecar_record(capture_id, entrance_id)
    sidecar_path = sidecar_dir / f"{capture_id}.json"
    sidecar_path.write_text(json.dumps(record), encoding="utf-8")
    image_path = tmp_path / f"{capture_id}.img"
    image_path.write_bytes(image)
    depth_path = tmp_path / f"{capture_id}.depth"
    depth_path.write_bytes(b"depth-not-loaded")
    append_capture(
        manifest,
        capture_id=capture_id,
        entrance_id=entrance_id,
        image_path=image_path,
        depth_path=depth_path,
        sidecar_path=sidecar_path,
    )
    return manifest, sidecar_dir, image


def test_load_returns_image_bytes_and_validated_sidecar(tmp_path):
    image = b"jpeg-payload"
    manifest, sidecar_dir, _ = _write_capture(tmp_path, image=image)
    loaded = DatasetLoader(
        manifest_path=manifest,
        sidecar_dir=sidecar_dir,
        get_image={"cap-1": image}.__getitem__,
    ).load("cap-1")
    assert isinstance(loaded, Capture)
    assert loaded.capture_id == "cap-1"
    assert loaded.entrance_id == "E-001"
    assert loaded.split == assign_split("E-001")
    assert loaded.image == image
    assert loaded.sidecar["capture_id"] == "cap-1"
    assert "depth" not in vars(loaded)


def test_corrupt_image_raises_naming_capture_and_file(tmp_path):
    image = b"original"
    manifest, sidecar_dir, _ = _write_capture(tmp_path, image=image)
    loader = DatasetLoader(
        manifest_path=manifest,
        sidecar_dir=sidecar_dir,
        get_image={"cap-1": b"tampered"}.__getitem__,
    )
    with pytest.raises(LoaderError, match="cap-1") as exc:
        loader.load("cap-1")
    assert "image" in str(exc.value).lower()


def test_corrupt_sidecar_bytes_raise_naming_capture_and_file(tmp_path):
    manifest, sidecar_dir, image = _write_capture(tmp_path)
    sidecar_path = sidecar_dir / "cap-1.json"
    sidecar_path.write_text(sidecar_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    loader = DatasetLoader(
        manifest_path=manifest,
        sidecar_dir=sidecar_dir,
        get_image={"cap-1": image}.__getitem__,
    )
    with pytest.raises(LoaderError, match="cap-1") as exc:
        loader.load("cap-1")
    assert "sidecar" in str(exc.value).lower()


def test_sidecar_missing_ground_truth_raises(tmp_path):
    record = _sidecar_record("cap-1", "E-001")
    del record["ground_truth"]
    manifest, sidecar_dir, image = _write_capture(tmp_path, sidecar=record)
    loader = DatasetLoader(
        manifest_path=manifest,
        sidecar_dir=sidecar_dir,
        get_image={"cap-1": image}.__getitem__,
    )
    with pytest.raises((LoaderError, ValidationError), match="ground_truth"):
        loader.load("cap-1")


def test_capture_absent_from_manifest_raises_without_reading_store(tmp_path):
    manifest, sidecar_dir, _ = _write_capture(tmp_path)
    calls = []

    def get_image(capture_id):
        calls.append(capture_id)
        return b"should-not-be-fetched"

    loader = DatasetLoader(
        manifest_path=manifest,
        sidecar_dir=sidecar_dir,
        get_image=get_image,
    )
    with pytest.raises(LoaderError, match="cap-missing"):
        loader.load("cap-missing")
    assert calls == []


def test_list_by_entrance_and_split_is_stable(tmp_path):
    images = {}
    written = None
    for capture_id, entrance_id, blob in (
        ("cap-b", "E-001", b"b"),
        ("cap-a", "E-001", b"a"),
        ("cap-c", "E-002", b"c"),
    ):
        manifest, sidecar_dir, image = _write_capture(
            tmp_path, capture_id=capture_id, entrance_id=entrance_id, image=blob
        )
        images[capture_id] = image
        written = (manifest, sidecar_dir)
    loader = DatasetLoader(
        manifest_path=written[0],
        sidecar_dir=written[1],
        get_image=images.__getitem__,
    )
    first = loader.list_captures(entrance_id="E-001")
    second = loader.list_captures(entrance_id="E-001")
    assert first == second == ["cap-a", "cap-b"]
    by_split = loader.list_captures(split=assign_split("E-001"))
    assert "cap-a" in by_split and "cap-b" in by_split
    assert by_split == sorted(by_split)


def test_corrupt_image_still_raises_when_skip_env_is_set(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTDOOR_SKIP_HASH", "1")
    monkeypatch.setenv("FRONTDOOR_SKIP_INTEGRITY", "1")
    image = b"original"
    manifest, sidecar_dir, _ = _write_capture(tmp_path, image=image)
    loader = DatasetLoader(
        manifest_path=manifest,
        sidecar_dir=sidecar_dir,
        get_image={"cap-1": b"tampered"}.__getitem__,
    )
    with pytest.raises(LoaderError, match="cap-1"):
        loader.load("cap-1")


def test_list_omits_sealed_rows_even_when_asked_for_that_split(tmp_path):
    images = {}
    written = None
    for capture_id, entrance_id, blob in (
        ("cap-dev", "E-001", b"dev"),
        ("cap-calib", "E-042", b"calib"),
        ("cap-sealed", "E-002", b"secret"),
    ):
        manifest, sidecar_dir, image = _write_capture(
            tmp_path, capture_id=capture_id, entrance_id=entrance_id, image=blob
        )
        images[capture_id] = image
        written = (manifest, sidecar_dir)
    loader = DatasetLoader(
        manifest_path=written[0],
        sidecar_dir=written[1],
        get_image=images.__getitem__,
    )
    assert loader.list_captures() == ["cap-calib", "cap-dev"]
    assert loader.list_captures(split="dev") == ["cap-dev"]
    assert loader.list_captures(split="calib") == ["cap-calib"]
    assert loader.list_captures(split="sealed") == []
    assert loader.list_captures(entrance_id="E-002") == []
    assert list(loader) == ["cap-calib", "cap-dev"]
    assert len(loader) == 2


def test_load_of_a_sealed_id_raises_naming_the_split_and_reads_nothing(tmp_path):
    reads = []

    def get_image(capture_id):
        reads.append(capture_id)
        return b"secret"

    manifest, sidecar_dir, _ = _write_capture(
        tmp_path, capture_id="cap-sealed", entrance_id="E-002", image=b"secret"
    )
    loader = DatasetLoader(
        manifest_path=manifest,
        sidecar_dir=sidecar_dir,
        get_image=get_image,
    )
    with pytest.raises(LoaderError, match=r"sealed.*split=sealed"):
        loader.load("cap-sealed")
    assert reads == []


def test_loader_has_no_include_sealed_switch():
    import inspect

    for target in (
        DatasetLoader.__init__,
        DatasetLoader.load,
        DatasetLoader.list_captures,
    ):
        assert "include_sealed" not in inspect.signature(target).parameters


def test_env_var_cannot_unseal_a_row(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTDOOR_INCLUDE_SEALED", "1")
    monkeypatch.setenv("INCLUDE_SEALED", "1")
    manifest, sidecar_dir, image = _write_capture(
        tmp_path, capture_id="cap-sealed", entrance_id="E-002", image=b"secret"
    )
    loader = DatasetLoader(
        manifest_path=manifest,
        sidecar_dir=sidecar_dir,
        get_image={"cap-sealed": image}.__getitem__,
    )
    with pytest.raises(LoaderError, match="sealed"):
        loader.load("cap-sealed")
    assert loader.list_captures() == []



@pytest.mark.skipif(
    not os.environ.get("FRONTDOOR_STORAGE_LIVE"),
    reason="live storage not configured",
)
def test_live_load_one_capture_from_the_image_bucket():
    from frontdoor.storage import image_store

    rows = (REPO / "data" / "manifest.csv").read_text(encoding="utf-8").splitlines()
    if len(rows) < 2:
        pytest.skip("manifest has no captures yet")
    capture_id = rows[1].split(",")[0]
    loaded = DatasetLoader(
        manifest_path=REPO / "data" / "manifest.csv",
        sidecar_dir=REPO / "data" / "sidecars",
        get_image=image_store().get,
    ).load(capture_id)
    assert loaded.capture_id == capture_id
    assert loaded.image
    assert loaded.sidecar["capture_id"] == capture_id
