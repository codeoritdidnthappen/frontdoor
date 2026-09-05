"""Owner claim flow (TICK-259, #248).

Seams: public HTTP + the claims JSONL store. The public map must not change
because a claim was submitted, approved, rejected, or abandoned — Owner-confirmed
is a later attested in-app capture, and camera-roll cannot attest.
"""

import inspect
import json

import pytest

from frontdoor.claims import (
    INCENTIVES_TEXT,
    ClaimError,
    has_approved_claim,
    load_claims,
    submit_claim,
)
from frontdoor.map_states import STATE_NEUTRAL, STATE_VERIFIED, STATES, pin_for_row
from frontdoor.scan_records import load_scan_records, merge_scans, new_scan_record
from frontdoor_server import claim_view
from frontdoor_server.app import create_app
from frontdoor_server.claim_view import CLAIM_TOKEN_HEADER
from frontdoor_server.scan_view import STORE_KEY
from frontdoor_server.screen_view import ENGINE_KEY
from tests.test_scan_publish_endpoint import FakeStore, post_publish
from tests.test_screen_endpoint import FakeEngine, image_part


PLACE = "ChIJcafe"
PHONE = "(512) 555-0137"
WEBSITE = "https://www.royalbluegrocery.com"
REVIEW_KEY = "claim-review-key"


def cafe_row(**overrides):
    base = {
        "place_id": PLACE,
        "name": "Royal Blue Grocery",
        "location": {"lat": 30.267, "lng": -97.743},
        "status": "ai_estimated",
        "source": "streetview",
        "phone": PHONE,
        "website": WEBSITE,
        "criteria": {},
        "imagery_date": "2024-06",
    }
    base.update(overrides)
    return base


@pytest.fixture
def env(tmp_path, monkeypatch):
    catalogue = tmp_path / "precat.json"
    catalogue.write_text(json.dumps({PLACE: cafe_row()}), encoding="utf-8")
    claims = tmp_path / "claims.jsonl"
    codes = tmp_path / "codes.json"
    codes.write_text(json.dumps({PLACE: "DOOR-42"}), encoding="utf-8")
    scans = tmp_path / "scans.jsonl"
    monkeypatch.setenv("FRONTDOOR_MAP_DATASET", str(catalogue))
    monkeypatch.setenv("FRONTDOOR_CLAIMS", str(claims))
    monkeypatch.setenv("FRONTDOOR_CLAIM_CODES", str(codes))
    monkeypatch.setenv("FRONTDOOR_SCANS", str(scans))
    monkeypatch.setenv("FRONTDOOR_UPLOAD_KEY", REVIEW_KEY)
    return {"catalogue": catalogue, "claims": claims, "codes": codes, "scans": scans}


def client():
    return create_app().test_client()


def pin_state(http, place_id=PLACE):
    payload = http.get("/map/data").get_json()
    pins = {pin["place_id"]: pin for pin in payload["pins"]}
    return pins.get(place_id)


def submit(http, **fields):
    body = {"place_id": PLACE, "channel": "listed_phone"}
    body.update(fields)
    return http.post("/claim", json=body)


def approve(http, claim_id):
    return http.post(
        f"/claim/{claim_id}/review",
        json={"action": "approve"},
        headers={"X-Frontdoor-Upload-Key": REVIEW_KEY},
    )


# --- catalogue search --------------------------------------------------------


def test_place_search_returns_channels_not_listing_contact(env):
    http = client()
    body = http.get("/claim/places", query_string={"q": "royal"}).get_json()
    assert body["places"] == [{
        "place_id": PLACE,
        "name": "Royal Blue Grocery",
        "location": {"lat": 30.267, "lng": -97.743},
        "channels": {
            "listed_phone": True,
            "business_email": True,
            "in_store_code": True,
        },
    }]
    dumped = json.dumps(body)
    assert PHONE not in dumped
    assert "royalbluegrocery.com" not in dumped


