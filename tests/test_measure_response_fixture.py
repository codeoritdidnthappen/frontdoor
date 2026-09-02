"""The response the app decodes must be the response the server sends (TICK-063, TICK-060).

`tests/fixtures/measure_response.json` is what `POST /measure` actually returns, and the Swift
suite decodes that exact file. Committing it is what stops the two sides drifting into agreeing
with themselves: the client would keep parsing a shape it invented, the server would keep sending
one nobody parses, and the disagreement would surface on stage.

Regenerated here rather than by hand, so the fixture cannot go stale while still passing.
"""

import io
import json
from pathlib import Path

import pytest

from frontdoor_server.app import create_app, validate_measure_response

from test_sidecar_schema import architecture_example

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "measure_response.json"


@pytest.fixture
def live_response():
    client = create_app().test_client()
    response = client.post(
        "/measure",
        data={
            "sidecar": json.dumps(architecture_example()),
            "image": (io.BytesIO(b"jpeg"), "c.jpg"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200, response.data
    return response.get_json()


def test_the_committed_fixture_is_what_the_server_still_sends(live_response):
    committed = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert committed == live_response, (
        "tests/fixtures/measure_response.json is stale. The Swift client decodes this file; "
        "regenerate it when the response shape changes, or the app is being tested against a "
        "response the server no longer produces."
    )


def test_the_fixture_satisfies_the_frozen_contract(live_response):
    """Including the two cross-field rules JSON Schema cannot express."""
    validate_measure_response(live_response)


def test_every_arm_is_a_result_or_a_stated_absence(live_response):
    """TICK-222: a client is never left guessing whether an arm was cut, failed, or is
    unavailable here."""
    for name, arm in live_response["arms"].items():
        if "absent_reason" in arm:
            assert arm["absent_reason"] in {"cut", "failed", "unavailable"}, name
        else:
            assert "rise_in" in arm and "interval_in" in arm and "decisions" in arm, name


def test_the_stub_flag_is_present_so_the_app_can_surface_it(live_response):
    """A placeholder rendered like a measurement is the most damaging thing the demo could show."""
    assert live_response["stub"] is True


def _error_cases(client):
    import io

    return {
        "missing image": client.post(
            "/measure", data={"sidecar": "{}"}, content_type="multipart/form-data"),
        "missing sidecar": client.post(
            "/measure", data={"image": (io.BytesIO(b"j"), "c.jpg")},
            content_type="multipart/form-data"),
        "sidecar is not valid JSON": client.post(
            "/measure", data={"sidecar": "not json", "image": (io.BytesIO(b"j"), "c.jpg")},
            content_type="multipart/form-data"),
        "sidecar failed validation": client.post(
            "/measure",
            data={"sidecar": json.dumps({"capture_id": "x"}),
                  "image": (io.BytesIO(b"j"), "c.jpg")},
            content_type="multipart/form-data"),
        "no such endpoint": client.get("/nope"),
        "wrong method for this endpoint": client.get("/measure"),
    }


def test_the_error_fixture_is_what_the_server_still_returns():
    """The Swift client decodes this file to learn the error tokens.

    It read a `message` key the contract never had, so every 4xx and 5xx rendered "no explanation
    given" and the retryable-versus-not distinction was discarded. Hand-written fixtures could not
    catch that: the parser and the fixture came from the same wrong assumption. These are captured
    from the endpoint.
    """
    client = create_app().test_client()
    live = {
        name: {"status": r.status_code, "body": r.get_json()}
        for name, r in _error_cases(client).items()
    }
    committed = json.loads(
        (FIXTURE.parent / "measure_errors.json").read_text(encoding="utf-8"))
    assert committed == live, "tests/fixtures/measure_errors.json is stale; regenerate it"


def test_no_error_response_carries_a_message_key():
    """The key the client used to look for. Asserted so the mistake cannot quietly return."""
    client = create_app().test_client()
    for name, response in _error_cases(client).items():
        body = response.get_json()
        assert "message" not in body, name
        assert {"error", "detail"} <= set(body), name
