# TICK-020 — calibration and depth delivery on team devices

**Status: probe built, awaiting hardware runs.** The decision this spike exists to take cannot be
recorded until the table below has a row per real device.

ASM-2 assumes AVFoundation delivers `AVCameraCalibrationData` — focal lengths, principal point and
the distortion table — alongside a full-resolution still, plus depth where the hardware has it.
R-9 is the risk that it does not. Everything downstream rests on the answer: Arm A′ needs
intrinsics to decompose the ground homography, and the error-versus-angle model needs the derived
plane pose.

## Why this needs measuring rather than reading

Calibration delivery is gated. Apple only offers it when depth or virtual-device constituent
delivery is enabled, so "the device supports it" and "the configuration D-014 fixes supports it"
are different questions. D-014 fixes capture to the **1× wide-angle lens, no digital zoom, no
crop**. If calibration is only available on a dual-camera virtual device, that is a direct conflict
with the capture geometry, and it is better found now than on day six.

The probe therefore reports three lens configurations, not one.

## Running it

Install the app on a device, tap **Run capability probe** on the home screen, then **Copy result**
and paste the block into the table below. The simulator reports every lens unavailable and fails
the capture — that result is expected and proves nothing, which is the point of recording device
model alongside every row.

## Results

Run 2026-09-02 on both phones. **The 1× lens the probe originally asked about answers "no" on
both — and that is not the whole answer.** See the second table.

| Device | Model ID | iOS | 1× calibration | 1× depth | Requested / delivered pixels | Full res? | Distortion table |
|--------|----------|-----|----------------|----------|------------------------------|-----------|------------------|
| Emily — iPhone 16 | `iPhone17,3` | 26.6.1 | **no** | **no** | 8064×6048 / 4032×3024 | no | none |
| iPhone 15 Pro Max | `iPhone16,2` | 26.6.1 | **no** | **no** | 8064×6048 / 4032×3024 | no | none |

James's phone is still unmeasured. It is an **iPhone 17 Pro** (`iPhone18,1`), not the iPhone 16 Pro
the team audit recorded, and a build was installed and launched on it on 2026-09-02 -- so the only
thing standing between it and a row here is running the probe. Both phones tested so far agree, so
the expectation is
that it agrees too — but it is an expectation, not a row.

### The row that matters: `builtInDualWideCamera`

| Device | calibration | depth | zoom for the 1× main lens | Delivered pixels | Intrinsics | Distortion table |
|--------|-------------|-------|---------------------------|------------------|------------|------------------|
| iPhone 15 Pro Max | **yes**, via `depthData.cameraCalibrationData` | yes (`accuracy=relative`) | **2.00** | 4032×3024 | `fx=2792.0 fy=2792.0 cx=2037.2 cy=1499.0`, reference 4032×3024 | 42 entries |
| Emily — iPhone 16 | **yes**, same channel | yes | 2.00 | 4032×3024 | delivered | delivered |

`builtInLiDARDepthCamera` on the Pro Max: depth **yes**, calibration **no**, intrinsics not
delivered. LiDAR is not a route to intrinsics on this hardware.

**Both phones can capture measurable frames. Neither can do it through the device type D-014
names.**

### What follows

1. **D-014's device type is unsatisfiable; its optics are fine.** A device with no depth stream has
   no route to intrinsics — direct delivery needs two constituent devices
   (`AVCapturePhotoOutput.h:1496`), which one physical lens cannot offer. `builtInDualWideCamera`
   is ultra-wide + wide, and at its switch-over factor the main lens is exposing: `fx=2792` on a
   4032-wide frame against ~2688 predicted for a 24 mm-equivalent main lens and ~1456 for the
   ultra-wide. **ARCHITECTURE §4 and D-014 name the wrong device type and need amending** — a team
   decision, not a quiet code change.

2. **"1×" is a device-dependent number.** On a virtual device the zoom scale is relative to its
   *widest* constituent, so `videoZoomFactor = 1.0` selects the **ultra-wide** and the main lens
   sits at the first switch-over factor — 2.00 on both phones. Pinning the literal 1.0 would have
   captured ~120° of barrel-distorted glass while every check reported "1×". The app reads
   `virtualDeviceSwitchOverVideoZoomFactors` and refuses 1.0 there as the wrong lens.

