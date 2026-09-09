"""A box may point. It may never judge (TICK-467).

This is the test the ticket exists to make possible, and it is written so that
it FAILS if someone later wires box presence into an assessment. The reason it
is a test and not a comment is that the same detector has already been measured
doing exactly the forbidden thing: cropping to detected door and handle regions
and re-asking took held-out accuracy from 94.2% to 86.5%, and three of the four
new errors were a real handle called absent because NO HANDLE BOX WAS FOUND.
The model read a missing box as evidence of absence. In an interface that would
be worse, not better -- a user shown a bare photograph reads it as a denial.

So four separate things are pinned:

1. Verdicts are byte-identical whether the detector finds everything, finds
   nothing, or is not installed at all.
2. The engine is handed byte-identical images in all three cases -- nothing
   about the boxes reaches the model call.
3. A criterion with no box is ABSENT from the mapping. Not null, not false, not
   an empty box, not a zero score. There is no shape for "we looked and there
   is nothing there", because that shape is the bug.
4. The detector is never given a verdict. Its call signature cannot carry one,
   and the record it produces is added to an assessment that was already final.
"""

import ast
import inspect
from types import SimpleNamespace

import pytest

from frontdoor import evidence_boxes, scan_records
from frontdoor.evidence_boxes import (
    CRITERION_QUERIES,
    DetectorUnavailable,
    locate_evidence,
)
from frontdoor.scan_publish import assess_publishable, build_records
from frontdoor.screening import CRITERIA_KEYS

from test_scan_publish import FakeCapture, RecordingEngine


VERDICT_WORDS = ("present", "absent", "not_visible", "not_assessed")


@pytest.fixture
def no_privacy_rescale(monkeypatch):
    """Take the image pipeline out of the way; this is about influence."""
    monkeypatch.setattr(
        "frontdoor.scan_publish.process_upload",
        lambda image_bytes: SimpleNamespace(
            image_bytes=b"stored:" + image_bytes, face_count=0),
    )
    monkeypatch.setattr("frontdoor.scan_publish._fit_for_the_model",
                        lambda b: b"fit:" + b)


def _run(monkeypatch, detector, entrances={"E-001": ["c1", "c2"]}):
    engine = RecordingEngine()
    results = assess_publishable(
        entrances, get_capture=FakeCapture, engine=engine, detector=detector,
    )
    return results, engine


class FindsEverything:
    """A detector that reports a confident box for every criterion."""

    def __call__(self, image, candidate_labels, threshold):
        return [
            {"label": label, "score": 0.99,
             "box": {"xmin": 10, "ymin": 20, "xmax": 60, "ymax": 90}}
            for label in candidate_labels
        ]


class FindsNothing:
    def __call__(self, image, candidate_labels, threshold):
        return []


def _boxes_for_everything():
    """What locate_evidence returns when the detector is sure of everything."""
    return {
        key: {"frame": 0, "x": 10, "y": 20, "w": 50, "h": 70,
              "label": phrasings[0], "score": 0.99}
        for key, phrasings in CRITERION_QUERIES.items()
    }


# --- 1. the verdicts do not move ---------------------------------------------


#: The assessment fields a box may not move. Named once because the mutation
#: check below has to run the SAME comparison the real test runs -- a mutation
#: check against a weaker copy of the assertion proves nothing.
SETTLED_FIELDS = ("verdicts", "confidences", "verdict_failures", "face_check",
                  "error", "failure", "attempts", "rejected_attempts",
                  "faces_blurred", "view_count", "mode")


def _the_verdicts_do_not_move(monkeypatch, assess=assess_publishable):
    """Run one entrance three ways and assert the assessment is the same.

    Factored out of the test below so the mutation check can put a deliberately
    box-influenced publish path through this exact comparison.
    """
    monkeypatch.setattr(evidence_boxes, "_detect_frame",
                        lambda detector, img: detector.frames)
    monkeypatch.setattr(evidence_boxes, "_decode_frame", lambda b: b)

    everything = SimpleNamespace(frames=[
        {"label": phrasings[0], "score": 0.99, "x": 1, "y": 2, "w": 30, "h": 40}
        for phrasings in CRITERION_QUERIES.values()
    ])
    nothing = SimpleNamespace(frames=[])

    def run(detector):
        return assess({"E-001": ["c1", "c2"]}, get_capture=FakeCapture,
                      engine=RecordingEngine(), detector=detector)

    with_boxes, without_boxes, no_detector = (
        run(everything), run(nothing), run(None))

    for field in SETTLED_FIELDS:
        assert (with_boxes["E-001"][field]
                == without_boxes["E-001"][field]
                == no_detector["E-001"][field]), field

    # And the boxes really did differ, so the comparison above meant something.
    assert set(with_boxes["E-001"]["evidence_boxes"]) == set(CRITERIA_KEYS)
    assert without_boxes["E-001"]["evidence_boxes"] == {}
    assert no_detector["E-001"]["evidence_boxes"] == {}


