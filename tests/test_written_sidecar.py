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

WRITTEN = Path(__file__).resolve().parent / "fixtures" / "written_sidecar.json"


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
