"""Vision screening engine: LLM checklist over entrance photos (TICK-245, #167).

Per image, one model call assesses which accessibility features are VISIBLE:
ramp or beveled threshold, handrails, accessible door hardware, accessibility
signage. Per entrance, verdicts from the 5-6 views are aggregated into a
majority verdict per criterion with the flip-rate reported alongside.

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

CRITERIA = (
    ("ramp_or_bevel",
     "A ramp (permanent or portable) or a beveled threshold serving the "
     "entrance is visible"),
    ("handrails",
     "Handrails on any visible steps or ramp"),
    ("accessible_door_hardware",
     "Door hardware is lever-style, push-bar, or loop pull (not a round knob)"),
    ("accessibility_signage",
     "International Symbol of Accessibility or directional accessibility "
     "signage visible"),
)

CRITERIA_KEYS = tuple(key for key, _ in CRITERIA)

ALLOWED_VERDICTS = ("present", "absent", "not_visible")

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
    model: str = "claude-opus-5"
    max_tokens: int = 2000
    max_usd_per_run: float = 1.00
    usd_per_image: float = 0.05  # conservative per-image estimate (cents-order)


@dataclass(frozen=True)
class ImageAssessment:
    """One image's checklist result, or a recorded error - never silence."""

    criteria: dict | None
    latency_s: float | None
    error: str | None = None


@dataclass(frozen=True)
class CriterionSummary:
    verdict: str | None  # None when no view produced a valid verdict
    flip_rate: float | None  # fraction of valid views disagreeing with verdict
    counts: dict  # valid verdict -> number of views


@dataclass(frozen=True)
class EntranceScreening:
    entrance_id: str
    split: str
    assessments: tuple
    summary: dict  # criterion key -> CriterionSummary


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
        'Return exactly this JSON shape: {"criteria": {"<key>": '
        '{"verdict": "...", "confidence": 0, "evidence": "..."}}}'
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

    def _check_spend_cap(self):
        projected = self.spent_usd + self.config.usd_per_image
        if projected > self.config.max_usd_per_run:
            raise SpendCapError(
                f"next call would spend an estimated ${projected:.2f}, over "
                f"the ${self.config.max_usd_per_run:.2f} cap for this run; "
                "aborting"
            )

    def assess_image(self, image, *, media_type="image/jpeg"):
        """One model call over one image; refusals and parse failures are
        recorded errors, never silent. Only the spend cap aborts the run."""
        # Checked and reserved together: the spend is booked before the call is made, so a
        # caller that would take the run over the cap is refused rather than discovering it
        # afterwards.
        with self._lock:
            self._check_spend_cap()
            self.spent_usd += self.config.usd_per_image
        t0 = time.perf_counter()
        try:
            response = self._get_client().messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image",
                         "source": {"type": "base64", "media_type": media_type,
                                    "data": base64.standard_b64encode(image).decode("ascii")}},
                        {"type": "text", "text": build_prompt()},
                    ],
                }],
            )
            latency = time.perf_counter() - t0
            if response.stop_reason == "refusal":
                raise ScreeningError("model refused the request")
            text = next((b.text for b in response.content if b.type == "text"), "")
            criteria = validate_verdicts(parse_json_response(text))
        except Exception as exc:
            latency = time.perf_counter() - t0
            error = f"{type(exc).__name__}: {exc}"
            logger.warning("image assessment failed: %s", error)
            return ImageAssessment(criteria=None, latency_s=round(latency, 3),
                                   error=error)
        return ImageAssessment(criteria=criteria, latency_s=round(latency, 3))

    def screen_entrance(self, entrance_id, images):
        """Screen one entrance from its captured views (image bytes).

        Resolves the split itself and refuses sealed entrances; the split
        check is logged for every entrance touched.
        """
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
        assessments = tuple(self.assess_image(image) for image in images)
        return EntranceScreening(
            entrance_id=entrance_id,
            split=split,
            assessments=assessments,
            summary=aggregate_assessments(assessments),
        )
