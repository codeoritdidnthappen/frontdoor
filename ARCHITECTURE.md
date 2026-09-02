# ARCHITECTURE — Monocular Measurement of Storefront Accessibility

**Status:** Drafted 2026-08-29. Derived from [`PRD.md`](PRD.md); decisions logged in [`CHANGES.log`](CHANGES.log).
**Demo Day:** 2026-09-09 · **Working days remaining at drafting:** 11

---

## 1. What this document decides

`PRD.md` owns the research design — the question, the pre-registered hypothesis, the success bar.
This document owns the system that produces the evidence: what gets built, how the pieces divide,
and which properties are enforced by construction rather than by discipline.

Three properties drive every structural choice here:

1. **The demo and the error budget must run the same code.** If they diverge, Demo Day exhibits a
   system whose behaviour the numbers do not characterise.
2. **The method must not be able to reach data it is not allowed to use.** The sealed split and the
   LiDAR depth maps are both enforced in code, not by intention.
3. **Every measurement must be reconstructable from what is committed.** An image, its metadata and
   its ground truth are one record, created at the shutter press.

## 2. Method boundary (D-015)

The method under test may consume:

- **one RGB still frame**
- **camera intrinsics** for that frame (focal lengths in pixels, principal point, distortion table)
- **the gravity vector** at the instant of capture

It may not consume: LiDAR depth, multi-frame or motion-derived scale, or any AR world tracking.

This boundary is what answers "why not just use ARKit?" — ARKit's visual-inertial odometry recovers
metric scale from motion, which would make the question uninteresting. The boundary is enforced
structurally: the capture app is built on **AVFoundation + CoreMotion and never starts an AR
session** (D-014), so motion-derived scale is not merely forbidden, it is unavailable.

The same choice gives full-resolution stills with matching intrinsics. ARKit's video frames are
substantially smaller, and the error budget is measured in pixels across the threshold rise — at
roughly half the frame width, localisation error roughly doubles, in the one place the margin is
thinnest.

## 3. System overview

```
  ┌────────────────────┐
  │  Capture app (iOS) │  AVFoundation + CoreMotion
  │  §4                │  still + intrinsics + gravity + depth + truth
  └─────────┬──────────┘
            │ upload
            ▼
  ┌────────────────────┐        ┌──────────────────────────┐
  │  Object storage    │◄───────│  Manifest + labels (git) │
  │  images, depth     │        │  hashes, splits, audit   │
  └─────────┬──────────┘        └──────────────────────────┘
            │
            ├──────────────────────┬───────────────────────┐
            ▼                      ▼                       │
  ┌────────────────────┐  ┌────────────────────┐           │
  │  Server (cloud VM) │  │  Eval harness      │           │
  │  §6  live demo     │  │  §7  error budget  │           │
  └─────────┬──────────┘  └─────────┬──────────┘           │
            │                       │                      │
            └───────────┬───────────┘                      │
                        ▼                                  │
            ┌───────────────────────┐                      │
            │  Core metrology lib   │◄─────────────────────┘
            │  §5   (Python)        │   never sees sealed or
            └───────────────────────┘   depth data  §7, §9
```

The core library is the only place metrology exists. The server and the evaluation harness are thin
entrypoints over it. Neither reimplements a measurement.

## 4. Capture app

A single-purpose iOS app, built before dataset capture begins. It is not the demo app; the demo app
(§6) is this app plus result rendering, so the capture path is identical in both.

**Stack:** AVFoundation photo capture with calibration-data delivery, depth-data delivery, and
CoreMotion device motion. No ARKit (D-014, §2).

**Per capture it writes one image, one depth map (or `"depth": null` when the
device has no depth sensor), and one JSON sidecar:**

```json
{
  "capture_id":     "uuid",
  "entrance_id":    "E-014",
  "captured_at":    "2026-08-30T14:22:31Z",
  "device_model":   "iPhone15,3",
  "lens":           "builtInWideAngleCamera",
  "image":          {"path": "...", "sha256": "6105d6cc76af400325e94d588ce511be5bfdbb73b437dc51eca43917d7a43e3d", "width": 4032, "height": 3024},
  "depth":          {"path": "...", "sha256": "ded32129b05bfc16ce501e654a169960583352cbc974824ed16ce94855904386"},
  "intrinsics":     {"fx": 2934.1, "fy": 2934.1, "cx": 2016.4, "cy": 1512.7},
  "gravity":        [0.02, -0.98, -0.19],
  "card_placement": "vertical",
  "ground_truth":   {"rise_in": 0.53, "instrument": "caliper"},
  "conditions":     {"distance_m": 2.5, "lighting": "overcast",
                     "surface": "concrete", "occlusion": "none"},
  "split":          "dev"
}
```

Three things this shape buys:

- **Ground truth binds at the shutter press.** The operator enters the entrance ID and the caliper
  reading in the app. There is no later reconciliation of a spreadsheet against filenames.
