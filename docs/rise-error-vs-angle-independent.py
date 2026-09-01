"""3D-projection and four-corner homography check for Arm A's rise-error budget.

TICK-244 (#159). Generates the tables in rise-error-vs-angle-independent.md.
Stdlib only. Constants from ARCHITECTURE.md §4 and ISO/IEC 7810 ID-1 (D-006).

    python docs/rise-error-vs-angle-independent.py
"""

from __future__ import annotations

import math
import random

F_PX = 2934.1
CARD_LONG_MM = 85.60
CARD_SHORT_MM = 53.98
RISE_MM = 12.7
MM_PER_IN = 25.4
DELTA_PX = 5.0
BAR_IN = 0.25
DIST_MM = {"2 m": 2000.0, "3 m": 3000.0}
ANGLES_DEG = (0, 15, 30, 45)
MC_N = 4000
MC_SEED = 244

PUBLISHED = {
    0: {"2 m": 0.192, "3 m": 0.288},
    15: {"2 m": 0.199, "3 m": 0.298},
    30: {"2 m": 0.222, "3 m": 0.332},
    45: {"2 m": 0.271, "3 m": 0.407},
}

# Card in the riser plane. Rise along the right edge, next to the control points.
CARD_XY = (
    (0.0, 0.0),
    (CARD_LONG_MM, 0.0),
    (CARD_LONG_MM, CARD_SHORT_MM),
    (0.0, CARD_SHORT_MM),
)
RISE_XY = ((CARD_LONG_MM, 0.0), (CARD_LONG_MM, RISE_MM))
# Vertical segment on the optical axis — used only for the pitch vs yaw check.
CENTERED_RISE = ((0.0, 0.0), (0.0, RISE_MM))


def project(p: tuple[float, float, float], f: float = F_PX) -> tuple[float, float]:
    x, y, z = p
    return (f * x / z, f * y / z)


def rot_x(v: tuple[float, float, float], th: float) -> tuple[float, float, float]:
    x, y, z = v
    c, s = math.cos(th), math.sin(th)
    return (x, y * c - z * s, y * s + z * c)


def rot_y(v: tuple[float, float, float], ph: float) -> tuple[float, float, float]:
    x, y, z = v
    c, s = math.cos(ph), math.sin(ph)
    return (x * c + z * s, y, -x * s + z * c)


def world(pivot, offset, rotate, ang: float) -> tuple[float, float, float]:
    ox, oy, oz = rotate(offset, ang)
    return (pivot[0] + ox, pivot[1] + oy, pivot[2] + oz)


def off_xy(x: float, y: float) -> tuple[float, float, float]:
    return (x, y, 0.0)


def pix_len(pivot, off0, off1, rotate, ang: float) -> float:
    u0, v0 = project(world(pivot, off0, rotate, ang))
    u1, v1 = project(world(pivot, off1, rotate, ang))
    return math.hypot(u1 - u0, v1 - v0)


def solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        div = m[col][col]
        if abs(div) < 1e-14:
            raise ZeroDivisionError("singular")
        for j in range(col, n + 1):
            m[col][j] /= div
        for r in range(n):
            if r == col:
                continue
            f = m[r][col]
            for j in range(col, n + 1):
                m[r][j] -= f * m[col][j]
    return [m[i][n] for i in range(n)]


def _similarity(pts: list[tuple[float, float]]) -> tuple[float, float, float]:
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    mean = sum(math.hypot(p[0] - cx, p[1] - cy) for p in pts) / len(pts)
    scale = math.sqrt(2.0) / mean if mean > 1e-12 else 1.0
    return scale, cx, cy


def _t_mat(s: float, cx: float, cy: float) -> list[list[float]]:
    return [[s, 0.0, -s * cx], [0.0, s, -s * cy], [0.0, 0.0, 1.0]]


def _t_inv(s: float, cx: float, cy: float) -> list[list[float]]:
    return [[1.0 / s, 0.0, cx], [0.0, 1.0 / s, cy], [0.0, 0.0, 1.0]]


