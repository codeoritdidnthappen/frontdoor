"""Screening accuracy eval: engine verdicts vs human labels (TICK-245, TICK-246).

Runs the vision screening engine over every captured view of each entrance in
one unsealed split (dev by default), joins the per-criterion majority verdicts
to the human ground-truth labels, and writes the accuracy report the results
freeze will be judged against: per-criterion correct / wrong / abstained, the
accuracy of committed verdicts, the not-visible rate, the entrance-level call,
per-entrance cross-view flip rates, and latency against the 15-second budget.

Scoring vocabulary: labels are presence-only ("present"/"absent") because the
operator stood at the door; the engine may also answer not_visible or produce
no verdict at all. A not_visible majority verdict is an ABSTENTION - scored
separately, never counted correct or wrong, because declining to guess is the
honest answer the engine is instructed to give.

A missing verdict is NOT an abstention when the engine never got an answer
(TICK-399). A rejected response, a refusal, a truncation or a transport error
is scored as a FAILURE, in its own column, with rejected responses counted
again as their own sub-total. Folding them into the abstention rate is how a
repeat run silently discarded 68 of 154 view responses and lost every
criterion on seven of twenty-eight entrances, while the report read as an
engine that had looked and honestly declined.

Split discipline (D-007, D-017): the split is resolved here from each entrance
ID via the committed seed, exactly like the screening engine. Day to day the
runner scores dev or calib and refuses sealed. The sealed split is opened once,
on results-freeze day, by the same runner with --include-sealed added - which
appends one SEAL_AUDIT.log line naming the command that ran, before a single
sealed byte is read, and refuses outright if the working tree is dirty.

The dry run (TICK-079) and the freeze-day run (TICK-080) are the same command
apart from `--include-sealed`. `--out` also differs so the sealed report cannot
overwrite the dry run's, which is the evidence the command was exercised
beforehand:

    python -m frontdoor.screening_eval --manifest data/manifest.csv \
        --labels data/labels.csv --out reports/dry-run
    python -m frontdoor.screening_eval --manifest data/manifest.csv \
        --labels data/labels.csv --out reports/sealed --include-sealed
"""

import argparse
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

from frontdoor.dataset_closeout import DatasetCloseoutError, load_eligible_entrances
from frontdoor.labels import SPLITS, labels_for_eval, load_labels
from frontdoor.manifest import read_manifest
from frontdoor.screening import (
    CRITERIA_KEYS,
    FAILURE_REJECTED,
    ScreeningConfig,
    ScreeningEngine,
    SealedSplitError,
    SpendCapError,
    criterion_verdict,
)
from frontdoor.seal_audit import SealAuditError
from frontdoor.split import assign_split, canonical_entrance_id

#: Per-image latency budget (seconds); the report counts every view over it.
LATENCY_BUDGET_S = 15.0

#: Screening-mode conditions recorded for each capture. Surface is
#: metrology-only, and angle is neither entered nor derived for screening.
CONDITION_KEYS = ("distance_m", "lighting", "occlusion")

#: Exploratory cells below this many independent entrances are still shown,
#: but are too thin to present as findings.
MIN_CONDITION_ENTRANCES = 3

#: Eval-runner spend cap, not the live /screen default ($1). The committed
#: closeout's largest split is 154 eligible dev captures; at the conservative
#: $0.05/image estimate that is $7.70. A $1 cap would abort a freeze-day run
#: after the audit line was already written (R-5, TICK-080).
EVAL_MAX_USD_PER_RUN = 20.0

JSON_NAME = "screening_eval.json"
MARKDOWN_NAME = "screening_eval.md"


class ScreeningEvalError(ValueError):
    """Raised when the eval cannot produce a trustworthy report."""


class MissingCaptureObjects(ScreeningEvalError):
    """The run would read captures whose bytes are not in the bucket.

    Raised before the audit line, never after: on 2026-09-04 the committed dataset was 338
    captures and the image bucket held 7 objects, none of them a dataset capture. Reaching the
    first fetch in that state on freeze day means the seal is open, no report exists, and the
    only way to try again is a second unsealing (R-5).
    """

    #: How many missing keys to name before summarising. Enough to see the pattern -- one
    #: entrance, one split, or the whole dataset -- without printing hundreds of lines.
    SHOWN = 10

    def __init__(self, missing, entrances_affected, split, source=None, remedy=None):
        self.missing = list(missing)
        self.entrances_affected = entrances_affected
        self.split = split
        # Named, because the run has two possible sources now (#342) and the remedy differs. The
        # bucket wording told an operator pointed at a mistyped LOCAL directory that the bytes had
        # never been uploaded, which sends them to chase someone else's task.
        self.source = source or "the image bucket"
        shown = ", ".join(self.missing[: self.SHOWN])
        if len(self.missing) > self.SHOWN:
            shown += f", and {len(self.missing) - self.SHOWN} more"
        super().__init__(
            f"{len(self.missing)} of the {split} split's captures are not in {self.source}, "
            f"across {entrances_affected} entrance(s): {shown}. Nothing was read and no audit "
            f"line was written. {remedy or self.DEFAULT_REMEDY}"
        )

    DEFAULT_REMEDY = (
        "Either those bytes were never uploaded (data/STORAGE.md: \"Bytes live here; records "
        "live in git\") or this run is pointed at the wrong bucket or endpoint -- check "
        "FRONTDOOR_IMAGES_* before concluding the former."
    )


