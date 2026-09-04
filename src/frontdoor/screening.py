"""Vision screening engine: LLM checklist over entrance photos (TICK-245, #167).

Two modes. Per-image: one model call per photo assesses which accessibility
features are VISIBLE - ramp or beveled threshold, handrails, accessible door
hardware, accessibility signage - and per entrance the 5-6 views are
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

import anthropic

from frontdoor.split import assign_split, canonical_entrance_id

logger = logging.getLogger(__name__)

# Criterion descriptions carry the decision rules that error adjudication on
# the pilot set showed the model needs spelled out: where ramps actually sit,
# what a same-tone platform hides from a frontal camera, and which hardware
# look-alikes are NOT accessible hardware.
CRITERIA = (
    ("ramp_or_bevel",
     "A ramp (permanent or portable) or a beveled threshold serving the "
     "entrance is visible. Ramps often sit off-axis at the side of the "
     "entrance, may be surfaced in brick or stone like the surroundings, and "
     "their railings can resemble fencing. Check the platform edges in every "
     "view: a raised platform in the same tone as the sidewalk hides its step "
     "when photographed from on top of it, so only commit to a verdict when a "
     "view actually shows the ground plane at the entrance"),
    ("handrails",
     "Handrails on any steps or ramp serving the entrance"),
    ("accessible_door_hardware",
     "Door hardware operable with a closed fist: a lever handle, a push bar, "
     "or a loop/D pull that stands off the door surface. Flat push plates, "
     "round knobs, and latch brackets are NOT accessible hardware"),
    ("accessibility_signage",
     "International Symbol of Accessibility or directional accessibility "
     "signage visible"),
)

CRITERIA_KEYS = tuple(key for key, _ in CRITERIA)

ALLOWED_VERDICTS = ("present", "absent", "not_visible")

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
#: (PR #243 review). "unknown" never quarantines - only face_visible does.
FACE_CHECK_UNKNOWN = "unknown"
FACE_CHECK_VALUES = FACE_CHECK_ANSWERS + (FACE_CHECK_UNKNOWN,)
FACE_CHECK_QUESTION = (
    "After the automatic blurring already applied to this image, is any "
    "identifiable human face still visible anywhere - including reflections "
    "in glass and people seen through windows? Answer face_visible if any "
    "face could be recognized, clear otherwise."
)

# Tie-break order for the majority verdict: most conservative first. A tie
# never invents certainty, and not_visible stays distinct from absent.
_CONSERVATIVE_ORDER = ("not_visible", "absent", "present")

SYSTEM_PROMPT = """\
You are the vision screening engine for frontdoor. You assess ONLY what is
visible in a photo of a building entrance. You never guess measurements:
slopes, widths, and heights are not assessable from a photo, and you never
state compliance or legal conclusions of any kind. Your job is presence or
absence of visible features. Be conservative: if a feature is not clearly
visible in frame, answer not_visible rather than absent - not_visible and
absent are different claims and must never be merged.
Respond with ONLY a JSON object - no prose, no markdown fences."""


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
    # 20.6s per entrance and roughly 2.5x cheaper. max_tokens must be >= 4000:
    # at 2000, adaptive thinking consumes the budget on hard entrances and
    # sonnet's JSON output truncates mid-object.
    model: str = "claude-sonnet-5"
    max_tokens: int = 4000
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


def build_prompt():
    lines = [
        "Assess this entrance photo against the criteria below.",
        "For each criterion return: verdict ('present', 'absent', or "
        "'not_visible'), confidence (0-100), evidence (one short phrase "
        "describing what you see in THIS image).",
        "Criteria:",
    ]
    for key, desc in CRITERIA:
        lines.append(f"- {key}: {desc}")
    lines.append(
        "Additionally answer one privacy check, which is not an "
        "accessibility criterion:"
    )
    lines.append(f"- {FACE_CHECK_KEY}: {FACE_CHECK_QUESTION}")
    lines.append(
        'Return exactly this JSON shape: {"criteria": {"<key>": '
        '{"verdict": "...", "confidence": 0, "evidence": "..."}}, '
        '"face_check": "clear" or "face_visible"}'
    )
    return "\n".join(lines)


def build_integrated_prompt(view_count):
    """The multi-view prompt: one integrated verdict per criterion.

    The instruction to trust the view that shows the relevant area is the
    point of the mode - it is how a single oblique frame showing a riser or a
    side ramp beats the frontal frames that cannot see it.
    """
    lines = [
        f"The {view_count} photos above are different views of the SAME "
        "entrance. Integrate ALL views into ONE checklist result for the "
        "entrance.",
        "A feature clearly visible in ANY view is visible. When views appear "
        "to disagree, trust the view that actually shows the relevant area - "
        "for example, only a view that shows the ground plane can settle "
        "whether a platform is raised, and an object that merely overlaps the "
        "doorway from an oblique angle is not blocking the path.",
        "For each criterion return: verdict ('present', 'absent', or "
        "'not_visible'), confidence (0-100), evidence (one short phrase "
        "describing what you see and, when it matters, which view shows it).",
        "Criteria:",
    ]
    for key, desc in CRITERIA:
        lines.append(f"- {key}: {desc}")
    lines.append(
        "Additionally answer one privacy check, which is not an "
        "accessibility criterion and covers ALL the views together:"
    )
    lines.append(
        f"- {FACE_CHECK_KEY}: {FACE_CHECK_QUESTION} Answer face_visible if "
        "ANY view still shows one."
    )
    lines.append(
        'Return exactly this JSON shape: {"criteria": {"<key>": '
        '{"verdict": "...", "confidence": 0, "evidence": "..."}}, '
        '"face_check": "clear" or "face_visible"}'
    )
    return "\n".join(lines)


def parse_json_response(text):
    """Parse model output that should be bare JSON; tolerate stray fences."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ScreeningError(f"no JSON object in response: {text[:200]!r}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ScreeningError(f"response is not valid JSON: {exc}") from exc


