"""POST /measure and GET /health (TICK-060).

A thin entrypoint over the core metrology library (ARCHITECTURE.md section 3): it holds no state
and owns no metrology. Every value it returns here is a fixed placeholder; TICK-061 replaces the
stub with a real call behind this identical contract, and the tests written for this module run
unchanged against it.
"""

import json
from importlib import resources

from flask import Flask, request
from jsonschema import ValidationError

from frontdoor.sidecar import validate_sidecar

RESPONSE_SCHEMA = json.loads(
    resources.files("frontdoor_server")
    .joinpath("measure_response.schema.json")
    .read_text(encoding="utf-8")
)

ERROR_SCHEMA = json.loads(
    resources.files("frontdoor_server")
    .joinpath("measure_error.schema.json")
    .read_text(encoding="utf-8")
)

# HTTP statuses /measure uses today, each tied to a class of failure (TICK-224).
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


def _error(message, detail, field=None, status=400):
    body = {"error": message, "detail": _bounded_detail(detail)}
    if field is not None:
        body["field"] = field
    return body, status


# Fixed placeholder values. The repdigit rises are deliberately synthetic so nobody reads stub
# output as a measurement, and the four arms between them exercise every decision value, giving
# TICK-063 all three render states to build against. Intervals are consistent with the decisions:
# an interval straddling a line abstains at that line (D-009).
STUB_ARMS = {
    "A": {
        "rise_in": 0.11,
        "interval_in": {"low": 0.09, "high": 0.13},
        "decisions": {"half_inch": "pass", "quarter_inch": "pass"},
    },
    "A_prime": {
        "rise_in": 0.22,
        "interval_in": {"low": 0.17, "high": 0.27},
        "decisions": {"half_inch": "pass", "quarter_inch": "abstain"},
    },
    "B": {
        "rise_in": 0.44,
        "interval_in": {"low": 0.31, "high": 0.57},
        "decisions": {"half_inch": "abstain", "quarter_inch": "fail"},
    },
    "C": {
        "rise_in": 0.77,
        "interval_in": {"low": 0.60, "high": 0.94},
        "decisions": {"half_inch": "fail", "quarter_inch": "fail"},
    },
}


def create_app():
    app = Flask(__name__)

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

    return app
