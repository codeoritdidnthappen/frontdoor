"""Tests for human ground-truth labels (TICK-246, #168)."""

import csv

import pytest

from frontdoor.labels import (
    ALLOWED_TRUTHS,
    COLUMNS,
    CRITERIA_KEYS,
    LabelError,
    SealedLabelError,
    entrance_ids_from_manifest,
    labels_for_eval,
    load_labels,
    template_rows,
    write_template,
)

# Split known answers from test_split.py (committed seed): E-001 dev,
# E-002 sealed, E-014 sealed, E-042 calib.


def _write_labels(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _row(entrance_id, criterion, truth, labeled_by="op-1", labeled_at="2026-09-01"):
    return {
        "entrance_id": entrance_id,
        "criterion": criterion,
        "truth": truth,
        "labeled_by": labeled_by,
        "labeled_at": labeled_at,
    }


def test_criteria_keys_match_screening_engine():
    # Pinned to the screening engine's CRITERIA (TICK-245) so eval joins
    # labels to verdicts cleanly. Change both together or not at all.
    assert CRITERIA_KEYS == (
        "ramp_or_bevel",
        "handrails",
        "accessible_door_hardware",
        "accessibility_signage",
    )


def test_truth_vocabulary_is_presence_only():
    assert ALLOWED_TRUTHS == ("present", "absent")


def test_template_one_blank_row_per_entrance_criterion(tmp_path):
    path = tmp_path / "labels.csv"
    write_template(path, ["E-001", "E-002"])
    with open(path, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2 * len(CRITERIA_KEYS)
    assert [r["entrance_id"] for r in rows[: len(CRITERIA_KEYS)]] == ["E-001"] * 4
    assert [r["criterion"] for r in rows[: len(CRITERIA_KEYS)]] == list(CRITERIA_KEYS)
    assert all(r["truth"] == "" for r in rows)
    assert all(r["labeled_by"] == "" for r in rows)
    assert all(r["labeled_at"] == "" for r in rows)


def test_template_canonicalizes_and_deduplicates_ids():
    rows = template_rows(["e-001 ", "E-001", "E-002"])
    assert [r["entrance_id"] for r in rows] == ["E-001"] * 4 + ["E-002"] * 4


def test_template_rejects_invalid_entrance_id():
    with pytest.raises(ValueError):
        template_rows(["E-14"])


def test_entrance_ids_from_manifest_deduplicates_in_capture_order(tmp_path):
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "capture_id,entrance_id,image_sha256,depth_sha256,sidecar_sha256,split\n"
        "c1,E-002,a,b,c,sealed\n"
        "c2,E-001,a,b,c,dev\n"
        "c3,E-002,a,b,c,sealed\n",
        encoding="utf-8",
    )
    assert entrance_ids_from_manifest(manifest) == ["E-002", "E-001"]


def test_load_round_trips_labeled_rows(tmp_path):
    path = _write_labels(
        tmp_path / "labels.csv",
        [
            _row("E-001", "ramp_or_bevel", "present"),
            _row("E-001", "handrails", "absent"),
        ],
    )
    loaded = load_labels(path)
    assert loaded.blank_skipped == 0
    assert [l["truth"] for l in loaded.labels] == ["present", "absent"]
    assert all(l["labeled_by"] == "op-1" for l in loaded.labels)


def test_load_skips_blank_truth_rows_with_a_count(tmp_path):
    path = _write_labels(
        tmp_path / "labels.csv",
        [
            _row("E-001", "ramp_or_bevel", "present"),
            _row("E-001", "handrails", "", labeled_by="", labeled_at=""),
            _row("E-001", "accessibility_signage", "", labeled_by="", labeled_at=""),
        ],
    )
    loaded = load_labels(path)
    assert loaded.blank_skipped == 2
    assert [l["criterion"] for l in loaded.labels] == ["ramp_or_bevel"]


def test_load_rejects_wrong_columns(tmp_path):
    path = tmp_path / "labels.csv"
    path.write_text("entrance_id,criterion,verdict\n", encoding="utf-8")
    with pytest.raises(LabelError, match="columns"):
        load_labels(path)


def test_load_rejects_invalid_entrance_id(tmp_path):
    path = _write_labels(
        tmp_path / "labels.csv", [_row("E-14", "handrails", "present")]
    )
    with pytest.raises(LabelError, match="line 2"):
        load_labels(path)


def test_load_rejects_noncanonical_spelling(tmp_path):
    path = _write_labels(
        tmp_path / "labels.csv", [_row("e-001", "handrails", "present")]
    )
    with pytest.raises(LabelError, match="canonical"):
        load_labels(path)


def test_load_rejects_unknown_criterion(tmp_path):
    path = _write_labels(
        tmp_path / "labels.csv", [_row("E-001", "door_width", "present")]
    )
    with pytest.raises(LabelError, match="unknown criterion"):
        load_labels(path)


@pytest.mark.parametrize("truth", ["not_visible", "appears_present", "yes", "Present"])
def test_load_rejects_out_of_vocabulary_truth(tmp_path, truth):
    path = _write_labels(
        tmp_path / "labels.csv", [_row("E-001", "handrails", truth)]
    )
    with pytest.raises(LabelError, match="presence-only"):
        load_labels(path)


def test_load_rejects_duplicate_entrance_criterion_pair(tmp_path):
    path = _write_labels(
        tmp_path / "labels.csv",
        [
            _row("E-001", "handrails", "present"),
            _row("E-001", "handrails", "absent"),
        ],
    )
    with pytest.raises(LabelError, match="duplicate"):
        load_labels(path)


def test_load_rejects_blank_labeler_on_labeled_row(tmp_path):
    path = _write_labels(
        tmp_path / "labels.csv",
        [_row("E-001", "handrails", "present", labeled_by="")],
    )
    with pytest.raises(LabelError, match="labeled_by"):
        load_labels(path)


def test_load_rejects_non_iso_date(tmp_path):
    path = _write_labels(
        tmp_path / "labels.csv",
        [_row("E-001", "handrails", "present", labeled_at="09/01/2026")],
    )
    with pytest.raises(LabelError, match="ISO date"):
        load_labels(path)


def _mixed_split_labels():
    return [
        _row("E-001", "handrails", "present"),  # dev
        _row("E-002", "handrails", "absent"),  # sealed
        _row("E-014", "ramp_or_bevel", "present"),  # sealed
        _row("E-042", "handrails", "present"),  # calib
    ]


def test_eval_filter_returns_dev_split_only(tmp_path):
    loaded = load_labels(_write_labels(tmp_path / "labels.csv", _mixed_split_labels()))
    dev = labels_for_eval(loaded.labels)
    assert [l["entrance_id"] for l in dev] == ["E-001"]


def test_eval_filter_refuses_sealed_without_audited_flag(tmp_path):
    loaded = load_labels(_write_labels(tmp_path / "labels.csv", _mixed_split_labels()))
    with pytest.raises(SealedLabelError, match="results freeze"):
        labels_for_eval(loaded.labels, split="sealed")


def test_audited_path_hands_back_sealed_labels(tmp_path):
    loaded = load_labels(_write_labels(tmp_path / "labels.csv", _mixed_split_labels()))
    sealed = labels_for_eval(loaded.labels, split="sealed", audited=True)
    assert [l["entrance_id"] for l in sealed] == ["E-002", "E-014"]


def test_eval_filter_rejects_unknown_split(tmp_path):
    loaded = load_labels(_write_labels(tmp_path / "labels.csv", _mixed_split_labels()))
    with pytest.raises(LabelError, match="unknown split"):
        labels_for_eval(loaded.labels, split="test")
