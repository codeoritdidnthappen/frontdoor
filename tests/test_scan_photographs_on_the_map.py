"""A scanned pin names its photographs, and the receipt shows them (TICK-494, #494).

The owner, on the live app: *"when clicking on a scanned on-site such as sushi
roku, i click evidence and it doesn't have the evidence receipt or
photograph"*. He was right, and the cause was that the photograph was not in
the payload at all. The bytes were stored, `GET /scan/photo/<key>` already
streamed them, and the pin simply never named them.

What these tests hold:

  * The pin carries KEYS, never bytes. /map/data serves 187 pins.
  * The keys are ONE scan's, in the order the frames were uploaded. That order
    is what `blur_regions` and an evidence box's `frame` index against, so a
    reordering here would draw a box on the wrong photograph.
  * A scan that stored nothing carries no photograph key, and the page says so
    in words rather than rendering an empty frame under the word "evidence" --
    and never says anything that reads as "this place was not scanned".
  * Nothing about a photograph touches a state, a label or a checklist. It is
    evidence of what was seen, never a verdict.
  * Only keys the /scan/photo/ allowlist would accept ever reach a reader, so
    no unprocessed original can be named through this field.
"""

import json
from importlib import resources

import pytest

from frontdoor.scan_records import merge_scans
from frontdoor_server.app import create_app

GOOD_KEYS = [
    "scans/desano/" + "a" * 32 + ".jpg",
    "scans/desano/" + "b" * 32 + ".jpg",
]


def scan(place_id, date, image_keys, scan_id="s1"):
    return {
        "scan_id": scan_id,
        "place_ref": {"place_id": place_id, "name": "Example Cafe",
                      "lat": 40.0, "lng": -75.0},
        "created_at": date,
        "verdicts": {"ramp_or_bevel": "present"},
        "confidences": {"ramp_or_bevel": 80},
        "faces_blurred": 0,
        "quarantined_count": 0,
        "image_keys": list(image_keys),
    }


def dataset_row(place_id="green"):
    return {
        "place_id": place_id,
        "name": "Example Cafe",
        "location": {"lat": 40.0, "lng": -75.0},
        "source": "streetview",
        "status": "ai_estimated",
        "covered": True,
        "coverage_status": "OK",
        "imagery_date": "2024-06",
        "headings": [10.0],
        "criteria": {},
        "assessment_errors": [],
    }


# --- the merge --------------------------------------------------------------


def test_meta_carries_the_scan_photographs_in_upload_order():
    _, meta = merge_scans(
        {"green": dataset_row()},
        [scan("green", "2026-09-04T10:00:00Z", GOOD_KEYS)],
    )
    assert meta["green"]["photos"] == GOOD_KEYS


def test_a_scan_that_stored_nothing_carries_no_photographs():
    # The curated on-site publication publishes verdicts and dates and no
    # bytes at all (frontdoor.scan_publish.build_records), so this is the
    # common case rather than an exotic one.
    _, meta = merge_scans(
        {"green": dataset_row()},
        [scan("green", "2026-09-04T10:00:00Z", [])],
    )
    assert meta["green"]["photos"] == []


def test_only_allowlisted_keys_reach_a_reader():
    # The same allowlist GET /scan/photo/<key> enforces. A key outside scans/
    # is not served with a shrug, it is not named at all.
    _, meta = merge_scans(
        {"green": dataset_row()},
        [scan("green", "2026-09-04T10:00:00Z",
              ["open/sealed/original.jpg", "../../etc/passwd",
               GOOD_KEYS[0], "captures/x/" + "c" * 32 + ".jpg"])],
    )
    assert meta["green"]["photos"] == [GOOD_KEYS[0]]


def test_the_photographs_are_the_scan_the_pin_is_dated_by():
    # One scan's frames, never a pooled set: an evidence box's `frame` is an
    # index into ONE scan's image_keys, so pooling two captures would make
    # every index a guess. The strip and the date on the receipt therefore
    # always describe the same visit.
    older = scan("green", "2026-08-01T10:00:00Z", GOOD_KEYS, scan_id="old")
    newer = scan("green", "2026-09-04T10:00:00Z",
                 ["scans/desano/" + "c" * 32 + ".jpg"], scan_id="new")
    _, meta = merge_scans({"green": dataset_row()}, [older, newer])
    assert meta["green"]["last_scanned"] == "2026-09-04"
    assert meta["green"]["photos"] == ["scans/desano/" + "c" * 32 + ".jpg"]


def test_a_later_scan_with_no_bytes_leaves_the_pin_without_photographs():
    # Deliberate, and the trade named in merge_scans: an older capture's
    # photographs are NOT shown under a newer capture's date, because the
    # receipt dates the strip it shows.
    older = scan("green", "2026-08-01T10:00:00Z", GOOD_KEYS, scan_id="old")
    newer = scan("green", "2026-09-04T10:00:00Z", [], scan_id="new")
    _, meta = merge_scans({"green": dataset_row()}, [older, newer])
    assert meta["green"]["photos"] == []


