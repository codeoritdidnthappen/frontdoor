"""The evidence box, on the bytes a phone actually gets (TICK-467).

Three defects in one week had a correct source, a passing test and a wrong
page: `src/frontdoor_server/app.html` is GENERATED from
`design-source/entrymap-app.html` by `tools/port_app_page.py`, and some render
paths exist twice -- once in the design source and once in a fragment under
`tools/app_wiring/` that the port substitutes wholesale. A test that reads the
design source proves nothing about what is served.

So every assertion here reads GET /app from the test client.
"""

import json
import re

import pytest

from frontdoor.screening import CRITERIA_KEYS
from frontdoor_server.app import create_app

#: The seeded door vocabulary DOOR_KEYMAP maps onto the four engine criteria.
#: A box may be drawn for these and for nothing else.
DOOR_CRITERIA = {
    "ramp_present", "handrails_present",
    "lever_or_pull_hardware", "accessible_signage",
}


@pytest.fixture(scope="module")
def served():
    response = create_app().test_client().get("/app")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _code_only_js(source):
    """The script with its comments removed.

    Prose describing a rule must not be able to satisfy or violate it -- the
    same discipline tests/test_evidence_boxes_off_the_scan_path.py applies to
    the Python. The comment above showEvidenceBox necessarily quotes the
    caption it forbids.
    """
    return re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", source, flags=re.S))


def _seeded_data(page):
    """The DATA literal the served page boots from."""
    start = page.index("const DATA = ")
    end = page.index("\n", start)
    return json.loads(page[start + len("const DATA = "):end].rstrip(";"))


# --- the feature is on the page at all ---------------------------------------


def test_the_receipt_offers_a_chip_that_points_into_the_photograph(served):
    assert "data-evbox=" in served
    assert "Tap a feature to see where we looked" in served
    assert "function placeEvidenceBox(" in served
    assert "function showEvidenceBox(" in served


def test_the_chips_are_gated_on_whether_the_detector_ran(served):
    """`p.evbox`, not "does this criterion have a box".

    Gating on which criteria came back with a box would turn the row of chips
    itself into a verdict -- the missing-box-as-absent-feature reading that got
    this detector dropped as a scorer -- and would also make the no-box
    sentence a guess, because a criterion with no box on an entrance nobody ran
    the detector on was not looked for at all.
    """
    assert "if(photos && p.evbox && p.f){" in served


def test_the_no_box_sentence_is_on_the_page_and_says_the_verdict_is_unchanged(served):
    sentence = ("we looked for this and couldn't point at it in these photos. "
                "That doesn't change the answer above.")
    assert sentence in served
    assert "The outline shows where our finder pointed. It never changes the answer." in served


def test_a_drawn_box_never_claims_the_feature_is_there(served):
    """Locating language only.

    The finder does put boxes on things the engine went on to call absent -- on
    the seeded doors it outlines a diagonal brass pull for "handrails", beside
    the engine's own sentence explaining that is exactly what it is. A caption
    asserting the feature would be the box contradicting the verdict on screen.
    """
    assert "outlined in ${which}" in served
    # Scoped to the caption itself: "here it is" is ordinary English and turns
    # up in the stylesheet's prose, so the assertion reads the function that
    # writes the words rather than the whole megabyte.
    body = _code_only_js(served[served.index("function showEvidenceBox("):
                                served.index("function openReceipt(")])
    for claim in ("here it is", "we found", "this is the", "confirmed"):
        assert claim not in body, f"the caption claims {claim!r}; it may only locate"


# --- the geometry ------------------------------------------------------------


def test_the_page_inverts_the_cover_fit_from_the_image_itself(served):
    """object-fit:cover scales to FILL and centre-crops; the inverse is the
    only correct mapping, and it must come from the image's own natural size
    rather than from any number the server sent."""
    assert "const s = Math.max(cw/nw, ch/nh);" in served
    assert "const nw = img.naturalWidth, nh = img.naturalHeight;" in served


def test_the_box_is_an_overlay_on_a_photograph_and_not_a_mark_on_a_pin(served):
    """Round 8's rule. `.ev-rect` may only ever be written into a `.rcpt-shot`
    figure, which exists only inside the receipt's photo strip."""
    assert 'class="rcpt-shot"' in served
    for hit in re.finditer(r'<span class="ev-rect"', served):
        window = served[max(0, hit.start() - 200):hit.start()]
        assert "rcpt-shot" in window, "an ev-rect was emitted outside a receipt photograph"
    # Nothing on the map or the pin draws one.
    assert "pin" not in served[served.index(".ev-rect{"):served.index(".ev-rect{") + 400]


# --- legibility --------------------------------------------------------------


