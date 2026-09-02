"""The sidecar the app actually writes must satisfy the committed schema (TICK-028 AC1).

`tests/fixtures/written_sidecar.json` is emitted by the Swift suite -- CaptureWriterTests
regenerates it on every run -- and validated here against the same schema the server enforces.
Two independent implementations of one contract drift silently otherwise: Swift would keep
producing a shape it is happy with, Python would keep accepting a shape nobody produces, and the
disagreement would surface as a rejected upload in the field.

Nothing here mocks the writer. If Swift emits a key the schema forbids, or omits one it requires,
this fails.
"""

import json
from pathlib import Path

import pytest
from jsonschema import ValidationError

from frontdoor.sidecar import validate_sidecar

FIXTURES = Path(__file__).resolve().parent / "fixtures"
WRITTEN = FIXTURES / "written_sidecar.json"
#: Every shape the Swift writer can emit needs one, or the shape it never emits is the
#: shape neither side checks. The depth object had NO fixture: every Swift test passed
#: `depth: nil`, so this suite only ever saw `"depth": null`, and the writer emitted
#: `width`/`height` into an object the schema declares additionalProperties: false
#: without either language noticing (QA B01).
GOLDEN = ("written_sidecar.json", "written_sidecar_with_depth.json",
          "written_sidecar_screening.json", "written_sidecar_imported.json")


@pytest.fixture
def written():
    return json.loads(WRITTEN.read_text(encoding="utf-8"))


def test_the_app_writes_a_sidecar_the_schema_accepts(written):
    validate_sidecar(written)


def test_depth_is_present_and_null_rather_than_absent(written):
    """A phone with no depth sensor still produces a valid capture (D-020, TICK-023).

    Swift's synthesised encoder drops nil optionals, which would have omitted the key entirely --
    and `depth` is required. Absence has to be recorded, not merely absent.
    """
    assert "depth" in written
    assert written["depth"] is None


def test_the_distortion_table_survives_the_round_trip(written):
    """The field #36 and #37 both need, and which had nowhere to live until this branch."""
    table = written["intrinsics"]["distortion_table"]
    assert isinstance(table, list) and len(table) >= 2
    assert all(isinstance(v, (int, float)) for v in table)
    assert set(written["intrinsics"]["distortion_center"]) == {"x", "y"}


def test_the_six_roi_taps_are_integers_in_sensor_space(written):
    roi = written["roi"]
    assert len(roi["card_corners"]) == 4
    points = [roi["threshold_top"], roi["threshold_bottom"], *roi["card_corners"]]
    assert len(points) == 6
    for x, y in points:
        assert isinstance(x, int) and isinstance(y, int), "taps are pixels, not fractions"
        assert 0 <= x < written["image"]["width"]
        assert 0 <= y < written["image"]["height"]


def test_the_camera_provenance_is_recorded_in_full(written):
    """lens is the optics; capture_device is the device opened; zoom_factor separates the 1x main
    lens from the ultra-wide on that device. All three, or the D-014 claim is unverifiable."""
    assert written["lens"] == "builtInWideAngleCamera"
    assert written["capture_device"] == "builtInDualWideCamera"
    assert written["zoom_factor"] > 0


def test_keys_are_sorted_so_the_bytes_are_reproducible(written):
    """`sidecar_sha256` is only meaningful if identical content gives identical bytes (AC6)."""
    raw = WRITTEN.read_text(encoding="utf-8")
    assert list(json.loads(raw).keys()) == sorted(written.keys())


@pytest.mark.parametrize("name", GOLDEN)
def test_every_golden_fixture_exists(name):
    """The Swift test bootstraps a missing fixture rather than failing on it.

    That is convenient when adding a case and dangerous if it is never committed, so
    the existence check lives here, where CI runs without a simulator.
    """
    assert (FIXTURES / name).is_file(), (
        f"{name} is missing. Run the Swift suite once to emit it, then commit it."
    )


@pytest.mark.parametrize("name", GOLDEN)
def test_every_shape_the_writer_emits_satisfies_the_schema(name):
    validate_sidecar(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def test_a_depth_capture_carries_only_path_and_sha256():
    """ARCHITECTURE section 4 defines depth as {path, sha256}; the schema forbids more.

    The writer built its depth reference from the same type as the image reference, so
    `width` and `height` rode along and every real depth capture wrote an invalid
    sidecar. Caught by no test on either side, because no test had a depth capture.
    """
    doc = json.loads((FIXTURES / "written_sidecar_with_depth.json").read_text(encoding="utf-8"))
    assert set(doc["depth"]) == {"path", "sha256"}


def test_the_depth_fixture_really_has_depth():
    """Otherwise this file could pass while testing the null case twice."""
    doc = json.loads((FIXTURES / "written_sidecar_with_depth.json").read_text(encoding="utf-8"))
    assert doc["depth"] is not None


# --- the modes D-034 added (TICK-027 / #31) ------------------------------------------------

def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_the_screening_sidecar_swift_writes_validates_here():
    """Written by Swift, validated by Python. Neither side gets to define the shape alone.

    This is the check that was missing when the depth object drifted (QA B01): both
    implementations agreed on a shape neither of them exercised.
    """
    validate_sidecar(_fixture("written_sidecar_screening.json"))


def test_the_imported_sidecar_swift_writes_validates_here():
    validate_sidecar(_fixture("written_sidecar_imported.json"))


def test_the_screening_sidecar_carries_no_metrology_claim():
    doc = _fixture("written_sidecar_screening.json")
    assert doc["capture_mode"] == "screening"
    for forbidden in ("ground_truth", "card_placement", "roi"):
        assert forbidden not in doc, f"{forbidden} must be absent, not null"
    assert "surface" not in doc["conditions"], (
        "the protocol never asks an operator for a surface, so a value here is a guess"
    )
    # Our camera took it, so what the camera measured is still recorded.
    assert doc["intrinsics"] and doc["gravity"]


def test_the_imported_sidecar_claims_nothing_the_file_did_not_say():
    doc = _fixture("written_sidecar_imported.json")
    assert doc["capture_mode"] == "imported"
    for forbidden in ("intrinsics", "gravity", "lens", "capture_device", "zoom_factor",
                      "ground_truth", "card_placement", "roi"):
        assert forbidden not in doc, (
            f"{forbidden} would put a measured-looking value on a photo this app never took"
        )
    assert doc["entrance_id"] and doc["captured_at"] and doc["split"]


def test_a_screening_capture_may_sit_beyond_the_metrology_distance_cap():
    """docs/capture-protocol.md asks for a far, ~3-4 m shot; R-3's 3 m cap is metrology-only."""
    assert _fixture("written_sidecar_screening.json")["conditions"]["distance_m"] > 3.0
