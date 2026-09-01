"""Contract tests for POST /measure and GET /health (TICK-060, #48).

These are contract tests, not stub tests: TICK-061 replaces the stub with real metrology behind
the same shape and every assertion here that is not explicitly about placeholder values must still
hold. That is the reason for writing them now rather than with the implementation.
"""

import io
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from frontdoor_server.app import RESPONSE_SCHEMA, create_app

REPO_ROOT = Path(__file__).resolve().parents[1]


def architecture_example():
    """The verbatim sidecar example from ARCHITECTURE.md section 4."""
    text = (REPO_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    block = re.search(r"```json\n(.*?)```", text, re.DOTALL)
    assert block, "no ```json block found in ARCHITECTURE.md"
    return json.loads(block.group(1))


@pytest.fixture
def client():
    return create_app().test_client()


@pytest.fixture
def sidecar():
    return architecture_example()


def post_measure(client, sidecar=None, image=b"not-a-real-jpeg", omit=()):
    data = {}
    if "image" not in omit:
        data["image"] = (io.BytesIO(image), "capture.jpg")
    if "sidecar" not in omit:
        data["sidecar"] = sidecar if isinstance(sidecar, str) else json.dumps(sidecar)
    return client.post("/measure", data=data, content_type="multipart/form-data")


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_response_schema_is_itself_valid():
    Draft202012Validator.check_schema(RESPONSE_SCHEMA)


def test_valid_request_matches_the_committed_schema(client, sidecar):
    response = post_measure(client, sidecar)
    assert response.status_code == 200
    Draft202012Validator(RESPONSE_SCHEMA).validate(response.get_json())


def test_capture_id_is_echoed(client, sidecar):
    body = post_measure(client, sidecar).get_json()
    assert body["capture_id"] == sidecar["capture_id"]


def test_stub_output_is_flagged_as_a_stub(client, sidecar):
    assert post_measure(client, sidecar).get_json()["stub"] is True


def test_primary_arm_is_always_present(client, sidecar):
    assert "A" in post_measure(client, sidecar).get_json()["arms"]


def test_every_decision_value_is_representable(client, sidecar):
    """TICK-063 needs all three render states, and abstain has to be reachable at both lines."""
    arms = post_measure(client, sidecar).get_json()["arms"]
    seen = {d for arm in arms.values() for d in arm["decisions"].values()}
    assert seen == {"pass", "fail", "abstain"}


def test_abstention_still_carries_a_measurement(client, sidecar):
    """D-009: abstain is a decision value, never a missing or null measurement."""
    arms = post_measure(client, sidecar).get_json()["arms"]
    abstaining = [
        arm for arm in arms.values() if "abstain" in arm["decisions"].values()
    ]
    assert abstaining
    for arm in abstaining:
        assert isinstance(arm["rise_in"], float)
        assert arm["interval_in"]["low"] < arm["interval_in"]["high"]


def test_the_two_ada_lines_decide_independently(client, sidecar):
    """PRD section 2: 1/2 inch is primary, 1/4 inch secondary; one may abstain while the other does not."""
    arms = post_measure(client, sidecar).get_json()["arms"]
    assert any(
        arm["decisions"]["half_inch"] != arm["decisions"]["quarter_inch"]
        for arm in arms.values()
    )


def test_response_round_trips_through_json(client, sidecar):
    body = post_measure(client, sidecar).get_json()
    assert json.loads(json.dumps(body)) == body


@pytest.mark.parametrize("field", ["capture_id", "ground_truth", "split", "intrinsics"])
def test_invalid_sidecar_returns_422_naming_the_field(client, sidecar, field):
    sidecar.pop(field)
    response = post_measure(client, sidecar)
    assert response.status_code == 422
    body = response.get_json()
    assert body["error"] == "sidecar failed validation"
    assert field in body["detail"]


def test_sidecar_enum_violation_returns_422(client, sidecar):
    sidecar["split"] = "test"
    response = post_measure(client, sidecar)
    assert response.status_code == 422
    assert response.get_json()["field"] == "$.split"


def test_sidecar_that_is_not_json_returns_400(client):
    response = post_measure(client, sidecar="{not json")
    assert response.status_code == 400
    assert response.get_json()["error"] == "sidecar is not valid JSON"


def test_missing_image_returns_400(client, sidecar):
    response = post_measure(client, sidecar, omit=("image",))
    assert response.status_code == 400
    assert response.get_json()["error"] == "missing image"


def test_missing_sidecar_returns_400(client):
    response = post_measure(client, omit=("sidecar",))
    assert response.status_code == 400
    assert response.get_json()["error"] == "missing sidecar"


def test_schema_rejects_an_abstention_encoded_as_a_missing_measurement(client, sidecar):
    """The committed schema, not just the stub, is what forbids the null-measurement encoding."""
    body = post_measure(client, sidecar).get_json()
    body["arms"]["B"]["rise_in"] = None
    with pytest.raises(ValidationError):
        Draft202012Validator(RESPONSE_SCHEMA).validate(body)

    body["arms"]["B"].pop("rise_in")
    with pytest.raises(ValidationError):
        Draft202012Validator(RESPONSE_SCHEMA).validate(body)


def test_schema_rejects_an_unknown_decision_value(client, sidecar):
    body = post_measure(client, sidecar).get_json()
    body["arms"]["A"]["decisions"]["half_inch"] = "probably fine"
    with pytest.raises(ValidationError):
        Draft202012Validator(RESPONSE_SCHEMA).validate(body)