def test_the_mark_is_a_stroke_inside_a_halo_as_measured(served):
    """The measurement in docs/evidence-boxes.md is of THIS construction.

    A bare white stroke measured 1.00:1 worst case over all 335 photographs in
    the capture corpus. Losing either half of the pair -- the halo or the
    stroke -- puts that number back on the page.
    """
    assert "--evbox-halo:rgba(30,17,66,.60);" in served
    assert "--evbox-ink:var(--white);" in served
    assert "border:var(--evbox-stroke) solid var(--evbox-ink);" in served
    assert "box-shadow:0 0 0 var(--evbox-halo-w) var(--evbox-halo)," in served
    assert "inset 0 0 0 var(--evbox-halo-w) var(--evbox-halo);" in served


# --- the seeded data the demo actually shows ---------------------------------


def test_the_seeded_doors_carry_real_boxes_the_receipt_can_draw(served):
    data = _seeded_data(served)
    boxed = [
        (door["id"], key, entry["box"])
        for door in data["doors"]
        for key, entry in door["crit"].items()
        if "box" in entry
    ]
    assert boxed, "no seeded door carries a box; the receipt has nothing to draw"
    for door_id, key, box in boxed:
        assert key in DOOR_CRITERIA, f"{door_id} has a box for {key}, which is not a criterion"
        assert set(box) == {"frame", "x", "y", "w", "h", "label", "score"}
        assert all(isinstance(box[n], int) and box[n] >= 0 for n in ("x", "y", "w", "h"))
        assert 0 < box["score"] <= 1


def test_every_seeded_box_lands_inside_the_photograph_it_names(served):
    """Geometry is in the stored frame's pixels, and the stored frame is the
    data: URI the receipt displays. A box that overhangs its own photograph is
    geometry from some other frame, which is the failure mode this discipline
    exists to prevent."""
    import base64
    import io

    from PIL import Image

    data = _seeded_data(served)
    start = served.index("const PHOTOS = ")
    photos = json.loads(served[start + len("const PHOTOS = "):served.index("\n", start)].rstrip(";"))

    checked = 0
    for door in data["doors"]:
        for key, entry in door["crit"].items():
            box = entry.get("box")
            if box is None:
                continue
            uri = photos[door["id"]][box["frame"]]
            frame = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))
            assert box["x"] + box["w"] <= frame.width, (door["id"], key)
            assert box["y"] + box["h"] <= frame.height, (door["id"], key)
            checked += 1
    assert checked, "nothing was checked; the seeded boxes went missing"


def test_a_seeded_door_the_finder_found_nothing_on_still_offers_its_chips(served):
    """The case the ticket is about, present in the demo rather than only in
    the code: an entrance where the detector ran and pointed at nothing still
    says so, chip by chip, with its verdicts untouched."""
    data = _seeded_data(served)
    searched = [d for d in data["doors"] if d.get("evbox")]
    assert searched, "no seeded door records that the finder ran"
    empty = [d for d in searched if not any("box" in e for e in d["crit"].values())]
    assert empty, "every searched door found something; the no-box path is undemonstrated"
    for door in empty:
        assert set(door["crit"]) <= DOOR_CRITERIA
        assert all(entry["v"] for entry in door["crit"].values())


def test_no_seeded_criterion_carries_a_null_box(served):
    """There is no per-criterion shape for "searched and found nothing".

    A null is a value a reader -- or a later change -- can talk itself into
    treating as a finding. The absence of the key is the only representation,
    and `evbox` on the door carries the fact that the search happened.
    """
    data = _seeded_data(served)
    for door in data["doors"]:
        for key, entry in door["crit"].items():
            if "box" in entry:
                assert isinstance(entry["box"], dict)
    assert '"box":null' not in served


# --- and it still cannot judge -----------------------------------------------


def test_the_page_carries_boxes_only_for_the_engines_four_criteria(served):
    """TICK-481 cut the product's vocabulary to the engine's four. A box for a
    fifth would be a finding about something nothing assessed."""
    data = _seeded_data(served)
    keys = {key for door in data["doors"] for key, e in door["crit"].items() if "box" in e}
    assert keys <= DOOR_CRITERIA
    assert len(DOOR_CRITERIA) == len(CRITERIA_KEYS) == 4


def test_the_verdict_the_receipt_prints_is_read_from_the_verdict_field(served):
    """featsOf carries the box alongside the verdict and never through it."""
    assert ("out[ck] = {v:normV(p.crit[k].v), raw:p.crit[k].v, c:p.crit[k].c, "
            "e:p.crit[k].e||'',") in served
    assert "box:p.crit[k].box};" in served
    # normV is the whole verdict mapping, and it never looks at a box.
    body = served[served.index("function normV(v){"):served.index("function featsOf(p){")]
    assert "box" not in body
