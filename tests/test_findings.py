"""TICK-101 (#71): the findings document reports committed artifacts, not memory.

Every number in docs/findings.md has to come from docs/rise-error-budget.json or be
explicitly absent because the sealed run has not happened. The capture protocol's
trustworthiness section is the same budget, not a second derivation.
"""

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FINDINGS = PROJECT_ROOT / "docs" / "findings.md"
PROTOCOL = PROJECT_ROOT / "docs" / "capture-protocol.md"
BUDGET_PATH = PROJECT_ROOT / "docs" / "rise-error-budget.json"
SEALED_REPORT = PROJECT_ROOT / "reports" / "sealed" / "screening_eval.json"


def _findings() -> str:
    return FINDINGS.read_text(encoding="utf-8")


def _protocol() -> str:
    return PROTOCOL.read_text(encoding="utf-8")


def _budget() -> dict:
    return json.loads(BUDGET_PATH.read_text(encoding="utf-8"))


def _measured_points() -> list[tuple[str, float, float]]:
    budget = _budget()
    points: list[tuple[str, float, float]] = []
    for series in budget["series"]:
        if series["focal_status"] != "measured on James's iPhone 17 Pro":
            continue
        for angle, inches in series["points"]:
            points.append((series["label"], float(angle), float(inches)))
    return points


def test_findings_document_exists() -> None:
    assert FINDINGS.is_file()


def test_pre_registered_mae_hypothesis_is_stated_untested() -> None:
    text = _findings()
    assert "MAE ≤ 0.25" in text or "MAE <= 0.25" in text
    assert "untested" in text
    assert "not relaxed" in text
    assert "A-3" in text
    assert "D-036" in text


def test_amendments_a1_and_a2_are_reported_as_amendments_with_dates() -> None:
    text = _findings()
    assert "Amendment A-1" in text
    assert "Amendment A-2" in text
    assert "2026-08-29" in text
    assert "reported as an amendment" in text.lower() or "reported as amendments" in text.lower()
    a1 = text.index("Amendment A-1")
    a2 = text.index("Amendment A-2")
    assert "2026-08-29" in text[a1 : a1 + 400]
    assert "2026-08-29" in text[a2 : a2 + 400]
    assert "Arm A" in text[a2 : a2 + 600]


def test_condition_error_is_not_a_single_headline_number() -> None:
    text = _findings()
    assert "exploratory" in text.lower()
    assert "capture angle" in text.lower()
    assert "confirmatory" in text.lower()


def test_other_arms_have_no_pass_fail_bar() -> None:
    text = _findings()
    assert "D-022" in text
    assert "pass/fail bar" in text
    assert "Arm A′" in text or "Arm A'" in text
    assert "Arm B" in text
    assert "Arm C" in text


def test_failure_classes_are_named() -> None:
    text = _findings()
    assert "glass" in text.lower()
    assert "bevel" in text.lower() or "bevelled" in text.lower() or "beveled" in text.lower()
    assert "occlusion" in text.lower()


def test_limitations_name_the_one_phone_and_refuse_cross_device_claims() -> None:
    text = _findings()
    assert "iPhone 17 Pro" in text
    assert "iPhone18,1" in text
    assert "D-040" in text
    assert "cross-device" in text.lower() or "cross-device generalisation" in text.lower()


def test_cited_inches_match_the_measured_prediction_series() -> None:
    findings = _findings()
    for _label, _angle, inches in _measured_points():
        token = f"{inches:.3f}"
        assert token in findings, f"{token}″ from the measured series is missing from findings"


def test_prediction_is_labelled_predicted_not_observed() -> None:
    findings = _findings()
    protocol = _protocol()
    status = _budget()["status"]
    assert status in findings
    for text in (findings, protocol):
        assert "predicted" in text.lower()
        assert "not an observed result" in text.lower()


def test_protocol_has_a_trustworthiness_section_sourced_from_the_budget() -> None:
    text = _protocol()
    heading = "## When an estimate can be trusted"
    assert heading in text
    section = text[text.index(heading) :]
    assert "TICK-075" in section
    assert "rise-error-budget.json" in section
    assert "2.5 m" in section
    assert "2807.7" in section


def test_sealed_screening_numbers_are_absent_until_the_sealed_report_exists() -> None:
    text = _findings()
    if SEALED_REPORT.is_file():
        report = json.loads(SEALED_REPORT.read_text(encoding="utf-8"))
        assert report.get("split") == "sealed"
        return
    assert "#63" in text
    assert not re.search(
        r"sealed[- ]split (?:accuracy|result)[:\s]+[0-9]",
        text,
        flags=re.IGNORECASE,
    )
    assert "97%" not in text
