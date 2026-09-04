"""Tests for the Street View batch pre-catalogue (TICK-248, #170).

No live HTTP and no live model calls: every test injects fake fetchers and a
stub screening engine.
"""

import json

import pytest

from frontdoor.precatalogue import (
    CENSUS_FILENAME,
    DATASET_FILENAME,
    PLACES_SEARCH_URL,
    STOREFRONT_PLACE_TYPES,
    STREETVIEW_IMAGE_URL,
    STREETVIEW_METADATA_URL,
    SUMMARY_FILENAME,
    ConfigError,
    MapsCallCapError,
    NEARBY_SEARCH_MAX_RESULTS,
    PAGE_TOKEN_DELAY_S,
    MapsCallCounter,
    PrecatalogueError,
    bearing_deg,
    enumerate_places,
    load_api_key,
    load_demo_area,
    run_census,
    run_precatalogue,
    storefront_headings,
)
from frontdoor.screening import CRITERIA_KEYS, ImageAssessment, SpendCapError

API_KEY = "test-maps-key"


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", API_KEY)


def write_config(tmp_path, **overrides):
    config = {
        "name": "test-area",
        "bounding_box": {
            "south": 30.0, "west": -97.8, "north": 30.01, "east": -97.79,
        },
        "headings_per_business": 3,
        "max_maps_calls": 100,
    }
    config.update(overrides)
    for key in [k for k, v in config.items() if v is None]:
        del config[key]
    path = tmp_path / "demo_area.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def place(pid, name="Shop", lat=30.005, lng=-97.795):
    return {
        "place_id": pid,
        "name": name,
        "geometry": {"location": {"lat": lat, "lng": lng}},
    }


def metadata_ok(date="2024-06", pano="pano-1", lat=30.0049, lng=-97.7951):
    return {
        "status": "OK",
        "date": date,
        "pano_id": pano,
        "location": {"lat": lat, "lng": lng},
    }


class FakeClock:
    """Records sleeps instead of taking them."""

    def __init__(self):
        self.slept = []

    def __call__(self, seconds):
        self.slept.append(seconds)


class FakeFetcher:
    """Records calls; answers by URL from queues (metadata/places) or a
    constant (images)."""

    def __init__(self, places_pages=(), metadata=()):
        self.places_pages = list(places_pages)
        self.metadata = list(metadata)
        self.calls = []

    def fetch_json(self, url, params):
        self.calls.append((url, dict(params)))
        if url == PLACES_SEARCH_URL:
            return self.places_pages.pop(0)
        if url == STREETVIEW_METADATA_URL:
            return self.metadata.pop(0)
        raise AssertionError(f"unexpected JSON fetch: {url}")

    def fetch_bytes(self, url, params):
        self.calls.append((url, dict(params)))
        assert url == STREETVIEW_IMAGE_URL
        return b"jpeg-bytes-" + str(params["heading"]).encode()

    def params_for(self, url):
        return [p for u, p in self.calls if u == url]


class StubEngine:
    """Stands in for ScreeningEngine: assess_image plus spent_usd."""

    def __init__(self, verdict="present", usd_per_image=0.05, fail_after=None):
        self.verdict = verdict
        self.usd_per_image = usd_per_image
        self.fail_after = fail_after
        self.images = []
        self.spent_usd = 0.0

    def assess_image(self, image, *, media_type="image/jpeg"):
        if self.fail_after is not None and len(self.images) >= self.fail_after:
            raise SpendCapError("over the cap")
        self.images.append(image)
        self.spent_usd += self.usd_per_image
        return ImageAssessment(
            criteria={
                key: {"verdict": self.verdict, "confidence": 80,
                      "evidence": f"{key} seen"}
                for key in CRITERIA_KEYS
            },
            latency_s=0.01,
        )


def run(tmp_path, fetcher, engine, config_path=None, **kwargs):
    area = load_demo_area(config_path or write_config(tmp_path))
    return run_precatalogue(
        area=area,
        out_dir=tmp_path / "out",
        engine=engine,
        fetch_json=fetcher.fetch_json,
        fetch_bytes=fetcher.fetch_bytes,
        **{"sleep": FakeClock(), **kwargs},
    )


# ---------------------------------------------------------------- config


def test_valid_bounding_box_config_loads(tmp_path):
    area = load_demo_area(write_config(tmp_path))
    assert area.name == "test-area"
    assert len(area.blocks) == 1
    block = area.blocks[0]
    assert block["lat"] == pytest.approx(30.005)
    assert block["lng"] == pytest.approx(-97.795)
    assert block["radius_m"] > 0
    assert area.headings_per_business == 3
    assert area.max_maps_calls == 100


