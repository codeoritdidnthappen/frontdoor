"""HTTP contract tests for the #216 depth-ingest Worker client (TICK-250, #217)."""

import hashlib
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from frontdoor_server.depth_ingest import (
    DepthIngestConfig,
    DepthIngestConflict,
    DepthIngestError,
    DepthIngestRejected,
    put_depth,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class _WorkerHandler(BaseHTTPRequestHandler):
    """Recording implementation of #216's published Worker request/response contract."""

    status = 201
    received = None
    response_payload = None

    def do_PUT(self):
        length = int(self.headers["Content-Length"])
        type(self).received = {
            "path": self.path,
            "headers": self.headers,
            "body": self.rfile.read(length),
        }
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        digest = self.headers.get("X-Frontdoor-SHA256", "")
        payload = type(self).response_payload
        self.wfile.write(json.dumps({"sha256": digest} if payload is None else payload).encode())

    def log_message(self, format, *args):
        return


@pytest.fixture
def worker(monkeypatch):
    _WorkerHandler.status = 201
    _WorkerHandler.received = None
    _WorkerHandler.response_payload = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), _WorkerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("FRONTDOOR_DEPTH_INGEST_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("FRONTDOOR_DEPTH_INGEST_KEY", "worker-service-key")
    try:
        yield _WorkerHandler
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _config():
    return DepthIngestConfig.from_environment()


def test_ac_1_sends_depth_to_the_worker_with_key_digest_and_service_credential(worker):
    payload = b"depth-bytes"
    digest = hashlib.sha256(payload).hexdigest()

    put_depth(io.BytesIO(payload), key="open/cap-1", sha256=digest, size=len(payload),
              config=_config())

    assert worker.received["path"] == "/depth?key=open%2Fcap-1"
    assert worker.received["headers"]["X-Frontdoor-Depth-Key"] == "worker-service-key"
    assert worker.received["headers"]["X-Frontdoor-SHA256"] == digest
    assert worker.received["body"] == payload


def test_ac_2_accepts_the_workers_matching_digest_confirmation(worker):
    payload = b"depth-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    put_depth(io.BytesIO(payload), key="sealed/cap-2", sha256=digest, size=len(payload),
              config=_config())


def test_ac_3_maps_worker_conflict_to_a_typed_conflict(worker):
    worker.status = 409
    with pytest.raises(DepthIngestConflict):
        put_depth(io.BytesIO(b"x"), key="open/cap-1", sha256="a" * 64, size=1,
                  config=_config())


def test_tick_254_a_worker_digest_rejection_is_permanent_not_retryable(worker):
    """422 means the bytes will never match; it must not be reported as a retryable outage."""
    worker.status = 422
    with pytest.raises(DepthIngestRejected, match="did not hash"):
        put_depth(io.BytesIO(b"x"), key="open/cap-1", sha256="a" * 64, size=1,
                  config=_config())


@pytest.mark.parametrize("payload", [[], {}, {"sha256": True}, {"sha256": "a" * 64, "extra": 1}])
def test_ac_3_rejects_worker_responses_outside_the_published_schema(worker, payload):
    worker.response_payload = payload
    with pytest.raises(DepthIngestError, match="invalid response"):
        put_depth(io.BytesIO(b"x"), key="open/cap-1", sha256="a" * 64, size=1,
                  config=_config())


@pytest.mark.parametrize("url", ["https://worker:abc", "https://worker:99999", "https://[broken"])
def test_ac_5_malformed_worker_urls_raise_a_typed_configuration_error(monkeypatch, url):
    monkeypatch.setenv("FRONTDOOR_DEPTH_INGEST_URL", url)
    monkeypatch.setenv("FRONTDOOR_DEPTH_INGEST_KEY", "key")
    with pytest.raises(DepthIngestError, match="malformed"):
        DepthIngestConfig.from_environment()


@pytest.mark.parametrize("status", [400, 401, 403, 500, 503])
def test_ac_3_maps_worker_failures_to_a_retryable_failure(worker, status):
    worker.status = status
    with pytest.raises(DepthIngestError, match=f"HTTP {status}"):
        put_depth(io.BytesIO(b"x"), key="open/cap-1", sha256="a" * 64, size=1,
                  config=_config())


def test_ac_5_depth_client_needs_no_permanent_r2_write_credentials(worker, monkeypatch):
    monkeypatch.delenv("FRONTDOOR_DEPTH_WRITE_ACCESS_KEY", raising=False)
    monkeypatch.delenv("FRONTDOOR_DEPTH_WRITE_SECRET_KEY", raising=False)
    put_depth(io.BytesIO(b"x"), key="open/cap-1", sha256="a" * 64, size=1,
              config=_config())


def test_ac_6_deploy_docs_replace_permanent_depth_credentials_with_worker_config():
    deploy = (REPO_ROOT / "docs" / "server-deploy.md").read_text(encoding="utf-8")
    example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "FRONTDOOR_DEPTH_INGEST_URL" in deploy
    assert "FRONTDOOR_DEPTH_INGEST_KEY" in deploy
    assert "FRONTDOOR_DEPTH_WRITE_ACCESS_KEY" not in deploy + example
    assert "FRONTDOOR_DEPTH_WRITE_SECRET_KEY" not in deploy + example


def test_ac_7_architecture_records_the_r2_limitation_and_worker_boundary():
    architecture = (REPO_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")

    assert "permanent write-only R2 token" in architecture
    assert "dedicated authenticated Worker" in architecture
