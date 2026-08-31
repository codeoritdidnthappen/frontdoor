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

from frontdoor_server.app import RESPONSE_SCHEMA, create_app, validate_measure_response

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
    seen = {d["verdict"] for arm in arms.values() for d in arm.get("decisions", {}).values()}
    assert seen == {"pass", "fail", "abstain"}


def test_abstention_still_carries_a_measurement(client, sidecar):
    """D-009: abstain is a decision value, never a missing or null measurement."""
    arms = post_measure(client, sidecar).get_json()["arms"]
    abstaining = [
        arm
        for arm in arms.values()
        if any(d["verdict"] == "abstain" for d in arm.get("decisions", {}).values())
    ]
    assert abstaining
    for arm in abstaining:
        assert isinstance(arm["rise_in"], (int, float))
        assert arm["interval_in"]["low"] < arm["interval_in"]["high"]


def test_the_two_ada_lines_decide_independently(client, sidecar):
    """PRD section 2: 1/2 inch is primary, 1/4 inch secondary; one may abstain while the other does not."""
    arms = post_measure(client, sidecar).get_json()["arms"]
    assert any(
        arm["decisions"]["half_inch"]["verdict"] != arm["decisions"]["quarter_inch"]["verdict"]
        for arm in arms.values()
        if "decisions" in arm
    )


def test_response_round_trips_through_json(client, sidecar):
    body = post_measure(client, sidecar).get_json()
    assert json.loads(json.dumps(body)) == body


@pytest.mark.parametrize("field", ["capture_id", "ground_truth", "split", "intrinsics"])
def test_invalid_sidecar_returns_400_naming_the_field(client, sidecar, field):
    sidecar.pop(field)
    response = post_measure(client, sidecar)
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "sidecar failed validation"
    assert field in body["detail"]


def test_sidecar_enum_violation_returns_400(client, sidecar):
    sidecar["split"] = "test"
    response = post_measure(client, sidecar)
    assert response.status_code == 400
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
    body["arms"]["A"]["decisions"]["half_inch"]["verdict"] = "probably fine"
    with pytest.raises(ValidationError):
        Draft202012Validator(RESPONSE_SCHEMA).validate(body)


# --- TICK-222: an abstain must be explainable, and an absent arm must say why ---


def abstaining_decisions(arms):
    return [
        (name, line, decision)
        for name, arm in arms.items()
        for line, decision in arm.get("decisions", {}).items()
        if decision["verdict"] == "abstain"
    ]


def test_every_abstain_carries_a_renderable_explanation(client, sidecar):
    """TICK-211 AC4: an abstention renders as a first-class outcome, never a blank."""
    found = abstaining_decisions(post_measure(client, sidecar).get_json()["arms"])
    assert found, "the stub must exercise abstain so TICK-063 has something to render"
    for name, line, decision in found:
        assert decision["explanation"].strip(), f"{name}/{line} abstains with no explanation"


def test_schema_requires_an_explanation_on_abstain(client, sidecar):
    """The contract enforces this, not just the stub — a client can rely on the field existing."""
    body = post_measure(client, sidecar).get_json()
    name, line, _ = abstaining_decisions(body["arms"])[0]
    del body["arms"][name]["decisions"][line]["explanation"]
    with pytest.raises(ValidationError):
        validate_measure_response(body)


def test_explanation_is_optional_on_pass_and_fail(client, sidecar):
    """Decided and stated: required on abstain, optional otherwise. Both forms must validate."""
    body = post_measure(client, sidecar).get_json()
    validate_measure_response(body)
    body["arms"]["A"]["decisions"]["half_inch"]["explanation"] = "0.11 in clears the 1/2 in line."
    validate_measure_response(body)


def test_an_empty_explanation_is_rejected(client, sidecar):
    body = post_measure(client, sidecar).get_json()
    name, line, _ = abstaining_decisions(body["arms"])[0]
    body["arms"][name]["decisions"][line]["explanation"] = ""
    with pytest.raises(ValidationError):
        validate_measure_response(body)


@pytest.mark.parametrize("reason", ["cut", "failed", "unavailable"])
def test_an_arm_can_state_why_it_is_absent(client, sidecar, reason):
    """TICK-063 must tell a cut arm from a failed one from one this deployment does not serve."""
    body = post_measure(client, sidecar).get_json()
    body["arms"]["C"] = {"absent_reason": reason, "detail": "recorded for the client to render"}
    validate_measure_response(body)


def test_an_absent_arm_needs_a_reason(client, sidecar):
    body = post_measure(client, sidecar).get_json()
    body["arms"]["C"] = {"detail": "no reason given"}
    with pytest.raises(ValidationError):
        validate_measure_response(body)


