"""Tests for SEAL_AUDIT.log (TICK-071, #54)."""

import json
import subprocess

import pytest

from frontdoor.manifest import manifest_sha256
from frontdoor.seal_audit import SealAuditError, record_unsealing
from tests.test_eval import _three_captures
from tests.test_gitignore import REPO_ROOT


def test_seal_audit_log_is_not_gitignored():
    result = subprocess.run(
        ["git", "check-ignore", "-q", "SEAL_AUDIT.log"],
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 1


def test_include_sealed_appends_one_well_formed_line(tmp_path, monkeypatch):
    manifest, _, _ = _three_captures(tmp_path)
    audit = tmp_path / "SEAL_AUDIT.log"
    monkeypatch.setattr("frontdoor.seal_audit._working_tree_dirty", lambda repo: False)
    monkeypatch.setattr("frontdoor.seal_audit._git_commit", lambda repo: "b" * 40)
    monkeypatch.setattr("frontdoor.seal_audit._operator", lambda: "qa-operator")
    argv = ["python", "-m", "frontdoor.eval", "--include-sealed"]
    record_unsealing(
        argv=argv,
        manifest_path=manifest,
        audit_path=audit,
        repo=tmp_path,
    )
    lines = audit.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    ts, commit, digest, operator, argv_json = lines[0].split("\t")
    assert ts.endswith("Z")
    assert commit == "b" * 40
    assert digest == manifest_sha256(manifest)
    assert operator == "qa-operator"
    assert json.loads(argv_json) == argv


def test_second_unsealing_appends_without_rewriting(tmp_path, monkeypatch):
    manifest, _, _ = _three_captures(tmp_path)
    audit = tmp_path / "SEAL_AUDIT.log"
    monkeypatch.setattr("frontdoor.seal_audit._working_tree_dirty", lambda repo: False)
    monkeypatch.setattr("frontdoor.seal_audit._git_commit", lambda repo: "c" * 40)
    monkeypatch.setattr("frontdoor.seal_audit._operator", lambda: "qa-operator")
    record_unsealing(
        argv=["first"],
        manifest_path=manifest,
        audit_path=audit,
        repo=tmp_path,
    )
    first = audit.read_text(encoding="utf-8")
    record_unsealing(
        argv=["second"],
        manifest_path=manifest,
        audit_path=audit,
        repo=tmp_path,
    )
    text = audit.read_text(encoding="utf-8")
    assert text.startswith(first)
    assert len(text.splitlines()) == 2
    assert "second" in text.splitlines()[1]


def test_dirty_tree_aborts_before_append(tmp_path, monkeypatch):
    manifest, _, _ = _three_captures(tmp_path)
    audit = tmp_path / "SEAL_AUDIT.log"
    monkeypatch.setattr("frontdoor.seal_audit._working_tree_dirty", lambda repo: True)
    with pytest.raises(SealAuditError, match="dirty"):
        record_unsealing(
            argv=["--include-sealed"],
            manifest_path=manifest,
            audit_path=audit,
            repo=tmp_path,
        )
    assert not audit.exists()
