"""Contract tests for the face-blur ingest step (TICK-257, #232).

Blurring destroys the region it is given (detection mocked), detection stays
quiet on a featureless image, EXIF orientation is physically applied, EXIF
(GPS included) does not survive re-encode, and process_upload's output is
always a valid JPEG. The YuNet primary detector (TICK-257 follow-up) is real
enough that a programmatically drawn face triggers it, so its tests use one -
no committed photo of a person, which would defeat the module's purpose.
Measured recall on real photos is reported on the ticket, not asserted here -
it depends on the photos.
"""

import cv2
import numpy as np
import pytest

from frontdoor import faceblur
from frontdoor.faceblur import (
    ProcessedImage,
    blur_faces,
    detect_faces,
    process_upload,
    strip_gps,
)

rng = np.random.default_rng(seed=257)


def encode(img, quality=95):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    assert ok
    return buf.tobytes()


def decode(image_bytes):
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    assert img is not None, "output is not decodable image bytes"
    return img


def noisy_image(h=240, w=320):
    """High-frequency noise: any real smoothing measurably destroys it."""
    return rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)


# --- blur_faces --------------------------------------------------------------


def test_blur_destroys_the_detected_region(monkeypatch):
    box = (100, 80, 60, 60)
    monkeypatch.setattr(faceblur, "_detect", lambda img: [box])
    original = noisy_image()

    processed_bytes, count = blur_faces(encode(original))

    assert count == 1
    processed = decode(processed_bytes)
    assert processed.shape == original.shape
    x, y, w, h = box
    region_before = original[y : y + h, x : x + w].astype(np.int16)
    region_after = processed[y : y + h, x : x + w].astype(np.int16)
    # The region changed a lot (noise vs flat blocks)...
    assert np.abs(region_before - region_after).mean() > 20
    # ...and is heavily smoothed: pixel-to-pixel variation collapses. The
    # original noise differs ~85 per channel between horizontal neighbors;
    # 12px-wide pixelation leaves flat blocks.
    def neighbor_delta(region):
        return np.abs(np.diff(region, axis=1)).mean()

    assert neighbor_delta(region_after) < neighbor_delta(region_before) / 4


def test_blur_expands_the_box_with_margin(monkeypatch):
    box = (100, 100, 50, 50)
    monkeypatch.setattr(faceblur, "_detect", lambda img: [box])
    original = noisy_image()

    processed = decode(blur_faces(encode(original))[0])

    # A strip just outside the reported box but inside the ~30% margin is
    # blurred too - hairlines and chins do not survive at the box edge.
    strip_before = original[100:150, 90:100].astype(np.int16)
    strip_after = processed[100:150, 90:100].astype(np.int16)
    assert np.abs(strip_before - strip_after).mean() > 20


def test_blur_leaves_the_rest_of_the_image_alone(monkeypatch):
    source = encode(noisy_image())

    monkeypatch.setattr(faceblur, "_detect", lambda img: [(10, 10, 40, 40)])
    blurred = decode(blur_faces(source)[0])
    monkeypatch.setattr(faceblur, "_detect", lambda img: [])
    control = decode(blur_faces(source)[0])

    # Same JPEG round-trip either way, so away from the box the two outputs
    # differ by nothing structural - only the blurred neighborhood changes.
    far_corner_blurred = blurred[180:230, 250:310].astype(np.int16)
    far_corner_control = control[180:230, 250:310].astype(np.int16)
    assert np.abs(far_corner_blurred - far_corner_control).mean() < 2


def test_blur_clamps_boxes_at_the_image_edge(monkeypatch):
    # A face at the frame edge: the margin-expanded box exceeds the image.
    monkeypatch.setattr(faceblur, "_detect", lambda img: [(0, 0, 50, 50), (300, 220, 60, 60)])
    processed_bytes, count = blur_faces(encode(noisy_image()))
    assert count == 2
    assert decode(processed_bytes).shape == (240, 320, 3)