def test_place_search_is_empty_for_short_or_unknown_queries(env):
    http = client()
    assert http.get("/claim/places", query_string={"q": "r"}).get_json()["places"] == []
    assert http.get("/claim/places", query_string={"q": "zzzzzz"}).get_json()["places"] == []


# --- submit / channels -------------------------------------------------------


def test_listed_phone_submit_is_pending_and_does_not_take_claimant_phone(env):
    http = client()
    response = submit(http)
    assert response.status_code == 201
    body = response.get_json()
    assert body["status"] == "pending"
    assert body["channel"] == "listed_phone"
    assert body["token"]
    assert "listed_contact_used" not in body
    assert PHONE not in json.dumps(body)
    stored = load_claims(env["claims"])
    assert stored[0]["listed_contact_used"] == PHONE
    assert stored[0]["status"] == "pending"


def test_self_asserted_ownership_is_refused(env):
    http = client()
    for payload in (
        {"place_id": PLACE},
        {"place_id": PLACE, "channel": "self"},
        {"place_id": PLACE, "channel": "i_own_this"},
        {"place_id": PLACE, "channel": "listed_phone", "phone": "512-555-9999"},
    ):
        response = http.post("/claim", json=payload)
        assert response.status_code == 422, payload
        assert response.get_json()["error"] == "invalid claim"


def test_business_email_must_match_the_listing_domain(env):
    http = client()
    bad = submit(http, channel="business_email", email="owner@gmail.com")
    assert bad.status_code == 422
    good = submit(http, channel="business_email", email="mgr@royalbluegrocery.com")
    assert good.status_code == 201
    assert good.get_json()["status"] == "pending"


def test_in_store_code_must_match_the_team_issued_code(env):
    http = client()
    bad = submit(http, channel="in_store_code", code="WRONG")
    assert bad.status_code == 422
    good = submit(http, channel="in_store_code", code="DOOR-42")
    assert good.status_code == 201


def test_unavailable_channel_is_refused(env, tmp_path, monkeypatch):
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps({PLACE: cafe_row(phone=None, website=None)}), encoding="utf-8")
    monkeypatch.setenv("FRONTDOOR_MAP_DATASET", str(bare))
    monkeypatch.setenv("FRONTDOOR_CLAIM_CODES", str(tmp_path / "no-codes.json"))
    http = client()
    assert submit(http, channel="listed_phone").status_code == 422
    assert submit(http, channel="business_email", email="a@x.com").status_code == 422
    assert submit(http, channel="in_store_code", code="DOOR-42").status_code == 422


# --- public map is independent of claims -------------------------------------


def test_map_data_module_does_not_read_claims():
    from frontdoor_server import map_view
    src = inspect.getsource(map_view)
    assert "frontdoor.claims" not in src
    assert "FRONTDOOR_CLAIMS" not in src
    assert "load_claims" not in src


def test_a_claim_never_changes_the_public_pin(env):
    http = client()
    before = pin_state(http)
    assert before["state"] == STATE_NEUTRAL
    assert before["owner_confirmed"] is False
    assert before["state"] in STATES

    created = submit(http).get_json()
    pending = pin_state(http)
    assert pending["state"] == before["state"]
    assert pending["owner_confirmed"] is False
    assert "claim_id" not in pending
    assert "claim_status" not in pending

    approve(http, created["claim_id"])
    approved = pin_state(http)
    assert approved["state"] == before["state"]
    assert approved["owner_confirmed"] is False

    http.post(
        f"/claim/{created['claim_id']}/abandon",
        json={"token": created["token"]},
    )
    # A second claim, rejected, also leaves no public trace.
    other = submit(http).get_json()
    http.post(
        f"/claim/{other['claim_id']}/review",
        json={"action": "reject"},
        headers={"X-Frontdoor-Upload-Key": REVIEW_KEY},
    )
    after = pin_state(http)
    assert after["state"] == before["state"]
    assert after["owner_confirmed"] is False
    dumped = json.dumps(http.get("/map/data").get_json())
    assert created["claim_id"] not in dumped
    assert other["claim_id"] not in dumped


