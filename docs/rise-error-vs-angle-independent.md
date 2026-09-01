# Independent re-derivation of Arm A's rise-error budget

**TICK-234 (#138).** Second derivation, started from D-012 and ARCHITECTURE §4–§5. The algebra in
`docs/rise-error-vs-angle.md` was not used as a starting point; the published table is a comparison
target at the end, not an input.

The empirical curve remains TICK-075, on the sealed split. This note only checks whether the
predicted numbers that #135 and #136 are about to ship against were derived correctly.

## 1. Geometry, not the first derivation

Arm A puts the reference card **vertically against the riser** (D-012). A homography from the
card's four known corners makes every length in that plane metric. In the noiseless case the
measurement is exact at any capture angle; the budget is what happens to tap noise.

Taken from the architecture, not from the first write-up:

| Symbol | Meaning | Value |
|---|---|---|
| `f` | focal length, pixels | 2934.1 — ARCHITECTURE §4 example, 4032×3024 |
| `W` | card long edge | 85.60 mm — ISO/IEC 7810 ID-1 |
| `R` | rise under test | 12.7 mm (0.5″, the ADA line) |
| `d` | camera-to-threshold distance | 2 m and 3 m |
| `θ` | obliquity that foreshortens the *rise* | 0°, 15°, 30°, 45° — see §4 |
| `δ` | per-tap localisation error, pixels | 5 px for the comparison table |

Pinhole scale on a fronto-parallel plane is `d/f` millimetres per pixel. Arm A does not use `d` or
`f` to *measure* — the card supplies scale — but the first-order map from an image-plane tap error
onto the riser is the same Jacobian.

## 2. Two noises on one length

The operator taps the top and bottom of the rise, and the four card corners that fix the
homography. Treat tap errors as independent, zero-mean, isotropic, of size `δ` pixels.

**Endpoints of the rise.** Two taps. Error along the connecting direction is `√2 · δ` pixels.
On a fronto-parallel plane that is

```
σ_tap  =  √2 · δ · (d/f)     millimetres
```

**Scale from the card.** Measuring the known long edge across `n = W · f / d` pixels, with the
same two-point localisation, the relative scale error is `√2 · δ / n`. It lands on the rise in
proportion to `R`:

```
σ_scale  =  R · √2 · δ · (d/f) / W     millimetres
```

The ratio of the two terms does not contain `d`, `f`, `δ`, or `θ`:

```
σ_scale / σ_tap  =  R / W  =  12.7 / 85.60  =  0.148
```

So the card-derived scale is a **fixed ~15%** of the tap term. That claim holds. It is a
consequence of measuring a 12.7 mm rise against an 85.60 mm ruler that lives on the same plane,
not of a particular capture distance or angle. (A 1″ rise would double the fraction to ~30% and
still not dominate.)

Combining independent terms in quadrature:

```
σ  =  √(σ_tap² + σ_scale²)
   =  √2 · √(1 + (R/W)²) · δ · (d/f)
   =  K · δ · (d/f)                      K = 1.430
```

Using four card corners rather than two points on the long edge would only shrink the already-small
scale term. It cannot change which source dominates.

## 3. What obliquity actually does

A small segment of physical length `L` in the plane, lying in the direction of the camera's tilt,
images to `L · (f/d) · cos θ` pixels. A fixed tap error in pixels is then a larger millimetre
error by `1/cos θ`.

That foreshortening applies to a **vertical rise** only when the camera pitches — standing above
the threshold, looking down. Standing to the side is a yaw about the vertical. A vertical rise is
parallel to that axis, so its image length near the centre of the frame is not compressed by
`cos φ`. Error therefore depends on the *direction* of obliquity, not only on a scalar angle.
D-019's single angle cannot separate the two.

`θ` in this budget is the pitch that foreshortens the rise. A scalar sidecar angle that mixes
pitch and yaw will not match this factor.

Does `1/cos θ` also stretch the scale term? If the card's long edge is horizontal along the
threshold, pitch compresses the rise and not the ruler. The tighter combination is then

```
σ  =  √2 · δ · (d/f) · √(sec²θ + (R/W)²)
```

rather than multiplying the already-combined `K` by `1/cos θ`. At 45° the two forms differ by
half a percent (see §5). Applying `1/cos θ` to the combined σ is a simplification, not a
geometric error, and it does not move any protocol number.

Obliquity enters as `1/cos θ` on the rise, and nothing steeper. +3.5% at 15°, +15% at 30°,
+41% at 45°. Linear in `δ` and in `d`, which is why those two dominate the budget.

## 4. Predicted rise error at δ = 5 px

Convert millimetres to inches with 25.4. `*` marks values over the 0.25″ bar.

| angle | 2 m | 3 m |
|---|---|---|
| 0° | 0.192 | 0.288 `*` |
| 15° | 0.199 | 0.298 `*` |
| 30° | 0.222 | 0.332 `*` |
| 45° | 0.271 `*` | 0.407 `*` |

The same formula, solved for the other variables the protocol cares about:

| | 0° | 30° |
|---|---|---|
| `δ` to hit 0.25″ at 2.0 m | ≤ 6.5 px | ≤ 5.6 px |
| `δ` to hit 0.25″ at 3.0 m | ≤ 4.3 px | ≤ 3.8 px |
| max `d` at δ = 5 px | 2.61 m | 2.26 m |

At δ = 5 px, 2.5 m head-on is 0.240″ — under the bar. 3 m head-on is 0.288″ — over.

## 5. Comparison with the published table

Published values from `docs/rise-error-vs-angle.md` §5, δ = 5 px. This derivation used
`K = √2 · √(1+(R/W)²)` applied as `K · δ · (d/f) / cos θ`.

| angle | 2 m here | 2 m published | Δ | 3 m here | 3 m published | Δ |
|---|---|---|---|---|---|---|
| 0° | 0.192 | 0.192 | <1% | 0.288 | 0.288 | <1% |
| 15° | 0.199 | 0.199 | <1% | 0.298 | 0.298 | <1% |
| 30° | 0.222 | 0.222 | <1% | 0.332 | 0.332 | <1% |
| 45° | 0.271 | 0.271 | <1% | 0.407 | 0.407 | <1% |

The pitch-only-on-the-tap form in §3 is 0.270″ / 0.405″ at 45° instead of 0.271″ / 0.407″. Still
well under the 10% disagreement that would halt #136.

**Agreement.** No value differs by more than one percent, which is rounding. The 15% scale-term
claim holds. `1/cos θ` holds for rise-foreshortening pitch and does not hold for side yaw.

## 6. What this does to #135 and #136

**#135 (δ ≤ 6.5 px at 2 m).** Confirmed. Independently: 6.35 mm / `(K · 2000 / 2934.1)` = 6.52 px.
The ticket also leans on an unaided fingertip being ~124 image pixels. That is a separate
arithmetic check, not this budget: 4032-wide still on an iPhone 16 display 1179 px across is 3.4
image pixels per screen pixel; 2 mm of targeting error at 460 ppi is ~36 screen pixels, ~124
image pixels. The magnification requirement stands. The ticket is not updated.

**#136 (2.5 m cap).** Confirmed. At δ = 5 px the head-on ceiling is 2.61 m; 3 m is over the bar
before any angle is applied. 2.5 m is the round protocol number under that ceiling. The ticket
is not updated.

Tap precision and distance dominate; angle does not. R-3's claim that "obliquity dominates the
budget" at 2–3 m is still the wrong half of that sentence.

## 7. What this budget does not cover

Same exclusions a disagreement with TICK-075 would have to land on:

- Rise not in the card's plane, or far from the control points along the threshold.
- Systematic tap bias (always the shadow line). That does not average down.
- Residual lens distortion after TICK-042.
- Motion blur, rolling shutter, a card that is not flat or not flush.
- `f` is the architecture example. Per-device intrinsics (TICK-022) scale every number linearly.

`R = 12.7 mm` is a modelling choice: the ADA line, not a typical door. The tap term does not
depend on `R`; only the 15% scale fraction does.
