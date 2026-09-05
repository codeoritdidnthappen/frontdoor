"""Tests for the vision screening engine (TICK-245, #167).

No live API calls: every test injects a fake anthropic client.
"""

import base64
import json
import logging
import threading
import time

import pytest

from frontdoor.screening import (
    ALLOWED_VERDICTS,
    ADA_CHECK_KEYS,
    CRITERIA_KEYS,
    FACE_CHECK_KEY,
    PROMPT_RESOURCE,
    EntranceScreening,
    ImageAssessment,
    ScreeningError,
    ScreeningConfig,
    ScreeningEngine,
    SealedSplitError,
    SpendCapError,
    aggregate_assessments,
    build_integrated_prompt,
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
    body["ada_checks"] = {
        key: {"result": "true", "evidence": f"{key} visible in the photos"}
        for key in ADA_CHECK_KEYS
    }
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
    with pytest.raises(ScreeningError, match="handrails.*invalid verdict"):
        validate_verdicts(parsed)


def test_missing_or_extra_criterion_rejects_the_whole_response():
    for change in ("missing", "extra"):
        parsed = json.loads(_payload())
        if change == "missing":
            del parsed["criteria"]["accessibility_signage"]
        else:
            parsed["criteria"]["door_width"] = parsed["criteria"]["handrails"]
        with pytest.raises(ScreeningError, match="exactly the four criteria"):
            validate_verdicts(parsed)


@pytest.mark.parametrize("confidence", [True, "80", 80.5, -1, 101])
def test_invalid_confidence_rejects_the_whole_response(confidence):
    parsed = json.loads(_payload())
    parsed["criteria"]["handrails"]["confidence"] = confidence
    with pytest.raises(ScreeningError, match="handrails confidence"):
        validate_verdicts(parsed)


@pytest.mark.parametrize("evidence", ["", "  ", "first line\nsecond line", "x" * 201])
def test_invalid_evidence_rejects_the_whole_response(evidence):
    parsed = json.loads(_payload())
    parsed["criteria"]["handrails"]["evidence"] = evidence
    with pytest.raises(ScreeningError, match="handrails evidence"):
        validate_verdicts(parsed)


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


def test_tick_245_ac_3_invalid_result_is_a_recorded_error_never_partial_output():
    parsed = json.loads(_payload())
    parsed["criteria"]["handrails"]["confidence"] = "80"
    engine = ScreeningEngine(client=FakeClient([_Response(json.dumps(parsed))]))
    result = engine.assess_image(b"jpeg-bytes")
    assert result.criteria is None
    assert "handrails confidence" in result.error


def test_api_exception_is_a_recorded_error():
    engine = ScreeningEngine(client=FakeClient([RuntimeError("connection reset")]))
    result = engine.assess_image(b"jpeg-bytes")
    assert result.criteria is None
    assert "connection reset" in result.error


# --- face_check: the automatic privacy audit (TICK-257 follow-up, #232) ------


def test_prompt_carries_the_face_check_question_as_a_fifth_item():
    prompt = build_prompt()
    assert FACE_CHECK_KEY in prompt
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


def test_missing_face_check_is_unknown_with_a_logged_warning_never_a_crash(caplog):
    # PR #243 review: a model that never answered must not be reported as
    # "clear" - that would assert a check that did not happen. The reply is
    # normalized to "unknown", logged, never crashed on.
    engine = ScreeningEngine(
        client=FakeClient([_Response(_payload(face_check=None))])
    )
    with caplog.at_level(logging.WARNING, logger="frontdoor.screening"):
        result = engine.assess_image(b"jpeg-bytes")
    assert result.error is None
    assert result.face_check == "unknown"
    assert "face_check missing or invalid" in caplog.text


def test_out_of_vocabulary_face_check_is_unknown_with_a_logged_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="frontdoor.screening"):
        assert validate_face_check({FACE_CHECK_KEY: "maybe"}) == "unknown"
    assert "face_check missing or invalid" in caplog.text
    assert validate_face_check({FACE_CHECK_KEY: " FACE_VISIBLE "}) == "face_visible"


def test_errored_assessment_defaults_face_check_to_unknown():
    # Nothing was retained for an errored view, so there is nothing to
    # quarantine; the default must not invent a face_visible - and it must
    # not claim "clear" either, because no check produced an answer.
    engine = ScreeningEngine(client=FakeClient([RuntimeError("boom")]))
    assert engine.assess_image(b"jpeg-bytes").face_check == "unknown"


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


def test_tick_245_ac_2_tie_resolves_to_the_conservative_verdict():
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


