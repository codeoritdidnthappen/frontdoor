"""Tests for two-bucket object storage (TICK-012, #20)."""

import os
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from frontdoor.storage import (
    PROBE_KEY,
    StorageDenied,
    StorageError,
    depth_store,
    image_store,
    load_depth_creds,
    load_image_creds,
    main,
    probe_loader_denied_depth,
    verify,
)

REPO = Path(__file__).resolve().parents[1]

IMAGES = "frontdoor-image"
DEPTH = "frontdoor-depth"


def _image_env(monkeypatch):
    monkeypatch.setenv("FRONTDOOR_S3_REGION", "us-east-1")
    monkeypatch.delenv("FRONTDOOR_S3_ENDPOINT", raising=False)
    monkeypatch.setenv("FRONTDOOR_IMAGES_BUCKET", IMAGES)
    monkeypatch.setenv("FRONTDOOR_IMAGES_ACCESS_KEY", "img-key")
    monkeypatch.setenv("FRONTDOOR_IMAGES_SECRET_KEY", "img-secret")


def _depth_env(monkeypatch):
    monkeypatch.setenv("FRONTDOOR_DEPTH_BUCKET", DEPTH)
    monkeypatch.setenv("FRONTDOOR_DEPTH_ACCESS_KEY", "dep-key")
    monkeypatch.setenv("FRONTDOOR_DEPTH_SECRET_KEY", "dep-secret")


def _both_env(monkeypatch):
    _image_env(monkeypatch)
    _depth_env(monkeypatch)


def _create_buckets():
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket=IMAGES)
    client.create_bucket(Bucket=DEPTH)
    return client


def test_env_example_lists_both_credential_sets_and_no_secrets():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    for key in (
        "FRONTDOOR_S3_ENDPOINT",
        "FRONTDOOR_IMAGES_BUCKET",
        "FRONTDOOR_IMAGES_ACCESS_KEY",
        "FRONTDOOR_IMAGES_SECRET_KEY",
        "FRONTDOOR_DEPTH_BUCKET",
        "FRONTDOOR_DEPTH_ACCESS_KEY",
        "FRONTDOOR_DEPTH_SECRET_KEY",
    ):
        assert key in text
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        if name.endswith("_KEY"):
            assert value == ""


def test_storage_layout_doc_names_two_buckets():
    text = (REPO / "data" / "STORAGE.md").read_text(encoding="utf-8")
    assert "frontdoor-image" in text
    assert "frontdoor-depth" in text
    assert "10 GB" in text
    assert "python -m frontdoor.storage verify" in text


def test_changes_log_records_the_provider():
    text = (REPO / "CHANGES.log").read_text(encoding="utf-8")
    assert "TICK-012" in text
    assert "Cloudflare R2" in text
    assert "frontdoor-image" in text
    assert "frontdoor-depth" in text


def test_loader_config_does_not_require_depth_credentials(monkeypatch):
    _image_env(monkeypatch)
    monkeypatch.delenv("FRONTDOOR_DEPTH_BUCKET", raising=False)
    monkeypatch.delenv("FRONTDOOR_DEPTH_ACCESS_KEY", raising=False)
    monkeypatch.delenv("FRONTDOOR_DEPTH_SECRET_KEY", raising=False)
    creds = load_image_creds()
    assert creds.bucket == IMAGES
    with pytest.raises(StorageError, match="FRONTDOOR_DEPTH_BUCKET"):
        load_depth_creds()


def test_missing_image_credential_is_an_error(monkeypatch):
    monkeypatch.delenv("FRONTDOOR_IMAGES_BUCKET", raising=False)
    with pytest.raises(StorageError, match="FRONTDOOR_IMAGES_BUCKET"):
        load_image_creds()


@mock_aws
def test_image_put_and_get_round_trip(monkeypatch):
    _image_env(monkeypatch)
    _create_buckets()
    store = image_store()
    store.put("cap-1", b"jpeg-bytes")
    assert store.get("cap-1") == b"jpeg-bytes"


@mock_aws
def test_harness_reads_depth_that_the_loader_wrote_to_the_depth_bucket(monkeypatch):
    _both_env(monkeypatch)
    _create_buckets()
    depth_store().put("cap-1", b"depth-bytes")
    assert depth_store().get("cap-1") == b"depth-bytes"


@mock_aws
def test_unknown_capture_is_an_error(monkeypatch):
    _image_env(monkeypatch)
    _create_buckets()
    with pytest.raises(StorageError):
        image_store().get("missing")


@mock_aws
def test_verify_fails_when_loader_can_read_depth(monkeypatch):
    """moto does not enforce per-token bucket scope, so verify must go red here.

    The live check (FRONTDOOR_STORAGE_LIVE=1) is the one that proves the
    provider denies the loader. This test proves verify does not silently
    pass when the deny is missing.
    """
    _both_env(monkeypatch)
    _create_buckets()
    with pytest.raises(StorageError, match="not denied on the depth bucket"):
        verify()


def test_cli_usage(capsys):
    assert main([]) == 2
    assert "verify" in capsys.readouterr().err


def test_cli_reports_missing_env(monkeypatch, capsys):
    for name in list(os.environ):
        if name.startswith("FRONTDOOR_"):
            monkeypatch.delenv(name, raising=False)
    assert main(["verify"]) == 1
    assert "missing" in capsys.readouterr().err


@pytest.mark.skipif(
    not os.environ.get("FRONTDOOR_STORAGE_LIVE"),
    reason="live storage not configured",
)
def test_live_loader_credential_is_denied_on_depth():
    images = image_store()
    depth = depth_store()
    depth.put(PROBE_KEY, b"secret-depth")
    try:
        with pytest.raises(StorageDenied):
            probe_loader_denied_depth(images.creds, depth.creds.bucket)
        images.put(PROBE_KEY, b"public-image")
        assert images.get(PROBE_KEY) == b"public-image"
    finally:
        try:
            images.delete(PROBE_KEY)
        except StorageError:
            pass
        try:
            depth.delete(PROBE_KEY)
        except StorageError:
            pass
