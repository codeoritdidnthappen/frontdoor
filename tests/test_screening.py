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
    ADA_RESULTS,
    CRITERIA_KEYS,
    FACE_CHECK_KEY,
    FAILURE_ERROR,
    FAILURE_REFUSED,
    FAILURE_REJECTED,
    FAILURE_TRUNCATED,
    PROMPT_RESOURCE,
    REJECTION_ADA_VALUE,
    REJECTION_MISSING,
    EntranceScreening,
    ImageAssessment,
    ResponseRejected,
    ScreeningError,
    ScreeningConfig,
    ScreeningEngine,
    SealedSplitError,
    SpendCapError,
    aggregate_assessments,
    build_integrated_prompt,
    build_prompt,
    criterion_verdict,
    integrated_summary,
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
    assert set(call) == {"model", "max_tokens", "temperature", "system", "messages"}
    # TICK-394: no temperature used to be sent at all, so every assessment ran
    # at the API default of 1.0 and the same photograph could come back with a
    # different verdict. The surface is still exactly these keys -- no top_p,
    # no top_k -- and the sampling it now states explicitly is none.
    assert call["temperature"] == 0
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


# --- TICK-399: a rejected response is a failure, not an abstention ------------
#
# The defect: the model sometimes puts an eight-check ADA value
# (`not_applicable`, `cannot_determine`) inside the FOUR-criterion block, which
# the same prompt restricts to present/absent/not_visible. validate_verdicts
# then refused the WHOLE reply, all four criteria were lost for that view,
# there was no retry, and downstream the loss was indistinguishable from the
# model having looked and abstained. Measured over the same 28 entrances: one
# run lost nothing, the repeat run discarded 68 of 154 view responses (44%) and
# lost every criterion on 7 entrances -- all scored as clean abstentions.
#
# Three things are pinned here: the failure is named, the reply is asked for
# again, and the criteria that DID validate survive - without ever turning an
# ADA value into a criterion verdict, which is the one collapse this product
# forbids most strongly.


def _ada_bleed_payload(value="not_applicable"):
    """A reply with the eight-check vocabulary in the four-criterion block."""
    return _payload(handrails={
        "verdict": value, "confidence": 70,
        "evidence": "no steps or ramp serve this entrance",
    })


def test_tick_399_ac1_a_rejected_response_is_recorded_as_a_failure():
    """A rejection is a FAILURE of the call, and the record says so.

    Before this, the only trace was an `error` string that a consumer had to
    parse an exception name out of, next to criteria of None that looked
    exactly like a view nobody could assess.
    """
    engine = ScreeningEngine(
        client=FakeClient([_Response("not JSON at all")] * 2)
    )
    result = engine.assess_image(b"jpeg-bytes")
    assert result.failure == FAILURE_REJECTED
    assert result.criteria is None
    assert result.rejected_attempts == 2


@pytest.mark.parametrize("stop_reason,expected", [
    ("refusal", FAILURE_REFUSED),
    ("max_tokens", FAILURE_TRUNCATED),
])
def test_tick_399_ac1_other_failures_are_named_and_not_confused_with_rejection(
    stop_reason, expected
):
    client = FakeClient([_Response(_payload(), stop_reason=stop_reason)] * 3)
    result = ScreeningEngine(client=client).assess_image(b"jpeg-bytes")
    assert result.failure == expected
    # Neither is a formatting slip: one is a deliberate answer, the other
    # repeats at the same token budget. Asking again would only spend money.
    assert len(client.calls) == 1
    assert result.attempts == 1


def test_tick_399_ac1_a_transport_error_is_a_failure_but_not_a_rejection():
    client = FakeClient([RuntimeError("connection reset")] * 3)
    result = ScreeningEngine(client=client).assess_image(b"jpeg-bytes")
    assert result.failure == FAILURE_ERROR
    assert len(client.calls) == 1


def test_tick_399_ac4_a_rejected_response_is_asked_again_once():
    """The bounded retry: a second attempt is made, and it recovers the view."""
    client = FakeClient([
        _Response(_ada_bleed_payload()),   # rejected
        _Response(_payload("absent")),     # the retry answers in vocabulary
    ])
    result = ScreeningEngine(client=client).assess_image(b"jpeg-bytes")
    assert len(client.calls) == 2
    assert result.attempts == 2
    assert result.rejected_attempts == 1
    assert result.failure is None
    assert result.error is None
    assert all(
        result.criteria[key]["verdict"] == "absent" for key in CRITERIA_KEYS
    )


def test_tick_399_ac4_the_retry_is_bounded_not_a_loop():
    client = FakeClient([_Response(_ada_bleed_payload()) for _ in range(10)])
    result = ScreeningEngine(client=client).assess_image(b"jpeg-bytes")
    assert len(client.calls) == 2  # ScreeningConfig.response_attempts
    assert result.attempts == 2
    assert result.rejected_attempts == 2