def test_a_phone_scan_is_not_shadowed_by_a_same_day_curated_row():
    # The curated publication is read first and stores no bytes. A phone's
    # scan on the same day must still bring its photographs.
    curated = scan("green", "2026-09-04T10:00:00Z", [], scan_id="curated")
    phone = scan("green", "2026-09-04T18:00:00Z", GOOD_KEYS, scan_id="phone")
    _, meta = merge_scans({"green": dataset_row()}, [curated, phone])
    assert meta["green"]["photos"] == GOOD_KEYS


# --- the endpoint -----------------------------------------------------------


@pytest.fixture
def client():
    return create_app().test_client()


def map_data(client, tmp_path, monkeypatch, records):
    dataset_path = tmp_path / "precatalogue.json"
    dataset_path.write_text(json.dumps({"green": dataset_row()}),
                            encoding="utf-8")
    scans_path = tmp_path / "scans.jsonl"
    scans_path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8")
    monkeypatch.setenv("FRONTDOOR_MAP_DATASET", str(dataset_path))
    monkeypatch.setenv("FRONTDOOR_SCANS", str(scans_path))
    monkeypatch.setenv("FRONTDOOR_PUBLISHED_SCANS", str(tmp_path / "none.jsonl"))
    response = client.get("/map/data")
    assert response.status_code == 200
    return response.get_json()


def only_pin(payload):
    (pin,) = payload["pins"]
    return pin


def test_a_scanned_pin_names_its_photographs(client, tmp_path, monkeypatch):
    payload = map_data(client, tmp_path, monkeypatch,
                       [scan("green", "2026-09-04T10:00:00Z", GOOD_KEYS)])
    pin = only_pin(payload)
    assert pin["state"] == "scanned_on_site"
    assert pin["photos"] == GOOD_KEYS


def test_the_payload_carries_references_and_never_bytes(
        client, tmp_path, monkeypatch):
    payload = map_data(client, tmp_path, monkeypatch,
                       [scan("green", "2026-09-04T10:00:00Z", GOOD_KEYS)])
    body = json.dumps(payload)
    assert "data:image" not in body
    assert "base64" not in body


def test_a_pin_with_no_stored_photograph_omits_the_key(
        client, tmp_path, monkeypatch):
    # Omitted, not an empty list and not a null: the same convention the
    # record's own optional keys and provenance already follow.
    payload = map_data(client, tmp_path, monkeypatch,
                       [scan("green", "2026-09-04T10:00:00Z", [])])
    assert "photos" not in only_pin(payload)


def test_a_photograph_changes_no_claim(client, tmp_path, monkeypatch):
    # The state, the label and every checklist entry are decided before the
    # photographs are attached, so the two payloads differ in exactly one key.
    with_photos = only_pin(map_data(
        client, tmp_path, monkeypatch,
        [scan("green", "2026-09-04T10:00:00Z", GOOD_KEYS)]))
    without = only_pin(map_data(
        client, tmp_path, monkeypatch,
        [scan("green", "2026-09-04T10:00:00Z", [])]))
    assert set(with_photos) - set(without) == {"photos"}
    assert {k: v for k, v in with_photos.items() if k != "photos"} == without


# --- the served page --------------------------------------------------------


def served_page():
    return (
        resources.files("frontdoor_server")
        .joinpath("app.html")
        .read_text(encoding="utf-8")
    )


def test_the_page_reads_the_pin_photographs_through_the_photo_route():
    page = served_page()
    assert "p.photos = Array.isArray(pin.photos) && pin.photos.length" in page
    assert "? pin.photos.map(k=>PHOTO_API+k) : null;" in page


def test_the_receipt_and_the_card_draw_the_pin_photographs():
    page = served_page()
    assert 'photos=`<div class="rcpt-photos">${p.photos.map(' in page
    assert "${p.photos.length} photo${p.photos.length>1?'s':''} from this scan" in page


def test_a_scanned_place_with_no_photograph_says_so_and_still_says_it_was_scanned():
    page = served_page()
    note = ("No photograph was published with this scan \\u2014 the checks and "
            "dates below came from an on-site visit.")
    assert note in page
    assert "    ${photos}${noPhoto}" in page


def test_the_receipt_does_not_count_photographs_it_does_not_have():
    # This row counts p.views, which on a server pin is the number of SCANS.
    # Calling those photographs printed "1 photo of this entrance so far"
    # directly beneath the note saying no photograph was published -- the
    # receipt contradicting itself on the surface that exists to be checked.
    page = served_page()
    assert "${nViews} on-site visit${nViews>1?'s':''} recorded here" in page
    assert ("${photos ? `${nViews} photo${nViews>1?'s':''} of this entrance so far`"
            in page)


def test_the_evidence_box_chips_still_require_a_real_photograph():
    # TICK-467's gate is `photos`, and the no-photograph note is deliberately
    # NOT in that variable: a note is not something a box can be drawn on, and
    # a row of chips over one would be the missing-box-as-absent-feature
    # reading that got the detector dropped as a scorer.
    page = served_page()
    assert "if(photos && p.evbox && p.f){" in page
    assert "const noPhoto = (!photos && p.tier!=='est')" in page
