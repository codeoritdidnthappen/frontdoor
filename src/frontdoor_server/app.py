"""POST /measure and GET /health (TICK-060).

A thin entrypoint over the core metrology library (ARCHITECTURE.md section 3): it holds no state
and owns no metrology. Every value it returns here is a fixed placeholder; TICK-061 replaces the
stub with a real call behind this identical contract, and the tests written for this module run
unchanged against it.
"""

import json
from importlib import resources

from flask import Flask, Response, jsonify, request
from jsonschema import Draft202012Validator, ValidationError
from werkzeug.exceptions import HTTPException

from frontdoor.metrology import ARM_NAMES
from frontdoor.sidecar import validate_sidecar
from frontdoor_server.map_view import map_page
from frontdoor_server.label_view import register_labels
from frontdoor_server.scan_view import scan_page
from frontdoor_server.screen_view import screen_page
from frontdoor_server.upload_view import register_upload

RESPONSE_SCHEMA = json.loads(
    resources.files("frontdoor_server")
    .joinpath("measure_response.schema.json")
    .read_text(encoding="utf-8")
)

_response_validator = Draft202012Validator(RESPONSE_SCHEMA)

ERROR_SCHEMA = json.loads(
    resources.files("frontdoor_server")
    .joinpath("measure_error.schema.json")
    .read_text(encoding="utf-8")
)

# HTTP statuses /measure uses today, each tied to a class of failure (TICK-224).
# The 422 supersedes TICK-060 AC4, which specified 400 for a schema-invalid sidecar.
# 404 / 405 / 413 / 500 are specified in measure_error.schema.json for TICK-225.
ERROR_STATUSES = {
    400: "malformed request: missing image, missing sidecar, or sidecar is not JSON",
    422: "sidecar is JSON but fails the capture sidecar schema",
}

DETAIL_MAX_LENGTH = 256
_DETAIL_ELLIPSIS = "..."


def _bounded_detail(detail):
    """Clip detail so a rejected sidecar cannot produce an unbounded response."""
    text = detail if isinstance(detail, str) else str(detail)
    if len(text) <= DETAIL_MAX_LENGTH:
        return text
    return text[: DETAIL_MAX_LENGTH - len(_DETAIL_ELLIPSIS)] + _DETAIL_ELLIPSIS


#: Messages for statuses raised before any view runs. Werkzeug's own text is fine for a browser
#: and useless to a client that needs to tell an operator what to do next.
#: Ceiling for a whole request. A full-resolution still plus its depth map and sidecar is a few
#: tens of megabytes; 64 MB leaves room without letting a runaway upload exhaust a free-tier host.
MAX_REQUEST_BYTES = 64 * 1024 * 1024

_HTTP_ERROR_MESSAGES = {
    404: "no such endpoint",
    405: "wrong method for this endpoint",
    413: "request body too large",
    415: "unsupported content type",
    500: "internal error",
}


def _error(message, detail, field=None, status=400):
    body = {"error": message, "detail": _bounded_detail(detail)}
    if field is not None:
        body["field"] = field
    return body, status

# Fixed placeholder values. The repdigit rises are deliberately synthetic so nobody reads stub
# output as a measurement. TICK-062 serves A and A' live on the free-tier image; B and C need
# the depth model and return unavailable. A and A' still exercise every decision value so
# TICK-063 has all three render states. Intervals are consistent with the decisions: an
# interval straddling a line abstains at that line, and says so (D-009, TICK-222).
_UNAVAILABLE_DEPTH_ARM = {
    "absent_reason": "unavailable",
    "detail": (
        "Arm B needs the monocular depth model, which this image does not carry "
        "(TICK-062). The offline harness still scores it."
    ),
}
# Arm C is CUT, not unavailable, and the two are different claims: `unavailable` says
# this deployment cannot serve it, `cut` says the project dropped it and nobody is
# coming back (D-030, #43). TICK-063 renders them differently -- a cut arm is expected,
# an unavailable one is about this host -- so serving `unavailable` here would promise a
# capability that no deployment will ever have.
_CUT_ARM = {
    "absent_reason": "cut",
    "detail": (
        "Arm C was cut on 2026-09-02 by D-030: the Sep 2 scope gate lapsed with no arm "
        "implemented and no captures taken. See CHANGES.log."
    ),
}
STUB_ARMS = {
    "A": {
        "rise_in": 0.11,
        "interval_in": {"low": 0.09, "high": 0.13},
        "decisions": {
            "half_inch": {"verdict": "pass"},
            "quarter_inch": {"verdict": "pass"},
        },
    },
    "A_prime": {
        "rise_in": 0.55,
        "interval_in": {"low": 0.40, "high": 0.70},
        "decisions": {
            "half_inch": {
                "verdict": "abstain",
                "explanation": (
                    "The 0.40-0.70 in interval straddles the 1/2 in line, so this capture "
                    "cannot be classified against it either way."
                ),
            },
            "quarter_inch": {"verdict": "fail"},
        },
    },
    "B": dict(_UNAVAILABLE_DEPTH_ARM),
    "C": dict(_CUT_ARM),
}

