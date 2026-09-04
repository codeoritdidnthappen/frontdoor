"""Screening accuracy eval: engine verdicts vs human labels (TICK-245, TICK-246).

Runs the vision screening engine over every captured view of each entrance in
one unsealed split (dev by default), joins the per-criterion majority verdicts
to the human ground-truth labels, and writes the accuracy report the results
freeze will be judged against: per-criterion correct / wrong / abstained, the
accuracy of committed verdicts, the not-visible rate, the entrance-level call,
per-entrance cross-view flip rates, and latency against the 15-second budget.

Scoring vocabulary: labels are presence-only ("present"/"absent") because the
operator stood at the door; the engine may also answer not_visible or produce
no verdict at all. A not_visible (or missing) majority verdict is an
ABSTENTION - scored separately, never counted correct or wrong, because
declining to guess is the honest answer the engine is instructed to give.

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

from frontdoor.labels import SPLITS, labels_for_eval, load_labels
from frontdoor.manifest import read_manifest
from frontdoor.screening import (
    ALLOWED_VERDICTS,
    CRITERIA_KEYS,
    ScreeningEngine,
    SealedSplitError,
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

JSON_NAME = "screening_eval.json"
MARKDOWN_NAME = "screening_eval.md"


class ScreeningEvalError(ValueError):
    """Raised when the eval cannot produce a trustworthy report."""


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


def collect_entrances(manifest_path, *, split="dev", allow_sealed=False):
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
        entrances.setdefault(entrance_id, []).append(row["capture_id"])
    return {eid: sorted(caps) for eid, caps in sorted(entrances.items())}


def classify(verdict, truth):
    """One join cell: engine majority verdict vs human truth."""
    if verdict is None or verdict == "not_visible":
        return "abstained"
    return "correct" if verdict == truth else "wrong"


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
            "unlabeled": 0,
        }
        for key in CRITERIA_KEYS
    }
    joins = []
    for entrance_id in sorted(screenings):
        summary = screenings[entrance_id].summary
        for key in CRITERIA_KEYS:
            verdict = summary[key].verdict
            label = truth.get((entrance_id, key))
            if label is None:
                per_criterion[key]["unlabeled"] += 1
                continue
            outcome = classify(verdict, label)
            per_criterion[key][outcome] += 1
            if verdict == "not_visible":
                per_criterion[key]["not_visible"] += 1
            joins.append(
                {
                    "entrance_id": entrance_id,
                    "criterion": key,
                    "verdict": verdict,
                    "truth": label,
                    "outcome": outcome,
                }
            )
    return per_criterion, joins


def entrance_calls(screenings, joins):
    """The entrance-level call: how each entrance's labeled criteria scored.

    `all_committed_correct` is the call itself - True when the engine committed
    to at least one criterion for this entrance and got every one it committed
    to right. Abstentions are reported beside it but never make the call wrong,
    the same rule the per-criterion numbers follow: declining to guess is not
    an error. An entrance the engine committed to nothing on has no call, which
    is not the same as a failed one, so it is None and stays out of the
    agreement figure.

    Every screened entrance appears, including one with no labels at all -
    vanishing from the report is how an entrance goes unnoticed.
    """
    counts = {
        entrance_id: {"correct": 0, "wrong": 0, "abstained": 0}
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
                verdict = None
                if assessment.criteria is not None:
                    candidate = assessment.criteria[key]["verdict"]
                    if candidate in ALLOWED_VERDICTS:
                        verdict = candidate
                joins.append({
                    "capture_id": capture.capture_id,
                    "entrance_id": entrance_id,
                    "criterion": key,
                    "verdict": verdict,
                    "truth": label,
                    "outcome": classify(verdict, label),
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
        for outcome in ("correct", "wrong", "abstained")
    }
    scored = sum(counts.values())
    entrance_count = len({row["entrance_id"] for row in rows})
    return {
        "analysis": "exploratory",
        "capture_count": len({row["capture_id"] for row in rows}),
        "entrance_count": entrance_count,
        "underpowered": entrance_count < MIN_CONDITION_ENTRANCES,
        **counts,
        "accuracy_of_committed": accuracy_of_committed(counts),
        "abstention_rate": counts["abstained"] / scored if scored else None,
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
        "correct": 0, "wrong": 0, "abstained": 0, "not_visible": 0, "unlabeled": 0,
    }
    criteria = {}
    for key in CRITERIA_KEYS:
        counts = per_criterion[key]
        for outcome, n in counts.items():
            overall[outcome] += n
        scored = counts["correct"] + counts["wrong"] + counts["abstained"]
        criteria[key] = {
            **counts,
            "accuracy_of_committed": accuracy_of_committed(counts),
            "abstention_rate": counts["abstained"] / scored if scored else None,
            "not_visible_rate": counts["not_visible"] / scored if scored else None,
        }
    scored = overall["correct"] + overall["wrong"] + overall["abstained"]
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
        },
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
        "(not_visible / no verdict) is scored separately, not as an error.",
        "",
        "## Per-criterion accuracy",
        "",
        "| criterion | correct | wrong | abstained | not visible | unlabeled "
        "| accuracy of committed | abstention rate | not visible rate |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for key in CRITERIA_KEYS:
        c = result["criteria"][key]
        lines.append(
            f"| {key} | {c['correct']} | {c['wrong']} | {c['abstained']} "
            f"| {c['not_visible']} | {c['unlabeled']} "
            f"| {_fmt(c['accuracy_of_committed'])} "
            f"| {_fmt(c['abstention_rate'])} | {_fmt(c['not_visible_rate'])} |"
        )
    overall = result["overall"]
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
        "",
        "## Entrance-level call",
        "",
        "An entrance's call is correct when every verdict the engine committed "
        "to for it was right. Abstentions are shown but never make the call "
        "wrong; an entrance the engine committed to nothing on has no call.",
        "",
        "| entrance | correct | wrong | abstained | accuracy of committed "
        "| all committed correct |",
        "| --- | --- | --- | --- | --- | --- |",
        *(
            f"| {entrance_id} | {call['correct']} | {call['wrong']} "
            f"| {call['abstained']} | {_fmt(call['accuracy_of_committed'])} "
            f"| {'n/a' if call['all_committed_correct'] is None else ('yes' if call['all_committed_correct'] else 'no')} |"
            for entrance_id, call in result["entrance_call"]["per_entrance"].items()
        ),
        f"| agreement | | | | | {_fmt(result['entrance_call']['agreement'])} |",
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
            "| correct | wrong | abstained | accuracy of committed "
            "| abstention rate |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
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
                    f"{metrics['abstained']} | "
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
    engine,
    get_capture,
    split="dev",
    audit=None,
    argv=None,
):
    """Screen every entrance of one split and write the report.

    engine is any object with screen_entrance / config / spent_usd (the real
    ScreeningEngine, or a fake in tests); get_capture maps a capture_id to a
    hash-verified Capture carrying both image bytes and its validated sidecar
    (the real path goes through the hash-verifying DatasetLoader).

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
    loaded = load_labels(labels_path)
    labels = labels_for_eval(
        list(loaded.labels),
        split=split,
        audited=sealed_run,
        audit=audit,
        argv=argv,
    )
    entrances = collect_entrances(
        manifest_path, split=split, allow_sealed=sealed_run
    )
    # A labeled entrance with no captures is AC4's "entrance with no views":
    # it must appear with an empty view list, not vanish from the report.
    for label in labels:
        entrances.setdefault(canonical_entrance_id(label["entrance_id"]), [])
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
        "--sidecars",
        default=None,
        help="sidecar directory (default: <manifest dir>/sidecars)",
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
            engine=ScreeningEngine(),
            get_capture=get_capture,
            split="sealed" if args.include_sealed else "dev",
            audit=audit,
            argv=sys.argv if argv is None else [sys.argv[0], *argv],
        )
    except SealAuditError as exc:
        # Nothing sealed has been read: the run is refused, not half-done.
        print(exc, file=sys.stderr)
        return 1
    run = result["run"]
    print(
        f"scored {run['labels_scored']} labeled pairs over "
        f"{run['entrance_count']} entrances in {_fmt(run['duration_s'], 1)}s; "
        f"accuracy of committed verdicts: "
        f"{_fmt(result['overall']['accuracy_of_committed'])}; "
        f"report in {args.out}"
    )
    return 0


if __name__ == "__main__":
    # The only place from_cli is True, so --include-sealed cannot be reached
    # by an import however sys.argv is arranged.
    sys.exit(main(from_cli=True))
