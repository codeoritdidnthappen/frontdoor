# Arm A rise error from 3D projection

**TICK-244 (#159), succeeding TICK-234 (#138).** This note does not use the tap/scale
quadrature or the closed form `K = √2·√(1+(R/W)²)` in `docs/rise-error-vs-angle.md`. It
projects the riser as a 3D plane, reads millimetre error off the image-span Jacobian, and
checks that against a four-corner homography Monte Carlo — the instrument Arm A actually
uses (D-012, ARCHITECTURE §5). The published table is a comparison target at the end.

Re-run: `python docs/rise-error-vs-angle-independent.py` (stdlib). Seed 244, 4000 draws.

## 1. What is being projected

Camera at the origin, looking down +Z. The riser is a plane whose nearest point on the
optical axis sits at distance `d`. Constants from ARCHITECTURE §4 and D-006, not from the
first write-up:

- example focal length `f = 2934.1` px (4032×3024 still)
- ID-1 card `85.60 × 53.98` mm
- ADA rise `R = 12.7` mm
- tap error `δ = 5` px per image coordinate, two endpoints, so length noise `√2 · δ` px
  along the segment — TICK-041's 1-D convention, stated so the comparison is fair

A homography from the card's four corners makes in-plane lengths metric. In the noiseless
case that is exact at any pose. The budget is what tap noise does.

Obliquity is a rotation of the *plane's local axes about that fixed pivot*, not a rotation
of the whole scene about the camera. Pitch is rotation about camera X (parallel to the
threshold). Yaw is rotation about camera Y (parallel to a vertical rise).

## 2. Pixel occupancy, no error formula yet

A vertical segment of length `R` on the optical axis, at `d = 2` m:

| deg | rise, pitch (px) | `f R cosθ / d` | rise, yaw (px) | `f R / d` | card long edge, pitch (px) |
|---|---|---|---|---|---|
| 0 | 18.63 | 18.63 | 18.63 | 18.63 | 125.58 |
| 15 | 17.97 | 18.00 | 18.63 | 18.63 | 125.58 |
| 30 | 16.08 | 16.14 | 18.63 | 18.63 | 125.58 |
| 45 | 13.12 | 13.17 | 18.63 | 18.63 | 125.58 |

Pitch shortens the rise. The residual against `f R cosθ / d` is the second-order `R/d`
term (`12.7 / 2000 = 0.6%` at 45°). Yaw leaves the on-axis rise at `f R / d` exactly:
the segment is parallel to the rotation axis, so its image length at the centre does not
pick up `cos φ`. The card's long edge, along the threshold, is unchanged by pitch for the
same reason.

A scalar sidecar angle that mixes the two rotations will not match this occupancy. That
is a geometric fact about which 3D vector is parallel to which axis; it is not a factor
applied after the fact.

## 3. Jacobian from occupancy

Let `n(θ)` be the projected length of the rise in pixels. Then millimetres per pixel on
that segment is `R / n(θ)`, and two taps of size `δ` along it give

```
σ = √2 · δ · R / n(θ)     millimetres
```

At pitch, `n(θ) ≈ f R cosθ / d`, so this is linear in `δ` and in `d`, and grows as the
rise occupies fewer pixels. Convert with 25.4 mm/in. No combined `K`, no `R/W` term yet —
this is endpoint noise only.

At `δ = 5` px:

| angle | 2 m | 3 m |
|---|---|---|
| 0° | 0.190 | 0.285 |
| 15° | 0.197 | 0.295 |
| 30° | 0.220 | 0.329 |
| 45° | 0.269 | 0.404 |

`*` against the 0.25″ bar: 3 m is over head-on; 2 m is over only at 45°.

## 4. Four corners, which is what Arm A fits

Arm A does not measure the card with two points on the long edge. It fits a homography
from four known ID-1 corners, then maps the rise taps through it. That scale noise is a
different object than `R/W`.

The script perturbs all four corners and both rise taps (`δ` per axis), Hartley-normalizes
the DLT, and reports the RMS of reconstructed rise over 4000 draws. Samples that explode
(`< 1` mm or `> 80` mm) are dropped; more than 99.5% of draws survive at every cell below.

| angle | 2 m, taps | 2 m, H | 3 m, taps | 3 m, H |
|---|---|---|---|---|
| 0° | 0.190 | 0.194 | 0.285 | 0.289 |
| 15° | 0.197 | 0.200 | 0.295 | 0.298 |
| 30° | 0.220 | 0.220 | 0.329 | 0.327 |
| 45° | 0.269 | 0.264 | 0.404 | 0.395 |

Fitting `H` adds about two percent on the total at head-on, and does not dominate at 45°.
The two-point `R/W ≈ 15%` story overstates how much scale matters once four corners fix
the rectangle; it does not change which term is binding. Tap precision and distance still
run the budget.

## 5. Comparison with the published table

Published values from `docs/rise-error-vs-angle.md` §5, `δ = 5` px. The column "here" is
the four-corner Monte Carlo.

| angle | 2 m here | 2 m published | Δ | 3 m here | 3 m published | Δ |
|---|---|---|---|---|---|---|
| 0° | 0.194 | 0.192 | 1.0% | 0.289 | 0.288 | 0.3% |
| 15° | 0.200 | 0.199 | 0.5% | 0.298 | 0.298 | 0.2% |
| 30° | 0.220 | 0.222 | 0.8% | 0.327 | 0.332 | 1.6% |
| 45° | 0.264 | 0.271 | 2.8% | 0.395 | 0.407 | 3.0% |

Largest gap 3.0%, under TICK-234's 10% halt. The tap-only Jacobian is already within 1% of
the published table; four corners move the numbers by about the same amount as rounding.

## 6. What this does to #135 and #136

**#135.** Invert the Jacobian at 2 m, 0°: `δ ≤ 6.59` px hits 0.25″ on taps alone. With the
homography Monte Carlo at `δ = 5` px (`σ = 0.194″`), the same bar is `δ ≤ 6.44` px. Both
round to the ticket's **6.5 px**. Not updated.

**#136.** Jacobian max `d` at `δ = 5` px, 0° is **2.63 m**. Homography Monte Carlo: 2.5 m
is 0.241″ (under), 3 m is 0.289″ (over). The 2.5 m cap holds. Not updated.

Pitch at 45° is +41% on occupancy (`1 / 0.707`). Doubling `δ` or stretching `d` from 2 m
to 3 m is 50–100%. Distance and tap size still dwarf angle.

## 7. What this does not cover

Same list a fight with TICK-075 would have to land on:

- Rise far from the card along the threshold (homography error grows off the control
  points; this Monte Carlo puts the rise on the card's right edge).
- Systematic tap bias. It does not average down.
- Residual distortion after TICK-042, motion blur, a card that is not flat or not flush.
- `f` is the architecture example. Per-device intrinsics scale every number linearly.

`R = 12.7` mm is the ADA line, not a typical door. Endpoint noise in millimetres scales
with `R / n(θ)` and `n(θ)` scales with `R`, so the tap term in millimetres is independent
of `R`; only how much of the card you are using as a ruler would change.