- **Split is assigned when an entrance ID is first created** (D-007), before any image is processed,
  and is immutable thereafter.
- **Capture angle is derived, not typed.** Obliquity comes from the recovered plane pose (§5), with
  gravity as an independent cross-check. This is what makes the angle curve in §7 a measurement
  rather than an operator's estimate.

**Fixed capture rules:** 1× main lens, no digital zoom, no crop. Angle, distance, lighting and
occlusion stay deliberately uncontrolled — realistic capture is the condition under evaluation.

## 5. Core metrology library

Pure Python, no network, no I/O beyond what it is handed. Input is one image plus one sidecar;
output is a measurement with an interval, or an abstention.

**Stage 1 — ROI.** The operator taps the threshold edges and the reference card (D-004). Learned
segmentation remains a stretch goal.

**Stage 2 — scale recovery.** Four arms behind one interface, so the harness can run any of them
over the same input:

| Arm | Scale source | Needs intrinsics | Role |
|-----|--------------|------------------|------|
| **A** | card **vertical against the riser**; homography from its four corners maps the riser plane; rise measured in-plane | no | primary; monocular accuracy ceiling |
| **A′** | card **flat on the ground**; ground homography, decomposed with intrinsics to camera pose, height solved off the plane | yes | realistic-user path |
| **B** | learned monocular depth, scaled by the reference object | yes | baseline to beat |
| **C** | learned monocular depth, intrinsics-only scaling, no reference object | yes | most usable, least accurate |

Arm A needs no camera model because scale and measurement share one surface: a homography built
from a known rectangle already absorbs the projection, so any length inside that plane is metric.
This is the reason A is the primary arm (D-012, D-013).

Arms A, A′ and C form a deliberate accuracy-versus-usability gradient, which is the ablation the
PRD promises as deliverable #4. Arm C carries the "works with what you already carry" usability
claim, since it is the only arm an unaided user can actually perform (D-013).

**Stage 3 — compliance reasoning.** Map measurement and interval to the ADA lines; emit pass, fail,
or abstain. The abstention rule's parameters are frozen in version control before the sealed run
(D-009, §7) — an unfrozen threshold is a dial fitted to the test set.

## 6. Server and the live demo

A single stateless endpoint on a free-tier host (D-016, D-026): `POST /measure` takes the image and sidecar,
calls the core library, returns per-arm measurement, interval, and decision.

It holds no state and owns no metrology. Its only job is to be reachable from a phone on stage.

**Fallback chain**, in order, for a venue where presentations happen in an interior atrium:

1. cellular to the host
2. venue wifi to the host
3. the identical server image running on a team laptop, phone tethered to it
4. the pre-recorded measurement captured Sep 8

Steps 1–3 run the same container image, so a fallback changes the network path and nothing else.

## 7. Evaluation harness and the seal

The harness is the second entrypoint over the core library. It produces every number in the error
budget, and it is the component that enforces D-007 mechanically rather than by promise.

**Manifest.** `data/manifest.csv`, committed to git, one row per capture: `capture_id`,
`entrance_id`, `image_sha256`, `depth_sha256`, `split`. Written at capture time, never edited.
`depth_sha256` is the SHA-256 of the depth file, or empty when that capture has no depth map
(TICK-023 AC5).