def test_tick_245_ac_2_per_image_evaluation_accepts_all_seven_eligible_views():
    client = FakeClient([_Response(_payload()) for _ in range(7)])
    result = ScreeningEngine(client=client).screen_entrance(
        DEV_ID, [bytes([value]) for value in range(7)]
    )
    assert len(client.calls) == 7
    assert len(result.assessments) == 7
    assert result.summary["ramp_or_bevel"].counts == {"present": 7}


def test_spend_cap_aborts_the_run_instead_of_exceeding_it():
    client = FakeClient([_Response(_payload())] * 3)
    config = ScreeningConfig(max_usd_per_run=0.08, usd_per_image=0.05)
    engine = ScreeningEngine(client=client, config=config)
    with pytest.raises(SpendCapError, match=r"\$0\.08"):
        engine.screen_entrance(DEV_ID, [b"a", b"b", b"c"])
    assert len(client.calls) == 1  # second call was stopped before spending


def test_tick_245_ac_9_injected_client_needs_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    engine = ScreeningEngine(client=FakeClient([_Response(_payload())]))
    result = engine.screen_entrance(DEV_ID, [b"jpeg-bytes"])
    assert result.summary["ramp_or_bevel"].verdict == "present"


def test_tick_245_ac_6_model_call_uses_exact_surface_without_sampling():
    client = FakeClient([_Response(_payload())])
    ScreeningEngine(client=client).assess_image(b"jpeg-bytes")
    call = client.calls[0]
    assert call["model"] == "claude-sonnet-5"
    assert set(call) == {"model", "max_tokens", "system", "messages"}
    # Offline eval: 2000 tokens truncates sonnet's JSON on hard entrances once
    # adaptive thinking has eaten the budget; the default must stay >= 4000.
    assert call["max_tokens"] >= 4000
    assert "not_visible" in call["system"]
    assert "Never guess measurements" in call["system"]
    prompt = call["messages"][0]["content"][1]["text"]
    for key in CRITERIA_KEYS:
        assert key in prompt
    assert prompt == build_prompt()


def test_tick_245_ac_4_prompts_load_from_committed_resource_at_call_time(
    monkeypatch,
):
    from frontdoor import screening

    calls = []
    real_prompt = screening._prompt

    def observed(name, **values):
        calls.append((name, values))
        return real_prompt(name, **values)

    monkeypatch.setattr(screening, "_prompt", observed)
    client = FakeClient([_Response(_payload())])
    ScreeningEngine(client=client).assess_image(b"jpeg-bytes")
    assert calls == [("single_view", {}), ("system", {})]
    resource = (
        screening.resources.files("frontdoor")
        .joinpath(PROMPT_RESOURCE)
        .read_text(encoding="utf-8")
    )
    assert "Never guess measurements" in resource


def test_model_is_overridable_via_config():
    client = FakeClient([_Response(_payload())])
    config = ScreeningConfig(model="claude-haiku-x")
    ScreeningEngine(client=client, config=config).assess_image(b"jpeg-bytes")
    assert client.calls[0]["model"] == "claude-haiku-x"


# --- integrated multi-view mode ----------------------------------------------
#
# Offline eval on the 12-entrance pilot set: per-image majority voting amplifies
# shared camera-position blind spots, so the integrated mode sends every view of
# an entrance in ONE model call. These tests pin the call structure, the split
# discipline, the n-image spend booking, and that refusal/truncation are
# recorded, never silent. Same rule as above: no live API calls.


def test_integrated_sends_all_views_in_one_call_with_image_blocks():
    client = FakeClient([_Response(_payload())])
    engine = ScreeningEngine(client=client)
    engine.screen_entrance_integrated(DEV_ID, [b"a", b"b", b"c"])
    assert len(client.calls) == 1
    content = client.calls[0]["messages"][0]["content"]
    assert [block["type"] for block in content] == ["image", "image", "image", "text"]
    sent = [base64.b64decode(block["source"]["data"]) for block in content[:3]]
    assert sent == [b"a", b"b", b"c"]
    assert content[3]["text"] == build_integrated_prompt(3)


def test_integrated_prompt_instructs_cross_view_integration():
    prompt = build_integrated_prompt(4)
    assert "4 photographs" in prompt
    assert "same entrance" in prompt
    assert "any view" in prompt
    assert "trust the view that shows the relevant area" in prompt
    for key in CRITERIA_KEYS:
        assert key in prompt


def test_criteria_text_carries_the_validated_decision_rules():
    prompt = build_prompt()
    # camera-position bias: commit on the ground plane, not the frontal frame
    assert "ground plane" in prompt
    assert "side of the entrance" in prompt
    # look-alike confusion: closed-fist rule, with the confusables excluded
    assert "closed fist" in prompt
    assert "push plates" in prompt and "latch brackets" in prompt


