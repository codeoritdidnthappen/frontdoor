"""One photograph, one assessment: the verdict store keyed by image bytes (TICK-435, #435).

WHY THIS EXISTS
---------------
A verdict is supposed to be a function of the photograph. Until this module it
was not. The assessment call is sampled and there is no way to turn that off:
#394 established that this SDK's ``messages.create`` does not accept a
``temperature`` argument at all and that this model generation rejects sampling
parameters outright, so the same bytes could return "ramp present" on Monday
and "not visible" on Tuesday. The measured residual between two identical runs,
on entrances where nothing else went wrong, was 1.7 points of accuracy and about
8% of coverage (#395).

So the determinism is made here instead of asked for there. Hash the image,
look the hash up, and serve the answer that already exists. That is
deterministic by construction rather than by a setting, which is a stronger
guarantee than ``temperature: 0`` would have given even if it existed —
sampling at zero reduces variation, it does not eliminate it.

WHAT IS KEYED
-------------
``(image sha256, engine version)``. Both halves are load-bearing.

* **The processed bytes, never the upload.** ``faceblur.process_upload`` runs
  BEFORE the lookup, and the digest is taken over what it returned. The thing
  keyed must be the thing the model saw — and it means no unprocessed byte is
  ever hashed, stored, or reasoned about. (Nothing here stores image bytes at
  all: a record holds a digest and a verdict.)

* **The engine as well as the image.** A cache keyed on the image alone keeps
  serving an answer from a retired prompt or a retired model after either
  moves, and nobody finds out. The engine version is the model id plus the
  sha256 of ``screening_prompts.json`` itself, so editing a prompt invalidates
  every entry it produced without anybody remembering to bump a number. The old
  entries stay in the store as history; they simply stop matching.

An entrance's views are assessed in ONE integrated call, so the key covers the
ordered list of processed digests rather than a single image. Order is part of
the key because order is part of what the model was sent. A re-scan with a
NEW photograph is therefore a miss, and that is correct: it is new evidence
about the same door and it gets assessed. This module makes one photograph give
one answer; it does not make one door give one answer forever.

WHAT IS SERVED, AND HOW IT SAYS SO
----------------------------------
A recalled assessment carries the timestamp it was ORIGINALLY produced, and a
``served_from_store`` flag. Presenting a stored answer as a fresh one is the
same class of defect as scoring a rejected response as an abstention, which
#399 has just finished removing from this codebase; it is not reintroduced here
from the other side.

WHAT IS NOT STORED
------------------
Only a settled answer. An assessment whose reply was refused, truncated,
rejected, or which produced no verdict at all is a failure of the CALL, and
freezing one into the store would make a transient failure permanent — the same
mistake as reading a failure as an abstention, cached. ``is_storable`` is the
one predicate, and it also requires the privacy audit to have actually answered:
a one-off missing ``face_check`` key must not quarantine a photograph forever.

STORAGE
-------
JSONL on the volume beside the scan records (``FRONTDOOR_ASSESSMENTS``, default
``data/assessments.jsonl``), appended through ``frontdoor.scan_records.
append_scan`` and read through ``load_scan_store`` — the same functions, not a
copy of them, so the torn-line recovery and the "never invent the parent
directory" rule are the ones already proven on the scan store rather than a
second implementation that drifts from it. ``frontdoor.corrections`` reuses them
the same way.

The store is append-only and the FIRST record matching a key wins. Nothing here
writes a second record for a key it already found, but two concurrent misses
can both append, and first-wins means even then the answer never changes after
it is first given.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from importlib import resources

# The append discipline and the store reader are the scan store's, imported
# rather than re-implemented -- see the module docstring.
from frontdoor.scan_records import (
    append_scan as _append_jsonl,
    load_scan_store as _load_jsonl,
)
from frontdoor.screening import (
    FACE_CHECK_UNKNOWN,
    PROMPT_RESOURCE,
    ImageAssessment,
    any_verdict,
)

logger = logging.getLogger(__name__)

ASSESSMENTS_ENV = "FRONTDOOR_ASSESSMENTS"
DEFAULT_ASSESSMENTS_PATH = "data/assessments.jsonl"

#: Separator between the model id and the prompt digest in an engine version.
#: A literal that appears in neither half, so the version is unambiguous.
_VERSION_JOIN = "+prompts:"


def assessments_path():
    """Where the store lives: the env var, or the repo-relative default.

    The same env-plus-default shape as ``FRONTDOOR_SCANS`` and
    ``FRONTDOOR_CORRECTIONS``, and pointed at the mounted volume by the
    ``Dockerfile`` for the same reason: the container filesystem is replaced on
    every deploy, and a store that does not survive one would hand out a
    different verdict for the same photograph after every release — precisely
    the defect this module exists to end, arriving on a slower clock.
    """
    return os.environ.get(ASSESSMENTS_ENV, DEFAULT_ASSESSMENTS_PATH)


def _read_prompt_bytes():
    """The raw bytes of the packaged prompt file.

    Its own function so a test can substitute an edited prompt file and watch
    the key move. ``test_assessment_store`` separately pins that what this
    returns IS ``src/frontdoor/screening_prompts.json``, so the substitution
    proves something about the real file rather than about a seam.
    """
    return (
        resources.files("frontdoor")
        .joinpath(PROMPT_RESOURCE)
        .read_bytes()
    )


def prompt_digest():
    """sha256 of the reviewable prompt file, hex."""
    return hashlib.sha256(_read_prompt_bytes()).hexdigest()


def engine_version(model, *, prompt_sha=None):
    """The half of the key that is not the photograph.

    Model id plus the prompt file's own hash. Deliberately derived rather than
    declared: a version number somebody has to remember to bump is a version
    number that goes stale the first time a prompt is edited in a hurry.
    """
    if prompt_sha is None:
        prompt_sha = prompt_digest()
    return f"{model}{_VERSION_JOIN}{prompt_sha}"


def image_digest(image_bytes):
    """sha256 of ONE privacy-processed image, hex."""
    return hashlib.sha256(image_bytes).hexdigest()


def content_digest(images):
    """The key's image half: one digest over the ordered processed views.

    A digest of digests, so the per-image hashes stay legible in the record
    while the key stays one value. Order-sensitive on purpose: the model was
    sent these views in this order, and the key must be a function of what it
    saw.
    """
    digests = [image_digest(image) for image in images]
    joined = "\n".join(digests).encode("ascii")
    return hashlib.sha256(joined).hexdigest(), digests


def is_storable(assessment):
    """Is this a settled answer, or a call that failed?

    Only a settled answer is worth freezing. Anything else re-asks next time,
    which is the honest outcome: a refusal, a truncation, a transport error or
    a validation rejection is the engine failing to get an answer, and a stored
    failure is a transient fault made permanent. ``face_check`` "unknown" is
    excluded for the same reason from the privacy side — the audit never
    answered, and caching that would quarantine a photograph forever on the
    strength of one missing key.
    """
    return (
        isinstance(assessment, ImageAssessment)
        and assessment.failure is None
        and assessment.criteria is not None
        and any_verdict(assessment)
        and assessment.ada_checks is not None
        and assessment.face_check != FACE_CHECK_UNKNOWN
    )


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_assessment_record(*, image_sha256, image_digests, engine_version,
                          model, prompt_sha256, assessed_at, assessment):
    """One store line: the key, its provenance, and the assessment itself.

    No image bytes, and nothing about who submitted them. A digest and a
    verdict is the whole record.
    """
    return {
        "image_sha256": image_sha256,
        "image_digests": list(image_digests),
        "engine_version": engine_version,
        "model": model,
        "prompt_sha256": prompt_sha256,
        "assessed_at": assessed_at,
        "assessment": {
            "criteria": assessment.criteria,
            "latency_s": assessment.latency_s,
            "error": assessment.error,
            "face_check": assessment.face_check,
            "ada_checks": assessment.ada_checks,
            "failure": assessment.failure,
            "attempts": assessment.attempts,
            "rejected_attempts": assessment.rejected_attempts,
        },
    }


def assessment_from_record(record):
    """The stored assessment as an ImageAssessment, or None if unusable.

    Total, like the store readers it sits on: a line somebody hand-edited into
    nonsense is a miss (the photograph gets assessed), never an exception on a
    request path.
    """
    if not isinstance(record, dict):
        return None
    stored = record.get("assessment")
    if not isinstance(stored, dict):
        return None
    criteria = stored.get("criteria")
    ada_checks = stored.get("ada_checks")
    if not isinstance(criteria, dict) or not isinstance(ada_checks, dict):
        return None
    latency = stored.get("latency_s")
    if isinstance(latency, bool) or not isinstance(latency, (int, float)):
        latency = None
    face_check = stored.get("face_check")
    if not isinstance(face_check, str):
        face_check = FACE_CHECK_UNKNOWN
    attempts = stored.get("attempts")
    rejected = stored.get("rejected_attempts")
    assessment = ImageAssessment(
        criteria=criteria,
        latency_s=latency,
        error=stored.get("error") if isinstance(stored.get("error"), str) else None,
        face_check=face_check,
        ada_checks=ada_checks,
        failure=stored.get("failure") if isinstance(stored.get("failure"), str) else None,
        attempts=attempts if isinstance(attempts, int) and not isinstance(attempts, bool) else 1,
        rejected_attempts=(
            rejected if isinstance(rejected, int) and not isinstance(rejected, bool) else 0
        ),
    )
    # A record that would not have been storable cannot be served: whatever put
    # it there, serving it would hand out a frozen failure.
    return assessment if is_storable(assessment) else None


def load_assessment_store(path):
    """A ScanStoreLoad over the assessment file: records, error, skipped.

    The reader is the scan store's, so its message says "scans unreadable" —
    the one word an operator acts on, and it would send them to the wrong file.
    Corrected here rather than left to mislead, exactly as
    ``corrections.load_correction_store`` does.
    """
    load = _load_jsonl(path)
    if load.error:
        return replace(load, error=load.error.replace("scans", "assessments", 1))
    return load


def find_assessment(path, image_sha256, version):
    """``(record, assessment)`` for the first USABLE match, or ``(None, None)``.

    First, not last: the store is append-only and nothing here rewrites a key
    it found, but two concurrent misses can both append. First-wins means the
    answer never changes after it has once been given, which is the property
    the whole module is for.

    Usable, not merely matching. A record whose assessment cannot be read back
    -- hand-edited, or written by some future shape -- is skipped rather than
    returned. Returning it and letting the caller fall through to a fresh
    assessment would mean the unusable record is found FIRST every time: every
    request would re-assess and append another line behind a record that is
    never served. Skipping means the good line written after it wins.

    A linear scan of the file per request, deliberately. The alternative is an
    index that has to be kept in step with an append-only log, and the cost it
    would save is a few milliseconds against a model call measured in seconds
    -- on a store that grows by one line per NEW photograph. If it ever stops
    being cheap, the fix is an index built from this same file, not a second
    format.
    """
    for record in load_assessment_store(path).records:
        if (record.get("image_sha256") != image_sha256
                or record.get("engine_version") != version):
            continue
        assessment = assessment_from_record(record)
        if assessment is not None:
            return record, assessment
        logger.warning(
            "skipping an unreadable assessment record for %s in %s",
            str(image_sha256)[:12], path,
        )
    return None, None


@dataclass(frozen=True)
class Recall:
    """One assessment plus where it came from.

    ``served_from_store`` and ``assessed_at`` travel together on purpose: a
    consumer must be able to tell a stored answer from a fresh one, and the
    timestamp is what makes the record show an answer from earlier rather than
    implying a new one.
    """

    assessment: object
    image_sha256: str
    engine_version: str
    assessed_at: str
    served_from_store: bool

    def reference(self):
        """The three DURABLE fields: which photograph, which engine, when.

        Properties of the assessment, so they are what a persisted record
        keeps. ``served_from_store`` is deliberately not among them: it is a
        fact about one request, and a stored record asserting it would be
        answering a question nobody asked it.
        """
        return {
            "image_sha256": self.image_sha256,
            "engine_version": self.engine_version,
            "assessed_at": self.assessed_at,
        }

    def provenance(self):
        """What an endpoint puts in its response body: the reference, plus
        whether THIS request was answered from the store."""
        return {**self.reference(), "served_from_store": self.served_from_store}


def recall_or_assess(engine, images, *, media_types=None, path=None, now=None):
    """The one entry point ``/screen`` and ``/screen/publish`` both call.

    Hit: return the stored assessment with the timestamp it was originally
    produced, and make NO model call. Miss: assess, store a settled answer, and
    return it stamped now.

    Fails OPEN on the store, never on the request. An unreadable store is a
    miss (the photograph is assessed); an append that fails is logged and the
    assessment is still returned. Determinism degrades to what it was before
    this module existed; a request never fails because a cache did.
    """
    if path is None:
        path = assessments_path()
    if now is None:
        now = _now
    image_sha256, digests = content_digest(images)
    prompt_sha = prompt_digest()
    version = engine_version(engine.config.model, prompt_sha=prompt_sha)

    record, stored = find_assessment(path, image_sha256, version)
    if stored is not None:
        assessed_at = record.get("assessed_at")
        logger.info(
            "serving a stored assessment for %s (assessed %s)",
            image_sha256[:12], assessed_at,
        )
        return Recall(
            assessment=stored,
            image_sha256=image_sha256,
            engine_version=version,
            assessed_at=assessed_at if isinstance(assessed_at, str) else None,
            served_from_store=True,
        )

    assessment = engine.assess_images_integrated(images, media_types=media_types)
    assessed_at = now()
    if is_storable(assessment):
        record = new_assessment_record(
            image_sha256=image_sha256,
            image_digests=digests,
            engine_version=version,
            model=engine.config.model,
            prompt_sha256=prompt_sha,
            assessed_at=assessed_at,
            assessment=assessment,
        )
        try:
            _append_jsonl(path, record)
        except (OSError, ValueError) as exc:
            # The assessment is good; only its durability is lost. Failing the
            # request here would turn a missing volume into an outage of the
            # thing the volume is only an optimisation for.
            logger.warning(
                "the assessment for %s could not be stored (%s); the same "
                "photograph may be assessed again",
                image_sha256[:12], exc,
            )
    return Recall(
        assessment=assessment,
        image_sha256=image_sha256,
        engine_version=version,
        assessed_at=assessed_at,
        served_from_store=False,
    )
