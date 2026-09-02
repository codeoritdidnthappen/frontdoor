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


def test_null_depth_is_accepted(record):
    """TICK-023 AC5: absence of a depth map must not cost an entrance."""
    record["depth"] = None
    validate_sidecar(record)


def test_malformed_depth_object_is_still_rejected(record):
    record["depth"] = {"path": "depth.bin"}
    with pytest.raises(ValidationError):
        validate_sidecar(record)


def test_non_object_non_null_depth_is_rejected(record):
    record["depth"] = "depth.bin"
    with pytest.raises(ValidationError):
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


@pytest.mark.parametrize(
    "entrance_id",
    ["e-014", "E-014 ", " E-014", "E-14", "E-0014", ""],
)
def test_noncanonical_entrance_id_rejected_by_schema(record, entrance_id):
    record["entrance_id"] = entrance_id
    with pytest.raises(ValidationError):
        validate_sidecar(record)


@pytest.mark.parametrize("field", ["image", "depth"])
@pytest.mark.parametrize("suffix", ["\n", " ", "\r"])
def test_sha256_rejects_trailing_whitespace(record, field, suffix):
    digest = hashlib.sha256(b"sidecar-hash-fixture").hexdigest()
    record[field]["sha256"] = digest + suffix
    with pytest.raises(ValidationError):
        validate_sidecar(record)


@pytest.mark.parametrize("field", ["image", "depth"])
def test_sha256_rejects_leading_newline(record, field):
    digest = hashlib.sha256(b"sidecar-hash-fixture").hexdigest()
    record[field]["sha256"] = "\n" + digest
    with pytest.raises(ValidationError):
        validate_sidecar(record)


@pytest.mark.parametrize("field", ["image", "depth"])
def test_sha256_rejects_internal_whitespace(record, field):
    digest = hashlib.sha256(b"sidecar-hash-fixture").hexdigest()
    record[field]["sha256"] = digest[:32] + " " + digest[32:]
    with pytest.raises(ValidationError):
        validate_sidecar(record)


@pytest.mark.parametrize("suffix", ["\n", " ", "\r"])
def test_captured_at_rejects_trailing_whitespace(record, suffix):
    """A bare $ matches before a trailing newline under Python re; the anchor must not (TICK-229)."""
    record["captured_at"] = "2026-08-30T14:22:31Z" + suffix
    with pytest.raises(ValidationError):
        validate_sidecar(record)
    with pytest.raises(ValidationError):
        validate_sidecar(record)


@pytest.mark.parametrize("suffix", ["\n", " ", "\r"])
def test_entrance_id_rejects_trailing_whitespace(record, suffix):
    """One spelling per entrance: "E-014\\n" must not validate alongside "E-014" (TICK-229)."""
    record["entrance_id"] = "E-014" + suffix
    with pytest.raises(ValidationError):
        validate_sidecar(record)


# --------------------------------------------------- distortion (TICK-028, #36, #37)


@pytest.mark.parametrize("field", ["distortion_table", "distortion_center"])
def test_intrinsics_require_the_distortion_data(record, field):
    """Section 2 lists the distortion table as part of the method's legal input, and #36 and #37
    both consume it. Until TICK-028 the schema had no field for it and `additionalProperties` was
    false, so a capture could not carry one even if the camera delivered it -- and both phones do,
    42 entries each. Arms A and A-prime had nothing to undistort with.

    Required rather than optional: a frame whose taps cannot be undistorted is not measurable, and
    this project refuses such frames rather than recording them and finding out at analysis.
    """
    del record["intrinsics"][field]
    with pytest.raises(ValidationError, match=field):
        validate_sidecar(record)


def test_a_one_entry_distortion_table_is_rejected(record):
    """One sample cannot be interpolated between, so it describes no correction at all."""
    record["intrinsics"]["distortion_table"] = [0.0]
    with pytest.raises(ValidationError):
        validate_sidecar(record)


@pytest.mark.parametrize("missing", ["x", "y"])
def test_the_distortion_centre_needs_both_coordinates(record, missing):
    del record["intrinsics"]["distortion_center"][missing]
    with pytest.raises(ValidationError):
        validate_sidecar(record)


def test_the_distortion_centre_is_not_assumed_to_be_the_principal_point(record):
    """They are different quantities and the schema must let them differ. The table is radial
    about the distortion centre; using cx/cy in its place biases the frame-edge corrections the
    table exists to make.
    """
    record["intrinsics"]["distortion_center"] = {"x": 2000.0, "y": 1500.0}
    validate_sidecar(record)


# ------------------------------------------- the D-014 claim must be checkable (TICK-020)


