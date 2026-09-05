"""Photo-based ADA screening score (issue #318).

The model supplies eight check results. The server, not the model, computes
the score, counts, and summary. No live model calls.
"""

import json
import logging

import pytest

from frontdoor.screening import (
    ADA_CHECK_KEYS,
    ADA_DISCLAIMER,
    ADA_STANDARDS_URL,
    CRITERIA_KEYS,
    FACE_CHECK_KEY,
    ScreeningError,
    ScreeningEngine,
    build_integrated_prompt,
    build_prompt,
    compute_ada_screening,
    validate_ada_checks,
    validate_verdicts,
)
from tests.test_screening import FakeClient, _Response, _payload


def _checks(**results):
    """Eight checks; unspecified keys default to cannot_determine."""
    out = {}
    for key in ADA_CHECK_KEYS:
        result = results.get(key, "cannot_determine")
        out[key] = {"result": result, "evidence": f"{key} evidence"}
    return out


def test_mixed_fixture_matches_the_contract_example():
    checks = _checks(
        entrance_route="true",
        threshold="false",
        ramp="not_applicable",
        door_hardware="true",
        door_opening="cannot_determine",
        handrails="not_applicable",
        signage="cannot_determine",
        temporary_barriers="true",
    )
    out = compute_ada_screening(checks)
    assert out["score_percent"] == 75.0
    assert out["determined_count"] == 4
    assert out["total_count"] == 8
    assert out["true_count"] == 3
    assert out["false_count"] == 1
    assert out["cannot_determine_count"] == 2
    assert out["not_applicable_count"] == 2
    assert (
        out["true_count"]
        + out["false_count"]
        + out["cannot_determine_count"]
        + out["not_applicable_count"]
        == out["total_count"]
        == 8
    )
    assert out["summary"] == (
        "Three of four determined photo checks were supported. "
        "A potential barrier was observed for threshold. "
        "Four checks could not be determined or were not applicable."
    )
    assert out["standards_url"] == ADA_STANDARDS_URL
    assert out["disclaimer"] == ADA_DISCLAIMER
    assert list(out["checks"]) == list(ADA_CHECK_KEYS)


def test_all_true_scores_one_hundred():
    out = compute_ada_screening(_checks(**{key: "true" for key in ADA_CHECK_KEYS}))
    assert out["score_percent"] == 100.0
    assert out["determined_count"] == 8
    assert out["true_count"] == 8
    assert out["false_count"] == 0
    assert out["cannot_determine_count"] == 0
    assert out["not_applicable_count"] == 0
    assert out["summary"] == "Eight of eight determined photo checks were supported."


def test_zero_determined_score_is_null():
    out = compute_ada_screening(_checks())
    assert out["score_percent"] is None
    assert out["determined_count"] == 0
    assert out["cannot_determine_count"] == 8
    assert out["summary"] == (
        "No photo checks were determined. "
        "Eight checks could not be determined or were not applicable."
    )


def test_not_applicable_is_excluded_from_the_score_denominator():
    out = compute_ada_screening(_checks(
        entrance_route="true",
        threshold="true",
        ramp="not_applicable",
        door_hardware="false",
        door_opening="not_applicable",
        handrails="not_applicable",
        signage="not_applicable",
        temporary_barriers="not_applicable",
    ))
    assert out["score_percent"] == 66.7
    assert out["determined_count"] == 3
    assert out["not_applicable_count"] == 5


def test_one_decimal_rounding():
    out = compute_ada_screening(_checks(
        entrance_route="true",
        threshold="false",
        ramp="false",
        **{key: "cannot_determine" for key in ADA_CHECK_KEYS[3:]},
    ))
    assert out["score_percent"] == 33.3


def test_summary_never_uses_compliance_language():
    fixtures = (
        _checks(**{key: "true" for key in ADA_CHECK_KEYS}),
        _checks(**{key: "false" for key in ADA_CHECK_KEYS}),
        _checks(),
        _checks(entrance_route="true", threshold="false", ramp="not_applicable"),
    )
    banned = ("compliant", "noncompliant", "passes", "fails")
    for checks in fixtures:
        summary = compute_ada_screening(checks)["summary"].lower()
        for word in banned:
            assert word not in summary, word


def test_missing_or_extra_check_rejects_the_whole_block():
    parsed = {"ada_checks": _checks()}
    del parsed["ada_checks"]["signage"]
    with pytest.raises(ScreeningError, match="exactly the eight"):
        validate_ada_checks(parsed)
    parsed = {"ada_checks": _checks()}
    parsed["ada_checks"]["door_width"] = parsed["ada_checks"]["threshold"]
    with pytest.raises(ScreeningError, match="exactly the eight"):
        validate_ada_checks(parsed)


