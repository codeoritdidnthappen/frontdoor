"""What the app puts on the wire must be what the server can parse (TICK-063).

`test_measure_response_fixture.py` pins the *response*, but it builds the request with Flask's
own test client -- so the app's multipart layout is never exercised. Rename the `sidecar` part on
either side and every other test still passes, while the demo returns "missing sidecar" on stage.

So the request here is assembled from `MeasureClient.body(sidecar:image:boundary:filename:)` as
committed: the Swift literals are read out of the source and replayed as bytes. A rename in the
Swift or in the Flask handler breaks this test, which is the only reason it exists.
"""

import json
import re
from pathlib import Path

import pytest

from frontdoor_server.app import create_app

from test_sidecar_schema import architecture_example

SWIFT = (
    Path(__file__).resolve().parents[1]
    / "ios" / "FrontdoorCapture" / "Measure" / "MeasureClient.swift"
)
BOUNDARY = "TEST-BOUNDARY-0123"
FILENAME = "capture.jpg"


def swift_body_source() -> str:
    """The text of `static func body(...)`, up to the closing `return body`."""
    text = SWIFT.read_text(encoding="utf-8")
    start = text.index("static func body(")
    return text[start : text.index("return body", start)]


def request_bytes(sidecar: bytes, image: bytes) -> bytes:
    """Replay the committed Swift body-builder, statement by statement, as bytes."""
    body = b""
    seen_append = False
    for statement in re.finditer(
        r'\bappend\("((?:[^"\\]|\\.)*)"\)|\bbody\.append\((sidecar|image)\)',
        swift_body_source(),
    ):
        literal, variable = statement.group(1), statement.group(2)
        if variable is not None:
            body += sidecar if variable == "sidecar" else image
            continue
        seen_append = True
        body += (
            literal.replace("\\r", "\r")
            .replace("\\n", "\n")
            .replace('\\"', '"')
            .replace("\\(boundary)", BOUNDARY)
            .replace("\\(filename)", FILENAME)
        ).encode("utf-8")
    assert seen_append, f"no body-building statements found in {SWIFT.name}"
    return body


def test_the_apps_own_request_layout_is_one_the_server_accepts():
    body = request_bytes(json.dumps(architecture_example()).encode("utf-8"), b"\xff\xd8\xff\xe0jpeg")
    response = create_app().test_client().post(
        "/measure",
        data=body,
        content_type=f"multipart/form-data; boundary={BOUNDARY}",
    )
    assert response.status_code == 200, response.data
    assert response.get_json()["stub"] is True


@pytest.mark.parametrize("part", ["sidecar", "image"])
def test_the_layout_actually_carries_both_parts(part):
    """Guards the replay itself: a body missing a part must be rejected, not quietly accepted."""
    sidecar = json.dumps(architecture_example()).encode("utf-8")
    body = request_bytes(b"" if part == "sidecar" else sidecar, b"" if part == "image" else b"jpeg")
    body = body.replace(f'name="{part}"'.encode("utf-8"), b'name="unexpected"')
    response = create_app().test_client().post(
        "/measure",
        data=body,
        content_type=f"multipart/form-data; boundary={BOUNDARY}",
    )
    assert response.status_code == 400, response.data
