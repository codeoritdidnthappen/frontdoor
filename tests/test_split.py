"""Tests for deterministic split assignment (TICK-011, #19)."""

import io
import random
import sys
import unicodedata
from collections import Counter

import pytest

from frontdoor.split import (
    SEED,
    InvalidEntranceId,
    _assign_split_with_seed,
    assign_split,
    canonical_entrance_id,
    main,
)

IDS = [f"E-{n:03d}" for n in range(1000)]


def test_committed_seed_is_64_hex_chars():
    assert len(SEED) == 64
    int(SEED, 16)


def test_same_id_gives_same_split_twice():
    for entrance_id in IDS[:50]:
        assert assign_split(entrance_id) == assign_split(entrance_id)


def test_assignment_is_order_independent():
    expected = {i: assign_split(i) for i in IDS}
    shuffled = random.Random(1).sample(IDS, len(IDS))
    assert {i: assign_split(i) for i in shuffled} == expected


def test_roughly_thirty_percent_sealed():
    counts = Counter(assign_split(i) for i in IDS)
    assert set(counts) == {"dev", "calib", "sealed"}
    assert 0.25 <= counts["sealed"] / len(IDS) <= 0.35
    assert 0.15 <= counts["calib"] / len(IDS) <= 0.25


def test_changed_seed_changes_assignments():
    other_seed = "0" * 64
    assert [_assign_split_with_seed(i, other_seed) for i in IDS] != [
        assign_split(i) for i in IDS
    ]


def test_public_assign_split_cannot_override_seed():
    with pytest.raises(TypeError):
        assign_split("E-014", seed=SEED)
    assert assign_split("E-014") == "sealed"
    assert _assign_split_with_seed("E-014", SEED) == "sealed"


def test_known_answers_with_committed_seed():
    # Pinned so that any change to the seed or the algorithm fails loudly (D-007: immutable).
    assert assign_split("E-001") == "dev"
    assert assign_split("E-002") == "sealed"
    assert assign_split("E-014") == "sealed"
    assert assign_split("E-042") == "calib"


def test_cli_prints_one_line_per_id(capsys):
    main(["E-001", "E-014"])
    assert capsys.readouterr().out.splitlines() == ["E-001,dev", "E-014,sealed"]


def test_spellings_of_the_same_entrance_get_the_same_split():
    expected = assign_split("E-014")
    assert assign_split("e-014") == expected
    assert assign_split("E-014 ") == expected
    assert assign_split(" E-014") == expected
    assert assign_split("E-014\t") == expected
    nfc = unicodedata.normalize("NFC", "E-014")
    nfd = unicodedata.normalize("NFD", "E-014")
    assert assign_split(nfc) == expected
    assert assign_split(nfd) == expected


def test_nfd_and_nfc_noncanonical_ids_are_both_rejected():
    nfd = "E\u0301-014"  # E + combining acute
    nfc = unicodedata.normalize("NFC", nfd)
    assert nfc != nfd
    with pytest.raises(InvalidEntranceId) as nfd_exc:
        assign_split(nfd)
    with pytest.raises(InvalidEntranceId) as nfc_exc:
        assign_split(nfc)
    assert repr(nfd) in str(nfd_exc.value)
    assert repr(nfc) in str(nfc_exc.value)


@pytest.mark.parametrize("entrance_id", ["E-14", "E-0014", "E- 014", "E014", "X-014", ""])
def test_noncanonical_entrance_id_rejected(entrance_id):
    with pytest.raises(InvalidEntranceId) as exc:
        assign_split(entrance_id)
    assert repr(entrance_id) in str(exc.value)


def test_canonical_entrance_id_returns_the_canonical_form():
    assert canonical_entrance_id(" e-014 ") == "E-014"


def _cli_argv(capsys, ids):
    main(ids)
    return capsys.readouterr().out


def _cli_stdin(capsys, monkeypatch, text):
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))
    main([])
    return capsys.readouterr().out


@pytest.mark.parametrize(
    ("argv_ids", "stdin_text"),
    [
        (["E-002 "], "E-002 \n"),
        ([" E-002"], " E-002\n"),
        (["E-002\t"], "E-002\t\n"),
        (
            ["E-001\r", "E-002\r", "E-014\r"],
            "E-001\r\nE-002\r\nE-014\r\n",
        ),
    ],
)
def test_cli_argv_and_stdin_agree(capsys, monkeypatch, argv_ids, stdin_text):
    argv_out = _cli_argv(capsys, argv_ids)
    stdin_out = _cli_stdin(capsys, monkeypatch, stdin_text)
    assert argv_out == stdin_out


def test_crlf_list_through_argv_matches_stdin(capsys, monkeypatch):
    expected = "E-001,dev\nE-002,sealed\nE-014,sealed\n"
    stdin_out = _cli_stdin(capsys, monkeypatch, "E-001\r\nE-002\r\nE-014\r\n")
    argv_out = _cli_argv(capsys, ["E-001\r", "E-002\r", "E-014\r"])
    assert stdin_out == expected
    assert argv_out == expected
