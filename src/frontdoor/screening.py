"""Vision screening engine: LLM checklist over entrance photos (TICK-245, #167).

Two modes. Per-image: one model call per photo assesses which accessibility
features are VISIBLE - ramp or beveled threshold, handrails, accessible door
hardware, accessibility signage - and per entrance the eligible 5-7 views are
aggregated into a majority verdict per criterion with the flip-rate reported
alongside. Integrated (preferred): ALL of an entrance's views go into ONE
model call that weighs them together, so the one oblique frame that shows a
platform's riser informs the verdict instead of being outvoted by the frontal
frames that hide it. Offline eval on the 12-entrance pilot set: per-image
majority voting amplifies shared camera-position blind spots; the integrated
call raised committed accuracy from ~90% to 97% and cut abstentions 38 -> 4.

The same call also answers a fifth checklist item, face_check (TICK-257
follow-up, #232): whether any identifiable face survived the automatic blur
pass. It is a privacy audit, not an accessibility criterion - it never joins
CRITERIA or the aggregate, and callers use it to quarantine the image.

Honesty rule (load-bearing, do not relax): verdicts are screening statements
about what is visible in the photos. Never measurements, never compliance or
legal conclusions. When a feature cannot be confidently seen the verdict is
not_visible, and not_visible is never collapsed into absent.

Split discipline (D-007): callers pass entrance IDs; this module resolves the
split itself and refuses sealed-split entrances. The sealed split is scored
exactly once, at results freeze, through a deliberate human-run path - not
through this engine's day-to-day loop.

The engine is import-safe without an API key: the anthropic client is only
constructed on first use, and tests inject a fake client.
"""

import base64
import json
import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass
from importlib import resources

import anthropic

from frontdoor.split import assign_split, canonical_entrance_id

logger = logging.getLogger(__name__)

CRITERIA_KEYS = (
    "ramp_or_bevel",
    "handrails",
    "accessible_door_hardware",
    "accessibility_signage",
)

ALLOWED_VERDICTS = ("present", "absent", "not_visible")

# Eight photo-assessable ADA checks (#318). Separate from CRITERIA_KEYS: those
# four remain the evaluation vocabulary. These eight are a photo evidence
# assessment, not a compliance determination. The model returns states; the
# server alone computes score, counts, and summary.
ADA_CHECK_KEYS = (
    "entrance_route",
    "threshold",
    "ramp",
    "door_hardware",
    "door_opening",
    "handrails",
    "signage",
    "temporary_barriers",
)
ADA_RESULTS = ("true", "false", "cannot_determine", "not_applicable")
ADA_STANDARDS_URL = (
    "https://www.ada.gov/law-and-regs/design-standards/2010-stds/"
)
ADA_DISCLAIMER = (
    "Photo-based screening only. This is not an ADA compliance or legal "
    "determination."
)
ADA_MODEL_AGGREGATE_KEYS = frozenset({
    "score_percent",
    "determined_count",
    "total_count",
    "true_count",
    "false_count",
    "cannot_determine_count",
    "not_applicable_count",
    "summary",
})
_COUNT_WORDS = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
)

# The automatic privacy audit (TICK-257 follow-up, #232). NOT an accessibility
# criterion: it never joins CRITERIA, never votes in aggregate_assessments,
# and is carried separately on ImageAssessment. The model has already seen
# the blurred image by the time it answers, so a face_visible answer is a
# retention decision (quarantine the image), never an assessment one.
FACE_CHECK_KEY = "face_check"
#: What the model may answer. "clear" asserts the model checked and saw no
#: face; "face_visible" quarantines.
FACE_CHECK_ANSWERS = ("clear", "face_visible")
#: The third value the pipeline itself supplies: the check never produced an
#: answer - the model skipped the key, answered out of vocabulary, or was
#: never asked. The same distinction the verdicts already insist on
#: (not_visible is never collapsed into absent) applied to the audit: a
#: consumer must be able to tell "checked, clear" from "never answered"
#: (PR #243 review). Callers quarantine "unknown" as well as "face_visible";
#: only an explicit "clear" passes the privacy gate.
FACE_CHECK_UNKNOWN = "unknown"
FACE_CHECK_VALUES = FACE_CHECK_ANSWERS + (FACE_CHECK_UNKNOWN,)
# Tie-break order for the majority verdict: most conservative first. A tie
# never invents certainty, and not_visible stays distinct from absent.
_CONSERVATIVE_ORDER = ("not_visible", "absent", "present")