def test_no_faces_means_zero_count_and_valid_jpeg(monkeypatch):
    monkeypatch.setattr(faceblur, "_detect", lambda img: [])
    processed_bytes, count = blur_faces(encode(noisy_image()))
    assert count == 0
    assert processed_bytes[:2] == b"\xff\xd8"
    decode(processed_bytes)


# --- YuNet primary detector (TICK-257 follow-up) ------------------------------


class _EmptyCascade:
    def detectMultiScale(self, img, **kwargs):
        return []


def drawn_face(size=200):
    """A face drawn with cv2 primitives. YuNet, unlike the Haar cascades,
    detects it (score ~0.88 at 200px) - so the DNN path is exercised on an
    image the repo can commit-free regenerate, not on a real person."""
    img = np.full((size, size, 3), 200, dtype=np.uint8)
    c = size // 2
    cv2.ellipse(img, (c, c), (int(size * 0.28), int(size * 0.38)), 0, 0, 360,
                (140, 170, 210), -1)  # head
    cv2.ellipse(img, (c, int(c - size * 0.22)), (int(size * 0.29), int(size * 0.20)),
                0, 180, 360, (40, 50, 60), -1)  # hair
    for ex in (int(c - size * 0.11), int(c + size * 0.11)):  # eyes and brows
        ey = int(c - size * 0.08)
        cv2.ellipse(img, (ex, ey), (int(size * 0.06), int(size * 0.035)), 0, 0, 360,
                    (245, 245, 245), -1)
        cv2.circle(img, (ex, ey), int(size * 0.025), (90, 60, 40), -1)
        cv2.circle(img, (ex, ey), int(size * 0.012), (10, 10, 10), -1)
        cv2.ellipse(img, (ex, ey - int(size * 0.05)), (int(size * 0.06), int(size * 0.015)),
                    0, 180, 360, (60, 70, 90), -1)
    cv2.line(img, (c, int(c - size * 0.04)), (int(c - size * 0.02), int(c + size * 0.08)),
             (110, 140, 180), 2)  # nose
    cv2.ellipse(img, (c, int(c + size * 0.09)), (int(size * 0.035), int(size * 0.02)),
                0, 0, 180, (100, 130, 170), 2)
    cv2.ellipse(img, (c, int(c + size * 0.20)), (int(size * 0.09), int(size * 0.035)),
                0, 0, 180, (80, 80, 170), -1)  # mouth
    cv2.ellipse(img, (c, int(c + size * 0.30)), (int(size * 0.10), int(size * 0.03)),
                0, 0, 180, (120, 150, 190), 2)  # chin shading
    return img


def test_yunet_loads_from_the_committed_model_file():
    # The model ships in the package: no download, no network, no cache dir.
    assert faceblur._get_yunet() is not None


def test_yunet_detects_a_face_without_the_cascades(monkeypatch):
    # Haar disabled: any box must come from the YuNet path.
    monkeypatch.setattr(
        faceblur, "_get_cascades", lambda: (_EmptyCascade(), _EmptyCascade())
    )
    boxes = detect_faces(encode(drawn_face()))
    assert boxes, "YuNet found no face in the drawn-face fixture"
    # At least one box covers the face's center.
    assert any(
        x <= 100 <= x + w and y <= 100 <= y + h for x, y, w, h in boxes
    ), f"no box covers the face center: {boxes}"


def test_yunet_boxes_come_back_in_full_resolution_coordinates(monkeypatch):
    # Detection runs downscaled (DETECT_MAX_SIDE=1600); a face drawn on a
    # 3200px-wide canvas must come back in that canvas's coordinates.
    monkeypatch.setattr(
        faceblur, "_get_cascades", lambda: (_EmptyCascade(), _EmptyCascade())
    )
    big = np.full((2400, 3200, 3), 200, dtype=np.uint8)
    big[1000:1400, 1400:1800] = drawn_face(400)  # face center at (1600, 1200)
    boxes = detect_faces(encode(big))
    assert any(
        x <= 1600 <= x + w and y <= 1200 <= y + h for x, y, w, h in boxes
    ), f"no box covers the face center at full resolution: {boxes}"


# --- detect_faces ------------------------------------------------------------