3. **The dual-wide's depth is `accuracy=relative`, not metric,** and on the iPhone 16 it is stereo
   disparity rather than LiDAR. Arms B and C were meant to lean on metric depth. Arm A is
   unaffected: it takes scale from the reference card.

   > **Correction, 2026-09-02 (TICK-020, #24).** "Arms B and C were meant to lean on metric depth"
   > is wrong, and it points at the wrong arms. ARCHITECTURE.md §5 defines **both** B and C as
   > *learned monocular* depth estimated from the image, and **D-015** forbids the method consuming
   > device depth at all — so device depth being relative cannot affect them. Arm C has since been
   > **cut** outright (D-030). What relative depth does touch is everything that treats device depth
   > as a *measurement*: **D-020**'s monocular-versus-LiDAR comparison, **deliverable #5**, and
   > **R-10**'s planned bench test against the caliper. None of those are resolved. The full
   > analysis is in `TEAM.md`; this note exists so the claim is not read as current.

4. **No device delivers its sensor maximum.** Both requested 8064×6048 and were handed 4032×3024 —
   a binned readout, full field of view, one binning step down. TICK-022 AC3's literal wording is
   unsatisfiable on a 48 MP iPhone; the check now compares aspect (which catches a crop) and
   requires at least one binning step.

5. **Capture works on both phones, not one.** ASM-3 and TEAM.md §4's single-device risk are
   relieved. Frames are 4032×3024, so the Arm A error derivation should be re-checked against that
   grid rather than 8064×6048.

Simulator, for contrast — every lens unavailable, capture fails with "no rear wide-angle camera":

```
Frontdoor capability probe (TICK-020)
device: x86_64  iOS 17.0.1

Lens configurations:
  builtInWideAngleCamera (1x, the D-014 path): available=false calibration=false depth=false maxPhoto=-
  builtInDualWideCamera: available=false calibration=false depth=false maxPhoto=-
  builtInLiDARDepthCamera: available=false calibration=false depth=false maxPhoto=-

FAILED: no rear wide-angle camera (expected on a simulator)
```

## The decision, once the rows are filled

Per the ticket, one of:

- **Proceed on AVFoundation** — calibration is delivered on the 1× path on both capture phones.
  Record it in `CHANGES.log` and close this spike.
- **Fall back to ARKit** — record the resolution cost from ARCHITECTURE §2 explicitly, acknowledge
  the error-budget consequence (the budget is counted in pixels across the rise, and ARKit's video
  frames are roughly half the width, so localisation error roughly doubles), file the follow-up
  tickets, and update TICK-021's approach.

A third outcome is possible and worth naming in advance: calibration available on a dual-camera
configuration but **not** on the 1× path D-014 fixes. That is neither of the options above — it is
a conflict between D-014 and ASM-2, and it would need a decision about capture geometry rather
than about frameworks.

Timebox is 4 hours. At the limit, the best available answer is recorded and the decision taken.

## Reading the output

The report separates **requested** from **delivered** deliberately. `calibration requested=false`
means this device could not offer it in that configuration; `requested=true delivered=false` means
it offered and then did not produce it, which is a different and more alarming finding. The same
split applies to depth, and `full-resolution=false` means the delivered still was smaller than the
active format's maximum — which is the comparison AC-3 exists to make.

## Known limitation of this probe

It answers availability, not correctness. A delivered intrinsic matrix that is subtly wrong would
pass every check here. Confirming the numbers are right is TICK-207's job, against caliper truth.

**An earlier revision could not have found the answer at all.** It captured only on
`builtInWideAngleCamera` — the one device type that reports `depth=false`, and therefore the one
that can never carry `depthData.cameraCalibrationData`. It reported "no calibration" on two phones
while proving nothing, because it was asking the only camera structurally incapable of saying yes.
It now captures once on every available back-camera device type and prints a verdict naming those
that delivered. Worth remembering as a shape of mistake: a probe that cannot observe the positive
case reads exactly like evidence of absence.