def test_committed_demo_area_config_is_valid():
    area = load_demo_area()
    assert area.blocks
    assert 2 <= area.headings_per_business <= 4


def test_blocks_config_loads(tmp_path):
    path = write_config(
        tmp_path,
        bounding_box=None,
        blocks=[{"name": "b1", "lat": 30.0, "lng": -97.8, "radius_m": 120}],
    )
    area = load_demo_area(path)
    assert area.blocks[0]["name"] == "b1"
    assert area.blocks[0]["radius_m"] == 120


@pytest.mark.parametrize("overrides", [
    {"bounding_box": None},  # neither area definition
    {"blocks": []},  # both defined (and blocks empty)
    {"bounding_box": {"south": 31, "west": -97.8, "north": 30, "east": -97.79}},
    {"bounding_box": {"south": 30, "west": -97.79, "north": 31, "east": -97.8}},
    {"bounding_box": {"south": 30, "west": -97.8, "north": 31}},
    {"name": ""},
    {"headings_per_business": 1},
    {"headings_per_business": 5},
    {"headings_per_business": None},
    {"max_maps_calls": 0},
    {"max_maps_calls": -3},
    {"max_maps_calls": None},
])
def test_invalid_config_rejected(tmp_path, overrides):
    with pytest.raises(ConfigError):
        load_demo_area(write_config(tmp_path, **overrides))


def test_invalid_block_entries_rejected(tmp_path):
    path = write_config(
        tmp_path, bounding_box=None,
        blocks=[{"name": "b1", "lat": 30.0, "lng": -97.8, "radius_m": -5}],
    )
    with pytest.raises(ConfigError):
        load_demo_area(path)


def test_missing_config_file_is_a_clear_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_demo_area(tmp_path / "nope.json")


# ---------------------------------------------------------------- API key


def test_missing_api_key_is_a_clear_error():
    with pytest.raises(PrecatalogueError, match="GOOGLE_MAPS_API_KEY"):
        load_api_key(env={})


def test_blank_api_key_is_a_clear_error():
    with pytest.raises(PrecatalogueError, match="GOOGLE_MAPS_API_KEY"):
        load_api_key(env={"GOOGLE_MAPS_API_KEY": "   "})


def test_run_fails_fast_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    area = load_demo_area(write_config(tmp_path))
    with pytest.raises(PrecatalogueError, match="GOOGLE_MAPS_API_KEY"):
        run_precatalogue(area=area, out_dir=tmp_path / "out",
                         engine=StubEngine())


# ---------------------------------------------------------------- enumeration


def test_enumeration_pages_and_dedupes(tmp_path):
    fetcher = FakeFetcher(places_pages=[
        {"status": "OK", "results": [place("p1"), place("p2")],
         "next_page_token": "tok"},
        {"status": "OK", "results": [place("p2"), place("p3")]},
    ])
    area = load_demo_area(write_config(tmp_path))
    counter = MapsCallCounter(area.max_maps_calls)
    found = enumerate_places(area, API_KEY, counter, fetcher.fetch_json,
                             FakeClock())
    places = list(found.places)
    assert [p["place_id"] for p in places] == ["p1", "p2", "p3"]
    assert places[0]["location"] == {"lat": 30.005, "lng": -97.795}
    assert counter.counts["places"] == 2
    assert found.truncated_blocks == ()
    assert fetcher.params_for(PLACES_SEARCH_URL)[1] == {
        "pagetoken": "tok", "key": API_KEY}


def test_enumeration_error_status_raises(tmp_path):
    fetcher = FakeFetcher(places_pages=[{"status": "REQUEST_DENIED"}])
    area = load_demo_area(write_config(tmp_path))
    with pytest.raises(PrecatalogueError, match="REQUEST_DENIED"):
        enumerate_places(area, API_KEY, MapsCallCounter(10),
                         fetcher.fetch_json, FakeClock())


# ---------------------------------------------------------------- headings


def test_bearing_cardinal_directions():
    assert bearing_deg(0, 0, 1, 0) == pytest.approx(0.0)
    assert bearing_deg(0, 0, 0, 1) == pytest.approx(90.0)
    assert bearing_deg(1, 0, 0, 0) == pytest.approx(180.0)
    assert bearing_deg(0, 1, 0, 0) == pytest.approx(270.0)


