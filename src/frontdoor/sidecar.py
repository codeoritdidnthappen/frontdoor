"""Validation for the per-capture JSON sidecar (ARCHITECTURE.md section 4, TICK-010)."""

import json
from importlib import resources

from jsonschema import Draft202012Validator

SCHEMA = json.loads(
    resources.files("frontdoor").joinpath("capture_sidecar.schema.json").read_text(encoding="utf-8")
)

# format is an annotation unless a format_checker is passed. rfc3339-validator
# registers the date-time checker; captured_at also requires a trailing Z.
_validator = Draft202012Validator(SCHEMA, format_checker=Draft202012Validator.FORMAT_CHECKER)


def validate_sidecar(record):
    """Validate one sidecar record against the capture sidecar schema.

    Raises jsonschema.ValidationError naming the offending field; returns None on success.
    """
    _validator.validate(record)