def test_an_arm_cannot_be_half_result_half_absence(client, sidecar):
    body = post_measure(client, sidecar).get_json()
    body["arms"]["C"]["absent_reason"] = "cut"
    with pytest.raises(ValidationError):
        validate_measure_response(body)


def test_every_arm_key_is_required(client, sidecar):
    """Omitting an arm is what made absence ambiguous; the contract no longer allows it."""
    body = post_measure(client, sidecar).get_json()
    del body["arms"]["C"]
    with pytest.raises(ValidationError):
        validate_measure_response(body)


# --- TICK-223: the schema must not admit impossible numbers ---


def test_the_stub_passes_full_contract_validation(client, sidecar):
    """Regression: the cross-field rules must not reject the stub's own four arms."""
    validate_measure_response(post_measure(client, sidecar).get_json())


def test_a_negative_rise_is_rejected(client, sidecar):
    body = post_measure(client, sidecar).get_json()
    body["arms"]["A"]["rise_in"] = -0.11
    body["arms"]["A"]["interval_in"] = {"low": -0.2, "high": 0.1}
    with pytest.raises(ValidationError):
        validate_measure_response(body)


def test_an_inverted_interval_is_rejected(client, sidecar):
    body = post_measure(client, sidecar).get_json()
    body["arms"]["B"]["interval_in"] = {"low": 0.57, "high": 0.31}
    with pytest.raises(ValidationError) as exc:
        validate_measure_response(body)
    assert "inverted" in str(exc.value)


@pytest.mark.parametrize("rise", [0.05, 0.99])
def test_a_rise_outside_its_own_interval_is_rejected(client, sidecar, rise):
    """The interval is the project's claim about its own uncertainty; a point estimate outside it
    makes every D-009 decision derived from the pair meaningless."""
    body = post_measure(client, sidecar).get_json()
    body["arms"]["B"]["rise_in"] = rise
    with pytest.raises(ValidationError) as exc:
        validate_measure_response(body)
    assert "outside its own interval" in str(exc.value)


def test_a_rise_exactly_on_an_interval_bound_is_accepted(client, sidecar):
    """The bounds are inclusive — a rise sitting on its own limit is legitimate, not an error."""
    body = post_measure(client, sidecar).get_json()
    for rise in (body["arms"]["B"]["interval_in"]["low"], body["arms"]["B"]["interval_in"]["high"]):
        body["arms"]["B"]["rise_in"] = rise
        validate_measure_response(body)


def test_cross_field_rules_skip_absent_arms(client, sidecar):
    """An absent arm has no interval to check; the validator must not trip over it."""
    body = post_measure(client, sidecar).get_json()
    body["arms"]["B"] = {"absent_reason": "failed"}
    validate_measure_response(body)


def test_a_whitespace_only_explanation_is_rejected(client, sidecar):
    """minLength alone would accept "   ", which renders as the blank TICK-222 exists to prevent."""
    body = post_measure(client, sidecar).get_json()
    name, line, _ = abstaining_decisions(body["arms"])[0]
    body["arms"][name]["decisions"][line]["explanation"] = "   "
    with pytest.raises(ValidationError):
        validate_measure_response(body)


def test_a_whitespace_only_absence_detail_is_rejected(client, sidecar):
    body = post_measure(client, sidecar).get_json()
    body["arms"]["C"] = {"absent_reason": "cut", "detail": " "}
    with pytest.raises(ValidationError):
        validate_measure_response(body)


def test_cross_field_errors_name_the_offending_arm(client, sidecar):
    """A caller reporting exc.json_path must locate a cross-field fault as precisely as a schema one."""
    body = post_measure(client, sidecar).get_json()
    body["arms"]["B"]["rise_in"] = 0.99
    with pytest.raises(ValidationError) as exc:
        validate_measure_response(body)
    assert exc.value.json_path == "$.arms.B.rise_in"

    body = post_measure(client, sidecar).get_json()
    body["arms"]["B"]["interval_in"] = {"low": 0.57, "high": 0.31}
    with pytest.raises(ValidationError) as exc:
        validate_measure_response(body)
    assert exc.value.json_path == "$.arms.B.interval_in"


def test_a_malformed_arm_names_the_field_that_is_wrong(client, sidecar):
    """The discriminated union must not degrade to "not valid under any of the given schemas"."""
    body = post_measure(client, sidecar).get_json()
    body["arms"]["A"]["interval"] = body["arms"]["A"].pop("interval_in")
    with pytest.raises(ValidationError) as exc:
        validate_measure_response(body)
    assert "interval_in" in exc.value.message
