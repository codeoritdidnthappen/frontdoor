"""Contract tests for the POST /measure error body (TICK-224, #112).

Success responses are covered in test_measure_endpoint.py. This module freezes the
failure half of the contract TICK-063 codes against: schema, status-to-class mapping,
and the bound on detail.
"""

import json

import pytest
from jsonschema import Draft202012Validator, ValidationError

from frontdoor_server.app import (
    DETAIL_MAX_LENGTH,
    ERROR_SCHEMA,
    ERROR_STATUSES,
    create_app,
)

from test_measure_endpoint import architecture_example, post_measure


@pytest.fixture
def client():
    return create_app().test_client()


@pytest.fixture
def sidecar():
    return architecture_example()


def assert_error_contract(response, status, error):
    assert response.status_code == status
    body = response.get_json()
    Draft202012Validator(ERROR_SCHEMA).validate(body)
    assert body["error"] == error
    assert 1 <= len(body["detail"]) <= DETAIL_MAX_LENGTH
    return body


def test_error_schema_is_itself_valid():
    Draft202012Validator.check_schema(ERROR_SCHEMA)


def test_status_codes_are_enumerated_and_tied_to_a_class():
    assert ERROR_STATUSES[400] == (
        "malformed request: missing image, missing sidecar, or sidecar is not JSON"
    )
    assert ERROR_STATUSES[422] == "sidecar is JSON but fails the capture sidecar schema"
    assert set(ERROR_STATUSES) == {400, 422}


def test_missing_image_matches_error_schema(client, sidecar):
    response = post_measure(client, sidecar, omit=("image",))
    body = assert_error_contract(response, 400, "missing image")
    assert "field" not in body


def test_missing_sidecar_matches_error_schema(client):
    response = post_measure(client, omit=("sidecar",))
    body = assert_error_contract(response, 400, "missing sidecar")
    assert "field" not in body


def test_sidecar_not_json_matches_error_schema(client):
    response = post_measure(client, sidecar="{not json")
    body = assert_error_contract(response, 400, "sidecar is not valid JSON")
    assert "field" not in body


def test_invalid_sidecar_matches_error_schema(client, sidecar):
    sidecar.pop("split")
    response = post_measure(client, sidecar)
    body = assert_error_contract(response, 422, "sidecar failed validation")
    assert "split" in body["detail"]


def test_detail_stays_bounded_when_the_rejected_value_is_huge(client, sidecar):
    sidecar["split"] = "x" * 10_000
    response = post_measure(client, sidecar)
    body = assert_error_contract(response, 422, "sidecar failed validation")
    assert len(body["detail"]) == DETAIL_MAX_LENGTH
    assert body["detail"].endswith("...")
    assert "x" * 10_000 not in json.dumps(body)


def test_detail_stays_bounded_for_a_deeply_nested_rejected_input(client, sidecar):
    nested = {"leaf": "x" * 4_000}
    for _ in range(40):
        nested = {"inner": nested}
    sidecar["ground_truth"] = nested
    response = post_measure(client, sidecar)
    body = assert_error_contract(response, 422, "sidecar failed validation")
    assert len(body["detail"]) <= DETAIL_MAX_LENGTH
    dumped = json.dumps(body)
    assert len(dumped) < 1_000


def test_schema_rejects_an_unbounded_detail():
    body = {
        "error": "sidecar failed validation",
        "detail": "x" * (DETAIL_MAX_LENGTH + 1),
    }
    with pytest.raises(ValidationError):
        Draft202012Validator(ERROR_SCHEMA).validate(body)


def test_schema_rejects_an_unknown_error_token():
    body = {"error": "something went wrong", "detail": "nope"}
    with pytest.raises(ValidationError):
        Draft202012Validator(ERROR_SCHEMA).validate(body)


@pytest.mark.parametrize("blank", ["   ", "\n", "\t"])
def test_error_schema_rejects_a_whitespace_only_detail(blank):
    """minLength alone accepts "   ", which renders as a blank — same hole as TICK-228/229."""
    with pytest.raises(ValidationError):
        Draft202012Validator(ERROR_SCHEMA).validate({"error": "missing image", "detail": blank})


def test_error_schema_rejects_a_whitespace_only_field():
    with pytest.raises(ValidationError):
        Draft202012Validator(ERROR_SCHEMA).validate(
            {"error": "sidecar failed validation", "detail": "bad", "field": " "}
        )
