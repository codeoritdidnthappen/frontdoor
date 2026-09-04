"""Tests for the screening accuracy eval runner (TICK-245, TICK-246).

Fully mocked: a fake engine returns canned EntranceScreening results, and no
test makes a live model call or reads real capture data. Report assertions
parse the written JSON/markdown and check values, not exact bytes.
"""

import csv
import json
from types import SimpleNamespace

import pytest

from frontdoor.labels import COLUMNS as LABEL_COLUMNS
from frontdoor.manifest import COLUMNS as MANIFEST_COLUMNS
from frontdoor.screening import (
    CRITERIA_KEYS,
    CriterionSummary,
    EntranceScreening,
    ImageAssessment,
    ScreeningConfig,
    SealedSplitError,
)
from frontdoor.screening_eval import (
    CONDITION_KEYS,
    LATENCY_BUDGET_S,
    MIN_CONDITION_ENTRANCES,
    ScreeningEvalError,
    _condition_analysis,
    classify,
    collect_entrances,
    entrance_flip_rates,
    latency_stats,
    main,
    run_eval,
    score_joins,
)

# Split known answers under the committed seed (pinned in test_split.py and
# recomputed here): E-001/E-003/E-007 dev, E-002/E-014 sealed, E-042 calib.
DEV_A, DEV_B, DEV_C = "E-001", "E-003", "E-007"
SEALED_ID = "E-014"
CALIB_ID = "E-042"


def _screening(
    entrance_id, verdicts, *, flip_rates=None, latencies=(1.0,),
    assessment_verdicts=None,
):
    """Build an EntranceScreening from {criterion: verdict}.

    Criteria missing from `verdicts` get verdict None (no valid view), whose
    flip_rate is None; committed verdicts default to flip_rate 0.0 unless
    overridden.
    """
    flip_rates = flip_rates or {}
    summary = {}
    for key in CRITERIA_KEYS:
        verdict = verdicts.get(key)
        default_rate = None if verdict is None else 0.0
        summary[key] = CriterionSummary(
            verdict=verdict,
            flip_rate=flip_rates.get(key, default_rate),
            counts={},
        )
    if assessment_verdicts is None:
        assessment_verdicts = [verdicts] * len(latencies)
    assessments = tuple(
        ImageAssessment(
            criteria={
                key: {"verdict": image_verdicts.get(key, "not_visible")}
                for key in CRITERIA_KEYS
            },
            latency_s=latency,
            error=None,
        )
        for latency, image_verdicts in zip(latencies, assessment_verdicts)
    )
    return EntranceScreening(
        entrance_id=entrance_id,
        split="dev",
        assessments=assessments,
        summary=summary,
    )


class FakeEngine:
    """Stands in for ScreeningEngine: canned results, spend tracking."""

    def __init__(self, results, *, model="fake-screening-model"):
        self.config = ScreeningConfig(model=model)
        self.spent_usd = 0.0
        self._results = dict(results)
        self.calls = []

    def screen_entrance(self, entrance_id, images):
        self.calls.append((entrance_id, len(images)))
        self.spent_usd += 0.05 * len(images)
        return self._results[entrance_id]


def _write_manifest(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=MANIFEST_COLUMNS, lineterminator="\n"
        )
        writer.writeheader()
        for capture_id, entrance_id in rows:
            writer.writerow(
                {
                    "capture_id": capture_id,
                    "entrance_id": entrance_id,
                    "image_sha256": "0" * 64,
                    "depth_sha256": "",
                    "sidecar_sha256": "0" * 64,
                    "split": "dev",
                }
            )
    return path


