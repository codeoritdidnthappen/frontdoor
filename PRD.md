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
  *(**D-036, 2026-09-02: no caliper is used, so this metric has no measurable subject in this
  window.** The criterion below is untested and reported as untested — see Amendment A-3.)*
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

**Amendment A-3 (2026-09-02) — one product, on iPhone Pro with LiDAR.** There is one product,
and its target device is an **iPhone Pro with LiDAR**. Everything serving a different device or a
different route to scale is a later version and is deprioritised. The plain-photo screening study
is the product; the metrology arms are not.

**The consequence for this section, stated plainly: the primary hypothesis above is not tested in
this window.** It is not relaxed, not re-scoped and not re-judged against a different arm — it is
untested, and is reported as untested. Reaching for a number from too few sealed entrances is the
failure D-007 exists to prevent. What survives as a finding is the rise-error-versus-angle budget,
derived before any data existed. LiDAR remains **captured, not consumed**: D-015's method boundary
and D-020's quarantine are unchanged by targeting hardware that has a depth sensor. Reported as an
amendment at Demo Day. Full entry in `CHANGES.log`.

**Amendment A-2 (date not established) — the success criterion names its arm.** The criterion
above reads "MAE ≤ 0.25" on the sealed test split" without saying which of the arms it judges.
A-2 fixes it to **Arm A only**; A′, B and C are reported without a pass/fail bar. Reason, as
stated in the tickets that cite it: an unnamed arm would let the hypothesis be scored against
whichever arm looked best once results were seen — the exact failure D-007 exists to prevent.

