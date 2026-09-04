# TICK-020 — calibration and depth delivery on James's iPhone

**Status: complete.** James's iPhone 17 Pro (`iPhone18,1`) with LiDAR is the only capture and demo
phone. The capability probe ran on it on 2026-09-04 and recorded the configuration the app uses.

## Why this needed measuring

Calibration delivery is gated. Apple offers it only when depth or virtual-device constituent
delivery is enabled, so “the phone supports it” and “the chosen capture configuration supports it”
are different claims. D-014 fixes the optics to the 1× main lens with no digital zoom or crop; the
probe therefore checked every relevant back-camera device type on the actual phone.

## Running it

Install the app on James's iPhone 17 Pro, tap **Run capability probe** on the home screen, then
**Copy result**. A simulator reports every lens unavailable and cannot provide hardware evidence.

## Results — 2026-09-04

| Phone | Model ID | iOS | Requested / delivered pixels | Full sensor maximum? |
|---|---|---|---|---|
| James's iPhone 17 Pro | `iPhone18,1` | 26.6 | 8064×6048 / 4032×3024 | no — one binned readout |

| Camera device | Calibration | Depth | Main-lens zoom | Intrinsics | Distortion table |
|---|---|---|---|---|---|
| `builtInWideAngleCamera` | no | no | 1.00 | none | none |
| `builtInDualWideCamera` | **yes** | yes — `hdis`, `accuracy=relative` | **2.00** | `fx=2807.7 fy=2807.7 cx=2006.4 cy=1503.2`, reference 4032×3024 | 42 entries |
| `builtInLiDARDepthCamera` | no | yes | n/a | none | none |

The app captures through `builtInDualWideCamera` because it is the only path on this phone that
delivers the intrinsics required by `CaptureValidation.record`. At the first virtual-device
switch-over factor, 2.00 selects the 1× main lens; 1.00 would select the ultra-wide.

The delivered depth is `kCVPixelFormatType_DisparityFloat16` with
`AVDepthData.Accuracy.relative`: relative stereo disparity, not metric LiDAR range. The dedicated
LiDAR camera delivers depth but no calibration, so choosing it would discard the intrinsics the
capture contract requires. This does not affect the screening study because D-020 quarantines
depth and the method never consumes it.

## Decisions supported by the result

1. Use `builtInDualWideCamera` at its main-lens switch-over factor (D-029).
2. Record 4032×3024 as the delivered full-field frame; do not require the sensor maximum.
3. Record depth for later work, but do not describe it as metric or use it in screening.
4. Normalize the phone's marketing-name and hardware-identifier aliases to `iPhone18,1` before
   grouping; it is the sole capture, test, and demo phone.

## Reading the output

The report separates **requested** from **delivered**. `calibration requested=false` means the
camera device could not offer it; `requested=true delivered=false` means it offered calibration
but did not produce it. `full-resolution=false` means the delivered still is smaller than the
active format's maximum, while the aspect-ratio check still detects a crop.

## Known limitation

The probe proves availability, not intrinsic-matrix accuracy. The hardware claim is limited to
James's measured iPhone 17 Pro.
