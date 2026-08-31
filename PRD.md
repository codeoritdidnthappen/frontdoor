# PRD — Monocular Measurement of Storefront Accessibility

**Track:** Capstone Track 2 (Technical Challenge)
**Status:** Scope locked 2026-08-28. System design in [`ARCHITECTURE.md`](ARCHITECTURE.md).
Living document — all changes logged in [`CHANGES.log`](CHANGES.log).
**Demo Day:** 2026-09-09 · **Working days remaining at lock:** 12

---

## 1. Summary

Measure ADA-relevant entrance geometry from a single ordinary phone photograph, and publish a
calibrated error budget saying under which capture conditions that measurement can be trusted.

The contribution is the characterized answer, not the app. A result showing that single-image
measurement *cannot* reach the ADA decision line — stated with error attributed to specific
conditions — is a valid and presentable outcome, and the evaluation protocol in §7 is designed
so that outcome remains credible.

## 2. Research question

> How accurately can entrance threshold rise be measured from a single phone photo without a
> depth sensor, and under what capture conditions does that estimate become untrustworthy?

**Pre-registered primary hypothesis (committed 2026-08-28, before data collection):**

- **Primary metric:** mean absolute error on threshold rise, in inches, against caliper ground truth.
- **Success criterion:** MAE ≤ 0.25" on the sealed test split.
- **Primary classification task:** pass/fail against the ADA **1/2"** line (above which a ramp is
  required). Reported as accuracy, plus false-pass rate — a false pass is the harmful error, since
  it tells a wheelchair user a barrier is passable.
- **Secondary classification task:** the 1/4" line, reported but not the bar we are judged against.
- **Stratification variables, fixed in advance:** capture angle, capture distance, lighting,
  surface material, occlusion.

Nothing in this section changes after 2026-08-28. Amendments, if forced, are logged in
`CHANGES.log` with a reason and reported as such at Demo Day.

**Amendment A-1 (2026-08-29) — stratification analysis plan.** The five stratification variables
above are unchanged. What changed is which of them the sealed run tests confirmatorily: **capture
angle** is now pre-registered as a continuous error-versus-angle model evaluated on the sealed
split, and the remaining four are reported from the dev split and labelled exploratory. Reason:
12-18 sealed entrances give a five-way stratification per-cell counts of one or two, which cannot
support confirmatory claims, whereas a curve fitted against a continuously measured angle can.
Capture angle became continuously measurable when capture moved into an instrumented app (D-014).
Committed before first capture and before any image was processed. Reported as an amendment at
Demo Day.

## 3. Scope

**In scope**

- One measurement type — **threshold rise** — characterized completely.
- Single RGB frame, no depth sensor required at inference.
- Opaque-door entrances.
- Four scale-recovery arms compared head to head (§5), spanning an accuracy-versus-usability
  gradient (D-013).
- Explicit abstention when the confidence interval straddles a decision line.

**Out of scope (explicitly not being built)**

- A consumer accessibility map or a replacement for Wheelmap / AccessNow.
- Compliance determinations of legal weight.
- Clear width, ramp slope, step height — stretch goals only, attempted only after threshold rise
  is fully characterized.
- Glass-door entrances — documented as a failure class, not solved.
- Automatic entrance detection (see D-004).