def _mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    out = [[0.0] * 3 for _ in range(3)]
    for i in range(3):
        for j in range(3):
            out[i][j] = a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j]
    return out


def _apply3(h: list[list[float]], u: float, v: float) -> tuple[float, float]:
    x = h[0][0] * u + h[0][1] * v + h[0][2]
    y = h[1][0] * u + h[1][1] * v + h[1][2]
    w = h[2][0] * u + h[2][1] * v + h[2][2]
    return (x / w, y / w)


def homography(uvs, xys) -> list[list[float]]:
    """Image → plane homography, Hartley-normalized DLT, h33 free."""
    su, cux, cuy = _similarity(uvs)
    sx, cxx, cxy = _similarity(xys)
    uvs_n = [((u - cux) * su, (v - cuy) * su) for u, v in uvs]
    xys_n = [((x - cxx) * sx, (y - cxy) * sx) for x, y in xys]
    a: list[list[float]] = []
    b: list[float] = []
    for (u, v), (x, y) in zip(uvs_n, xys_n):
        a.append([u, v, 1.0, 0.0, 0.0, 0.0, -x * u, -x * v])
        b.append(x)
        a.append([0.0, 0.0, 0.0, u, v, 1.0, -y * u, -y * v])
        b.append(y)
    hn = solve(a, b)
    h_n = [
        [hn[0], hn[1], hn[2]],
        [hn[3], hn[4], hn[5]],
        [hn[6], hn[7], 1.0],
    ]
    return _mul(_t_inv(sx, cxx, cxy), _mul(h_n, _t_mat(su, cux, cuy)))


def jitter(uv: tuple[float, float], delta: float, rng: random.Random) -> tuple[float, float]:
    # Per-axis σ = δ ⇒ error along a segment is δ per tap, √2·δ for two
    # endpoints. Same 1-D convention TICK-041 used for "δ px".
    return (uv[0] + rng.gauss(0.0, delta), uv[1] + rng.gauss(0.0, delta))


def spans_centered(d_mm: float, deg: float) -> tuple[float, float, float]:
    """Pitch/yaw check on a vertical segment through the optical axis."""
    pivot = (0.0, 0.0, d_mm)
    th = math.radians(deg)
    rise_p = pix_len(pivot, off_xy(*CENTERED_RISE[0]), off_xy(*CENTERED_RISE[1]), rot_x, th)
    rise_y = pix_len(pivot, off_xy(*CENTERED_RISE[0]), off_xy(*CENTERED_RISE[1]), rot_y, th)
    card_p = pix_len(pivot, off_xy(*CARD_XY[0]), off_xy(*CARD_XY[1]), rot_x, th)
    return rise_p, rise_y, card_p


def rise_span_pitch(d_mm: float, deg: float) -> float:
    pivot = (0.0, 0.0, d_mm)
    th = math.radians(deg)
    return pix_len(pivot, off_xy(*RISE_XY[0]), off_xy(*RISE_XY[1]), rot_x, th)


def jacobian_sigma_in(delta_px: float, d_mm: float, deg: float) -> float:
    rise_px = rise_span_pitch(d_mm, deg)
    return math.sqrt(2.0) * delta_px * (RISE_MM / rise_px) / MM_PER_IN