def test_verdicts_are_identical_whether_or_not_a_box_was_found(
        monkeypatch, no_privacy_rescale):
    _the_verdicts_do_not_move(monkeypatch)


def test_that_check_fails_when_a_missing_box_is_wired_into_a_verdict(
        monkeypatch, no_privacy_rescale):
    """The mutation check. Without it the test above proves only that nobody
    has broken the rule YET, not that the test would notice.

    The mutation is the exact failure the grounded-crops arm measured: a
    criterion with no box gets called `absent`. It went 94.2% -> 86.5% on
    held-out photographs, three of the four new errors being a real handle
    called absent because no handle box was found. If a future change wires box
    presence into an assessment in any equivalent way, the test above turns
    red; this proves that claim rather than asserting it.
    """
    def assess_that_reads_the_boxes(entrances, **kwargs):
        results = assess_publishable(entrances, **kwargs)
        for result in results.values():
            for key in list(result["verdicts"]):
                if key not in result["evidence_boxes"]:
                    result["verdicts"][key] = "absent"
        return results

    with pytest.raises(AssertionError):
        _the_verdicts_do_not_move(monkeypatch, assess=assess_that_reads_the_boxes)


def test_that_check_fails_when_a_box_only_softens_a_confidence(
        monkeypatch, no_privacy_rescale):
    """The same check, against a subtler mutation than flipping a verdict.

    "The verdict is untouched, we only weight the confidence by whether we
    could point at it" is the reasonable-sounding version of this mistake, and
    it is the same mistake: a number a reader sees, moved by a pointer. The
    comparison has to catch that too, so it is asserted and not hoped for.
    """
    def assess_that_weights_confidence(entrances, **kwargs):
        results = assess_publishable(entrances, **kwargs)
        for result in results.values():
            for key, value in list(result["confidences"].items()):
                if key not in result["evidence_boxes"] and isinstance(value, int):
                    result["confidences"][key] = max(0, value - 10)
        return results

    with pytest.raises(AssertionError):
        _the_verdicts_do_not_move(monkeypatch, assess=assess_that_weights_confidence)


def test_the_model_is_handed_the_same_images_either_way(
        monkeypatch, no_privacy_rescale):
    monkeypatch.setattr(evidence_boxes, "_detect_frame",
                        lambda detector, img: detector.frames)
    monkeypatch.setattr(evidence_boxes, "_decode_frame", lambda b: b)
    everything = SimpleNamespace(frames=[
        {"label": "door handle", "score": 0.99, "x": 1, "y": 2, "w": 30, "h": 40}])
    nothing = SimpleNamespace(frames=[])

    _, engine_with = _run(monkeypatch, everything)
    _, engine_without = _run(monkeypatch, nothing)
    _, engine_none = _run(monkeypatch, None)

    assert engine_with.images == engine_without.images == engine_none.images
    assert engine_with.seen == engine_without.seen == engine_none.seen


def test_a_detector_that_explodes_costs_the_boxes_and_nothing_else(
        monkeypatch, no_privacy_rescale):
    def blow_up(detector, img):
        raise RuntimeError("the checkpoint is corrupt")

    monkeypatch.setattr(evidence_boxes, "_decode_frame", lambda b: b)
    monkeypatch.setattr(evidence_boxes, "_detect_frame", blow_up)
    exploding, _ = _run(monkeypatch, object())
    clean, _ = _run(monkeypatch, None)
    assert exploding["E-001"]["verdicts"] == clean["E-001"]["verdicts"]
    assert exploding["E-001"]["evidence_boxes"] == {}


def test_an_uninstalled_detector_publishes_the_verdicts_anyway(
        monkeypatch, no_privacy_rescale):
    def unavailable(frames, *, detector=None):
        raise DetectorUnavailable("no torch here")

    monkeypatch.setattr("frontdoor.scan_publish.locate_evidence", unavailable)
    results, _ = _run(monkeypatch, object())
    assert results["E-001"]["verdicts"]
    assert results["E-001"]["evidence_boxes"] == {}
    # And it says NOBODY LOOKED rather than "we looked and found nothing".
    # A detector that could not be loaded looked at no photograph at all, so a
    # receipt built on this must not offer to say where it looked.
    assert results["E-001"]["evidence_boxes_searched"] is False


# --- 1b. "we looked" and "nobody looked" stay different sentences -------------


