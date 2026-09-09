"""frontdoor.scan_records: the JSONL scan store and the never-negative merge (TICK-262, #270).

The merge is the map's legal shield extended to community data: whatever a
scan contains — adversarial, malformed, or honestly negative — merging it can
only ever ADD a pin or RAISE one. The battery here pins that property the way
test_map_states pins Green-or-Gray: by contract table, not by trusting the
implementation.
"""

import json
import logging
import threading

import pytest

from frontdoor.map_states import (
    OBSERVATION_NOT_ASSESSED,
    OBSERVATION_NOT_VISIBLE,
    OBSERVATION_VISIBLE,
    STATE_NEUTRAL,
    STATE_SCANNED,
    checklist_for_row,
    state_for_row,
)
from frontdoor.scan_records import (
    ScanRecordError,
    append_scan,
    is_scan_image_key,
    load_scan_records,
    load_scan_store,
    merge_scans,
    new_image_key,
    new_scan_record,
    physical_key,
    place_slug,
)

PLACE = "ChIJexample"


def precat_row(**overrides):
    base = {
        "place_id": PLACE,
        "name": "Example Cafe",
        "location": {"lat": 40.0, "lng": -75.0},
        "source": "streetview",
        "status": "ai_estimated",
        "imagery_date": "2024-06",
        "criteria": {
            "ramp_or_bevel": {"verdict": "present", "confidence": 0.9},
            "handrails": {"verdict": "not_visible", "confidence": 0.6},
        },
    }
    base.update(overrides)
    return base


def scan(**overrides):
    base = {
        "scan_id": "abc123",
        "place_ref": {"place_id": PLACE, "name": "Example Cafe",
                      "lat": 40.0, "lng": -75.0},
        "created_at": "2026-09-04T10:00:00Z",
        "verdicts": {key: "present" for key in (
            "ramp_or_bevel", "handrails",
            "accessible_door_hardware", "accessibility_signage")},
        "confidences": {key: 80 for key in (
            "ramp_or_bevel", "handrails",
            "accessible_door_hardware", "accessibility_signage")},
        "faces_blurred": 0,
        "quarantined_count": 0,
        "image_keys": ["scans/ChIJexample/" + "a" * 32 + ".jpg"],
        "contributor": None,
    }
    base.update(overrides)
    return base


# --- the JSONL store ---------------------------------------------------------