## 4. Locked decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| D-001 | **Single-view metrology is the primary arm.** A learned monocular depth model is retained only as the baseline to beat. | Absolute error of monocular depth nets at 2-3m is measured in inches; the decision line is 1/4". Metrology on a near-planar scene with a known-size reference never estimates absolute depth, so its error at small magnitudes is bounded by feature localization, not by the depth model. |
| D-002 | **40-60 entrances, deeper per entrance** (more angles/distances/lighting each) rather than 100-150 shallow. | Error-stratified-by-condition needs variation *within* an entrance. Breadth leaves per-condition cells with n too small to say anything. |
| D-003 | **Digital caliper / depth gauge (±0.01") is the ground-truth instrument for threshold rise.** Tape measure retained for clear width and ramp run. | Evaluating a 1/4" decision line with a tape read to 1/8" puts instrument uncertainty at half the disputed quantity. First objection any reviewer raises. |
| D-004 | **Human-tap ROI for v1.** The operator taps the threshold edge in the photo; learned segmentation is deferred to stretch. | Fine-tuned segmentation means a second hand-annotation job stacked on tape measurement in the same five days. Detection is not the research question. |
| D-005 | **Native iOS app, thin client.** Swift app captures, uploads, and renders; all metrology runs server-side in Python. | Keeps development in one language and leaves Sep 6-8 free for iteration instead of Core ML conversion. Requires venue connectivity — see R-4. |
| D-006 | **Reference object is a credit card (ISO/IEC 7810 ID-1, 85.60 × 53.98mm).** | Spec-exact dimensions and already in the user's pocket. It is small in frame at 2-3m and will cost precision — but "works with what you already carry" is the usability finding worth having. |
| D-007 | **Pre-registration + sealed test set.** ~30% of entrances randomly sealed at collection time, unopened until results freeze 2026-09-07; run once. | The contribution is an honest error budget. Without this, reported accuracy partly reflects choices fitted to the same images, and the negative-result framing collapses under "how many variants did you try?" |
| D-008 | **Primary success bar is the 1/2" ADA line, MAE ≤ 0.25".** | The consequential line — above it the law requires a ramp. Honestly reachable, and the classification most useful to the end user. |
| D-009 | **Abstention is a first-class output.** Where the interval spans a decision line, the system declines to classify. | A confident wrong answer about passability is worse for the user than no answer. Abstention rate is a reported metric, not a hidden failure. |
| D-010 | **Team of 4**, roles assigned in §9. | Enables field capture, metrology, evaluation, and demo/deck to run in parallel — the only way §9 fits in 12 days. |
| D-012 | **The reference card is placed vertically against the riser face.** Arm A recovers the rise in-plane from a homography built on the card's four corners. | Scale and measurement share one surface, so the homography absorbs the projection: no intrinsics, no pose, no depth. Removes the largest unknown from the primary arm. Supersedes the ground-plane formulation in §5. |
| D-013 | **Three-arm usability gradient.** A (vertical card) is the monocular accuracy ceiling, A′ (card on ground) the realistic-user path, C (no card) the most usable. | Arm A requires physical access to the step — the one thing a wheelchair user at the bottom of it cannot do. Calling A a ceiling rather than the shipping path keeps the claim honest, and D-006's "already in your pocket" rationale moves to Arm C, where it is true. |
| D-014 | **Capture-only app, built before dataset capture**, on AVFoundation + CoreMotion. No ARKit. | Yields true intrinsics, gravity, LiDAR depth and full-resolution stills, and makes capture angle a measured quantity rather than an operator's estimate. ARKit's video frames are too small for an error budget counted in pixels across the rise. Supersedes stock-camera capture. |
| D-015 | **Method boundary: one RGB still + intrinsics + gravity.** No depth map, no motion-derived scale. | Answers "why not just use ARKit?" — visual-inertial odometry recovers metric scale from motion, which would make the question uninteresting. Enforced by construction: no AR session is ever started. |
| D-016 | **Metrology server runs on a cloud VM**, with fallback chain cellular → venue wifi → identical image on a laptop → pre-recorded. | Presentations happen in an interior atrium, which is exactly where cellular fails. Steps 1-3 run the same container image, so a fallback changes the network path and nothing else. Extends D-005 and R-4. |
| D-017 | **The seal is enforced in code.** Manifest with image hashes committed at capture; the loader refuses sealed rows without an explicit flag; the unsealing run appends to a committed audit log. | "How do we know you didn't peek?" needs an answer that is not our word. Turns D-007 from a claim into an artifact. |
| D-018 | **Dataset: bytes in object storage, records in git.** Entrance ID and caliper reading are entered in the app at capture and written to a per-capture sidecar. | Low single-digit gigabytes is the wrong shape for a repo. Binding truth to image at the shutter press removes the reconciliation step where datasets rot. |
| D-019 | **Capture angle is pre-registered as a continuous error-versus-angle model on the sealed split**; the other four condition variables are reported from dev as exploratory. | A curve fitted against a continuously measured angle is affordable at 12-18 sealed entrances; a five-way contingency table is not. Amends the §2 analysis plan — see Amendment A-1. |
| D-020 | **LiDAR captured on every entrance and quarantined** from the metrology code path; loaded only by the evaluation harness. | Free once capture is instrumented, and it strengthens deliverable #5. If depth sits where the method can reach it, it eventually gets used to tune. Supersedes the matched-subset scope in §6. |

**Proposed, not yet locked**

| ID | Decision | Note |
|----|----------|------|
| D-011 | **Split conformal prediction** for confidence intervals, calibrated on a held-out split distinct from the sealed test set. | Distribution-free, gives coverage guarantees without distributional assumptions, and is roughly a day of work versus a learned heteroscedastic head. Needs confirmation. |

## 5. System design

**Stage 1 — ROI selection.** Operator taps the threshold edges and the reference card in the
captured frame. No learned model in v1 (D-004).

**Stage 2 — Metric recovery.** Four arms behind one interface, compared head to head. Interfaces
and rationale in [`ARCHITECTURE.md`](ARCHITECTURE.md) §5.

- **Arm A (primary, D-012):** single-view metrology with the card placed **vertically against the
  riser**. A homography from the card's four corners maps the riser plane, and the rise is measured
  inside that plane. Needs no intrinsics, no pose, no depth. The monocular accuracy ceiling (D-013).
- **Arm A′ (D-013):** the same metrology with the card **flat on the ground** — ground-plane
  homography decomposed with intrinsics to recover camera pose, height solved off the plane. The
  path a user can realistically perform.
- **Arm B:** learned monocular depth + reference-object scaling. The proposal's original approach,
  retained as the comparison point.
- **Arm C:** learned monocular depth + intrinsics-only scaling, no reference object. The most usable
  and least accurate arm, and the one that carries the usability claim (D-013); cut on 2026-09-02
  if weak.

**Stage 3 — Compliance reasoning.** Map the measurement and its interval to the ADA lines; emit
pass, fail, or abstain (D-009). The abstention rule's parameters are frozen in version control
before the sealed run — an unfrozen threshold is a dial fitted to the test set.

## 6. Data and ground truth

- **Target:** 40-60 entrances, each captured at 3-4 angles × 2 distances × available lighting.
- **Ground truth:** digital caliper to ±0.01" on threshold rise, recorded per entrance (D-003).
- **LiDAR reference:** depth captured on **every** entrance and quarantined from the metrology code
  path (D-020), loaded only for the monocular-vs-LiDAR comparison. LiDAR is a comparison, not ground
  truth — see R-10 in `ARCHITECTURE.md` §11.
- **Capture realism:** handheld, arbitrary angle, ambient light — deliberately not a clean protocol,
  because realistic capture is the condition under evaluation. Geometry is the one thing fixed:
  1× main lens, no digital zoom, no crop.
- **Capture instrument:** a purpose-built app (D-014) records the still, intrinsics, gravity, depth,
  entrance ID, caliper reading and condition tags as a single record per capture.
- **Condition tags** recorded at capture: distance, lighting, surface material, occlusion. **Capture
  angle is derived** from the recovered plane pose rather than estimated by the operator (D-019).
- **Ground truth binds at the shutter press** (D-018): entrance ID and caliper reading are entered in
  the app, not reconciled against filenames afterward.
- **Split assignment happens at collection time**, before any image is processed (D-007).
- **Constraint that drove topic choice:** storefronts are publicly observable and need no permission.

## 7. Evaluation protocol

1. **Pre-registration** (§2) committed to the repo on 2026-08-28, before first capture.
2. **Sealed test split** — ~30% of entrances, assigned randomly at collection, not processed and not
   viewed until results freeze on 2026-09-07. Run once. Anything noticed in it afterward is reported
   as exploratory, never as confirmatory. **Enforced in code, not by promise** (D-017): the loader
   refuses sealed rows without an explicit flag, and the single unsealing run appends to a committed
   audit log recording commit SHA, manifest hash and command line.
3. **Reported metrics.** From the sealed split: MAE in inches per arm; classification accuracy and
   false-pass rate at the 1/2" line (1/4" secondary); the pre-registered continuous error-versus-angle
   model (D-019); interval calibration (do the stated intervals contain truth at the stated rate?);
   abstention rate; monocular vs. LiDAR. From the dev split, labelled exploratory: error stratified by
   distance, lighting, surface material and occlusion.