def test_storefront_headings_face_the_business():
    pano = {"lat": 30.0, "lng": -97.8}
    business = {"lat": 30.0, "lng": -97.7999}  # due east of the pano
    headings = storefront_headings(pano, business, 3)
    assert headings == [60.0, 90.0, 120.0]
    assert len(storefront_headings(pano, business, 2)) == 2
    assert len(storefront_headings(pano, business, 4)) == 4


def test_storefront_headings_coincident_points_fall_back_north():
    point = {"lat": 30.0, "lng": -97.8}
    assert storefront_headings(point, dict(point), 3) == [330.0, 0.0, 30.0]


# ---------------------------------------------------------------- batch run


def test_covered_business_is_screened_with_imagery_date(tmp_path, env):
    fetcher = FakeFetcher(
        places_pages=[{"status": "OK", "results": [place("p1")]}],
        metadata=[metadata_ok(date="2023-11")],
    )
    engine = StubEngine()
    summary = run(tmp_path, fetcher, engine)

    dataset = json.loads(
        (tmp_path / "out" / DATASET_FILENAME).read_text(encoding="utf-8"))
    row = dataset["p1"]
    assert row["covered"] is True
    assert row["imagery_date"] == "2023-11"
    assert len(row["headings"]) == 3
    assert set(row["criteria"]) == set(CRITERIA_KEYS)
    for entry in row["criteria"].values():
        assert entry["verdict"] == "present"
        assert entry["confidence"] == 80
        assert entry["flip_rate"] == 0.0
    # one image fetched and screened per heading
    assert len(engine.images) == 3
    image_params = fetcher.params_for(STREETVIEW_IMAGE_URL)
    assert [p["heading"] for p in image_params] == row["headings"]
    assert all(p["pano"] == "pano-1" for p in image_params)
    assert summary["screened"] == 1


def test_uncovered_business_recorded_not_dropped(tmp_path, env):
    fetcher = FakeFetcher(
        places_pages=[{"status": "OK", "results": [place("p1"), place("p2")]}],
        metadata=[{"status": "ZERO_RESULTS"}, metadata_ok()],
    )
    engine = StubEngine()
    summary = run(tmp_path, fetcher, engine)

    dataset = json.loads(
        (tmp_path / "out" / DATASET_FILENAME).read_text(encoding="utf-8"))
    assert set(dataset) == {"p1", "p2"}
    uncovered = dataset["p1"]
    assert uncovered["covered"] is False
    assert uncovered["coverage_status"] == "ZERO_RESULTS"
    assert uncovered["criteria"] is None
    # no image was fetched (and none screened) for the uncovered business
    assert len(fetcher.params_for(STREETVIEW_IMAGE_URL)) == 3
    assert len(engine.images) == 3
    assert summary["covered"] == 1
    assert summary["uncovered"] == 1


def test_every_row_flagged_streetview_ai_estimated(tmp_path, env):
    fetcher = FakeFetcher(
        places_pages=[{"status": "OK", "results": [place("p1"), place("p2")]}],
        metadata=[{"status": "ZERO_RESULTS"}, metadata_ok()],
    )
    run(tmp_path, fetcher, StubEngine())
    dataset = json.loads(
        (tmp_path / "out" / DATASET_FILENAME).read_text(encoding="utf-8"))
    assert len(dataset) == 2
    for row in dataset.values():
        assert row["source"] == "streetview"
        assert row["status"] == "ai_estimated"


def test_rerun_is_idempotent_and_resumes(tmp_path, env):
    pages = [{"status": "OK", "results": [place("p1"), place("p2")]}]
    first = FakeFetcher(places_pages=[json.loads(json.dumps(pages[0]))],
                        metadata=[metadata_ok(), metadata_ok(pano="pano-2")])
    engine = StubEngine(fail_after=3)  # p1 screens fine, p2's first image trips
    summary1 = run(tmp_path, first, engine)
    assert summary1["stopped"] and "SpendCapError" in summary1["stopped"]
    dataset1 = json.loads(
        (tmp_path / "out" / DATASET_FILENAME).read_text(encoding="utf-8"))
    assert set(dataset1) == {"p1"}  # p2's row was never written

    second = FakeFetcher(places_pages=[json.loads(json.dumps(pages[0]))],
                         metadata=[metadata_ok(date="2024-01", pano="pano-2")])
    engine2 = StubEngine(verdict="not_visible")
    summary2 = run(tmp_path, second, engine2)

    dataset2 = json.loads(
        (tmp_path / "out" / DATASET_FILENAME).read_text(encoding="utf-8"))
    assert set(dataset2) == {"p1", "p2"}
    # p1 kept its first-run row untouched: not refetched, not rescreened
    assert dataset2["p1"] == dataset1["p1"]
    assert dataset2["p2"]["imagery_date"] == "2024-01"
    assert summary2["skipped_existing"] == 1
    # second run made no metadata/image calls for p1
    assert len(second.params_for(STREETVIEW_METADATA_URL)) == 1
    assert len(second.params_for(STREETVIEW_IMAGE_URL)) == 3
    assert len(engine2.images) == 3
    assert summary2["stopped"] is None


