"""Tests for the evaluation harness seal (TICK-070, TICK-071)."""

import pytest

import frontdoor.eval as eval_mod
import frontdoor.seal_audit as seal_audit
from frontdoor.eval import main
from frontdoor.loader import LoaderError
from tests.test_loader import _write_capture


def _three_captures(tmp_path):
    images = {}
    written = None
    for capture_id, entrance_id, blob in (
        ("cap-dev", "E-001", b"dev-bytes"),
        ("cap-calib", "E-042", b"calib-bytes"),
        ("cap-sealed", "E-002", b"sealed-bytes"),
    ):
        manifest, sidecar_dir, image = _write_capture(
            tmp_path, capture_id=capture_id, entrance_id=entrance_id, image=blob
        )
        images[capture_id] = image
        written = (manifest, sidecar_dir)
    return written[0], written[1], images


def _point_harness(monkeypatch, tmp_path, manifest, sidecar_dir, get_image):
    monkeypatch.setattr(eval_mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(eval_mod, "MANIFEST", manifest)
    monkeypatch.setattr(eval_mod, "SIDECARS", sidecar_dir)
    monkeypatch.setattr(eval_mod, "AUDIT_LOG", tmp_path / "SEAL_AUDIT.log")
    monkeypatch.setattr(eval_mod, "_image_getter", lambda: get_image)
    monkeypatch.setattr(seal_audit, "_working_tree_dirty", lambda repo: False)
    monkeypatch.setattr(seal_audit, "_git_commit", lambda repo: "a" * 40)


def test_eval_without_flag_reads_zero_sealed_bytes(monkeypatch, tmp_path):
    manifest, sidecar_dir, images = _three_captures(tmp_path)
    reads = []

    def get_image(capture_id):
        reads.append(capture_id)
        return images[capture_id]

    _point_harness(monkeypatch, tmp_path, manifest, sidecar_dir, get_image)
    assert main([]) == 0
    assert "cap-sealed" not in reads
    assert set(reads) == {"cap-dev", "cap-calib"}
    assert not (tmp_path / "SEAL_AUDIT.log").exists()


def test_eval_include_sealed_loads_sealed_after_audit(monkeypatch, tmp_path):
    manifest, sidecar_dir, images = _three_captures(tmp_path)
    reads = []
    audit = tmp_path / "SEAL_AUDIT.log"

    def get_image(capture_id):
        assert audit.is_file() and audit.read_text(encoding="utf-8").strip()
        reads.append(capture_id)
        return images[capture_id]

    _point_harness(monkeypatch, tmp_path, manifest, sidecar_dir, get_image)
    assert main(["--include-sealed"]) == 0
    assert reads == ["cap-calib", "cap-dev", "cap-sealed"]
    line = audit.read_text(encoding="utf-8").splitlines()
    assert len(line) == 1
    assert "--include-sealed" in line[0]


def test_eval_refuses_dirty_tree_before_any_read(monkeypatch, tmp_path):
    manifest, sidecar_dir, images = _three_captures(tmp_path)
    reads = []

    def get_image(capture_id):
        reads.append(capture_id)
        return images[capture_id]

    _point_harness(monkeypatch, tmp_path, manifest, sidecar_dir, get_image)
    monkeypatch.setattr(seal_audit, "_working_tree_dirty", lambda repo: True)
    assert main(["--include-sealed"]) == 1
    assert reads == []
    audit = tmp_path / "SEAL_AUDIT.log"
    assert not audit.exists() or audit.read_text(encoding="utf-8") == ""


def test_eval_usage(capsys):
    assert main(["--nope"]) == 2
    assert "--include-sealed" in capsys.readouterr().err


def test_harness_flag_is_not_a_function_argument():
    import inspect

    assert "include_sealed" not in inspect.signature(main).parameters


def test_crash_mid_unseal_leaves_the_audit_line(monkeypatch, tmp_path):
    manifest, sidecar_dir, _images = _three_captures(tmp_path)

    def get_image(capture_id):
        raise RuntimeError("boom")

    _point_harness(monkeypatch, tmp_path, manifest, sidecar_dir, get_image)
    with pytest.raises(LoaderError, match="boom"):
        main(["--include-sealed"])
    lines = (tmp_path / "SEAL_AUDIT.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert "--include-sealed" in lines[0]

