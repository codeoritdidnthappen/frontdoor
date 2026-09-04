"""Contract tests for POST /screen (TICK-245).

Fully mocked: every test injects a fake engine via app.config, so no test
constructs an anthropic client or needs an API key.
"""

import io

from frontdoor.screening import CRITERIA_KEYS, ImageAssessment, ScreeningConfig
from frontdoor_server.app import create_app
from frontdoor_server.screen_view import ENGINE_KEY, MAX_IMAGES, WORDING

# Known assignments under the committed seed (pinned in test_split.py):
DEV_ID = "E-001"
SEALED_ID = "E-014"


def ok_assessment(verdict="present"):
    return ImageAssessment(
        criteria={
            key: {"verdict": verdict, "confidence": 80, "evidence": f"{key} seen"}
            for key in CRITERIA_KEYS
        },
        latency_s=1.234,
    )


def errored_assessment(error="ScreeningError: no JSON object in response"):
    return ImageAssessment(criteria=None, latency_s=0.5, error=error)


class FakeEngine:
    """Stands in for ScreeningEngine as the view uses it: .config and
    .assess_images_integrated.

    One request is one integrated engine call over ALL the views, so the fake
    records each call as (images tuple, media_types tuple) and returns a single
    integrated assessment.
    """

    def __init__(self, assessment=None, raises=None):
        self._assessment = assessment
        self._raises = raises
        self.config = ScreeningConfig()
        self.calls = []

    def assess_images_integrated(self, images, *, media_types=None):
        self.calls.append((tuple(images), tuple(media_types or ())))
        if self._raises is not None:
            raise self._raises
        if self._assessment is not None:
            return self._assessment
        return ok_assessment()


def make_client(engine):
    app = create_app()
    app.config[ENGINE_KEY] = engine
    return app.test_client()


def image_part(name="view.jpg", content_type="image/jpeg", data=b"fake-image-bytes"):
    return (io.BytesIO(data), name, content_type)


def post_screen(client, parts, entrance_id=None):
    data = {"images": parts}
    if entrance_id is not None:
        data["entrance_id"] = entrance_id
    return client.post("/screen", data=data, content_type="multipart/form-data")


# --- happy paths -------------------------------------------------------------


def test_single_image_returns_the_integrated_per_criterion_verdicts():
    engine = FakeEngine()
    response = post_screen(make_client(engine), [image_part()])
    assert response.status_code == 200
    body = response.get_json()
    assert body["images"] == [{"filename": "view.jpg"}]
    assessment = body["assessment"]
    assert assessment["error"] is None
    assert assessment["latency_ms"] == 1234
    for key in CRITERIA_KEYS:
        entry = assessment["criteria"][key]
        assert entry["verdict"] == "present"
        assert entry["confidence"] == 80
        assert entry["evidence"]


def test_single_image_carries_status_model_latency_and_wording():
    engine = FakeEngine()
    body = post_screen(make_client(engine), [image_part()]).get_json()
    assert body["status"] == "ai_estimated"
    assert body["model"] == ScreeningConfig().model
    assert isinstance(body["latency_ms"], int)
    wording = body["wording"].lower()
    assert "visible" in wording
    assert "not measurements" in wording
    assert "not compliance" in wording


def test_wording_never_claims_measurement_or_compliance():
    body = post_screen(make_client(FakeEngine()), [image_part()]).get_json()
    # The field states observations only; measurement and compliance appear
    # solely inside explicit negations.
    wording = body["wording"].lower()
    for banned in ("measurement", "compliance"):
        index = wording.find(banned)
        assert index != -1 and "not" in wording[max(0, index - 30) : index]


def test_single_image_has_no_aggregate():
    body = post_screen(make_client(FakeEngine()), [image_part()]).get_json()
    assert "aggregate" not in body