def test_summary_math_and_call_counts(tmp_path, env):
    fetcher = FakeFetcher(
        places_pages=[{"status": "OK",
                       "results": [place("p1"), place("p2"), place("p3")]}],
        metadata=[metadata_ok(), {"status": "ZERO_RESULTS"}, metadata_ok()],
    )
    engine = StubEngine(usd_per_image=0.05)
    summary = run(tmp_path, fetcher, engine)

    assert summary["businesses_enumerated"] == 3
    assert summary["covered"] == 2
    assert summary["uncovered"] == 1
    assert summary["screened"] == 2
    assert summary["covered"] + summary["uncovered"] == \
        summary["businesses_enumerated"]
    assert summary["maps_api_calls"] == {
        "places": 1, "metadata": 3, "image": 6, "total": 10}
    assert summary["model_spend_usd_estimate"] == pytest.approx(0.30)
    assert summary["wall_clock_s"] >= 0
    assert summary["stopped"] is None

    written = json.loads(
        (tmp_path / "out" / SUMMARY_FILENAME).read_text(encoding="utf-8"))
    assert written == json.loads(json.dumps(summary))


def test_maps_call_cap_stops_cleanly_and_is_resumable(tmp_path, env):
    config = write_config(tmp_path, max_maps_calls=6)
    # 1 places + (1 metadata + 3 images) for p1 = 5; p2's metadata would be 6
    # (allowed) but its first image would be call 7 - over the cap of 6.
    fetcher = FakeFetcher(
        places_pages=[{"status": "OK", "results": [place("p1"), place("p2")]}],
        metadata=[metadata_ok(), metadata_ok(pano="pano-2")],
    )
    engine = StubEngine()
    summary = run(tmp_path, fetcher, engine, config_path=config)

    assert summary["stopped"] and "MapsCallCapError" in summary["stopped"]
    assert summary["maps_api_calls"]["total"] == 6
    dataset = json.loads(
        (tmp_path / "out" / DATASET_FILENAME).read_text(encoding="utf-8"))
    assert set(dataset) == {"p1"}  # p1 finished; p2 resumes on re-run


def test_assessment_errors_recorded_per_row(tmp_path, env):
    class ErrorEngine(StubEngine):
        def assess_image(self, image, *, media_type="image/jpeg"):
            self.images.append(image)
            return ImageAssessment(criteria=None, latency_s=0.01,
                                   error="ScreeningError: model refused")

    fetcher = FakeFetcher(
        places_pages=[{"status": "OK", "results": [place("p1")]}],
        metadata=[metadata_ok()],
    )
    summary = run(tmp_path, fetcher, ErrorEngine())
    dataset = json.loads(
        (tmp_path / "out" / DATASET_FILENAME).read_text(encoding="utf-8"))
    row = dataset["p1"]
    assert row["covered"] is True
    assert len(row["assessment_errors"]) == 3
    # no view produced a valid verdict: honest None, still ai_estimated
    assert all(entry["verdict"] is None for entry in row["criteria"].values())
    assert summary["screened"] == 1


def test_no_api_key_in_dataset_or_summary(tmp_path, env):
    fetcher = FakeFetcher(
        places_pages=[{"status": "OK", "results": [place("p1")]}],
        metadata=[metadata_ok()],
    )
    run(tmp_path, fetcher, StubEngine())
    for name in (DATASET_FILENAME, SUMMARY_FILENAME):
        text = (tmp_path / "out" / name).read_text(encoding="utf-8")
        assert API_KEY not in text


# ------------------------------------------------- live-API behaviour (#177)
# Every test above mocks the network, which is right, but it means the suite
# only ever sees the API behaving as the code expects. These cover the ways
# the real Places and Street View endpoints differ from that.