def test_integrated_summary_is_the_integrated_verdicts_without_flip_stats():
    """The verdicts carry through; flip_rate and counts are None because no
    cross-view comparison was made - a fabricated 0.0 would turn the honesty
    signal about view disagreement into false confidence."""
    client = FakeClient([_Response(_payload("present", handrails={
        "verdict": "absent", "confidence": 90, "evidence": "no rails in any view",
    }))])
    engine = ScreeningEngine(client=client)
    result = engine.screen_entrance_integrated(DEV_ID, [b"a", b"b"])
    assert isinstance(result, EntranceScreening)
    assert result.entrance_id == DEV_ID and result.split == "dev"
    assert result.mode == "integrated"
    assert len(result.assessments) == 1
    assert result.summary["ramp_or_bevel"].verdict == "present"
    assert result.summary["handrails"].verdict == "absent"
    for key in CRITERIA_KEYS:
        assert result.summary[key].flip_rate is None
        assert result.summary[key].counts is None


def test_per_image_mode_keeps_real_flip_stats_and_says_so():
    client = FakeClient([_Response(_payload("present")),
                         _Response(_payload("absent"))])
    engine = ScreeningEngine(client=client)
    result = engine.screen_entrance(DEV_ID, [b"a", b"b"])
    assert result.mode == "per_image"
    summary = result.summary["ramp_or_bevel"]
    assert summary.flip_rate == pytest.approx(0.5)
    assert summary.counts == {"present": 1, "absent": 1}


def test_tick_245_ac_5_integrated_sealed_id_is_refused_before_model_call():
    client = FakeClient([_Response(_payload())])
    engine = ScreeningEngine(client=client)
    with pytest.raises(SealedSplitError, match=SEALED_ID):
        engine.screen_entrance_integrated(SEALED_ID, [b"a", b"b"])
    assert client.calls == []


def test_integrated_books_spend_for_every_image_in_the_call():
    client = FakeClient([_Response(_payload())])
    engine = ScreeningEngine(client=client)
    engine.screen_entrance_integrated(DEV_ID, [b"a", b"b", b"c"])
    assert engine.spent_usd == pytest.approx(3 * engine.config.usd_per_image)


def test_integrated_spend_cap_refuses_the_call_before_spending():
    client = FakeClient([_Response(_payload())])
    config = ScreeningConfig(max_usd_per_run=0.10, usd_per_image=0.05)
    engine = ScreeningEngine(client=client, config=config)
    with pytest.raises(SpendCapError, match=r"\$0\.10"):
        engine.screen_entrance_integrated(DEV_ID, [b"a", b"b", b"c"])
    assert client.calls == []
    assert engine.spent_usd == 0.0


def test_integrated_refusal_is_a_recorded_error_never_silent():
    client = FakeClient([_Response(_payload(), stop_reason="refusal")])
    engine = ScreeningEngine(client=client)
    result = engine.screen_entrance_integrated(DEV_ID, [b"a"])
    (assessment,) = result.assessments
    assert assessment.criteria is None
    assert "refused" in assessment.error
    assert result.summary["ramp_or_bevel"].verdict is None


def test_integrated_truncation_is_a_recorded_error_never_silent():
    client = FakeClient([_Response('{"criteria": {"ramp', stop_reason="max_tokens")])
    engine = ScreeningEngine(client=client)
    result = engine.screen_entrance_integrated(DEV_ID, [b"a"])
    (assessment,) = result.assessments
    assert assessment.criteria is None
    assert "truncated" in assessment.error
    assert "max_tokens" in assessment.error


def test_integrated_media_types_default_to_jpeg_and_are_overridable():
    client = FakeClient([_Response(_payload()), _Response(_payload())])
    engine = ScreeningEngine(client=client)
    engine.assess_images_integrated([b"a", b"b"])
    engine.assess_images_integrated(
        [b"a", b"b"], media_types=["image/png", "image/webp"]
    )
    first = client.calls[0]["messages"][0]["content"]
    assert [b["source"]["media_type"] for b in first[:2]] == ["image/jpeg"] * 2
    second = client.calls[1]["messages"][0]["content"]
    assert [b["source"]["media_type"] for b in second[:2]] == [
        "image/png", "image/webp",
    ]


def test_tick_245_ac_8_rejects_zero_images_or_media_type_drift_before_call():
    client = FakeClient([_Response(_payload())])
    engine = ScreeningEngine(client=client)
    with pytest.raises(ScreeningError, match="at least one image"):
        engine.assess_images_integrated([])
    with pytest.raises(ScreeningError, match="one value for every image"):
        engine.assess_images_integrated(
            [b"a", b"b"], media_types=["image/jpeg"]
        )
    assert client.calls == []
    assert engine.spent_usd == 0.0


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