def test_multi_image_gets_one_integrated_assessment_and_aggregate():
    """N views are ONE engine call now, and the aggregate carries the
    integrated verdicts with flip_rate and counts null - no cross-view
    comparison was made, so there is no flip rate to report, and a fabricated
    0.0 would read as "all views agreed"."""
    engine = FakeEngine(assessment=ok_assessment("present"))
    parts = [image_part(f"v{i}.jpg", data=f"v{i}".encode()) for i in range(3)]
    body = post_screen(make_client(engine), parts).get_json()
    assert len(engine.calls) == 1
    assert [img["filename"] for img in body["images"]] == [
        "v0.jpg", "v1.jpg", "v2.jpg",
    ]
    for key in CRITERIA_KEYS:
        assert body["assessment"]["criteria"][key]["verdict"] == "present"
        summary = body["aggregate"][key]
        assert summary["verdict"] == "present"
        assert summary["flip_rate"] is None
        assert summary["counts"] is None


def test_response_declares_integrated_mode():
    """A consumer must be able to tell "the views agreed" from "no cross-view
    comparison was made"; the response says which mode produced it."""
    body = post_screen(make_client(FakeEngine()), [image_part()]).get_json()
    assert body["mode"] == "integrated"
    parts = [image_part(f"v{i}.jpg", data=f"v{i}".encode()) for i in range(3)]
    body = post_screen(make_client(FakeEngine()), parts).get_json()
    assert body["mode"] == "integrated"


def test_engine_receives_all_bytes_and_media_types_in_one_call_in_order():
    engine = FakeEngine()
    parts = [
        image_part("a.jpg", "image/jpeg", b"jpeg-bytes"),
        image_part("b.png", "image/png", b"png-bytes"),
        image_part("c.webp", "image/webp", b"webp-bytes"),
    ]
    post_screen(make_client(engine), parts)
    assert engine.calls == [
        (
            (b"jpeg-bytes", b"png-bytes", b"webp-bytes"),
            ("image/jpeg", "image/png", "image/webp"),
        )
    ]


def test_valid_entrance_id_is_echoed_in_canonical_form():
    body = post_screen(
        make_client(FakeEngine()), [image_part()], entrance_id=" e-001 "
    ).get_json()
    assert body["entrance_id"] == DEV_ID


# --- error contract ----------------------------------------------------------


def assert_error_shape(response, status, token):
    assert response.status_code == status
    assert response.headers["Content-Type"].startswith("application/json")
    body = response.get_json()
    assert body["error"] == token
    assert body["detail"].strip()
    return body


def test_no_file_returns_400():
    engine = FakeEngine()
    client = make_client(engine)
    response = client.post("/screen", data={}, content_type="multipart/form-data")
    assert_error_shape(response, 400, "missing image")
    assert engine.calls == []


def test_too_many_images_returns_400():
    engine = FakeEngine()
    parts = [image_part(f"v{i}.jpg") for i in range(MAX_IMAGES + 1)]
    response = post_screen(make_client(engine), parts)
    assert_error_shape(response, 400, "too many images")
    assert engine.calls == []


def test_unsupported_file_type_returns_415():
    engine = FakeEngine()
    parts = [image_part(), image_part("notes.txt", "text/plain")]
    response = post_screen(make_client(engine), parts)
    body = assert_error_shape(response, 415, "unsupported content type")
    assert "text/plain" in body["detail"]
    assert engine.calls == []


def test_invalid_entrance_id_returns_400():
    engine = FakeEngine()
    response = post_screen(make_client(engine), [image_part()], entrance_id="lobby-3")
    body = assert_error_shape(response, 400, "invalid entrance_id")
    assert "E-" in body["detail"]
    assert engine.calls == []


def test_sealed_entrance_returns_403_before_any_engine_call():
    engine = FakeEngine()
    response = post_screen(make_client(engine), [image_part()], entrance_id=SEALED_ID)
    body = assert_error_shape(response, 403, "sealed entrance")
    assert SEALED_ID in body["detail"]
    assert "results freeze" in body["detail"]
    assert engine.calls == []


