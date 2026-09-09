"""Locate the evidence a verdict is about, so a person can check it (TICK-467).

The product's central claim is a verdict about a doorway. This module answers
the next question a sceptic asks -- *where* -- by finding, for each criterion,
one rectangle on one stored photograph that a person can look at. Tapping
"handrails" should show the handrail.

What this is, and what it deliberately is not
---------------------------------------------
This is a POINTER. It never sees a verdict, it is never asked for one, and
nothing it returns can become one. The function that does the work takes image
bytes and returns geometry; there is no parameter through which a verdict
could reach it and no return value a verdict could be read out of. That is not
politeness, it is the whole reason this module is allowed to exist.

The same detector was measured as a SCORER and dropped. Cropping to detected
door and handle regions and re-asking the model went 82.7% -> 92.3% on the
tuning half and 94.2% -> 86.5% on held-out photographs: zero fixes, four new
errors, three of them a real handle called absent because NO HANDLE BOX WAS
FOUND and the model read a missing box as evidence of absence rather than
abstaining. A coverage gate cut four errors to one and the arm was still net
negative. That evaluation's own recorded conclusion was to keep box receipts
as a diagnostic and not as a scoring path, and this module is that diagnostic.

So the rule this module is built around, stated once and enforced by
tests/test_evidence_boxes_do_not_judge.py rather than by this paragraph:

    A MISSING BOX IS NOT AN ABSENT FEATURE.

A criterion simply does not appear in the returned mapping when nothing was
found. It never appears with a null, a false, or a zero-confidence box,
because every one of those is a shape a caller could later mistake for a
finding. The interface says "we looked for this and couldn't point at it" and
prints the verdict it already had, unchanged.

It can say that truthfully because the fact that a search HAPPENED is recorded
once per entrance, by the caller -- scan_publish writes evidence_boxes_searched
onto the record -- and never per criterion. Every criterion is looked for on
every entrance, so one boolean carries the whole difference between "we looked
and could not point at one" and "nobody looked", and this module never has to
own a value meaning "searched and empty". That value is the shape that got this
detector dropped as a scorer, and it is not worth re-inventing to say a
sentence a flag already says.

When it runs, and why never during a scan
-----------------------------------------
At publish time only. The detector is a vision transformer run on CPU, and
measured on this repository's machine it takes about twelve seconds a frame:
24.1 s mean over twelve two-frame entrances, so roughly a minute for a
five-view door. Fine once, when nobody is waiting, and unacceptable inside a
capture flow that is already at about nineteen seconds from shutter to
verdict. Nothing in the live scan path imports this module, and
tests/test_evidence_boxes_off_the_scan_path.py fails if that ever changes.

It costs no API call at all: $0.00 per entrance. The detector is local and
open-weights, so the per-entrance cost is CPU time and nothing else -- the
$0.0075 figure recorded against the dropped scoring arm was its Claude re-ask,
which this module does not make.

Coordinate space -- deliberate, read before "fixing"
----------------------------------------------------
Boxes are in the pixel frame of the STORED image bytes: the same frame
frontdoor.faceblur reports blur_regions in, which is the privacy-processed,
orientation-applied, DECODE_MAX_SIDE-capped picture the receipt actually
displays. Detection runs on a downscaled copy for speed and every box is
scaled back before it is returned, so no caller ever has to translate between
spaces and no geometry outlives the frame it was measured in. Hand this
function an ORIGINAL camera file rather than the stored bytes and the boxes
will be drawn in the wrong place, which is worse than drawing none.

Optional dependency
-------------------
The detector needs torch and transformers, which the server does not install
and does not need. They are declared as the "boxes" extra. Without them
``locate_evidence`` raises DetectorUnavailable and the publish path records no
boxes, which is a supported outcome: the box is a courtesy, so an entrance
published without one is complete, not broken.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

log = logging.getLogger(__name__)


class DetectorUnavailable(RuntimeError):
    """The open-vocabulary detector could not be loaded on this machine."""


#: Open-vocabulary detector, the same checkpoint the grounded-crops evaluation
#: measured, so its recorded coverage describes THIS code and not a cousin of
#: it. That coverage -- door box on 26 of 26 pilot entrances, handle box on 20
#: of 26 -- came from the queries "door" and "door handle", and only the second
#: maps onto a criterion here. The evaluation also asked for a ramp, a handrail
#: and a wheelchair symbol sign, but never scored their coverage against ground
#: truth, so there is no published figure for the other three criteria and this
#: comment does not invent one. See docs/evidence-boxes.md.
DETECTOR_MODEL = "google/owlvit-base-patch32"

#: What to ask the detector for, per screening criterion. The keys are exactly
#: frontdoor.screening.CRITERIA_KEYS and
#: tests/test_evidence_boxes_do_not_judge.py fails if they ever drift apart --
#: a criterion with no entry here would silently never get a box, which reads
#: on screen as "we looked and could not point at this one" and would be a lie:
#: nobody looked.
#:
#: Several phrasings per criterion because the detector is a text-conditioned
#: model and "handrail" and "hand rail" are not the same query to it. The best
#: scoring box across all phrasings wins; the phrasing itself is recorded on
#: the box so a wrong box can be traced to the words that produced it.
CRITERION_QUERIES = {
    "ramp_or_bevel": ("ramp", "wheelchair ramp", "sloped threshold"),
    "handrails": ("handrail", "hand rail", "metal railing"),
    "accessible_door_hardware": ("door handle", "door lever handle", "door pull"),
    "accessibility_signage": (
        "wheelchair symbol sign",
        "accessibility sign",
        "wheelchair accessible entrance sign",
    ),
}

#: Score below which a box is not shown. The evaluation ran its own detection
#: pass at 0.08, which was the right floor for a scorer that could weigh a weak
#: box against other evidence. A pointer cannot: it is drawn on a photograph
#: with no hedge beside it, and a confident rectangle around the wrong object
#: costs more trust than an honest "we could not point at this one". So the
#: display gate sits above the evaluation's, and what it costs in coverage is
#: recorded rather than assumed: run over the twelve receipt photographs the
#: app carries, four entrances got a box and eight say we looked and could not
#: point at one. Those are 360x480 thumbnails, well under the 2048 a real
#: publish works from, so that is a floor. See docs/evidence-boxes.md.
MIN_SCORE = 0.10

#: Raw threshold handed to the detector. Below MIN_SCORE on purpose: the model
#: is asked wide and the gate is applied here, in code that can be read, rather
#: than buried in a pipeline argument.
DETECT_THRESHOLD = 0.05

#: Longest side the detector reads. OWL-ViT resizes to 768 internally, so
#: feeding it a 2048px frame buys nothing and costs preprocessing time; the
#: geometry is scaled back to the stored frame either way.
DETECT_MAX_SIDE = 1024

#: A box smaller than this SHARE of the frame's long side, on either side, is
#: dropped: a rectangle a handful of pixels across is a speck that points at
#: nothing, and drawing it would claim a precision the detector does not have.
#:
#: A share and not a pixel count, because the stored frames this reads are not
#: all one size. TICK-453 caps the long side at 2048, but the app also carries
#: much smaller receipt photographs, and "12 pixels" means two entirely
#: different things on a 2048px frame and a 480px one -- on the smaller frame
#: it silently throws away boxes that display LARGER than the ones it keeps on
#: the bigger. 0.6% is the 2048px frame's old 12px threshold expressed in the
#: unit that survives a resize; MIN_BOX_FLOOR keeps it sane on a tiny frame.
MIN_BOX_FRACTION = 0.006
MIN_BOX_FLOOR = 8


def _decode_frame(image_bytes):
    """Decode STORED bytes to a BGR array, with no cap and no rotation.

    Deliberately not frontdoor.faceblur._decode: these bytes have ALREADY been
    through it. They carry no EXIF, so there is no orientation to apply, and
    they are already at or under the decode cap, so there is nothing to cap.
    Re-running either step would be a second transform on an already
    transformed picture and would put the boxes in a frame nothing else uses.
    """
    img = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("could not decode stored image bytes")
    return img


def load_detector(model=DETECTOR_MODEL):
    """Return a zero-shot object detection callable, or raise.

    Imported here rather than at module scope so that importing this module --
    which the publish path does unconditionally, and which the tests do -- does
    not require torch. Raises DetectorUnavailable for a missing dependency and
    for a checkpoint that cannot be fetched, because the caller's response to
    both is the same: publish this entrance with no boxes.
    """
    try:
        from transformers import pipeline
    except ImportError as exc:  # pragma: no cover - exercised by absence
        raise DetectorUnavailable(
            "torch and transformers are needed to locate evidence; "
            'install the "boxes" extra'
        ) from exc
    try:
        return pipeline("zero-shot-object-detection", model=model)
    except Exception as exc:  # pragma: no cover - network/checkpoint failure
        raise DetectorUnavailable(f"could not load {model}: {exc}") from exc


def _detect_frame(detector, img):
    """Every candidate box in one stored frame, in that frame's pixels.

    The detector reads a downscaled copy and its boxes are multiplied back up,
    then clamped to the frame. Clamping is not cosmetic: the model can and does
    return boxes that overhang the picture, and a rectangle drawn partly
    outside the photograph looks like a bug in the receipt.
    """
    from PIL import Image

    height, width = img.shape[:2]
    longest = max(height, width)
    scale = min(1.0, DETECT_MAX_SIDE / longest) if longest else 1.0
    small = img
    if scale < 1.0:
        small = cv2.resize(
            img, (max(1, round(width * scale)), max(1, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    pil = Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
    back_x = width / pil.width
    back_y = height / pil.height

    queries = [q for phrasings in CRITERION_QUERIES.values() for q in phrasings]
    raw = detector(pil, candidate_labels=queries, threshold=DETECT_THRESHOLD)

    min_side = max(MIN_BOX_FLOOR, round(longest * MIN_BOX_FRACTION))
    found = []
    for result in raw:
        box = result["box"]
        x0 = max(0, min(width, round(box["xmin"] * back_x)))
        y0 = max(0, min(height, round(box["ymin"] * back_y)))
        x1 = max(0, min(width, round(box["xmax"] * back_x)))
        y1 = max(0, min(height, round(box["ymax"] * back_y)))
        if x1 - x0 < min_side or y1 - y0 < min_side:
            continue
        found.append({
            "label": result["label"],
            "score": round(float(result["score"]), 3),
            "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0,
        })
    return found


def locate_evidence(frames, *, detector=None):
    """Where each criterion's evidence is, across one entrance's stored frames.

    ``frames`` is the stored image bytes for one entrance in upload order --
    the SAME bytes the receipt will display, straight out of
    ``faceblur.process_upload``, never an original camera file. See the
    module's coordinate-space note.

    Returns ``{criterion: {"frame": i, "x", "y", "w", "h", "label", "score"}}``
    with x/y/w/h in that frame's pixels, exactly as ``blur_regions`` reports.
    A criterion with nothing above MIN_SCORE is ABSENT FROM THE MAPPING. There
    is no null entry, no empty box and no zero score, because a caller reading
    a null could talk itself into treating it as a finding, and that is the
    confusion that got this detector dropped as a scorer.

    Every criterion is looked for on every entrance regardless of what the
    engine said, so what the detector saw cannot be a function of what the
    engine answered, in either direction. This function is not given the
    verdicts and could not use them if it were.

    Raises DetectorUnavailable when the optional detector is not installed.
    """
    frames = list(frames)
    if not frames:
        return {}
    if detector is None:
        detector = load_detector()

    best_for_query = {}
    for index, image_bytes in enumerate(frames):
        try:
            img = _decode_frame(image_bytes)
        except ValueError:
            log.warning("evidence boxes: frame %d did not decode; skipped", index)
            continue
        for box in _detect_frame(detector, img):
            candidate = dict(box, frame=index)
            current = best_for_query.get(box["label"])
            if current is None or candidate["score"] > current["score"]:
                best_for_query[box["label"]] = candidate

    located = {}
    for criterion, phrasings in CRITERION_QUERIES.items():
        candidates = [
            best_for_query[q] for q in phrasings
            if q in best_for_query and best_for_query[q]["score"] >= MIN_SCORE
        ]
        if candidates:
            located[criterion] = max(candidates, key=lambda b: b["score"])
    return located
