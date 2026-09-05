# TEAM — roster, capture device and track coverage

Closes PRD §12 open item **O-1**. Records who is on the team and what capture hardware exists,
and fixes the response rule for **R-8** (one capture phone serialises the parallel field tracks).

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

## 2. Capture device

There is exactly one capture and demo phone: **James's iPhone 17 Pro (`iPhone18,1`) with LiDAR**
(D-032, D-036, D-045). It runs the iOS capture app and carries every entrance. No other handset is a
capture device, test device, fallback, standby, or part of the supported device pool.

The in-app capability probe measured this phone on 2026-09-04; see
[docs/tick-020-capability-probe.md](docs/tick-020-capability-probe.md). Through
`builtInDualWideCamera` at the main-lens switch-over factor it delivers a 4032×3024 still,
intrinsics, a 42-entry distortion table, and relative stereo disparity. Its
`builtInLiDARDepthCamera` delivers depth without calibration, so the app does not use that path for
normal capture. The measured `builtInDualWideCamera` configuration delivered relative stereo
disparity, which the app converts to `DepthFloat32` before persistence; the probe did not observe
LiDAR range, and D-015 still forbids the screening method from consuming device depth.

James runs Windows, so signing and installing the app requires James's phone to be physically
connected to a team Mac. Free-provisioning builds expire every seven days; the mandatory sessions
are recorded in [docs/signing-calendar.md](docs/signing-calendar.md). This is an accepted,
unmitigated single point of failure: if James's phone or its build is unavailable, capture stops.

## 3. Work division

PRD §9 runs four parallel tracks and every one is covered. The division below goes further than
TICK-003's "at least one person can cover each": it is the assignment the backlog now carries.
**Tickets are assigned, not self-assigned** — this supersedes the self-assign-and-rotate convention
from O-1, and every open issue names an owner in GitHub.

Work can still move between people. When it does, **reassign the ticket rather than clearing it**,
so no issue is ever left without a name against it.

A hardware constraint shapes it: **field capture and the live demo run only on James's iPhone 17
Pro (`iPhone18,1`) with LiDAR.** James carries field capture; Emily carries capture-app development
and uses a team Mac to sign and install builds on James's connected phone. There is no alternate
phone or operator path.

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

## 4. R-8 response rule — **FIRED**

The active capture pool contains one phone: James's iPhone 17 Pro with LiDAR. This is a deliberate
single-device protocol decision, not a fallback arrangement.

1. **Cut the entrance target, never the protocol.** Every entrance still follows the complete
   5–6-view plain-photo protocol with presence labels and the committed split discipline.
2. **The floor is 30 entrances.** Below that, per-condition cells are too small to interpret.
3. **Treat the phone as an unmitigated single point of failure.** Keep its free-provisioning build
   valid, launch-check it before leaving, and stop capture if it is unavailable. Do not switch
   hardware.

## 5. How this was verified

- James's iPhone 17 Pro model identifier was read from `devicectl` as `iPhone18,1`.
- The capability probe recorded its camera, intrinsics, distortion, and depth behavior.
- Roster and X handles were confirmed by each person.
- Track coverage was confirmed as coverage, not assignment.