def test_append_writes_one_newline_terminated_json_line(tmp_path):
    path = tmp_path / "scans.jsonl"
    record = new_scan_record(
        place_ref={"place_id": PLACE}, created_at="2026-09-04T10:00:00Z",
        verdicts={"ramp_or_bevel": "present"}, confidences={"ramp_or_bevel": 80},
        faces_blurred=1, quarantined_count=0,
        image_keys=["scans/p/" + "a" * 32 + ".jpg"], contributor="tok-1",
    )
    append_scan(path, record)
    append_scan(path, record)
    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    lines = raw.decode("utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == record


def test_blur_regions_are_recorded_when_given_and_absent_otherwise():
    # Additive (#350): a record made without them carries no key, so nothing
    # reading older records has to change.
    kwargs = dict(
        place_ref={"place_id": PLACE}, created_at="2026-09-04T10:00:00Z",
        verdicts={"ramp_or_bevel": "present"}, confidences={"ramp_or_bevel": 80},
        faces_blurred=1, quarantined_count=0,
        image_keys=["scans/p/" + "a" * 32 + ".jpg"],
    )
    regions = [[{"x": 82, "y": 62, "w": 96, "h": 96}], []]
    assert new_scan_record(**kwargs, blur_regions=regions)["blur_regions"] == regions
    assert "blur_regions" not in new_scan_record(**kwargs)


def test_append_does_not_create_the_parent_directory(tmp_path):
    # A missing volume must stay missing: mkdir would invent /data inside the
    # container, publish would 200, and every scan would die with the process.
    path = tmp_path / "missing-volume" / "scans.jsonl"
    with pytest.raises(FileNotFoundError):
        append_scan(path, scan())
    assert not path.parent.exists()


def test_append_recovers_a_store_with_a_torn_last_line(tmp_path, caplog):
    # A worker killed mid-append leaves the file unterminated. Recover by
    # dropping the incomplete last line, then append; do not wedge forever.
    path = tmp_path / "scans.jsonl"
    path.write_bytes(json.dumps(scan()).encode() + b"\n" + b'{"scan_id": "partial"')
    with caplog.at_level(logging.WARNING):
        append_scan(path, scan(scan_id="new"))
    records = load_scan_records(path)
    assert [record["scan_id"] for record in records] == ["abc123", "new"]
    assert "partial" not in path.read_text(encoding="utf-8")
    assert "newline" in caplog.text.lower() or "interrupted" in caplog.text.lower()


def test_concurrent_appends_stay_line_separated(tmp_path):
    path = tmp_path / "scans.jsonl"
    threads = [
        threading.Thread(target=append_scan, args=(path, scan(scan_id=f"s{i}")))
        for i in range(20)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    records = load_scan_records(path)
    assert {record["scan_id"] for record in records} == {f"s{i}" for i in range(20)}


def test_load_is_total_over_missing_unreadable_and_junk(tmp_path):
    assert load_scan_records(tmp_path / "nope.jsonl") == []
    assert load_scan_records(None) == []
    path = tmp_path / "scans.jsonl"
    path.write_text(
        json.dumps(scan()) + "\n"
        + "not json at all\n"
        + '"a bare string"\n'
        + "\n"
        + json.dumps(scan(scan_id="s2")) + "\n",
        encoding="utf-8",
    )
    records = load_scan_records(path)
    assert [record["scan_id"] for record in records] == ["abc123", "s2"]


def test_load_reports_skipped_lines_and_logs_them(tmp_path, caplog):
    path = tmp_path / "scans.jsonl"
    path.write_text(
        json.dumps(scan()) + "\n"
        + "not json at all\n"
        + '"a bare string"\n'
        + "\n"
        + json.dumps(scan(scan_id="s2")) + "\n",
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING):
        result = load_scan_store(path)
    assert [record["scan_id"] for record in result.records] == ["abc123", "s2"]
    assert result.skipped == 2
    assert result.error is None
    assert "skipped" in caplog.text.lower()


def test_load_distinguishes_a_missing_file_from_a_missing_volume(tmp_path):
    missing_file = load_scan_store(tmp_path / "nope.jsonl")
    assert missing_file.records == []
    assert missing_file.error is None
    assert missing_file.skipped == 0

    missing_volume = load_scan_store(tmp_path / "not-mounted" / "scans.jsonl")
    assert missing_volume.records == []
    assert missing_volume.error is not None
    assert "unreadable" in missing_volume.error

    blocked = tmp_path / "blocked-dir"
    blocked.mkdir()
    unreadable = load_scan_store(blocked)
    assert unreadable.records == []
    assert unreadable.error is not None
    assert "unreadable" in unreadable.error


# --- image keys --------------------------------------------------------------


def test_new_image_key_matches_the_allowlist_and_embeds_the_place():
    key = new_image_key({"place_id": PLACE})
    assert is_scan_image_key(key)
    assert key.startswith(f"scans/{PLACE}/")


def test_place_slug_is_bounded_and_key_safe():
    assert place_slug({"place_id": PLACE}) == PLACE
    assert place_slug({"name": "Joe's Cafe & Bar"}) == "Joe-s-Cafe-Bar"
    assert place_slug({"name": "../../../etc"}) == "etc"
    assert place_slug({}) == "place"
    assert place_slug(None) == "place"
    assert len(place_slug({"place_id": "x" * 500})) <= 64
    for ref in ({"place_id": PLACE}, {"name": "Joe's Cafe & Bar"},
                {"name": "../.."}, {}, None):
        assert is_scan_image_key(new_image_key(ref))


@pytest.mark.parametrize("bad", [
    "open/cap-1",                              # a capture key, not a scan key
    "sealed/cap-1",                            # sealed material must not resolve
    "scans/../open/cap-1.jpg",                 # traversal via the slug
    "scans/a/../b/" + "a" * 32 + ".jpg",       # traversal via extra segments
    "scans/a/b/" + "a" * 32 + ".jpg",          # too many segments
    "scans/" + "a" * 32 + ".jpg",              # missing slug segment
    "scans/place/" + "a" * 32 + ".png",        # wrong extension
    "scans/place/" + "A" * 32 + ".jpg",        # uppercase hex is not a uuid hex
    "scans/place/" + "a" * 31 + ".jpg",        # short id
    "scans/pl.ce/" + "a" * 32 + ".jpg",        # dots cannot appear in the slug
    "scans/" + "x" * 65 + "/" + "a" * 32 + ".jpg",  # oversized slug
    "scans//" + "a" * 32 + ".jpg",             # empty slug
    "SCANS/place/" + "a" * 32 + ".jpg",        # prefix is case-exact
    "",
    None,
    42,
])
def test_only_keys_under_the_scans_prefix_resolve(bad):
    assert not is_scan_image_key(bad)
    with pytest.raises(ScanRecordError):
        physical_key(bad)


def test_physical_key_is_the_open_partition_twin():
    key = "scans/place/" + "a" * 32 + ".jpg"
    assert physical_key(key) == "open/" + key


# --- the never-negative merge ------------------------------------------------


def _obs(row):
    return {item["key"]: item["observation"] for item in checklist_for_row(row)}


_RANK = {OBSERVATION_NOT_ASSESSED: 0, OBSERVATION_NOT_VISIBLE: 1,
         OBSERVATION_VISIBLE: 2}
_STATE_RANK = {STATE_NEUTRAL: 0, STATE_SCANNED: 1}

# Base rows and scans chosen to include the downgrade attempts: honest
# all-absent scans, adversarial verdicts, junk shapes.
BASE_ROWS = [
    precat_row(),
    precat_row(status="verified", source="onsite_visit"),
    precat_row(criteria={key: {"verdict": "present", "confidence": 1.0}
                         for key in ("ramp_or_bevel", "handrails",
                                     "accessible_door_hardware",
                                     "accessibility_signage")}),
    {"place_id": PLACE, "location": {"lat": 40.0, "lng": -75.0}},
    None,
]
SCANS = [
    scan(),
    scan(verdicts={key: "absent" for key in (
        "ramp_or_bevel", "handrails",
        "accessible_door_hardware", "accessibility_signage")}),
    scan(verdicts={"ramp_or_bevel": "not_visible"}),
    scan(verdicts={"ramp_or_bevel": "dangerous", "handrails": None}),
    scan(verdicts={}, confidences=None),
]


@pytest.mark.parametrize("base", BASE_ROWS)
@pytest.mark.parametrize("record", SCANS)
def test_merge_never_downgrades_state_or_any_observation(base, record):
    dataset = {PLACE: base} if base is not None else {}
    merged, _ = merge_scans(dataset, [record])
    before, after = dataset.get(PLACE), merged[PLACE]
    assert _STATE_RANK[state_for_row(after)] >= _STATE_RANK[state_for_row(before)]
    obs_before, obs_after = _obs(before), _obs(after)
    for key in obs_before:
        assert _RANK[obs_after[key]] >= _RANK[obs_before[key]], (
            f"criterion {key} downgraded from {obs_before[key]} to {obs_after[key]}"
        )


def test_an_already_verified_row_is_left_exactly_as_it_is():
    base = precat_row(status="verified", source="onsite_visit",
                      imagery_date="2027-01-01")
    merged, _ = merge_scans({PLACE: base}, [scan(verdicts={})])
    after = merged[PLACE]
    assert after["status"] == "verified"
    assert after["source"] == "onsite_visit"
    assert after["imagery_date"] == "2027-01-01"


def test_a_scan_upgrades_a_neutral_pin_to_the_verified_scanned_state():
    merged, meta = merge_scans({PLACE: precat_row()}, [scan()])
    row = merged[PLACE]
    assert state_for_row(row) == STATE_SCANNED
    assert row["source"] == "community_scan"
    # Freshness moved forward to the scan's date.
    assert row["imagery_date"] == "2026-09-04"
    # "photos" joined this mapping with TICK-494: the scan's stored
    # photographs, so the receipt the pin points at has something to show.
    assert meta == {PLACE: {
        "scan_count": 1,
        "last_scanned": "2026-09-04",
        "photos": ["scans/ChIJexample/" + "a" * 32 + ".jpg"],
    }}


def test_scan_confidences_stay_on_the_one_public_scale():
    """TICK-462, #462 — this test used to assert the opposite.

    It pinned a division by 100 into the map's supposed 0-1 range, and that
    division was the second scale: the pre-catalogue rows the merge writes
    into are on the engine's 0-100 scale, so a merged row could carry 20.0
    beside 0.8 and /map/data served both as `confidence`. The merge is
    monotone and only replaces an entry the scan RAISES, so the rescaled
    values were the model's most confident readings, and a percentage
    renderer showed 0.8 as 1%.
    """
    merged, _ = merge_scans({}, [scan()])
    row = merged[PLACE]
    entry = row["criteria"]["accessible_door_hardware"]
    assert entry == {"verdict": "present", "confidence": 80}


def test_freshness_is_monotone_across_scans():
    older = scan(scan_id="old", created_at="2025-01-02T00:00:00Z")
    newer = scan(scan_id="new", created_at="2026-09-04T00:00:00Z")
    merged, meta = merge_scans({PLACE: precat_row()}, [newer, older])
    assert merged[PLACE]["imagery_date"] == "2026-09-04"
    # The photographs are the newer scan's, whichever order the store was
    # read in -- one scan's frames, dated by the same scan (TICK-494).
    assert meta[PLACE] == {
        "scan_count": 2,
        "last_scanned": "2026-09-04",
        "photos": ["scans/ChIJexample/" + "a" * 32 + ".jpg"],
    }


def test_a_scan_matches_by_distance_and_name_without_a_place_id():
    record = scan(place_ref={"name": "Example Cafe",
                             "lat": 40.0001, "lng": -75.0001})  # ~14 m away
    merged, meta = merge_scans({PLACE: precat_row()}, [record])
    assert list(merged) == [PLACE]
    assert state_for_row(merged[PLACE]) == STATE_SCANNED
    assert PLACE in meta


def test_a_disagreeing_name_nearby_does_not_match_and_adds_its_own_pin():
    record = scan(scan_id="s9",
                  place_ref={"name": "Completely Different Deli",
                             "lat": 40.0001, "lng": -75.0001})
    merged, _ = merge_scans({PLACE: precat_row()}, [record])
    assert state_for_row(merged[PLACE]) == STATE_NEUTRAL  # untouched
    new_key = next(k for k in merged if k != PLACE)
    assert new_key == "scan:s9"
    assert state_for_row(merged[new_key]) == STATE_SCANNED
    assert merged[new_key]["name"] == "Completely Different Deli"
    assert merged[new_key]["location"] == {"lat": 40.0001, "lng": -75.0001}


def test_a_scan_for_an_unknown_place_id_adds_a_row_under_it():
    record = scan(place_ref={"place_id": "ChIJnew", "name": "New Spot",
                             "lat": 41.0, "lng": -76.0})
    merged, meta = merge_scans({PLACE: precat_row()}, [record])
    assert state_for_row(merged["ChIJnew"]) == STATE_SCANNED
    assert meta["ChIJnew"]["scan_count"] == 1


def test_merge_is_total_over_junk_scans_and_junk_datasets():
    junk_scans = [None, 42, "scan", {}, {"verdicts": {}},
                  {"created_at": "not-a-date", "verdicts": {}},
                  scan(created_at=None), scan(verdicts="present")]
    merged, meta = merge_scans({PLACE: precat_row()}, junk_scans)
    assert merged == {PLACE: precat_row()}
    assert meta == {}
    for dataset in (None, [], "junk", 7):
        merged, meta = merge_scans(dataset, [scan()])
        assert state_for_row(merged[PLACE]) == STATE_SCANNED
    merged, meta = merge_scans({PLACE: precat_row()}, "not-a-list")
    assert merged == {PLACE: precat_row()}


def test_adversarial_verdicts_never_become_visible_observations():
    record = scan(verdicts={"ramp_or_bevel": "definitely_accessible",
                            "handrails": {"verdict": "present"}})
    merged, _ = merge_scans({}, [record])
    obs = _obs(merged[PLACE])
    assert obs["ramp_or_bevel"] == OBSERVATION_NOT_ASSESSED
    assert obs["handrails"] == OBSERVATION_NOT_ASSESSED
    assert OBSERVATION_VISIBLE not in obs.values()
