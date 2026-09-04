"""Point undistortion against Apple's documented radial lookup model (#36)."""

from math import hypot

import pytest

from frontdoor.metrology import DistortionError, undistort_point, undistort_points


def test_ac1_and_ac5_distortion_center_is_unchanged() -> None:
    assert undistort_point(
        (40.0, 60.0),
        (100.0, 100.0),
        (0.0, 0.25),
        (40.0, 60.0),
    ) == (40.0, 60.0)


def test_ac2_exact_lookup_sample_uses_relative_radial_magnification() -> None:
    radius_max = hypot(50.0, 50.0)
    point = (50.0 + radius_max / 2.0, 50.0)

    corrected = undistort_point(
        point,
        (100.0, 100.0),
        (0.0, 0.1, 0.2),
        (50.0, 50.0),
    )

    assert corrected == pytest.approx((50.0 + 1.1 * radius_max / 2.0, 50.0))


def test_ac2_interpolates_between_evenly_spaced_radii() -> None:
    radius_max = hypot(50.0, 50.0)
    point = (50.0 + radius_max / 4.0, 50.0)

    corrected = undistort_point(
        point,
        (100.0, 100.0),
        (0.0, 0.1, 0.2),
        (50.0, 50.0),
    )

    assert corrected == pytest.approx((50.0 + 1.05 * radius_max / 4.0, 50.0))


def test_ac2_farthest_corner_uses_last_lookup_sample() -> None:
    corrected = undistort_point(
        (100.0, 100.0),
        (100.0, 100.0),
        (0.0, 0.1, 0.2),
        (50.0, 50.0),
    )

    assert corrected == pytest.approx((110.0, 110.0))


def test_ac3_uses_distortion_center_not_principal_point() -> None:
    principal_point = (50.0, 50.0)
    distortion_center = (40.0, 60.0)
    point = (50.0, 60.0)

    corrected = undistort_point(
        point,
        (100.0, 100.0),
        (0.1, 0.1),
        distortion_center,
    )

    assert corrected == pytest.approx((51.0, 60.0))
    assert corrected != pytest.approx(
        undistort_point(point, (100.0, 100.0), (0.1, 0.1), principal_point)
    )


def test_ac4_batch_preserves_order_and_does_not_mutate_input() -> None:
    points = [(50.0, 50.0), (60.0, 50.0), (50.0, 60.0)]
    original = points.copy()

    corrected = undistort_points(
        points,
        (100.0, 100.0),
        (0.1, 0.1),
        (50.0, 50.0),
    )

    assert corrected == ((50.0, 50.0), (61.0, 50.0), (50.0, 61.0))
    assert points == original


def test_ac5_correction_magnitude_increases_toward_edge() -> None:
    points = ((55.0, 50.0), (70.0, 50.0), (90.0, 50.0))
    corrected = undistort_points(
        points,
        (100.0, 100.0),
        (0.0, 0.1, 0.2),
        (50.0, 50.0),
    )
    shifts = [abs(after[0] - before[0]) for before, after in zip(points, corrected)]

    assert shifts[0] < shifts[1] < shifts[2]


def test_ac6_accepts_james_iphone_42_entry_table_at_exact_and_interpolated_radii() -> None:
    table = tuple(index / 1000.0 for index in range(42))
    radius_max = hypot(50.0, 50.0)
    exact_radius = radius_max * 20.0 / 41.0
    interpolated_radius = radius_max * 20.5 / 41.0

    exact = undistort_point(
        (50.0 + exact_radius, 50.0),
        (100.0, 100.0),
        table,
        (50.0, 50.0),
    )
    interpolated = undistort_point(
        (50.0 + interpolated_radius, 50.0),
        (100.0, 100.0),
        table,
        (50.0, 50.0),
    )

    assert exact == pytest.approx((50.0 + exact_radius * 1.020, 50.0))
    assert interpolated == pytest.approx(
        (50.0 + interpolated_radius * 1.0205, 50.0)
    )


@pytest.mark.parametrize(
    ("point", "image_size", "table", "center", "message"),
    [
        ((1.0, 1.0), (100.0, 100.0), (0.0,), (50.0, 50.0), "at least two"),
        ((1.0, 1.0), (0.0, 100.0), (0.0, 0.1), (50.0, 50.0), "positive"),
        ((float("nan"), 1.0), (100.0, 100.0), (0.0, 0.1), (50.0, 50.0), "point"),
        ((1.0, 1.0), (float("inf"), 100.0), (0.0, 0.1), (50.0, 50.0), "image_size"),
        ((1.0, 1.0), (100.0, 100.0), (0.0, float("nan")), (50.0, 50.0), "table"),
        ((1.0, 1.0), (100.0, 100.0), (0.0, 0.1), (float("inf"), 50.0), "center"),
    ],
)
def test_ac7_invalid_inputs_raise_typed_error(
    point: tuple[float, float],
    image_size: tuple[float, float],
    table: tuple[float, ...],
    center: tuple[float, float],
    message: str,
) -> None:
    with pytest.raises(DistortionError, match=message):
        undistort_point(point, image_size, table, center)
