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
   captured depth maps are both enforced in code, not by intention.
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
  "device_model":   "iPhone18,1",
  "lens":           "builtInWideAngleCamera",
  "capture_device": "builtInDualWideCamera",
  "zoom_factor":    2.0,
  "image":          {"path": "...", "sha256": "6105d6cc76af400325e94d588ce511be5bfdbb73b437dc51eca43917d7a43e3d", "width": 4032, "height": 3024,
                     "exif_orientation": 6},
  "depth":          {"path": "...", "sha256": "ded32129b05bfc16ce501e654a169960583352cbc974824ed16ce94855904386"},
  "intrinsics":     {"fx": 2807.7, "fy": 2807.7, "cx": 2006.4, "cy": 1503.2,
                     "distortion_table": [0.0, 0.0021, 0.0086, 0.0195, 0.0349],
                     "distortion_center": {"x": 2016.0, "y": 1512.0}},
  "gravity":        [0.02, -0.98, -0.19],
  "card_placement": "vertical",
  "ground_truth":   {"rise_in": 0.53, "instrument": "caliper"},
  "conditions":     {"distance_m": 2.5, "lighting": "overcast",
                     "surface": "concrete", "occlusion": "none"},
  "split":          "dev"
}
```

`lens` and `capture_device` are different claims and both are needed. The 1x main lens is the
optics D-014 fixes; on James's iPhone 17 Pro it is reached through `builtInDualWideCamera`, because the
bare `builtInWideAngleCamera` delivers no calibration data at all and therefore cannot produce a
measurable frame (TICK-020). `zoom_factor` is what makes the claim checkable: on that device the
zoom scale is relative to the ultra-wide, so **2.00 is the 1x main lens** and 1.00 would be the
ultra-wide's ~120 degrees. A record carrying only a lens name cannot tell those apart.

**D-014 names `builtInWideAngleCamera` as the device type. That is not satisfiable on the hardware
the team has** -- the optics it fixes are unchanged, the device reaching them is not. **Amended
2026-09-02 by D-029** (CHANGES.log), which moves the device to `builtInDualWideCamera` and withdraws
D-014's claim that this path yields LiDAR depth.

The `distortion_table` above is truncated for readability. A real one is as long as the camera
delivers -- 42 entries on James's iPhone 17 Pro -- and is recorded verbatim, never resampled
or applied on device. `distortion_center` is deliberately separate from `cx`/`cy`: the table is
radial about that point, and substituting the principal point biases exactly the frame-edge
corrections the table exists to make.

Existing imported records carry the marketing-name value `device_model = "iPhone 17 Pro"`, while
new app captures carry the hardware identifier `iPhone18,1`. They name the same physical phone.
Analysis must normalize both to `iPhone18,1` before grouping; only then is the device field constant.

Three things this shape buys:

> **Amended 2026-09-02 by D-036.** No caliper is used, so there is no instrument reading to bind.
> What binds at the shutter is the entrance ID and the condition tags; ground truth for the
> screening study is James's retrospective **presence labels** (#302), entered with the workflow
> built by #168 and recorded from his original
> photos and recollection after dataset closeout. They need no instrument and are not part of an
> image upload. Capture
> runs on **one device** — James's iPhone 17 Pro (`iPhone18,1`) with LiDAR — so `device_model` is a
> constant rather than a stratification variable after applying D-040's alias normalization.

- **Capture identity binds at the shutter press.** The app records the entrance ID and condition
  tags with each capture. The separate label CSV joins by entrance ID; it does not rely on filename
  reconciliation and is not required for upload.
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

> **Amended 2026-09-02 by D-030: Arm C is cut**, and it was never implemented, so the gradient
> above loses its most-usable end. Deliverable #4's ablation runs over A and A′ only — Arm B is
> registered but not served by the live deployment (D-031). The "works with what you already
> carry" claim is left unevidenced, not disproved; §6 carries the wire-level consequence.

**Stage 3 — compliance reasoning.** Map measurement and interval to the ADA lines; emit pass, fail,
or abstain. The abstention rule's parameters are frozen in version control before the sealed run
(D-009, §7) — an unfrozen threshold is a dial fitted to the test set.

## 6. Server and the live demo

A single stateless endpoint on a small paid host (D-016; D-026 as amended by **D-031**, which authorises
the server host only — object storage stays on the free tier): `POST /measure` takes the image and sidecar,
calls the core library, returns per-arm measurement, interval, and decision.

It holds no state and owns no metrology. Its only job is to be reachable from James's iPhone 17 Pro on stage.

**Deployed at https://frontdoor-measure.fly.dev** (2026-09-02): Fly.io `shared-cpu-1x`, 256 MB, one
machine held always-on in `sjc` near the WNAM buckets. `GET /health` and `POST /measure` are live and
the response validates against the frozen contract. Plain HTTP redirects to TLS, which iOS App
Transport Security requires of the phone. Deploy steps, secrets, prepaid-credit procedure and the
pre-Demo-Day checks: [docs/server-deploy.md](docs/server-deploy.md).

**Live arms (TICK-062).** The image serves Arms A and A′ only, and carries no depth model or
weights — which is why it runs in 69 MiB and why the laptop fallback needs no download.

The live response still includes every arm key, with two **different** absences:

- **Arm B** — `{absent_reason: "unavailable"}`. This deployment does not serve it; another could.
  The offline harness still scores it.
- **Arm C** — `{absent_reason: "cut"}`. Dropped by **D-030** on 2026-09-02; no deployment will ever
  serve it. Reporting it as `unavailable` would promise a capability that no longer exists.

TICK-063 renders the two differently — a cut arm is expected, an unavailable one is about this
host — so a client can tell them apart, and both apart from "this capture failed".

**Run,** for local development. From the repo root:

```
docker build -t frontdoor-server .
docker run --rm -p 8080:8080 -e PORT=8080 frontdoor-server
```

> **Not for step 3 of the fallback chain below.** A local build is a *different image that came
> from the same source*, which is exactly what step 3 exists to rule out — the fallback is only a
> mitigation if it changes the network path and nothing else. The demo laptop must **pull** the
> deployed release and run that; `docs/server-deploy.md` has the commands, and
> `python -m frontdoor_server.deployment verify` checks the host, the laptop's cache and the
> committed record against each other.

Storage credentials are environment variables at run time (`data/STORAGE.md`). They are never
baked into the image. There are no depth-model weights to pin; the image does not carry any.

**Fallback chain**, in order, for a venue where presentations happen in an interior atrium:

1. cellular to the host
2. venue wifi to the host
3. the identical server image running on a team laptop, phone tethered to it
4. the pre-recorded measurement captured Sep 8

Steps 1–3 run the same container image, so a fallback changes the network path and nothing else.

## 7. Evaluation harness and the seal

The harness is the second entrypoint over the core library. It produces every number in the error
budget, and it is the component that enforces D-007 mechanically rather than by promise.

It does not run on the server VM. **D-035** put it on a team Mac: the host is sized for
`POST /measure`, not for scoring a few hundred captures through four arms, and the team already
has the machines. Object storage stays on R2; the Mac reads it over the network. It also keeps the
depth READ credential off the request path, which is what D-020 and D-033 are for — the harness is
the only reader of depth, and it should not live where the server lives.

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
unsealing run executes a script already exercised, not one written that morning. The freeze-day
procedure — pre-flight, the exact command, and what to do if it crashes — is
`docs/unsealing-run.md` (TICK-080).

**What the sealed split carries.** Headline MAE, classification accuracy and false-pass rate at the
1/2" line, and the pre-registered continuous error-versus-angle model (D-019). The remaining four
condition variables are reported from dev and labelled exploratory — with 12–18 sealed entrances,
a five-way stratification has per-cell counts of one or two and cannot support confirmatory claims.

Fitting a curve against a continuously measured angle is what makes one confirmatory stratified
result affordable at this sample size; a contingency table over five variables is not.

## 8. Data architecture

**Bytes in object storage, records in git** (D-018). Images and depth maps live in free-tier
object storage (D-026). Evaluation reads them from a team Mac (TICK-062), not from the server
host — the "bucket beside the VM" premise does not describe the system. The repository holds the manifest, labels, condition tags,
hashes, the seal audit log, and the frozen abstention parameters — everything needed to verify a
result, and nothing large enough to make the repo unusable.

A few hundred captures plus depth maps is low single-digit gigabytes, which is the wrong shape for
git and larger than the free LFS allowance in any case.

**Integrity.** Every image and depth map is hashed at capture. The harness verifies hashes on load,
so a corrupted or substituted file fails loudly rather than quietly changing a number.

**Retention.** The bucket is the system of record during the sprint. At results freeze the dataset
is published as a release artifact, satisfying deliverable #1.

**On-site publication (TICK-333).** The map's Scanned on-site tier is fed by `data/published_scans.jsonl`, a
committed record of one scan per non-sealed entrance: verdicts, confidences, the capture date from
the sidecar, and a place reference — never image bytes, so no capture is republished by this path.
`data/scan_matches.json` records, for every published entrance, which catalogue place it was
matched to and on what basis, or why it was left unmatched; an ambiguous or distant candidate is
left unmatched rather than guessed onto the wrong storefront. The eighteen sealed entrances are
absent from both by construction — `frontdoor.scan_publish` derives what it may assess from
`frontdoor.split` and has no override — and are published after results freeze as their own
change (`docs/unsealing-run.md`).

## 9. Depth quarantine (D-020, corrected by D-040)

Every app capture on James's iPhone 17 Pro enables AVFoundation depth delivery. The measured
configuration delivered relative stereo disparity; supported depth data is converted to
`DepthFloat32` before persistence. A frame with no depth-carried calibration is rejected for
missing intrinsics; a frame whose calibrated depth cannot be persisted may write `"depth": null`.
Imported photos also carry no depth (TICK-023).

> **Amended 2026-09-02 by D-034.** The sidecar carries a `capture_mode` — `metrology`,
> `screening` or `imported` — and each mode's required fields differ. A screening capture is
> forbidden from carrying a caliper reading, and an imported photo from carrying intrinsics,
> rather than merely permitted to omit them. An absent mode means metrology, so every sidecar
> written before that entry keeps its original contract. R-3's 3 m distance cap is metrology-only:
> the plain-photo protocol asks for a far, ~3-4 m shot.

> **Corrected 2026-09-04 by D-040 and D-045.** **D-032** puts depth capture on James's iPhone 17 Pro
> (`iPhone18,1`). Its completed probe shows that normal capture receives relative stereo disparity
> and persists relative `DepthFloat32`, not LiDAR range. **D-039 supersedes D-033's mechanism:** Cloudflare does
> not issue a permanent write-only R2 token. Uploads still pass through the server for validation,
> but depth is forwarded to a dedicated authenticated Worker with the R2 binding. Fly has no depth
> credential or read route; the harness keeps the only credential that can read depth.

Depth maps are stored in a **separate bucket** (D-026) that the image-only loader
credential cannot read. A prefix inside one bucket is not enough where the provider
scopes credentials per bucket. They are loaded only by the evaluation harness. The planned
monocular-versus-LiDAR comparison is unavailable because the stored depth is relative disparity
and no caliper reference exists. If depth sits where the method can reach
it, it is eventually used to tune, and the comparison stops meaning anything — the
same reasoning as the sealed split. Layout: `data/STORAGE.md`.

The phone's LiDAR hardware is not a ground-truth source for this dataset. The normal capture path
does not store LiDAR range, and D-036 removed the caliper reference. Deliverable #5 and R-10's
bench test are therefore not delivered in this window: the comparison has no subject.

## 10. Assumptions

- **A-1. REPLACED.** The supported hardware is exactly James's iPhone 17 Pro (`iPhone18,1`) with
  LiDAR. No generalisation to another phone is claimed. After D-040's alias normalization,
  `device_model` represents one physical phone in this dataset. See TEAM.md §2 and
  docs/tick-020-capability-probe.md.
- **A-2. Calibration-data delivery works on James's iPhone 17 Pro.** Its probe verified the
  4032×3024 main-lens path, intrinsics, distortion table, and relative stereo disparity (R-9).
- **A-3. REPLACED — one capture device.** R-8 has fired; its response rule is recorded in TEAM.md
  §4. James's iPhone 17 Pro shoots every entrance, and no hardware fallback is in scope.
- **A-4. The threshold rise presents a usable planar riser face.** Heavily bevelled or rounded
  thresholds are a documented failure class, as glass doors already are.

## 11. Architecture risks

| ID | Risk | Mitigation |
|----|------|------------|
| R-7 | App signing is on the critical path for the whole dataset; free-provisioning builds expire after 7 days, landing mid-capture | **Accepted, not mitigated by purchase** (D-025). Managed by a committed signing calendar with no gap through Sep 11, including a mandatory re-sign by Sep 6. James runs Windows and holds the only LiDAR device, so each of his installs is a scheduled physical session with a Mac owner |
| R-8 | One capture phone serialises field work and is a single point of failure | Cut the entrance target, not the protocol; keep James's iPhone 17 Pro signed and launch-tested; stop capture rather than switch hardware |
| R-9 | Calibration-data delivery unavailable on James's iPhone 17 Pro | Verified by the on-device probe; no hardware fallback is in scope |
| R-10 **(no longer testable — D-036)** | LiDAR is coarser than the 0.25" bar, so the "accuracy ceiling" sits below the success criterion | ~~Bench-test against the caliper in week one~~ — **no caliper is used (D-036), so there is nothing to bench-test against.** The risk is neither confirmed nor refuted; it is recorded as untested. |
| R-11 | Demo app and capture app drift apart, so Demo Day exhibits uncharacterised behaviour | Demo app is the capture app plus rendering; one capture path, one metrology library |
