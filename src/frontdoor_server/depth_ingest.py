"""Client for the isolated depth-ingest Worker (TICK-250, #217)."""

import http.client
import json
import os
from dataclasses import dataclass
from typing import BinaryIO
from urllib.parse import quote, urlsplit


class DepthIngestError(Exception):
    """The Worker could not safely accept a depth object."""


class DepthIngestConflict(DepthIngestError):
    """The Worker refused to overwrite an existing depth object."""


@dataclass(frozen=True)
class DepthIngestResponse:
    sha256: str

    @classmethod
    def parse(cls, raw: bytes) -> "DepthIngestResponse":
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DepthIngestError("depth-ingest Worker returned invalid JSON") from exc
        if (
                not isinstance(payload, dict)
                or set(payload) != {"sha256"}
                or not isinstance(payload["sha256"], str)
        ):
            raise DepthIngestError("depth-ingest Worker returned an invalid response")
        return cls(sha256=payload["sha256"])


@dataclass(frozen=True)
class DepthIngestConfig:
    scheme: str
    host: str
    port: int | None
    base_path: str
    service_key: str

    @classmethod
    def from_environment(cls) -> "DepthIngestConfig":
        raw_url = os.environ.get("FRONTDOOR_DEPTH_INGEST_URL", "").strip()
        service_key = os.environ.get("FRONTDOOR_DEPTH_INGEST_KEY", "").strip()
        try:
            parsed = urlsplit(raw_url)
            port = parsed.port
        except ValueError as exc:
            raise DepthIngestError("FRONTDOOR_DEPTH_INGEST_URL is malformed") from exc
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise DepthIngestError("FRONTDOOR_DEPTH_INGEST_URL must be an http(s) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise DepthIngestError("FRONTDOOR_DEPTH_INGEST_URL must not contain credentials or a query")
        if not service_key:
            raise DepthIngestError("FRONTDOOR_DEPTH_INGEST_KEY is not set")
        return cls(parsed.scheme, parsed.hostname, port, parsed.path.rstrip("/"), service_key)


def put_depth(
        stream: BinaryIO, *, key: str, sha256: str, size: int, config: DepthIngestConfig) -> None:
    """Stream one validated depth object to the write-only HTTP capability."""
    connection_type = (
        http.client.HTTPSConnection if config.scheme == "https" else http.client.HTTPConnection
    )
    connection = connection_type(config.host, config.port, timeout=30)
    path = f"{config.base_path}/depth?key={quote(key, safe='')}"
    try:
        connection.request(
            "PUT",
            path,
            body=stream,
            headers={
                "Content-Length": str(size),
                "Content-Type": "application/octet-stream",
                "X-Frontdoor-Depth-Key": config.service_key,
                "X-Frontdoor-SHA256": sha256,
            },
        )
        response = connection.getresponse()
        response_body = response.read(4097)
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise DepthIngestError("depth-ingest Worker is unavailable") from exc
    finally:
        connection.close()

    if response.status == 409:
        raise DepthIngestConflict("depth object already exists")
    if response.status != 201:
        raise DepthIngestError(f"depth-ingest Worker returned HTTP {response.status}")
    if len(response_body) > 4096:
        raise DepthIngestError("depth-ingest Worker returned an oversized response")
    confirmation = DepthIngestResponse.parse(response_body)
    if confirmation.sha256 != sha256:
        raise DepthIngestError("depth-ingest Worker confirmed a different digest")