PROMPT_RESOURCE = "screening_prompts.json"


class ScreeningError(ValueError):
    """Raised when the engine cannot produce an honest screening result."""


class SealedSplitError(ScreeningError):
    """Raised when a caller asks the engine to screen a sealed-split entrance."""


class SpendCapError(ScreeningError):
    """Raised when the next call would push the run past its spend cap."""


@dataclass(frozen=True)
class ScreeningConfig:
    # Offline eval on the 12-entrance pilot set: claude-sonnet-5 matches opus at
    # 97% committed accuracy in integrated multi-view mode, at a median 7.2s vs
    # 20.6s per entrance and roughly 2.5x cheaper. max_tokens must cover
    # thinking plus the four criteria and the eight ADA checks: at 2000,
    # adaptive thinking used to consume the budget and truncate mid-object.
    model: str = "claude-sonnet-5"
    max_tokens: int = 6000
    max_usd_per_run: float = 1.00
    usd_per_image: float = 0.05  # conservative per-image estimate (cents-order)


@dataclass(frozen=True)
class ImageAssessment:
    """One image's checklist result, or a recorded error - never silence."""

    criteria: dict | None
    latency_s: float | None
    error: str | None = None
    #: The privacy audit answer ("clear", "face_visible", or "unknown"),
    #: separate from the accessibility criteria. Defaults to "unknown": an
    #: assessment built without the field never had the question answered, and
    #: reporting "clear" would assert a check that did not happen (PR #243
    #: review). A reply missing the key is likewise normalized to "unknown"
    #: (with a logged warning) rather than crashed on.
    face_check: str = FACE_CHECK_UNKNOWN
    #: The eight photo ADA checks after validation, or None when the model
    #: reply was rejected. Score, counts and summary are never stored here:
    #: callers compute them with compute_ada_screening.
    ada_checks: dict | None = None


@dataclass(frozen=True)
class CriterionSummary:
    verdict: str | None  # None when no view produced a valid verdict
    # Cross-view statistics. Both are None in integrated mode: one integrated
    # call makes no cross-view comparison, so there is no flip rate or vote
    # count to report -- and reporting a fabricated 0.0 would turn the honesty
    # signal about view disagreement into false confidence.
    flip_rate: float | None  # fraction of valid views disagreeing with verdict
    counts: dict | None  # valid verdict -> number of voting views


@dataclass(frozen=True)
class EntranceScreening:
    entrance_id: str
    split: str
    assessments: tuple
    summary: dict  # criterion key -> CriterionSummary
    # "per_image": one model call per view, summary holds real cross-view
    # statistics. "integrated": one call over all views, summary carries the
    # integrated verdicts with flip_rate/counts None.
    mode: str = "per_image"


def _prompt(name: str, **values: object) -> str:
    """Load one reviewable prompt from the packaged file at call time."""
    try:
        raw = json.loads(
            resources.files("frontdoor")
            .joinpath(PROMPT_RESOURCE)
            .read_text(encoding="utf-8")
        )
        template = raw[name]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ScreeningError(f"screening prompt {name!r} could not be loaded") from exc
    if not isinstance(template, str) or not template.strip():
        raise ScreeningError(f"screening prompt {name!r} is empty or not text")
    rendered = template
    for key, value in values.items():
        marker = "{" + key + "}"
        if marker not in rendered:
            raise ScreeningError(f"screening prompt {name!r} has no {marker} placeholder")
        rendered = rendered.replace(marker, str(value))
    return rendered


def build_prompt() -> str:
    return _prompt("single_view")


def build_integrated_prompt(view_count: int) -> str:
    """The multi-view prompt: one integrated verdict per criterion.

    The instruction to trust the view that shows the relevant area is the
    point of the mode - it is how a single oblique frame showing a riser or a
    side ramp beats the frontal frames that cannot see it.
    """
    if view_count < 1:
        raise ScreeningError("integrated prompt needs at least one view")
    return _prompt("integrated", view_count=view_count)