def test_review_is_manual_and_requires_the_upload_key(env):
    http = client()
    created = submit(http).get_json()
    url = f"/claim/{created['claim_id']}/review"
    assert http.post(url, json={"action": "approve"}).status_code == 401
    assert http.post(
        url, json={"action": "approve"},
        headers={"X-Frontdoor-Upload-Key": "wrong"},
    ).status_code == 401
    response = approve(http, created["claim_id"])
    assert response.status_code == 200
    assert response.get_json()["status"] == "approved"
    # Manual: nothing here flipped the pin.
    assert pin_state(http)["owner_confirmed"] is False


def test_claimant_get_needs_the_token_and_does_not_echo_listing_contact(env):
    http = client()
    created = submit(http).get_json()
    claim_id = created["claim_id"]
    assert http.get(f"/claim/{claim_id}").status_code == 404
    assert http.get(f"/claim/{claim_id}", query_string={"token": "nope"}).status_code == 404
    body = http.get(f"/claim/{claim_id}", query_string={"token": created["token"]}).get_json()
    assert body["status"] == "pending"
    assert PHONE not in json.dumps(body)
    assert "token" not in body


# --- workspace after approval ------------------------------------------------


def test_workspace_is_404_until_approved_then_shows_the_public_pin(env):
    http = client()
    created = submit(http).get_json()
    url = f"/claim/{created['claim_id']}/workspace"
    qs = {"token": created["token"]}
    assert http.get(url, query_string=qs).status_code == 404
    approve(http, created["claim_id"])
    body = http.get(url, query_string=qs).get_json()
    assert body["claim"]["status"] == "approved"
    assert body["pin"]["place_id"] == PLACE
    assert body["pin"]["state"] == STATE_NEUTRAL
    assert body["pin"]["owner_confirmed"] is False
    assert body["incentives"] == INCENTIVES_TEXT
    assert "ask your accountant" in body["incentives"]
    assert "tax advice" not in body["incentives"].lower()
    assert body["guided_capture"] == {
        "capture_kind": "in_app",
        "attested": True,
        "camera_roll": False,
    }


def test_rejected_claim_has_no_workspace(env):
    http = client()
    created = submit(http).get_json()
    http.post(
        f"/claim/{created['claim_id']}/review",
        json={"action": "reject"},
        headers={"X-Frontdoor-Upload-Key": REVIEW_KEY},
    )
    assert http.get(
        f"/claim/{created['claim_id']}/workspace",
        query_string={"token": created["token"]},
    ).status_code == 404
    body = http.get(
        f"/claim/{created['claim_id']}",
        query_string={"token": created["token"]},
    ).get_json()
    assert body["status"] == "rejected"


def test_dispute_does_not_change_the_public_pin(env):
    http = client()
    created = submit(http).get_json()
    approve(http, created["claim_id"])
    before = pin_state(http)
    response = http.post(
        f"/claim/{created['claim_id']}/dispute",
        json={"token": created["token"], "note": "The ramp photo is from the alley door."},
    )
    assert response.status_code == 200
    assert response.get_json()["dispute"].startswith("The ramp photo")
    after = pin_state(http)
    assert after == before


# --- owner-confirmed is attested in-app capture, not camera-roll -------------


def test_owner_attested_scan_sets_owner_confirmed_without_a_third_stamp_state():
    dataset = {PLACE: cafe_row()}
    community = new_scan_record(
        place_ref={"place_id": PLACE, "name": "Royal Blue Grocery",
                   "lat": 30.267, "lng": -97.743},
        created_at="2026-09-05T10:00:00Z",
        verdicts={"ramp_or_bevel": "present"},
        confidences={"ramp_or_bevel": 80},
        faces_blurred=0,
        quarantined_count=0,
        image_keys=[],
    )
    owner = dict(community)
    owner["scan_id"] = "owner1"
    owner["attested"] = True
    owner["capture_kind"] = "in_app"
    merged, _ = merge_scans(dataset, [community, owner])
    row = merged[PLACE]
    assert row["status"] == "verified"
    assert row["owner_confirmed"] is True
    pin = pin_for_row(PLACE, row)
    assert pin["state"] == STATE_VERIFIED
    assert pin["state"] in STATES
    assert pin["owner_confirmed"] is True


