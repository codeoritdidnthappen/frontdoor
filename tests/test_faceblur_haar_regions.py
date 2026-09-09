"""The cascades sweep only around YuNet's boxes now - proof and measurement.

TICK-472. `faceblur._detect` used to run six Haar passes over the whole frame
and then throw away every box no YuNet detection stood near (#350). It now
runs them only over padded neighbourhoods of the YuNet boxes, derived in
`_haar_scan_regions` from BOX_MARGIN and HAAR_CORROBORATION_IOU. Two claims
have to hold, and this file is split along them:

  * THE DERIVATION IS SOUND. A cascade box that could clear the corroboration
    threshold is inside the swept region. That is arithmetic, so it is tested
    as arithmetic - over generated geometry, with no photograph and no
    detector in it. These tests run everywhere.
  * THE DETECTOR AGREES. The regions are BLACKED OUT rather than cropped, so
    the frame keeps its size and every pixel inside a region reaches the
    cascade exactly as it did before (cropping does not: detectMultiScale
    rebuilds its scale pyramid from whatever image it was handed, and
    measured over the 62 captures a cropping implementation changed the
    accepted set on 13 of them and lost 44093 pixels of blur). What masking
    still cannot rule out by argument is the black itself firing a cascade at
    a region's edge. Only photographs settle that, so the equivalence test
    below recomputes the WHOLE-FRAME path for every capture and compares. It
    needs the capture set, which is not in this repository - point
    FRONTDOOR_CAPTURE_PHOTOS at a directory of it and the test runs; leave it
    unset and the test skips, saying so.
"""

import math
import os
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from frontdoor import faceblur

#: Where the capture photographs are. They are not committed - they are
#: photographs of real doorways, several with identifiable people in the
#: glass, which is the whole reason this module exists.
PHOTO_DIR_VAR = "FRONTDOOR_CAPTURE_PHOTOS"

#: What captureFrame() in the app actually uploads: the long side capped at
#: 1280 and JPEG quality 0.85. Detection cost is what this ticket is about, so
#: the photographs are measured at the size the server really receives, not at
#: the size the camera wrote.
UPLOAD_MAX_SIDE = 1280
UPLOAD_QUALITY = 85

#: The face-bearing photographs of the TICK-092 pilot, named one by one in PR
#: #243 (TICK-257), where "0 of 17 recognizable after blur" was measured on
#: the whole-frame pass. Their blurred output is what this change is least
#: allowed to weaken, so it is checked apart from the other captures.
PILOT_FACE_PHOTOS = (
    "IMG_3221", "IMG_3222", "IMG_3225", "IMG_3226", "IMG_3229", "IMG_3240",
    "IMG_3244", "IMG_3250", "IMG_3258", "IMG_3261", "IMG_3262", "IMG_3271",
    "IMG_3272", "IMG_3276", "IMG_3277", "IMG_3280", "IMG_3281",
)


def _photographs():
    value = os.environ.get(PHOTO_DIR_VAR)
    directory = Path(value) if value else None
    if directory is None or not directory.is_dir():
        return []
    return sorted(
        path for path in directory.rglob("*")
        if path.suffix.lower() in (".jpeg", ".jpg")
    )


_PHOTOGRAPHS = _photographs()

needs_photographs = pytest.mark.skipif(
    not _PHOTOGRAPHS,
    reason=(
        f"set {PHOTO_DIR_VAR} to a directory of capture photographs to run the "
        f"equivalence check; the photographs are not committed"
    ),
)


def _upload_bytes(path):
    """The photograph as the app would upload it: long side 1280, JPEG q85."""
    img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert img is not None, f"could not decode {path.name}"
    height, width = img.shape[:2]
    scale = min(1.0, UPLOAD_MAX_SIDE / max(height, width))
    if scale < 1.0:
        img = cv2.resize(
            img, (round(width * scale), round(height * scale)),
            interpolation=cv2.INTER_AREA,
        )
    ok, encoded = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, UPLOAD_QUALITY])
    assert ok
    return encoded.tobytes()