def _require_permitted_split(split, *, allow_sealed=False):
    """Raise unless this split may be scored, before any file is read.

    `allow_sealed` means an audit mapping is present, not that the log line
    has been written yet. Recording happens next, in labels_for_eval. On its
    own the argument is not permission to read anything; it only stops this
    check from refusing a sealed split the caller is about to audit.
    """
    if split not in SPLITS:
        raise ScreeningEvalError(f"unknown split {split!r}; expected one of {SPLITS}")
    if split == "sealed" and not allow_sealed:
        raise SealedSplitError(
            "the sealed split is scored once, by an audited --include-sealed "
            "run that records the unsealing first (D-007, D-017)"
        )


def collect_entrances(
    manifest_path, *, eligible_entrances, split="dev", allow_sealed=False
):
    """Entrance ID -> sorted capture IDs for one split.

    The split is re-derived from the committed seed per entrance; the
    manifest's split cell is a cache, not an authority.
    """
    _require_permitted_split(split, allow_sealed=allow_sealed)
    entrances = {}
    for row in read_manifest(manifest_path):
        entrance_id = canonical_entrance_id(row["entrance_id"])
        if assign_split(entrance_id) != split:
            continue
        if entrance_id not in eligible_entrances:
            continue
        entrances.setdefault(entrance_id, []).append(row["capture_id"])
    return {eid: sorted(caps) for eid, caps in sorted(entrances.items())}


#: The outcome of one scored cell. `failed` is TICK-399's addition: the engine
#: produced no verdict because the call failed, which is NOT the engine looking
#: and declining. Folding the two together is what let seven of twenty-eight
#: entrances vanish into the abstention rate - the honesty signal this product
#: leans on - with nothing in the report saying so.
OUTCOMES = ("correct", "wrong", "abstained", "failed")


def classify(verdict, truth, *, failed=False):
    """One join cell: engine majority verdict vs human truth.

    `failed` says the missing verdict is a recorded failure (a rejected
    response, a refusal, a truncation, a transport error) rather than an
    abstention. Without it a discarded answer is indistinguishable from the
    engine having looked and said it could not tell.
    """
    if verdict is None and failed:
        return "failed"
    if verdict is None or verdict == "not_visible":
        return "abstained"
    return "correct" if verdict == truth else "wrong"


def _scored(counts):
    """Cells the engine was asked about: committed, abstained or failed.

    Unchanged in total by TICK-399 - failures used to be inside `abstained`
    and are now beside it - so the denominator does not move and the two
    reports remain comparable.
    """
    return (
        counts["correct"] + counts["wrong"] + counts["abstained"]
        + counts["failed"]
    )


def accuracy_of_committed(counts):
    """Accuracy over verdicts the engine committed to; None if it never did."""
    committed = counts["correct"] + counts["wrong"]
    if committed == 0:
        return None
    return counts["correct"] / committed


def score_joins(screenings, labels):
    """Join every screened (entrance, criterion) to its label.

    Returns (per_criterion counts, join rows). A screened pair with no label
    is counted unlabeled and never scored; a label for an unscreened entrance
    is ignored (there is no verdict to judge).
    """
    truth = {
        (label["entrance_id"], label["criterion"]): label["truth"]
        for label in labels
    }
    per_criterion = {
        key: {
            "correct": 0, "wrong": 0, "abstained": 0,
            # A sub-count of abstained, not a fifth outcome: the engine saying
            # "I cannot see it" and the engine returning nothing at all are
            # both abstentions, but only the first is the not-visible rate
            # TICK-079 asks the sealed run to report.
            "not_visible": 0,
            # An outcome in its own right (TICK-399): the engine produced no
            # verdict because the call failed. It used to land in `abstained`.
            "failed": 0,
            # A sub-count of failed, the way not_visible is a sub-count of
            # abstained: the failures that were a rejected response rather
            # than a refusal, a truncation or a transport error.
            "rejected": 0,
            "unlabeled": 0,
        }
        for key in CRITERIA_KEYS
    }
    joins = []
    for entrance_id in sorted(screenings):
        summary = screenings[entrance_id].summary
        for key in CRITERIA_KEYS:
            cell = summary[key]
            verdict = cell.verdict
            failed = verdict is None and bool(cell.rejected or cell.failed)
            label = truth.get((entrance_id, key))
            if label is None:
                per_criterion[key]["unlabeled"] += 1
                continue
            outcome = classify(verdict, label, failed=failed)
            per_criterion[key][outcome] += 1
            if verdict == "not_visible":
                per_criterion[key]["not_visible"] += 1
            if outcome == "failed" and cell.rejected:
                per_criterion[key]["rejected"] += 1
            joins.append(
                {
                    "entrance_id": entrance_id,
                    "criterion": key,
                    "verdict": verdict,
                    "truth": label,
                    "outcome": outcome,
                    # How many views produced nothing here, and why. Zero on a
                    # clean cell; a nonzero `rejected` beside a null verdict is
                    # the discarded answer this ticket exists to make visible.
                    "rejected_views": cell.rejected,
                    "failed_views": cell.failed,
                }
            )
    return per_criterion, joins


