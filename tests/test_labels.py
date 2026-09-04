"""Tests for human ground-truth labels (TICK-246, #168)."""

import csv
import json
from datetime import date

import pytest

from frontdoor.labels import (
    ALLOWED_TRUTHS,
    AUDIT_KEYS,
    COLUMNS,
    CRITERIA_KEYS,
    LabelError,
    SealedLabelError,
    entrance_ids_from_manifest,
    initialize_labeling_sheet,
    labeling_progress,
    labels_for_eval,
    load_labels,
    read_labeling_sheet,
    require_complete_labeling,
    save_entrance_labels,
    template_rows,
    write_template,
)
from frontdoor.seal_audit import AUDIT_FIELDS, SealAuditError

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


def test_labeling_sheet_saves_four_button_answers_and_tracks_review(tmp_path):
    path = tmp_path / "labels.csv"
    eligible = ["E-001", "E-042"]
    initialize_labeling_sheet(path, eligible)

    save_entrance_labels(
        path,
        eligible,
        "E-001",
        {
            "ramp_or_bevel": "present",
            "handrails": "absent",
            "accessible_door_hardware": "",
            "accessibility_signage": "present",
        },
        labeled_by="James",
        labeled_at=date(2026, 9, 4),
    )

    rows = read_labeling_sheet(path, eligible)
    saved = [row for row in rows if row["entrance_id"] == "E-001"]
    assert [row["truth"] for row in saved] == ["present", "absent", "", "present"]
    assert {row["labeled_by"] for row in saved} == {"James"}
    assert {row["labeled_at"] for row in saved} == {"2026-09-04"}
    assert labeling_progress(path, eligible).reviewed_entrances == 1
    assert not labeling_progress(path, eligible).complete


@pytest.mark.parametrize(
    "entrance_id,answers,error",
    [
        ("E-002", {key: "present" for key in CRITERIA_KEYS}, "not evaluation eligible"),
        ("E-001", {"handrails": "present"}, "each screening criterion"),
        (
            "E-001",
            {key: "maybe" for key in CRITERIA_KEYS},
            "present, absent, or blank",
        ),
    ],
)
def test_invalid_labeling_submission_leaves_sheet_unchanged(
    tmp_path, entrance_id, answers, error
):
    path = tmp_path / "labels.csv"
    initialize_labeling_sheet(path, ["E-001"])
    before = path.read_bytes()

    with pytest.raises(LabelError, match=error):
        save_entrance_labels(
            path,
            ["E-001"],
            entrance_id,
            answers,
            labeled_by="James",
            labeled_at=date(2026, 9, 4),
        )

    assert path.read_bytes() == before


def test_labeling_completion_requires_every_eligible_entrance_reviewed(tmp_path):
    path = tmp_path / "labels.csv"
    eligible = ["E-001", "E-042"]
    initialize_labeling_sheet(path, eligible)
    with pytest.raises(LabelError, match="0 of 2"):
        require_complete_labeling(path, eligible)
    for entrance_id in eligible:
        save_entrance_labels(
            path,
            eligible,
            entrance_id,
            {key: "" for key in CRITERIA_KEYS},
            labeled_by="James",
            labeled_at=date(2026, 9, 4),
        )
    progress = labeling_progress(path, eligible)
    assert progress.complete
    assert progress.reviewed_entrances == progress.total_entrances == 2
    require_complete_labeling(path, eligible)


def test_existing_sheet_with_ineligible_or_missing_rows_is_refused(tmp_path):
    path = tmp_path / "labels.csv"
    write_template(path, ["E-001", "E-002"])
    before = path.read_bytes()

    with pytest.raises(LabelError, match="exactly one ordered row"):
        initialize_labeling_sheet(path, ["E-001"])

    assert path.read_bytes() == before


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


def _audit_context(tmp_path):
    """A minimal audit mapping for record_unsealing, mirroring test_seal_audit."""
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "capture_id,entrance_id,image_sha256,depth_sha256,sidecar_sha256,split\n"
        "c1,E-002,a,b,c,sealed\n",
        encoding="utf-8",
    )
    return {
        "manifest_path": manifest,
        "audit_path": tmp_path / "SEAL_AUDIT.log",
        "repo": tmp_path,
        "config": {"images_bucket": "frontdoor-image", "endpoint": "default"},
    }


def _clean_recordable_repo(monkeypatch):
    """Monkeypatch the git-cleanliness bits the way test_seal_audit.py does."""
    monkeypatch.setattr("frontdoor.seal_audit._working_tree_dirty", lambda repo: False)
    monkeypatch.setattr("frontdoor.seal_audit._git_commit", lambda repo: "b" * 40)
    monkeypatch.setattr("frontdoor.seal_audit._operator", lambda: "qa-operator")


def test_eval_filter_refuses_sealed_without_audited_flag(tmp_path):
    loaded = load_labels(_write_labels(tmp_path / "labels.csv", _mixed_split_labels()))
    with pytest.raises(SealedLabelError, match="results freeze"):
        labels_for_eval(loaded.labels, split="sealed")