def test_the_searched_flag_says_the_detector_ran_and_nothing_more(
        monkeypatch, no_privacy_rescale):
    """One boolean per entrance, true whether or not anything was found.

    This is the whole apparatus for telling "we looked here and could not point
    at one" from "nobody looked", and it is per ENTRANCE on purpose. Every
    criterion is looked for on every entrance, so a per-criterion flag would
    carry no extra truth and would re-create the per-criterion "searched and
    empty" value that made this detector fail as a scorer.
    """
    monkeypatch.setattr(evidence_boxes, "_decode_frame", lambda b: b)
    monkeypatch.setattr(evidence_boxes, "_detect_frame",
                        lambda detector, img: detector.frames)

    found_nothing, _ = _run(monkeypatch, SimpleNamespace(frames=[]))
    found_one, _ = _run(monkeypatch, SimpleNamespace(frames=[
        {"label": "door handle", "score": 0.9, "x": 1, "y": 2, "w": 30, "h": 40}]))
    never_ran, _ = _run(monkeypatch, None)

    assert found_nothing["E-001"]["evidence_boxes_searched"] is True
    assert found_nothing["E-001"]["evidence_boxes"] == {}
    assert found_one["E-001"]["evidence_boxes_searched"] is True
    assert never_ran["E-001"]["evidence_boxes_searched"] is False

    # It reaches the record as a flag and NEVER as a per-criterion value: a
    # searched record with nothing found still has no key for any criterion.
    matches = [{"entrance_id": "E-001", "place_ref": None, "matched": False}]
    record = build_records({"E-001": found_nothing["E-001"]}, matches)[0]
    assert record["evidence_boxes_searched"] is True
    assert "evidence_boxes" not in record
    for key in CRITERIA_KEYS:
        assert key not in record.get("evidence_boxes", {})


# --- 2. the record's verdicts are untouched by the record's boxes -------------


def test_the_published_record_carries_the_same_verdicts_with_and_without_boxes():
    settled = {
        "entrance_id": "E-001", "captured_at": "2026-09-04T18:00:00Z",
        "view_count": 2, "faces_blurred": 0, "mode": "integrated",
        "verdicts": {key: "present" for key in CRITERIA_KEYS},
        "confidences": {key: 80 for key in CRITERIA_KEYS},
        "face_check": "clear", "error": None, "failure": None,
        "attempts": 1, "rejected_attempts": 0, "verdict_failures": {},
    }
    matches = [{"entrance_id": "E-001", "place_ref": None, "matched": False}]

    bare = build_records({"E-001": dict(settled)}, matches)[0]
    boxed = build_records(
        {"E-001": dict(settled, evidence_boxes=_boxes_for_everything())}, matches
    )[0]

    assert bare["verdicts"] == boxed["verdicts"]
    assert bare["confidences"] == boxed["confidences"]
    assert "evidence_boxes" not in bare
    assert set(boxed["evidence_boxes"]) == set(CRITERIA_KEYS)
    # Everything except the boxes and the fresh scan_id is byte-identical, so a
    # record that gained boxes gained nothing else.
    assert ({k: v for k, v in bare.items() if k != "scan_id"}
            == {k: v for k, v in boxed.items()
                if k not in ("scan_id", "evidence_boxes")})


def test_an_absent_verdict_is_still_absent_when_a_box_was_found():
    """The exact confusion that killed the scoring arm, refused in the record.

    A box on a criterion the engine called `absent` does not upgrade it, soften
    it, or annotate it. The verdict is the engine's and the box is a pointer to
    where the engine looked.
    """
    settled = {
        "entrance_id": "E-001", "captured_at": "2026-09-04T18:00:00Z",
        "view_count": 1, "faces_blurred": 0, "mode": "integrated",
        "verdicts": {key: "absent" for key in CRITERIA_KEYS},
        "confidences": {key: 90 for key in CRITERIA_KEYS},
        "face_check": "clear", "error": None, "failure": None,
        "attempts": 1, "rejected_attempts": 0, "verdict_failures": {},
        "evidence_boxes": _boxes_for_everything(),
    }
    record = build_records(
        {"E-001": settled},
        [{"entrance_id": "E-001", "place_ref": None, "matched": False}])[0]
    assert all(v == "absent" for v in record["verdicts"].values())


# --- 3. a missing box has no shape at all ------------------------------------


def test_a_criterion_with_nothing_found_is_absent_from_the_mapping(monkeypatch):
    monkeypatch.setattr(evidence_boxes, "_decode_frame", lambda b: b)
    monkeypatch.setattr(evidence_boxes, "_detect_frame", lambda d, img: [
        {"label": "door handle", "score": 0.9, "x": 5, "y": 5, "w": 30, "h": 30},
    ])
    located = locate_evidence([b"frame"], detector=object())
    assert set(located) == {"accessible_door_hardware"}
    for key in CRITERIA_KEYS:
        if key == "accessible_door_hardware":
            continue
        # Not None, not False, not {} -- there is no entry to misread.
        assert key not in located