def rejected_response_stats(screenings):
    """View-level accounting of rejected responses (TICK-399, AC4).

    Reported beside the abstention rate and never inside it. `responses` is
    one per model call the engine made an assessment out of - per view in
    per-image mode, per entrance in integrated mode.

    `first_attempt_rejected` is the number the OLD engine would have discarded
    outright: every one of these lost all four criteria for that view and was
    scored as an abstention. `discarded` is what is still lost after the
    bounded retry and field-level recovery, so the pair is this fix's before
    and after, measured on the same run rather than across two.
    """
    stats = {
        "responses": 0,
        "first_attempt_rejected": 0,
        "retry_calls": 0,
        "recovered_by_retry": 0,
        "partially_recovered": 0,
        "discarded": 0,
        "other_failures": 0,
        "entrances_with_no_verdicts": [],
    }
    for entrance_id in sorted(screenings):
        screening = screenings[entrance_id]
        for assessment in screening.assessments:
            stats["responses"] += 1
            stats["retry_calls"] += max(0, assessment.attempts - 1)
            if assessment.rejected_attempts:
                stats["first_attempt_rejected"] += 1
            if assessment.failure == FAILURE_REJECTED:
                if assessment.criteria is None:
                    stats["discarded"] += 1
                else:
                    stats["partially_recovered"] += 1
            elif assessment.failure is not None:
                stats["other_failures"] += 1
            elif assessment.rejected_attempts:
                stats["recovered_by_retry"] += 1
        summary = screening.summary
        if all(summary[key].verdict is None for key in CRITERIA_KEYS) and any(
            summary[key].rejected or summary[key].failed for key in CRITERIA_KEYS
        ):
            # AC2: an entrance the engine never successfully assessed. It is
            # named, not left to be inferred from an abstention count.
            stats["entrances_with_no_verdicts"].append(entrance_id)
    responses = stats["responses"]
    stats["first_attempt_rejection_rate"] = (
        stats["first_attempt_rejected"] / responses if responses else None
    )
    stats["discard_rate"] = stats["discarded"] / responses if responses else None
    return stats


def entrance_calls(screenings, joins):
    """The entrance-level call: how each entrance's labeled criteria scored.

    `all_committed_correct` is the call itself - True when the engine committed
    to at least one criterion for this entrance and got every one it committed
    to right. Abstentions are reported beside it but never make the call wrong,
    the same rule the per-criterion numbers follow: declining to guess is not
    an error. An entrance the engine committed to nothing on has no call, which
    is not the same as a failed one, so it is None and stays out of the
    agreement figure.

    Failed cells (TICK-399) are counted in their own column, not in
    `abstained`. An entrance whose every view was rejected therefore shows
    four failures and no abstentions, instead of reading as a door the engine
    looked at and honestly declined to call.

    Every screened entrance appears, including one with no labels at all -
    vanishing from the report is how an entrance goes unnoticed.
    """
    counts = {
        entrance_id: {outcome: 0 for outcome in OUTCOMES}
        for entrance_id in screenings
    }
    for join in joins:
        counts[join["entrance_id"]][join["outcome"]] += 1
    calls = {}
    for entrance_id in sorted(counts):
        tally = counts[entrance_id]
        committed = tally["correct"] + tally["wrong"]
        calls[entrance_id] = {
            **tally,
            "accuracy_of_committed": accuracy_of_committed(tally),
            "all_committed_correct": tally["wrong"] == 0 if committed else None,
        }
    return calls


def _condition_joins(screenings, captures, labels):
    """Score each image against its capture's recorded conditions."""
    truth = {
        (label["entrance_id"], label["criterion"]): label["truth"]
        for label in labels
    }
    joins = []
    for entrance_id in sorted(screenings):
        assessments = screenings[entrance_id].assessments
        entrance_captures = captures[entrance_id]
        if len(assessments) != len(entrance_captures):
            raise ScreeningEvalError(
                f"entrance {entrance_id} produced {len(assessments)} per-image "
                f"assessments for {len(entrance_captures)} captures"
            )
        for assessment, capture in zip(assessments, entrance_captures):
            conditions = capture.sidecar["conditions"]
            recorded = {key: conditions[key] for key in CONDITION_KEYS}
            for key in CRITERIA_KEYS:
                label = truth.get((entrance_id, key))
                if label is None:
                    continue
                verdict, failure = criterion_verdict(assessment, key)
                joins.append({
                    "capture_id": capture.capture_id,
                    "entrance_id": entrance_id,
                    "criterion": key,
                    "verdict": verdict,
                    "truth": label,
                    "outcome": classify(
                        verdict, label, failed=failure is not None),
                    # Which failure, when there was one, so a condition cell
                    # full of failures is not read as a condition the engine
                    # honestly abstains under (TICK-399).
                    "failure": failure,
                    "conditions": recorded,
                })
    return joins


