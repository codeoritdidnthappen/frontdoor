"""Tests for SEAL_AUDIT.log (TICK-071, #54)."""

import json
import subprocess

import pytest

from frontdoor.manifest import manifest_sha256
from frontdoor.seal_audit import (
    AUDIT_FIELDS,
    AUDIT_KEYS,
    SealAuditError,
    record_unsealing,
    validate_audit_mapping,
)
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
            config={"images_bucket": "frontdoor-image", "endpoint": "default"},
    )
    lines = audit.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    fields = lines[0].split("\t")
    # Field order is AUDIT_FIELDS, which ARCHITECTURE.md section 7 documents. Asserting against the
    # constant rather than a literal count keeps the log and the documentation from drifting.
    assert len(fields) == len(AUDIT_FIELDS)
    record = dict(zip(AUDIT_FIELDS, fields))
    assert record["utc_timestamp"].endswith("Z")
    assert record["commit_sha"] == "b" * 40
    assert record["manifest_sha256"] == manifest_sha256(manifest)
    assert record["operator"] == "qa-operator"
    assert json.loads(record["command_line"]) == argv
    # The resolved storage configuration is recorded because .env is gitignored and selects the
    # image bucket, so a clean tree alone does not mean two runs read the same bytes.
    assert set(json.loads(record["resolved_config"])) == {"images_bucket", "endpoint"}


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
            config={"images_bucket": "frontdoor-image", "endpoint": "default"},
    )
    first = audit.read_text(encoding="utf-8")
    record_unsealing(
        argv=["second"],
        manifest_path=manifest,
        audit_path=audit,
        repo=tmp_path,
            config={"images_bucket": "frontdoor-image", "endpoint": "default"},
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
            config={"images_bucket": "frontdoor-image", "endpoint": "default"},
        )
    assert not audit.exists()


def test_an_unwritable_audit_log_refuses_instead_of_raising_a_traceback(tmp_path, monkeypatch):
    """An unsealing run that cannot be recorded must not happen (QA B09)."""
    manifest, _, _ = _three_captures(tmp_path)
    audit = tmp_path / "SEAL_AUDIT.log"
    audit.write_text("", encoding="utf-8")
    audit.chmod(0o444)
    monkeypatch.setattr("frontdoor.seal_audit._working_tree_dirty", lambda repo: False)
    monkeypatch.setattr("frontdoor.seal_audit._git_commit", lambda repo: "d" * 40)
    try:
        with pytest.raises(SealAuditError, match="cannot append to the audit log"):
            record_unsealing(
                argv=["python", "-m", "frontdoor.eval", "--include-sealed"],
                manifest_path=manifest, audit_path=audit, repo=tmp_path,
            config={"images_bucket": "frontdoor-image", "endpoint": "default"},
            )
    finally:
        audit.chmod(0o644)


def test_a_non_git_tree_refuses_instead_of_raising_a_traceback(tmp_path):
    """The harness can be pointed at a directory that is not a checkout (QA B05, B09)."""
    manifest, _, _ = _three_captures(tmp_path)
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    with pytest.raises(SealAuditError, match="working tree|commit SHA"):
        record_unsealing(
            argv=["python", "-m", "frontdoor.eval", "--include-sealed"],
            manifest_path=manifest, audit_path=plain / "SEAL_AUDIT.log", repo=plain,
            config={"images_bucket": "frontdoor-image", "endpoint": "default"},
        )


def test_the_command_line_is_reconstructable(tmp_path, monkeypatch):
    """An absolute path to eval.py is not a command anyone can re-run (QA B07)."""
    manifest, _, _ = _three_captures(tmp_path)
    audit = tmp_path / "SEAL_AUDIT.log"
    monkeypatch.setattr("frontdoor.seal_audit._working_tree_dirty", lambda repo: False)
    monkeypatch.setattr("frontdoor.seal_audit._git_commit", lambda repo: "e" * 40)
    record_unsealing(
        argv=["/abs/path/to/src/frontdoor/eval.py", "--include-sealed"],
        manifest_path=manifest, audit_path=audit, repo=tmp_path,
            config={"images_bucket": "frontdoor-image", "endpoint": "default"},
    )
    fields = dict(zip(AUDIT_FIELDS, audit.read_text(encoding="utf-8").splitlines()[0].split("\t")))
    assert json.loads(fields["command_line"])[0] == "python -m frontdoor.eval"


def test_audit_keys_are_exactly_record_unsealing_parameters():
    """The mapping contract lives next to the signature it mirrors; equality (not subset) so a
    new record_unsealing parameter cannot be added without extending AUDIT_KEYS too."""
    import inspect

    params = [p for p in inspect.signature(record_unsealing).parameters if p != "argv"]
    assert params == list(AUDIT_KEYS)


def test_validate_audit_mapping_names_every_missing_key():
    with pytest.raises(SealAuditError, match=r"missing \['audit_path', 'config'\]"):
        validate_audit_mapping({"manifest_path": "m", "repo": "r"})


def test_validate_audit_mapping_returns_a_complete_mapping():
    audit = {key: object() for key in AUDIT_KEYS}
    assert validate_audit_mapping(audit) is audit


def test_a_missing_repo_directory_is_named_rather_than_blamed_on_git(tmp_path):
    """cwd= raises FileNotFoundError for a missing dir, same as a missing git binary (review 7)."""
    manifest, _, _ = _three_captures(tmp_path)
    with pytest.raises(SealAuditError, match="is not a directory"):
        record_unsealing(
            argv=["python", "-m", "frontdoor.eval", "--include-sealed"],
            manifest_path=manifest,
            audit_path=tmp_path / "SEAL_AUDIT.log",
            repo=tmp_path / "no-such-dir",
            config={"images_bucket": "frontdoor-image", "endpoint": "default"},
        )