@pytest.mark.parametrize("field", ["capture_device", "zoom_factor"])
def test_the_camera_provenance_fields_are_required(record, field):
    """`lens` alone cannot support the claim D-014 makes.

    On builtInDualWideCamera the zoom scale is relative to the ultra-wide, so 2.00 is the 1x main
    lens and 1.00 is ~120 degrees of ultra-wide. A record carrying only a lens name describes both
    identically -- and the wrong one is a D-014 violation nothing downstream could detect.
    """
    del record[field]
    with pytest.raises(ValidationError, match=field):
        validate_sidecar(record)


def test_lens_and_capture_device_are_allowed_to_differ(record):
    """They are different claims: the optics used, and the device opened to reach them. Both team
    phones reach the 1x wide lens through builtInDualWideCamera, because the bare wide camera
    delivers no calibration data and cannot produce a measurable frame at all (TICK-020).
    """
    assert record["lens"] != record["capture_device"]
    validate_sidecar(record)


def test_a_zero_or_negative_zoom_factor_is_rejected(record):
    for bad in (0, -1.0):
        record["zoom_factor"] = bad
        with pytest.raises(ValidationError):
            validate_sidecar(record)


# --- capture_mode: one schema, three kinds of record (D-034, TICK-027 / #31) -------------


def screening_record():
    """A plain-photo capture: our camera, no caliper, no card, no ROI taps."""
    record = architecture_example()
    record["capture_mode"] = "screening"
    for gone in ("ground_truth", "card_placement", "roi"):
        record.pop(gone, None)
    record["conditions"].pop("surface", None)
    return record


def imported_record():
    """A photo taken outside this app. None of our capture metadata exists for it."""
    record = screening_record()
    record["capture_mode"] = "imported"
    for gone in ("lens", "capture_device", "zoom_factor", "intrinsics", "gravity"):
        record.pop(gone, None)
    return record


def test_a_screening_capture_validates_without_caliper_card_or_roi():
    validate_sidecar(screening_record())


def test_an_imported_photo_validates_without_any_of_our_capture_metadata():
    validate_sidecar(imported_record())


def test_a_sidecar_with_no_capture_mode_is_still_held_to_the_metrology_contract():
    """Every sidecar written before D-034 must keep meaning exactly what it meant.

    Absent is metrology, not "any mode I like" -- otherwise the loosening would silently
    reach backwards and let an old record drop its intrinsics.
    """
    record = architecture_example()
    record.pop("capture_mode", None)
    record.pop("intrinsics")
    with pytest.raises(ValidationError):
        validate_sidecar(record)


@pytest.mark.parametrize(
    "missing", ["lens", "capture_device", "zoom_factor", "intrinsics", "gravity",
                "card_placement", "ground_truth"])
def test_a_metrology_capture_still_requires_everything_it_always_did(missing):
    record = architecture_example()
    record["capture_mode"] = "metrology"
    record.pop(missing)
    with pytest.raises(ValidationError):
        validate_sidecar(record)


@pytest.mark.parametrize("field", ["ground_truth", "card_placement", "roi"])
def test_a_screening_capture_may_not_carry_metrology_fields(field):
    """Not merely optional -- forbidden.

    A screening capture that carried a caliper reading would mean the protocol was not
    followed, or that someone filled a field in to make a form pass. Either way the record
    would claim a measurement nobody took.
    """
    record = screening_record()
    record[field] = architecture_example().get(field, {"rise_in": 0.5, "instrument": "caliper"})
    with pytest.raises(ValidationError):
        validate_sidecar(record)


@pytest.mark.parametrize("field", ["intrinsics", "gravity", "zoom_factor", "lens"])
def test_an_imported_photo_may_not_claim_capture_metadata_it_cannot_have(field):
    """The whole point of the imported mode: a camera-roll photo has none of this.

    Letting it carry intrinsics would put a measured-looking value on a record that
    measured nothing -- and the error analysis reads device and lens as facts.
    """
    record = imported_record()
    record[field] = architecture_example()[field]
    with pytest.raises(ValidationError):
        validate_sidecar(record)


def test_a_screening_capture_still_needs_its_entrance_conditions_and_split():
    for field in ("entrance_id", "conditions", "split", "image", "depth", "captured_at"):
        record = screening_record()
        record.pop(field)
        with pytest.raises(ValidationError):
            validate_sidecar(record)


def test_surface_is_optional_because_the_protocol_never_asks_for_it():
    record = screening_record()
    assert "surface" not in record["conditions"]
    validate_sidecar(record)


def test_lighting_and_occlusion_are_still_required_because_the_protocol_does_ask():
    for field in ("lighting", "occlusion", "distance_m"):
        record = screening_record()
        record["conditions"].pop(field)
        with pytest.raises(ValidationError):
            validate_sidecar(record)


def test_an_unknown_capture_mode_is_refused():
    record = screening_record()
    record["capture_mode"] = "guess"
    with pytest.raises(ValidationError):
        validate_sidecar(record)