def _condition_label(dimension, value):
    if dimension == "distance_m":
        return repr(float(value))
    return str(value)


def _condition_sort_key(dimension, value):
    if dimension == "distance_m":
        return float(value)
    return str(value)


def _outcome_metrics(rows):
    counts = {
        outcome: sum(row["outcome"] == outcome for row in rows)
        for outcome in OUTCOMES
    }
    rejected = sum(
        1 for row in rows
        if row["outcome"] == "failed" and row.get("failure") == FAILURE_REJECTED
    )
    scored = sum(counts.values())
    entrance_count = len({row["entrance_id"] for row in rows})
    return {
        "analysis": "exploratory",
        "capture_count": len({row["capture_id"] for row in rows}),
        "entrance_count": entrance_count,
        "underpowered": entrance_count < MIN_CONDITION_ENTRANCES,
        **counts,
        "rejected": rejected,
        "accuracy_of_committed": accuracy_of_committed(counts),
        "abstention_rate": counts["abstained"] / scored if scored else None,
        "failure_rate": counts["failed"] / scored if scored else None,
    }


def _condition_analysis(joins):
    dimensions = {}
    for dimension in CONDITION_KEYS:
        observed = {row["conditions"][dimension] for row in joins}
        if dimension == "distance_m":
            observed = {float(value) for value in observed}
        values = sorted(
            observed,
            key=lambda value: _condition_sort_key(dimension, value),
        )
        groups = {}
        for value in values:
            rows = [
                row for row in joins
                if (
                    float(row["conditions"][dimension]) == value
                    if dimension == "distance_m"
                    else row["conditions"][dimension] == value
                )
            ]
            groups[_condition_label(dimension, value)] = {
                "analysis": "exploratory",
                "capture_count": len({row["capture_id"] for row in rows}),
                "entrance_count": len({row["entrance_id"] for row in rows}),
                "criteria": {
                    key: _outcome_metrics([
                        row for row in rows if row["criterion"] == key
                    ])
                    for key in CRITERIA_KEYS
                },
            }
        dimensions[dimension] = {
            "analysis": "exploratory",
            "groups": groups,
        }
    return {
        "analysis": "exploratory",
        "interpretation": "descriptive associations only; not causal",
        "minimum_entrances": MIN_CONDITION_ENTRANCES,
        "dimensions": dimensions,
        "joins": joins,
    }


def entrance_flip_rates(screenings):
    """Mean flip rate per entrance across criteria with a valid verdict."""
    out = {}
    for entrance_id in sorted(screenings):
        summary = screenings[entrance_id].summary
        rates = [
            summary[key].flip_rate
            for key in CRITERIA_KEYS
            if summary[key].flip_rate is not None
        ]
        out[entrance_id] = sum(rates) / len(rates) if rates else None
    return out


def latency_stats(screenings, *, budget_s=LATENCY_BUDGET_S):
    """min/median/p95/max over every per-image latency, plus the over-budget count."""
    values = sorted(
        assessment.latency_s
        for screening in screenings.values()
        for assessment in screening.assessments
        if assessment.latency_s is not None
    )
    stats = {"budget_s": budget_s, "count": len(values), "over_budget": 0,
             "min": None, "median": None, "p95": None, "max": None}
    if not values:
        return stats
    stats["min"] = values[0]
    stats["median"] = statistics.median(values)
    stats["p95"] = values[max(0, math.ceil(0.95 * len(values)) - 1)]
    stats["max"] = values[-1]
    stats["over_budget"] = sum(1 for v in values if v > budget_s)
    return stats


def build_result(
    screenings, labels, *, split, engine, image_count, blank_skipped,
    condition_joins, duration_s,
):
    per_criterion, joins = score_joins(screenings, labels)
    overall = {
        "correct": 0, "wrong": 0, "abstained": 0, "not_visible": 0,
        "failed": 0, "rejected": 0, "unlabeled": 0,
    }
    criteria = {}
    for key in CRITERIA_KEYS:
        counts = per_criterion[key]
        for outcome, n in counts.items():
            overall[outcome] += n
        scored = _scored(counts)
        criteria[key] = {
            **counts,
            "accuracy_of_committed": accuracy_of_committed(counts),
            "abstention_rate": counts["abstained"] / scored if scored else None,
            "not_visible_rate": counts["not_visible"] / scored if scored else None,
            # Reported beside the abstention rate, never inside it (TICK-399).
            "failure_rate": counts["failed"] / scored if scored else None,
            "rejection_rate": counts["rejected"] / scored if scored else None,
        }
    scored = _scored(overall)
    calls = entrance_calls(screenings, joins)
    call_outcomes = [
        call["all_committed_correct"]
        for call in calls.values()
        if call["all_committed_correct"] is not None
    ]
    flip_rates = entrance_flip_rates(screenings)
    rated = [rate for rate in flip_rates.values() if rate is not None]
    return {
        "split": split,
        "criteria": criteria,
        "overall": {
            **overall,
            "accuracy_of_committed": accuracy_of_committed(overall),
            "abstention_rate": overall["abstained"] / scored if scored else None,
            "not_visible_rate": overall["not_visible"] / scored if scored else None,
            "failure_rate": overall["failed"] / scored if scored else None,
            "rejection_rate": overall["rejected"] / scored if scored else None,
        },
        # AC4: the rejected-response count, as its own block rather than a
        # share of the abstention rate.
        "rejected_responses": rejected_response_stats(screenings),
        "entrance_call": {
            "per_entrance": calls,
            "agreement": (
                sum(call_outcomes) / len(call_outcomes) if call_outcomes else None
            ),
        },
        "flip_rate": {
            "per_entrance": flip_rates,
            "mean": sum(rated) / len(rated) if rated else None,
        },
        "latency_s": latency_stats(screenings),
        "condition_analysis": _condition_analysis(condition_joins),
        "run": {
            "model": engine.config.model,
            "entrance_count": len(screenings),
            "image_count": image_count,
            "spend_estimate_usd": engine.spent_usd,
            "labels_scored": len(joins),
            "labels_blank_skipped": blank_skipped,
            # Recorded so freeze day is not a surprise: the sealed run is this
            # run's size, and it happens once (TICK-079).
            "duration_s": duration_s,
        },
        "joins": joins,
    }


