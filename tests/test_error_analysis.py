"""Executable notebook and figure contract for TICK-100 (#70)."""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from frontdoor.error_analysis import ErrorAnalysisError, generate_figures
from frontdoor.screening import CRITERIA_KEYS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUDGET_PATH = PROJECT_ROOT / "docs" / "rise-error-budget.json"
NOTEBOOK_PATH = PROJECT_ROOT / "notebooks" / "error_analysis.py"


def _criterion_metrics(index: int) -> dict[str, int | float]:
    correct = 7 + index
    wrong = 2
    abstained = 1
    scored = correct + wrong + abstained
    return {
        "correct": correct,
        "wrong": wrong,
        "abstained": abstained,
        "not_visible": 1,
        "unlabeled": 0,
        "accuracy_of_committed": correct / (correct + wrong),
        "abstention_rate": abstained / scored,
        "not_visible_rate": 1 / scored,
    }


def _condition_metrics(index: int) -> dict[str, int | float | bool | str]:
    entrance_count = 2 + index
    return {
        "analysis": "exploratory",
        "capture_count": 4,
        "entrance_count": entrance_count,
        "underpowered": entrance_count < 3,
        "correct": 3,
        "wrong": 1,
        "abstained": 0,
        "accuracy_of_committed": 0.75,
        "abstention_rate": 0.0,
    }


def _report() -> dict[str, object]:
    dimensions: dict[str, object] = {}
    for dimension, group_names in {
        "distance_m": ("2.5", "10.0"),
        "lighting": ("direct sun",),
        "occlusion": ("none",),
    }.items():
        dimensions[dimension] = {
            "analysis": "exploratory",
            "groups": {
                group_name: {
                    "analysis": "exploratory",
                    "capture_count": 4,
                    "entrance_count": 4,
                    "criteria": {
                        criterion: _condition_metrics(index)
                        for index, criterion in enumerate(CRITERIA_KEYS)
                    },
                }
                for group_name in group_names
            },
        }
    return {
        "split": "dev",
        "criteria": {
            criterion: _criterion_metrics(index)
            for index, criterion in enumerate(CRITERIA_KEYS)
        },
        "condition_analysis": {
            "analysis": "exploratory",
            "interpretation": "descriptive associations only; not causal",
            "minimum_entrances": 3,
            "dimensions": dimensions,
            "joins": [],
        },
    }


def _write_report(path: Path) -> Path:
    path.write_text(json.dumps(_report()), encoding="utf-8")
    return path