def test_tick_399_the_retry_count_is_configurable():
    client = FakeClient([_Response(_ada_bleed_payload()) for _ in range(10)])
    engine = ScreeningEngine(
        client=client, config=ScreeningConfig(response_attempts=4)
    )
    engine.assess_image(b"jpeg-bytes")
    assert len(client.calls) == 4

    single = FakeClient([_Response(_ada_bleed_payload()) for _ in range(10)])
    ScreeningEngine(
        client=single, config=ScreeningConfig(response_attempts=1)
    ).assess_image(b"jpeg-bytes")
    assert len(single.calls) == 1


def test_tick_399_the_retry_books_its_own_spend():
    """A retry is a real call. A cap that ignored it would hold on paper."""
    client = FakeClient([_Response(_ada_bleed_payload())] * 2)
    engine = ScreeningEngine(
        client=client, config=ScreeningConfig(usd_per_image=0.05))
    engine.assess_image(b"jpeg-bytes")
    assert len(client.calls) == 2
    assert engine.spent_usd == pytest.approx(0.10)


def test_tick_399_a_retry_that_would_break_the_spend_cap_is_not_made():
    client = FakeClient([_Response(_ada_bleed_payload())] * 2)
    engine = ScreeningEngine(
        client=client,
        config=ScreeningConfig(max_usd_per_run=0.05, usd_per_image=0.05),
    )
    result = engine.assess_image(b"jpeg-bytes")
    assert len(client.calls) == 1
    assert engine.spent_usd == pytest.approx(0.05)
    # The rejection stands and is still recorded as one; the run is not aborted
    # part-way over a formatting slip.
    assert result.failure == FAILURE_REJECTED


def test_tick_399_ac3_an_ada_value_in_one_criterion_keeps_the_other_three():
    """Recovery: the reply loses the field it got wrong, not all four.

    Both attempts answer the same way, so this is what survives when the retry
    does not help either.
    """
    client = FakeClient([_Response(_ada_bleed_payload())] * 2)
    result = ScreeningEngine(client=client).assess_image(b"jpeg-bytes")
    assert result.failure == FAILURE_REJECTED  # still a rejected response
    for key in ("ramp_or_bevel", "accessible_door_hardware",
                "accessibility_signage"):
        assert result.criteria[key]["verdict"] == "present"
    assert result.criteria["handrails"]["verdict"] is None


@pytest.mark.parametrize("value", ADA_RESULTS)
def test_tick_399_ac3_an_ada_value_is_never_reinterpreted_as_a_verdict(value):
    """`not_applicable` is not `absent` and is not `not_visible`.

    Guessing what an off-vocabulary answer meant is the single collapse this
    product forbids most strongly, so the refused field carries NO verdict at
    all, and says it was refused rather than pretending it was never asked.
    """
    client = FakeClient([_Response(_ada_bleed_payload(value))] * 2)
    result = ScreeningEngine(client=client).assess_image(b"jpeg-bytes")
    entry = result.criteria["handrails"]
    assert entry["verdict"] is None
    assert entry["verdict"] not in ALLOWED_VERDICTS
    assert entry["rejected"] == REJECTION_ADA_VALUE
    assert entry["rejected_value"] == value
    # The confidence and evidence written to justify the refused answer do not
    # travel with it.
    assert entry["confidence"] is None
    assert entry["evidence"] is None


def test_tick_399_recovery_covers_a_criterion_missing_from_the_block():
    """The other observed shape: a criteria object that was not exactly four."""
    parsed = json.loads(_payload())
    del parsed["criteria"]["accessibility_signage"]
    client = FakeClient([_Response(json.dumps(parsed))] * 2)
    result = ScreeningEngine(client=client).assess_image(b"jpeg-bytes")
    assert result.criteria["ramp_or_bevel"]["verdict"] == "present"
    entry = result.criteria["accessibility_signage"]
    assert entry["verdict"] is None
    assert entry["rejected"] == REJECTION_MISSING


def test_tick_399_recovery_does_not_widen_to_a_reply_of_unknown_shape():
    """A verdict word from NEITHER vocabulary still rejects the whole reply.

    Recovery is for the one understood failure mode. A reply that invents a
    word is a reply whose shape the engine does not recognise, and salvaging
    fields out of one would be guessing about the rest.
    """
    parsed = json.loads(_payload())
    parsed["criteria"]["handrails"]["verdict"] = "maybe"
    client = FakeClient([_Response(json.dumps(parsed))] * 2)
    result = ScreeningEngine(client=client).assess_image(b"jpeg-bytes")
    assert result.criteria is None
    assert result.failure == FAILURE_REJECTED
    with pytest.raises(ResponseRejected, match="handrails.*invalid verdict"):
        validate_verdicts(parsed, recover=True)


def test_tick_399_a_refused_ada_block_no_longer_takes_the_criteria_with_it():
    """The same whole-response loss, arriving from the other half of the reply.

    The eight checks and the four criteria are validated independently now.
    The refused half is refused outright -- nothing the model wrote about it
    is carried -- and the half that validated stands.
    """
    parsed = json.loads(_payload())
    parsed["ada_checks"]["threshold"]["evidence"] = "this entrance is compliant"
    client = FakeClient([_Response(json.dumps(parsed))] * 2)
    result = ScreeningEngine(client=client).assess_image(b"jpeg-bytes")
    assert result.ada_checks is None
    assert result.failure == FAILURE_REJECTED
    assert set(result.criteria) == set(CRITERIA_KEYS)
    assert "compliant" not in (result.error or "")


