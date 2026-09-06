"""One photograph, one assessment (TICK-435, #435).

The engine is sampled and cannot be told not to be (#394: the SDK takes no
`temperature` and the model rejects sampling parameters), so the same bytes
could return different verdicts on different submissions -- a measured 1.7
points of accuracy and about 8% of coverage between two identical runs (#395).
The determinism is therefore made in `frontdoor.assessment_store`, and these
tests pin every claim it makes.

The fake engine used throughout is deliberately a SAMPLING one: it returns a
different verdict on every call. A cache that did not work would show up as a
changed verdict rather than as an extra call nobody counted, and every
determinism assertion below would fail rather than pass vacuously against a
fake that could only ever answer one way.

What these CANNOT do is demonstrate it against the real API, which is the one
acceptance criterion of #435 left open: there is no API credit at the time of
writing. `docs/server-deploy.md` and the pull request both say so, and
`test_screening.py` still pins the call surface itself.
"""

import hashlib
import io
import json
import threading
import time
from pathlib import Path

import pytest

from frontdoor import assessment_store
from frontdoor.assessment_store import (
    ASSESSMENTS_ENV,
    DEFAULT_ASSESSMENTS_PATH,
    assessments_path,
    content_digest,
    engine_version,
    image_digest,
    is_storable,
    load_assessment_store,
    new_assessment_record,
    prompt_digest,
    recall_or_assess,
)
from frontdoor.scan_records import load_scan_records
from frontdoor.screening import (
    CRITERIA_KEYS,
    FAILURE_REJECTED,
    FAILURE_REFUSED,
    FAILURE_TRUNCATED,
    PROMPT_RESOURCE,
    ImageAssessment,
    ScreeningConfig,
)
from frontdoor_server.app import create_app
from frontdoor_server.scan_view import STORE_KEY
from frontdoor_server.screen_view import ENGINE_KEY
from tests.test_scan_publish_endpoint import PLACE_FORM, FakeStore
from tests.test_screen_endpoint import ok_ada_checks, real_jpeg

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The four verdicts the sampling fake cycles through, so "the same photograph
#: gave the same answer" cannot be true by the fake having only one answer.
_SAMPLES = ("present", "absent", "not_visible", "present")


def assessment_with(verdict, *, face_check="clear", latency_s=1.234, **kwargs):
    return ImageAssessment(
        criteria={
            key: {"verdict": verdict, "confidence": 80, "evidence": f"{key} seen"}
            for key in CRITERIA_KEYS
        },
        latency_s=latency_s,
        face_check=face_check,
        ada_checks=ok_ada_checks(),
        **kwargs,
    )


class SamplingEngine:
    """A model that answers differently every time -- which is the real one.

    Counts its calls, so "the second submission made no model call" is an
    assertion about a number rather than about a verdict that might have
    matched by luck.
    """

    def __init__(self, assessments=None, model=None):
        self.config = ScreeningConfig(model=model) if model else ScreeningConfig()
        self._assessments = list(assessments) if assessments else [
            assessment_with(verdict) for verdict in _SAMPLES
        ]
        self.calls = []

    @property
    def call_count(self):
        return len(self.calls)

    def assess_images_integrated(self, images, *, media_types=None):
        self.calls.append((tuple(images), tuple(media_types or ())))
        index = min(len(self.calls) - 1, len(self._assessments) - 1)
        return self._assessments[index]


@pytest.fixture(autouse=True)
def _scans_go_to_a_tmp_file(tmp_path, monkeypatch):
    """The publish tests below write scan records; none of them may reach the
    working tree's `data/scans.jsonl`, which /map/data reads."""
    monkeypatch.setenv("FRONTDOOR_SCANS", str(tmp_path / "scans.jsonl"))


@pytest.fixture
def store_path(tmp_path, monkeypatch):
    path = tmp_path / "assessments.jsonl"
    monkeypatch.setenv(ASSESSMENTS_ENV, str(path))
    return path


def make_client(engine, store=None):
    app = create_app()
    app.config[ENGINE_KEY] = engine
    if store is not None:
        app.config[STORE_KEY] = store
    return app.test_client()


