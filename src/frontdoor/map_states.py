"""Public map stamp states: the Green-or-Gray rule (TICK-247, #169).

The public map has exactly two stamp states — "Verified Accessible" (green)
and "Not Yet Checked" (neutral) — and this module is the single place that
decides which one a dataset row gets. The rule is the legal and backlash
shield for putting real businesses on a public map: the map only ever
celebrates or stays silent, and nothing a screen finds is ever published as
a negative verdict against a named business.

Enforcement, not convention:
- ``state_for_row`` is total and default-neutral. Green requires a row whose
  ``status`` is exactly ``"verified"`` (human confirmation) from a
  non-imagery source; every other input — ``ai_estimated``, missing,
  malformed, or any adversarial or negative-looking value — is Not Yet
  Checked. No input can produce a third state.
- Imagery alone never turns a business green: a row whose ``source`` is an
  imagery-only source stays neutral even if it claims ``status: verified``.
- Per-criterion checklist entries use a three-word public vocabulary —
  visible / not visible in photos / not assessed — so a screening "absent"
  verdict is published as an observation ("not visible in photos"), never as
  a negative claim.

Rows are the TICK-248 pre-catalogue shape (place_id-keyed, per-criterion
verdicts, ``status``/``source``/``imagery_date``). This is a data-shape
dependency only; nothing here imports the screening or pre-catalogue code.
"""

STATE_VERIFIED = "verified_accessible"
STATE_NEUTRAL = "not_yet_checked"
STATES = frozenset((STATE_VERIFIED, STATE_NEUTRAL))

STAMP_LABELS = {
    STATE_VERIFIED: "Verified Accessible",
    STATE_NEUTRAL: "Not Yet Checked",
}

# The only status that can ever produce a green stamp, and the imagery-only
# sources that can never produce one regardless of status.
VERIFIED_STATUS = "verified"
IMAGERY_ONLY_SOURCES = frozenset({"streetview"})

# Display order and public names for the checklist criteria (TICK-245 keys).
CRITERIA = (
    ("ramp_or_bevel", "Ramp or beveled threshold"),
    ("handrails", "Handrails"),
    ("accessible_door_hardware", "Accessible door hardware"),
    ("accessibility_signage", "Accessibility signage"),
)

# Public per-criterion vocabulary. "absent" is deliberately published as
# NOT_VISIBLE: the checklist reports what the photos show, never a negative
# claim about the business.
OBSERVATION_VISIBLE = "visible"
OBSERVATION_NOT_VISIBLE = "not_visible"
OBSERVATION_NOT_ASSESSED = "not_assessed"

OBSERVATION_LABELS = {
    OBSERVATION_VISIBLE: "Visible in photos",
    OBSERVATION_NOT_VISIBLE: "Not visible in photos",
    OBSERVATION_NOT_ASSESSED: "Not assessed",
}

OBSERVATION_NOTE = (
    "Checklist entries are visible-feature observations from photos. They "
    "are not measurements, compliance determinations, or legal conclusions."
)

AI_ESTIMATED_LABEL = "AI-estimated"


def state_for_row(row):
    """Map any dataset row to exactly one of the two public stamp states.

    Total and default-neutral: the only input that produces the green state
    is a dict with ``status == "verified"`` and a source that is not
    imagery-only. Everything else — including any unexpected, negative, or
    adversarial value — is ``STATE_NEUTRAL``.
    """
    if (
        isinstance(row, dict)
        and row.get("status") == VERIFIED_STATUS
        and row.get("source") not in IMAGERY_ONLY_SOURCES
    ):
        return STATE_VERIFIED
    return STATE_NEUTRAL


def _observation(entry):
    """Public observation for one criterion entry. Total, default not-assessed."""
    verdict = entry.get("verdict") if isinstance(entry, dict) else None
    if verdict == "present":
        return OBSERVATION_VISIBLE
    if verdict in ("absent", "not_visible"):
        return OBSERVATION_NOT_VISIBLE
    return OBSERVATION_NOT_ASSESSED


def checklist_for_row(row):
    """Per-criterion checklist for a pin, in display order.

    Every entry's ``observation`` is one of the three public vocabulary
    values; confidence is passed through only when it is a number.
    """
    criteria = row.get("criteria") if isinstance(row, dict) else None
    if not isinstance(criteria, dict):
        criteria = {}
    checklist = []
    for key, label in CRITERIA:
        entry = criteria.get(key)
        observation = _observation(entry)
        confidence = entry.get("confidence") if isinstance(entry, dict) else None
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            confidence = None
        checklist.append({
            "key": key,
            "label": label,
            "observation": observation,
            "observation_label": OBSERVATION_LABELS[observation],
            "confidence": confidence,
        })
    return checklist


def _valid_location(row):
    location = row.get("location")
    if not isinstance(location, dict):
        return None
    lat, lng = location.get("lat"), location.get("lng")
    for value, bound in ((lat, 90), (lng, 180)):
        if (not isinstance(value, (int, float)) or isinstance(value, bool)
                or not -bound <= value <= bound):
            return None
    return {"lat": float(lat), "lng": float(lng)}


def pin_for_row(place_id, row):
    """One map pin, with its state and checklist pre-computed server-side.

    Returns None when the row has no usable coordinates — a stamp cannot be
    placed without a location.
    """
    if not isinstance(row, dict):
        return None
    location = _valid_location(row)
    if location is None:
        return None
    state = state_for_row(row)
    name = row.get("name")
    imagery_date = row.get("imagery_date")
    return {
        "place_id": str(place_id),
        "name": name if isinstance(name, str) else "",
        "location": location,
        "state": state,
        "label": STAMP_LABELS[state],
        "ai_estimated": row.get("status") == "ai_estimated",
        "imagery_date": imagery_date if isinstance(imagery_date, str) else None,
        "checklist": checklist_for_row(row),
    }


def prepare_map_payload(dataset):
    """Map payload for a place_id-keyed dataset (TICK-248 output shape).

    Total: a malformed dataset yields an empty pin list rather than an error,
    and every pin's state is one of the two public states.
    """
    pins = []
    if isinstance(dataset, dict):
        for place_id in sorted(dataset):
            pin = pin_for_row(place_id, dataset[place_id])
            if pin is not None:
                pins.append(pin)
    return {"note": OBSERVATION_NOTE, "pins": pins}