def test_a_paged_request_waits_for_the_token_to_become_valid(tmp_path):
    """A next_page_token is not valid the moment it is issued.

    Without the wait the second page answers INVALID_REQUEST and the run dies,
    so any area with more than 20 businesses -- every area worth doing -- never
    completes.
    """
    fetcher = FakeFetcher(places_pages=[
        {"status": "OK", "results": [place("p1")], "next_page_token": "tok"},
        {"status": "OK", "results": [place("p2")]},
    ])
    clock = FakeClock()
    area = load_demo_area(write_config(tmp_path))
    enumerate_places(area, API_KEY, MapsCallCounter(10), fetcher.fetch_json,
                     clock)
    assert clock.slept == [PAGE_TOKEN_DELAY_S], (
        "exactly the paged request waits; the first page must not"
    )


def test_invalid_request_on_a_paged_call_is_retried(tmp_path):
    fetcher = FakeFetcher(places_pages=[
        {"status": "OK", "results": [place("p1")], "next_page_token": "tok"},
        {"status": "INVALID_REQUEST"},
        {"status": "OK", "results": [place("p2")]},
    ])
    clock = FakeClock()
    found = enumerate_places(
        load_demo_area(write_config(tmp_path)), API_KEY, MapsCallCounter(10),
        fetcher.fetch_json, clock)
    assert [p["place_id"] for p in found.places] == ["p1", "p2"]
    assert len(clock.slept) == 2


def test_invalid_request_without_a_token_is_not_retried(tmp_path):
    """A first-page INVALID_REQUEST is a malformed query. Retrying it burns
    calls against the cap and cannot succeed."""
    fetcher = FakeFetcher(places_pages=[{"status": "INVALID_REQUEST"}])
    counter = MapsCallCounter(10)
    with pytest.raises(PrecatalogueError, match="INVALID_REQUEST"):
        enumerate_places(load_demo_area(write_config(tmp_path)), API_KEY,
                         counter, fetcher.fetch_json, FakeClock())
    assert counter.counts["places"] == 1


def test_results_outside_the_declared_box_are_dropped(tmp_path):
    """The circle covering a box is nearly twice its area. Businesses in the
    margin are not in the demo area and must not reach the map."""
    fetcher = FakeFetcher(places_pages=[{"status": "OK", "results": [
        place("inside", lat=30.005, lng=-97.795),
        place("north-of-it", lat=30.02, lng=-97.795),
        place("east-of-it", lat=30.005, lng=-97.70),
    ]}])
    found = enumerate_places(
        load_demo_area(write_config(tmp_path)), API_KEY, MapsCallCounter(10),
        fetcher.fetch_json, FakeClock())
    assert [p["place_id"] for p in found.places] == ["inside"]


def test_a_result_without_coordinates_is_dropped(tmp_path):
    """It cannot be coverage-checked: its location would reach the metadata
    endpoint as the string "None,None"."""
    nowhere = {"place_id": "no-geo", "name": "Shop", "geometry": {}}
    fetcher = FakeFetcher(places_pages=[
        {"status": "OK", "results": [nowhere, place("ok")]}])
    found = enumerate_places(
        load_demo_area(write_config(tmp_path)), API_KEY, MapsCallCounter(10),
        fetcher.fetch_json, FakeClock())
    assert [p["place_id"] for p in found.places] == ["ok"]


def test_a_block_returning_the_api_maximum_is_reported_as_truncated(tmp_path):
    """Nearby Search stops at 60. A full list is indistinguishable from a
    complete one in the response, so the summary has to say so."""
    full = [place(f"p{i}") for i in range(NEARBY_SEARCH_MAX_RESULTS)]
    fetcher = FakeFetcher(places_pages=[{"status": "OK", "results": full}])
    found = enumerate_places(
        load_demo_area(write_config(tmp_path)), API_KEY, MapsCallCounter(10),
        fetcher.fetch_json, FakeClock())
    assert found.truncated_blocks == ("test-area",)


def test_the_summary_names_truncated_blocks(tmp_path, env):
    full = [place(f"p{i}") for i in range(NEARBY_SEARCH_MAX_RESULTS)]
    fetcher = FakeFetcher(
        places_pages=[{"status": "OK", "results": full}],
        metadata=[{"status": "ZERO_RESULTS"}] * NEARBY_SEARCH_MAX_RESULTS,
    )
    summary = run(tmp_path, fetcher, StubEngine())
    assert summary["truncated_blocks"] == ["test-area"]