# EPIC-06 AC4: removing the core library must break this server at IMPORT time rather than
# silently changing a number. Until this line, nothing here imported `frontdoor.metrology` at
# all -- the four arm names were spelled out independently in three places (the library, the
# stub above, and the frozen response schema), and deleting the entire metrology package left
# the server serving four arms as though nothing had happened.
#
# Checked rather than derived, because the response schema is FROZEN (TICK-060) and the stub is
# literal data by design; generating the keys from ARM_NAMES would make the server's output
# follow the library silently, which is the opposite of what a frozen contract is for. This way
# a divergence is a loud failure at startup, in the process that is about to serve it.
#
# `raise` rather than `assert`: assertions vanish under `python -O`, and this must hold in the
# container.
if len(STUB_ARMS) != len(ARM_NAMES) or set(STUB_ARMS) != set(ARM_NAMES):
    raise RuntimeError(
        "the server's arms and frontdoor.metrology.ARM_NAMES disagree: "
        f"server {sorted(STUB_ARMS)} vs library {sorted(ARM_NAMES)}. "
        "One of them has drifted; the demo and the error budget must run the same arms (R-11)."
    )


def validate_measure_response(body):
    """Validate a response against the full contract, schema plus cross-field rules.

    JSON Schema cannot compare two sibling numbers, so the two constraints that make an interval
    mean anything live here (TICK-223). A point estimate outside its own interval is not a
    measurement with uncertainty, it is two unrelated numbers, and every decision D-009 derives
    from them is meaningless.

    Cross-field errors carry the same path as schema errors, so a caller reporting json_path
    locates both kinds the same way.

    Raises jsonschema.ValidationError; returns None on success.
    """
    _response_validator.validate(body)
    for name, arm in body["arms"].items():
        if "rise_in" not in arm:
            continue
        low, high = arm["interval_in"]["low"], arm["interval_in"]["high"]
        if low > high:
            raise ValidationError(
                f"arm {name}: interval_in is inverted, low {low} exceeds high {high}",
                path=["arms", name, "interval_in"],
            )
        if not low <= arm["rise_in"] <= high:
            raise ValidationError(
                f"arm {name}: rise_in {arm['rise_in']} lies outside its own interval [{low}, {high}]",
                path=["arms", name, "rise_in"],
            )