def _whole_frame_detect(img):
    """`_detect` as it stood before TICK-472: six cascade passes over the
    entire frame, corroboration afterwards. Returns (yunet, accepted).

    Written out here rather than remembered from a fixture, so the comparison
    is against a path that actually RAN on this OpenCV build, on this
    photograph, in this process. Everything it does not change - the YuNet
    pass, the corroboration rule, the two scalings - it calls out of the
    module, so a drift in those cannot make the two sides agree spuriously.
    """
    yscale = min(1.0, faceblur.YUNET_MAX_SIDE / max(img.shape[:2]))
    ysmall = img if yscale == 1.0 else cv2.resize(
        img, None, fx=yscale, fy=yscale, interpolation=cv2.INTER_AREA
    )
    yunet_boxes = [
        (round(x / yscale), round(y / yscale), round(w / yscale), round(h / yscale))
        for x, y, w, h in faceblur._detect_yunet(ysmall)
    ]

    frontal, profile = faceblur._get_cascades()
    scale = min(1.0, faceblur.DETECT_MAX_SIDE / max(img.shape[:2]))
    small = img if scale == 1.0 else cv2.resize(
        img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
    )
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    boosted = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)

    haar_boxes = []
    for variant in (gray, boosted):
        width = variant.shape[1]
        mirrored = cv2.flip(variant, 1)
        kwargs = {"scaleFactor": 1.06, "minNeighbors": 3, "minSize": (20, 20)}
        haar_boxes.extend(frontal.detectMultiScale(variant, **kwargs))
        haar_boxes.extend(profile.detectMultiScale(variant, **kwargs))
        for x, y, w, h in profile.detectMultiScale(mirrored, **kwargs):
            haar_boxes.append((width - x - w, y, w, h))

    candidates = [
        (round(x / scale), round(y / scale), round(w / scale), round(h / scale))
        for x, y, w, h in haar_boxes
    ]
    accepted = [
        box for box in candidates if faceblur._corroborated(box, yunet_boxes)
    ]
    return yunet_boxes, accepted


# --------------------------------------------------------------------------
# The derivation, as arithmetic. No photographs, no detector.
# --------------------------------------------------------------------------

#: Cascade box sides to probe with, in the cascade copy's own pixels. Roughly
#: geometric from the 20px floor detectMultiScale is given up to a box that
#: fills the frame, so no scale between the two goes unprobed.
_PROBE_SIDES = (20, 24, 30, 38, 48, 61, 77, 97, 122, 154, 194, 245, 309, 389,
                490, 617, 777)

_DIRECTIONS = ((1, 0), (-1, 0), (0, 1), (0, -1),
               (1, 1), (1, -1), (-1, 1), (-1, -1))


def _inside_some_region(box, regions):
    x, y, w, h = box
    return any(
        rx <= x and ry <= y and x + w <= rx + rw and y + h <= ry + rh
        for rx, ry, rw, rh in regions
    )


def _escaped(yunet_boxes, regions, shape, scale):
    """Square cascade boxes that _corroborated would accept and no region holds.

    Boxes are generated in the CASCADE COPY's coordinates, which is where the
    regions live and where detectMultiScale would find them, and taken back to
    full-image coordinates through the same round(x / scale) the module uses
    before corroboration is tested - so a padding derived at the wrong scale
    shows up here rather than in production.

    The search is a walk outwards from each YuNet box in eight directions,
    one pixel at a time, at each probe size: the boxes that matter are the
    ones at the very edge of acceptance, and a coarse grid steps over them.
    """
    height, width = shape[:2]
    escaped = []

    def verdict(xs, ys, side):
        """(corroborated, escaped) for a box at (xs, ys, side, side)."""
        if xs < 0 or ys < 0 or xs + side > width or ys + side > height:
            return False, False  # a cascade never returns a box off its image
        full = (round(xs / scale), round(ys / scale),
                round(side / scale), round(side / scale))
        if not faceblur._corroborated(full, yunet_boxes):
            return False, False
        return True, not _inside_some_region((xs, ys, side, side), regions)

    for x, y, w, h in yunet_boxes:
        cx, cy = (x + w / 2) * scale, (y + h / 2) * scale
        for side in _PROBE_SIDES:
            for dx, dy in _DIRECTIONS:
                misses, step = 0, 0
                while misses < 60 and step < max(width, height):
                    corroborated, out = verdict(
                        round(cx - side / 2 + dx * step),
                        round(cy - side / 2 + dy * step),
                        side,
                    )
                    if out:
                        escaped.append((round(cx + dx * step), side))
                    misses = 0 if corroborated else misses + 1
                    step += 1
    return escaped