def post_screen(client, data):
    return client.post(
        "/screen",
        data={"images": [(io.BytesIO(data), "view.jpg", "image/jpeg")]},
        content_type="multipart/form-data",
    )


def post_publish(client, data, form=None):
    payload = {"images": [(io.BytesIO(data), "view.jpg", "image/jpeg")]}
    payload.update(form or PLACE_FORM)
    return client.post("/screen/publish", data=payload,
                       content_type="multipart/form-data")


# --- the key: (image sha256, engine version) ---------------------------------


def test_the_image_half_of_the_key_is_the_sha256_of_the_bytes():
    digest, per_image = content_digest([b"one"])
    assert per_image == [hashlib.sha256(b"one").hexdigest()]
    assert digest == hashlib.sha256(
        hashlib.sha256(b"one").hexdigest().encode("ascii")
    ).hexdigest()


def test_different_bytes_are_a_different_key():
    """A different photograph of the same entrance is still assessed (AC5)."""
    assert content_digest([b"one"])[0] != content_digest([b"two"])[0]


def test_the_key_covers_every_view_and_their_order():
    """The key must be a function of what the model was SENT, which is an
    ordered list of views, not one image."""
    assert content_digest([b"a", b"b"])[0] != content_digest([b"a"])[0]
    assert content_digest([b"a", b"b"])[0] != content_digest([b"b", b"a"])[0]


def test_the_engine_version_carries_the_model_id():
    version = engine_version("claude-sonnet-5")
    assert version.startswith("claude-sonnet-5")
    assert engine_version("some-other-model") != version


def test_the_prompt_digest_is_the_hash_of_the_reviewable_prompt_file():
    """Makes the substitution in the next test a statement about the real file.

    Without this, `_read_prompt_bytes` could return anything at all and the
    prompt-invalidation test would only prove that a seam moves the key.
    """
    on_disk = (REPO_ROOT / "src" / "frontdoor" / PROMPT_RESOURCE).read_bytes()
    assert prompt_digest() == hashlib.sha256(on_disk).hexdigest()


def test_editing_the_prompt_file_moves_the_key(monkeypatch, store_path):
    """AC4: a stale assessment cannot outlive the engine that produced it.

    Nobody bumps a number. The prompt file's own hash is half the engine
    version, so an edit invalidates every entry the old prompt produced --
    which is the whole reason the engine is in the key at all. A cache on the
    image alone would keep serving a retired prompt's answers and nothing would
    report it.
    """
    original = assessment_store._read_prompt_bytes()
    engine = SamplingEngine()

    first = recall_or_assess(engine, [b"photo"], path=store_path)
    assert engine.call_count == 1
    assert recall_or_assess(engine, [b"photo"], path=store_path).served_from_store
    assert engine.call_count == 1

    edited = json.loads(original)
    edited["system"] = edited["system"] + " Answer with particular care."
    monkeypatch.setattr(
        assessment_store, "_read_prompt_bytes",
        lambda: json.dumps(edited).encode("utf-8"),
    )

    after = recall_or_assess(engine, [b"photo"], path=store_path)
    assert after.engine_version != first.engine_version
    assert after.served_from_store is False
    assert engine.call_count == 2, "the retired prompt's answer was served"

    # The old entry is history, not a casualty: it is still in the store, and
    # it comes back the moment the old engine version does.
    assert len(load_assessment_store(store_path).records) == 2
    monkeypatch.setattr(assessment_store, "_read_prompt_bytes", lambda: original)
    assert recall_or_assess(engine, [b"photo"], path=store_path).served_from_store


def test_changing_the_model_moves_the_key(store_path):
    old = SamplingEngine(model="claude-sonnet-5")
    recall_or_assess(old, [b"photo"], path=store_path)
    new = SamplingEngine(model="claude-opus-9")
    assert recall_or_assess(new, [b"photo"], path=store_path).served_from_store is False
    assert new.call_count == 1


# --- the guarantee -----------------------------------------------------------


