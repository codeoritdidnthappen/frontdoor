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
mode this ticket exists for. The primary detector is YuNet
(cv2.FaceDetectorYN, model committed under models/ - see models/README.md),
run at a deliberately low score threshold: on the pilot photos it finds the
small through-glass and reflected faces the Haar cascades measurably missed.
The Haar pass from the first cut is kept as a cheap supplementary net - both
frontal and profile cascades, the profile cascade also on the mirrored image
(it only knows one profile), everything again on a contrast-boosted (CLAHE)
copy for ghosted reflections. All boxes from both detectors are unioned.

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

import math
import threading
from dataclasses import dataclass
from importlib import resources

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

#: YuNet score threshold. The model default is 0.9; this is set far below it
#: on purpose - recall over precision, same reasoning as the Haar tuning. On
#: the pilot photos the small through-glass faces score in the 0.4-0.8 range.
YUNET_SCORE_THRESHOLD = 0.35

#: Two-tier acceptance: below YUNET_SCORE_THRESHOLD a detection is kept only
#: when it is SMALL (longest side at most YUNET_SMALL_FACE_FRACTION of the
#: image's long side) and still scores at least this. Measured rationale: the
#: pilot's dim through-glass faces (~15-20px) score 0.15-0.25 - systematically
#: under-scored for lack of pixels - and a small false positive blurs a
#: hand-sized patch of glass, costing nothing. A LOW-score LARGE box is the
#: opposite on both counts: almost never a face, and blurring half the door
#: can destroy the hardware evidence a criterion actually reads - so large
#: boxes stay held to the full threshold. 0.15 is set from the worst real
#: face in the pilot set (0.196 contrast-boosted), with headroom.
YUNET_SMALL_SCORE_THRESHOLD = 0.15
YUNET_SMALL_FACE_FRACTION = 0.05

#: YuNet detects on its own copy, downscaled to at most this long side -
#: larger than DETECT_MAX_SIDE because the DNN, unlike the cascades, keeps
#: finding faces as they get small IF the pixels are there: measured on the
#: pilot photos, ~20px through-glass faces score ~0.6 at 2048 and ~0.2 at
#: 1600. One YuNet pass at 2048 is still far cheaper than the Haar stack.
YUNET_MAX_SIDE = 2048

#: The YuNet model committed with the package; see models/README.md for
#: source and license. Committed so runtime needs no download.
YUNET_MODEL = "models/face_detection_yunet_2023mar.onnx"

_cascades = None
_yunet = None
#: FaceDetectorYN is stateful (setInputSize before each detect), so the shared
#: instance is guarded; concurrent /screen requests must not interleave it.
_yunet_lock = threading.Lock()


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


def _get_yunet():
    """Load the committed YuNet model, once. Callers hold _yunet_lock.

    Created at the LOW threshold; the two-tier score/size rule is applied in
    _detect_yunet, where the box size is known.
    """
    global _yunet
    if _yunet is None:
        model = resources.files("frontdoor").joinpath(YUNET_MODEL)
        with resources.as_file(model) as path:
            _yunet = cv2.FaceDetectorYN.create(
                str(path), "", (320, 320),
                score_threshold=YUNET_SMALL_SCORE_THRESHOLD,
            )
    return _yunet


def _boost_luma(img):
    """CLAHE on the luminance channel: same trick the Haar pass uses, in
    color. The pilot's dim behind-glass faces score ~0.1 higher on it."""
    ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
    ycrcb[:, :, 0] = cv2.createCLAHE(
        clipLimit=3.0, tileGridSize=(8, 8)
    ).apply(ycrcb[:, :, 0])
    return cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)


def _detect_yunet(small):
    """YuNet boxes as (x, y, w, h) in the (downscaled) image's coordinates.

    Runs on the image and on a contrast-boosted copy, unioned. Each detection
    passes the two-tier rule: full YUNET_SCORE_THRESHOLD for any size, or
    YUNET_SMALL_SCORE_THRESHOLD for small boxes (see the constants above).
    """
    height, width = small.shape[:2]
    small_limit = YUNET_SMALL_FACE_FRACTION * max(height, width)
    boxes = []
    with _yunet_lock:
        detector = _get_yunet()
        detector.setInputSize((width, height))
        for variant in (small, _boost_luma(small)):
            _, faces = detector.detect(variant)
            if faces is None:
                continue
            # Rows are [x, y, w, h, 10 landmark floats, score]; boxes can poke
            # past the frame edge - _blur clamps, so only rounding happens here.
            # Out-of-DOMAIN is different from out-of-range: on some OpenCV
            # builds YuNet emits non-finite coordinates for degenerate inputs
            # (PR #243 review repro: a 32x32 featureless frame), and round(inf)
            # raises OverflowError before _blur ever sees the box. A box that
            # is nowhere blurs nothing - skip the row.
            for row in faces:
                x, y, w, h, score = *row[:4], row[14]
                if not all(math.isfinite(float(v)) for v in (x, y, w, h)):
                    continue
                if score >= YUNET_SCORE_THRESHOLD or max(w, h) <= small_limit:
                    boxes.append(
                        (round(float(x)), round(float(y)),
                         round(float(w)), round(float(h)))
                    )
    return boxes


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
    # Primary pass: YuNet at a low threshold, on its own larger copy
    # (YUNET_MAX_SIDE) so the small through-glass faces keep enough pixels
    # to score above threshold.
    yscale = min(1.0, YUNET_MAX_SIDE / max(img.shape[:2]))
    ysmall = img if yscale == 1.0 else cv2.resize(
        img, None, fx=yscale, fy=yscale, interpolation=cv2.INTER_AREA
    )
    boxes = [
        (round(x / yscale), round(y / yscale), round(w / yscale), round(h / yscale))
        for x, y, w, h in _detect_yunet(ysmall)
    ]

    # Supplementary pass: the Haar union from the first cut. Cheap, and its
    # CLAHE and mirrored variants still add recall on ghosted reflections
    # that YuNet scores under even the low threshold.
    frontal, profile = _get_cascades()
    scale = min(1.0, DETECT_MAX_SIDE / max(img.shape[:2]))
    small = img if scale == 1.0 else cv2.resize(
        img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
    )
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    boosted = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)

    haar_boxes = []
    for variant in (gray, boosted):
        width = variant.shape[1]
        mirrored = cv2.flip(variant, 1)
        # Recall-tuned: small scale step, few required neighbors, small floor.
        kwargs = {"scaleFactor": 1.06, "minNeighbors": 3, "minSize": (20, 20)}
        haar_boxes.extend(frontal.detectMultiScale(variant, **kwargs))
        haar_boxes.extend(profile.detectMultiScale(variant, **kwargs))
        # The profile cascade only knows one facing; the mirror catches the other.
        for x, y, w, h in profile.detectMultiScale(mirrored, **kwargs):
            haar_boxes.append((width - x - w, y, w, h))

    boxes.extend(
        (round(x / scale), round(y / scale), round(w / scale), round(h / scale))
        for x, y, w, h in haar_boxes
    )
    return boxes


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