def create_app():
    app = Flask(__name__)
    # An explicit ceiling, so 413 is a decision rather than a side effect of Flask's default
    # MAX_FORM_MEMORY_SIZE — which only covers non-file form fields, leaving the realistic oversized
    # body (the image part) uncapped, and which differs across the flask>=3 range this pins.
    app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES
    # Public stamp map: GET /map and GET /map/data (TICK-247).
    app.register_blueprint(map_page)
    # Photo-upload ADA feature screening: POST /screen (TICK-245).
    app.register_blueprint(screen_page)
    # Scan persistence: POST /screen/publish and GET /scan/photo/<key> (TICK-262, #270).
    app.register_blueprint(scan_page)

    # Capture ingest: POST /upload (TICK-029, #33). Registered via a function rather than a
    # blueprint so it can use this module's _error contract without a circular import.
    register_upload(app, _error)
    # Future-capture human labels: authenticated with the same ingest-only phone key.
    register_labels(app, _error)

    @app.get("/health")
    def health():
        """Cheap liveness probe for the fallback chain on stage (TICK-064)."""
        return {"status": "ok"}, 200

    @app.get("/app")
    def app_page():
        """The EntryMap app page (TICK-247): the phone-web scanner, served by this image.

        Same origin as the endpoints it calls -- the page's /screen, /screen/publish,
        /scan/photo/<key> and /map/data URLs are relative -- so there is no second host to
        get wrong and no CORS in the way, and the page on a phone is the page that was
        tested. The page is self-contained (its photos are embedded, ~1 MB), so the only
        caching header is a short max-age: enough to spare a phone the download on every
        navigation, short enough that a redeploy shows within minutes.
        """
        html = (
            resources.files("frontdoor_server")
            .joinpath("app.html")
            .read_text(encoding="utf-8")
        )
        response = Response(html, mimetype="text/html")
        response.headers["Cache-Control"] = "public, max-age=300"
        return response

    @app.get("/app-manifest.json")
    def app_manifest():
        """The web app manifest (TICK-327).

        With this and the service worker, adding the page to a home screen
        installs an app: its own icon, its own name, no browser chrome, and a
        launch that works with no signal. There is no paid developer account
        and no store review between this and a phone, which is the point.
        """
        body = (
            resources.files("frontdoor_server")
            .joinpath("app-manifest.json")
            .read_text(encoding="utf-8")
        )
        response = Response(body, mimetype="application/manifest+json")
        response.headers["Cache-Control"] = "public, max-age=300"
        return response

    @app.get("/app-sw.js")
    def app_service_worker():
        """The service worker, served from the root so its scope covers the app.

        Never cached itself: the browser must be able to see a new one on the
        next launch, or a deploy cannot reach a phone that already installed.
        """
        body = (
            resources.files("frontdoor_server")
            .joinpath("app-sw.js")
            .read_text(encoding="utf-8")
        )
        response = Response(body, mimetype="text/javascript")
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Service-Worker-Allowed"] = "/"
        return response

    @app.get("/app-icon.png")
    def app_icon():
        """The home-screen icon for the app page (TICK-325).

        iOS reads apple-touch-icon only from a real URL: a data: URI in the
        link tag is ignored and Safari falls back to the page favicon, which
        is how an installed shortcut ends up with the wrong image. Serving
        the mark from this origin is the whole fix. The bytes are fixed for
        the life of a deploy, so they cache for a day.
        """
        icon = (
            resources.files("frontdoor_server")
            .joinpath("app-icon.png")
            .read_bytes()
        )
        response = Response(icon, mimetype="image/png")
        response.headers["Cache-Control"] = "public, max-age=86400"
        return response

    @app.post("/measure")
    def measure():
        if "image" not in request.files:
            return _error(
                "missing image",
                "POST /measure expects multipart/form-data with a file part named 'image'.",
            )
        # A part that is present but empty is not a lesser version of an image, it is no image:
        # nothing can be measured from zero bytes. Flask puts an empty FileStorage in
        # request.files, so the membership test above passes and, while /measure is a stub that
        # never looks at the pixels, the request returns a confident measurement-shaped 200. Found
        # on the #51 device round trip. The failure it produces on stage is the one D-009 exists to
        # prevent: the image part fails to attach, and the phone renders a rise for a photo the
        # server never had. Reported as "missing image" rather than a new token because that is
        # what happened, and the committed enum in measure_error.schema.json is what TICK-063
        # branches on -- an unrecognised token decodes to nil on the client and loses the
        # not-worth-retrying advice that tells the operator to re-take the shot.
        image = request.files["image"]
        if not image.read(1):
            return _error(
                "missing image",
                "The 'image' part of this request carried no bytes, so there is nothing to "
                "measure.",
            )
        # Reading to test the part CONSUMED it: a second read returns b"". One byte rather than
        # the whole file, and rewound, because the next thing to touch these bytes is TICK-061's
        # real metrology -- which would otherwise decode an empty image on every well-formed
        # request, with this guard passing. That is the failure above, one layer down.
        image.stream.seek(0)

        if "sidecar" not in request.form:
            return _error(
                "missing sidecar",
                "POST /measure expects multipart/form-data with a form field named 'sidecar' "
                "holding the capture sidecar JSON.",
            )

        try:
            sidecar = json.loads(request.form["sidecar"])
        except json.JSONDecodeError as exc:
            return _error("sidecar is not valid JSON", str(exc))

        try:
            validate_sidecar(sidecar)
        except ValidationError as exc:
            return _error(
                "sidecar failed validation",
                exc.message,
                field=exc.json_path,
                status=422,
            )

        return {
            "stub": True,
            "capture_id": sidecar["capture_id"],
            "arms": STUB_ARMS,
        }, 200

    # Browser scan clients call the screening surface cross-origin, and without
    # Access-Control-Allow-Origin the browser DISCARDS the response after the server has
    # already done the work: a multipart POST is a CORS "simple request", so it is sent
    # (and burns a model call) and only the reply is dropped. `*` is safe on exactly these
    # routes: they serve public, privacy-processed content and verdicts, use no cookies and
    # no auth, so a wildcard exposes no credentials.
    #
    # An after_request hook rather than headers in the views, because the error paths
    # matter as much as the 200s -- the 413 Flask raises before the view body runs, the
    # JSON-ified 405 from the errorhandler below, the views' own 4xx/5xx -- and a browser
    # client needs to read that error contract, not a blank CORS failure. One path-scoped
    # hook covers every response on the covered routes and cannot drift between the two
    # view modules.
    #
    # Scope is deliberate and closed: /screen, /screen/publish, /scan/photo/<key>.
    # /map/data is intentionally NOT covered (unchanged scope), and /upload and /measure
    # are not browser surfaces.
    @app.after_request
    def _screening_cors(response):
        path = request.path
        if path in ("/screen", "/screen/publish") or path.startswith("/scan/photo/"):
            response.headers["Access-Control-Allow-Origin"] = "*"
            if request.method == "OPTIONS":
                # The multipart POST itself never preflights, but a publish carrying the
                # optional X-Frontdoor-Contributor header does -- a non-safelisted request
                # header makes the request non-simple -- so OPTIONS answers with what the
                # browser asks about. Flask's automatic OPTIONS supplies the response;
                # these headers make it a valid preflight answer.
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = (
                    "Content-Type, X-Frontdoor-Contributor"
                )
        return response

    # Every response this service produces carries the committed error contract, including the
    # statuses Werkzeug raises before any view runs — 404 for a typo'd path, 405 for a wrong method,
    # 413 for an oversized body (#113). The consumer is an iOS client parsing JSON over a venue
    # network, and those are exactly the conditions the TICK-064 fallback chain exists for: meeting
    # HTML where it expects JSON turns a clear message into a parse failure on stage.
    #
    # Registered as one general handler rather than per-status cases, so a status nobody anticipated
    # cannot slip back to HTML.
    @app.errorhandler(HTTPException)
    def _http_error_as_json(exc):
        # Unmapped statuses fall back to a token that IS in the committed enum. Inventing one --
        # 408, 429, 431, or a Werkzeug 400 for a malformed multipart boundary -- would satisfy the
        # "always JSON" rule while violating the schema the client branches on, which is a subtler
        # version of the same failure.
        body, status = _error(
            _HTTP_ERROR_MESSAGES.get(exc.code, "internal error"),
            exc.description or exc.name,
            status=exc.code or 500,
        )
        # Werkzeug's own headers carry things the status is meaningless without: Allow on a 405 is
        # required by RFC 9110, and Retry-After/WWW-Authenticate would matter if those arise.
        response = jsonify(body)
        response.status_code = status
        for header, value in exc.get_headers():
            if header.lower() != "content-type":
                response.headers.setdefault(header, value)
        return response

    # An unhandled exception must not return a traceback or an HTML 500 page either. QA saw zero
    # 500s across 84 requests, so this is a guard rather than a fix.
    @app.errorhandler(Exception)
    def _unexpected_error_as_json(exc):
        if isinstance(exc, HTTPException):
            return _http_error_as_json(exc)
        app.logger.exception("unhandled error in %s", request.path)
        body, status = _error(
            "internal error",
            "The server failed to handle the request. Nothing was measured.",
            status=500,
        )
        return jsonify(body), status

    return app