def test_community_scan_does_not_set_owner_confirmed():
    merged, _ = merge_scans({PLACE: cafe_row()}, [new_scan_record(
        place_ref={"place_id": PLACE, "name": "Royal Blue Grocery",
                   "lat": 30.267, "lng": -97.743},
        created_at="2026-09-05T10:00:00Z",
        verdicts={"ramp_or_bevel": "present"},
        confidences={"ramp_or_bevel": 80},
        faces_blurred=0,
        quarantined_count=0,
        image_keys=[],
    )])
    pin = pin_for_row(PLACE, merged[PLACE])
    assert pin["state"] == STATE_VERIFIED
    assert pin["owner_confirmed"] is False


def _publish_client():
    app = create_app()
    app.config[ENGINE_KEY] = FakeEngine()
    app.config[STORE_KEY] = FakeStore()
    return app.test_client()


def test_camera_roll_attested_publish_is_refused(env):
    http = _publish_client()
    created = submit(http).get_json()
    approve(http, created["claim_id"])
    form = {
        "place_id": PLACE, "name": "Royal Blue Grocery",
        "lat": "30.267", "lng": "-97.743",
        "capture_kind": "camera_roll", "attested": "1",
    }
    response = post_publish(http, [image_part("door.jpg")], form=form)
    assert response.status_code == 422
    assert load_scan_records(env["scans"]) == []
    assert pin_state(http)["owner_confirmed"] is False


def test_in_app_attested_publish_requires_an_approved_claim(env):
    http = _publish_client()
    form = {
        "place_id": PLACE, "name": "Royal Blue Grocery",
        "lat": "30.267", "lng": "-97.743",
        "capture_kind": "in_app", "attested": "1",
    }
    response = post_publish(http, [image_part("door.jpg")], form=form)
    assert response.status_code == 422
    created = submit(http).get_json()
    still = post_publish(http, [image_part("door.jpg")], form=form)
    assert still.status_code == 422
    approve(http, created["claim_id"])
    published = post_publish(http, [image_part("door.jpg")], form=form)
    assert published.status_code == 200
    assert published.get_json()["published"] is True
    pin = pin_state(http)
    assert pin["owner_confirmed"] is True
    assert pin["state"] == STATE_VERIFIED


def test_in_app_without_attestation_stays_community_scanned(env):
    http = _publish_client()
    form = {
        "place_id": PLACE, "name": "Royal Blue Grocery",
        "lat": "30.267", "lng": "-97.743",
        "capture_kind": "in_app",
    }
    body = post_publish(http, [image_part("door.jpg")], form=form).get_json()
    assert body["published"] is True
    pin = pin_state(http)
    assert pin["state"] == STATE_VERIFIED
    assert pin["owner_confirmed"] is False


def test_submit_claim_helper_refuses_unknown_places():
    with pytest.raises(ClaimError):
        submit_claim("unused.jsonl", place_id=PLACE, channel="listed_phone",
                     row=None, codes={})


def test_has_approved_claim_is_place_scoped(env):
    http = client()
    created = submit(http).get_json()
    assert has_approved_claim(env["claims"], PLACE) is False
    approve(http, created["claim_id"])
    assert has_approved_claim(env["claims"], PLACE) is True
    assert has_approved_claim(env["claims"], "ChIJother") is False


def test_map_page_links_owners_into_the_claim_flow(env):
    html = client().get("/map").get_data(as_text=True)
    assert 'id="owner-entry"' in html
    assert 'href="/app#claim"' in html
    assert "For business owners" in html