def test_metadata_ok_without_a_pano_id_is_uncovered_not_a_crash(tmp_path, env):
    """Requesting an image with an empty pano is a 400 that would end the
    batch. Nothing to look at is the same as no coverage."""
    fetcher = FakeFetcher(
        places_pages=[{"status": "OK", "results": [place("p1")]}],
        metadata=[{"status": "OK", "date": "2024-06", "location": {
            "lat": 30.005, "lng": -97.795}}],
    )
    summary = run(tmp_path, fetcher, StubEngine())
    row = json.loads(
        (tmp_path / "out" / DATASET_FILENAME).read_text())["p1"]
    assert row["covered"] is False
    assert row["coverage_status"] == "NO_PANO_ID"
    assert summary["stopped"] is None
    assert fetcher.params_for(STREETVIEW_IMAGE_URL) == []


def test_an_unexpected_failure_still_writes_the_summary(tmp_path, env):
    """The rows survive -- they are flushed per row -- but what they cost is
    only recorded in the summary."""
    class Exploding(FakeFetcher):
        def fetch_bytes(self, url, params):
            raise TimeoutError("street view timed out")

    fetcher = Exploding(
        places_pages=[{"status": "OK", "results": [place("p1")]}],
        metadata=[metadata_ok()],
    )
    summary = run(tmp_path, fetcher, StubEngine())
    assert summary["stopped_is_error"] is True
    assert "TimeoutError" in summary["stopped"]
    # places + metadata + the image call that was billed before it failed.
    # Preserving exactly this is why the summary must survive a crash.
    assert summary["maps_api_calls"] == {
        "places": 1, "metadata": 1, "image": 1, "total": 3}
    assert (tmp_path / "out" / SUMMARY_FILENAME).exists()


def test_a_cap_stop_is_not_reported_as_an_error(tmp_path, env):
    fetcher = FakeFetcher(
        places_pages=[{"status": "OK", "results": [place("p1")]}],
        metadata=[metadata_ok()],
    )
    summary = run(tmp_path, fetcher, StubEngine(fail_after=0))
    assert summary["stopped_is_error"] is False
    assert "SpendCapError" in summary["stopped"]


# ------------------------------- storefront-type sweeps (TICK-248 round two)
# One type=establishment sweep truncates at 60 on office towers where every
# suite is an establishment. Targeted per-type sweeps change what competes for
# the 60 slots; these tests cover the union, the per-type truncation report,
# and that a config without place_types behaves exactly as before.


def test_config_without_place_types_keeps_the_establishment_sweep(tmp_path):
    """Backward compatibility: the extended config shape is opt-in."""
    fetcher = FakeFetcher(places_pages=[
        {"status": "OK", "results": [place("p1")]}])
    area = load_demo_area(write_config(tmp_path))
    assert area.sweep_types == ("establishment",)
    enumerate_places(area, API_KEY, MapsCallCounter(10), fetcher.fetch_json,
                     FakeClock())
    sweeps = fetcher.params_for(PLACES_SEARCH_URL)
    assert [p["type"] for p in sweeps] == ["establishment"]


def test_place_types_config_loads_and_orders_sweeps(tmp_path):
    area = load_demo_area(write_config(
        tmp_path, place_types=["restaurant", "cafe"]))
    assert area.place_types == ("restaurant", "cafe")
    assert area.sweep_types == ("restaurant", "cafe")
    with_extra = load_demo_area(write_config(
        tmp_path, place_types=["restaurant"],
        include_establishment_sweep=True))
    assert with_extra.sweep_types == ("restaurant", "establishment")


@pytest.mark.parametrize("overrides", [
    {"place_types": []},
    {"place_types": ["restaurant", 7]},
    {"place_types": ["restaurant", "  "]},
    {"place_types": ["restaurant", "restaurant"]},  # a paid-for no-op sweep
    {"place_types": "restaurant"},
    {"place_types": ["restaurant"], "include_establishment_sweep": "yes"},
    {"include_establishment_sweep": True},  # no-op without place_types
])
def test_invalid_place_types_config_rejected(tmp_path, overrides):
    with pytest.raises(ConfigError):
        load_demo_area(write_config(tmp_path, **overrides))


def test_committed_demo_config_uses_the_curated_storefront_types():
    """The rationale for the list lives on STOREFRONT_PLACE_TYPES in the
    module; this keeps the committed demo config from drifting away from the
    documented list."""
    area = load_demo_area()
    assert area.place_types == STOREFRONT_PLACE_TYPES
    assert area.include_establishment_sweep is True


