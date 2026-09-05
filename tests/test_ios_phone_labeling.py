"""Cross-language and flow guards for the future-capture phone labeler (#309)."""

import re
from pathlib import Path

from frontdoor.labels import ALLOWED_TRUTHS, CRITERIA_KEYS

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ios" / "FrontdoorCapture"
CONTRACT = APP / "Screening" / "ScreeningResponse.swift"
TRUTHS = APP / "Truth" / "EntranceLabels.swift"
CAPTURE = APP / "UI" / "CaptureView.swift"
LABELING = APP / "UI" / "EntranceLabelingView.swift"
CONTROLLER = APP / "Capture" / "CaptureController.swift"
UPLOADER = APP / "Upload" / "LabelUploader.swift"


def test_ac_11_swift_criteria_match_python_keys_and_order():
    source = CONTRACT.read_text(encoding="utf-8")
    block = source[source.index("enum ScreeningCriterion") :]
    keys = re.findall(r'case\s+\w+\s*=\s*"([a-z_]+)"', block)
    assert keys == list(CRITERIA_KEYS)


def test_ac_11_swift_truth_wire_values_match_python_and_button_order():
    source = TRUTHS.read_text(encoding="utf-8")
    block = source[source.index("enum LabelTruth") : source.index("enum EntranceLabelState")]
    cases = re.findall(r"case\s+(present|absent)|case\s+cannotDetermine\s*=\s*\"\"", block)
    assert cases == ["present", "absent", ""]
    assert list(ALLOWED_TRUTHS) + [""] == ["present", "absent", ""]


def test_ac_1_finish_capture_is_gated_by_complete_view_coverage():
    source = CAPTURE.read_text(encoding="utf-8")
    assert 'Button("Finish capture")' in source
    assert "CaptureFinishDecision.isEnabled(" in source
    assert "CaptureFinishDecision.destination(" in source
    assert "onFinish(destination)" in source


def test_ac_2_and_3_ui_shows_all_rows_and_three_buttons_without_truth_text_entry():
    source = LABELING.read_text(encoding="utf-8")
    assert "ForEach(ScreeningCriterion.allCases)" in source
    assert "ForEach(LabelTruth.allCases)" in source
    assert "@State private var draft = EntranceLabelDraft()" in source
    assert "draft.select(truth, for: criterion)" in source
    assert ".disabled(!canSave)" in source
    assert source.count("TextField(") == 1
    assert 'TextField("Your name"' in source


def test_ac_4_model_screening_is_released_only_after_durable_label_save():
    source = CONTROLLER.read_text(encoding="utf-8")
    commit = source[source.index("private func commit(") : source.index("// MARK: screening")]
    queue = source[source.index("func queueLabels(") : source.index("func drainLabelQueue()")]
    assert "screen(" not in commit
    assert "LabelCompletionGate(queue: labelQueue).save(" in queue
    # The rule is unchanged -- screening is released only after the durable save. The symbol
    # moved when #316 made the release send the entrance's whole view set instead of its last
    # frame, so this follows it rather than pinning a name that no longer exists.
    assert queue.index(") { _ in") < queue.index("screen(views:")


def test_ac_7_pending_labels_have_a_visible_edit_route_and_queue_errors_are_visible():
    home = (APP / "UI" / "HomeView.swift").read_text(encoding="utf-8")
    root = (APP / "UI" / "RootView.swift").read_text(encoding="utf-8")
    assert "ForEach(controller.queuedLabelIds" in home
    assert 'Button("Edit labels for \\(entranceId)")' in home
    assert "controller.labelQueueError" in home
    assert "onEditLabel: { entranceId in" in root


def test_ac_6_and_8_phone_sends_only_server_owned_label_fields_with_existing_key():
    source = UPLOADER.read_text(encoding="utf-8")
    assert 'appendingPathComponent("labels")' in source
    assert 'forHTTPHeaderField: "X-Frontdoor-Upload-Key"' in source
    assert '"entrance_id": record.entranceId' in source
    assert '"labeled_by": record.labeledBy' in source
    assert '"answers": record.answers' in source
    assert "labeled_at" not in source


def test_ac_12_docs_call_labels_future_only_and_container_ephemeral():
    labeling = (ROOT / "docs" / "labeling.md").read_text(encoding="utf-8").lower()
    deploy = (ROOT / "docs" / "server-deploy.md").read_text(encoding="utf-8").lower()
    assert "future capture" in labeling
    assert "#302" in labeling
    assert "container" in deploy and "lost" in deploy