def test_a_weak_box_is_dropped_rather_than_recorded_with_a_low_score(monkeypatch):
    monkeypatch.setattr(evidence_boxes, "_decode_frame", lambda b: b)
    monkeypatch.setattr(evidence_boxes, "_detect_frame", lambda d, img: [
        {"label": "ramp", "score": evidence_boxes.MIN_SCORE - 0.01,
         "x": 5, "y": 5, "w": 30, "h": 30},
    ])
    assert locate_evidence([b"frame"], detector=object()) == {}


def test_no_returned_box_ever_carries_a_verdict_word(monkeypatch):
    monkeypatch.setattr(evidence_boxes, "_decode_frame", lambda b: b)
    monkeypatch.setattr(evidence_boxes, "_detect_frame", lambda d, img: [
        {"label": phrasings[0], "score": 0.8, "x": 1, "y": 1, "w": 40, "h": 40}
        for phrasings in CRITERION_QUERIES.values()
    ])
    located = locate_evidence([b"frame"], detector=object())
    assert located
    for key, box in located.items():
        assert set(box) == {"frame", "x", "y", "w", "h", "label", "score"}
        for field, value in box.items():
            assert not (isinstance(value, str) and value in VERDICT_WORDS), (
                f"{key}.{field} carries a verdict word")


# --- 4. the detector is structurally incapable of reading a verdict ----------


def test_locate_evidence_has_no_parameter_a_verdict_could_arrive_through():
    signature = inspect.signature(locate_evidence)
    assert list(signature.parameters) == ["frames", "detector"]


def _executable_names(module):
    """Every identifier and literal the module actually RUNS.

    Read off the syntax tree with docstrings dropped, so the module's prose --
    which necessarily says the word "verdict" while explaining why it may not
    have one -- cannot fail the rule, and cannot satisfy it either. Only names
    the interpreter would evaluate are returned.
    """
    tree = ast.parse(inspect.getsource(module))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(id(node.body[0].value))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                names.add(node.value)
    return names


def test_the_detector_module_never_reaches_anything_that_knows_a_verdict():
    """The vocabulary is shared; the judgement is not.

    frontdoor.evidence_boxes may not import frontdoor.screening,
    frontdoor.scan_records or anything else that knows what a verdict is, and
    no name it evaluates may be a verdict or a confidence. If it could reach a
    verdict it could condition on one, and no amount of care in the file above
    would rule that out.
    """
    names = _executable_names(evidence_boxes)
    forbidden = ("screening", "scan_records", "assessment_store", "anthropic",
                 "verdict", "verdicts", "confidence", "confidences",
                 "ALLOWED_VERDICTS", "present", "absent", "not_visible")
    for name in sorted(names):
        for word in forbidden:
            assert word not in name, (
                f"frontdoor.evidence_boxes evaluates {name!r}, which reaches "
                f"{word!r}; a pointer that can see a verdict is a scorer, and "
                "this one was measured making the product worse")


def test_the_forbidden_name_check_would_actually_catch_something():
    """The scanner above is only worth having if it can fail."""
    assert "verdicts" in _executable_names(scan_records)


def test_the_detector_runs_after_the_assessment_is_settled(monkeypatch,
                                                           no_privacy_rescale):
    """Order, not just absence of arguments: nothing re-enters the engine.

    In assess_publishable the box pass sits below the attempt loop, so by the
    time a box exists the verdicts cannot change. Driven here by a detector
    that asserts the engine has already been called and then fails the test if
    the engine is called again afterwards.
    """
    engine = RecordingEngine()
    order = []

    def detect(detector, img):
        order.append("detect")
        return []

    monkeypatch.setattr(evidence_boxes, "_decode_frame", lambda b: b)
    monkeypatch.setattr(evidence_boxes, "_detect_frame", detect)
    real_screen = engine.screen_entrance_integrated

    def screen(entrance_id, images):
        order.append("screen")
        return real_screen(entrance_id, images)

    engine.screen_entrance_integrated = screen
    assess_publishable({"E-001": ["c1"]}, get_capture=FakeCapture,
                       engine=engine, detector=object())
    assert order == ["screen", "detect"]


def test_the_criteria_this_points_at_are_exactly_the_criteria_scored():
    """A criterion with no query would silently never get a box.

    On screen that reads as "we could not point at this one", which would be a
    lie: nobody looked. Keeping the two vocabularies equal is the only way that
    sentence stays true.
    """
    assert tuple(CRITERION_QUERIES) == tuple(CRITERIA_KEYS)