def _fmt(value, places=3):
    return "n/a" if value is None else f"{value:.{places}f}"


def render_markdown(result):
    run = result["run"]
    lat = result["latency_s"]
    lines = [
        f"# Screening accuracy eval ({result['split']} split)",
        "",
        f"- model: {run['model']}",
        f"- entrances: {run['entrance_count']}",
        f"- images: {run['image_count']}",
        f"- spend estimate: ${run['spend_estimate_usd']:.2f}",
        f"- labeled pairs scored: {run['labels_scored']} "
        f"(blank labels skipped: {run['labels_blank_skipped']})",
        f"- total runtime: {_fmt(run['duration_s'], 1)}s",
        "",
        "Verdicts are screening statements about what is visible in photos - "
        "never measurements, never compliance conclusions. An abstention "
        "(not_visible / no verdict) is scored separately, not as an error. A "
        "FAILURE - a rejected response, a refusal, a truncation, a transport "
        "error - is scored separately again: the engine never got an answer, "
        "which is not the engine looking and declining to call it (TICK-399).",
        "",
        "## Per-criterion accuracy",
        "",
        "| criterion | correct | wrong | abstained | not visible | failed "
        "| rejected | unlabeled | accuracy of committed | abstention rate "
        "| not visible rate | failure rate |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for key in CRITERIA_KEYS:
        c = result["criteria"][key]
        lines.append(
            f"| {key} | {c['correct']} | {c['wrong']} | {c['abstained']} "
            f"| {c['not_visible']} | {c['failed']} | {c['rejected']} "
            f"| {c['unlabeled']} "
            f"| {_fmt(c['accuracy_of_committed'])} "
            f"| {_fmt(c['abstention_rate'])} | {_fmt(c['not_visible_rate'])} "
            f"| {_fmt(c['failure_rate'])} |"
        )
    overall = result["overall"]
    rejected = result["rejected_responses"]
    lost = rejected["entrances_with_no_verdicts"]
    lines += [
        "",
        "## Overall",
        "",
        f"- accuracy of committed verdicts: "
        f"{_fmt(overall['accuracy_of_committed'])} "
        f"({overall['correct']} correct / "
        f"{overall['correct'] + overall['wrong']} committed)",
        f"- abstention rate: {_fmt(overall['abstention_rate'])} "
        f"({overall['abstained']} abstained)",
        f"- not visible rate: {_fmt(overall['not_visible_rate'])} "
        f"({overall['not_visible']} of those said not visible)",
        f"- failure rate: {_fmt(overall['failure_rate'])} "
        f"({overall['failed']} produced no verdict because the call failed, "
        f"{overall['rejected']} of them a rejected response)",
        "",
        "## Rejected responses",
        "",
        "A rejected response is a model reply this engine refused - most often "
        "an eight-check ADA value (`not_applicable`, `cannot_determine`) "
        "inside the four-criterion block. It is a failure of the call, not an "
        "abstention, and it is counted here rather than in the abstention "
        "rate. `first attempt rejected` is what the pre-TICK-399 engine would "
        "have discarded outright; `discarded` is what is still lost after one "
        "bounded retry and field-level recovery.",
        "",
        f"- responses assessed: {rejected['responses']}",
        f"- first attempt rejected: {rejected['first_attempt_rejected']} "
        f"({_fmt(rejected['first_attempt_rejection_rate'])})",
        f"- retry calls made: {rejected['retry_calls']}",
        f"- recovered by retry: {rejected['recovered_by_retry']}",
        f"- partially recovered (some criteria kept): "
        f"{rejected['partially_recovered']}",
        f"- discarded after retry and recovery: {rejected['discarded']} "
        f"({_fmt(rejected['discard_rate'])})",
        f"- other failures (refusal, truncation, transport): "
        f"{rejected['other_failures']}",
        "- entrances with no verdict on any criterion: "
        + (", ".join(lost) if lost else "none"),
        "",
        "## Entrance-level call",
        "",
        "An entrance's call is correct when every verdict the engine committed "
        "to for it was right. Abstentions are shown but never make the call "
        "wrong; an entrance the engine committed to nothing on has no call. "
        "Failures are shown in their own column, so an entrance the engine "
        "never successfully assessed cannot read as one it honestly declined.",
        "",
        "| entrance | correct | wrong | abstained | failed "
        "| accuracy of committed | all committed correct |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        *(
            f"| {entrance_id} | {call['correct']} | {call['wrong']} "
            f"| {call['abstained']} | {call['failed']} "
            f"| {_fmt(call['accuracy_of_committed'])} "
            f"| {'n/a' if call['all_committed_correct'] is None else ('yes' if call['all_committed_correct'] else 'no')} |"
            for entrance_id, call in result["entrance_call"]["per_entrance"].items()
        ),
        f"| agreement | | | | | | {_fmt(result['entrance_call']['agreement'])} |",
    ]
    condition_analysis = result["condition_analysis"]
    for dimension in CONDITION_KEYS:
        groups = condition_analysis["dimensions"][dimension]["groups"]
        lines += [
            "",
            f"## Exploratory condition analysis: {dimension}",
            "",
            "**Exploratory — descriptive associations only; not causal.**",
            "",
            "| analysis | value | criterion | captures | entrances | status "
            "| correct | wrong | abstained | failed | rejected "
            "| accuracy of committed | abstention rate |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- "
            "| --- | --- |",
        ]
        for value, group in groups.items():
            for key in CRITERIA_KEYS:
                metrics = group["criteria"][key]
                status = (
                    "underpowered" if metrics["underpowered"] else "descriptive"
                )
                lines.append(
                    f"| exploratory | {value} | {key} | "
                    f"{metrics['capture_count']} | {metrics['entrance_count']} | "
                    f"{status} | {metrics['correct']} | {metrics['wrong']} | "
                    f"{metrics['abstained']} | {metrics['failed']} | "
                    f"{metrics['rejected']} | "
                    f"{_fmt(metrics['accuracy_of_committed'])} | "
                    f"{_fmt(metrics['abstention_rate'])} |"
                )
    lines += [
        "",
        "## Per-entrance cross-view consistency (flip rate)",
        "",
        "| entrance | mean flip rate |",
        "| --- | --- |",
    ]
    for entrance_id, rate in result["flip_rate"]["per_entrance"].items():
        lines.append(f"| {entrance_id} | {_fmt(rate)} |")
    lines += [
        f"| mean | {_fmt(result['flip_rate']['mean'])} |",
        "",
        f"## Latency vs the {lat['budget_s']:.0f}s budget",
        "",
        "| min | median | p95 | max | over budget |",
        "| --- | --- | --- | --- | --- |",
        f"| {_fmt(lat['min'])} | {_fmt(lat['median'])} | {_fmt(lat['p95'])} "
        f"| {_fmt(lat['max'])} | {lat['over_budget']} of {lat['count']} |",
        "",
    ]
    return "\n".join(lines)


