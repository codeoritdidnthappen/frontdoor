"""Tests for the vision screening engine (TICK-245, #167).

No live API calls: every test injects a fake anthropic client.
"""

import json
import logging
import threading
import time

import pytest

from frontdoor.screening import (
    ALLOWED_VERDICTS,
    CRITERIA_KEYS,
    FACE_CHECK_KEY,
    FACE_CHECK_QUESTION,
    SYSTEM_PROMPT,
    EntranceScreening,
    ImageAssessment,
    ScreeningConfig,
    ScreeningEngine,
    SealedSplitError,
    SpendCapError,
    aggregate_assessments,
    build_prompt,
    validate_face_check,
    validate_verdicts,
)

# Known assignments under the committed seed (pinned in test_split.py):
DEV_ID = "E-001"
SEALED_ID = "E-014"


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, text, stop_reason="end_turn"):
        self.stop_reason = stop_reason
        self.content = [_Block(text)]


class FakeClient:
    """Stands in for anthropic.Anthropic: client.messages.create(...)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _payload(verdict="present", face_check="clear", **overrides):
    criteria = {
        key: {"verdict": verdict, "confidence": 80, "evidence": f"{key} seen"}
        for key in CRITERIA_KEYS
    }
    for key, entry in overrides.items():
        criteria[key] = entry
    body = {"criteria": criteria}
    if face_check is not None:
        body[FACE_CHECK_KEY] = face_check
    return json.dumps(body)


def _assessment(verdicts):
    """Build an ImageAssessment from {criterion: verdict}."""
    return ImageAssessment(
        criteria={
            key: {"verdict": verdicts.get(key, "not_visible"),
                  "confidence": 80, "evidence": ""}
            for key in CRITERIA_KEYS
        },
        latency_s=1.0,
    )


def test_assess_image_returns_verdicts_confidence_evidence_and_latency():
    engine = ScreeningEngine(client=FakeClient([_Response(_payload())]))
    result = engine.assess_image(b"jpeg-bytes")
    assert result.error is None
    assert result.latency_s is not None
    for key in CRITERIA_KEYS:
        assert result.criteria[key]["verdict"] == "present"
        assert result.criteria[key]["confidence"] == 80
        assert result.criteria[key]["evidence"]


def test_out_of_vocabulary_verdict_is_flagged_not_silently_accepted():
    parsed = json.loads(_payload())
    parsed["criteria"]["handrails"]["verdict"] = "maybe"
    del parsed["criteria"]["accessibility_signage"]
    out = validate_verdicts(parsed)
    assert out["handrails"]["verdict"] == "INVALID:maybe"
    assert out["accessibility_signage"]["verdict"] == "INVALID:missing"
    assert out["ramp_or_bevel"]["verdict"] == "present"


def test_not_visible_stays_distinct_from_absent():
    parsed = json.loads(_payload(verdict="not_visible"))
    out = validate_verdicts(parsed)
    assert all(out[key]["verdict"] == "not_visible" for key in CRITERIA_KEYS)
    assert "not_visible" in ALLOWED_VERDICTS and "absent" in ALLOWED_VERDICTS


def test_refusal_is_a_recorded_error_never_silent():
    engine = ScreeningEngine(
        client=FakeClient([_Response(_payload(), stop_reason="refusal")])
    )
    result = engine.assess_image(b"jpeg-bytes")
    assert result.criteria is None
    assert "refused" in result.error


def test_parse_failure_is_a_recorded_error_never_silent():
    engine = ScreeningEngine(
        client=FakeClient([_Response("sorry, I can only answer in prose")])
    )
    result = engine.assess_image(b"jpeg-bytes")
    assert result.criteria is None
    assert "no JSON object" in result.error


def test_api_exception_is_a_recorded_error():
    engine = ScreeningEngine(client=FakeClient([RuntimeError("connection reset")]))
    result = engine.assess_image(b"jpeg-bytes")
    assert result.criteria is None
    assert "connection reset" in result.error


# --- face_check: the automatic privacy audit (TICK-257 follow-up, #232) ------


def test_prompt_carries_the_face_check_question_as_a_fifth_item():
    prompt = build_prompt()
    assert FACE_CHECK_KEY in prompt
    assert FACE_CHECK_QUESTION in prompt
    assert "reflections in glass" in prompt


def test_face_check_is_not_an_accessibility_criterion():
    # It never joins CRITERIA (so it never votes in the aggregate) and never
    # appears in the criteria block validate_verdicts returns.
    assert FACE_CHECK_KEY not in CRITERIA_KEYS
    out = validate_verdicts(json.loads(_payload(face_check="face_visible")))
    assert FACE_CHECK_KEY not in out


def test_assess_image_carries_face_visible_through():
    engine = ScreeningEngine(
        client=FakeClient([_Response(_payload(face_check="face_visible"))])
    )
    result = engine.assess_image(b"jpeg-bytes")
    assert result.face_check == "face_visible"
    assert result.error is None
    # The audit answer does not disturb the accessibility verdicts.
    assert result.criteria["ramp_or_bevel"]["verdict"] == "present"


def test_a_clear_face_check_is_carried_through():
    engine = ScreeningEngine(client=FakeClient([_Response(_payload())]))
    assert engine.assess_image(b"jpeg-bytes").face_check == "clear"


def test_missing_face_check_is_clear_with_a_logged_warning_never_a_crash(caplog):
    engine = ScreeningEngine(
        client=FakeClient([_Response(_payload(face_check=None))])
    )
    with caplog.at_level(logging.WARNING, logger="frontdoor.screening"):
        result = engine.assess_image(b"jpeg-bytes")
    assert result.error is None
    assert result.face_check == "clear"
    assert "face_check missing or invalid" in caplog.text


def test_out_of_vocabulary_face_check_is_clear_with_a_logged_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="frontdoor.screening"):
        assert validate_face_check({FACE_CHECK_KEY: "maybe"}) == "clear"
    assert "face_check missing or invalid" in caplog.text
    assert validate_face_check({FACE_CHECK_KEY: " FACE_VISIBLE "}) == "face_visible"


def test_errored_assessment_defaults_face_check_to_clear():
    # Nothing was retained for an errored view, so there is nothing to
    # quarantine; the default must not invent a face_visible.
    engine = ScreeningEngine(client=FakeClient([RuntimeError("boom")]))
    assert engine.assess_image(b"jpeg-bytes").face_check == "clear"


def test_aggregation_majority_verdict_and_flip_rate():
    views = [
        _assessment({"ramp_or_bevel": "present", "handrails": "absent"}),
        _assessment({"ramp_or_bevel": "present", "handrails": "absent"}),
        _assessment({"ramp_or_bevel": "present", "handrails": "absent"}),
        _assessment({"ramp_or_bevel": "absent", "handrails": "absent"}),
        _assessment({"ramp_or_bevel": "not_visible", "handrails": "absent"}),
    ]
    summary = aggregate_assessments(views)
    assert summary["ramp_or_bevel"].verdict == "present"
    assert summary["ramp_or_bevel"].flip_rate == pytest.approx(2 / 5)
    assert summary["ramp_or_bevel"].counts == {
        "present": 3, "absent": 1, "not_visible": 1,
    }
    assert summary["handrails"].verdict == "absent"
    assert summary["handrails"].flip_rate == 0.0


def test_aggregation_tie_resolves_to_the_conservative_verdict():
    views = [
        _assessment({"ramp_or_bevel": "present", "handrails": "present"}),
        _assessment({"ramp_or_bevel": "not_visible", "handrails": "absent"}),
    ]
    summary = aggregate_assessments(views)
    assert summary["ramp_or_bevel"].verdict == "not_visible"
    assert summary["handrails"].verdict == "absent"


def test_aggregation_skips_errored_views_and_invalid_verdicts():
    errored = ImageAssessment(criteria=None, latency_s=None, error="boom")
    invalid = _assessment({"ramp_or_bevel": "INVALID:maybe"})
    voting = _assessment({"ramp_or_bevel": "present"})
    summary = aggregate_assessments([errored, invalid, voting])
    assert summary["ramp_or_bevel"].verdict == "present"
    assert summary["ramp_or_bevel"].counts == {"present": 1}


def test_aggregation_with_no_valid_verdicts_reports_none_not_a_guess():
    errored = ImageAssessment(criteria=None, latency_s=None, error="boom")
    summary = aggregate_assessments([errored])
    assert summary["ramp_or_bevel"].verdict is None
    assert summary["ramp_or_bevel"].flip_rate is None


def test_sealed_entrance_is_refused_before_any_model_call(caplog):
    client = FakeClient([_Response(_payload())])
    engine = ScreeningEngine(client=client)
    with caplog.at_level(logging.INFO, logger="frontdoor.screening"):
        with pytest.raises(SealedSplitError, match=SEALED_ID):
            engine.screen_entrance(SEALED_ID, [b"jpeg-bytes"])
    assert client.calls == []
    assert f"split check: entrance {SEALED_ID} -> sealed" in caplog.text


def test_dev_entrance_screens_all_views_and_logs_the_split_check(caplog):
    client = FakeClient([
        _Response(_payload("present")),
        _Response(_payload("not_visible")),
        _Response(_payload("present")),
    ])
    engine = ScreeningEngine(client=client)
    with caplog.at_level(logging.INFO, logger="frontdoor.screening"):
        result = engine.screen_entrance(DEV_ID, [b"a", b"b", b"c"])
    assert isinstance(result, EntranceScreening)
    assert result.entrance_id == DEV_ID
    assert result.split == "dev"
    assert len(result.assessments) == 3
    assert result.summary["handrails"].verdict == "present"
    assert result.summary["handrails"].flip_rate == pytest.approx(1 / 3)
    assert f"split check: entrance {DEV_ID} -> dev" in caplog.text
    assert "spend cap" in caplog.text


def test_spend_cap_aborts_the_run_instead_of_exceeding_it():
    client = FakeClient([_Response(_payload())] * 3)
    config = ScreeningConfig(max_usd_per_run=0.08, usd_per_image=0.05)
    engine = ScreeningEngine(client=client, config=config)
    with pytest.raises(SpendCapError, match=r"\$0\.08"):
        engine.screen_entrance(DEV_ID, [b"a", b"b", b"c"])
    assert len(client.calls) == 1  # second call was stopped before spending


def test_engine_works_without_an_api_key_in_the_environment(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    engine = ScreeningEngine(client=FakeClient([_Response(_payload())]))
    result = engine.screen_entrance(DEV_ID, [b"jpeg-bytes"])
    assert result.summary["ramp_or_bevel"].verdict == "present"


def test_model_call_carries_the_honest_criteria_contract():
    client = FakeClient([_Response(_payload())])
    ScreeningEngine(client=client).assess_image(b"jpeg-bytes")
    call = client.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["system"] == SYSTEM_PROMPT
    assert "not_visible" in call["system"]
    assert "never guess measurements" in call["system"]
    prompt = call["messages"][0]["content"][1]["text"]
    for key in CRITERIA_KEYS:
        assert key in prompt
    assert prompt == build_prompt()


def test_model_is_overridable_via_config():
    client = FakeClient([_Response(_payload())])
    config = ScreeningConfig(model="claude-haiku-x")
    ScreeningEngine(client=client, config=config).assess_image(b"jpeg-bytes")
    assert client.calls[0]["model"] == "claude-haiku-x"


def test_the_spend_cap_is_checked_and_reserved_atomically():
    """The cap is a check followed by an increment, and /screen now assesses an entrance's
    views in parallel. If another thread can land between the two, every thread reads the
    same `spent_usd`, every thread passes the check, and every thread spends -- the cap
    holds on paper while the run goes over it.

    Racing threads and hoping they interleave does NOT test this: the check and the
    increment are a few bytecodes apart and the window is almost never hit, so that version
    of this test passed with the lock removed. This parks a thread INSIDE the critical
    section and asks whether a second one can get in, which is the property itself rather
    than a symptom of it.
    """
    inside = threading.Event()
    may_leave = threading.Event()
    second_got_in = threading.Event()

    class Parking(ScreeningEngine):
        def _check_spend_cap(self):
            if not inside.is_set():
                inside.set()
                # Hold the section open. With the lock this is the only thread in here.
                may_leave.wait(timeout=2)
            else:
                second_got_in.set()
            super()._check_spend_cap()

    client = FakeClient([_Response(_payload())] * 4)
    engine = Parking(client=client, config=ScreeningConfig(
        max_usd_per_run=10.0, usd_per_image=0.05))

    first = threading.Thread(target=lambda: engine.assess_image(b"a"))
    first.start()
    assert inside.wait(timeout=2), "first thread never reached the spend check"

    second = threading.Thread(target=lambda: engine.assess_image(b"b"))
    second.start()
    entered = second_got_in.wait(timeout=0.3)

    may_leave.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not entered, (
        "a second thread entered the spend check while the first was still inside it; "
        "the check and the reservation are not atomic and the cap can be exceeded"
    )
    assert engine.spent_usd == pytest.approx(0.10)
