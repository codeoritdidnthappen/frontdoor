"""POST /measure and GET /health (TICK-060).

A thin entrypoint over the core metrology library (ARCHITECTURE.md section 3): it holds no state
and owns no metrology. Every value it returns here is a fixed placeholder; TICK-061 replaces the
stub with a real call behind this identical contract, and the tests written for this module run
unchanged against it.
"""

import json
from importlib import resources

from flask import Flask, jsonify, request
from jsonschema import Draft202012Validator, ValidationError
from werkzeug.exceptions import HTTPException

from frontdoor.sidecar import validate_sidecar
from frontdoor_server.map_view import map_page

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
        "Arms B and C need the monocular depth model, which this free-tier image "
        "does not carry (TICK-062)."
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
    "C": dict(_UNAVAILABLE_DEPTH_ARM),
}


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

    @app.get("/health")
    def health():
        """Cheap liveness probe for the fallback chain on stage (TICK-064)."""
        return {"status": "ok"}, 200

    @app.post("/measure")
    def measure():
        if "image" not in request.files:
            return _error(
                "missing image",
                "POST /measure expects multipart/form-data with a file part named 'image'.",
            )
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