# --- the claimant's token must not have to travel in the URL -----------------
#
# It is the SOLE credential for an approved workspace, and a query string is written down along
# the way: the access log, the proxy's log, and -- for a client that puts one in a document URL
# rather than a fetch -- the browser's history and the Referer of everything that page loads.
# None of those can be revoked. Which of them apply is a property of the client, which is why
# the rule is "not in a URL at all" rather than a list of clients to keep checking.


def test_the_claim_token_never_has_to_travel_in_the_url(env):
    """Every claimant-authenticated handler accepts the token out of band.

    `/dispute` already read it from the body. `GET /claim/<id>` and `GET .../workspace` are
    GETs, which a browser cannot put a body on, so the header is what makes those two possible
    at all -- and it is then the one way that works for all four.
    """
    http = client()
    created = submit(http).get_json()
    claim_id = created["claim_id"]
    approve(http, claim_id)
    auth = {CLAIM_TOKEN_HEADER: created["token"]}

    got = http.get(f"/claim/{claim_id}", headers=auth)
    assert got.status_code == 200
    assert got.get_json()["status"] == "approved"

    workspace = http.get(f"/claim/{claim_id}/workspace", headers=auth)
    assert workspace.status_code == 200
    assert workspace.get_json()["pin"]["place_id"] == PLACE

    disputed = http.post(
        f"/claim/{claim_id}/dispute",
        json={"note": "The ramp photo is from the alley door."},
        headers=auth,
    )
    assert disputed.status_code == 200

    abandoned = http.post(f"/claim/{claim_id}/abandon", headers=auth)
    assert abandoned.status_code == 200
    assert abandoned.get_json()["status"] == "abandoned"


def test_a_wrong_token_in_the_header_is_refused_exactly_as_one_in_the_url_was(env):
    """The new route in must not be a way around the check it replaced."""
    http = client()
    claim_id = submit(http).get_json()["claim_id"]
    approve(http, claim_id)
    for header in ({CLAIM_TOKEN_HEADER: "nope"}, {CLAIM_TOKEN_HEADER: ""}, {}):
        assert http.get(f"/claim/{claim_id}", headers=header).status_code == 404
        assert http.get(f"/claim/{claim_id}/workspace", headers=header).status_code == 404


def test_the_query_string_token_still_works_for_exactly_one_release(env):
    """Deliberate, and deliberately temporary.

    The shipped `/app` page still sends `?token=`, and that page is not changed here. Removing
    the fallback in the same change would 404 every live workspace. This test is what makes the
    removal a decision someone takes rather than a line someone forgets: delete it together
    with the fallback, and not before the client sends the header.
    """
    http = client()
    created = submit(http).get_json()
    claim_id, token = created["claim_id"], created["token"]
    approve(http, claim_id)
    assert http.get(f"/claim/{claim_id}", query_string={"token": token}).status_code == 200
    assert http.get(
        f"/claim/{claim_id}/workspace", query_string={"token": token}
    ).status_code == 200


def test_the_url_is_read_in_one_place_so_the_fallback_can_be_deleted_in_one_edit():
    """Four handlers read the token; only the shared helper may look at the URL for it."""
    source = inspect.getsource(claim_view)
    assert source.count('request.args.get("token")') == 1, (
        "a handler reads the token straight out of the query string; the deprecated fallback "
        "has to live in one place or it will not all be removed at once"
    )
    assert source.count("_claimant_record(claim_id, _presented_token())") == 4, (
        "every claimant-authenticated handler must go through the shared reader: "
        "GET /claim/<id>, /abandon, /workspace and /dispute"
    )


def test_app_page_has_no_hardcoded_listings_and_opens_claim_from_hash():
    html = create_app().test_client().get("/app").get_data(as_text=True)
    assert "CLAIM_RESULTS" not in html
    assert "const CLAIM_API = '/claim';" in html
    assert "location.hash==='#claim'" in html
    assert 'id="claim-workspace"' in html
    assert 'id="claim-phone"' not in html
    assert "ask your accountant" in html
    assert "tax advice" not in html.lower()

