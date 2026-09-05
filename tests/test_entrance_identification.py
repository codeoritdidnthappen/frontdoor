"""The committed entrance-to-business identification (TICK-341, #341).

#333 consumes this file to key a scan record to a place. Two properties matter
more than the rest and are pinned here: no sealed entrance may appear at all,
and an entrance that could not be pinned to one business must claim no business
— no name, no confidence, no basis, no evidence. The second is the ticket's own
rule that an unmatched entrance is a smaller failure than a scan record attached
to the wrong storefront, and `place_id is None` does not stand in for it: 23 of
the 29 identifications carry no place_id, so the identifying claim lives in
`name`.
"""

import csv
import json
from pathlib import Path

import pytest

from frontdoor.split import assign_split

REPO = Path(__file__).resolve().parents[1]
IDENTIFICATION = REPO / "data" / "entrance_identification.json"
MANIFEST = REPO / "data" / "manifest.csv"
CATALOGUE = REPO / "data" / "precatalogue_census.json"

BASES = {
    "surveyed_location",
    "read_sign",
    "read_branding",
    "read_street_number",
    "walk_order",
}
CONFIDENCES = {"high", "low"}

#: Bases that are themselves a reading of an address off the building.
ADDRESS_BASES = {"surveyed_location", "read_street_number"}


@pytest.fixture(scope="module")
def entrances():
    return json.loads(IDENTIFICATION.read_text(encoding="utf-8"))["entrances"]


@pytest.fixture(scope="module")
def captured_entrances():
    with MANIFEST.open(newline="", encoding="utf-8") as fh:
        return {row["entrance_id"] for row in csv.DictReader(fh)}


def test_no_sealed_entrance_appears(entrances):
    sealed = sorted(e for e in entrances if assign_split(e) == "sealed")
    assert sealed == [], f"sealed entrances must be withheld until the freeze: {sealed}"


def test_every_non_sealed_captured_entrance_is_accounted_for(entrances, captured_entrances):
    expected = {e for e in captured_entrances if assign_split(e) != "sealed"}
    assert set(entrances) == expected


def test_an_unidentified_entrance_claims_no_business(entrances):
    """The ticket's hard rule, pinned field by field.

    `address` is deliberately exempt: six of these doors have a legible street
    number and no readable tenant, and losing the number would throw away the
    one thing that was read. An address is not a claim about a business.
    """
    for entrance_id, record in sorted(entrances.items()):
        if record["status"] != "unidentified":
            continue
        assert record["reason"], entrance_id
        assert record["name"] is None, entrance_id
        assert record["place_id"] is None, entrance_id
        assert record["confidence"] is None, entrance_id
        assert record["basis"] == [], entrance_id
        assert record["evidence"] is None, entrance_id


def test_an_identified_entrance_names_a_business_and_says_why(entrances):
    for entrance_id, record in sorted(entrances.items()):
        if record["status"] == "unidentified":
            continue
        assert record["status"] == "identified", entrance_id
        assert record["name"], entrance_id
        assert record["confidence"] in CONFIDENCES, entrance_id
        assert record["basis"], entrance_id
        assert set(record["basis"]) <= BASES, entrance_id
        assert record["evidence"], entrance_id
        assert record["reason"] is None, entrance_id


def test_an_address_is_only_claimed_where_one_was_read(entrances):
    """No record may carry an address it never says it read."""
    for entrance_id, record in sorted(entrances.items()):
        if record["address"] is None:
            continue
        if record["status"] == "unidentified":
            continue  # the reason text carries the number it read
        assert set(record["basis"]) & ADDRESS_BASES, (
            f"{entrance_id} claims an address without a basis that reads one"
        )


def test_place_ids_resolve_to_the_catalogue(entrances):
    known = {
        place["place_id"]
        for place in json.loads(CATALOGUE.read_text(encoding="utf-8"))["places"]
    }
    for entrance_id, record in sorted(entrances.items()):
        place_id = record["place_id"]
        if place_id is not None:
            assert place_id in known, f"{entrance_id} names an uncatalogued place_id"


def test_no_two_entrances_claim_the_same_place(entrances):
    claimed = [r["place_id"] for r in entrances.values() if r["place_id"] is not None]
    assert len(claimed) == len(set(claimed)), "one place cannot be two front doors"


def test_a_photographed_entrance_records_the_views_it_was_read_from(entrances, captured_entrances):
    """A read identification must be traceable back to specific captures."""
    with MANIFEST.open(newline="", encoding="utf-8") as fh:
        captures = {}
        for row in csv.DictReader(fh):
            captures.setdefault(row["entrance_id"], set()).add(row["capture_id"])

    for entrance_id, record in sorted(entrances.items()):
        views = record["views_read"]
        if not views:
            assert record["basis"] == ["surveyed_location"], entrance_id
            continue
        assert "surveyed_location" not in record["basis"], entrance_id
        assert len(views) == len(captures[entrance_id]), entrance_id
