"""Deterministic figures from screening-evaluation output (TICK-100, #70).

This module reads only the JSON artifact written by ``frontdoor.screening_eval``
and the committed pre-data prediction table. It does not import the evaluation
runner, manifests, labels, capture storage, or seal machinery.
"""

from __future__ import annotations

import html
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypeAlias

from frontdoor.screening import CRITERIA_KEYS

JSONValue: TypeAlias = (
    None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
)

WIDTH = 960
LEFT = 410
BAR_WIDTH = 390
ROW_HEIGHT = 58
COLORS = ("#1565c0", "#ef6c00", "#2e7d32", "#6a1b9a")

CRITERION_LABELS = {
    "ramp_or_bevel": "Ramp or beveled threshold",
    "handrails": "Handrails",
    "accessible_door_hardware": "Accessible door hardware",
    "accessibility_signage": "Accessibility signage",
}


class ErrorAnalysisError(ValueError):
    """Raised when an input artifact cannot support trustworthy figures."""


def _load_object(path: Path, description: str) -> dict[str, JSONValue]:
    try:
        with path.open(encoding="utf-8") as handle:
            value: JSONValue = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ErrorAnalysisError(f"cannot read {description} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ErrorAnalysisError(f"{description} must be a JSON object: {path}")
    return value


def _mapping(value: JSONValue, field: str) -> Mapping[str, JSONValue]:
    if not isinstance(value, dict):
        raise ErrorAnalysisError(f"{field} must be an object")
    return value


def _sequence(value: JSONValue, field: str) -> Sequence[JSONValue]:
    if not isinstance(value, list):
        raise ErrorAnalysisError(f"{field} must be an array")
    return value


def _text(value: JSONValue, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ErrorAnalysisError(f"{field} must be a non-empty string")
    return value


def _count(value: JSONValue, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ErrorAnalysisError(f"{field} must be a non-negative integer")
    return value


def _boolean(value: JSONValue, field: str) -> bool:
    if not isinstance(value, bool):
        raise ErrorAnalysisError(f"{field} must be a boolean")
    return value


def _rate(value: JSONValue, field: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ErrorAnalysisError(f"{field} must be a number or null")
    rate = float(value)
    if not 0.0 <= rate <= 1.0:
        raise ErrorAnalysisError(f"{field} must be between zero and one")
    return rate


def _number(value: JSONValue, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ErrorAnalysisError(f"{field} must be a number")
    return float(value)


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _svg_document(
    title: str,
    subtitle: str,
    description: str,
    height: int,
    body: Sequence[str],
) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
            f'viewBox="0 0 {WIDTH} {height}" role="img" aria-labelledby="title desc">',
            f"<title id=\"title\">{_escape(title)}</title>",
            f"<desc id=\"desc\">{_escape(description)}</desc>",
            '<rect width="100%" height="100%" fill="#ffffff"/>',
            '<style>text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}'
            ".title{font-size:24px;font-weight:700}.subtitle{font-size:14px;fill:#444}"
            ".label{font-size:14px;fill:#111}.small{font-size:12px;fill:#444}"
            ".axis{stroke:#999;stroke-width:1}</style>",
            f'<text class="title" x="30" y="38">{_escape(title)}</text>',
            f'<text class="subtitle" x="30" y="62">{_escape(subtitle)}</text>',
            *body,
            "</svg>",
            "",
        ]
    )


def _bar(x: int, y: int, rate: float | None, color: str) -> list[str]:
    width = 0 if rate is None else round(BAR_WIDTH * rate)
    label = "n/a" if rate is None else f"{rate:.1%}"
    return [
        f'<rect x="{x}" y="{y}" width="{BAR_WIDTH}" height="16" fill="#eeeeee" rx="2"/>',
        f'<rect x="{x}" y="{y}" width="{width}" height="16" fill="{color}" rx="2"/>',
        f'<text class="small" x="{x + BAR_WIDTH + 12}" y="{y + 13}">{label}</text>',
    ]


def _criterion_figure(report: Mapping[str, JSONValue]) -> str:
    split = _text(report.get("split"), "split")
    criteria = _mapping(report.get("criteria"), "criteria")
    body: list[str] = []
    descriptions: list[str] = []
    for index, criterion in enumerate(CRITERIA_KEYS):
        metrics = _mapping(criteria.get(criterion), f"criteria.{criterion}")
        correct = _count(metrics.get("correct"), f"criteria.{criterion}.correct")
        wrong = _count(metrics.get("wrong"), f"criteria.{criterion}.wrong")
        abstained = _count(metrics.get("abstained"), f"criteria.{criterion}.abstained")
        scored = correct + wrong + abstained
        accuracy = _rate(
            metrics.get("accuracy_of_committed"),
            f"criteria.{criterion}.accuracy_of_committed",
        )
        not_visible = _rate(
            metrics.get("not_visible_rate"), f"criteria.{criterion}.not_visible_rate"
        )
        descriptions.append(
            f"{CRITERION_LABELS[criterion]}: n={scored}, accuracy "
            f"{'not available' if accuracy is None else f'{accuracy:.1%}'}, not visible "
            f"{'not available' if not_visible is None else f'{not_visible:.1%}'}"
        )
        y = 102 + index * (ROW_HEIGHT * 2)
        body.extend(
            [
                f'<text class="label" x="30" y="{y + 13}">'
                f"{_escape(CRITERION_LABELS[criterion])}</text>",
                f'<text class="small" x="30" y="{y + 34}">n={scored} labeled pairs</text>',
                f'<text class="small" x="{LEFT - 76}" y="{y + 13}">accuracy</text>',
                *_bar(LEFT, y, accuracy, COLORS[0]),
                f'<text class="small" x="{LEFT - 76}" y="{y + 42}">not visible</text>',
                *_bar(LEFT, y + 29, not_visible, COLORS[1]),
            ]
        )
    title_prefix = "EXPLORATORY — " if split == "dev" else ""
    return _svg_document(
        f"{title_prefix}Per-criterion screening results",
        f"{split} split; accuracy is over committed verdicts; sample sizes include abstentions",
        "; ".join(descriptions) + ".",
        118 + len(CRITERIA_KEYS) * ROW_HEIGHT * 2,
        body,
    )


def _condition_sort(dimension: str, item: tuple[str, JSONValue]) -> tuple[int, float | str]:
    key = item[0]
    if dimension == "distance_m":
        try:
            return (0, float(key))
        except ValueError as exc:
            raise ErrorAnalysisError(f"condition distance {key!r} is not numeric") from exc
    return (1, key)


def _condition_figure(
    dimension: str,
    dimension_data: Mapping[str, JSONValue],
    minimum_entrances: int,
) -> str:
    if dimension_data.get("analysis") != "exploratory":
        raise ErrorAnalysisError(f"condition_analysis.{dimension} is not exploratory")
    groups = _mapping(dimension_data.get("groups"), f"condition_analysis.{dimension}.groups")
    rows: list[tuple[str, str, int, bool, float | None, float | None]] = []
    for group_name, raw_group in sorted(
        groups.items(), key=lambda item: _condition_sort(dimension, item)
    ):
        group = _mapping(raw_group, f"condition_analysis.{dimension}.{group_name}")
        criteria = _mapping(
            group.get("criteria"), f"condition_analysis.{dimension}.{group_name}.criteria"
        )
        for criterion in CRITERIA_KEYS:
            metrics = _mapping(criteria.get(criterion), f"{dimension}.{group_name}.{criterion}")
            entrances = _count(metrics.get("entrance_count"), "entrance_count")
            underpowered = _boolean(metrics.get("underpowered"), "underpowered")
            if underpowered != (entrances < minimum_entrances):
                raise ErrorAnalysisError(
                    f"{dimension}.{group_name}.{criterion}.underpowered disagrees with "
                    f"minimum_entrances={minimum_entrances}"
                )
            accuracy = _rate(metrics.get("accuracy_of_committed"), "accuracy_of_committed")
            abstention = _rate(metrics.get("abstention_rate"), "abstention_rate")
            rows.append(
                (group_name, criterion, entrances, underpowered, accuracy, abstention)
            )
    body: list[str] = []
    descriptions: list[str] = []
    for index, (
        group_name,
        criterion,
        entrances,
        underpowered,
        accuracy,
        abstention,
    ) in enumerate(rows):
        y = 100 + index * ROW_HEIGHT
        power_label = (
            f" · UNDERPOWERED (minimum n={minimum_entrances})" if underpowered else ""
        )
        descriptions.append(
            f"{group_name}, {CRITERION_LABELS[criterion]}: n={entrances} entrances"
            f"{' underpowered' if underpowered else ''}, accuracy "
            f"{'not available' if accuracy is None else f'{accuracy:.1%}'}, abstention "
            f"{'not available' if abstention is None else f'{abstention:.1%}'}"
        )
        body.extend(
            [
                f'<text class="label" x="30" y="{y + 13}">'
                f"{_escape(group_name)} · {_escape(CRITERION_LABELS[criterion])}</text>",
                f'<text class="small" x="30" y="{y + 34}">'
                f"n={entrances} entrances{power_label}</text>",
                *_bar(LEFT, y, accuracy, COLORS[0]),
                *_bar(LEFT, y + 23, abstention, COLORS[1]),
                f'<text class="small" x="{LEFT - 70}" y="{y + 13}">accuracy</text>',
                f'<text class="small" x="{LEFT - 70}" y="{y + 36}">abstain</text>',
            ]
        )
    return _svg_document(
        f"EXPLORATORY — screening by {dimension}",
        f"Descriptive association only; not causal. Underpowered means fewer than {minimum_entrances} entrances.",
        "; ".join(descriptions) + ".",
        116 + len(rows) * ROW_HEIGHT,
        body,
    )


def _prediction_figure(budget: Mapping[str, JSONValue]) -> str:
    status = _text(budget.get("status"), "budget.status")
    sources = [_text(value, "budget.sources[]") for value in _sequence(budget.get("sources"), "budget.sources")]
    source_ids = ", ".join(source.split(":", 1)[0] for source in sources)
    tap_error_px = _number(budget.get("tap_error_px"), "budget.tap_error_px")
    if tap_error_px <= 0:
        raise ErrorAnalysisError("budget.tap_error_px must be greater than zero")
    series = _sequence(budget.get("series"), "budget.series")
    plot_left, plot_top, plot_width, plot_height = 90, 115, 620, 340
    body = [
        f'<line class="axis" x1="{plot_left}" y1="{plot_top + plot_height}" '
        f'x2="{plot_left + plot_width}" y2="{plot_top + plot_height}"/>',
        f'<line class="axis" x1="{plot_left}" y1="{plot_top}" '
        f'x2="{plot_left}" y2="{plot_top + plot_height}"/>',
    ]
    for tick in range(5):
        angle = tick * 15
        x = plot_left + round(plot_width * angle / 60)
        body.append(f'<text class="small" x="{x - 8}" y="{plot_top + plot_height + 22}">{angle}°</text>')
    for tick in range(5):
        value = tick / 10
        y = plot_top + plot_height - round(plot_height * value / 0.5)
        body.extend(
            [
                f'<line x1="{plot_left}" y1="{y}" x2="{plot_left + plot_width}" y2="{y}" stroke="#eeeeee"/>',
                f'<text class="small" x="42" y="{y + 4}">{value:.1f}″</text>',
            ]
        )
    descriptions: list[str] = []
    for index, raw_series in enumerate(series):
        item = _mapping(raw_series, f"budget.series[{index}]")
        label = _text(item.get("label"), f"budget.series[{index}].label")
        focal_length = _number(
            item.get("focal_length_px"), f"budget.series[{index}].focal_length_px"
        )
        focal_status = _text(
            item.get("focal_status"), f"budget.series[{index}].focal_status"
        )
        if focal_length <= 0:
            raise ErrorAnalysisError("prediction focal length must be greater than zero")
        points = _sequence(item.get("points"), f"budget.series[{index}].points")
        coordinates: list[tuple[int, int, float, float]] = []
        for point_index, raw_point in enumerate(points):
            point = _sequence(raw_point, f"budget.series[{index}].points[{point_index}]")
            if len(point) != 2:
                raise ErrorAnalysisError("each prediction point must contain angle and error")
            angle = _number(point[0], "prediction angle")
            error = _number(point[1], "prediction error")
            if not 0 <= angle <= 60 or not 0 <= error <= 0.5:
                raise ErrorAnalysisError("prediction point is outside the chart domain")
            coordinates.append(
                (
                    plot_left + round(plot_width * angle / 60),
                    plot_top + plot_height - round(plot_height * error / 0.5),
                    angle,
                    error,
                )
            )
        descriptions.append(
            f"{label}, focal length {focal_length:g} pixels ({focal_status}): "
            + ", ".join(f"{angle:g} degrees {error:.3f} inches" for _, _, angle, error in coordinates)
        )
        color = COLORS[index % len(COLORS)]
        joined = " ".join(f"{x},{y}" for x, y, _, _ in coordinates)
        body.append(f'<polyline points="{joined}" fill="none" stroke="{color}" stroke-width="3"/>')
        label_offsets = ((-8, 17), (7, -8), (-8, 17), (7, -8))
        label_dx, label_dy = label_offsets[index % len(label_offsets)]
        for x, y, _, error in coordinates:
            body.extend(
                [
                    f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/>',
                    f'<text class="small" x="{x + label_dx}" y="{y + label_dy}">{error:.3f}″</text>',
                ]
            )
        legend_y = 130 + index * 28
        body.extend(
            [
                f'<line x1="745" y1="{legend_y}" x2="777" y2="{legend_y}" stroke="{color}" stroke-width="3"/>',
                f'<text class="small" x="787" y="{legend_y + 4}">'
                f"{_escape(label)} · f={focal_length:g}</text>",
            ]
        )
    body.extend(
        [
            '<text class="small" x="90" y="492">capture angle</text>',
            f'<text class="small" x="745" y="262">rise error (inches)</text>',
            f'<text class="small" x="90" y="514">Sources: {_escape(source_ids)}.</text>',
            f'<text class="small" x="90" y="536">δ = {tap_error_px:g} px; values are published inputs, not fitted to labels.</text>',
        ]
    )
    return _svg_document(
        "PREDICTED — PRE-DATA rise error versus angle",
        f"{status}; analytical f=2934.1 example, 3D f=2807.7 measured",
        "; ".join(descriptions) + f". Tap error is {tap_error_px:g} pixels.",
        565,
        body,
    )


def generate_figures(report_path: Path, budget_path: Path, output_dir: Path) -> tuple[Path, ...]:
    """Generate all TICK-100 figures from two explicit, non-image artifacts."""
    report = _load_object(report_path, "screening evaluation report")
    budget = _load_object(budget_path, "predicted rise-error budget")
    split = _text(report.get("split"), "split")
    if split != "dev":
        raise ErrorAnalysisError(
            f"error-analysis notebook accepts only the dev split, not {split!r}"
        )
    condition_analysis = _mapping(report.get("condition_analysis"), "condition_analysis")
    if condition_analysis.get("analysis") != "exploratory":
        raise ErrorAnalysisError("condition_analysis must be labeled exploratory")
    dimensions = _mapping(condition_analysis.get("dimensions"), "condition_analysis.dimensions")
    minimum_entrances = _count(
        condition_analysis.get("minimum_entrances"),
        "condition_analysis.minimum_entrances",
    )
    if minimum_entrances == 0:
        raise ErrorAnalysisError("condition_analysis.minimum_entrances must be positive")

    figures: list[tuple[str, str]] = [
        ("criterion_accuracy.svg", _criterion_figure(report)),
        ("predicted_rise_error_vs_angle.svg", _prediction_figure(budget)),
    ]
    for dimension in ("distance_m", "lighting", "occlusion"):
        figures.append(
            (
                f"condition_{dimension}.svg",
                _condition_figure(
                    dimension,
                    _mapping(dimensions.get(dimension), f"condition_analysis.{dimension}"),
                    minimum_entrances,
                ),
            )
        )

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for name, content in figures:
            path = output_dir / name
            path.write_text(content, encoding="utf-8", newline="\n")
            written.append(path)
        manifest = {
            "analysis": "presentation of harness metrics; no metric recomputation",
            "prediction": _text(budget.get("status"), "budget.status"),
            "report_split": _text(report.get("split"), "split"),
            "figures": [path.name for path in written],
        }
        manifest_path = output_dir / "analysis_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written.append(manifest_path)
    except OSError as exc:
        raise ErrorAnalysisError(f"cannot write figures to {output_dir}: {exc}") from exc
    return tuple(written)
