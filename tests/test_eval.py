"""Tests for the evaluation harness seal (TICK-070, TICK-071)."""

import sys

import pytest

import frontdoor.eval as eval_mod
import frontdoor.seal_audit as seal_audit
import frontdoor.storage as storage
from frontdoor.eval import main


def _run_cli(monkeypatch, *args):
    """Invoke main exactly as the `__main__` block does.

    `from_cli=True` is the permission only that block passes. Setting `sys.argv` and calling
    `main()` — which is what a notebook would do, and what this helper used to do — is refused;
    `test_a_notebook_cannot_unseal_however_it_shapes_the_call` is the test for that.
    """
    monkeypatch.setattr(sys, "argv", ["frontdoor.eval", *args])
    return main(from_cli=True)
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


class _FakeStore:
    """Stands in for ObjectStore, and enforces the seal the same way it does."""

    def __init__(self, get_image):
        self._get_image = get_image

    def get(self, key, *, allow_sealed=False):
        if key.startswith(storage.SEALED_PREFIX) and not allow_sealed:
            raise storage.StorageDenied(f"{key!r} is sealed")
        capture_id = key.split("/", 1)[1]
        return self._get_image(capture_id)


def _point_harness(monkeypatch, tmp_path, manifest, sidecar_dir, get_image):
    monkeypatch.setattr(eval_mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(eval_mod, "MANIFEST", manifest)
    monkeypatch.setattr(eval_mod, "SIDECARS", sidecar_dir)
    monkeypatch.setattr(eval_mod, "AUDIT_LOG", tmp_path / "SEAL_AUDIT.log")
    # Intercept at the store, not at a loader argument. eval used to inject a
    # capture_id-keyed getter, which walked straight past the partitioned key the
    # loader now builds -- so patching that seam would have tested nothing (#182).
    monkeypatch.setattr(storage, "image_store", lambda: _FakeStore(get_image))
    monkeypatch.setattr(seal_audit, "_working_tree_dirty", lambda repo: False)
    monkeypatch.setattr(seal_audit, "_git_commit", lambda repo: "a" * 40)
    # The audit line records which bucket the run read; there is no storage in a temp repo,
    # and eval refuses rather than recording "unresolved" (review finding 8).
    monkeypatch.setattr(
        eval_mod, "_storage_config",
        lambda: {"images_bucket": "frontdoor-image", "endpoint": "default"},
    )


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
    assert _run_cli(monkeypatch, "--include-sealed") == 0
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
    assert _run_cli(monkeypatch, "--include-sealed") == 1
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
        _run_cli(monkeypatch, "--include-sealed")
    lines = (tmp_path / "SEAL_AUDIT.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert "--include-sealed" in lines[0]



def test_a_notebook_cannot_unseal_however_it_shapes_the_call(monkeypatch, tmp_path):
    """TICK-070 AC4, enforced rather than asserted.

    An earlier guard keyed on `argv is not None`, which any in-process caller walks past by setting
    sys.argv and calling main() — the exact shape a notebook uses, and the shape this file's own
    helper used. Both call shapes must be refused without the __main__ permission.
    """
    monkeypatch.setattr(sys, "argv", ["frontdoor.eval", "--include-sealed"])
    assert main() == 2, "setting sys.argv must not grant an unsealing run"
    assert main(["--include-sealed"]) == 2, "passing argv must not grant one either"