@pytest.mark.parametrize("yunet_box", [
    (500, 400, 10, 12),     # the pilot's small through-glass faces
    (500, 400, 24, 29),
    (500, 400, 60, 73),
    (500, 400, 200, 190),   # a face filling much of the door
    (500, 400, 9, 40),      # elongated: the per-side bound, not the area one
    (500, 400, 40, 9),
    (2, 2, 11, 13),         # against the frame edge
    (1390, 990, 11, 13),    # against the far corner
])
def test_every_corroborated_cascade_box_is_inside_a_swept_region(yunet_box):
    """The claim the whole change rests on.

    Probes square cascade boxes - the shape OpenCV's 24x24 and 20x20 windows
    can produce - around one YuNet box. Every box `_corroborated` would ACCEPT
    has to be inside a region the cascades actually look at; a box it rejects
    may be anywhere, which is the point of the change.
    """
    shape = (1000, 1400)
    regions = faceblur._haar_scan_regions([yunet_box], shape)
    escaped = _escaped([yunet_box], regions, shape, 1.0)
    assert not escaped, (
        f"{len(escaped)} corroborated cascade boxes fall outside the swept "
        f"regions {regions}; first: {escaped[:3]}"
    )


def test_the_region_derivation_survives_the_cascade_downscale():
    """The likeliest bug in this change: boxes coming back from the cascade
    copy at one scale while YuNet's came back at another.

    Here the frame is larger than DETECT_MAX_SIDE, so the cascades read a
    downscaled copy and every box crosses back through round(x / scale) before
    corroboration sees it. YUNET_MAX_SIDE and DETECT_MAX_SIDE differ, so the
    two passes are genuinely in different coordinates, as they are on a real
    capture.
    """
    full = (3000, 2400)  # height, width
    scale = min(1.0, faceblur.DETECT_MAX_SIDE / max(full))
    assert scale < 1.0, "this test is pointless if the cascades read full size"
    small = (round(full[0] * scale), round(full[1] * scale))
    yunet_boxes = [(1200, 900, 30, 36), (400, 2100, 120, 130)]
    regions = faceblur._haar_scan_regions(yunet_boxes, small, scale)
    escaped = _escaped(yunet_boxes, regions, small, scale)
    assert not escaped, (
        f"{len(escaped)} boxes that corroborate at full scale sit outside the "
        f"regions expressed at the cascade scale; first: {escaped[:3]}"
    )


def test_the_regions_are_smaller_than_the_frame_for_a_face_sized_box():
    """Otherwise the change is a rewrite that saves nothing."""
    shape = (1280, 960)
    regions = faceblur._haar_scan_regions([(400, 500, 14, 17)], shape)
    swept = sum(w * h for _, _, w, h in regions)
    assert swept < 0.15 * shape[0] * shape[1]


def test_no_yunet_boxes_means_no_regions():
    """The empty case is the same proof, not a shortcut: with nothing to
    corroborate against, no cascade box could ever be kept."""
    assert faceblur._haar_scan_regions([], (1000, 1400)) == []


class _RefusingCascade:
    """A cascade that fails the test if anything asks it to detect."""

    def getOriginalWindowSize(self):
        return (24, 24)

    def detectMultiScale(self, *args, **kwargs):
        raise AssertionError("a cascade ran with no YuNet box to corroborate")


