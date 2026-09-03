"""Automatic face blurring at ingest (TICK-257, #232).

The TICK-092 pilot lost 17 of 65 captures to identifiable faces the operator
never saw - reflections in door glass, people inside visible through the pane,
the photographer's own reflection. This module is the systematic fix: detect
faces and irreversibly blur them before an image is stored or sent to the
vision model, so privacy stops depending on operator vigilance. Blurring is
evidence-free for this product: every screening criterion is about the
entrance, never about people.

Detection is tuned for recall over precision. A false positive costs a blurred
patch of door glass, which no criterion reads; a false negative is the failure
mode this ticket exists for. Both the frontal and profile Haar cascades run,
the profile cascade also runs on the mirrored image (it only knows one
profile), and everything runs again on a contrast-boosted (CLAHE) copy to help
with ghosted reflections in glass. All boxes are unioned.

EXIF policy - deliberate, read before "fixing":
    Re-encoding through OpenCV drops the entire EXIF block, GPS included -
    which is exactly what the ticket's location-stripping AC asks for. The one
    tag that cannot simply be dropped is Orientation, so its rotation is
    physically applied to the pixels before re-encode; after that the tag is
    redundant and dropping it is safe. Every other tag this project cares
    about (captured_at, device_model) lives in the capture SIDECAR
    (capture_sidecar.schema.json), never in image EXIF, so losing EXIF at
    ingest is by design: GPS stripping comes free, and nothing downstream
    reads image metadata.
"""

from dataclasses import dataclass

import cv2
import numpy as np

#: JPEG quality for re-encoded output. High enough that screening evidence
#: (hardware detail, surface texture) is not degraded by the privacy pass.
JPEG_QUALITY = 90

#: Detection runs on a copy downscaled to at most this many pixels on the long
#: side. 12MP phone captures make multi-cascade Haar detection cost seconds;
#: at 1600px a reflected face of ~60px still clears the minimum size below.
DETECT_MAX_SIDE = 1600

#: Each detected box is expanded by this fraction on every side before
#: blurring, so hairlines and chins do not survive at the box edge.
BOX_MARGIN = 0.30

#: Pixelation target: the blurred region is resized down to this many pixels
#: wide (height scaled to match) and back up. At 12px across, a face is a
#: handful of flat color blocks - unrecoverable by construction, not by
#: kernel-size tuning.
PIXELATE_WIDTH = 12

_cascades = None


def _get_cascades():
    """Load the Haar cascades OpenCV ships, once."""
    global _cascades
    if _cascades is None:
        base = cv2.data.haarcascades
        _cascades = (
            cv2.CascadeClassifier(base + "haarcascade_frontalface_default.xml"),
            cv2.CascadeClassifier(base + "haarcascade_profileface.xml"),
        )
    return _cascades


def _decode(image_bytes):
    """Decode to a BGR array with EXIF orientation physically applied.

    IMREAD_IGNORE_ORIENTATION turns off OpenCV's own EXIF handling so the
    rotation happens exactly once, here, where it is explicit and tested.
    """
    img = cv2.imdecode(
        np.frombuffer(image_bytes, dtype=np.uint8),
        cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION,
    )
    if img is None:
        raise ValueError("could not decode image bytes")
    return _apply_orientation(img, _exif_orientation(image_bytes))


def _exif_orientation(image_bytes):
    """Return the EXIF Orientation value (1-8), or 1 when absent or unreadable.

    OpenCV's decoder ignores EXIF, so the JPEG APP1 segment is walked by hand:
    find the Exif APP1, then tag 0x0112 in IFD0 of its TIFF block.
    """
    if image_bytes[:2] != b"\xff\xd8":
        return 1  # not a JPEG; PNG/WebP carry no EXIF orientation worth honoring
    i = 2
    while i + 4 <= len(image_bytes):
        if image_bytes[i] != 0xFF:
            return 1
        marker = image_bytes[i + 1]
        if marker == 0xD8 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0xDA:  # start of scan: no APP segments past this point
            return 1
        length = int.from_bytes(image_bytes[i + 2 : i + 4], "big")
        if length < 2:
            return 1
        if marker == 0xE1 and image_bytes[i + 4 : i + 10] == b"Exif\x00\x00":
            return _orientation_from_tiff(image_bytes[i + 10 : i + 2 + length])
        i += 2 + length
    return 1