**Refusal, in two layers.** The dataset loader derives each row's split from `assign_split` and the
committed seed — never from the manifest's `split` cell, which is a cache — and refuses sealed rows
without an explicit `--include-sealed` flag. Underneath it, object keys carry their partition
(`open/` or `sealed/`), so `storage.ObjectStore.get` refuses a sealed key on its own, without
reading the manifest (#182). The second layer exists because the first one was, for a while, the
only one: the seal lived entirely in `loader` and `eval`, and anyone holding the images credential
could fetch sealed bytes directly with no audit line.

**What that does and does not guarantee.** No code path in this repository reaches a sealed capture
without writing a `SEAL_AUDIT.log` line first. Sealed bytes are not, however, unreachable: R2 scopes
tokens per bucket rather than per prefix (D-026), so the images token still permits a raw client to
read `sealed/`. Closing that would take a third bucket. The seal is an integrity mechanism for
honest use, backed by an audit trail — not an access control.

**Audit.** Any run passing `--include-sealed` appends one line to `SEAL_AUDIT.log`, committed.
Tab-separated fields, in this order — the same order `seal_audit.AUDIT_FIELDS` writes, so the log
and this document cannot disagree about which column is which:

`utc_timestamp`, `commit_sha`, `manifest_sha256`, `command_line`, `operator`, `resolved_config`.

`resolved_config` records the image bucket and endpoint the run actually addressed, never
credentials. `.env` is gitignored and selects them, so a clean working tree alone does not mean two
runs read the same bytes; recording the resolution closes that gap without pretending an ignored
file is a tracked change.

The audit log is the evidence that the sealed set was opened once, on 2026-09-07, against a known
state of the code.

**Dry run before the real one.** The full evaluation runs end to end on dev first (R-5). The
unsealing run executes a script already exercised, not one written that morning.

**What the sealed split carries.** Headline MAE, classification accuracy and false-pass rate at the
1/2" line, and the pre-registered continuous error-versus-angle model (D-019). The remaining four
condition variables are reported from dev and labelled exploratory — with 12–18 sealed entrances,
a five-way stratification has per-cell counts of one or two and cannot support confirmatory claims.

Fitting a curve against a continuously measured angle is what makes one confirmatory stratified
result affordable at this sample size; a contingency table over five variables is not.

## 8. Data architecture

**Bytes in object storage, records in git** (D-018). Images and depth maps live in free-tier
object storage (D-026) beside whatever host runs evaluation — which may be a team Mac rather than
the server host; that choice is open and must be logged when taken (#50). The repository holds the manifest, labels, condition tags,
hashes, the seal audit log, and the frozen abstention parameters — everything needed to verify a
result, and nothing large enough to make the repo unusable.

A few hundred captures plus depth maps is low single-digit gigabytes, which is the wrong shape for
git and larger than the free LFS allowance in any case.

**Integrity.** Every image and depth map is hashed at capture. The harness verifies hashes on load,
so a corrupted or substituted file fails loudly rather than quietly changing a number.

**Retention.** The bucket is the system of record during the sprint. At results freeze the dataset
is published as a release artifact, satisfying deliverable #1.

## 9. LiDAR quarantine (D-020)

Every capture records a LiDAR depth map, on every entrance rather than a matched subset — with the
capture app in place this is free, and it strengthens deliverable #5. A device without a depth
sensor still captures: the sidecar writes `"depth": null` and the manifest leaves `depth_sha256`
empty (TICK-023).

Depth maps are stored in a **separate bucket** (D-026) that the image-only loader
credential cannot read. A prefix inside one bucket is not enough where the provider
scopes credentials per bucket. They are loaded only by the evaluation harness, only
for the monocular-versus-LiDAR comparison. If depth sits where the method can reach
it, it is eventually used to tune, and the comparison stops meaning anything — the
same reasoning as the sealed split. Layout: `data/STORAGE.md`.

LiDAR is a comparison, not ground truth. Commonly reported depth error is around ±1cm, coarser than
the 0.25" target and comparable to the 1/2" decision line itself. The caliper (±0.01") remains the
reference (D-003). Whether LiDAR clears your own bar is an open empirical question — see R-10.

## 10. Assumptions

- **A-1. FALSIFIED — one LiDAR-capable iPhone, not a fleet.** The team holds an iPhone 16 Pro
  (LiDAR), an iPhone 16 (no depth sensor) and two Android devices, which cannot run an
  AVFoundation capture app at all. Evidence comes from **two devices of one generation across two
  camera tiers**, not from Pro-class cameras uniformly; `device_model` is recorded per capture so
  device remains visible to the error analysis. See TEAM.md §2.
- **A-2. Calibration-data delivery works on the team's actual devices.** Verified day one (R-9).
  ARKit is the fallback if it does not, at the resolution cost described in §2.
- **A-3. FALSIFIED — two capture-capable devices, one with LiDAR.** R-8 has fired; its response
  rule is recorded in TEAM.md §4 (cut the entrance target, floor of 30, drop Arm A′ captures before
  entrances). Note that cutting the target does not clear the binding constraint: D-020 requires
  LiDAR on every entrance and only one device produces it, so capture serialises onto a single
  operator regardless of target. Relaxing D-020 to a matched subset is an open protocol decision.
- **A-4. The threshold rise presents a usable planar riser face.** Heavily bevelled or rounded
  thresholds are a documented failure class, as glass doors already are.

## 11. Architecture risks

| ID | Risk | Mitigation |
|----|------|------------|
| R-7 | App signing is on the critical path for the whole dataset; free-provisioning builds expire after 7 days, landing mid-capture | **Accepted, not mitigated by purchase** (D-025). Managed by a committed signing calendar with no gap through Sep 11, including a mandatory re-sign by Sep 6. James runs Windows and holds the only LiDAR device, so each of his installs is a scheduled physical session with a Mac owner |
| R-8 | Fewer capture devices than parallel field tracks assume | Detected at roster assignment (O-1); response is to cut the entrance target, not the protocol |
| R-9 | Calibration-data delivery unavailable on target devices | Verified day one; ARKit fallback, accepting the resolution cost in §2 |
| R-10 | LiDAR is coarser than the 0.25" bar, so the "accuracy ceiling" sits below the success criterion | Bench-test against the caliper in week one; if confirmed, deliverable #5 is reframed as evidence the decision line is below what phone depth sensors deliver |
| R-11 | Demo app and capture app drift apart, so Demo Day exhibits uncharacterised behaviour | Demo app is the capture app plus rendering; one capture path, one metrology library |