def homography_mc(delta_px: float, d_mm: float, deg: float,
                  n: int = MC_N, seed: int = MC_SEED) -> tuple[float, int]:
    """RMS rise error (inches) from noisy 4-corner H + noisy taps. Returns (σ, n_kept)."""
    pivot = (0.0, 0.0, d_mm)
    th = math.radians(deg)
    rng = random.Random(seed)
    true_c = [project(world(pivot, off_xy(x, y), rot_x, th)) for x, y in CARD_XY]
    true_t = [project(world(pivot, off_xy(x, y), rot_x, th)) for x, y in RISE_XY]
    samples: list[float] = []
    for _ in range(n):
        try:
            h = homography(
                [jitter(uv, delta_px, rng) for uv in true_c],
                CARD_XY,
            )
            p0 = _apply3(h, *jitter(true_t[0], delta_px, rng))
            p1 = _apply3(h, *jitter(true_t[1], delta_px, rng))
        except (ZeroDivisionError, ValueError):
            continue
        length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        if 1.0 < length < 80.0:
            samples.append(length)
    if len(samples) < n // 2:
        raise RuntimeError(f"homography MC discarded too many samples at {deg}° {d_mm} mm")
    mean = sum(samples) / len(samples)
    var = sum((s - mean) ** 2 for s in samples) / len(samples)
    return math.sqrt(var) / MM_PER_IN, len(samples)


def main() -> None:
    print("== centered vertical rise, pixel span at 2 m ==")
    print(f"{'deg':>5} {'rise pitch':>12} {'f R cos/d':>12} {'rise yaw':>10} "
          f"{'f R/d':>10} {'card long':>12}")
    for deg in ANGLES_DEG:
        rp, ry, cp = spans_centered(2000.0, deg)
        th = math.radians(deg)
        print(f"{deg:>5} {rp:12.4f} {F_PX * RISE_MM * math.cos(th) / 2000.0:12.4f} "
              f"{ry:10.4f} {F_PX * RISE_MM / 2000.0:10.4f} {cp:12.4f}")

    print("\n== Jacobian (two rise taps) vs four-corner H Monte Carlo, δ = 5 px ==")
    print(f"{'deg':>5} {'2m jac':>8} {'2m H':>8} {'2m pub':>8} {'Δ%':>7} "
          f"{'3m jac':>8} {'3m H':>8} {'3m pub':>8} {'Δ%':>7} {'kept':>8}")
    max_d = 0.0
    for deg in ANGLES_DEG:
        bits = [f"{deg:5d}"]
        kept_note = []
        for label in ("2 m", "3 m"):
            d_mm = DIST_MM[label]
            jac = jacobian_sigma_in(DELTA_PX, d_mm, deg)
            mc, kept = homography_mc(DELTA_PX, d_mm, deg)
            pub = PUBLISHED[deg][label]
            pct = abs(mc - pub) / pub * 100.0
            max_d = max(max_d, pct)
            bits.extend([f"{jac:8.3f}", f"{mc:8.3f}", f"{pub:8.3f}", f"{pct:6.2f}"])
            kept_note.append(str(kept))
        bits.append(" / ".join(kept_note))
        print(" ".join(bits))
    print(f"max |H-MC − published| = {max_d:.2f}%")

    rp0 = rise_span_pitch(2000.0, 0)
    delta_bar = (BAR_IN * MM_PER_IN / RISE_MM) * rp0 / math.sqrt(2.0)
    print(f"\nδ to hit 0.25 in at 2 m, 0° (Jacobian): {delta_bar:.2f} px")
    d_max_m = BAR_IN / jacobian_sigma_in(DELTA_PX, 1000.0, 0)
    print(f"max d at δ=5 px, 0° (Jacobian): {d_max_m:.2f} m")
    for d_mm, name in ((2500.0, "2.5 m"), (3000.0, "3.0 m")):
        mc, _ = homography_mc(DELTA_PX, d_mm, 0)
        print(f"H-MC at {name}, 0°, δ=5: {mc:.3f} in")

    print("\n== H-MC relative to tap-only Jacobian (extra is four-corner scale) ==")
    for deg in (0, 45):
        for label, d_mm in DIST_MM.items():
            jac = jacobian_sigma_in(DELTA_PX, d_mm, deg)
            mc, _ = homography_mc(DELTA_PX, d_mm, deg)
            print(f"  {deg:2d}° {label}: jac={jac:.4f}  H={mc:.4f}  "
                  f"extra={(mc / jac - 1.0) * 100:.1f}%")


if __name__ == "__main__":
    main()