def _orientation_from_tiff(tiff):
    try:
        endian = {b"II": "little", b"MM": "big"}[tiff[:2]]
        ifd = int.from_bytes(tiff[4:8], endian)
        count = int.from_bytes(tiff[ifd : ifd + 2], endian)
        for n in range(count):
            entry = tiff[ifd + 2 + 12 * n : ifd + 14 + 12 * n]
            if int.from_bytes(entry[0:2], endian) == 0x0112:
                value = int.from_bytes(entry[8:10], endian)
                return value if 1 <= value <= 8 else 1
    except (KeyError, IndexError):
        pass
    return 1


def _apply_orientation(img, orientation):
    if orientation == 2:
        return cv2.flip(img, 1)
    if orientation == 3:
        return cv2.rotate(img, cv2.ROTATE_180)
    if orientation == 4:
        return cv2.flip(img, 0)
    if orientation == 5:
        return cv2.transpose(img)
    if orientation == 6:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if orientation == 7:
        return cv2.flip(cv2.transpose(img), -1)
    if orientation == 8:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img


def _detect(img):
    """Detect faces in a BGR array; boxes as (x, y, w, h) in its coordinates."""
    frontal, profile = _get_cascades()
    scale = min(1.0, DETECT_MAX_SIDE / max(img.shape[:2]))
    small = img if scale == 1.0 else cv2.resize(
        img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
    )
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    boosted = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)

    boxes = []
    for variant in (gray, boosted):
        width = variant.shape[1]
        mirrored = cv2.flip(variant, 1)
        # Recall-tuned: small scale step, few required neighbors, small floor.
        kwargs = {"scaleFactor": 1.06, "minNeighbors": 3, "minSize": (20, 20)}
        boxes.extend(frontal.detectMultiScale(variant, **kwargs))
        boxes.extend(profile.detectMultiScale(variant, **kwargs))
        # The profile cascade only knows one facing; the mirror catches the other.
        for x, y, w, h in profile.detectMultiScale(mirrored, **kwargs):
            boxes.append((width - x - w, y, w, h))

    return [
        (round(x / scale), round(y / scale), round(w / scale), round(h / scale))
        for x, y, w, h in boxes
    ]


def _blur(img, boxes):
    """Pixelate each box (expanded by BOX_MARGIN) in place; irreversible."""
    height, width = img.shape[:2]
    for x, y, w, h in boxes:
        mx, my = round(w * BOX_MARGIN), round(h * BOX_MARGIN)
        x0, y0 = max(0, x - mx), max(0, y - my)
        x1, y1 = min(width, x + w + mx), min(height, y + h + my)
        if x1 <= x0 or y1 <= y0:
            continue
        region = img[y0:y1, x0:x1]
        rh, rw = region.shape[:2]
        tw = min(PIXELATE_WIDTH, rw)
        th = min(max(1, round(rh * tw / rw)), rh)
        down = cv2.resize(region, (tw, th), interpolation=cv2.INTER_AREA)
        img[y0:y1, x0:x1] = cv2.resize(down, (rw, rh), interpolation=cv2.INTER_NEAREST)
    return img


def _encode(img):
    ok, encoded = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise ValueError("could not encode image as JPEG")
    return encoded.tobytes()


def detect_faces(image_bytes):
    """Return face boxes as (x, y, w, h) in the orientation-applied frame."""
    return _detect(_decode(image_bytes))


def blur_faces(image_bytes):
    """Blur every detected face; return (processed JPEG bytes, face count)."""
    img = _decode(image_bytes)
    boxes = _detect(img)
    return _encode(_blur(img, boxes)), len(boxes)


def strip_gps(image_bytes):
    """Return JPEG bytes with no EXIF (GPS included), orientation applied.

    See the module docstring: orientation is preserved by rotating the pixels,
    everything else this project keeps lives in the sidecar.
    """
    return _encode(_decode(image_bytes))


@dataclass(frozen=True)
class ProcessedImage:
    image_bytes: bytes
    face_count: int
    gps_stripped: bool


def process_upload(image_bytes):
    """The one ingest entry point: blur faces, strip EXIF/GPS, re-encode.

    Returns a ProcessedImage; raises ValueError for bytes no decoder accepts
    (the caller decides what an undecodable upload means on its path).
    """
    img = _decode(image_bytes)
    boxes = _detect(img)
    return ProcessedImage(
        image_bytes=_encode(_blur(img, boxes)),
        face_count=len(boxes),
        gps_stripped=True,
    )