def parse_json_response(text):
    """Parse model output that should be bare JSON; tolerate stray fences."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ScreeningError(f"no JSON object in response: {text[:200]!r}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ScreeningError(f"response is not valid JSON: {exc}") from exc


def validate_verdicts(parsed: object) -> dict[str, dict[str, object]]:
    """Return the four valid criteria or reject the whole model response."""
    if not isinstance(parsed, dict):
        raise ScreeningError("model response must be a JSON object")
    crit = parsed.get("criteria")
    if not isinstance(crit, dict) or set(crit) != set(CRITERIA_KEYS):
        raise ScreeningError("model response must contain exactly the four criteria")
    out = {}
    for key in CRITERIA_KEYS:
        entry = crit[key]
        if not isinstance(entry, dict):
            raise ScreeningError(f"criterion {key} must be an object")
        verdict = str(entry.get("verdict", "")).strip().lower()
        if verdict not in ALLOWED_VERDICTS:
            raise ScreeningError(f"criterion {key} has invalid verdict {verdict!r}")
        confidence = entry.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, int):
            raise ScreeningError(f"criterion {key} confidence must be an integer")
        if not 0 <= confidence <= 100:
            raise ScreeningError(f"criterion {key} confidence must be from 0 through 100")
        evidence = entry.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ScreeningError(f"criterion {key} evidence must be non-empty text")
        evidence = evidence.strip()
        if "\n" in evidence or "\r" in evidence or len(evidence) > 200:
            raise ScreeningError(
                f"criterion {key} evidence must be one line of at most 200 characters"
            )
        out[key] = {
            "verdict": verdict,
            "confidence": confidence,
            "evidence": evidence,
        }
    return out


def validate_ada_checks(parsed: object) -> dict[str, dict[str, str]]:
    """Return the eight photo checks or reject the whole model response.

    Aggregate fields (score, counts, summary) and a wrapping ada_screening
    object are forbidden here: the server computes those after validation.
    """
    if not isinstance(parsed, dict):
        raise ScreeningError("model response must be a JSON object")
    if "ada_screening" in parsed:
        raise ScreeningError("model must not supply ada_screening")
    supplied = ADA_MODEL_AGGREGATE_KEYS & parsed.keys()
    if supplied:
        raise ScreeningError(
            f"model must not supply aggregate field {sorted(supplied)[0]}"
        )
    checks = parsed.get("ada_checks")
    if not isinstance(checks, dict) or set(checks) != set(ADA_CHECK_KEYS):
        raise ScreeningError(
            "model response must contain exactly the eight photo checks"
        )
    supplied = ADA_MODEL_AGGREGATE_KEYS & checks.keys()
    if supplied:
        raise ScreeningError(
            f"model must not supply aggregate field {sorted(supplied)[0]}"
        )
    out = {}
    for key in ADA_CHECK_KEYS:
        entry = checks[key]
        if not isinstance(entry, dict):
            raise ScreeningError(f"check {key} must be an object")
        result = entry.get("result")
        if isinstance(result, bool) or not isinstance(result, str):
            raise ScreeningError(f"check {key} has invalid result {result!r}")
        result = result.strip().lower()
        if result not in ADA_RESULTS:
            raise ScreeningError(f"check {key} has invalid result {result!r}")
        evidence = entry.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ScreeningError(f"check {key} evidence must be non-empty text")
        evidence = evidence.strip()
        if "\n" in evidence or "\r" in evidence or len(evidence) > 200:
            raise ScreeningError(
                f"check {key} evidence must be one line of at most 200 characters"
            )
        out[key] = {"result": result, "evidence": evidence}
    return out


def _count_word(n: int) -> str:
    return _COUNT_WORDS[n]


def _join_check_names(keys: list[str]) -> str:
    if len(keys) == 1:
        return keys[0]
    if len(keys) == 2:
        return f"{keys[0]} and {keys[1]}"
    return ", ".join(keys[:-1]) + f", and {keys[-1]}"


def _ada_summary(true_count, false_count, undetermined_count, false_keys):
    parts = []
    determined = true_count + false_count
    if determined == 0:
        parts.append("No photo checks were determined.")
    else:
        parts.append(
            f"{_count_word(true_count).capitalize()} of {_count_word(determined)} "
            "determined photo checks were supported."
        )
    if false_keys:
        names = _join_check_names(false_keys)
        if len(false_keys) == 1:
            parts.append(f"A potential barrier was observed for {names}.")
        else:
            parts.append(f"Potential barriers were observed for {names}.")
    if undetermined_count == 1:
        parts.append(
            "One check could not be determined or was not applicable."
        )
    elif undetermined_count > 1:
        parts.append(
            f"{_count_word(undetermined_count).capitalize()} checks could not "
            "be determined or were not applicable."
        )
    return " ".join(parts)


def compute_ada_screening(checks: object) -> dict:
    """Server-side score, counts and summary from validated check states."""
    if not isinstance(checks, dict) or set(checks) != set(ADA_CHECK_KEYS):
        raise ScreeningError(
            "ada_checks must contain exactly the eight photo checks"
        )
    true_count = false_count = cannot_determine_count = not_applicable_count = 0
    false_keys = []
    normalized = {}
    for key in ADA_CHECK_KEYS:
        entry = checks[key]
        if not isinstance(entry, dict):
            raise ScreeningError(f"check {key} must be an object")
        result = entry.get("result")
        if isinstance(result, bool) or not isinstance(result, str):
            raise ScreeningError(f"check {key} has invalid result {result!r}")
        result = result.strip().lower()
        evidence = entry.get("evidence")
        if result not in ADA_RESULTS:
            raise ScreeningError(f"check {key} has invalid result {result!r}")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ScreeningError(f"check {key} evidence must be non-empty text")
        evidence = evidence.strip()
        if result == "true":
            true_count += 1
        elif result == "false":
            false_count += 1
            false_keys.append(key)
        elif result == "cannot_determine":
            cannot_determine_count += 1
        else:
            not_applicable_count += 1
        normalized[key] = {"result": result, "evidence": evidence}
    determined = true_count + false_count
    total = (
        true_count + false_count + cannot_determine_count + not_applicable_count
    )
    if total != 8:
        raise ScreeningError("ada_screening counts must sum to 8")
    score = None if determined == 0 else round(true_count / determined * 100, 1)
    return {
        "score_percent": score,
        "determined_count": determined,
        "total_count": 8,
        "true_count": true_count,
        "false_count": false_count,
        "cannot_determine_count": cannot_determine_count,
        "not_applicable_count": not_applicable_count,
        "checks": normalized,
        "summary": _ada_summary(
            true_count,
            false_count,
            cannot_determine_count + not_applicable_count,
            false_keys,
        ),
        "standards_url": ADA_STANDARDS_URL,
        "disclaimer": ADA_DISCLAIMER,
    }


def validate_face_check(parsed):
    """Normalize the privacy-audit answer to "clear", "face_visible" or "unknown".

    A missing or out-of-vocabulary answer becomes "unknown" with a logged
    warning, never a crash: the audit is an extra net over the blur pass, and
    a model that skips the key must not take the whole assessment down with
    it. (The blur pass has already run regardless.) It is also never "clear":
    "clear" asserts the model checked and saw no face, and a reply that never
    answered is a different fact a consumer must be able to see (PR #243
    review). Callers quarantine "unknown" as the fail-closed fallback.
    """
    value = str(parsed.get(FACE_CHECK_KEY, "")).strip().lower()
    if value in FACE_CHECK_ANSWERS:
        return value
    logger.warning(
        "face_check missing or invalid in model reply (%r); treating as unknown",
        value or None,
    )
    return FACE_CHECK_UNKNOWN


def aggregate_assessments(assessments):
    """Majority verdict per criterion across views, with the flip-rate shown.

    Only valid verdicts vote. Ties resolve to the most conservative verdict
    among the tied ones. flip_rate is the fraction of voting views that
    disagree with the majority verdict - reported, never hidden.
    """
    summary = {}
    for key in CRITERIA_KEYS:
        counts = Counter()
        for assessment in assessments:
            if assessment.criteria is None:
                continue
            verdict = assessment.criteria[key]["verdict"]
            if verdict in ALLOWED_VERDICTS:
                counts[verdict] += 1
        if not counts:
            summary[key] = CriterionSummary(verdict=None, flip_rate=None, counts={})
            continue
        top = max(counts.values())
        majority = next(
            v for v in _CONSERVATIVE_ORDER if counts.get(v, 0) == top
        )
        total = sum(counts.values())
        summary[key] = CriterionSummary(
            verdict=majority,
            flip_rate=(total - counts[majority]) / total,
            counts=dict(counts),
        )
    return summary


def integrated_summary(assessment):
    """Per-criterion summary for ONE integrated assessment.

    The verdicts are the integrated verdicts; flip_rate and counts are None
    because no cross-view comparison was made. A constant flip_rate of 0.0
    here would read as "all views agreed" -- a measurement that never
    happened -- and counts of {verdict: 1} would read as one view voting when
    several were submitted. None is the stronger signal: a consumer branching
    on the number notices, one reading 0.0 does not.
    """
    summary = {}
    for key in CRITERIA_KEYS:
        verdict = None
        if assessment.criteria is not None:
            candidate = assessment.criteria[key]["verdict"]
            if candidate in ALLOWED_VERDICTS:
                verdict = candidate
        summary[key] = CriterionSummary(verdict=verdict, flip_rate=None, counts=None)
    return summary


class ScreeningEngine:
    def __init__(self, client=None, config=None):
        self._client = client
        self.config = config if config is not None else ScreeningConfig()
        self.spent_usd = 0.0
        # The cap is a check followed by an increment, which is only a cap if no other
        # thread can land between the two. /screen assesses an entrance's views
        # concurrently, so without this N concurrent calls could all read the same
        # spent_usd, all pass, and all spend -- the cap would hold on paper and be
        # exceeded in fact. Also guards lazy client construction.
        self._lock = threading.Lock()

    def _get_client(self):
        with self._lock:
            if self._client is None:
                self._client = anthropic.Anthropic()
            return self._client

    def _check_spend_cap(self, cost=None):
        if cost is None:
            cost = self.config.usd_per_image
        projected = self.spent_usd + cost
        if projected > self.config.max_usd_per_run:
            raise SpendCapError(
                f"next call would spend an estimated ${projected:.2f}, over "
                f"the ${self.config.max_usd_per_run:.2f} cap for this run; "
                "aborting"
            )

    @staticmethod
    def _image_block(image, media_type):
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type,
                       "data": base64.standard_b64encode(image).decode("ascii")},
        }

    def _call_model(self, content, *, expect_face_check=False):
        """One model call over the given content blocks; refusals, truncation
        and parse failures are recorded errors, never silent.

        With expect_face_check the reply's face_check privacy answer is
        validated and carried on the result; without it the question was never
        asked, so the answer is "unknown" - never "clear", which would assert
        a check that did not happen - and no missing-key warning is logged."""
        t0 = time.perf_counter()
        try:
            response = self._get_client().messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=_prompt("system"),
                messages=[{"role": "user", "content": content}],
            )
            latency = time.perf_counter() - t0
            if response.stop_reason == "refusal":
                raise ScreeningError("model refused the request")
            if response.stop_reason == "max_tokens":
                raise ScreeningError(
                    "response truncated at max_tokens; raise "
                    "ScreeningConfig.max_tokens"
                )
            text = next((b.text for b in response.content if b.type == "text"), "")
            parsed = parse_json_response(text)
            criteria = validate_verdicts(parsed)
            ada_checks = validate_ada_checks(parsed)
            face_check = (validate_face_check(parsed) if expect_face_check
                          else FACE_CHECK_UNKNOWN)
        except Exception as exc:
            latency = time.perf_counter() - t0
            error = f"{type(exc).__name__}: {exc}"
            logger.warning("assessment failed: %s", error)
            return ImageAssessment(criteria=None, latency_s=round(latency, 3),
                                   error=error)
        return ImageAssessment(criteria=criteria, latency_s=round(latency, 3),
                               face_check=face_check, ada_checks=ada_checks)

    def assess_image(self, image, *, media_type="image/jpeg"):
        """One model call over one image; refusals and parse failures are
        recorded errors, never silent. Only the spend cap aborts the run."""
        # Checked and reserved together: the spend is booked before the call is made, so a
        # caller that would take the run over the cap is refused rather than discovering it
        # afterwards.
        with self._lock:
            self._check_spend_cap()
            self.spent_usd += self.config.usd_per_image
        return self._call_model([
            self._image_block(image, media_type),
            {"type": "text", "text": build_prompt()},
        ], expect_face_check=True)

    def assess_images_integrated(self, images, *, media_types=None):
        """ALL of an entrance's views in ONE model call, one integrated result.

        The cost booked is usd_per_image * len(images): an integrated call
        sends the same image tokens as the per-image calls it replaces, so the
        conservative per-image estimate is kept rather than assumed away.
        """
        if not images:
            raise ScreeningError("assess_images_integrated needs at least one image")
        if media_types is None:
            media_types = ["image/jpeg"] * len(images)
        if len(media_types) != len(images):
            raise ScreeningError(
                "media_types must contain exactly one value for every image"
            )
        cost = self.config.usd_per_image * len(images)
        with self._lock:
            self._check_spend_cap(cost)
            self.spent_usd += cost
        content = [
            self._image_block(image, media_type)
            for image, media_type in zip(images, media_types)
        ]
        content.append({"type": "text", "text": build_integrated_prompt(len(images))})
        return self._call_model(content, expect_face_check=True)

    def _resolve_split_or_refuse(self, entrance_id, *, allow_sealed=False):
        """Canonicalize, resolve and log the split; refuse sealed entrances.

        `allow_sealed` is for the one results-freeze run, whose caller has
        already recorded the unsealing in SEAL_AUDIT.log (D-017). This engine
        does not verify that record - the doorway that releases sealed labels
        and sealed bytes does - so nothing but that run should pass it.
        """
        entrance_id = canonical_entrance_id(entrance_id)
        split = assign_split(entrance_id)
        logger.info("split check: entrance %s -> %s", entrance_id, split)
        if split == "sealed" and not allow_sealed:
            raise SealedSplitError(
                f"entrance {entrance_id} is in the sealed split; the sealed "
                "split is evaluated exactly once at results freeze, not here"
            )
        logger.info(
            "spend cap for this run: $%.2f (estimated $%.4f per image, "
            "$%.4f spent so far)",
            self.config.max_usd_per_run, self.config.usd_per_image,
            self.spent_usd,
        )
        return entrance_id, split

    def screen_entrance(self, entrance_id, images, *, allow_sealed=False):
        """Screen one entrance from its captured views (image bytes), one
        model call per view. Kept for callers that need per-view verdicts.

        Resolves the split itself and refuses sealed entrances unless
        `allow_sealed` says the unsealing has already been recorded; the split
        check is logged for every entrance touched.
        """
        entrance_id, split = self._resolve_split_or_refuse(
            entrance_id, allow_sealed=allow_sealed
        )
        assessments = tuple(self.assess_image(image) for image in images)
        return EntranceScreening(
            entrance_id=entrance_id,
            split=split,
            assessments=assessments,
            summary=aggregate_assessments(assessments),
            mode="per_image",
        )

    def screen_entrance_integrated(self, entrance_id, images):
        """Screen one entrance by assessing ALL its views in ONE model call.

        Same split discipline and result shape as screen_entrance: one
        assessment carrying the integrated verdicts, and a summary carrying
        those verdicts with flip_rate and counts None -- no cross-view
        comparison was made, and the mode field says so.
        """
        entrance_id, split = self._resolve_split_or_refuse(entrance_id)
        assessments = (self.assess_images_integrated(images),)
        return EntranceScreening(
            entrance_id=entrance_id,
            split=split,
            assessments=assessments,
            summary=integrated_summary(assessments[0]),
            mode="integrated",
        )
