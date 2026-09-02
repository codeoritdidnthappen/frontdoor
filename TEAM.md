# TEAM — roster, capture devices and track coverage

Closes PRD §12 open item **O-1**. Records who is on the team and what capture hardware exists,
and fixes the response rule for **R-8** (fewer capture devices than the parallel field tracks
assume).

This note records *facts and one decision*, and names the **work division** the backlog is
assigned from. It supersedes the earlier self-assign-and-rotate convention recorded in O-1:
**tickets are assigned, not self-assigned.** Every open issue names an owner.

Sources: [PRD.md](PRD.md) §9, §11, §12 · [ARCHITECTURE.md](ARCHITECTURE.md) §10 (A-1, A-3), §11 (R-8) ·
[CHANGES.log](CHANGES.log) D-002, D-010, D-013.
Ticket: TICK-003 (#15).

## 1. Roster

Team size is confirmed at four (D-010). Recorded by first name plus X handle; full legal names are
deliberately not published to this public repo.

| # | Name | GitHub | X handle | Carries |
|---|------|--------|----------|---------|
| 1 | David | `codeoritdidnthappen` | @codehappened | Metrology (all four arms), confirmatory metrics, charts |
| 2 | James | `james-merithew` | @JamesMerithew | Field capture, then demo and deck |
| 3 | Emily | `wliang002` | @EmilyLiangwx | Capture app, client-side contract |
| 4 | Ruben | `rubanikov` | @rubanikov | Data integrity, seal enforcement, server deploy |

Track detail in §3. All four handles are recorded, since PRD §11 grades build-in-public per
person and #82 has to check four accounts against the floors.

Every member needs an X account recorded: build-in-public is graded **per person**, not per
project (PRD §11) — four accounts, not one.

## 2. Capture devices

A-1 assumes capture devices are LiDAR-capable iPhones; A-3 assumes at least three are available.
**Both assumptions are false.** The capture app is iOS-only — AVFoundation photo capture plus
CoreMotion device motion, no ARKit (D-014, ARCHITECTURE.md §4) — so an Android device cannot run
it at all, with or without a depth sensor.

Measured 2026-09-02 with the in-app capability probe (TICK-020, #24); see
[docs/tick-020-capability-probe.md](docs/tick-020-capability-probe.md).

| Holder | Device | Runs the capture app | Delivers intrinsics | Depth | Consequence |
|--------|--------|----------------------|---------------------|-------|-------------|
| David | Samsung Galaxy S25 | **No** — Android | — | — | Cannot capture |
| Emily | iPhone 16 (non-Pro) | Yes | **Yes**, verified | Relative (stereo) | **Full capture** |
| Emily *(unconfirmed — see §5)* | iPhone 15 Pro Max | Yes | **Yes**, verified | Relative | **Full capture** |
| James | iPhone 16 Pro | Yes — a build has run on it (confirmed 2026-09-02) | Expected, **not yet probed** | **LiDAR — the depth device (D-032)** | **Carries LiDAR capture.** Run the capability probe on it to record its row |
| Ruben | Google Pixel 9 | **No** — Android | — | — | Cannot capture |

Three things the probe changed. **Intrinsics arrive on both tested phones, including the non-Pro**,
which the row above used to deny — but only through `builtInDualWideCamera`, never through the
`builtInWideAngleCamera` that D-014 names. **LiDAR delivers depth with no calibration at all**, so
it is not a route to intrinsics on any device. And **the depth that does arrive is
`accuracy=relative`** rather than metric range. The probe records the stereo-disparity
reading for the iPhone 16 specifically; the 15 Pro Max is recorded as relative without the
disparity detail, so "stereo on both" would say more than was measured.

James's iPhone 16 Pro **has had a build run on it** (confirmed 2026-09-02), but it has not been
through the capability probe, so it has no measured row above. D-032 makes it the depth device, so
that probe run is what is outstanding — not an install.

### Development machines

| Holder | Machine | Can build the iOS app | Has an iPhone to test on |
|--------|---------|-----------------------|--------------------------|
| David | Mac | Yes | No |
| James | **Windows** | **No** | Yes — the only LiDAR device |
| Emily | Mac | Yes | Yes |
| Ruben | Mac | Yes | No |

Xcode is macOS-only, so James cannot build the capture app, and cannot install a build onto his own
phone unaided — that requires a Mac with the device physically connected, or a paid-account
distribution channel (TICK-001, #13).

**Emily is the only person with both a Mac and an iPhone**, and therefore the only one who can
develop and test the capture app without borrowing hardware.

**The LiDAR capture path (#27) is not what it was assumed to be.** TICK-020 found that
`builtInLiDARDepthCamera` delivers a depth map with **no calibration data**, so a LiDAR frame
carries no intrinsics to interpret it with. Both tested phones instead get depth through the
dual-wide, at `accuracy=relative`.

This does **not** touch Arms B and C. Both consume *learned monocular* depth estimated from the
image (ARCHITECTURE.md §5), and D-015 forbids the method consuming device depth at all — so device
depth being relative cannot affect them. What it does touch is everything that treats device depth
as a **measurement**:

- **D-020**, whose premise is a monocular-versus-LiDAR comparison. A relative map has no metric
  scale to compare against a caliper, so the comparison as specified does not have a subject.
- **Deliverable #5**, "comparison against LiDAR on every entrance", which inherits that.
- **R-10**, which planned to bench-test device depth against the caliper. There is no longer a
  device-depth quantity in inches to test.

None of that is resolved here. It is recorded so the next person does not re-derive it.

Free-provisioning builds still expire every seven days (R-7), which is what TICK-001 (#13)
schedules; see [docs/signing-calendar.md](docs/signing-calendar.md).

- **Verified capture devices: 2**, both Emily's (iPhone 16, iPhone 15 Pro Max) — against A-3's
  assumed three. James's iPhone 16 Pro runs a build but has not been probed, so it is not counted
  as verified until it has a measured row.
- **LiDAR-capable devices: 1** (James's, untested). LiDAR is not a route to intrinsics on any
  device, so it does not gate capture the way A-1 assumed — but **D-032 (2026-09-02) puts depth
  capture on this phone**, so the count now gates *depth*: one unprobed device carries all of it.
  A build runs on it; what is missing is its measured probe row.

All five devices are now recorded. The two verified capture phones are an **iPhone 16 and an
iPhone 15 Pro Max** — two generations and two camera tiers, not the single generation an earlier
draft of this section claimed.

A-1 states that evidence comes from Pro-class cameras, with generalisation to other phones recorded
as a limitation rather than a result. That no longer holds: the pool is an iPhone 16 (non-Pro) and
an iPhone 15 Pro Max — **both a tier and a generation apart**.

The spread is wider than A-1 assumed but still bounded. The Pro adds a telephoto and the LiDAR
scanner, and under the fixed capture rule of **1× main lens, no digital zoom, no crop**
(ARCHITECTURE.md §4) neither enters the dataset; both shoot a 48MP main wide. Intrinsics differ per
device and per unit anyway, and the sidecar records `device_model` on every capture, so device stays
a variable the error analysis can see — with two devices, it is a variable with two levels rather
than a constant. A-1 needs restating to cover both, and that restatement is not in this document.

**Calibration-data delivery is now verified on two phones** (A-2, R-9). TICK-020 (#24) ran on
2026-09-02: both the iPhone 16 and the iPhone 15 Pro Max deliver intrinsics, a distortion table and
depth through `builtInDualWideCamera`, and neither delivers anything through the bare 1× wide
camera that D-014 names. The capture pool is two devices, not one, and the risk this paragraph
described did not materialise — R-9 fired on the *device type*, not on the phones.

## 3. Work division

PRD §9 runs four parallel tracks and every one is covered. The division below goes further than
TICK-003's "at least one person can cover each": it is the assignment the backlog now carries.
**Tickets are assigned, not self-assigned** — this supersedes the self-assign-and-rotate convention
from O-1, and every open issue names an owner in GitHub.

Work can still move between people. When it does, **reassign the ticket rather than clearing it**,
so no issue is ever left without a name against it.

Two constraints shape it, both from §2:

- **Field capture runs on Emily's two phones, not James's.** This constraint used to read "James
  holds the only LiDAR device, so every entrance must pass through his phone". TICK-020 retired it:
  LiDAR is not a route to intrinsics, both verified capture devices are Emily's, and James's iPhone
  16 Pro had not been probed. James still runs Windows and cannot build iOS.

  > **Reopened 2026-09-02 by D-032.** Depth capture is now assigned to James's iPhone 16 Pro, so
  > entrances carrying LiDAR do pass through his phone after all. A build has run on that phone, so
  > the install is not the open item — the capability probe is, and so is the 7-day re-sign, which
  > James cannot do unaided on Windows. Who operates which device is still unsettled.

  **This has a consequence §3 does not yet resolve.** Field capture (#9, #64–#69) is assigned to
  James, and the phones that can capture belong to Emily. Either the devices move to the operator,
  or the operator changes, or Emily carries capture on top of the capture app. Whoever decides that
  should also revisit "he carries little else until capture closes", which was reasoning built on
  the constraint that no longer holds.
- **Emily is the only person with both a Mac and an iPhone**, so the capture app is hers.

A third rule applies throughout: **nobody verifies their own work.** Every `qa` ticket is held by
someone who did not build the thing under test.

The division below is implemented as GitHub assignees across all 93 open issues: David 29,
Ruben 26, Emily 20, James 18.

| Track | Holder | Tickets |
|-------|--------|---------|
| Field capture | **James** | #9, #64-#69 |
| Capture app | **Emily** | #4, #24-#33, #51 |
| Metrology, all four arms | **David** | #5, #34-#47 |
| Data and dataset integrity | **Ruben** | #8, #18-#23 |
| Eval and seal enforcement | **Ruben** | #7, #53-#55, #62, #63 |
| Reported metrics | **David** (#56-#58), **Ruben** (#59-#61) | |
| Server and deploy | **Ruben** (#49, #50, #52), **Emily** (#6, #48) | |
| Findings, charts, notebook | **David** (#70, #72), **Ruben** (#71) | |
| Demo, deck, showcase | **James** | #10, #73-#75 |
| Build-in-public | **all four post individually**; coordination: James (#76, #77), David (#78, #79), Ruben (#80), Emily (#11, #81, #82) | |
| Logistics | Emily (#13), James (#14, #16), David (#12, #15), Ruben (#17) | |

**Independent verification.** QA holders, none of whom built what they check:

| QA ticket | Verifies work by | Held by |
|-----------|------------------|---------|
| #83, #85 | Emily (capture app) | James |
| #94 | Ruben, Emily (server, rendering) | James |
| #84, #86, #87, #88, #96 | Ruben (data, seal) | David |
| #90, #91, #92, #95 | David (metrology, notebook) | Ruben |
| #89, #93 | David and Ruben (library, metrics) | Emily |

**Phasing.** Aug 31 - Sep 5 James is in the field effectively full time; his deck and QA tickets sit
after capture closes. Emily's capture-app work is front-loaded, since nothing can be captured until
it ships (D-014).

## 4. R-8 response rule — **FIRED, on a trigger that has since been re-read**

The trigger condition was met as written: fewer than three LiDAR-capable iPhones are available.
There is one, and it is untested.

**What TICK-020 changed (2026-09-02).** LiDAR turned out not to be the thing that gates capture —
it delivers no calibration data, so it is not a route to intrinsics on any device. What actually
gates capture is *devices that deliver intrinsics*, and there are two verified, both Emily's. So the
rule stays fired on A-3's count of capture devices, and stops being fired on A-1's LiDAR premise.
The response below is unchanged, because it cuts the entrance target and that argument does not
depend on which capability was scarce.

The response is a **schedule change, not an architecture change** (ARCHITECTURE.md §10, A-3):

1. **Cut the entrance target, never the protocol.** Per-entrance shot list, ROI taps, caliper
   ground truth and split-at-capture stay exactly as specified.
   *Superseded in part by the 2026-09-01 pivot to plain-photo screening (#67, #9 thread), recorded
   in CHANGES.log: capture is plain photos, with no caliper, no ROI taps and no LiDAR depth, and the
   per-entrance plan is now #64's 5–6-view protocol. Split-at-capture survives. The clause is kept
   because "cut the target, not the protocol" still holds — it is the protocol underneath it that
   changed.*
2. **The floor is 30 entrances.** Below that, per-condition cells are too small to interpret,
   which is the whole reason the target was cut to 40-60 in the first place (D-002).
3. **Arm A′ captures are dropped before entrances are.** A′ is the realistic-user path in the
   usability gradient (D-013); losing it costs one arm of the ablation, whereas losing entrances
   costs the error budget its resolution.
   *Overtaken by the same pivot: the A′ ground-card subset is retired and #68 is closed, so there is
   no longer an A′ capture to drop first. What this clause protected — entrance count over arm
   count — has no remaining lever.*

### Open conflict this rule does not resolve

R-8 anticipated *fewer devices than tracks*. The actual constraint is tighter, and cutting the
entrance target does not clear it:

**RETIRED 2026-09-02 by TICK-020 (#24).** The paragraph below was written when LiDAR was believed
to be both available on one device and necessary on every entrance. The probe found LiDAR delivers
no calibration data at all, so it is not a route to intrinsics; depth arrives through the dual-wide
on both verified phones, and both of those are Emily's. Capture is no longer serialised onto one
device. Kept as the record of what was believed, not as a live constraint — and D-020's own premise
is now open (see §2).

~~**D-020 requires LiDAR on every entrance, and exactly one device can produce it.** Every entrance
must therefore pass through James's phone, which serialises field capture onto one device and one
operator regardless of how far the target is cut. Emily's iPhone can capture a conforming record
in every respect except depth.

Resolving this means either relaxing D-020 to a matched LiDAR subset — reverting to the pre-D-020
position in PRD §6, which changes what deliverable #5 can claim — or accepting a single-device
capture pipeline. **Both are protocol decisions and out of scope for this ticket**, which cuts
targets rather than rewriting the protocol. Escalated, not decided here.~~

## 5. How this was verified

- Device list: confirmed by someone physically holding each phone and reading its model from
  Settings, not from memory — for the four devices in the original roster.
  **The iPhone 15 Pro Max is the exception.** TICK-020's probe records it as `iPhone16,2` but its
  row carries no holder, unlike the iPhone 16 row which reads "Emily — iPhone 16". Its owner is
  asserted here and nowhere else. Since it is one of only two verified capture devices, whoever
  holds it should confirm, and the probe row should gain a name.
- Roster and X handles: confirmed by each person.
- Track coverage: confirmed as coverage, not assignment.