def test_the_same_photograph_returns_the_identical_assessment(store_path):
    """AC1, against a model that would otherwise answer differently."""
    engine = SamplingEngine()
    first = recall_or_assess(engine, [b"photo"], path=store_path)
    second = recall_or_assess(engine, [b"photo"], path=store_path)
    assert first.assessment.criteria == second.assessment.criteria
    assert second.assessment.criteria["ramp_or_bevel"]["verdict"] == "present"
    # Proof the fake really would have changed its mind.
    other = recall_or_assess(engine, [b"different photo"], path=store_path)
    assert other.assessment.criteria["ramp_or_bevel"]["verdict"] == "absent"


def test_the_second_submission_makes_no_model_call(store_path):
    """AC2, as a call count rather than as a matching verdict."""
    engine = SamplingEngine()
    recall_or_assess(engine, [b"photo"], path=store_path)
    assert engine.call_count == 1
    for _ in range(5):
        recall_or_assess(engine, [b"photo"], path=store_path)
    assert engine.call_count == 1


def test_a_stored_answer_is_distinguishable_from_a_fresh_one(store_path):
    """AC3. Presenting a recalled result as a fresh one is the same defect
    class as scoring a rejected response as an abstention (#399)."""
    engine = SamplingEngine()
    stamps = iter(["2026-01-01T00:00:00Z", "2026-06-30T12:00:00Z"])
    first = recall_or_assess(engine, [b"photo"], path=store_path,
                             now=lambda: next(stamps))
    assert first.served_from_store is False
    assert first.assessed_at == "2026-01-01T00:00:00Z"

    second = recall_or_assess(engine, [b"photo"], path=store_path,
                              now=lambda: next(stamps))
    assert second.served_from_store is True
    assert second.assessed_at == "2026-01-01T00:00:00Z", (
        "a stored answer must carry the timestamp it was ORIGINALLY produced"
    )
    assert second.provenance() == {
        "image_sha256": first.image_sha256,
        "engine_version": first.engine_version,
        "assessed_at": "2026-01-01T00:00:00Z",
        "served_from_store": True,
    }
    # The durable half a persisted record keeps says nothing about which
    # request served it.
    assert "served_from_store" not in second.reference()


def test_a_key_with_two_lines_still_answers_with_the_first(store_path):
    """Not the concurrency case -- that is the two-thread test below. This is
    the reader: if a key ever has two lines, every read picks the same one, so
    an answer cannot change after it has been stored."""
    engine = SamplingEngine()
    first = recall_or_assess(engine, [b"photo"], path=store_path)
    duplicate = new_assessment_record(
        image_sha256=first.image_sha256,
        image_digests=[image_digest(b"photo")],
        engine_version=first.engine_version,
        model=engine.config.model,
        prompt_sha256=prompt_digest(),
        assessed_at="2030-01-01T00:00:00Z",
        assessment=assessment_with("absent"),
    )
    assessment_store._append_jsonl(store_path, duplicate)

    served = recall_or_assess(engine, [b"photo"], path=store_path)
    assert served.assessed_at == first.assessed_at
    assert served.assessment.criteria["ramp_or_bevel"]["verdict"] == "present"


