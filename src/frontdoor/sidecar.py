"""Validation for the per-capture JSON sidecar (ARCHITECTURE.md section 4, TICK-010)."""

import json
from importlib import resources

from jsonschema import Draft202012Validator

SCHEMA = json.loads(
    resources.files("frontdoor").joinpath("capture_sidecar.schema.json").read_text(encoding="utf-8")
)

_validator = Draft202012Validator(SCHEMA)


def validate_sidecar(record):
    """Validate one sidecar record against the capture sidecar schema.

    Raises jsonschema.ValidationError naming the offending field; returns None on success.
    """
    _validator.validate(record)
