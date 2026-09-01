# Predicted rise error versus capture angle — Arm A

**TICK-041 (#35).** A prediction made *before* the dataset exists, so the capture protocol can be
sanity-checked before forty entrances are collected under it. The empirical curve is TICK-075 on
the sealed split; a large disagreement between the two means one of them is wrong and must be
resolved before the sealed run.

Independently re-derived in TICK-234 (#138) — `docs/rise-error-vs-angle-independent.md`. The two
tables agree to <1%; F-001 through F-005 survived.

## 1. Setup

Arm A places the reference card **vertically against the riser face**, so scale and measurement
share one surface. A homography built from the card's four known corners already absorbs the
projection, and any length inside that plane is metric (D-012, ARCHITECTURE §5). In the noiseless
case this is exact at **any** capture angle — obliquity introduces no bias. What obliquity does is
amplify noise, and that is what this budget estimates.

| Symbol | Meaning | Value used |
|---|---|---|
| `f` | focal length, pixels | **2934.1** — ARCHITECTURE §4 example intrinsics, 4032×3024 |
| `W` | card long edge | **85.60 mm** — ISO/IEC 7810 ID-1 (D-006) |
| `R` | threshold rise being measured | **12.7 mm** (0.5″, the ADA line) |
| `d` | camera-to-threshold distance | 2 m, 3 m |
| `θ` | obliquity, optical axis to plane normal | 0°, 15°, 30°, 45° |
| `δ` | **per-tap localisation error, pixels** | the dominant unknown — see §4 |

Metric scale at the plane is `d/f` mm per pixel. At 2.5 m that puts the card across
**100.5 px**, which reproduces R-3's own "roughly 100 px at 2-3 m" — the model agrees with the
project's existing arithmetic before it is used to argue against it.

## 2. The two error terms

**Rise endpoints.** The operator taps the top and bottom of the rise. Two independent taps at δ
pixels each give `√2·δ` pixels of error along the rise, worth `√2·δ·(d/f)` mm.

**Card-derived scale.** The card's known width is measured across `W·f/(d)` pixels, each corner
localised to δ. The relative scale error is `√2·δ/(W·f/d)`, and it propagates to the rise in
proportion to `R`.

Their ratio is the useful part:

```
scale term / tap term  =  R / W  =  12.7 / 85.60  =  0.148
```

**Independent of both angle and distance.** The card-derived scale contributes a fixed ~15% on top
of the tap error, and never more. The card's pixel span is *not* the binding constraint, because
the rise being measured is small compared to the card that scales it.

## 3. Obliquity

Foreshortening compresses the rise into fewer pixels by `cos θ`, so a fixed tap error in pixels
buys a larger error in millimetres:

```
σ_R  =  K · δ · (d/f) / cos θ        K = √2·√(1 + (R/W)²) = 1.430
```

**Obliquity enters as 1/cos θ and nothing worse** — a 15% penalty at 30°, 41% at 45°.

> **Caveat that matters for TICK-075.** The `1/cos θ` factor applies only to obliquity that
> foreshortens the *rise* direction — the camera above the threshold, looking down. Standing to
> one side rotates about the vertical axis and does **not** foreshorten a vertical rise. So error
> depends on the *direction* of obliquity, not only its magnitude, and a scalar angle cannot
> separate the two. The pre-registered model (D-019) fits against a scalar; expect unexplained
> scatter from this, and prefer the signed elevation component if the recovered pose can supply it.

## 4. What is δ, really?

This is the term everything turns on, so it is worth stating honestly rather than assuming.

On an iPhone 16, a 4032-px-wide still displayed full width across 1179 screen pixels is **3.4 image
pixels per screen pixel**, at 460 ppi:

| Tapping method | Image pixels |
|---|---|
| Unaided fingertip (~2 mm targeting error) | **≈ 124 px** |
| Careful tap with a 4× loupe (~0.5 mm) | **≈ 31 px** |
| Crosshair with fine adjustment at ~1:1 (~0.15 mm) | **≈ 9 px** |

## 5. Predicted rise error (inches)

`*` marks values over the 0.25″ success bar.

| δ | angle | 2 m | 3 m |
|---|---|---|---|
| **5 px** | 0° | 0.192 | 0.288 `*` |
| | 15° | 0.199 | 0.298 `*` |
| | 30° | 0.222 | 0.332 `*` |
| | 45° | 0.271 `*` | 0.407 `*` |
| **10 px** | 0° | 0.384 `*` | 0.576 `*` |
| | 30° | 0.443 `*` | 0.665 `*` |
| **20 px** | 0° | 0.767 `*` | 1.151 `*` |

## 6. The answers this ticket asks for

**Angle beyond which predicted error exceeds 0.25″** — it depends far more on δ and `d` than on θ:

| δ | 1.5 m | 2 m | 2.5 m | 3 m |
|---|---|---|---|---|
| 3 px | 70° | 63° | 55° | 46° |
| 5 px | 55° | **40°** | 16° | over the bar head-on |
| 10 px | over the bar head-on | over | over | over |

**Maximum distance to stay under the bar:**

| δ | 0° | 30° | 45° |
|---|---|---|---|
| 3 px | 4.34 m | 3.76 m | 3.07 m |
| 5 px | **2.61 m** | 2.26 m | 1.84 m |
| 10 px | 1.30 m | 1.13 m | 0.92 m |

**Required tap precision**, which is the real finding:

| | 0° | 30° |
|---|---|---|
| at 2.0 m | δ ≤ 6.5 px | δ ≤ 5.6 px |
| at 2.5 m | δ ≤ 5.2 px | δ ≤ 4.5 px |
| at 3.0 m | δ ≤ 4.3 px | δ ≤ 3.8 px |

**R-3 is refuted.** R-3 claims that at 2-3 m "scale is well conditioned and obliquity dominates the
budget instead". The first half is right and the second is not. The card-derived scale term is a
fixed 15% of the tap term at every angle and distance, so scale conditioning is indeed a non-issue.
But obliquity contributes only `1/cos θ`, while **tap precision and distance enter linearly and
dominate completely**. At 45° the obliquity penalty is 41%; going from 5 px to 10 px taps is 100%,
and going from 2 m to 3 m is 50%.

**The 3 m distance cap does not survive.** At a realistic δ = 5 px, 3 m exceeds the bar *head-on*.
The cap that matches the bar is **2.5 m**, and only with tap precision the app does not yet provide.

## 7. Assumptions and exclusions

Stated so the disagreement with TICK-075, if any, has somewhere to land.

- The rise lies in the card's plane and adjacent to it. Homography error grows with distance from
  the control points; a card placed far along the threshold from the measured rise is not covered.
- Tap errors are independent, zero-mean and isotropic. Systematic bias — consistently tapping the
  shadow line rather than the edge — is not modelled and would not shrink with more taps.
- Lens distortion is corrected (TICK-042, #36). Residual distortion adds to δ.
- Excludes motion blur, rolling shutter, card non-planarity, and card placement not flush to the
  riser.
- `f` is the ARCHITECTURE §4 example value. Every number scales linearly with `f`; per-device
  intrinsics should be substituted once TICK-022 (#26) records them.

## 8. Consequences

1. **The ROI tap UI must provide pixel-level magnification.** At an unaided ~124 px, Arm A misses
   the bar by a factor of twenty at any distance. This is a UI requirement, not an operator-skill
   requirement, and it lands on TICK-026 (#30), which has not started. Filed as TICK-232 (#135).
2. **Revise the distance cap from 3 m to 2.5 m** in the capture protocol (TICK-090, #64) — filed as TICK-233 (#136) — and
   record distance per capture as a first-class condition variable — it matters more than angle.
3. **Angle guidance can be looser than assumed.** With δ and `d` controlled, the bar is not crossed
   until 40-63°. Deliberately varying angle across entrances remains right for the curve; treating
   obliquity as the main threat to accuracy is not.