@pytest.mark.parametrize("result", ["present", "yes", True, False, ""])
def test_invalid_state_rejects_the_whole_block(result):
    parsed = {"ada_checks": _checks()}
    parsed["ada_checks"]["threshold"]["result"] = result
    with pytest.raises(ScreeningError, match="threshold"):
        validate_ada_checks(parsed)


@pytest.mark.parametrize(
    "evidence",
    ["", "  ", "first\nsecond", "\nvisible\n", "one\u2028two", "line\rwith cr"],
)
def test_blank_or_multiline_evidence_rejects_the_whole_block(evidence):
    parsed = {"ada_checks": _checks()}
    parsed["ada_checks"]["ramp"]["evidence"] = evidence
    with pytest.raises(ScreeningError, match="ramp evidence"):
        validate_ada_checks(parsed)


@pytest.mark.parametrize(
    "evidence",
    [
        "This entrance is ADA compliant.",
        "The doorway passes ADA requirements.",
        "Door is 36 inches wide.",
        "The slope is 7.5%.",
    ],
)
def test_unsafe_model_authored_evidence_is_rejected(evidence):
    parsed = {"ada_checks": _checks()}
    parsed["ada_checks"]["door_opening"]["evidence"] = evidence
    with pytest.raises(ScreeningError, match="door_opening evidence"):
        validate_ada_checks(parsed)


def test_explicit_nonnumeric_measurement_uncertainty_is_allowed():
    parsed = {"ada_checks": _checks()}
    parsed["ada_checks"]["door_opening"]["evidence"] = (
        "Exact clear width cannot be measured from these photographs."
    )
    assert validate_ada_checks(parsed)["door_opening"]["evidence"].startswith(
        "Exact clear width"
    )


def test_invalid_state_does_not_leak_model_authored_text(caplog):
    secret = "James visible through the window"
    poisoned = json.loads(_payload())
    poisoned["ada_checks"]["threshold"]["result"] = secret
    engine = ScreeningEngine(client=FakeClient([_Response(json.dumps(poisoned))]))
    with caplog.at_level(logging.WARNING):
        result = engine.assess_image(b"jpeg-bytes")
    assert result.criteria is None
    assert secret not in (result.error or "")
    assert secret not in caplog.text


@pytest.mark.parametrize("field", [
    "score_percent", "determined_count", "total_count", "true_count",
    "false_count", "cannot_determine_count", "not_applicable_count", "summary",
])
def test_model_supplied_aggregates_are_rejected(field):
    parsed = {"ada_checks": _checks(), field: 1}
    with pytest.raises(ScreeningError, match="must not supply"):
        validate_ada_checks(parsed)


def test_model_supplied_ada_screening_object_is_rejected():
    parsed = {
        "ada_checks": _checks(),
        "ada_screening": {"score_percent": 100, "summary": "passes"},
    }
    with pytest.raises(ScreeningError, match="must not supply"):
        validate_ada_checks(parsed)


def test_engine_carries_validated_checks_and_rejects_aggregates():
    engine = ScreeningEngine(client=FakeClient([_Response(_payload())]))
    result = engine.assess_image(b"jpeg-bytes")
    assert result.error is None
    assert set(result.ada_checks) == set(ADA_CHECK_KEYS)

    poisoned = json.loads(_payload())
    poisoned["score_percent"] = 99
    engine = ScreeningEngine(client=FakeClient([_Response(json.dumps(poisoned))]))
    result = engine.assess_image(b"jpeg-bytes")
    assert result.criteria is None
    assert result.ada_checks is None
    assert "must not supply" in result.error


def test_prompt_asks_for_the_eight_checks_and_forbids_compliance_claims():
    for prompt in (build_prompt(), build_integrated_prompt(6)):
        for key in ADA_CHECK_KEYS:
            assert key in prompt
        for state in ("true", "false", "cannot_determine", "not_applicable"):
            assert state in prompt
        assert "ada_checks" in prompt
        lowered = prompt.lower()
        assert "dimensional" in lowered or "never guess" in lowered
        assert "compliance" in lowered or "legal" in lowered
        assert "ada_screening" not in prompt


def test_existing_four_criteria_remain_in_the_prompt_and_validator():
    prompt = build_prompt()
    for key in CRITERIA_KEYS:
        assert key in prompt
    parsed = json.loads(_payload())
    assert set(validate_verdicts(parsed)) == set(CRITERIA_KEYS)
    assert FACE_CHECK_KEY in parsed