def test_type_sweeps_union_and_dedupe_by_place_id(tmp_path):
    """A cafe that is also a restaurant comes back from both sweeps; it must
    appear once, remembering which sweeps returned it."""
    fetcher = FakeFetcher(places_pages=[
        {"status": "OK", "results": [place("r1"), place("both")]},
        {"status": "OK", "results": [place("both"), place("c1")]},
    ])
    area = load_demo_area(write_config(
        tmp_path, place_types=["restaurant", "cafe"]))
    found = enumerate_places(area, API_KEY, MapsCallCounter(10),
                             fetcher.fetch_json, FakeClock())
    sweeps = fetcher.params_for(PLACES_SEARCH_URL)
    assert [p["type"] for p in sweeps] == ["restaurant", "cafe"]
    assert [p["place_id"] for p in found.places] == ["r1", "both", "c1"]
    by_id = {p["place_id"]: p for p in found.places}
    assert by_id["both"]["sweeps"] == ["restaurant", "cafe"]
    assert by_id["r1"]["sweeps"] == ["restaurant"]


def test_establishment_sweep_flag_still_catches_oddballs(tmp_path):
    """The typed sweeps are the fix, but an untyped business the curated list
    misses is still worth finding; the flag adds the old sweep on top."""
    fetcher = FakeFetcher(places_pages=[
        {"status": "OK", "results": [place("r1")]},
        {"status": "OK", "results": [place("r1"), place("oddball")]},
    ])
    area = load_demo_area(write_config(
        tmp_path, place_types=["restaurant"],
        include_establishment_sweep=True))
    found = enumerate_places(area, API_KEY, MapsCallCounter(10),
                             fetcher.fetch_json, FakeClock())
    assert [p["place_id"] for p in found.places] == ["r1", "oddball"]
    by_id = {p["place_id"]: p for p in found.places}
    assert by_id["oddball"]["sweeps"] == ["establishment"]
    assert by_id["r1"]["sweeps"] == ["restaurant", "establishment"]


def test_truncation_is_reported_per_type_sweep(tmp_path):
    """The cap is per query, so with typed sweeps the honest report is which
    sweep hit it -- a full restaurant sweep means storefronts are still
    missing even when every other type came back complete."""
    full = [place(f"r{i}") for i in range(NEARBY_SEARCH_MAX_RESULTS)]
    fetcher = FakeFetcher(places_pages=[
        {"status": "OK", "results": full},
        {"status": "OK", "results": [place("c1")]},
    ])
    area = load_demo_area(write_config(
        tmp_path, place_types=["restaurant", "cafe"]))
    found = enumerate_places(area, API_KEY, MapsCallCounter(10),
                             fetcher.fetch_json, FakeClock())
    assert found.truncated_types == (("test-area", "restaurant"),)
    assert found.truncated_blocks == ("test-area",)


def test_the_summary_names_truncated_types_per_block(tmp_path, env):
    full = [place(f"r{i}") for i in range(NEARBY_SEARCH_MAX_RESULTS)]
    fetcher = FakeFetcher(
        places_pages=[
            {"status": "OK", "results": full},
            {"status": "OK", "results": []},
        ],
        metadata=[{"status": "ZERO_RESULTS"}] * NEARBY_SEARCH_MAX_RESULTS,
    )
    config = write_config(tmp_path, place_types=["restaurant", "cafe"],
                          max_maps_calls=200)
    summary = run(tmp_path, fetcher, StubEngine(), config_path=config)
    assert summary["truncated_types"] == {"test-area": ["restaurant"]}
    assert summary["truncated_blocks"] == ["test-area"]


def test_typed_enumeration_resumes_over_an_existing_dataset(tmp_path, env):
    """Resume safety is unchanged by the sweep change: rows already in the
    dataset are skipped by place_id no matter which sweep found them."""
    fetcher = FakeFetcher(
        places_pages=[{"status": "OK", "results": [place("p1"), place("p2")]}],
        metadata=[metadata_ok(pano="pano-2")],
    )
    out = tmp_path / "out"
    out.mkdir()
    existing_row = {"place_id": "p1", "covered": True, "criteria": {},
                    "source": "streetview", "status": "ai_estimated"}
    (out / DATASET_FILENAME).write_text(
        json.dumps({"p1": existing_row}), encoding="utf-8")
    config = write_config(tmp_path, place_types=["restaurant"])
    summary = run(tmp_path, fetcher, StubEngine(), config_path=config)
    assert summary["skipped_existing"] == 1
    dataset = json.loads((out / DATASET_FILENAME).read_text(encoding="utf-8"))
    assert dataset["p1"] == existing_row  # untouched, not refetched
    assert set(dataset) == {"p1", "p2"}


