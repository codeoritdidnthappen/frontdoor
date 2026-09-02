"""Screening accuracy eval: engine verdicts vs human labels (TICK-245, TICK-246).

Runs the vision screening engine over every captured view of each entrance in
one unsealed split (dev by default), joins the per-criterion majority verdicts
to the human ground-truth labels, and writes the accuracy report the results
freeze will be judged against: per-criterion correct / wrong / abstained, the
accuracy of committed verdicts, per-entrance cross-view flip rates, and
latency against the 15-second budget.

Scoring vocabulary: labels are presence-only ("present"/"absent") because the
operator stood at the door; the engine may also answer not_visible or produce
no verdict at all. A not_visible (or missing) majority verdict is an
ABSTENTION - scored separately, never counted correct or wrong, because
declining to guess is the honest answer the engine is instructed to give.

Split discipline (D-007, D-017): the split is resolved here from each entrance
ID via the committed seed, exactly like the screening engine, and the sealed
split is refused outright. The audited unsealing path is deliberately NOT
implemented in this runner: freeze-day sealed scoring is a separate, audited,
human-run process (labels_for_eval with audited=True plus a recorded
SEAL_AUDIT.log line), and this module never passes that flag.

Run:  python -m frontdoor.screening_eval --manifest ... --labels ... --out ...
"""

import argparse
import json
import math
import os
import statistics
import sys
from pathlib import Path

from frontdoor.labels import labels_for_eval, load_labels
from frontdoor.manifest import read_manifest
from frontdoor.screening import CRITERIA_KEYS, ScreeningEngine, SealedSplitError
from frontdoor.split import assign_split, canonical_entrance_id

#: Per-image latency budget (seconds); the report counts every view over it.
LATENCY_BUDGET_S = 15.0

#: The splits this runner will score. sealed is refused, not merely absent.
EVAL_SPLITS = ("dev", "calib")

JSON_NAME = "screening_eval.json"
MARKDOWN_NAME = "screening_eval.md"


class ScreeningEvalError(ValueError):
    """Raised when the eval cannot produce a trustworthy report."""


def _require_unsealed_split(split):
    """Refuse sealed before any file is read, exactly like the engine."""
    if split == "sealed":
        raise SealedSplitError(
            "the sealed split is not scored by this runner; freeze-day sealed "
            "scoring is a separate, audited run (D-007, D-017)"
        )
    if split not in EVAL_SPLITS:
        raise ScreeningEvalError(
            f"unknown split {split!r}; expected one of {EVAL_SPLITS}"
        )


def collect_entrances(manifest_path, *, split="dev"):
    """Entrance ID -> sorted capture IDs for one unsealed split.

    The split is re-derived from the committed seed per entrance; the
    manifest's split cell is a cache, not an authority.
    """
    _require_unsealed_split(split)
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
        key: {"correct": 0, "wrong": 0, "abstained": 0, "unlabeled": 0}
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


def build_result(screenings, labels, *, split, engine, image_count, blank_skipped):
    per_criterion, joins = score_joins(screenings, labels)
    overall = {"correct": 0, "wrong": 0, "abstained": 0, "unlabeled": 0}
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
        }
    scored = overall["correct"] + overall["wrong"] + overall["abstained"]
    flip_rates = entrance_flip_rates(screenings)
    rated = [rate for rate in flip_rates.values() if rate is not None]
    return {
        "split": split,
        "criteria": criteria,
        "overall": {
            **overall,
            "accuracy_of_committed": accuracy_of_committed(overall),
            "abstention_rate": overall["abstained"] / scored if scored else None,
        },
        "flip_rate": {
            "per_entrance": flip_rates,
            "mean": sum(rated) / len(rated) if rated else None,
        },
        "latency_s": latency_stats(screenings),
        "run": {
            "model": engine.config.model,
            "entrance_count": len(screenings),
            "image_count": image_count,
            "spend_estimate_usd": engine.spent_usd,
            "labels_scored": len(joins),
            "labels_blank_skipped": blank_skipped,
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
        "",
        "Verdicts are screening statements about what is visible in photos - "
        "never measurements, never compliance conclusions. An abstention "
        "(not_visible / no verdict) is scored separately, not as an error.",
        "",
        "## Per-criterion accuracy",
        "",
        "| criterion | correct | wrong | abstained | unlabeled "
        "| accuracy of committed | abstention rate |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for key in CRITERIA_KEYS:
        c = result["criteria"][key]
        lines.append(
            f"| {key} | {c['correct']} | {c['wrong']} | {c['abstained']} "
            f"| {c['unlabeled']} | {_fmt(c['accuracy_of_committed'])} "
            f"| {_fmt(c['abstention_rate'])} |"
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
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return json_path, md_path


def run_eval(*, manifest_path, labels_path, out_dir, engine, get_image, split="dev"):
    """Screen every entrance of one unsealed split and write the report.

    engine is any object with screen_entrance / config / spent_usd (the real
    ScreeningEngine, or a fake in tests); get_image maps a capture_id to image
    bytes (the real path goes through the hash-verifying DatasetLoader).
    """
    _require_unsealed_split(split)
    loaded = load_labels(labels_path)
    labels = labels_for_eval(list(loaded.labels), split=split)
    entrances = collect_entrances(manifest_path, split=split)
    screenings = {}
    image_count = 0
    for entrance_id, capture_ids in entrances.items():
        images = [get_image(capture_id) for capture_id in capture_ids]
        image_count += len(images)
        screenings[entrance_id] = engine.screen_entrance(entrance_id, images)
    result = build_result(
        screenings,
        labels,
        split=split,
        engine=engine,
        image_count=image_count,
        blank_skipped=loaded.blank_skipped,
    )
    write_outputs(result, out_dir)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m frontdoor.screening_eval",
        description=(
            "Screening accuracy eval on the dev split. Freeze-day sealed "
            "scoring is a separate, audited run and is not available here."
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
    args = parser.parse_args(argv)

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
    result = run_eval(
        manifest_path=manifest_path,
        labels_path=args.labels,
        out_dir=args.out,
        engine=ScreeningEngine(),
        get_image=lambda capture_id: loader.load(capture_id).image,
    )
    overall = result["overall"]
    print(
        f"scored {result['run']['labels_scored']} labeled pairs over "
        f"{result['run']['entrance_count']} entrances; accuracy of committed "
        f"verdicts: {_fmt(overall['accuracy_of_committed'])}; report in {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
