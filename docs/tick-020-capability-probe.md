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

| Device | Model ID | iOS | 1× calibration | 1× depth | Requested / delivered pixels | Full res? | Distortion table |
|--------|----------|-----|----------------|----------|------------------------------|-----------|------------------|
| Emily — iPhone 16 | `iPhone17,3` | 26.6.1 | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ |
| James — iPhone 16 Pro | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ |

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
