"""Tests for the screening accuracy eval runner (TICK-245, TICK-246).

Fully mocked: a fake engine returns canned EntranceScreening results, and no
test makes a live model call or reads real capture data. Report assertions
parse the written JSON/markdown and check values, not exact bytes.
"""

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import frontdoor.screening_eval as screening_eval_module
from frontdoor.dataset_closeout import DatasetCloseoutError
from frontdoor.labels import COLUMNS as LABEL_COLUMNS
from frontdoor.manifest import COLUMNS as MANIFEST_COLUMNS, manifest_sha256
from frontdoor.screening import (
    CRITERIA_KEYS,
    CriterionSummary,
    EntranceScreening,
    ImageAssessment,
    ScreeningConfig,
    SealedSplitError,
    SpendCapError,
)
from frontdoor.screening_eval import (
    CONDITION_KEYS,
    EVAL_MAX_USD_PER_RUN,
    LATENCY_BUDGET_S,
    MARKDOWN_NAME,
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
from frontdoor.seal_audit import AUDIT_FIELDS, SealAuditError

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

    def screen_entrance(self, entrance_id, images, *, allow_sealed=False):
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


@pytest.fixture(autouse=True)
def _fixture_eligibility(monkeypatch):
    """Unit fixtures predate the committed closeout; admit their manifest IDs."""
    def eligible(_closeout_path, manifest_path, _sidecar_dir):
        with open(manifest_path, encoding="utf-8", newline="") as handle:
            return frozenset(row["entrance_id"] for row in csv.DictReader(handle))

    monkeypatch.setattr(screening_eval_module, "load_eligible_entrances", eligible)


def _run_eval(tmp_path, **kwargs):
    return run_eval(
        closeout_path=tmp_path / "dataset-closeout.json",
        sidecar_dir=tmp_path / "sidecars",
        **kwargs,
    )


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
        "correct": 2, "wrong": 0, "abstained": 0, "not_visible": 0, "unlabeled": 0,
    }
    assert per_criterion["handrails"] == {
        "correct": 0, "wrong": 1, "abstained": 0, "not_visible": 0, "unlabeled": 1,
    }
    # This one abstained by saying not_visible ...
    assert per_criterion["accessible_door_hardware"] == {
        "correct": 0, "wrong": 0, "abstained": 1, "not_visible": 1, "unlabeled": 1,
    }
    # ... and this one by returning no verdict at all. Both abstain; only the
    # first counts toward the not-visible rate.
    assert per_criterion["accessibility_signage"] == {
        "correct": 0, "wrong": 0, "abstained": 1, "not_visible": 0, "unlabeled": 1,
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


def test_tick_245_ac_7_latency_stats_and_over_budget_count():
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
        _run_eval(
            tmp_path,
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
        collect_entrances(
            tmp_path / "irrelevant.csv", eligible_entrances=frozenset(), split="devv"
        )


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
    entrances = collect_entrances(
        manifest, eligible_entrances={DEV_A, DEV_B, CALIB_ID, SEALED_ID}
    )
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
    _run_eval(
        tmp_path,
        manifest_path=manifest,
        labels_path=labels,
        out_dir=tmp_path / "out",
        engine=engine,
        get_capture=_fake_get_capture,
    )
    assert engine.calls == [(DEV_A, 1)]


def test_run_eval_never_hands_an_ineligible_entrance_to_the_engine(
    tmp_path, monkeypatch
):
    manifest = _write_manifest(
        tmp_path / "manifest.csv", [("cap-1", DEV_A), ("cap-2", DEV_B)]
    )
    labels = _write_labels(
        tmp_path / "labels.csv",
        [(DEV_A, "ramp_or_bevel", "present"), (DEV_B, "ramp_or_bevel", "present")],
    )
    monkeypatch.setattr(
        screening_eval_module,
        "load_eligible_entrances",
        lambda *_args: frozenset({DEV_A}),
    )
    engine = FakeEngine({DEV_A: _screening(DEV_A, {"ramp_or_bevel": "present"})})

    _run_eval(
        tmp_path,
        manifest_path=manifest,
        labels_path=labels,
        out_dir=tmp_path / "out",
        engine=engine,
        get_capture=_fake_get_capture,
    )

    assert engine.calls == [(DEV_A, 1)]


def test_stale_closeout_fails_before_images_are_read_or_output_is_written(
    tmp_path, monkeypatch
):
    manifest = _write_manifest(tmp_path / "manifest.csv", [("cap-1", DEV_A)])
    labels = _write_labels(
        tmp_path / "labels.csv", [(DEV_A, "ramp_or_bevel", "present")]
    )
    image_reads = []

    def reject_stale_closeout(*_args):
        raise DatasetCloseoutError("manifest hash does not match")

    monkeypatch.setattr(
        screening_eval_module,
        "load_eligible_entrances",
        reject_stale_closeout,
    )

    with pytest.raises(DatasetCloseoutError, match="manifest hash does not match"):
        _run_eval(
            tmp_path,
            manifest_path=manifest,
            labels_path=labels,
            out_dir=tmp_path / "out",
            engine=FakeEngine({}),
            get_capture=lambda capture_id: image_reads.append(capture_id),
        )

    assert image_reads == []
    assert not (tmp_path / "out").exists()


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
    result = _run_eval(
        tmp_path,
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
        "correct": 0, "wrong": 0, "abstained": 0, "not_visible": 0, "unlabeled": 2,
        "accuracy_of_committed": None, "abstention_rate": None,
        "not_visible_rate": None,
    }

    overall = written["overall"]
    assert overall["correct"] == 3 and overall["wrong"] == 1
    assert overall["abstained"] == 1
    assert overall["accuracy_of_committed"] == pytest.approx(3 / 4)
    assert overall["abstention_rate"] == pytest.approx(1 / 5)
    # The one abstention was a not_visible, so the rates coincide here; they
    # part company as soon as a view returns no verdict at all.
    assert overall["not_visible"] == 1
    assert overall["not_visible_rate"] == pytest.approx(1 / 5)

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
    assert "| ramp_or_bevel | 2 | 0 | 0 | 0 | 0 | 1.000 |" in text
    assert "| handrails | 1 | 1 | 0 | 0 | 0 | 0.500 |" in text
    assert "- not visible rate: 0.200" in text
    assert "0.750 (3 correct / 4 committed)" in text
    for dimension in CONDITION_KEYS:
        assert f"## Exploratory condition analysis: {dimension}" in text
    assert text.count("**Exploratory — descriptive associations only; not causal.**") == 3
    assert "| exploratory | 1.5 | ramp_or_bevel | 2 | 2 | underpowered " in text
    assert f"| {DEV_A} | 0.167 |" in text
    assert "| 2.000 | 4.000 | 16.000 | 16.000 | 1 of 3 |" in text
    assert SEALED_ID not in text


def _without_runtime(text):
    """The report minus its wall-clock runtime, which is legitimately variable.

    Determinism here means the same inputs score the same way, not that two
    runs took the same number of seconds.
    """
    report = json.loads(text)
    report["run"].pop("duration_s")
    return json.dumps(report, indent=2, sort_keys=True)


def test_report_is_deterministic_across_runs(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _, out_a = _run_report(tmp_path / "a")
    _, out_b = _run_report(tmp_path / "b")
    assert _without_runtime(
        (out_a / "screening_eval.json").read_text(encoding="utf-8")
    ) == _without_runtime(
        (out_b / "screening_eval.json").read_text(encoding="utf-8")
    )
    md_a, md_b = (
        [
            line
            for line in (out / "screening_eval.md")
            .read_text(encoding="utf-8")
            .splitlines()
            if not line.startswith("- total runtime:")
        ]
        for out in (out_a, out_b)
    )
    assert md_a == md_b


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

    _run_eval(
        tmp_path,
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

    result = _run_eval(
        tmp_path,
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


# --- the audited sealed path (TICK-079, TICK-080) ----------------------------
#
# The Sep 7 unsealing run is this same runner with --include-sealed added and
# nothing else changed (TICK-079 AC2), so the flag is exercised here rather
# than written on the morning it has to work.


def _audit_context(tmp_path, manifest):
    """A minimal audit mapping for record_unsealing, mirroring test_labels."""
    return {
        "manifest_path": manifest,
        "audit_path": tmp_path / "SEAL_AUDIT.log",
        "repo": tmp_path,
        "config": {"images_bucket": "frontdoor-image", "endpoint": "default"},
    }


def _clean_recordable_repo(monkeypatch):
    """Monkeypatch the git-cleanliness bits the way test_seal_audit.py does."""
    monkeypatch.setattr("frontdoor.seal_audit._working_tree_dirty", lambda repo: False)
    monkeypatch.setattr("frontdoor.seal_audit._git_commit", lambda repo: "b" * 40)
    monkeypatch.setattr("frontdoor.seal_audit._operator", lambda: "qa-operator")


def _sealed_fixture(tmp_path):
    """A manifest and labels covering one sealed and one dev entrance."""
    manifest = _write_manifest(
        tmp_path / "manifest.csv", [("cap-1", SEALED_ID), ("cap-2", DEV_A)]
    )
    labels = _write_labels(
        tmp_path / "labels.csv",
        [
            (SEALED_ID, "ramp_or_bevel", "present"),
            (DEV_A, "ramp_or_bevel", "absent"),
        ],
    )
    return manifest, labels


SEALED_ARGV = ["python", "-m", "frontdoor.screening_eval", "--include-sealed"]


def test_sealed_split_without_an_audit_context_is_refused(tmp_path):
    """No audit context, no sealed run - the flag alone never unseals."""
    manifest, labels = _sealed_fixture(tmp_path)

    def _boom(capture_id):
        raise AssertionError("no image should be read")

    with pytest.raises(SealedSplitError, match="audited"):
        run_eval(
            manifest_path=manifest,
            labels_path=labels,
            out_dir=tmp_path / "out",
            engine=FakeEngine({}),
            get_capture=_boom,
            split="sealed",
        )
    assert not (tmp_path / "out").exists()
    assert not (tmp_path / "SEAL_AUDIT.log").exists()


def test_sealed_run_records_one_audit_line_carrying_the_real_command(
    tmp_path, monkeypatch
):
    manifest, labels = _sealed_fixture(tmp_path)
    audit = _audit_context(tmp_path, manifest)
    _clean_recordable_repo(monkeypatch)
    engine = FakeEngine({SEALED_ID: _screening(SEALED_ID, {"ramp_or_bevel": "present"})})

    run_eval(
        manifest_path=manifest,
        labels_path=labels,
        out_dir=tmp_path / "out",
        engine=engine,
        get_capture=_fake_get_capture,
        split="sealed",
        audit=audit,
        argv=SEALED_ARGV,
    )

    lines = audit["audit_path"].read_text(encoding="utf-8").splitlines()
    # TICK-080 AC3: exactly one line, and its command line is the command that
    # actually ran, not a placeholder nobody can re-run.
    assert len(lines) == 1
    record = dict(zip(AUDIT_FIELDS, lines[0].split("\t")))
    assert json.loads(record["command_line"]) == SEALED_ARGV
    assert record["operator"] == "qa-operator"
    assert record["manifest_sha256"] == manifest_sha256(manifest)


def test_audit_line_is_written_before_any_sealed_image_is_read(tmp_path, monkeypatch):
    manifest, labels = _sealed_fixture(tmp_path)
    audit = _audit_context(tmp_path, manifest)
    _clean_recordable_repo(monkeypatch)
    seen = []

    def _get_capture(capture_id):
        # The seal's whole promise: the record exists before the first byte.
        seen.append(audit["audit_path"].exists())
        return _fake_get_capture(capture_id)

    run_eval(
        manifest_path=manifest,
        labels_path=labels,
        out_dir=tmp_path / "out",
        engine=FakeEngine(
            {SEALED_ID: _screening(SEALED_ID, {"ramp_or_bevel": "present"})}
        ),
        get_capture=_get_capture,
        split="sealed",
        audit=audit,
        argv=SEALED_ARGV,
    )
    assert seen == [True]


def test_dirty_working_tree_aborts_the_sealed_run_and_reads_nothing(
    tmp_path, monkeypatch
):
    # TICK-079 exercises this abort during the dry run, because Sep 7 is the
    # wrong morning to discover the guard.
    manifest, labels = _sealed_fixture(tmp_path)
    audit = _audit_context(tmp_path, manifest)
    monkeypatch.setattr("frontdoor.seal_audit._working_tree_dirty", lambda repo: True)

    def _boom(capture_id):
        raise AssertionError("no image should be read")

    with pytest.raises(SealAuditError, match="dirty"):
        run_eval(
            manifest_path=manifest,
            labels_path=labels,
            out_dir=tmp_path / "out",
            engine=FakeEngine({}),
            get_capture=_boom,
            split="sealed",
            audit=audit,
            argv=SEALED_ARGV,
        )
    assert not audit["audit_path"].exists()
    assert not (tmp_path / "out").exists()


def test_sealed_run_scores_the_sealed_split_only(tmp_path, monkeypatch):
    manifest, labels = _sealed_fixture(tmp_path)
    audit = _audit_context(tmp_path, manifest)
    _clean_recordable_repo(monkeypatch)
    engine = FakeEngine({SEALED_ID: _screening(SEALED_ID, {"ramp_or_bevel": "present"})})

    result = run_eval(
        manifest_path=manifest,
        labels_path=labels,
        out_dir=tmp_path / "out",
        engine=engine,
        get_capture=_fake_get_capture,
        split="sealed",
        audit=audit,
        argv=SEALED_ARGV,
    )
    assert engine.calls == [(SEALED_ID, 1)]
    assert result["split"] == "sealed"
    assert result["criteria"]["ramp_or_bevel"]["correct"] == 1


def test_dev_run_writes_no_audit_line(tmp_path, monkeypatch):
    # TICK-079 AC5: the dry run must leave SEAL_AUDIT.log untouched.
    manifest, labels = _sealed_fixture(tmp_path)
    _clean_recordable_repo(monkeypatch)
    run_eval(
        manifest_path=manifest,
        labels_path=labels,
        out_dir=tmp_path / "out",
        engine=FakeEngine({DEV_A: _screening(DEV_A, {"ramp_or_bevel": "absent"})}),
        get_capture=_fake_get_capture,
    )
    assert not (tmp_path / "SEAL_AUDIT.log").exists()


def test_cli_refuses_include_sealed_unless_launched_from_a_terminal(tmp_path, capsys):
    # Same discipline as frontdoor.eval: the unsealing run is a deliberate act
    # at a terminal, not something an import or a notebook can perform.
    out_dir = tmp_path / "out"
    code = main([
        "--manifest", str(tmp_path / "manifest.csv"),
        "--labels", str(tmp_path / "labels.csv"),
        "--out", str(out_dir),
        "--include-sealed",
    ])
    assert code == 2
    assert "--include-sealed" in capsys.readouterr().err
    assert not out_dir.exists()
    assert not (tmp_path / "SEAL_AUDIT.log").exists()


# --- runtime and the empty-group failure modes (TICK-079 AC3, AC4) -----------


def test_report_records_total_runtime(tmp_path):
    result, out_dir = _run_report(tmp_path)
    # AC3: how long the run takes must not be a surprise on Sep 7.
    assert result["run"]["duration_s"] >= 0.0
    assert "- total runtime:" in (out_dir / MARKDOWN_NAME).read_text(encoding="utf-8")


def test_run_with_no_entrances_writes_a_report_instead_of_dividing_by_zero(tmp_path):
    # Manifest and labels both sealed: the scored split (dev) is empty, including
    # no labeled-but-missing entrance that AC4 would otherwise pull in.
    manifest = _write_manifest(tmp_path / "manifest.csv", [("cap-1", SEALED_ID)])
    labels = _write_labels(
        tmp_path / "labels.csv", [(SEALED_ID, "ramp_or_bevel", "present")]
    )
    result = run_eval(
        manifest_path=manifest,
        labels_path=labels,
        out_dir=tmp_path / "out",
        engine=FakeEngine({}),
        get_capture=_fake_get_capture,
    )
    assert result["run"]["entrance_count"] == 0
    assert result["overall"]["accuracy_of_committed"] is None
    assert result["overall"]["abstention_rate"] is None
    assert result["flip_rate"]["mean"] is None
    assert result["entrance_call"]["per_entrance"] == {}
    assert result["entrance_call"]["agreement"] is None
    assert result["latency_s"]["median"] is None
    assert (tmp_path / "out" / MARKDOWN_NAME).exists()


def test_entrance_with_no_views_is_reported_not_crashed(tmp_path):
    manifest = _write_manifest(tmp_path / "manifest.csv", [("cap-1", DEV_A)])
    labels = _write_labels(
        tmp_path / "labels.csv", [(DEV_A, "ramp_or_bevel", "present")]
    )
    # One assessment came back with no valid verdict: the view was captured
    # but the engine declined every criterion.
    empty = _screening(DEV_A, {}, latencies=(1.0,))
    result = run_eval(
        manifest_path=manifest,
        labels_path=labels,
        out_dir=tmp_path / "out",
        engine=FakeEngine({DEV_A: empty}),
        get_capture=_fake_get_capture,
    )
    assert result["flip_rate"]["per_entrance"][DEV_A] is None
    assert result["criteria"]["ramp_or_bevel"]["abstained"] == 1
    assert result["overall"]["accuracy_of_committed"] is None


def test_labeled_entrance_with_no_captures_is_reported_not_vanished(tmp_path):
    # TICK-079 AC4: "an entrance with no views". A labeled entrance that never
    # made it into the manifest is that case — vanishing is how an incomplete
    # capture goes unnoticed on the one run that cannot be repeated.
    manifest = _write_manifest(tmp_path / "manifest.csv", [("cap-1", DEV_B)])
    labels = _write_labels(
        tmp_path / "labels.csv",
        [
            (DEV_A, "ramp_or_bevel", "present"),
            (DEV_B, "ramp_or_bevel", "present"),
        ],
    )
    engine = FakeEngine(
        {
            DEV_A: _screening(DEV_A, {}, latencies=()),
            DEV_B: _screening(DEV_B, {"ramp_or_bevel": "present"}),
        }
    )
    result = run_eval(
        manifest_path=manifest,
        labels_path=labels,
        out_dir=tmp_path / "out",
        engine=engine,
        get_capture=_fake_get_capture,
    )
    assert engine.calls == [(DEV_A, 0), (DEV_B, 1)]
    assert DEV_A in result["entrance_call"]["per_entrance"]
    assert result["criteria"]["ramp_or_bevel"]["abstained"] == 1
    assert result["criteria"]["ramp_or_bevel"]["correct"] == 1


def test_criterion_where_every_view_abstained_reports_no_accuracy(tmp_path):
    manifest = _write_manifest(tmp_path / "manifest.csv", [("cap-1", DEV_A)])
    labels = _write_labels(
        tmp_path / "labels.csv", [(DEV_A, "ramp_or_bevel", "present")]
    )
    result = run_eval(
        manifest_path=manifest,
        labels_path=labels,
        out_dir=tmp_path / "out",
        engine=FakeEngine({DEV_A: _screening(DEV_A, {"ramp_or_bevel": "not_visible"})}),
        get_capture=_fake_get_capture,
    )
    ramp = result["criteria"]["ramp_or_bevel"]
    assert ramp["abstained"] == 1
    assert ramp["accuracy_of_committed"] is None
    assert ramp["abstention_rate"] == 1.0


def _cli_args(tmp_path, *extra):
    return [
        "--manifest", str(tmp_path / "manifest.csv"),
        "--labels", str(tmp_path / "labels.csv"),
        "--out", str(tmp_path / "out"),
        *extra,
    ]


def _stub_freeze_day(monkeypatch):
    """Everything the sealed CLI path needs except the eval itself."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        "frontdoor.eval._storage_config",
        lambda: {"images_bucket": "frontdoor-image", "endpoint": "default"},
    )


def _stub_run_eval(monkeypatch):
    """Capture run_eval kwargs; return a dummy report so main can print."""
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return {
            "run": {"labels_scored": 0, "entrance_count": 0, "duration_s": 1.0},
            "overall": {"accuracy_of_committed": None},
        }

    monkeypatch.setattr("frontdoor.screening_eval.run_eval", _capture)
    return captured


def test_cli_include_sealed_asks_for_the_sealed_split_with_an_audit_context(
    tmp_path, monkeypatch
):
    from frontdoor.labels import AUDIT_KEYS

    _stub_freeze_day(monkeypatch)
    captured = _stub_run_eval(monkeypatch)
    assert main(_cli_args(tmp_path, "--include-sealed"), from_cli=True) == 0
    assert captured["split"] == "sealed"
    assert all(key in captured["audit"] for key in AUDIT_KEYS)
    # The recorded command is the one that ran, so the audit line names
    # something a third party can re-run (TICK-080 AC3).
    assert "--include-sealed" in captured["argv"]


def test_cli_without_the_flag_asks_for_dev_and_no_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    captured = _stub_run_eval(monkeypatch)
    assert main(_cli_args(tmp_path), from_cli=True) == 0
    assert captured["split"] == "dev"
    assert captured["audit"] is None
    # Live /screen keeps ScreeningConfig's $1 default. The eval runner must
    # not: 154 eligible dev captures at $0.05/image is already $7.70, and a
    # cap abort after --include-sealed has written SEAL_AUDIT.log is the
    # freeze-day failure TICK-080 exists to prevent (R-5).
    assert captured["engine"].config.max_usd_per_run == EVAL_MAX_USD_PER_RUN


def test_eval_spend_cap_covers_the_committed_eligible_corpus():
    closeout = json.loads(
        Path("data/dataset-closeout.json").read_text(encoding="utf-8")
    )
    worst = max(closeout["eligible"]["captures_by_split"].values())
    needed = worst * ScreeningConfig().usd_per_image
    assert EVAL_MAX_USD_PER_RUN >= needed
    assert EVAL_MAX_USD_PER_RUN > ScreeningConfig().max_usd_per_run


def test_cli_reports_a_spend_cap_hit_after_unsealing_as_a_second_unsealing(
    tmp_path, monkeypatch, capsys
):
    # The audit line is written before the first image. A cap abort is not a
    # clean refusal: the seal is already open.
    _stub_freeze_day(monkeypatch)

    def _blow_the_cap(**kwargs):
        raise SpendCapError(
            "next call would spend an estimated $1.05, over the $1.00 cap"
        )

    monkeypatch.setattr("frontdoor.screening_eval.run_eval", _blow_the_cap)
    assert main(_cli_args(tmp_path, "--include-sealed"), from_cli=True) == 1
    err = capsys.readouterr().err
    assert "cap" in err
    assert "second unsealing" in err


def test_cli_spend_cap_on_dev_does_not_claim_the_seal_opened(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def _blow_the_cap(**kwargs):
        raise SpendCapError(
            "next call would spend an estimated $1.05, over the $1.00 cap"
        )

    monkeypatch.setattr("frontdoor.screening_eval.run_eval", _blow_the_cap)
    assert main(_cli_args(tmp_path), from_cli=True) == 1
    err = capsys.readouterr().err
    assert "cap" in err
    assert "second unsealing" not in err


def test_cli_reports_a_refused_unsealing_instead_of_a_traceback(
    tmp_path, monkeypatch, capsys
):
    # A dirty tree on Sep 7 must print what to fix and exit non-zero, not
    # bury the reason in a stack trace.
    _stub_freeze_day(monkeypatch)

    def _refuse(**kwargs):
        raise SealAuditError("working tree is dirty; refusing to unseal")

    monkeypatch.setattr("frontdoor.screening_eval.run_eval", _refuse)
    assert main(_cli_args(tmp_path, "--include-sealed"), from_cli=True) == 1
    assert "dirty" in capsys.readouterr().err


def test_not_visible_is_distinguished_from_no_verdict_at_all(tmp_path):
    # Both abstain, and neither is ever scored correct or wrong. But TICK-079
    # asks the sealed run for the *not visible* rate specifically: "I looked
    # and could not see it" is a finding about the photos; "no view returned
    # anything" is a finding about the run.
    manifest = _write_manifest(tmp_path / "manifest.csv", [("cap-1", DEV_A)])
    labels = _write_labels(
        tmp_path / "labels.csv",
        [
            (DEV_A, "ramp_or_bevel", "present"),
            (DEV_A, "handrails", "present"),
        ],
    )
    result = run_eval(
        manifest_path=manifest,
        labels_path=labels,
        out_dir=tmp_path / "out",
        engine=FakeEngine(
            # handrails is absent from the dict, so its verdict is None.
            {DEV_A: _screening(DEV_A, {"ramp_or_bevel": "not_visible"})}
        ),
        get_capture=_fake_get_capture,
    )
    ramp = result["criteria"]["ramp_or_bevel"]
    hand = result["criteria"]["handrails"]
    assert ramp["abstained"] == 1 and ramp["not_visible"] == 1
    assert hand["abstained"] == 1 and hand["not_visible"] == 0
    assert ramp["not_visible_rate"] == 1.0
    assert hand["not_visible_rate"] == 0.0
    # Two abstentions, one of them not_visible.
    assert result["overall"]["abstention_rate"] == 1.0
    assert result["overall"]["not_visible_rate"] == 0.5


# --- the entrance-level call (TICK-079 AC1) ----------------------------------


def test_entrance_call_rolls_up_each_entrance_labeled_criteria(tmp_path):
    result, out_dir = _run_report(tmp_path)
    calls = result["entrance_call"]["per_entrance"]
    # DEV_A: one correct, one wrong, one abstained -> it committed to two and
    # got one of them wrong, so the call is not correct.
    assert calls[DEV_A] == {
        "correct": 1, "wrong": 1, "abstained": 1,
        "accuracy_of_committed": 0.5,
        "all_committed_correct": False,
    }
    # DEV_B: committed to two, both right.
    assert calls[DEV_B] == {
        "correct": 2, "wrong": 0, "abstained": 0,
        "accuracy_of_committed": 1.0,
        "all_committed_correct": True,
    }
    assert result["entrance_call"]["agreement"] == 0.5
    text = (out_dir / MARKDOWN_NAME).read_text(encoding="utf-8")
    assert "## Entrance-level call" in text
    assert f"| {DEV_B} | 2 | 0 | 0 | 1.000 | yes |" in text


def test_an_abstention_never_makes_the_entrance_call_wrong(tmp_path):
    # The honesty rule applies at entrance level too: declining to guess on one
    # criterion must not turn a fully correct entrance into a failed call.
    manifest = _write_manifest(tmp_path / "manifest.csv", [("cap-1", DEV_A)])
    labels = _write_labels(
        tmp_path / "labels.csv",
        [
            (DEV_A, "ramp_or_bevel", "present"),
            (DEV_A, "handrails", "present"),
        ],
    )
    result = run_eval(
        manifest_path=manifest,
        labels_path=labels,
        out_dir=tmp_path / "out",
        engine=FakeEngine(
            {DEV_A: _screening(
                DEV_A,
                {"ramp_or_bevel": "present", "handrails": "not_visible"},
            )}
        ),
        get_capture=_fake_get_capture,
    )
    call = result["entrance_call"]["per_entrance"][DEV_A]
    assert call == {
        "correct": 1, "wrong": 0, "abstained": 1,
        "accuracy_of_committed": 1.0,
        "all_committed_correct": True,
    }
    assert result["entrance_call"]["agreement"] == 1.0


def test_an_entrance_the_engine_committed_to_nothing_on_has_no_call(tmp_path):
    # No call is not a failed call, so it must not drag the agreement down.
    manifest = _write_manifest(
        tmp_path / "manifest.csv", [("cap-1", DEV_A), ("cap-2", DEV_B)]
    )
    labels = _write_labels(
        tmp_path / "labels.csv",
        [
            (DEV_A, "ramp_or_bevel", "present"),
            (DEV_B, "ramp_or_bevel", "present"),
        ],
    )
    result = run_eval(
        manifest_path=manifest,
        labels_path=labels,
        out_dir=tmp_path / "out",
        engine=FakeEngine(
            {
                DEV_A: _screening(DEV_A, {"ramp_or_bevel": "not_visible"}),
                DEV_B: _screening(DEV_B, {"ramp_or_bevel": "present"}),
            }
        ),
        get_capture=_fake_get_capture,
    )
    calls = result["entrance_call"]["per_entrance"]
    assert calls[DEV_A]["all_committed_correct"] is None
    assert calls[DEV_B]["all_committed_correct"] is True
    # DEV_A is out of the denominator entirely, not counted as a miss.
    assert result["entrance_call"]["agreement"] == 1.0


def test_a_screened_entrance_with_no_labels_still_appears(tmp_path):
    manifest = _write_manifest(tmp_path / "manifest.csv", [("cap-1", DEV_A)])
    labels = _write_labels(tmp_path / "labels.csv", [(DEV_B, "ramp_or_bevel", "present")])
    result = run_eval(
        manifest_path=manifest,
        labels_path=labels,
        out_dir=tmp_path / "out",
        engine=FakeEngine(
            {
                DEV_A: _screening(DEV_A, {"ramp_or_bevel": "present"}),
                # Label for DEV_B has no captures; AC4 still screens it.
                DEV_B: _screening(DEV_B, {}, latencies=()),
            }
        ),
        get_capture=_fake_get_capture,
    )
    calls = result["entrance_call"]["per_entrance"]
    # Screened but unlabeled: it appears with no call rather than vanishing.
    assert calls[DEV_A] == {
        "correct": 0, "wrong": 0, "abstained": 0,
        "accuracy_of_committed": None,
        "all_committed_correct": None,
    }
    assert result["entrance_call"]["agreement"] is None
