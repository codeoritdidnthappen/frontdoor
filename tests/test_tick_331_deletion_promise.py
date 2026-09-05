"""The protocol must not promise a cloud delete the image bucket will refuse (#331)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "capture-protocol.md"
STORAGE = ROOT / "data" / "STORAGE.md"
REVIEW = ROOT / "ios" / "FrontdoorCapture" / "UI" / "ScreeningReviewView.swift"


def test_shopkeeper_objection_does_not_promise_on_the_spot_cloud_deletion():
    text = PROTOCOL.read_text(encoding="utf-8")
    assert "shopkeeper objection" in text.lower()
    assert "delete that entrance's photos on the spot" not in text
    assert "discard any unpublished" in text.lower()
    assert "cannot be deleted from the phone" in text.lower()
    assert "sealed" in text.lower()


def test_storage_doc_records_which_image_prefix_the_images_token_can_delete():
    text = STORAGE.read_text(encoding="utf-8")
    section = text[text.index("## Shopkeeper-objection deletion") :]
    assert "FRONTDOOR_IMAGES" in section
    assert "`sealed/`" in section
    assert "`open/`" in section
    assert "ObjectLockedByBucketPolicy" in section
    assert "succeeds" in section.lower()
    assert "refused" in section.lower()
    assert "No S3 credential we hold can delete" in section
    assert "indefinite" in section.lower()
    assert "Cloudflare account login" in section


def test_review_gate_discard_is_honest_only_before_publish():
    source = REVIEW.read_text(encoding="utf-8")
    assert "Discarding keeps nothing" in source
    assert "not saved" in source
    assert "cannot be deleted from this phone" in source
    assert "delete from the cloud" not in source.lower()