def validate_verdicts(parsed):
    """Normalize the criteria block; flag out-of-vocabulary verdicts loudly."""
    out = {}
    crit = parsed.get("criteria", {})
    for key in CRITERIA_KEYS:
        entry = crit.get(key, {})
        if not isinstance(entry, dict):
            entry = {}
        verdict = str(entry.get("verdict", "")).strip().lower()
        if verdict not in ALLOWED_VERDICTS:
            verdict = f"INVALID:{verdict or 'missing'}"
        out[key] = {
            "verdict": verdict,
            "confidence": entry.get("confidence", ""),
            "evidence": str(entry.get("evidence", ""))[:200],
        }
    return out


def validate_face_check(parsed):
    """Normalize the privacy-audit answer to "clear", "face_visible" or "unknown".

    A missing or out-of-vocabulary answer becomes "unknown" with a logged
    warning, never a crash: the audit is an extra net over the blur pass, and
    a model that skips the key must not take the whole assessment down with
    it. (The blur pass has already run regardless.) It is also never "clear":
    "clear" asserts the model checked and saw no face, and a reply that never
    answered is a different fact a consumer must be able to see (PR #243
    review). "unknown" does not quarantine - only face_visible does.
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
                system=SYSTEM_PROMPT,
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
            face_check = (validate_face_check(parsed) if expect_face_check
                          else FACE_CHECK_UNKNOWN)
        except Exception as exc:
            latency = time.perf_counter() - t0
            error = f"{type(exc).__name__}: {exc}"
            logger.warning("assessment failed: %s", error)
            return ImageAssessment(criteria=None, latency_s=round(latency, 3),
                                   error=error)
        return ImageAssessment(criteria=criteria, latency_s=round(latency, 3),
                               face_check=face_check)

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

    def _resolve_split_or_refuse(self, entrance_id):
        """Canonicalize, resolve and log the split; refuse sealed entrances."""
        entrance_id = canonical_entrance_id(entrance_id)
        split = assign_split(entrance_id)
        logger.info("split check: entrance %s -> %s", entrance_id, split)
        if split == "sealed":
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

    def screen_entrance(self, entrance_id, images):
        """Screen one entrance from its captured views (image bytes), one
        model call per view. Kept for callers that need per-view verdicts.

        Resolves the split itself and refuses sealed entrances; the split
        check is logged for every entrance touched.
        """
        entrance_id, split = self._resolve_split_or_refuse(entrance_id)
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
