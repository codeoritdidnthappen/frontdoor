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

- James's iPhone 17 Pro focal length `f = 2807.7` px (4032×3024 still)
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
| 0 | 17.83 | 17.83 | 17.83 | 17.83 | 120.17 |
| 15 | 17.19 | 17.22 | 17.83 | 17.83 | 120.17 |
| 30 | 15.39 | 15.44 | 17.83 | 17.83 | 120.17 |
| 45 | 12.55 | 12.61 | 17.83 | 17.83 | 120.17 |

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
| 0° | 0.198 | 0.297 |
| 15° | 0.206 | 0.308 |
| 30° | 0.230 | 0.344 |
| 45° | 0.281 | 0.422 |

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
| 0° | 0.198 | 0.202 | 0.297 | 0.303 |
| 15° | 0.206 | 0.209 | 0.308 | 0.312 |
| 30° | 0.230 | 0.230 | 0.344 | 0.344 |
| 45° | 0.281 | 0.274 | 0.422 | 0.415 |

Fitting `H` adds about two percent on the total at head-on, and does not dominate at 45°.
The two-point `R/W ≈ 15%` story overstates how much scale matters once four corners fix
the rectangle; it does not change which term is binding. Tap precision and distance still
run the budget.

## 5. Comparison with the published table

Published values from `docs/rise-error-vs-angle.md` §5, `δ = 5` px. The column "here" is
the four-corner Monte Carlo.

| angle | 2 m here | 2 m published | Δ | 3 m here | 3 m published | Δ |
|---|---|---|---|---|---|---|
| 0° | 0.202 | 0.192 | 5.4% | 0.303 | 0.288 | 5.3% |
| 15° | 0.209 | 0.199 | 5.0% | 0.312 | 0.298 | 4.7% |
| 30° | 0.230 | 0.222 | 3.6% | 0.344 | 0.332 | 3.5% |
| 45° | 0.274 | 0.271 | 1.3% | 0.415 | 0.407 | 2.0% |

Largest gap 5.4%, under TICK-234's 10% halt. Most of the shift is the measured focal length
replacing the original example; the four-corner fit remains a smaller term than tap precision.

## 6. What this does to #135 and #136

**#135.** Invert the Jacobian at 2 m, 0°: `δ ≤ 6.30` px hits 0.25″ on taps alone. With the
homography Monte Carlo at `δ = 5` px (`σ = 0.202″`), the same bar is `δ ≤ 6.18` px. The
ticket's stricter **5 px** target remains within budget at 2 m.

**#136.** Jacobian max `d` at `δ = 5` px, 0° is **2.52 m**. Homography Monte Carlo: 2.5 m
is 0.253″ and 3 m is 0.303″, both over. The 2.5 m cap does not hold at exactly 5 px; capture
must be slightly closer or tap precision must be better than 5 px.

Pitch at 45° is +41% on occupancy (`1 / 0.707`). Doubling `δ` or stretching `d` from 2 m
to 3 m is 50–100%. Distance and tap size still dwarf angle.

## 7. What this does not cover

Same list a fight with TICK-075 would have to land on:

- Rise far from the card along the threshold (homography error grows off the control
  points; this Monte Carlo puts the rise on the card's right edge).
- Systematic tap bias. It does not average down.
- Residual distortion after TICK-042, motion blur, a card that is not flat or not flush.
- `f = 2807.7` is the value measured on James's iPhone 17 Pro. No other phone is in scope.

`R = 12.7` mm is the ADA line, not a typical door. Endpoint noise in millimetres scales
with `R / n(θ)` and `n(θ)` scales with `R`, so the tap term in millimetres is independent
of `R`; only how much of the card you are using as a ruler would change.