def test_bare_audited_flag_without_audit_mechanism_refuses(tmp_path):
    # audited=True alone must not unseal (fix-forward on TICK-246): the
    # release goes through seal_audit or not at all.
    loaded = load_labels(_write_labels(tmp_path / "labels.csv", _mixed_split_labels()))
    with pytest.raises(SealedLabelError, match="does not unseal"):
        labels_for_eval(loaded.labels, split="sealed", audited=True)


def test_incomplete_audit_mapping_refuses(tmp_path):
    loaded = load_labels(_write_labels(tmp_path / "labels.csv", _mixed_split_labels()))
    audit = _audit_context(tmp_path)
    del audit["config"]
    with pytest.raises(SealedLabelError, match="missing"):
        labels_for_eval(loaded.labels, split="sealed", audited=True, audit=audit)


def test_audited_path_records_unsealing_then_hands_back_sealed_labels(
    tmp_path, monkeypatch
):
    loaded = load_labels(_write_labels(tmp_path / "labels.csv", _mixed_split_labels()))
    audit = _audit_context(tmp_path)
    _clean_recordable_repo(monkeypatch)
    sealed = labels_for_eval(loaded.labels, split="sealed", audited=True, audit=audit)
    assert [l["entrance_id"] for l in sealed] == ["E-002", "E-014"]
    lines = audit["audit_path"].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = dict(zip(AUDIT_FIELDS, lines[0].split("\t")))
    assert json.loads(record["command_line"]) == ["labels", "--split", "sealed"]
    assert record["operator"] == "qa-operator"


def test_dirty_tree_refuses_sealed_labels_and_writes_nothing(tmp_path, monkeypatch):
    loaded = load_labels(_write_labels(tmp_path / "labels.csv", _mixed_split_labels()))
    audit = _audit_context(tmp_path)
    monkeypatch.setattr("frontdoor.seal_audit._working_tree_dirty", lambda repo: True)
    with pytest.raises(SealAuditError, match="dirty"):
        labels_for_eval(loaded.labels, split="sealed", audited=True, audit=audit)
    assert not audit["audit_path"].exists()


def test_audit_keys_match_record_unsealing_signature():
    import inspect

    from frontdoor.seal_audit import record_unsealing

    params = inspect.signature(record_unsealing).parameters
    assert all(key in params for key in AUDIT_KEYS)


def test_audit_keys_are_owned_by_seal_audit():
    # One contract, defined once, next to record_unsealing's signature. A
    # labels-side copy is exactly the drift this pin exists to prevent.
    from frontdoor import seal_audit

    assert AUDIT_KEYS is seal_audit.AUDIT_KEYS


def test_sealed_release_delegates_to_seal_audit_record_unsealing(
    tmp_path, monkeypatch
):
    # The audited path goes through seal_audit.record_unsealing - the one
    # doorway - not a labels-side reimplementation. Patching the seal_audit
    # module attribute intercepts the call only if labels.py delegates.
    loaded = load_labels(_write_labels(tmp_path / "labels.csv", _mixed_split_labels()))
    audit = _audit_context(tmp_path)
    calls = []
    monkeypatch.setattr(
        "frontdoor.seal_audit.record_unsealing",
        lambda argv, **kwargs: calls.append((argv, kwargs)),
    )
    sealed = labels_for_eval(loaded.labels, split="sealed", audited=True, audit=audit)
    assert [l["entrance_id"] for l in sealed] == ["E-002", "E-014"]
    assert calls == [
        (
            ["labels", "--split", "sealed"],
            {key: audit[key] for key in AUDIT_KEYS},
        )
    ]


def test_labels_audit_line_matches_seal_audit_log_format(tmp_path, monkeypatch):
    # The line labels_for_eval causes to be written is a seal_audit line:
    # same tab-separated AUDIT_FIELDS order the eval doorway writes and
    # ARCHITECTURE.md documents. One log, one format.
    from frontdoor.manifest import manifest_sha256

    loaded = load_labels(_write_labels(tmp_path / "labels.csv", _mixed_split_labels()))
    audit = _audit_context(tmp_path)
    _clean_recordable_repo(monkeypatch)
    labels_for_eval(loaded.labels, split="sealed", audited=True, audit=audit)
    line = audit["audit_path"].read_text(encoding="utf-8").splitlines()[0]
    fields = line.split("\t")
    assert len(fields) == len(AUDIT_FIELDS)
    record = dict(zip(AUDIT_FIELDS, fields))
    assert record["utc_timestamp"].endswith("Z")
    assert record["commit_sha"] == "b" * 40
    assert record["manifest_sha256"] == manifest_sha256(audit["manifest_path"])
    assert json.loads(record["command_line"]) == ["labels", "--split", "sealed"]
    assert set(json.loads(record["resolved_config"])) == {"images_bucket", "endpoint"}


def test_eval_filter_rejects_unknown_split(tmp_path):
    loaded = load_labels(_write_labels(tmp_path / "labels.csv", _mixed_split_labels()))
    with pytest.raises(LabelError, match="unknown split"):
        labels_for_eval(loaded.labels, split="test")