def test_flat_gray_image_has_no_faces():
    flat = np.full((400, 600, 3), 128, dtype=np.uint8)
    assert detect_faces(encode(flat)) == []


def test_boxes_are_reported_in_full_resolution_coordinates(monkeypatch):
    # Detection runs downscaled (DETECT_MAX_SIDE); boxes must come back in the
    # coordinates of the image the caller handed in.
    class FakeCascade:
        def __init__(self, boxes):
            self._boxes = boxes

        def detectMultiScale(self, img, **kwargs):
            return list(self._boxes)

    monkeypatch.setattr(
        faceblur,
        "_get_cascades",
        lambda: (FakeCascade([(10, 10, 20, 20)]), FakeCascade([])),
    )
    big = np.full((2400, 3200, 3), 128, dtype=np.uint8)  # scale = 0.5

    boxes = detect_faces(encode(big))

    assert boxes and all(box == (20, 20, 40, 40) for box in boxes)


# --- EXIF: orientation and GPS -----------------------------------------------


def exif_app1(orientation, endian="II"):
    """A minimal Exif APP1 segment: one IFD0 entry, tag 0x0112."""
    if endian == "II":
        tiff = (
            b"II*\x00\x08\x00\x00\x00"
            + b"\x01\x00"
            + b"\x12\x01\x03\x00\x01\x00\x00\x00"
            + orientation.to_bytes(2, "little") + b"\x00\x00"
            + b"\x00\x00\x00\x00"
        )
    else:
        tiff = (
            b"MM\x00*\x00\x00\x00\x08"
            + b"\x00\x01"
            + b"\x01\x12\x00\x03\x00\x00\x00\x01"
            + orientation.to_bytes(2, "big") + b"\x00\x00"
            + b"\x00\x00\x00\x00"
        )
    payload = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload


def with_exif(jpeg_bytes, app1):
    assert jpeg_bytes[:2] == b"\xff\xd8"
    return b"\xff\xd8" + app1 + jpeg_bytes[2:]


def landscape_with_marker():
    """40x20, black, with a white square in the top-left corner."""
    img = np.zeros((20, 40, 3), dtype=np.uint8)
    img[0:6, 0:6] = 255
    return img


@pytest.mark.parametrize("endian", ["II", "MM"])
def test_orientation_6_is_physically_applied(endian):
    tagged = with_exif(encode(landscape_with_marker()), exif_app1(6, endian))

    out = decode(strip_gps(tagged))

    # Orientation 6 means "rotate 90 CW to display": 40x20 becomes 20x40, and
    # the top-left marker lands in the top-RIGHT corner.
    assert out.shape[:2] == (40, 20)
    assert out[2, 17].mean() > 200  # marker now top-right
    assert out[2, 2].mean() < 50  # top-left now dark


def test_orientation_1_and_untagged_images_pass_through_unrotated():
    plain = encode(landscape_with_marker())
    for source in (plain, with_exif(plain, exif_app1(1))):
        out = decode(strip_gps(source))
        assert out.shape[:2] == (20, 40)
        assert out[2, 2].mean() > 200


def test_exif_including_gps_does_not_survive_processing():
    tagged = with_exif(encode(landscape_with_marker()), exif_app1(6))
    assert b"Exif\x00\x00" in tagged

    result = process_upload(tagged)

    assert result.gps_stripped is True
    assert b"Exif\x00\x00" not in result.image_bytes


# --- process_upload ----------------------------------------------------------


def test_process_upload_contract():
    result = process_upload(encode(noisy_image()))
    assert isinstance(result, ProcessedImage)
    assert result.image_bytes[:2] == b"\xff\xd8"
    decode(result.image_bytes)
    assert result.face_count >= 0
    assert result.gps_stripped is True


def test_process_upload_reencodes_png_as_jpeg():
    ok, buf = cv2.imencode(".png", noisy_image())
    assert ok
    result = process_upload(buf.tobytes())
    assert result.image_bytes[:2] == b"\xff\xd8"


def test_process_upload_rejects_undecodable_bytes():
    with pytest.raises(ValueError):
        process_upload(b"not an image at all")
