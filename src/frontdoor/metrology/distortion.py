"""Rectify image points with Apple's radial lens-distortion lookup table.

Apple defines ``lensDistortionLookupTable`` as relative radial magnification
sampled evenly from ``lensDistortionCenter`` to the farthest image corner.  The
interpolation and magnification below follow Apple's documented
``LensDistortionData`` point-undistortion example:
https://developer.apple.com/documentation/realitykit/lensdistortiondata

The utility works on points only.  It does not resample images or read sidecars.
"""

from __future__ import annotations

from math import hypot, isfinite
from typing import Sequence, TypeAlias

Point: TypeAlias = tuple[float, float]
ImageSize: TypeAlias = tuple[float, float]


class DistortionError(ValueError):
    """The supplied calibration data cannot define a distortion correction."""


def _validate_pair(name: str, value: Point) -> None:
    if not all(isfinite(component) for component in value):
        raise DistortionError(f"{name} must contain only finite values")


def _validate_calibration(
    image_size: ImageSize,
    distortion_table: Sequence[float],
    distortion_center: Point,
) -> tuple[float, float, tuple[float, ...], float]:
    _validate_pair("image_size", image_size)
    width, height = image_size
    if width <= 0 or height <= 0:
        raise DistortionError("image dimensions must be positive")

    _validate_pair("distortion_center", distortion_center)
    table = tuple(distortion_table)
    if len(table) < 2:
        raise DistortionError("distortion table must contain at least two entries")
    if not all(isfinite(value) for value in table):
        raise DistortionError("distortion table must contain only finite values")

    center_x, center_y = distortion_center
    radius_max = hypot(
        max(center_x, width - center_x),
        max(center_y, height - center_y),
    )
    if radius_max == 0:
        raise DistortionError("image dimensions and distortion center define no usable radius")
    return center_x, center_y, table, radius_max


def _undistort_validated(
    point: Point,
    center_x: float,
    center_y: float,
    table: tuple[float, ...],
    radius_max: float,
) -> Point:
    _validate_pair("point", point)
    delta_x = point[0] - center_x
    delta_y = point[1] - center_y
    radius = hypot(delta_x, delta_y)

    if radius >= radius_max:
        magnification = table[-1]
    else:
        table_position = radius * (len(table) - 1) / radius_max
        left_index = int(table_position)
        fraction = table_position - left_index
        magnification = (
            (1.0 - fraction) * table[left_index]
            + fraction * table[left_index + 1]
        )

    scale = 1.0 + magnification
    return center_x + scale * delta_x, center_y + scale * delta_y


def undistort_point(
    point: Point,
    image_size: ImageSize,
    distortion_table: Sequence[float],
    distortion_center: Point,
) -> Point:
    """Map one distorted image point into rectified pixel coordinates."""

    center_x, center_y, table, radius_max = _validate_calibration(
        image_size, distortion_table, distortion_center
    )
    return _undistort_validated(point, center_x, center_y, table, radius_max)


def undistort_points(
    points: Sequence[Point],
    image_size: ImageSize,
    distortion_table: Sequence[float],
    distortion_center: Point,
) -> tuple[Point, ...]:
    """Rectify an ordered collection of points without mutating it."""

    center_x, center_y, table, radius_max = _validate_calibration(
        image_size, distortion_table, distortion_center
    )
    return tuple(
        _undistort_validated(point, center_x, center_y, table, radius_max)
        for point in points
    )