4. **Negative results are presented as findings**, with error attributed to conditions rather than
   aggregated into one number.

## 8. Deliverables

1. Labeled dataset of storefront entrances with caliper ground truth and condition tags.
2. Working measurement pipeline, demonstrable live on an iPhone (D-005).
3. Error budget — accuracy by measurement type and capture condition, including the
   error-versus-angle curve.
4. Ablation — metrology vs. depth+reference vs. depth+intrinsics.
5. Comparison against LiDAR on every entrance (D-020).
6. Written findings and a capture protocol stating when an estimate is trustworthy.
7. Demo Day slide deck.

## 9. Timeline and ownership

Four parallel tracks. Owners are roles, not yet names (see §12).

| Dates | Field capture | Metrology (A/A′) | Depth baseline (B/C) | Demo + deck |
|-------|---------------|-------------------|----------------------|-------------|
| Aug 28-30 | Start paid developer account (R-7). Buy caliper. Build capture app (D-014); verify calibration-data delivery on team devices (R-9). Bench-test LiDAR against caliper (R-10). First 15 entrances, split assigned at capture. | Derive rise-error vs. capture angle before capture scales up. Homography + card detection end to end on 3 test images. | Off-the-shelf depth model running, establishes the floor. | Server endpoint stub; demo app is the capture app plus rendering. |
| Aug 31-Sep 2 | Dataset to 40+ entrances; LiDAR captured automatically per D-020. | Arms A and A′ metrically correct on dev split. | Arms B and C end to end. **Cut decision on Arm C, Sep 2.** | Upload → result round trip working. |
| Sep 3-5 | Complete to 60 if pace allows; otherwise stop and label. | Conformal calibration; abstention rule implemented. | — | Error-analysis notebook and charts. |
| Sep 6-7 | — | Iterate on the dominant failure mode. **Results freeze Sep 7. Unseal test split, run once.** | — | Deck built from frozen numbers. |
| Sep 8 | Cursor Workshop. Rehearse live demo. Backup recording captured. | | | |
| Sep 9 | **Demo Day** — 10 min + 5 min Q&A. | | | |

