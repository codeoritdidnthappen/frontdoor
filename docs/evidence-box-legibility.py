"""Is the evidence box legible over an arbitrary photograph? (TICK-467, #467)

Generates the tables in evidence-boxes.md.

The box is drawn over a receipt photograph, and a receipt photograph can be
anything: a white stucco wall in full sun, a black glass shopfront, a brick
facade at dusk. A stroke colour that looks right on one of them is not an
answer, so this sweeps EVERY DISPLAYED PIXEL of the whole pilot corpus and
reports the worst case, the same method the round that placed the white
doorway guide used and for the same reason.

WHAT IS MEASURED
----------------
The mark's cross-section is

    photograph | halo | stroke | halo | photograph

so a reader can see it if EITHER boundary is visible. Per displayed pixel P:

    H(P)  = the halo, indigo900 composited over P at the halo's alpha
    outer = contrast(H(P), P)          the halo against the photograph
    inner = contrast(stroke, H(P))     the stroke against the halo
    mark  = max(outer, inner)          the mark is legible if either edge is

and the naive comparison -- the same stroke with no halo -- is
contrast(stroke, P). Contrast is WCAG 2.x relative luminance; compositing is
in sRGB, because that is where a browser composites a `box-shadow`.

The threshold that applies to a mark rather than to text is WCAG 2.1 SC 1.4.11
(non-text contrast), which is 3:1. 4.5:1 is reported beside it because it is
the number the earlier glyph sweep quoted.

GEOMETRY
--------
Measured on the served page (GET /app) in a browser at the 375px viewport,
not assumed: `.rcpt-shot` is 166x220 CSS px when a receipt shows two
photographs and 339x220 when it shows one, at devicePixelRatio 2. The stored
frame is what the receipt displays -- orientation applied, long side capped at
DECODE_MAX_SIDE (TICK-453) -- and it reaches those boxes through
`object-fit:cover`, which scales to fill and centre-crops the overflow. That
crop is reproduced here, so the pixels swept are the pixels a reader sees and
not the pixels the file holds.

USAGE
-----
The captures are repo-external (D-018), so the corpus root is a required
argument and there is no default pointing outside the repository.

    python docs/evidence-box-legibility.py --photos <corpus root> [--json <out>]

Needs pillow; pillow-heif as well if the corpus holds HEIC, which the pilot's
does. Anything that will not decode is reported and counted, never skipped
silently -- a sweep that quietly dropped the dark photographs would report the
answer it was hoping for.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover - corpus-dependent
    pass

#: The stored frame the receipt displays. Long side capped at 2048 (TICK-453),
#: so geometry and legibility are both measured in the frame that is served.
DECODE_MAX_SIDE = 2048

#: `.rcpt-shot`, measured on the served page rather than read off the CSS.
LAYOUTS = {"two-up (166x220)": (166, 220), "one-up (339x220)": (339, 220)}
DPR = 2

#: The mark, as design-source/entrymap-app.html declares it.
STROKE = (255, 255, 255)  # --evbox-ink, --white
HALO_RGB = (30, 17, 66)  # --evbox-halo, indigo900
HALO_ALPHA = 0.60

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
AA = 3.0  # SC 1.4.11 non-text contrast
AAA = 4.5  # the figure the earlier glyph sweep quoted


def luminance(rgb):
    """WCAG relative luminance for an array of sRGB triples in 0..255."""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = np.maximum(la, lb), np.minimum(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def stored_frame(path):
    """The bytes the receipt shows: orientation applied, long side capped."""
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    longest = max(img.size)
    if longest > DECODE_MAX_SIDE:
        scale = DECODE_MAX_SIDE / longest
        img = img.resize(
            (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
            Image.LANCZOS,
        )
    return img


def cover(img, box_w, box_h):
    """`object-fit:cover` into box_w x box_h: scale to fill, centre-crop."""
    scale = max(box_w / img.width, box_h / img.height)
    filled = img.resize(
        (max(box_w, round(img.width * scale)), max(box_h, round(img.height * scale))),
        Image.LANCZOS,
    )
    left = (filled.width - box_w) // 2
    top = (filled.height - box_h) // 2
    return filled.crop((left, top, left + box_w, top + box_h))


def sweep(displayed):
    """Worst case and below-threshold share over every pixel of one frame."""
    photo = np.asarray(displayed, dtype=np.float64)
    halo = HALO_ALPHA * np.array(HALO_RGB, dtype=np.float64) + (1 - HALO_ALPHA) * photo

    naive = contrast(STROKE, photo)
    outer = contrast(halo, photo)
    inner = contrast(STROKE, halo)
    mark = np.maximum(outer, inner)

    n = photo.shape[0] * photo.shape[1]
    return {
        "naive_worst": float(naive.min()),
        "naive_below_3": float((naive < AA).sum() / n),
        "naive_below_4_5": float((naive < AAA).sum() / n),
        "mark_worst": float(mark.min()),
        "mark_below_3": float((mark < AA).sum() / n),
        "mark_below_4_5": float((mark < AAA).sum() / n),
        "outer_worst": float(outer.min()),
        "inner_worst": float(inner.min()),
    }


def guaranteed_floor():
    """The stroke-against-halo floor, over every colour a pixel can be.

    The halo is opaque enough that the stroke's own boundary cannot depend on
    the photograph very much: the halo is at most (1 - alpha) of the pixel
    under it, so the lightest halo possible is the one over white. That makes
    the inner boundary's worst case a CONSTANT, computable without a corpus,
    and it is the reason a halo answers the arbitrary-photograph problem at
    all where a bare stroke cannot.
    """
    grid = np.array(
        [[r, g, b] for r in range(0, 256, 5) for g in range(0, 256, 5) for b in range(0, 256, 5)],
        dtype=np.float64,
    )
    halo = HALO_ALPHA * np.array(HALO_RGB, dtype=np.float64) + (1 - HALO_ALPHA) * grid
    inner = contrast(STROKE, halo)
    worst = grid[int(inner.argmin())]
    return float(inner.min()), tuple(int(v) for v in worst)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--photos",
        type=Path,
        required=True,
        help="root of the capture corpus (repo-external, D-018)",
    )
    parser.add_argument("--json", type=Path, default=None, help="write the per-frame rows here")
    args = parser.parse_args(argv)

    paths = sorted(
        p for p in args.photos.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES and p.is_file()
    )
    if not paths:
        print(f"no photographs under {args.photos}", file=sys.stderr)
        return 1

    floor, floor_at = guaranteed_floor()
    print(f"photographs found: {len(paths)}")
    print(
        f"stroke-against-halo floor over every possible pixel: {floor:.2f}:1 "
        f"(worst at rgb{floor_at})\n"
    )

    rows, unreadable = [], []
    for i, path in enumerate(paths, 1):
        try:
            frame = stored_frame(path)
        except Exception as exc:  # noqa: BLE001 - reported, never skipped silently
            unreadable.append((str(path), repr(exc)))
            continue
        for layout, (w, h) in LAYOUTS.items():
            result = sweep(cover(frame, w * DPR, h * DPR))
            result.update(layout=layout, frame=path.name)
            rows.append(result)
        if i % 25 == 0:
            print(f"  {i}/{len(paths)}", file=sys.stderr)

    print(f"photographs swept: {len(rows) // len(LAYOUTS)}")
    if unreadable:
        print(f"photographs that would not decode: {len(unreadable)}")
        for path, exc in unreadable[:5]:
            print(f"  {path}: {exc}")

    header = f"{'layout':<18}{'mark':>9}{'<3:1':>8}{'<4.5:1':>9}{'naive':>9}{'<3:1':>8}{'<4.5:1':>9}"
    print("\nworst case over every displayed pixel, and how many of the "
          "photographs fall below each threshold:")
    print(header)
    print("-" * len(header))
    summary = {}
    for layout in LAYOUTS:
        here = [r for r in rows if r["layout"] == layout]
        n = len(here)
        mark_worst = min(r["mark_worst"] for r in here)
        naive_worst = min(r["naive_worst"] for r in here)
        mark_3 = sum(1 for r in here if r["mark_worst"] < AA)
        mark_45 = sum(1 for r in here if r["mark_worst"] < AAA)
        naive_3 = sum(1 for r in here if r["naive_worst"] < AA)
        naive_45 = sum(1 for r in here if r["naive_worst"] < AAA)
        print(
            f"{layout:<18}{mark_worst:>8.2f}:1{mark_3:>6}/{n}{mark_45:>7}/{n}"
            f"{naive_worst:>8.2f}:1{naive_3:>6}/{n}{naive_45:>7}/{n}"
        )
        summary[layout] = {
            "photographs": n,
            "mark_worst": mark_worst,
            "mark_below_3": mark_3,
            "mark_below_4_5": mark_45,
            "naive_worst": naive_worst,
            "naive_below_3": naive_3,
            "naive_below_4_5": naive_45,
            "outer_worst": min(r["outer_worst"] for r in here),
            "inner_worst": min(r["inner_worst"] for r in here),
        }

    print(
        "\na worst case is one pixel; this is how much of each photograph is "
        "hostile to a bare stroke (share of displayed pixels under 3:1):"
    )
    print(f"{'layout':<18}{'median':>9}{'mean':>8}{'max':>8}")
    for layout in LAYOUTS:
        here = [r["naive_below_3"] for r in rows if r["layout"] == layout]
        here.sort()
        median = here[len(here) // 2]
        print(
            f"{layout:<18}{median * 100:>8.1f}%{sum(here) / len(here) * 100:>7.1f}%"
            f"{max(here) * 100:>7.1f}%"
        )
        summary[layout]["naive_share_under_3_median"] = median
        summary[layout]["naive_share_under_3_max"] = max(here)
        mark_share = max(r["mark_below_3"] for r in rows if r["layout"] == layout)
        summary[layout]["mark_share_under_3_max"] = mark_share

    print(
        "\nThe halo's own boundary against the photograph (outer) is allowed to "
        "vanish -- it does, on a dark doorway, which is the whole reason a bare "
        "stroke was not enough either. What carries the mark there is the stroke "
        "against the halo (inner), and that is the column with a floor."
    )
    for layout, s in summary.items():
        print(
            f"  {layout:<18} outer worst {s['outer_worst']:.2f}:1"
            f"   inner worst {s['inner_worst']:.2f}:1"
        )

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "guaranteed_inner_floor": floor,
                    "guaranteed_inner_floor_at": floor_at,
                    "summary": summary,
                    "unreadable": unreadable,
                    "frames": rows,
                },
                indent=1,
            ),
            encoding="utf-8",
        )
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