def test_the_cascades_do_not_run_when_yunet_found_nothing(monkeypatch):
    """...and _detect really skips them, rather than computing regions that
    happen to come out empty."""
    monkeypatch.setattr(faceblur, "_detect_yunet", lambda _: [])
    monkeypatch.setattr(
        faceblur, "_get_cascades", lambda: (_RefusingCascade(), _RefusingCascade())
    )
    assert faceblur._detect(np.full((400, 600, 3), 127, dtype=np.uint8)) == []


def test_an_unloadable_cascade_still_fails_closed_with_no_yunet_boxes(
        monkeypatch, tmp_path):
    """The skip must not become a way round the fail-closed contract: a
    cascade that did not load is a FaceDetectorError on every image, including
    one YuNet found nothing in (#370). cv2.CascadeClassifier returns an EMPTY
    classifier for a missing XML rather than raising, so an empty directory is
    all it takes to reproduce."""
    monkeypatch.setattr(faceblur, "_detect_yunet", lambda _: [])
    monkeypatch.setattr(faceblur, "_cascades", None)
    monkeypatch.setattr(cv2.data, "haarcascades", str(tmp_path) + "/")
    with pytest.raises(faceblur.FaceDetectorError):
        faceblur._detect(np.full((400, 600, 3), 127, dtype=np.uint8))


def test_the_cascades_read_a_frame_of_the_same_size_with_the_regions_intact():
    """Masked, not cropped: the frame keeps its dimensions - which is what
    keeps detectMultiScale's scale pyramid, and so the pixels the cascade
    scores, identical to the whole-frame pass - and inside a region not one
    pixel is touched."""
    rng = np.random.default_rng(0)
    variant = rng.integers(0, 255, (400, 600), dtype=np.uint8)
    regions = [(50, 60, 120, 90), (300, 200, 80, 80)]
    masked = faceblur._outside_regions_blacked(variant, regions)
    assert masked.shape == variant.shape and masked.dtype == variant.dtype
    kept = np.zeros(variant.shape, bool)
    for x, y, w, h in regions:
        kept[y:y + h, x:x + w] = True
        assert np.array_equal(masked[y:y + h, x:x + w], variant[y:y + h, x:x + w])
    assert not masked[~kept].any()


def test_the_window_aspect_is_read_off_the_loaded_cascades():
    """The area bound becomes a per-side bound only because a cascade box
    carries its window's aspect ratio. That ratio is read, not assumed."""
    widest, narrowest = faceblur._cascade_window_aspect(faceblur._get_cascades())
    assert narrowest <= widest
    for cascade in faceblur._get_cascades():
        w, h = cascade.getOriginalWindowSize()
        assert narrowest <= w / h <= widest


def test_a_detector_that_will_not_give_its_window_gets_no_guessed_one():
    """A stand-in, or a future backend that is not a cascade, cannot be
    assumed square. It falls back to the per-side bound, which holds for a box
    of any shape - so the regions get bigger, never smaller."""

    class _Silent:
        pass

    assert faceblur._cascade_window_aspect([_Silent()]) == (math.inf, 0.0)
    box = [(500, 400, 40, 48)]
    unknown = faceblur._haar_scan_regions([*box], (1000, 1400), 1.0, math.inf, 0.0)
    square = faceblur._haar_scan_regions([*box], (1000, 1400), 1.0, 1.0, 1.0)
    assert unknown and square
    for (ux, uy, uw, uh), (sx, sy, sw, sh) in zip(unknown, square):
        assert ux <= sx and uy <= sy and ux + uw >= sx + sw and uy + uh >= sy + sh
    escaped = _escaped(box, unknown, (1000, 1400), 1.0)
    assert not escaped, escaped[:3]


# --------------------------------------------------------------------------
# The detector, on real photographs.
# --------------------------------------------------------------------------