def test_a_failed_integrated_assessment_returns_502_naming_the_failure():
    """One call for all views means a recorded engine error fails the request
    as a whole - named, never a 200 with silently missing verdicts."""
    engine = FakeEngine(assessment=errored_assessment("model refused the request"))
    response = post_screen(make_client(engine), [image_part("a.jpg"), image_part("b.jpg")])
    body = assert_error_shape(response, 502, "screening engine failure")
    assert "refused" in body["detail"]


def test_an_engine_exception_returns_502_named_not_a_bare_500():
    engine = FakeEngine(raises=RuntimeError("spend cap breached"))
    response = post_screen(make_client(engine), [image_part()])
    body = assert_error_shape(response, 502, "screening engine failure")
    assert "RuntimeError" in body["detail"]
    assert "spend cap breached" in body["detail"]


def test_missing_api_key_returns_503_with_a_clear_message(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    client = create_app().test_client()  # no injected engine
    response = post_screen(client, [image_part()])
    body = assert_error_shape(response, 503, "screening unavailable")
    assert "ANTHROPIC_API_KEY" in body["detail"]


def test_server_boots_and_serves_health_without_an_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    response = create_app().test_client().get("/health")
    assert response.status_code == 200


def test_wrong_method_on_screen_is_json_405():
    """GET used to be the wrong method here; it now serves the demo page, so this asserts
    the same thing against a method that is still wrong.

    What it has always guarded is that a wrong method answers with the JSON error contract
    rather than Werkzeug's HTML page -- the consumer is a client parsing JSON over a venue
    network, and HTML where it expects JSON turns a clear message into a parse failure.
    """
    response = make_client(FakeEngine()).put("/screen")
    assert response.status_code == 405
    assert response.headers["Content-Type"].startswith("application/json")


# --- the laptop demo page (GET /screen) ---------------------------------------------------
#
# The demo surface, chosen over an in-app client because the phone route lands behind a
# signing session with no agreed date (#214) on a build that expires on Demo Day itself.
# These are contract tests on what the page must not do, not a rendering test: the page has
# no logic worth testing in a browser, and the things that would ruin a demo are structural.


def page():
    return create_app().test_client().get("/screen")


def test_the_page_is_served_as_html():
    response = page()
    assert response.status_code == 200
    assert response.mimetype == "text/html"


def test_the_page_is_served_without_an_api_key():
    """The page must render on a laptop that cannot reach the model.

    `create_app()` here has no injected engine and the suite sets no key, so this is the
    keyless case. If serving the page ever required the engine, a missing key would turn
    the demo surface itself into a 503 instead of a page that says why screening failed.
    """
    assert page().status_code == 200


def test_get_and_post_share_the_path():
    """One path, two methods -- so the page posts to itself and there is no second URL to
    get wrong on stage."""
    client = create_app().test_client()
    assert client.get("/screen").status_code == 200
    assert client.post("/screen").status_code == 400


def test_the_page_makes_no_external_requests():
    """D-016's fallback runs this container on a laptop with no working venue network.

    A font, script or stylesheet pulled from a CDN renders blank at exactly the moment
    the fallback exists for. Everything is inline; nothing is fetched but the page's own
    POST back to /screen.
    """
    html = page().get_data(as_text=True)
    for scheme in ("http://", "https://", "//cdn", "//fonts"):
        assert scheme not in html, f"page references an external resource: {scheme}"


def test_the_page_does_not_hardcode_the_honesty_wording():
    """The wording is printed from the response, not copied into the page.

    A second copy in HTML is a copy that drifts: `frontdoor.screening` could tighten the
    disclaimer and the page would keep showing the old one, which is the failure mode the
    honesty rule exists to prevent.
    """
    html = page().get_data(as_text=True)
    assert WORDING not in html
    assert "body.wording" in html


def test_the_page_carries_a_provenance_tag():
    """#73's added AC: every demo moment is tagged live or canned as it is displayed.

    This page can only show a result it just fetched, so the tag is LIVE and there is no
    canned branch that could mislabel a recording as live.
    """
    html = page().get_data(as_text=True)
    assert "LIVE " in html
    # Only in the comment explaining why there is no canned branch -- never in anything
    # the page can render.
    assert html.count("CANNED") == 1


# --- face-blur ingest (TICK-257, #232) ----------------------------------------------------
#
# Every upload passes through frontdoor.faceblur.process_upload before the engine sees it,
# and the response totals the blurred faces. The blur pipeline itself is contract-tested in
# test_faceblur.py; here the wiring is what's under test, so process_upload is mocked the
# same way the engine is.


def real_jpeg(shade=128):
    import cv2
    import numpy as np

    ok, buf = cv2.imencode(
        ".jpg", np.full((32, 32, 3), shade, dtype=np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 95]
    )
    assert ok
    return buf.tobytes()


def test_response_reports_faces_blurred_even_when_zero():
    body = post_screen(make_client(FakeEngine()), [image_part()]).get_json()
    assert body["faces_blurred"] == 0


def test_uploads_are_processed_before_the_engine_sees_them(monkeypatch):
    from frontdoor.faceblur import ProcessedImage
    from frontdoor_server import screen_view

    monkeypatch.setattr(
        screen_view,
        "process_upload",
        lambda raw: ProcessedImage(b"blurred:" + raw, face_count=2, gps_stripped=True),
    )
    engine = FakeEngine()
    parts = [image_part(f"v{i}.jpg", data=f"v{i}".encode()) for i in range(2)]

    body = post_screen(make_client(engine), parts).get_json()

    # The engine only ever saw processed bytes, re-typed as the JPEG they now are...
    assert engine.calls == [
        ((b"blurred:v0", b"blurred:v1"), ("image/jpeg", "image/jpeg")),
    ]
    # ...and the response totals the blurred faces across images.
    assert body["faces_blurred"] == 4


def test_a_real_image_reaches_the_engine_reencoded():
    engine = FakeEngine()
    post_screen(make_client(engine), [image_part(data=real_jpeg())])
    ((sent,), (media_type,)), = engine.calls
    assert media_type == "image/jpeg"
    assert sent[:2] == b"\xff\xd8"
    assert sent != real_jpeg()  # processed, not the raw upload


def test_undecodable_bytes_pass_through_to_the_engine_unchanged():
    # Covered positionally by test_engine_receives_all_bytes_and_media_types_in_one_call
    # too; this states the ingest rule on its own: bytes no decoder accepts hold no
    # renderable face, so they go through untouched for the engine to fail on by name.
    engine = FakeEngine()
    post_screen(make_client(engine), [image_part("a.png", "image/png", b"not-an-image")])
    assert engine.calls == [((b"not-an-image",), ("image/png",))]


# --- one integrated call ------------------------------------------------------------------
#
# The endpoint used to fan a request's views out into one model call each and aggregate by
# majority. Offline eval on the 12-entrance pilot set showed the majority vote amplifying
# shared camera-position blind spots, so the views now go into ONE integrated call -- which
# also replaces N calls' worth of waiting with one against the timed demo budget in
# docs/deck-outline.md.


def test_a_full_batch_of_views_is_exactly_one_engine_call_in_posted_order():
    engine = FakeEngine()
    parts = [image_part(f"v{i}.jpg", data=f"v{i}".encode()) for i in range(MAX_IMAGES)]
    response = post_screen(make_client(engine), parts)
    assert response.status_code == 200
    assert len(engine.calls) == 1
    (images, media_types), = engine.calls
    assert images == tuple(f"v{i}".encode() for i in range(MAX_IMAGES))
    assert len(media_types) == MAX_IMAGES