def test_tick_399_ac2_aggregation_separates_rejected_views_from_abstentions():
    """Two views, both refused: the summary reports failure, not abstention."""
    rejected = ImageAssessment(
        criteria=None, latency_s=1.0, error="ResponseRejected: ...",
        failure=FAILURE_REJECTED,
    )
    summary = aggregate_assessments((rejected, rejected))
    for key in CRITERIA_KEYS:
        assert summary[key].verdict is None
        assert summary[key].rejected == 2
        assert summary[key].failed == 0

    abstained = _assessment({key: "not_visible" for key in CRITERIA_KEYS})
    honest = aggregate_assessments((abstained,))
    for key in CRITERIA_KEYS:
        # The honest abstention still reads as one: a verdict, and nothing
        # counted against the engine.
        assert honest[key].verdict == "not_visible"
        assert honest[key].rejected == 0 and honest[key].failed == 0


def test_tick_399_ac2_a_recovered_field_is_rejected_only_for_that_criterion():
    client = FakeClient([_Response(_ada_bleed_payload())] * 2)
    result = ScreeningEngine(client=client).assess_image(b"jpeg-bytes")
    summary = aggregate_assessments((result,))
    assert summary["handrails"].verdict is None
    assert summary["handrails"].rejected == 1
    assert summary["ramp_or_bevel"].verdict == "present"
    assert summary["ramp_or_bevel"].rejected == 0


def test_tick_399_integrated_summary_says_a_criterion_was_rejected():
    client = FakeClient([_Response(_ada_bleed_payload())] * 2)
    result = ScreeningEngine(client=client).assess_images_integrated([b"a"])
    summary = integrated_summary(result)
    assert summary["handrails"].verdict is None
    assert summary["handrails"].rejected == 1
    assert summary["accessibility_signage"].verdict == "present"
    assert summary["accessibility_signage"].rejected == 0


def test_tick_399_an_integrated_retry_books_every_view_again():
    client = FakeClient([_Response(_ada_bleed_payload())] * 2)
    engine = ScreeningEngine(
        client=client, config=ScreeningConfig(
            max_usd_per_run=10.0, usd_per_image=0.05))
    engine.assess_images_integrated([b"a", b"b", b"c"])
    # A retry re-sends all three views, so it books what the first call booked.
    assert engine.spent_usd == pytest.approx(0.30)


def test_tick_399_criterion_verdict_is_the_one_place_none_is_explained():
    clean = _assessment({"ramp_or_bevel": "present"})
    assert criterion_verdict(clean, "ramp_or_bevel") == ("present", None)
    assert criterion_verdict(clean, "handrails") == ("not_visible", None)

    dead = ImageAssessment(criteria=None, latency_s=1.0,
                           error="boom", failure=FAILURE_ERROR)
    assert criterion_verdict(dead, "handrails") == (None, FAILURE_ERROR)


# --- TICK-394: an explicit temperature ---------------------------------------


def test_tick_394_the_call_sets_an_explicit_temperature_of_zero():
    """Pinned, because it was absent silently and must not be dropped silently.

    Before this the call passed no temperature at all, so every assessment ran
    at the API default of 1.0 and a contributor who rescanned the same door
    could get a different answer with nothing about the world having changed.
    """
    assert ScreeningConfig().temperature == 0
    client = FakeClient([_Response(_payload())])
    ScreeningEngine(client=client).assess_image(b"jpeg-bytes")
    assert client.calls[0]["temperature"] == 0


def test_tick_394_the_integrated_call_sets_it_too():
    client = FakeClient([_Response(_payload())])
    ScreeningEngine(client=client).assess_images_integrated([b"a", b"b"])
    assert client.calls[0]["temperature"] == 0


def test_tick_394_temperature_is_configured_not_a_literal():
    client = FakeClient([_Response(_payload())])
    ScreeningEngine(
        client=client, config=ScreeningConfig(temperature=0.7)
    ).assess_image(b"jpeg-bytes")
    assert client.calls[0]["temperature"] == 0.7


def test_tick_394_the_same_reply_twice_gives_the_same_verdicts():
    """The engine's own half of determinism: same input, same output.

    Temperature 0 is what makes the model's half hold; this pins that nothing
    in the engine adds variation of its own. The end-to-end demonstration
    against the real API is in the pull request, not here - the suite makes no
    live calls.
    """
    payload = _payload("absent")
    first = ScreeningEngine(
        client=FakeClient([_Response(payload)])).assess_image(b"jpeg-bytes")
    second = ScreeningEngine(
        client=FakeClient([_Response(payload)])).assess_image(b"jpeg-bytes")
    assert first.criteria == second.criteria
    assert first.ada_checks == second.ada_checks
    assert first.face_check == second.face_check