## 10. Demo Day plan

Live measurement of an entrance in the venue, compared against a caliper reading in real time,
including — if it occurs — an honest abstention. A pre-recorded backup of the same measurement is
captured on Sep 8 and shown only if the live attempt fails.

Presentation maps to the Track 2 rubric: research question → approach → technical demo → what we
learned and where it goes next → slide deck.

## 11. Build-in-public (X)

A graded Capstone requirement, per person, by Sep 9: 150+ engagements on project posts, 25+ new
followers, 5+ build-in-public posts, 1+ repost from outside the team.

Planned posts: (1) the problem in one image — a half-inch lip beside the ADA line that calls it a
violation; (2) dataset build, caliper in frame; (3) first honest error number, including if it is
bad; (4) the ablation chart — metrology vs. depth model; (5) LiDAR vs. single photo, the money
chart; (6) Demo Day live measurement clip.

Failure cases perform well and cost nothing to publish. The accessibility and civic-tech
communities are the realistic source of the outside repost; the Project Sidewalk / Makeability Lab
research community is a reasonable tag given the work builds on that line.

## 12. Open items — blocking

- **O-1. Team roster.** Four people confirmed as a count; names, X handles and device count
  recorded in [TEAM.md](TEAM.md) (TICK-003, #15), which also fixes the R-8 response rule if fewer
  than three LiDAR-capable iPhones are available. Closes when that note is filled from devices in
  hand.
- **O-2. Caliper not yet in hand.** D-003 depends on it and ground-truth capture starts Aug 28.
  Same-day purchase.
- **O-3. No tripod or measuring aids confirmed.** The controlled-angle subset that makes the
  angle-error curve interpretable needs a repeatable way to fix camera pose.
- **O-4. D-011 unconfirmed.** Interval method must be settled before Sep 3.
- **O-5. Tickets not yet filed.** Tracker chosen: **GitHub Issues** on this repo — already
  configured and currently empty. `CLAUDE.md` §5 requires every change to trace to a ticket; O-1 to
  O-4 and the architecture risks still need filing. Closes when the backlog exists.

## 13. Risks

| ID | Risk | Mitigation |
|----|------|------------|
| R-1 | Metrology accuracy lands far off the ADA lines | Reframe as characterization; the error budget is the contribution either way (this is why D-007 exists) |
| R-2 | Data collection consumes the timeline | 40 entrances is the floor, 60 the goal; well-labeled beats numerous |
| R-3 | Credit card too small in frame at realistic distance to anchor scale precisely | Reduced by D-012: at ~2.5m on a 12MP frame the card spans roughly 100px, so scale is well conditioned and obliquity dominates the budget instead. Printed marker on a subset remains the fallback, reported as the reference-object ablation |
| R-4 | Venue connectivity fails and the thin client cannot reach the server | Fallback chain per D-016: cellular → venue wifi → identical server image on a laptop → pre-recorded demo |
| R-5 | Sealed split burned early or corrupted by a bug in the single run | Dry-run the full evaluation on the dev split first; the unsealing run executes a script already exercised end to end |
| R-6 | Occlusion (mats, sandwich boards) sits directly in the ROI | Tagged as a condition; expected to appear in the error budget as a named failure mode rather than be engineered around |

Architecture-level risks — app signing on the critical path, device availability, calibration-data
delivery, LiDAR coarser than the success bar, and demo/capture drift — are tracked as R-7 to R-11
in [`ARCHITECTURE.md`](ARCHITECTURE.md) §11.