@needs_photographs
@pytest.mark.parametrize("photo", _PHOTOGRAPHS, ids=[p.stem for p in _PHOTOGRAPHS])
def test_the_region_sweep_accepts_exactly_what_the_whole_frame_sweep_accepted(photo):
    """Identical, not similar: the same boxes at the same coordinates, and as
    many of each."""
    img = faceblur._decode(_upload_bytes(photo))
    expected_yunet, expected_accepted = _whole_frame_detect(img.copy())
    boxes = faceblur._detect(img.copy())
    assert boxes[:len(expected_yunet)] == expected_yunet
    assert sorted(boxes[len(expected_yunet):]) == sorted(expected_accepted)


@needs_photographs
def test_the_pilot_face_photographs_are_blurred_no_less_than_before(capsys):
    """The 0/17 result was measured on the whole-frame pass, so the pilot's
    face-bearing photographs get their own gate: byte-identical output, or
    failing that, blur that only GREW - never a pixel that used to be
    pixelated and is not any more.

    Which of the 17 are present is printed, because the audit was over all
    seventeen and a checkout holding fewer is not the same evidence.
    """
    present = [p for p in _PHOTOGRAPHS if p.stem in PILOT_FACE_PHOTOS]
    assert present, (
        f"none of the 17 face-bearing pilot photographs are under "
        f"{PHOTO_DIR_VAR}"
    )
    identical, grew = [], []
    for photo in present:
        image_bytes = _upload_bytes(photo)
        img = faceblur._decode(image_bytes)
        yunet, accepted = _whole_frame_detect(img.copy())
        before_img, before_regions = faceblur._blur(img.copy(), yunet + accepted)
        after = faceblur.process_upload(image_bytes)
        if faceblur._encode(before_img) == after.image_bytes:
            identical.append(photo.stem)
            continue
        lost = np.count_nonzero(
            _blur_mask(img.shape, before_regions)
            & ~_blur_mask(img.shape, after.blur_regions)
        )
        assert not lost, (
            f"{photo.stem}: {lost} px the whole-frame pass pixelated are no "
            f"longer pixelated"
        )
        grew.append(photo.stem)
    missing = sorted(set(PILOT_FACE_PHOTOS) - {p.stem for p in present})
    with capsys.disabled():
        print(f"\n{len(present)} of the 17 pilot face photographs present"
              f"{'; absent: ' + ', '.join(missing) if missing else ''}")
        print(f"  byte-identical output: {len(identical)}")
        print(f"  blurred no less: {len(grew)} {grew if grew else ''}")


def _blur_mask(shape, regions):
    mask = np.zeros(shape[:2], dtype=bool)
    for region in regions:
        mask[region["y"]:region["y"] + region["h"],
             region["x"]:region["x"] + region["w"]] = True
    return mask


@needs_photographs
def test_detection_is_measurably_faster_than_the_whole_frame_sweep(capsys):
    """The point of the change, measured rather than estimated - and reported
    per photograph, so a regression is legible instead of averaged away."""
    faceblur._get_cascades()
    faceblur._detect(np.full((64, 64, 3), 127, dtype=np.uint8))  # warm the model
    rows, before_total, after_total = [], 0.0, 0.0
    for photo in _PHOTOGRAPHS:
        img = faceblur._decode(_upload_bytes(photo))
        start = time.perf_counter()
        _whole_frame_detect(img.copy())
        before = time.perf_counter() - start
        start = time.perf_counter()
        faceblur._detect(img.copy())
        after = time.perf_counter() - start
        rows.append((photo.stem, before, after))
        before_total += before
        after_total += after
    with capsys.disabled():
        print(f"\n{'photograph':<16}{'whole frame':>14}{'regions':>12}{'ratio':>10}")
        for name, before, after in rows:
            print(f"{name:<16}{before:>13.2f}s{after:>11.2f}s{before / after:>9.1f}x")
        print(f"{'TOTAL':<16}{before_total:>13.2f}s{after_total:>11.2f}s"
              f"{before_total / after_total:>9.1f}x")
    assert after_total < before_total