def write_outputs(result, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / JSON_NAME
    md_path = out_dir / MARKDOWN_NAME
    json_path.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return json_path, md_path


def run_eval(
    *,
    manifest_path,
    labels_path,
    out_dir,
    closeout_path=None,
    sidecar_dir=None,
    engine,
    get_capture,
    verify_images=None,
    image_source=None,
    image_remedy=None,
    split="dev",
    audit=None,
    argv=None,
):
    """Screen every entrance of one split and write the report.

    engine is any object with screen_entrance / config / spent_usd (the real
    ScreeningEngine, or a fake in tests); get_capture maps a capture_id to a
    hash-verified Capture carrying both image bytes and its validated sidecar
    (the real path goes through the hash-verifying DatasetLoader).

    verify_images, when given, takes this run's capture IDs and its split and returns the ones
    with no object in the bucket. It is checked BEFORE the audit line, so a dataset whose bytes
    were never uploaded refuses the run instead of burning the seal on the first fetch. None skips
    the check, which is for tests that inject their own captures; the CLI always supplies one.

    It proves the objects EXIST, not that they are the committed bytes -- only the loader's hash
    check does that, and that needs the bytes themselves. A run can still fail after the audit
    line on a hash mismatch; existence is the part that can be settled cheaply and in advance.

    split="sealed" needs `audit`, a mapping with labels.AUDIT_KEYS. It is the
    audit context, and it is also the permission: sealed labels are released
    only after seal_audit.record_unsealing appends the SEAL_AUDIT.log line, so
    the log gains exactly one line and gains it before the first sealed image
    is fetched. `argv` is recorded as that line's command. A dirty working tree
    raises SealAuditError here, having written and read nothing.
    """
    sealed_run = split == "sealed"
    _require_permitted_split(split, allow_sealed=audit is not None)
    started = time.perf_counter()
    manifest_path = Path(manifest_path)
    sidecar_dir = (
        Path(sidecar_dir) if sidecar_dir else manifest_path.parent / "sidecars"
    )
    closeout_path = (
        Path(closeout_path)
        if closeout_path
        else manifest_path.parent / "dataset-closeout.json"
    )
    # EVERYTHING THAT CAN FAIL AND READS NOTHING SEALED HAPPENS BEFORE THE AUDIT LINE.
    #
    # `labels_for_eval` is what appends to SEAL_AUDIT.log, and that append is irreversible: a
    # crash after it means the seal is open, no report exists, and a retry is a SECOND unsealing
    # (R-5). Until now the closeout load and the manifest walk ran AFTER it, so a stale closeout
    # -- exactly the failure #69 added a hash check for -- burned the seal on its way to being
    # reported. Reading labels, the closeout and the manifest touches no capture bytes and no
    # sealed object, so all of it belongs on this side of the line.
    loaded = load_labels(labels_path)
    eligible_entrances = load_eligible_entrances(
        closeout_path, manifest_path, sidecar_dir
    )
    entrances = collect_entrances(
        manifest_path,
        eligible_entrances=eligible_entrances,
        split=split,
        allow_sealed=sealed_run,
    )
    if verify_images is not None:
        missing = set(verify_images(
            sorted(
                capture_id
                for capture_ids in entrances.values()
                for capture_id in capture_ids
            ),
            split,
        ))
        if missing:
            # The entrances actually affected, not the run's total. "1 capture missing across 28
            # entrances" reads as a dataset-wide outage when it is one file.
            affected = sum(
                1
                for capture_ids in entrances.values()
                if any(capture_id in missing for capture_id in capture_ids)
            )
            raise MissingCaptureObjects(
                sorted(missing), affected, split,
                source=image_source, remedy=image_remedy)
    labels = labels_for_eval(
        list(loaded.labels),
        split=split,
        audited=sealed_run,
        audit=audit,
        argv=argv,
    )
    # A labeled entrance with no captures is AC4's "entrance with no views":
    # it must appear with an empty view list, not vanish from the report.
    recorded_entrances = {
        canonical_entrance_id(row["entrance_id"])
        for row in read_manifest(manifest_path)
    }
    for label in labels:
        entrance_id = canonical_entrance_id(label["entrance_id"])
        if (
            entrance_id in eligible_entrances
            or entrance_id not in recorded_entrances
        ):
            entrances.setdefault(entrance_id, [])
    entrances = {eid: caps for eid, caps in sorted(entrances.items())}
    screenings = {}
    captures = {}
    image_count = 0
    for entrance_id, capture_ids in entrances.items():
        entrance_captures = [get_capture(capture_id) for capture_id in capture_ids]
        captures[entrance_id] = entrance_captures
        image_count += len(entrance_captures)
        screenings[entrance_id] = engine.screen_entrance(
            entrance_id,
            [capture.image for capture in entrance_captures],
            allow_sealed=sealed_run,
        )
    condition_joins = _condition_joins(screenings, captures, labels)
    result = build_result(
        screenings,
        labels,
        split=split,
        engine=engine,
        image_count=image_count,
        blank_skipped=loaded.blank_skipped,
        condition_joins=condition_joins,
        duration_s=round(time.perf_counter() - started, 3),
    )
    write_outputs(result, out_dir)
    return result


def main(argv=None, *, from_cli=False):
    parser = argparse.ArgumentParser(
        prog="python -m frontdoor.screening_eval",
        description=(
            "Screening accuracy eval. Scores the dev split by default; "
            "--include-sealed performs the once-only, audited freeze-day run."
        ),
    )
    parser.add_argument("--manifest", required=True, help="path to data/manifest.csv")
    parser.add_argument("--labels", required=True, help="path to the labels CSV")
    parser.add_argument("--out", required=True, help="directory for the report files")
    parser.add_argument(
        "--images",
        help="read capture images from this local directory instead of the bucket, located by "
             "each sidecar's own image.path. Bytes are still hash-verified against the manifest, "
             "and a sealed capture is still refused unless this is the audited run (#342).",
    )
    parser.add_argument(
        "--sidecars",
        default=None,
        help="sidecar directory (default: <manifest dir>/sidecars)",
    )
    parser.add_argument(
        "--closeout",
        default=None,
        help="dataset closeout (default: <manifest dir>/dataset-closeout.json)",
    )
    parser.add_argument(
        "--include-sealed",
        action="store_true",
        help="score the sealed split instead of dev, once, recording the "
             "unsealing in SEAL_AUDIT.log first (D-007, D-017)",
    )
    args = parser.parse_args(argv)

    # Same rule as frontdoor.eval: the unsealing is a deliberate act at a
    # terminal. from_cli is passed only by the __main__ block below, so an
    # import cannot reach it by arranging sys.argv.
    if args.include_sealed and not from_cli:
        print(
            "--include-sealed is only accepted from the command line. "
            "Run `python -m frontdoor.screening_eval --include-sealed` in a "
            "terminal; the unsealing run is audited and happens once (D-017).",
            file=sys.stderr,
        )
        return 2

    # The eval makes live model calls; a keyless run must fail here, clearly,
    # before any manifest, label, or output file is touched.
    from frontdoor import storage

    storage._load_dotenv_once()
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print(
            "no ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) in the environment "
            "or .env; the screening eval makes live model calls and will not "
            "start without one. Nothing was read or written.",
            file=sys.stderr,
        )
        return 2

    from frontdoor.loader import DatasetLoader

    manifest_path = Path(args.manifest)
    sidecar_dir = (
        Path(args.sidecars) if args.sidecars else manifest_path.parent / "sidecars"
    )
    loader = DatasetLoader(manifest_path, sidecar_dir)

    # --images points the run at the directory the photographs are already in, instead of at the
    # bucket they have not been uploaded to (#342). The seal is enforced by the reader itself:
    # DatasetLoader hands an injected getter the bytes before it ever reaches storage.get, so if
    # LocalImages does not refuse a sealed capture, nothing does.
    local_images = None
    if args.images:
        from frontdoor.local_images import LocalImages

        local_images = LocalImages(
            args.images, sidecar_dir, allow_sealed=args.include_sealed)
        # The getter derives each capture's split from the manifest and uses only `_row`, so the
        # plain loader above is what it reads through; the reading loader is built from it.
        loader = DatasetLoader(
            manifest_path, sidecar_dir, get_image=local_images.getter(loader))

    def verify_images(capture_ids, split):
        """Which of these captures cannot be read, before the audit line is written.

        Existence only: nothing is downloaded and no model is called, which is the entire point of
        doing it here. Every capture in one run shares the run's split (collect_entrances filters
        on it), so the partition comes from the caller rather than being re-derived per capture id.
        """
        if local_images is not None:
            return local_images.missing(capture_ids, split)

        from frontdoor.storage import missing_capture_objects

        return missing_capture_objects(
            (capture_id, split) for capture_id in capture_ids
        )

    def get_capture(capture_id):
        # loader.load refuses sealed rows outright, so the unsealing run goes
        # through _load_row's allow_sealed - the same doorway frontdoor.eval
        # uses. Everything else stays on the public API.
        if args.include_sealed:
            return loader._load_row(loader._row(capture_id), allow_sealed=True)
        return loader.load(capture_id)

    audit = None
    try:
        if args.include_sealed:
            # The audit context comes from frontdoor.eval so both unsealing
            # doorways describe the same checkout, manifest and log. Imported
            # here rather than at module scope because resolving the repo root
            # raises outside a git checkout, and a dev run has no business
            # failing on that.
            from frontdoor.eval import AUDIT_LOG, REPO_ROOT, _storage_config

            audit = {
                "manifest_path": manifest_path,
                "audit_path": AUDIT_LOG,
                "repo": REPO_ROOT,
                # Raises rather than recording a line that cannot say which
                # bucket the one unsealing run read.
                "config": _storage_config(),
            }
        result = run_eval(
            manifest_path=manifest_path,
            labels_path=args.labels,
            out_dir=args.out,
            closeout_path=(
                Path(args.closeout)
                if args.closeout
                else manifest_path.parent / "dataset-closeout.json"
            ),
            sidecar_dir=sidecar_dir,
            engine=ScreeningEngine(
                config=ScreeningConfig(max_usd_per_run=EVAL_MAX_USD_PER_RUN)
            ),
            get_capture=get_capture,
            verify_images=verify_images,
            image_source=(
                f"the local directory {args.images}" if args.images else None),
            image_remedy=(
                f"Check that {args.images} is the directory holding the capture photographs, and "
                "that each is at the path its sidecar names." if args.images else None),
            split="sealed" if args.include_sealed else "dev",
            audit=audit,
            argv=sys.argv if argv is None else [sys.argv[0], *argv],
        )
    except (DatasetCloseoutError, MissingCaptureObjects, SealAuditError) as exc:
        # Nothing sealed has been read: the run is refused, not half-done.
        print(exc, file=sys.stderr)
        return 1
    except SpendCapError as exc:
        # The audit line is written before the first image. Hitting the cap
        # on --include-sealed means the seal is already open; a retry is a
        # second unsealing. A dry-run cap abort has not opened anything.
        print(exc, file=sys.stderr)
        if args.include_sealed:
            print(
                "the unsealing has already been recorded; commit "
                "SEAL_AUDIT.log and do not re-run --include-sealed. A "
                "recovery run is a second unsealing.",
                file=sys.stderr,
            )
        return 1
    run = result["run"]
    rejected = result["rejected_responses"]
    print(
        f"scored {run['labels_scored']} labeled pairs over "
        f"{run['entrance_count']} entrances in {_fmt(run['duration_s'], 1)}s; "
        f"accuracy of committed verdicts: "
        f"{_fmt(result['overall']['accuracy_of_committed'])}; "
        f"rejected responses: {rejected['first_attempt_rejected']} of "
        f"{rejected['responses']} on first attempt, {rejected['discarded']} "
        f"still discarded after retry; "
        f"report in {args.out}"
    )
    return 0


if __name__ == "__main__":
    # The only place from_cli is True, so --include-sealed cannot be reached
    # by an import however sys.argv is arranged.
    sys.exit(main(from_cli=True))