def test_two_requests_racing_on_one_photograph_get_the_same_answer(store_path):
    """The window the store could not close by reading alone.

    Two requests for one photograph arriving TOGETHER both miss, and without a
    lock both call the model and both return their OWN sample. First-wins on
    the read does not save them: the two answers have already been handed out,
    and if one was a publish, its scan record durably carries verdicts the
    store will never serve again. The deployed server is one worker with two
    threads and the app posts /screen then /screen/publish with the same
    frames, so this is reachable rather than theoretical.

    The engine here BLOCKS inside the call until both threads have entered
    recall_or_assess, so the race is forced rather than hoped for.
    """
    entered = threading.Barrier(2, timeout=10)

    class RacingEngine(SamplingEngine):
        def assess_images_integrated(self, images, *, media_types=None):
            # Only the thread that wins the lock reaches here; hold it long
            # enough that the loser is definitely waiting.
            time.sleep(0.2)
            return super().assess_images_integrated(images, media_types=media_types)

    engine = RacingEngine()
    results = []
    lock = threading.Lock()

    def submit():
        entered.wait()
        recall = recall_or_assess(engine, [b"photo"], path=store_path)
        with lock:
            results.append(recall)

    threads = [threading.Thread(target=submit) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len(results) == 2
    assert engine.call_count == 1, "the same photograph was assessed twice"
    assert results[0].assessment.criteria == results[1].assessment.criteria
    assert results[0].assessed_at == results[1].assessed_at
    assert sorted(recall.served_from_store for recall in results) == [False, True]
    assert len(load_assessment_store(store_path).records) == 1


def test_the_key_lock_table_does_not_grow_with_every_photograph(store_path):
    """A lock per key, dropped when the last waiter leaves. A dict that kept
    one entry per image ever seen would be a slow leak in a long-lived worker."""
    engine = SamplingEngine()
    for index in range(5):
        recall_or_assess(engine, [f"photo-{index}".encode()], path=store_path)
    assert assessment_store._key_locks == {}


def test_two_different_photographs_do_not_wait_on_each_other(store_path):
    """The lock is per key, so a slow assessment of one door cannot serialize
    the queue behind an unrelated one."""
    engine = SamplingEngine()
    with assessment_store._assessing("some-other-key"):
        recall = recall_or_assess(engine, [b"photo"], path=store_path)
    assert recall.served_from_store is False
    assert engine.call_count == 1


def test_a_record_that_cannot_say_when_it_was_assessed_is_not_served(store_path):
    """A stored answer with a null timestamp is the defect wearing the fix's
    clothes: `served_from_store: true` with nothing saying when, and that null
    written into a durable scan record."""
    engine = SamplingEngine()
    assessment_store._append_jsonl(store_path, new_assessment_record(
        image_sha256=content_digest([b"photo"])[0],
        image_digests=[image_digest(b"photo")],
        engine_version=engine_version(engine.config.model),
        model=engine.config.model,
        prompt_sha256=prompt_digest(),
        assessed_at=None,
        assessment=assessment_with("absent"),
    ))
    recall = recall_or_assess(engine, [b"photo"], path=store_path)
    assert recall.served_from_store is False
    assert recall.assessed_at is not None
    # And the good line written behind it is what every later request gets.
    later = recall_or_assess(engine, [b"photo"], path=store_path)
    assert later.served_from_store is True
    assert later.assessed_at == recall.assessed_at


# --- what is never frozen ----------------------------------------------------


#: Assessments that produce NO public verdict: both endpoints answer 502 on
#: each of these, so nothing public came of the call.
NOTHING_PUBLIC = [
    (ImageAssessment(criteria=None, latency_s=0.5, error="boom",
                     failure=FAILURE_REFUSED), "a refusal"),
    (ImageAssessment(criteria=None, latency_s=0.5, error="truncated",
                     failure=FAILURE_TRUNCATED), "a truncation"),
    (ImageAssessment(criteria={key: {"verdict": None} for key in CRITERIA_KEYS},
                     latency_s=0.5, ada_checks=ok_ada_checks()),
     "a criteria dict whose every field was refused"),
    (ImageAssessment(criteria={"ramp_or_bevel": {"verdict": "present"}},
                     latency_s=0.5, ada_checks=None),
     "ADA checks the validator threw away"),
]

#: Assessments both endpoints DO publish. Each of these is a verdict a
#: contributor is shown, so each must be keyed.
PUBLISHED_ANYWAY = [
    (assessment_with("present"), "a clean answer"),
    (assessment_with("present", failure=FAILURE_REJECTED, error="rejected",
                     rejected_attempts=1),
     "a rejected reply whose other criteria were recovered (TICK-399)"),
    (assessment_with("not_visible", face_check="unknown"),
     "a quarantined request, whose verdicts /screen still returns"),
]


@pytest.mark.parametrize("assessment, why", NOTHING_PUBLIC,
                         ids=lambda value: str(value)[:40])
def test_a_call_that_produced_no_public_verdict_is_never_stored(
        assessment, why, store_path):
    """Storing one would serve a permanent 502 for that photograph, and
    re-asking costs nothing public because nothing public came of it."""
    assert not is_storable(assessment), why
    engine = SamplingEngine(assessments=[assessment, assessment_with("absent")])
    recall_or_assess(engine, [b"photo"], path=store_path)
    assert load_assessment_store(store_path).records == []
    assert recall_or_assess(engine, [b"photo"], path=store_path).served_from_store is False
    assert engine.call_count == 2, "a failure was served back instead of re-asked"


@pytest.mark.parametrize("assessment, why", PUBLISHED_ANYWAY,
                         ids=lambda value: str(value)[:40])
def test_anything_the_endpoints_publish_is_keyed(assessment, why, store_path):
    """The defect the first draft of this store had.

    `is_storable` required `failure is None`, while /screen/publish's gate is
    only "criteria and at least one verdict". A reply whose `handrails` verdict
    came back in the ADA vocabulary is field-recovered and carries
    FAILURE_REJECTED WITH criteria -- a normal TICK-399 outcome. Both endpoints
    publish it; the store refused to keep it; so the same photograph was
    re-sampled on every submission and could give two different PUBLIC
    verdicts. Anything good enough to show a contributor is good enough to key.
    """
    assert is_storable(assessment), why
    engine = SamplingEngine(assessments=[assessment, assessment_with("absent")])
    first = recall_or_assess(engine, [b"photo"], path=store_path)
    second = recall_or_assess(engine, [b"photo"], path=store_path)
    assert second.served_from_store is True
    assert engine.call_count == 1
    assert second.assessment.criteria == first.assessment.criteria


def test_a_recalled_rejected_reply_still_says_it_was_rejected(store_path):
    """Keying it must not launder it. TICK-399's distinction survives the
    round trip: a criterion thrown away by validation is still reported as
    thrown away, never as the model having looked and abstained."""
    rejected = assessment_with("present", failure=FAILURE_REJECTED,
                               error="ResponseRejected: handrails",
                               rejected_attempts=1)
    engine = SamplingEngine(assessments=[rejected])
    recall_or_assess(engine, [b"photo"], path=store_path)
    served = recall_or_assess(engine, [b"photo"], path=store_path).assessment
    assert served.failure == FAILURE_REJECTED
    assert served.rejected_attempts == 1
    assert served.error == "ResponseRejected: handrails"


def test_a_not_visible_verdict_survives_the_round_trip(store_path):
    """not_visible is never absent (the honesty rule), including through the
    store: a recalled abstention must come back as one."""
    engine = SamplingEngine(assessments=[assessment_with("not_visible")])
    recall_or_assess(engine, [b"photo"], path=store_path)
    served = recall_or_assess(engine, [b"photo"], path=store_path).assessment
    assert {entry["verdict"] for entry in served.criteria.values()} == {"not_visible"}


def test_the_store_keeps_exactly_what_the_endpoint_publishes(store_path):
    """The invariant behind both parametrized tests above, stated once.

    `is_storable` and the endpoints' success gate must agree case by case. If
    the store is ever made stricter than the gate, the assessments in the gap
    are published and re-sampled -- which is the defect. If it is ever made
    looser, a 502 becomes permanent for that photograph.
    """
    for assessment, why in NOTHING_PUBLIC + PUBLISHED_ANYWAY:
        engine = SamplingEngine(assessments=[assessment])
        client = make_client(engine, store=FakeStore())
        answered = post_screen(client, real_jpeg()).status_code == 200
        assert answered is is_storable(assessment), why


def test_a_hand_corrupted_record_is_a_miss_not_a_crash(store_path):
    engine = SamplingEngine()
    assessment_store._append_jsonl(store_path, {
        "image_sha256": content_digest([b"photo"])[0],
        "engine_version": engine_version(engine.config.model),
        "assessed_at": "2026-01-01T00:00:00Z",
        "assessment": {"criteria": "not a dict"},
    })
    recall = recall_or_assess(engine, [b"photo"], path=store_path)
    assert recall.served_from_store is False
    assert engine.call_count == 1


def test_an_unreadable_record_is_skipped_rather_than_re_found_forever(store_path):
    """The one that would have made a corrupt line cost a model call a request.

    An unreadable record matching the key is passed over, so the good record
    written behind it wins. Returning it and falling through to a fresh
    assessment would find the same bad line first every time: re-assess,
    append, re-assess, forever, behind a record that is never served.
    """
    engine = SamplingEngine()
    assessment_store._append_jsonl(store_path, {
        "image_sha256": content_digest([b"photo"])[0],
        "engine_version": engine_version(engine.config.model),
        "assessed_at": "2026-01-01T00:00:00Z",
        "assessment": {"criteria": "not a dict"},
    })
    recall_or_assess(engine, [b"photo"], path=store_path)
    assert engine.call_count == 1
    for _ in range(3):
        assert recall_or_assess(engine, [b"photo"], path=store_path).served_from_store
    assert engine.call_count == 1
    assert len(load_assessment_store(store_path).records) == 2


def test_an_unreadable_store_fails_open_to_a_fresh_assessment(tmp_path):
    """A missing volume must not take /screen down; it only costs determinism."""
    missing = tmp_path / "no-such-directory" / "assessments.jsonl"
    engine = SamplingEngine()
    recall = recall_or_assess(engine, [b"photo"], path=missing)
    assert recall.served_from_store is False
    assert recall.assessment.criteria is not None
    assert engine.call_count == 1


def test_the_store_holds_no_image_bytes(store_path):
    engine = SamplingEngine()
    recall_or_assess(engine, [b"the-photograph-bytes"], path=store_path)
    text = store_path.read_text(encoding="utf-8")
    assert "the-photograph-bytes" not in text
    record = json.loads(text.strip())
    assert record["image_sha256"] == content_digest([b"the-photograph-bytes"])[0]
    assert record["image_digests"] == [image_digest(b"the-photograph-bytes")]


# --- it is the scan store's append discipline, not a second one ---------------


def test_the_append_and_read_are_the_scan_stores_own_functions():
    """Reused rather than re-implemented, exactly as `corrections` reuses them,
    so the torn-line recovery cannot drift into a second copy."""
    from frontdoor import scan_records

    assert assessment_store._append_jsonl is scan_records.append_scan
    assert assessment_store._load_jsonl is scan_records.load_scan_store


def test_a_torn_last_line_is_recovered_rather_than_wedging_the_store(store_path):
    engine = SamplingEngine()
    recall_or_assess(engine, [b"photo"], path=store_path)
    with open(store_path, "a", encoding="utf-8", newline="") as handle:
        handle.write('{"image_sha256": "torn')  # an interrupted write

    recall_or_assess(engine, [b"other"], path=store_path)
    assert store_path.read_bytes().endswith(b"\n")
    assert len(load_assessment_store(store_path).records) == 2
    assert recall_or_assess(engine, [b"photo"], path=store_path).served_from_store


def test_an_unreadable_store_names_the_right_file(tmp_path):
    load = load_assessment_store(tmp_path / "gone" / "assessments.jsonl")
    assert "assessments unreadable" in load.error
    assert "scans" not in load.error


# --- the endpoints -----------------------------------------------------------


def test_screen_serves_the_stored_verdicts_and_makes_one_model_call(store_path):
    """AC1 and AC2 through the endpoint the phone actually posts to."""
    engine = SamplingEngine()
    client = make_client(engine)
    photo = real_jpeg()

    first = post_screen(client, photo).get_json()
    second = post_screen(client, photo).get_json()

    assert first["assessment"]["criteria"] == second["assessment"]["criteria"]
    assert engine.call_count == 1
    assert first["assessment"]["served_from_store"] is False
    assert second["assessment"]["served_from_store"] is True
    assert (second["assessment"]["assessed_at"]
            == first["assessment"]["assessed_at"])
    assert second["assessment"]["image_sha256"] == first["assessment"]["image_sha256"]
    assert second["assessment"]["engine_version"].startswith(engine.config.model)


def test_screen_still_assesses_a_different_photograph(store_path):
    """AC5: a re-scan with new evidence is not a miss to be avoided."""
    engine = SamplingEngine()
    client = make_client(engine)
    post_screen(client, real_jpeg(shade=40))
    body = post_screen(client, real_jpeg(shade=200)).get_json()
    assert engine.call_count == 2
    assert body["assessment"]["served_from_store"] is False


def test_the_key_is_the_processed_bytes_not_the_upload(store_path, monkeypatch):
    """Two different uploads that the privacy pass reduces to the SAME bytes
    are one photograph. The thing keyed must be the thing the model saw."""
    from frontdoor.faceblur import ProcessedImage
    from frontdoor_server import screen_view

    processed = real_jpeg(shade=99)
    monkeypatch.setattr(
        screen_view, "process_upload",
        lambda raw: ProcessedImage(processed, face_count=0, gps_stripped=True),
    )
    engine = SamplingEngine()
    client = make_client(engine)
    post_screen(client, b"upload-one-raw-bytes")
    body = post_screen(client, b"upload-two-quite-different-raw-bytes").get_json()

    assert engine.call_count == 1
    assert body["assessment"]["served_from_store"] is True
    assert body["assessment"]["image_sha256"] == content_digest([processed])[0]
    stored = json.loads(store_path.read_text(encoding="utf-8").strip())
    assert stored["image_digests"] == [image_digest(processed)]


def test_publish_and_a_live_recheck_of_the_same_photograph_agree(store_path):
    """The one they must never disagree on: a published record and the
    /screen answer a person gets when they re-check the same door."""
    engine = SamplingEngine()
    client = make_client(engine, store=FakeStore())
    photo = real_jpeg()

    published = post_publish(client, photo).get_json()
    assert published["published"] is True
    rechecked = post_screen(client, photo).get_json()

    assert engine.call_count == 1
    assert published["assessment"]["criteria"] == rechecked["assessment"]["criteria"]
    assert rechecked["assessment"]["served_from_store"] is True


def test_screen_first_then_publish_also_agrees_and_calls_once(store_path):
    engine = SamplingEngine()
    client = make_client(engine, store=FakeStore())
    photo = real_jpeg()

    screened = post_screen(client, photo).get_json()
    published = post_publish(client, photo).get_json()

    assert engine.call_count == 1
    assert published["assessment"]["criteria"] == screened["assessment"]["criteria"]
    assert published["assessment"]["served_from_store"] is True


def test_the_published_record_names_the_assessment_it_carries(store_path, tmp_path):
    scans = tmp_path / "scans.jsonl"
    engine = SamplingEngine()
    client = make_client(engine, store=FakeStore())
    body = post_publish(client, real_jpeg()).get_json()

    record = load_scan_records(scans)[0]
    assert record["assessment_ref"] == {
        "image_sha256": body["assessment"]["image_sha256"],
        "engine_version": body["assessment"]["engine_version"],
        "assessed_at": body["assessment"]["assessed_at"],
    }
    # created_at is when it was PUBLISHED; assessed_at is when the verdicts
    # were produced. A publish of an answer from earlier says so.
    assert "created_at" in record
    assert "served_from_store" not in record["assessment_ref"]


def test_a_failed_screen_is_not_cached_into_the_publish_path(store_path):
    engine = SamplingEngine(assessments=[
        ImageAssessment(criteria=None, latency_s=0.2, error="boom",
                        failure=FAILURE_REFUSED),
        assessment_with("present"),
    ])
    client = make_client(engine, store=FakeStore())
    photo = real_jpeg()
    assert post_screen(client, photo).status_code == 502
    assert post_publish(client, photo).get_json()["published"] is True
    assert engine.call_count == 2


# --- it survives a deploy ----------------------------------------------------


def test_the_store_path_comes_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.delenv(ASSESSMENTS_ENV, raising=False)
    assert assessments_path() == DEFAULT_ASSESSMENTS_PATH
    monkeypatch.setenv(ASSESSMENTS_ENV, str(tmp_path / "elsewhere.jsonl"))
    assert assessments_path() == str(tmp_path / "elsewhere.jsonl")


def test_the_image_points_the_store_at_the_mounted_volume():
    """AC6. `test_image_ships_its_data` parametrizes the same property over
    every runtime store; this is it named for the ticket that needs it, because
    an ephemeral path here loses no record -- it loses the guarantee, and the
    only symptom is a number changing quietly between two releases.
    """
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert f"ENV {ASSESSMENTS_ENV}=/data/" in dockerfile
    assert "[mounts]" in (REPO_ROOT / "fly.toml").read_text(encoding="utf-8")


def test_the_operator_documentation_describes_the_store():
    docs = (REPO_ROOT / "docs" / "server-deploy.md").read_text(encoding="utf-8")
    assert ASSESSMENTS_ENV in docs
    assert "/data/assessments.jsonl" in docs