def test_notebook_runs_top_to_bottom_without_sealed_access(tmp_path: Path) -> None:
    report = _write_report(tmp_path / "screening_eval.json")
    output = tmp_path / "figures"

    completed = subprocess.run(
        [
            sys.executable,
            str(NOTEBOOK_PATH),
            "--report",
            str(report),
            "--budget",
            str(BUDGET_PATH),
            "--out",
            str(output),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--include-sealed" not in NOTEBOOK_PATH.read_text(encoding="utf-8")
    assert sorted(path.name for path in output.iterdir()) == [
        "analysis_manifest.json",
        "condition_distance_m.svg",
        "condition_lighting.svg",
        "condition_occlusion.svg",
        "criterion_accuracy.svg",
        "predicted_rise_error_vs_angle.svg",
    ]


def test_figures_are_identical_across_two_regenerations(tmp_path: Path) -> None:
    report = _write_report(tmp_path / "screening_eval.json")
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_paths = generate_figures(report, BUDGET_PATH, first)
    second_paths = generate_figures(report, BUDGET_PATH, second)

    assert [path.name for path in first_paths] == [path.name for path in second_paths]
    for first_path, second_path in zip(first_paths, second_paths):
        assert first_path.read_bytes() == second_path.read_bytes()


def test_observed_figures_label_dev_as_exploratory_and_show_sample_sizes(
    tmp_path: Path,
) -> None:
    output = tmp_path / "figures"
    generate_figures(
        _write_report(tmp_path / "screening_eval.json"), BUDGET_PATH, output
    )

    criterion = (output / "criterion_accuracy.svg").read_text(encoding="utf-8")
    assert "EXPLORATORY — Per-criterion screening results" in criterion
    assert "accuracy" in criterion
    assert "not visible" in criterion
    assert criterion.count("labeled pairs") == len(CRITERIA_KEYS)
    assert "Ramp or beveled threshold: n=10, accuracy 77.8%, not visible 10.0%" in criterion

    distance = (output / "condition_distance_m.svg").read_text(encoding="utf-8")
    lighting = (output / "condition_lighting.svg").read_text(encoding="utf-8")
    occlusion = (output / "condition_occlusion.svg").read_text(encoding="utf-8")
    for figure in (distance, lighting, occlusion):
        assert "EXPLORATORY" in figure
        assert "Descriptive association only; not causal" in figure
        assert figure.count("n=") >= len(CRITERIA_KEYS)
        assert "UNDERPOWERED (minimum n=3)" in figure
        assert "underpowered, accuracy 75.0%, abstention 0.0%" in figure
    assert distance.index("2.5 ·") < distance.index("10.0 ·")


def test_prediction_uses_committed_pre_data_values_and_labels_itself(
    tmp_path: Path,
) -> None:
    output = tmp_path / "figures"
    generate_figures(
        _write_report(tmp_path / "screening_eval.json"), BUDGET_PATH, output
    )

    prediction = (output / "predicted_rise_error_vs_angle.svg").read_text(
        encoding="utf-8"
    )
    assert "PREDICTED — PRE-DATA" in prediction
    assert "not an observed result" in prediction
    assert "TICK-041 (#35)" in prediction
    assert "TICK-234 (#138)" in prediction
    assert "TICK-244 (#159)" in prediction
    assert "0.192″" in prediction
    assert "0.415″" in prediction
    assert "f=2934.1" in prediction
    assert "f=2807.7" in prediction
    assert "superseded architecture example" in prediction
    assert "measured on James&#x27;s iPhone 17 Pro" in prediction


def test_notebook_contains_no_metric_arithmetic() -> None:
    tree = ast.parse(NOTEBOOK_PATH.read_text(encoding="utf-8"))

    assert not [node for node in ast.walk(tree) if isinstance(node, ast.BinOp)]
    assert "frontdoor.screening_eval" not in NOTEBOOK_PATH.read_text(encoding="utf-8")


def test_generator_rejects_condition_data_not_marked_exploratory(
    tmp_path: Path,
) -> None:
    report = _report()
    condition = report["condition_analysis"]
    assert isinstance(condition, dict)
    condition["analysis"] = "causal"
    report_path = tmp_path / "screening_eval.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ErrorAnalysisError, match="must be labeled exploratory"):
        generate_figures(report_path, BUDGET_PATH, tmp_path / "figures")


@pytest.mark.parametrize("split", ["sealed", "calib", "mystery"])
def test_generator_rejects_every_non_dev_split(tmp_path: Path, split: str) -> None:
    report = _report()
    report["split"] = split
    report_path = tmp_path / "screening_eval.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ErrorAnalysisError, match="accepts only the dev split"):
        generate_figures(report_path, BUDGET_PATH, tmp_path / "figures")

    assert not (tmp_path / "figures").exists()


def test_prediction_uses_tap_error_from_the_artifact(tmp_path: Path) -> None:
    budget = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
    budget["tap_error_px"] = 9
    budget_path = tmp_path / "budget.json"
    budget_path.write_text(json.dumps(budget), encoding="utf-8")
    output = tmp_path / "figures"

    generate_figures(
        _write_report(tmp_path / "screening_eval.json"), budget_path, output
    )

    prediction = (output / "predicted_rise_error_vs_angle.svg").read_text(
        encoding="utf-8"
    )
    assert "δ = 9 px" in prediction
    assert "Tap error is 9 pixels" in prediction