# ------------------------------------------------- census mode (TICK-248 v2)


def test_census_enumerates_without_imagery_or_dataset_writes(tmp_path, env):
    fetcher = FakeFetcher(places_pages=[
        {"status": "OK", "results": [place("p1"), place("p2")]},
    ])
    area = load_demo_area(write_config(tmp_path, place_types=["restaurant"]))
    summary = run_census(area=area, out_dir=tmp_path / "out",
                         fetch_json=fetcher.fetch_json, sleep=FakeClock())
    assert summary["census"] is True
    assert summary["businesses_enumerated"] == 2
    assert summary["new_businesses"] == 2
    assert summary["sweep_types"] == ["restaurant"]
    assert summary["maps_api_calls"] == {
        "places": 1, "metadata": 0, "image": 0, "total": 1}
    # only the Places endpoint was touched, and the dataset was not created
    assert {u for u, _ in fetcher.calls} == {PLACES_SEARCH_URL}
    assert not (tmp_path / "out" / DATASET_FILENAME).exists()
    census = json.loads(
        (tmp_path / "out" / CENSUS_FILENAME).read_text(encoding="utf-8"))
    assert census["summary"] == json.loads(json.dumps(summary))
    assert [p["place_id"] for p in census["places"]] == ["p1", "p2"]


def test_census_counts_overlap_with_the_existing_dataset(tmp_path, env):
    """The census answers "what would a full run add?", so it counts against
    the same place_id-keyed dataset the resumable run skips by."""
    out = tmp_path / "out"
    out.mkdir()
    (out / DATASET_FILENAME).write_text(
        json.dumps({"p1": {"place_id": "p1"}}), encoding="utf-8")
    fetcher = FakeFetcher(places_pages=[
        {"status": "OK", "results": [place("p1"), place("p2"), place("p3")]},
    ])
    area = load_demo_area(write_config(tmp_path))
    summary = run_census(area=area, out_dir=out,
                         fetch_json=fetcher.fetch_json, sleep=FakeClock())
    assert summary["already_catalogued"] == 1
    assert summary["new_businesses"] == 2
    # read-only against the dataset: still exactly the row it started with
    dataset = json.loads((out / DATASET_FILENAME).read_text(encoding="utf-8"))
    assert set(dataset) == {"p1"}


def test_census_reports_a_cap_stop_cleanly(tmp_path, env):
    fetcher = FakeFetcher(places_pages=[
        {"status": "OK", "results": [place("p1")], "next_page_token": "tok"},
    ])
    config = write_config(tmp_path, max_maps_calls=1)
    area = load_demo_area(config)
    summary = run_census(area=area, out_dir=tmp_path / "out",
                         fetch_json=fetcher.fetch_json, sleep=FakeClock())
    assert summary["stopped"] and "MapsCallCapError" in summary["stopped"]
    assert summary["stopped_is_error"] is False
    assert (tmp_path / "out" / CENSUS_FILENAME).exists()


def test_cli_census_flag_routes_to_the_census(tmp_path, monkeypatch):
    from frontdoor import precatalogue

    seen = {}

    def fake_census(out_dir="data"):
        seen["out_dir"] = out_dir
        return {"stopped_is_error": False}

    monkeypatch.setattr(precatalogue, "run_census", fake_census)
    monkeypatch.setattr(precatalogue, "run_precatalogue",
                        lambda **kwargs: pytest.fail("full run must not start"))
    assert precatalogue.main(["run", "--census", str(tmp_path)]) == 0
    assert seen["out_dir"] == str(tmp_path)


def test_the_dataset_is_never_left_half_written(tmp_path, env):
    """The dataset is rewritten after every row. A plain write truncates
    first, so an interrupt in any of those windows would leave invalid JSON --
    and this file is how the next run knows what it already paid for."""
    fetcher = FakeFetcher(
        places_pages=[{"status": "OK", "results": [place("p1")]}],
        metadata=[metadata_ok()],
    )
    run(tmp_path, fetcher, StubEngine())
    out = tmp_path / "out"
    assert list(out.glob("*.tmp")) == [], "temp files must be renamed away"
    json.loads((out / DATASET_FILENAME).read_text())
