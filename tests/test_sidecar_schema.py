"""Tests for the capture sidecar schema and validator (TICK-010, #18)."""

import hashlib
import json
import re
from pathlib import Path

import pytest
from jsonschema import ValidationError

from frontdoor.sidecar import validate_sidecar

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FIELDS = [
    "capture_id",
    "entrance_id",
    "captured_at",
    "device_model",
    "lens",
    "image",
    "depth",
    "intrinsics",
    "gravity",
    "card_placement",
    "ground_truth",
    "conditions",
    "split",
]


def architecture_example():
    """The verbatim JSON example from ARCHITECTURE.md section 4.

    Parsed out of the document itself so schema and document cannot drift apart silently.
    """
    text = (REPO_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    block = re.search(r"```json\n(.*?)```", text, re.DOTALL)
    assert block, "no ```json block found in ARCHITECTURE.md"
    return json.loads(block.group(1))


def valid_roi():
    return {
        "threshold_top": [1010.0, 1400.0],
        "threshold_bottom": [1012.0, 1480.0],
        "card_corners": [
            [900.0, 1500.0],
            [1100.0, 1500.0],
            [1100.0, 1620.0],
            [900.0, 1620.0],
        ],
    }


@pytest.fixture
def record():
    return architecture_example()


def test_architecture_example_validates(record):
    validate_sidecar(record)


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_missing_required_field_rejected(record, field):
    del record[field]
    with pytest.raises(ValidationError, match=field):
        validate_sidecar(record)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("card_placement", "diagonal"),
        ("card_placement", "Vertical"),
        ("split", "test"),
        ("split", "DEV"),
    ],
)
def test_enum_violation_rejected(record, field, value):
    record[field] = value
    with pytest.raises(ValidationError):
        validate_sidecar(record)


@pytest.mark.parametrize("gravity", [[], [0.02, -0.98], [0.02, -0.98, -0.19, 0.01]])
def test_gravity_wrong_length_rejected(record, gravity):
    record["gravity"] = gravity
    with pytest.raises(ValidationError):
        validate_sidecar(record)


def test_missing_caliper_reading_rejected(record):
    del record["ground_truth"]["rise_in"]
    with pytest.raises(ValidationError, match="rise_in"):
        validate_sidecar(record)


def test_missing_instrument_rejected(record):
    del record["ground_truth"]["instrument"]
    with pytest.raises(ValidationError, match="instrument"):
        validate_sidecar(record)


def test_non_numeric_rise_rejected(record):
    record["ground_truth"]["rise_in"] = "0.53"
    with pytest.raises(ValidationError):
        validate_sidecar(record)


def test_roi_accepted_when_present(record):
    record["roi"] = valid_roi()
    validate_sidecar(record)


@pytest.mark.parametrize("field", ["threshold_top", "threshold_bottom", "card_corners"])
def test_roi_missing_field_rejected(record, field):
    roi = valid_roi()
    del roi[field]
    record["roi"] = roi
    with pytest.raises(ValidationError, match=field):
        validate_sidecar(record)


@pytest.mark.parametrize("count", [3, 5])
def test_roi_wrong_corner_count_rejected(record, count):
    roi = valid_roi()
    roi["card_corners"] = [[0.0, 0.0]] * count
    record["roi"] = roi
    with pytest.raises(ValidationError):
        validate_sidecar(record)


def test_unknown_field_rejected(record):
    record["measured_rise_in"] = 0.5
    with pytest.raises(ValidationError):
        validate_sidecar(record)


@pytest.mark.parametrize("field", ["image", "depth"])
@pytest.mark.parametrize(
    "digest",
    [
        "",
        "not-a-hash",
        "deadbeef",
        "a" * 65,
        "g" * 64,
        "A" * 64,
    ],
)
def test_invalid_sha256_rejected(record, field, digest):
    record[field]["sha256"] = digest
    with pytest.raises(ValidationError):
        validate_sidecar(record)


@pytest.mark.parametrize("field", ["image", "depth"])
def test_real_sha256_digest_accepted(record, field):
    record[field]["sha256"] = hashlib.sha256(b"sidecar-hash-fixture").hexdigest()
    validate_sidecar(record)


@pytest.mark.parametrize(
    "timestamp",
    [
        "banana",
        "",
        "2026-13-45T99:99:99Z",
        "2026-08-30",
        "2026-08-30T14:22:31+00:00",
    ],
)
def test_invalid_captured_at_rejected(record, timestamp):
    record["captured_at"] = timestamp
    with pytest.raises(ValidationError):
        validate_sidecar(record)


def test_date_time_format_checker_is_registered():
    from jsonschema import Draft202012Validator

    assert "date-time" in Draft202012Validator.FORMAT_CHECKER.checkers
