# Findings

TICK-101 (#71). Written findings and error budget — PRD §8 deliverables #3 and #6.

Every number in this document names a committed artifact. Nothing is typed from
memory. The screening study's sealed-split result does not exist yet: TICK-080
(#63) is the single unsealing run, and it is still waiting on operator labels
(#302). That number is not filled in here.

The notebook that will present a labelled harness report, once one exists, is
documented in [error-analysis.md](error-analysis.md). It accepts only the `dev`
split. The predicted rise-error figure it already draws is the table below.

## 1. The pre-registered hypothesis went untested

PRD §2 pre-registered MAE ≤ 0.25″ on threshold rise, against caliper ground
truth, on the sealed test split, judged on Arm A.

That hypothesis went **untested**. It is not relaxed, not re-scoped, and not
re-judged against another arm (A-3, D-036). There is no caliper, so the metric
has no measurable subject in this window. Reaching for a number from a
different arm, or from too few sealed entrances, is the failure D-007 exists to
prevent.

The surviving metrology finding is the predicted rise-error-versus-angle budget
derived before any data existed (TICK-041, independently checked by TICK-234
and TICK-244). It is reported in §5 and labelled
**predicted before data; not an observed result**.

## 2. Amendments, reported as amendments

PRD §2's own rule: nothing in that section changes after 2026-08-28;
amendments are logged in `CHANGES.log` with a reason and reported as
amendments at Demo Day. Three exist.

**Amendment A-1 (2026-08-29) — stratification analysis plan.** The five
stratification variables (capture angle, distance, lighting, surface,
occlusion) did not change. What changed is which of them the sealed run tests
confirmatorily: **capture angle** is pre-registered as a continuous
error-versus-angle model on the sealed split; the remaining four are reported
from the dev split and labelled **exploratory**. Reason: 12–18 sealed
entrances cannot support a five-way contingency table. Committed before first
capture and before any image was processed. Reported as an amendment at Demo
Day. Full entry: `CHANGES.log`, PRD §2.

**Amendment A-2 (2026-08-29) — the success criterion names its arm.** "MAE ≤
0.25″ on the sealed test split" did not say which of four arms it judged. It
is fixed to **Arm A** (D-022). Arm A', Arm B and Arm C are reported without a
pass/fail bar. Reason: an unnamed arm lets the hypothesis be scored against
whichever arm looks best once results are seen. Committed 2026-08-29, before
first capture and before any image was processed. Reported as an amendment at
Demo Day. Original wording recovered from commit 13e735a (#132).

**Amendment A-3 (2026-09-02) — one product, on iPhone Pro with LiDAR.** The
plain-photo screening study is the product; the metrology arms are a later
version. Consequence for §1: the primary hypothesis is untested in this
window. D-040 (2026-09-04) then narrowed current hardware to James's iPhone 17
Pro (`iPhone18,1`) alone. Reported as an amendment at Demo Day.

## 3. Screening result — confirmatory numbers wait on #63

The sealed run reports, from the sealed split: per-criterion accuracy against
operator presence labels, the **not visible** rate, and the entrance-level
call. Until `reports/sealed/screening_eval.json` exists, those figures are
absent on purpose.

Error is attributed **by condition**, not aggregated into a single headline
number:

- **Capture angle** was the confirmatory stratification (A-1 / D-019) for the
  *rise-error* model. The empirical fit is TICK-075. It did not run: there is
  no caliper (D-036). The predicted curve in §5 is what that run would have
  been compared against.
- **Distance, lighting, surface, occlusion** are labelled **exploratory**.
  They will come from a `dev` harness report presented by the TICK-100
  notebook, with independent-entrance sample sizes, once labels exist. They
  are descriptive associations, not causal.

No 12-entrance pilot accuracy is restated here. That figure lived in a module
docstring, was not a sealed run, and quoting it as a finding would be peeking
in all but name.

## 4. Arms without a pass/fail bar (D-022)

The 0.25″ bar applies to **Arm A only**. Other arms are reported without a
pass/fail bar:

| Arm | This window |
|---|---|
| A | Predicted budget only (§5). No caliper MAE. |
| A' | Later-version. No measured MAE. No pass/fail bar. |
| B | Later-version. No measured MAE. No pass/fail bar. |
| C | Cut by D-030 with no measured error. No pass/fail bar. |

There is no four-arm ablation chart this window (#72 is `later-version`).

## 5. Predicted rise-error budget

Source: `docs/rise-error-budget.json`. Status:
**predicted before data; not an observed result**. Tap error δ = 5 px.
Regenerated as
`predicted_rise_error_vs_angle.svg` by the TICK-100 notebook.

Use the **3D check** series for any requirement. It uses `fx = 2807.7` px
measured on James's iPhone 17 Pro. The analytical series used the superseded
ARCHITECTURE example `f = 2934.1` px and is kept so the arithmetic stays
checkable, not so it can be cited as the phone's budget.

Predicted absolute error on a 0.5″ rise, in inches:

| Series | f (px) | 0° | 15° | 30° | 45° |
|---|---|---|---|---|---|
| 3D check, 2 m | 2807.7 measured | 0.202 | 0.209 | 0.230 | 0.274 |
| 3D check, 3 m | 2807.7 measured | 0.303 | 0.312 | 0.344 | 0.415 |
| Analytical, 2 m | 2934.1 superseded | 0.192 | 0.199 | 0.222 | 0.271 |
| Analytical, 3 m | 2934.1 superseded | 0.288 | 0.298 | 0.332 | 0.407 |

At δ = 5 px on the measured series, predicted error at 3 m is 0.303″ head-on —
already above 0.25″. At 2 m it is 0.202″ head-on and 0.230″ at 30°, and 0.274″
at 45°. That is a prediction compared to 0.25″ so the capture protocol has a
bound; it is not the pre-registered hypothesis being scored. The JSON has no
2.5 m row. F-004's **2.5 m** cap is from the analytical series (superseded
`f`); the measured series is only known to sit under 0.25″ at 2 m through 30°
and over it at 3 m head-on. Tap precision dominates angle: doubling δ doubles
the error; obliquity contributes only `1/cos θ`.

These numbers characterise Arm A with a vertical card against the riser. They
are not a screening result and they are not an observed MAE.

## 6. Failure classes

Documented, not solved:

- **Glass-door entrances.** Reflections and through-glass figures are a
  privacy and a visibility problem. The protocol is blur-first; a glass door
  is still a documented failure class for a presence call about the entrance
  itself (PRD §3).
- **Heavily bevelled or rounded thresholds.** Arm A assumes a usable planar
  riser face (ARCHITECTURE A-4). There is no caliper in this window, so this
  class is recorded rather than measured.
- **Occlusion in the ROI.** Mats, sandwich boards, parked vehicles: tagged as
  a condition (R-6) and expected in the error budget as a named failure mode.
  Heavy occlusion of the feature's relevant area makes the honest screening
  answer **not visible**, never **absent**.

Pilot finding carried into the protocol: if no view covers the ground at the
threshold, ramp/bevel and handrail calls come back not visible or flip across
views. That is framing, not the entrance.

## 7. Limitations

All evidence in this document comes from **James's iPhone 17 Pro
(`iPhone18,1`)** with LiDAR hardware (D-040). No other handset is a capture
device, test device, or part of the supported pool. **No cross-device
generalisation is claimed.** D-040's alias rule (`iPhone 17 Pro` and
`iPhone18,1` name the same phone) is a reporting normalisation, not a second
device.

Captured depth on this phone is relative stereo disparity persisted as
`DepthFloat32`, not LiDAR range (D-045). Screening does not consume device
depth (D-015). The planned monocular-versus-LiDAR comparison has no metric
reference under D-036 and is not delivered.

The sealed split remains unopened. Anything noticed in it after #63 is
exploratory, never confirmatory.

## 8. Sources

| Claim | Artifact |
|---|---|
| Predicted inches in §5 | `docs/rise-error-budget.json` |
| Derivation and crossing-angle table | `docs/rise-error-vs-angle.md` (TICK-041) |
| Independent 3D check | `docs/rise-error-vs-angle-independent.md` (TICK-244) |
| Amendments A-1, A-2, A-3 | `PRD.md` §2, `CHANGES.log` |
| Sealed screening numbers | `reports/sealed/screening_eval.json` — not yet written (#63) |
| Exploratory condition figures | TICK-100 notebook, from a `dev` harness report, after labels |