**This entry is RECONSTRUCTED from ticket usage; its date and original wording are not
recoverable.** It is recorded so the amendment is not silently absent from the pre-registration,
not to assert when it was agreed. Whether this rule originates in A-2 or in D-022 is unresolved
(#183, #132), and the distinction matters: an amendment must be reported as such at Demo Day,
while a locked decision carries no such obligation. Until whoever took the decision settles it,
treat this as reportable. See `CHANGES.log`, "Decision-log gap".

## 3. Scope

**In scope**

- One measurement type — **threshold rise** — characterized completely.
- Single RGB frame, no depth sensor required at inference.
- Opaque-door entrances.
- Four scale-recovery arms compared head to head (§5), spanning an accuracy-versus-usability
  gradient (D-013). **Amended 2026-09-02: Arm C is cut (D-030), and Arm B is not served by the
  live deployment (D-031), so the head-to-head as actually run is A against A′.**
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
| D-003 **(SUPERSEDED — see D-036)** | **Digital caliper / depth gauge (±0.01") is the ground-truth instrument for threshold rise.** Tape measure retained for clear width and ramp run. **Superseded 2026-09-02 by D-036: no caliper is used. There is no instrument ground truth, so the threshold-rise study has no measurable subject in this window.** | Evaluating a 1/4" decision line with a tape read to 1/8" puts instrument uncertainty at half the disputed quantity. First objection any reviewer raises. |
| D-004 | **Human-tap ROI for v1.** The operator taps the threshold edge in the photo; learned segmentation is deferred to stretch. | Fine-tuned segmentation means a second hand-annotation job stacked on tape measurement in the same five days. Detection is not the research question. |
| D-005 | **Native iOS app, thin client.** Swift app captures, uploads, and renders; all metrology runs server-side in Python. | Keeps development in one language and leaves Sep 6-8 free for iteration instead of Core ML conversion. Requires venue connectivity — see R-4. |
| D-006 | **Reference object is a credit card (ISO/IEC 7810 ID-1, 85.60 × 53.98mm).** | Spec-exact dimensions and already in the user's pocket. It is small in frame at 2-3m and will cost precision — but "works with what you already carry" is the usability finding worth having. |
| D-007 | **Pre-registration + sealed test set.** ~30% of entrances randomly sealed at collection time, unopened until results freeze 2026-09-07; run once. | The contribution is an honest error budget. Without this, reported accuracy partly reflects choices fitted to the same images, and the negative-result framing collapses under "how many variants did you try?" |
| D-008 | **Primary success bar is the 1/2" ADA line, MAE ≤ 0.25".** | The consequential line — above it the law requires a ramp. Honestly reachable, and the classification most useful to the end user. |
| D-009 | **Abstention is a first-class output.** Where the interval spans a decision line, the system declines to classify. | A confident wrong answer about passability is worse for the user than no answer. Abstention rate is a reported metric, not a hidden failure. |
| D-010 | **Team of 4**, roles assigned in §9. | Enables field capture, metrology, evaluation, and demo/deck to run in parallel — the only way §9 fits in 12 days. |
| D-012 | **The reference card is placed vertically against the riser face.** Arm A recovers the rise in-plane from a homography built on the card's four corners. | Scale and measurement share one surface, so the homography absorbs the projection: no intrinsics, no pose, no depth. Removes the largest unknown from the primary arm. Supersedes the ground-plane formulation in §5. |
| D-013 | **Three-arm usability gradient.** A (vertical card) is the monocular accuracy ceiling, A′ (card on ground) the realistic-user path, C (no card) the most usable. | Arm A requires physical access to the step — the one thing a wheelchair user at the bottom of it cannot do. Calling A a ceiling rather than the shipping path keeps the claim honest, and D-006's "already in your pocket" rationale moves to Arm C, where it is true. **Amended 2026-09-02 by D-030: Arm C is cut.** The gradient's most-usable end is not built, so the usability claim it anchored is not evidenced by this study. |
| D-014 **(AMENDED — see D-029)** | **Capture-only app, built before dataset capture**, on AVFoundation + CoreMotion. No ARKit. | Yields true intrinsics, gravity, LiDAR depth and full-resolution stills, and makes capture angle a measured quantity rather than an operator's estimate. ARKit's video frames are too small for an error budget counted in pixels across the rise. Supersedes stock-camera capture. **Amended 2026-09-02 by D-029: the device is `builtInDualWideCamera`, not `builtInWideAngleCamera`, which delivers no calibration data on any team hardware. The 1× optics are unchanged. This row's claim of LiDAR depth is also withdrawn — LiDAR carries no calibration.** |
| D-015 | **Method boundary: one RGB still + intrinsics + gravity.** No depth map, no motion-derived scale. | Answers "why not just use ARKit?" — visual-inertial odometry recovers metric scale from motion, which would make the question uninteresting. Enforced by construction: no AR session is ever started. |
| D-016 | **Metrology server runs on a free-tier host** (D-026), with fallback chain cellular → venue wifi → identical image on a laptop → pre-recorded. | Presentations happen in an interior atrium, which is exactly where cellular fails. Steps 1-3 run the same container image, so a fallback changes the network path and nothing else. Extends D-005 and R-4. **Amended 2026-09-02 by D-031: the host is paid** (Fly.io, ~$2/month, under an explicit spend limit). The fallback chain is unchanged. |
| D-017 | **The seal is enforced in code.** Manifest with image hashes committed at capture; the loader refuses sealed rows without an explicit flag; the unsealing run appends to a committed audit log. | "How do we know you didn't peek?" needs an answer that is not our word. Turns D-007 from a claim into an artifact. |
| D-018 | **Dataset: bytes in free-tier object storage, records in git** (D-026). Entrance ID and caliper reading are entered in the app at capture and written to a per-capture sidecar. | Low single-digit gigabytes is the wrong shape for a repo. Binding truth to image at the shutter press removes the reconciliation step where datasets rot. |
| D-019 | **Capture angle is pre-registered as a continuous error-versus-angle model on the sealed split**; the other four condition variables are reported from dev as exploratory. | A curve fitted against a continuously measured angle is affordable at 12-18 sealed entrances; a five-way contingency table is not. Amends the §2 analysis plan — see Amendment A-1. |
| D-020 | **LiDAR captured on every entrance and quarantined** from the metrology code path; loaded only by the evaluation harness. | Free once capture is instrumented, and it strengthens deliverable #5. If depth sits where the method can reach it, it eventually gets used to tune. Supersedes the matched-subset scope in §6. **Confirmed 2026-09-02 by D-032: depth is captured, on James's iPhone 17 Pro (`iPhone18,1`)** — one LiDAR device shooting every entrance meets "every entrance". LiDAR delivers no calibration and depth arrives `accuracy=relative`, so it is a map to compare against, not a metric ruler; D-015 is untouched. |
| D-021–D-024 | **RECONSTRUCTED — not original text, and not locked by this table.** D-021 (the per-entrance shot plan is enforced by the instrument), D-022 (the success bar applies to Arm A only), D-023 (three-way dev/calib/sealed split assigned deterministically at capture and immutable thereafter), D-024 (Stage 1 ROI taps happen in-app at capture and go inside the seal). | These four IDs are cited across the backlog but were never written into `CHANGES.log`. The statements there are reconstructed from how each ID is used in tickets and are **not claimed to be the original wording**; they are listed here so the IDs resolve rather than dangle. **D-022's attribution is unresolved** — it states the same rule as Amendment A-2, and a decision and an amendment cannot both originate one rule (#183, #132). Full text and status lines: `CHANGES.log`, "Decision-log gap". |
| D-025 | **No paid Apple Developer Program.** The capture app is signed with **free provisioning** and installed over a cable from a team Mac. | No paid-gated capability is needed: AVFoundation capture, depth delivery and CoreMotion require only Info.plist usage descriptions. Accepted cost: builds expire after 7 days (R-7), making signing a scheduled activity rather than a one-off. A build signed 2026-08-31 expires 2026-09-07, **before Demo Day, so a re-sign no later than 2026-09-06 is mandatory.** Supersedes TICK-001's requirement to enrol and pay by 2026-08-29. |
| D-026 | **All hosted infrastructure runs on provider free tiers.** No spend authorised for object storage or the server host. | Cost decision. Load-bearing consequences: projected dataset volume is 2-5 GB, so a 5 GB allowance is marginal and 10 GB comfortable; **billing must be incapable of starting silently**; and the D-020 depth quarantine must be satisfied by **two buckets** where a provider scopes credentials per bucket rather than per prefix — the denial is the requirement, not the layout. Supersedes the unstated assumption in D-016 and D-018 that hosting would be paid. **Amended 2026-09-02 by D-031, for the server host only; object storage stays free.** |
| D-027 | **Tickets are assigned, not self-assigned.** Every open issue names an owner in GitHub, following the work division in TEAM.md §3. | The self-assign-and-rotate convention left the whole backlog owner-less, and the device audit showed the division is constrained by hardware rather than preference — only one person can capture entrances, and only one can build and test the capture app unaided. Work may still move between people; the rule is to **reassign rather than clear**, so no ticket is ever left without a name against it. Supersedes D-010's "names pending" and O-1's self-assign convention. |
| D-028 | **Object keys carry their partition, and the seal is enforced in storage** — not only in the loader. | After TICK-070/TICK-071 (#166) the seal lived entirely in `loader.py` and `eval.py`; `ObjectStore.get(capture_id)` consulted neither, so anyone holding the images credential — everyone on the team — could fetch a sealed capture's bytes directly, and no `SEAL_AUDIT.log` line was written. Taken 2026-09-01, closing #182. |
| D-029 | **AMENDMENT TO D-014 (2026-09-02) — the capture device is `builtInDualWideCamera`, not `builtInWideAngleCamera`.** | Measured on two team phones by TICK-020's on-device probe (#24): the bare wide angle delivers **no calibration data at all**. The 1× optics are unchanged. D-014's claim of LiDAR depth is also withdrawn — LiDAR carries no calibration. **Reported as an amendment at Demo Day.** |
| D-030 | **Arm C is cut** (2026-09-02). Learned depth with intrinsics-only scaling and no reference object will not be implemented. | Frozen rather than deleted: `frontdoor.metrology` keeps `C` registered and the ablation reports it cut with this reason. **This is not the decision #43 asked for** — TICK-049 required citing Arm C's measured dev-split error, and there is none: Arm C was never implemented, the metrology library was scaffolded the same day, and no capture has been taken. The gate arrived with nothing to weigh, and that is recorded rather than papered over. Closes #43. |
| D-031 | **AMENDMENT TO D-026 (2026-09-02) — the measure server runs on a PAID host.** Fly.io `shared-cpu-1x`/256 MB in `sjc`, about $2/month. Object storage stays free. | Measured, not estimated: the image serves `GET /health` capped at 256 MB using 69 MiB, and Fly's smallest always-on machine is 256 MB at ~$2 against Render's 512 MB at $7. **D-026's "billing must be incapable of starting silently" clause is not waived** — on a paid plan it is met by an explicit spend limit plus a billing alert rather than by the absence of a card, both prerequisites recorded in `docs/server-deploy.md`. Authorises the server host and nothing else. Live at `https://frontdoor-measure.fly.dev`. **Reported as an amendment at Demo Day.** |
| D-032 | **LiDAR depth is captured, on James's iPhone 17 Pro (`iPhone18,1`)** (2026-09-02). Reverses the 2026-09-01 pivot's "no LiDAR depth" clause for capture; the rest of the pivot stands. | D-020 asks for depth on every entrance, not on every device, so one phone shooting every entrance satisfies it. **Authorises capture and storage only**: TICK-020 measured that LiDAR delivers no calibration and that dual-wide depth is `accuracy=relative`, so it is neither a route to intrinsics nor a metric ruler, and D-015 still forbids the method consuming device depth. **Two prerequisites, not waived:** a build runs on that phone, but it has not been through the capability probe, so its depth delivery is expected rather than measured; and James runs Windows, so the mandatory 7-day re-sign (D-025) needs a Mac owner present. Reopens the TEAM.md §3 constraint that capture runs on Emily's phones. |
| D-033 | **AMENDMENT TO D-020 and D-031 (2026-09-02) — the server holds a WRITE-ONLY depth token.** Read+write on `frontdoor-image`, **write-only** on `frontdoor-depth`. | #33 routes uploads through the server so no R2 credential ships inside the app; depth still has to reach its bucket. D-020's guarantee is that the metrology path cannot **read** depth — "if depth sits where the method can reach it, it eventually gets used to tune" — and a write-only credential cannot tune, peek or load. The harness keeps the only read token, so the invariant is unchanged; only the direction of the server's access is. Verified by asserting the token can PUT and is refused on GET. |
| D-035 | **The evaluation harness runs on a team Mac**, not on the server host (2026-09-02). | The host is one 256 MB machine with a single worker, sized for a request rather than for scoring a few hundred captures, and the team has the machines. It also keeps the depth **read** credential off the request path, which is what D-020 and D-033 are for. Settles a contradiction: the 2026-09-01 entry had recorded this while D-031 said the question was still open. |
| D-036 | **One capture device, LiDAR on, no caliper** (2026-09-02). Capture runs on **James's iPhone Pro with LiDAR alone**; depth is captured on every entrance; **no caliper is used**. Supersedes D-003. | Depth on every entrance (D-020) needs a device that has a sensor, and one operator with one phone is the shortest path to a uniform dataset. **Costs, not waived:** `device_model` becomes a constant rather than a stratification variable, so the findings must say the result is measured on a single phone; and that phone is a single point of failure — free-provisioning builds expire in 7 days (D-025), James runs Windows and cannot re-sign unaided, and the device has still never been through the capability probe (#24). **No caliper means no instrument ground truth**, so the §2 criterion is untested rather than relaxed, deliverable #1 becomes photographs with operator presence labels, and deliverable #5's LiDAR comparison has no reference to compare against. The screening study is unaffected — its truth is the operator's labels, which need no instrument. |
| D-034 | **The capture sidecar carries its mode** (2026-09-02): `metrology`, `screening` or `imported`. One schema with a discriminator, not two. An absent mode means metrology, so every sidecar written before this entry stays valid and stays held to its original contract. | The 2026-09-01 pivot made capture plain photos, and the app implemented the pre-pivot study — the camera sat behind a caliper reading, the writer refused a capture with no ROI taps, and the schema required `ground_truth`, `card_placement` and `intrinsics`. An operator following `docs/capture-protocol.md` literally could not produce a record. **The forbidding is the point:** a screening capture may not *carry* a caliper reading and an imported photo may not carry intrinsics — a plausible number in either would be read downstream as a measurement. Metrology's path and every one of its gates are unchanged; whether that study is alive is A-3 (#67) and is not decided here. |

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
  if weak. **Cut 2026-09-02 by D-030** — and not because it was measured weak: it was never
  implemented, so the gate arrived with nothing to weigh. The usability claim it carried is
  therefore unevidenced by this study rather than disproved.

**Stage 3 — Compliance reasoning.** Map the measurement and its interval to the ADA lines; emit
pass, fail, or abstain (D-009). The abstention rule's parameters are frozen in version control
before the sealed run — an unfrozen threshold is a dial fitted to the test set.

## 6. Data and ground truth

- **Target:** 40-60 entrances, each captured at 3-4 angles × 2 distances × available lighting.
- **Ground truth:** ~~digital caliper to ±0.01" on threshold rise, recorded per entrance (D-003)~~.
  **Superseded 2026-09-02 by D-036: no caliper.** Ground truth is the capturing operator's
  **presence labels** — ramp/bevel, handrails, accessible hardware, signage — recorded at the door
  (#168). No instrument is used, and no threshold-rise measurement is taken.
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

Four parallel tracks. Owners are **named** — the roster and the full work division are in
[TEAM.md](TEAM.md), and every open issue is assigned in GitHub. Tickets are assigned, not
self-assigned; the earlier convention in O-1 is superseded.

| Dates | Field capture | Metrology (A/A′) | Depth baseline (B/C) | Demo + deck |
|-------|---------------|-------------------|----------------------|-------------|
| Aug 28-30 | Set up free-provisioning signing and schedule the re-signs (R-7, D-025). Buy caliper. Build capture app (D-014); verify calibration-data delivery on team devices (R-9). Bench-test LiDAR against caliper (R-10). First 15 entrances, split assigned at capture. | Derive rise-error vs. capture angle before capture scales up. Homography + card detection end to end on 3 test images. | Off-the-shelf depth model running, establishes the floor. | Server endpoint stub; demo app is the capture app plus rendering. |
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
| R-3 | Credit card too small in frame at realistic distance to anchor scale precisely | Reduced by D-012: at ~2.5m on a 12MP frame the card spans roughly 100px, so scale is well conditioned. **The clause "and obliquity dominates the budget instead" was refuted by TICK-041 (#35): tap precision is the binding term, not obliquity. See `docs/rise-error-vs-angle.md`; the distance cap moved to 2.5 m in #136 as a result.** Printed marker on a subset remains the fallback, reported as the reference-object ablation |
| R-4 | Venue connectivity fails and the thin client cannot reach the server | Fallback chain per D-016: cellular → venue wifi → identical server image on a laptop → pre-recorded demo |
| R-5 | Sealed split burned early or corrupted by a bug in the single run | Dry-run the full evaluation on the dev split first; the unsealing run executes a script already exercised end to end |
| R-6 | Occlusion (mats, sandwich boards) sits directly in the ROI | Tagged as a condition; expected to appear in the error budget as a named failure mode rather than be engineered around |

Architecture-level risks — app signing on the critical path, device availability, calibration-data
delivery, LiDAR coarser than the success bar, and demo/capture drift — are tracked as R-7 to R-11
in [`ARCHITECTURE.md`](ARCHITECTURE.md) §11.