def _write_labels(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for entrance_id, criterion, truth in rows:
            writer.writerow(
                {
                    "entrance_id": entrance_id,
                    "criterion": criterion,
                    "truth": truth,
                    "labeled_by": "" if truth == "" else "op-1",
                    "labeled_at": "" if truth == "" else "2026-09-01",
                }
            )
    return path


def _capture(capture_id, *, distance=2.5, lighting="overcast", occlusion="none"):
    return SimpleNamespace(
        capture_id=capture_id,
        image=b"img-" + capture_id.encode("ascii"),
        sidecar={"conditions": {
            "distance_m": distance,
            "lighting": lighting,
            "occlusion": occlusion,
        }},
    )


def _fake_get_capture(capture_id):
    return _capture(capture_id)


# --- join math ---------------------------------------------------------------


def test_classify_each_outcome_class():
    assert classify("present", "present") == "correct"
    assert classify("absent", "absent") == "correct"
    assert classify("present", "absent") == "wrong"
    assert classify("absent", "present") == "wrong"
    assert classify("not_visible", "present") == "abstained"
    assert classify("not_visible", "absent") == "abstained"
    assert classify(None, "present") == "abstained"


def test_score_joins_counts_per_criterion_and_skips_unlabeled():
    screenings = {
        DEV_A: _screening(DEV_A, {
            "ramp_or_bevel": "present",           # labeled present -> correct
            "handrails": "absent",                # labeled present -> wrong
            "accessible_door_hardware": "not_visible",  # labeled -> abstained
            # accessibility_signage: verdict None, labeled -> abstained
        }),
        DEV_B: _screening(DEV_B, {
            "ramp_or_bevel": "absent",            # labeled absent -> correct
            "handrails": "present",               # unlabeled
        }),
    }
    labels = [
        {"entrance_id": DEV_A, "criterion": "ramp_or_bevel", "truth": "present"},
        {"entrance_id": DEV_A, "criterion": "handrails", "truth": "present"},
        {"entrance_id": DEV_A, "criterion": "accessible_door_hardware", "truth": "absent"},
        {"entrance_id": DEV_A, "criterion": "accessibility_signage", "truth": "present"},
        {"entrance_id": DEV_B, "criterion": "ramp_or_bevel", "truth": "absent"},
        # a label for an entrance that was never screened is ignored
        {"entrance_id": DEV_C, "criterion": "handrails", "truth": "present"},
    ]
    per_criterion, joins = score_joins(screenings, labels)
    assert per_criterion["ramp_or_bevel"] == {
        "correct": 2, "wrong": 0, "abstained": 0, "unlabeled": 0,
    }
    assert per_criterion["handrails"] == {
        "correct": 0, "wrong": 1, "abstained": 0, "unlabeled": 1,
    }
    assert per_criterion["accessible_door_hardware"] == {
        "correct": 0, "wrong": 0, "abstained": 1, "unlabeled": 1,
    }
    assert per_criterion["accessibility_signage"] == {
        "correct": 0, "wrong": 0, "abstained": 1, "unlabeled": 1,
    }
    assert len(joins) == 5
    assert all(join["entrance_id"] != DEV_C for join in joins)


def test_abstentions_are_scored_separately_never_correct_or_wrong():
    screenings = {
        DEV_A: _screening(DEV_A, {"ramp_or_bevel": "not_visible"}),
    }
    labels = [
        {"entrance_id": DEV_A, "criterion": "ramp_or_bevel", "truth": "absent"},
        {"entrance_id": DEV_A, "criterion": "handrails", "truth": "present"},
    ]
    per_criterion, joins = score_joins(screenings, labels)
    # not_visible against a real truth is an abstention, not a miss ...
    assert per_criterion["ramp_or_bevel"]["abstained"] == 1
    assert per_criterion["ramp_or_bevel"]["wrong"] == 0
    # ... and so is a criterion with no valid verdict at all.
    assert per_criterion["handrails"]["abstained"] == 1
    outcomes = {(j["criterion"]): j["outcome"] for j in joins}
    assert outcomes == {"ramp_or_bevel": "abstained", "handrails": "abstained"}


# --- flip rate and latency ---------------------------------------------------


def test_entrance_flip_rates_mean_over_criteria_with_verdicts():
    screenings = {
        DEV_A: _screening(
            DEV_A,
            {"ramp_or_bevel": "present", "handrails": "absent"},
            flip_rates={"ramp_or_bevel": 0.4, "handrails": 0.2},
        ),
        DEV_B: _screening(DEV_B, {}),  # no valid verdict on any criterion
    }
    rates = entrance_flip_rates(screenings)
    assert rates[DEV_A] == pytest.approx(0.3)
    assert rates[DEV_B] is None


def test_latency_stats_and_over_budget_count():
    screenings = {
        DEV_A: _screening(DEV_A, {}, latencies=(1.0, 2.0, 3.0)),
        DEV_B: _screening(DEV_B, {}, latencies=(4.0, 16.5)),
    }
    stats = latency_stats(screenings)
    assert stats["count"] == 5
    assert stats["min"] == 1.0
    assert stats["median"] == 3.0
    assert stats["p95"] == 16.5
    assert stats["max"] == 16.5
    assert stats["over_budget"] == 1
    assert stats["budget_s"] == LATENCY_BUDGET_S


def test_latency_stats_with_no_recorded_latencies():
    screenings = {DEV_A: _screening(DEV_A, {}, latencies=())}
    stats = latency_stats(screenings)
    assert stats["count"] == 0
    assert stats["min"] is None and stats["max"] is None
    assert stats["over_budget"] == 0


# --- split discipline --------------------------------------------------------


def test_sealed_split_is_refused_before_any_file_is_touched(tmp_path):
    def _boom(capture_id):
        raise AssertionError("no image should be read")

    with pytest.raises(SealedSplitError, match="audited"):
        run_eval(
            manifest_path=tmp_path / "does-not-exist.csv",
            labels_path=tmp_path / "does-not-exist-either.csv",
            out_dir=tmp_path / "out",
            engine=FakeEngine({}),
            get_capture=_boom,
            split="sealed",
        )
    assert not (tmp_path / "out").exists()


def test_unknown_split_is_an_error_not_an_empty_report(tmp_path):
    with pytest.raises(ScreeningEvalError, match="unknown split"):
        collect_entrances(tmp_path / "irrelevant.csv", split="devv")


def test_collect_entrances_filters_to_the_dev_split(tmp_path):
    manifest = _write_manifest(
        tmp_path / "manifest.csv",
        [
            ("cap-3", DEV_B),
            ("cap-1", DEV_A),
            ("cap-2", DEV_A),
            ("cap-4", SEALED_ID),
            ("cap-5", CALIB_ID),
        ],
    )
    entrances = collect_entrances(manifest)
    assert entrances == {DEV_A: ["cap-1", "cap-2"], DEV_B: ["cap-3"]}
    assert list(entrances) == sorted(entrances)


def test_run_eval_never_hands_sealed_or_calib_entrances_to_the_engine(tmp_path):
    manifest = _write_manifest(
        tmp_path / "manifest.csv",
        [("cap-1", DEV_A), ("cap-2", SEALED_ID), ("cap-3", CALIB_ID)],
    )
    labels = _write_labels(
        tmp_path / "labels.csv",
        [(DEV_A, "ramp_or_bevel", "present")],
    )
    engine = FakeEngine({DEV_A: _screening(DEV_A, {"ramp_or_bevel": "present"})})
    run_eval(
        manifest_path=manifest,
        labels_path=labels,
        out_dir=tmp_path / "out",
        engine=engine,
        get_capture=_fake_get_capture,
    )
    assert engine.calls == [(DEV_A, 1)]


# --- end-to-end report -------------------------------------------------------


def _run_report(tmp_path):
    manifest = _write_manifest(
        tmp_path / "manifest.csv",
        [
            ("cap-1", DEV_A),
            ("cap-2", DEV_A),
            ("cap-3", DEV_B),
            ("cap-4", SEALED_ID),  # filtered out, never screened
        ],
    )
    labels = _write_labels(
        tmp_path / "labels.csv",
        [
            (DEV_A, "ramp_or_bevel", "present"),
            (DEV_A, "handrails", "absent"),
            (DEV_A, "accessible_door_hardware", "present"),
            (DEV_A, "accessibility_signage", ""),  # blank: operator could not observe
            (DEV_B, "ramp_or_bevel", "absent"),
            (DEV_B, "handrails", "absent"),
            (SEALED_ID, "ramp_or_bevel", "present"),  # sealed label: filtered out
        ],
    )
    engine = FakeEngine(
        {
            DEV_A: _screening(
                DEV_A,
                {
                    "ramp_or_bevel": "present",            # correct
                    "handrails": "present",                # wrong
                    "accessible_door_hardware": "not_visible",  # abstained
                },
                flip_rates={"ramp_or_bevel": 0.5, "handrails": 0.0,
                            "accessible_door_hardware": 0.0},
                latencies=(2.0, 16.0),
                assessment_verdicts=(
                    {
                        "ramp_or_bevel": "present",
                        "handrails": "present",
                        "accessible_door_hardware": "present",
                    },
                    {
                        "ramp_or_bevel": "absent",
                        "handrails": "present",
                        "accessible_door_hardware": "not_visible",
                    },
                ),
            ),
            DEV_B: _screening(
                DEV_B,
                {"ramp_or_bevel": "absent", "handrails": "absent"},  # both correct
                latencies=(4.0,),
            ),
        }
    )
    captures = {
        "cap-1": _capture(
            "cap-1", distance=1.5, lighting="overcast", occlusion="none"
        ),
        "cap-2": _capture(
            "cap-2", distance=3.5, lighting="low_light", occlusion="partial"
        ),
        "cap-3": _capture(
            "cap-3", distance=1.5, lighting="overcast", occlusion="none"
        ),
    }
    result = run_eval(
        manifest_path=manifest,
        labels_path=labels,
        out_dir=tmp_path / "out",
        engine=engine,
        get_capture=captures.__getitem__,
    )
    return result, tmp_path / "out"


def test_report_json_values(tmp_path):
    result, out_dir = _run_report(tmp_path)
    written = json.loads((out_dir / "screening_eval.json").read_text(encoding="utf-8"))
    assert written == result
    assert written["split"] == "dev"

    ramp = written["criteria"]["ramp_or_bevel"]
    assert ramp["correct"] == 2 and ramp["wrong"] == 0 and ramp["abstained"] == 0
    assert ramp["accuracy_of_committed"] == 1.0
    hand = written["criteria"]["handrails"]
    assert hand["correct"] == 1 and hand["wrong"] == 1
    assert hand["accuracy_of_committed"] == 0.5
    hardware = written["criteria"]["accessible_door_hardware"]
    assert hardware["abstained"] == 1 and hardware["unlabeled"] == 1
    assert hardware["accuracy_of_committed"] is None
    assert hardware["abstention_rate"] == 1.0
    signage = written["criteria"]["accessibility_signage"]
    # blank label row means the pair is unlabeled, never guessed
    assert signage == {
        "correct": 0, "wrong": 0, "abstained": 0, "unlabeled": 2,
        "accuracy_of_committed": None, "abstention_rate": None,
    }

    overall = written["overall"]
    assert overall["correct"] == 3 and overall["wrong"] == 1
    assert overall["abstained"] == 1
    assert overall["accuracy_of_committed"] == pytest.approx(3 / 4)
    assert overall["abstention_rate"] == pytest.approx(1 / 5)

    flips = written["flip_rate"]
    assert flips["per_entrance"][DEV_A] == pytest.approx(0.5 / 3)
    assert flips["per_entrance"][DEV_B] == 0.0
    assert flips["mean"] == pytest.approx(0.5 / 6)

    lat = written["latency_s"]
    assert lat["count"] == 3
    assert lat["min"] == 2.0 and lat["max"] == 16.0
    assert lat["median"] == 4.0
    assert lat["over_budget"] == 1

    run = written["run"]
    assert run["model"] == "fake-screening-model"
    assert run["entrance_count"] == 2
    assert run["image_count"] == 3
    assert run["spend_estimate_usd"] == pytest.approx(0.15)
    assert run["labels_scored"] == 5
    assert run["labels_blank_skipped"] == 1

    conditions = written["condition_analysis"]
    assert conditions["analysis"] == "exploratory"
    assert conditions["interpretation"] == "descriptive associations only; not causal"
    assert conditions["minimum_entrances"] == MIN_CONDITION_ENTRANCES
    assert tuple(conditions["dimensions"]) == CONDITION_KEYS
    distance = conditions["dimensions"]["distance_m"]
    assert list(distance["groups"]) == ["1.5", "3.5"]
    near = distance["groups"]["1.5"]
    assert near["capture_count"] == 2
    assert near["entrance_count"] == 2
    assert near["criteria"]["ramp_or_bevel"]["correct"] == 2
    assert near["criteria"]["ramp_or_bevel"]["underpowered"] is True
    far = distance["groups"]["3.5"]
    assert far["criteria"]["ramp_or_bevel"]["wrong"] == 1
    assert far["criteria"]["accessible_door_hardware"]["abstained"] == 1
    condition_text = json.dumps(conditions)
    assert "surface" not in condition_text
    assert "angle" not in condition_text

    # sealed entrance appears nowhere in the report
    assert SEALED_ID not in json.dumps(written)


def test_report_markdown_carries_the_numbers(tmp_path):
    _, out_dir = _run_report(tmp_path)
    text = (out_dir / "screening_eval.md").read_text(encoding="utf-8")
    assert "# Screening accuracy eval (dev split)" in text
    assert "- model: fake-screening-model" in text
    assert "- images: 3" in text
    assert "- spend estimate: $0.15" in text
    assert "| ramp_or_bevel | 2 | 0 | 0 | 0 | 1.000 |" in text
    assert "| handrails | 1 | 1 | 0 | 0 | 0.500 |" in text
    assert "0.750 (3 correct / 4 committed)" in text
    for dimension in CONDITION_KEYS:
        assert f"## Exploratory condition analysis: {dimension}" in text
    assert text.count("**Exploratory — descriptive associations only; not causal.**") == 3
    assert "| exploratory | 1.5 | ramp_or_bevel | 2 | 2 | underpowered " in text
    assert f"| {DEV_A} | 0.167 |" in text
    assert "| 2.000 | 4.000 | 16.000 | 16.000 | 1 of 3 |" in text
    assert SEALED_ID not in text


def test_report_is_deterministic_across_runs(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _, out_a = _run_report(tmp_path / "a")
    _, out_b = _run_report(tmp_path / "b")
    for name in ("screening_eval.json", "screening_eval.md"):
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes()


def test_joins_are_ordered_by_entrance_then_criterion(tmp_path):
    result, _ = _run_report(tmp_path)
    keys = [(j["entrance_id"], j["criterion"]) for j in result["joins"]]
    order = {key: i for i, key in enumerate(CRITERIA_KEYS)}
    assert keys == sorted(keys, key=lambda pair: (pair[0], order[pair[1]]))


def test_condition_power_uses_distinct_entrances_and_orders_distance_numerically():
    joins = []
    for capture_id, entrance_id, distance, lighting in (
        ("cap-1", "E-001", 10, "overcast"),
        ("cap-2", "E-001", 2.5, "overcast"),
        ("cap-3", "E-003", 2.5, "overcast"),
        ("cap-4", "E-007", 2.5, "overcast"),
        ("cap-5", "E-009", 3, "low_light"),
    ):
        joins.append({
            "capture_id": capture_id,
            "entrance_id": entrance_id,
            "criterion": "ramp_or_bevel",
            "verdict": "present",
            "truth": "present",
            "outcome": "correct",
            "conditions": {
                "distance_m": distance,
                "lighting": lighting,
                "occlusion": "none",
            },
        })

    analysis = _condition_analysis(joins)
    distance_groups = analysis["dimensions"]["distance_m"]["groups"]
    assert list(distance_groups) == ["2.5", "3.0", "10.0"]
    assert distance_groups["2.5"]["capture_count"] == 3
    assert distance_groups["2.5"]["entrance_count"] == 3
    assert (
        distance_groups["2.5"]["criteria"]["ramp_or_bevel"]["underpowered"]
        is False
    )
    assert (
        distance_groups["10.0"]["criteria"]["ramp_or_bevel"]["underpowered"]
        is True
    )
    assert (
        distance_groups["2.5"]["criteria"]["handrails"]["entrance_count"]
        == 0
    )
    assert (
        distance_groups["2.5"]["criteria"]["handrails"]["underpowered"]
        is True
    )

    lighting_groups = analysis["dimensions"]["lighting"]["groups"]
    assert lighting_groups["overcast"]["capture_count"] == 4
    assert lighting_groups["overcast"]["entrance_count"] == 3
    assert (
        lighting_groups["overcast"]["criteria"]["ramp_or_bevel"]["underpowered"]
        is False
    )
    assert (
        lighting_groups["low_light"]["criteria"]["ramp_or_bevel"]["underpowered"]
        is True
    )


def test_condition_analysis_keeps_close_recorded_distances_distinct():
    joins = []
    for index, distance in enumerate((2.5000001, 2.5000002), start=1):
        joins.append({
            "capture_id": f"cap-{index}",
            "entrance_id": f"E-00{index}",
            "criterion": "ramp_or_bevel",
            "verdict": "present",
            "truth": "present",
            "outcome": "correct",
            "conditions": {
                "distance_m": distance,
                "lighting": "overcast",
                "occlusion": "none",
            },
        })

    groups = _condition_analysis(joins)["dimensions"]["distance_m"]["groups"]
    assert list(groups) == ["2.5000001", "2.5000002"]
    assert [group["capture_count"] for group in groups.values()] == [1, 1]


def test_written_json_preserves_numeric_distance_order(tmp_path):
    manifest = _write_manifest(
        tmp_path / "manifest.csv",
        [("cap-1", DEV_A), ("cap-2", DEV_B), ("cap-3", DEV_C)],
    )
    labels = _write_labels(
        tmp_path / "labels.csv",
        [
            (DEV_A, "ramp_or_bevel", "present"),
            (DEV_B, "ramp_or_bevel", "present"),
            (DEV_C, "ramp_or_bevel", "present"),
        ],
    )
    engine = FakeEngine({
        entrance_id: _screening(entrance_id, {"ramp_or_bevel": "present"})
        for entrance_id in (DEV_A, DEV_B, DEV_C)
    })
    captures = {
        "cap-1": _capture("cap-1", distance=10),
        "cap-2": _capture("cap-2", distance=2.5),
        "cap-3": _capture("cap-3", distance=3),
    }

    run_eval(
        manifest_path=manifest,
        labels_path=labels,
        out_dir=tmp_path / "out",
        engine=engine,
        get_capture=captures.__getitem__,
    )

    written = json.loads(
        (tmp_path / "out" / "screening_eval.json").read_text(encoding="utf-8")
    )
    groups = written["condition_analysis"]["dimensions"]["distance_m"]["groups"]
    assert list(groups) == ["2.5", "3.0", "10.0"]


def test_condition_analysis_treats_an_invalid_model_verdict_as_uncommitted(tmp_path):
    manifest = _write_manifest(tmp_path / "manifest.csv", [("cap-1", DEV_A)])
    labels = _write_labels(
        tmp_path / "labels.csv", [(DEV_A, "ramp_or_bevel", "present")]
    )
    engine = FakeEngine({
        DEV_A: _screening(
            DEV_A,
            {"ramp_or_bevel": None},
            assessment_verdicts=({"ramp_or_bevel": "INVALID:maybe"},),
        ),
    })

    result = run_eval(
        manifest_path=manifest,
        labels_path=labels,
        out_dir=tmp_path / "out",
        engine=engine,
        get_capture=_fake_get_capture,
    )

    metrics = result["condition_analysis"]["dimensions"]["distance_m"][
        "groups"
    ]["2.5"]["criteria"]["ramp_or_bevel"]
    assert metrics["correct"] == 0
    assert metrics["wrong"] == 0
    assert metrics["abstained"] == 1
    assert metrics["accuracy_of_committed"] is None
    assert metrics["abstention_rate"] == 1.0


# --- CLI ---------------------------------------------------------------------


def test_cli_keyless_run_fails_clearly_before_touching_anything(
    tmp_path, monkeypatch, capsys
):
    from frontdoor import storage

    # Keep the CLI's dotenv load from pulling a real key out of a local .env.
    monkeypatch.setattr(storage, "_dotenv_loaded", True)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    out_dir = tmp_path / "out"
    code = main([
        "--manifest", str(tmp_path / "missing-manifest.csv"),
        "--labels", str(tmp_path / "missing-labels.csv"),
        "--out", str(out_dir),
    ])
    assert code == 2
    err = capsys.readouterr().err
    assert "ANTHROPIC_API_KEY" in err
    assert "Nothing was read or written" in err
    assert not out_dir.exists()
