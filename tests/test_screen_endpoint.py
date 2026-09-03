"""Contract tests for POST /screen (TICK-245).

Fully mocked: every test injects a fake engine via app.config, so no test
constructs an anthropic client or needs an API key.
"""

import io

import pytest

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
    """Stands in for ScreeningEngine as the view uses it: .config, .assess_image."""

    def __init__(self, assessments=None, raises=None):
        self._assessments = None if assessments is None else list(assessments)
        self._raises = raises
        self.config = ScreeningConfig()
        self.calls = []

    def assess_image(self, image, *, media_type="image/jpeg"):
        self.calls.append((image, media_type))
        if self._raises is not None:
            raise self._raises
        if self._assessments is not None:
            return self._assessments.pop(0)
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


def test_single_image_returns_per_criterion_verdicts():
    engine = FakeEngine()
    response = post_screen(make_client(engine), [image_part()])
    assert response.status_code == 200
    body = response.get_json()
    assert len(body["images"]) == 1
    image = body["images"][0]
    assert image["error"] is None
    assert image["latency_ms"] == 1234
    for key in CRITERIA_KEYS:
        entry = image["criteria"][key]
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


def test_multi_image_aggregates_majority_and_flip_rate():
    engine = FakeEngine(
        assessments=[
            ok_assessment("present"),
            ok_assessment("present"),
            ok_assessment("not_visible"),
        ]
    )
    parts = [image_part(f"v{i}.jpg") for i in range(3)]
    body = post_screen(make_client(engine), parts).get_json()
    assert len(body["images"]) == 3
    for key in CRITERIA_KEYS:
        summary = body["aggregate"][key]
        assert summary["verdict"] == "present"
        assert summary["flip_rate"] == pytest.approx(1 / 3)
        assert summary["counts"] == {"present": 2, "not_visible": 1}


def test_engine_receives_bytes_and_the_declared_media_type():
    engine = FakeEngine()
    parts = [
        image_part("a.jpg", "image/jpeg", b"jpeg-bytes"),
        image_part("b.png", "image/png", b"png-bytes"),
        image_part("c.webp", "image/webp", b"webp-bytes"),
    ]
    post_screen(make_client(engine), parts)
    assert engine.calls == [
        (b"jpeg-bytes", "image/jpeg"),
        (b"png-bytes", "image/png"),
        (b"webp-bytes", "image/webp"),
    ]


def test_valid_entrance_id_is_echoed_in_canonical_form():
    body = post_screen(
        make_client(FakeEngine()), [image_part()], entrance_id=" e-001 "
    ).get_json()
    assert body["entrance_id"] == DEV_ID


def test_a_partially_failed_batch_still_returns_200_with_the_error_recorded():
    engine = FakeEngine(assessments=[ok_assessment(), errored_assessment("boom")])
    parts = [image_part("a.jpg"), image_part("b.jpg")]
    response = post_screen(make_client(engine), parts)
    assert response.status_code == 200
    images = response.get_json()["images"]
    assert images[0]["error"] is None
    assert images[1]["error"] == "boom"
    assert images[1]["criteria"] is None


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


def test_all_assessments_failing_returns_502_naming_the_failures():
    engine = FakeEngine(
        assessments=[errored_assessment("refused"), errored_assessment("no JSON")]
    )
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
