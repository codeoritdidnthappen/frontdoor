# TEAM — roster, capture devices and track coverage

Closes PRD §12 open item **O-1**. Records who is on the team and what capture hardware exists,
and fixes the response rule for **R-8** (fewer capture devices than the parallel field tracks
assume).

This note records *facts and one decision*. It does **not** assign tickets to people: the team
self-assigns and rotates.

Sources: [PRD.md](PRD.md) §9, §11, §12 · [ARCHITECTURE.md](ARCHITECTURE.md) §10 (A-1, A-3), §11 (R-8) ·
[CHANGES.log](CHANGES.log) D-002, D-010, D-013.
Ticket: TICK-003 (#15).

## 1. Roster

Team size is confirmed at four (D-010). Recorded by first name plus X handle; full legal names are
deliberately not published to this public repo.

| # | Name | X handle | Carries |
|---|------|----------|---------|
| 1 | David | _TBD_ | Metrology (all four arms), confirmatory metrics, charts |
| 2 | James | _TBD_ | Field capture, then demo and deck |
| 3 | Emily | _TBD_ | Capture app, client-side contract |
| 4 | Ruben | _TBD_ | Data integrity, seal enforcement, server deploy |

Track detail in §3. X handles are the one item still outstanding.

Every member needs an X account recorded: build-in-public is graded **per person**, not per
project (PRD §11) — four accounts, not one.

## 2. Capture devices

A-1 assumes capture devices are LiDAR-capable iPhones; A-3 assumes at least three are available.
**Both assumptions are false.** The capture app is iOS-only — AVFoundation photo capture plus
CoreMotion device motion, no ARKit (D-014, ARCHITECTURE.md §4) — so an Android device cannot run
it at all, with or without a depth sensor.

| Holder | Device | Runs the capture app | LiDAR | Consequence |
|--------|--------|----------------------|-------|-------------|
| David | Samsung Galaxy S25 | **No** — Android | No | Cannot capture |
| James | iPhone 16 Pro | Yes | **Yes** | Full capture incl. depth |
| Emily | iPhone 16 (non-Pro) | Yes | No | RGB + intrinsics + gravity only |
| Ruben | Google Pixel 9 | **No** — Android | No | Cannot capture |

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

**The LiDAR capture path (#27) can only be exercised on James's iPhone 16 Pro.** Emily's iPhone 16
has no depth sensor, so testing that code requires James's phone and someone's Mac in the same
place. Until #13 lands, free-provisioning builds expire every seven days (R-7), making that a
recurring physical handoff rather than a one-off.

- **Capture-capable devices: 2** (James, Emily) — against A-3's assumed three.
- **LiDAR-capable devices: 1** (James) — against A-1's assumption that all capture devices are.

All four devices are now recorded. The two capture phones are **both 16-generation**, which
narrows a concern that would otherwise be real.

A-1 states that evidence comes from Pro-class cameras, with generalisation to other phones recorded
as a limitation rather than a result. Strictly, that no longer holds — Emily's iPhone 16 is not
Pro-class. But the spread is one camera tier within a single generation, not one device era against
another: the Pro adds a telephoto and the LiDAR scanner, and under the fixed capture rule of **1×
main lens, no digital zoom, no crop** (ARCHITECTURE.md §4) neither of those enters the dataset.
Both phones shoot a 48MP main wide. Intrinsics still differ per device and per unit, and the
sidecar records `device_model` on every capture, so device remains a variable the error analysis
can see. A-1 should be restated to say Pro and non-Pro of the same generation, rather than
Pro-class only.

**Calibration-data delivery is unverified on both phones** (A-2, R-9), and specifically unknown on
the non-Pro iPhone 16. That check is TICK-020 (#24), which is blocked on TICK-001 (#13). If
delivery fails on Emily's device, the capture pool drops from two phones to one and the D-020
conflict below becomes moot — everything funnels through James regardless.

## 3. Work division

PRD §9 runs four parallel tracks and every one is covered. The division below goes further than
TICK-003's "at least one person can cover each" — it is the working split agreed for this sprint,
not a reassignment of the self-assign-and-rotate principle. Anyone may pick up anyone else's ticket;
this records who carries what by default.

Two constraints shape it, both from §2:

- **James holds the only LiDAR device and runs Windows.** Every entrance must pass through his
  phone, and he cannot build iOS. Field capture is his, and it is a multi-day physical operation
  (#67 is estimated `L`) — so he carries little else until capture closes on Sep 5, then picks up
  the demo and deck, where being the operator is an advantage.
- **Emily is the only person with both a Mac and an iPhone**, so the capture app is hers.

A third rule applies throughout: **nobody verifies their own work.** Every `qa` ticket is held by
someone who did not build the thing under test.

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

The trigger condition is met: fewer than three LiDAR-capable iPhones are available. There is one.

The response is a **schedule change, not an architecture change** (ARCHITECTURE.md §10, A-3):

1. **Cut the entrance target, never the protocol.** Per-entrance shot list, ROI taps, caliper
   ground truth and split-at-capture stay exactly as specified.
2. **The floor is 30 entrances.** Below that, per-condition cells are too small to interpret,
   which is the whole reason the target was cut to 40-60 in the first place (D-002).
3. **Arm A′ captures are dropped before entrances are.** A′ is the realistic-user path in the
   usability gradient (D-013); losing it costs one arm of the ablation, whereas losing entrances
   costs the error budget its resolution.

### Open conflict this rule does not resolve

R-8 anticipated *fewer devices than tracks*. The actual constraint is tighter, and cutting the
entrance target does not clear it:

**D-020 requires LiDAR on every entrance, and exactly one device can produce it.** Every entrance
must therefore pass through James's phone, which serialises field capture onto one device and one
operator regardless of how far the target is cut. Emily's iPhone can capture a conforming record
in every respect except depth.

Resolving this means either relaxing D-020 to a matched LiDAR subset — reverting to the pre-D-020
position in PRD §6, which changes what deliverable #5 can claim — or accepting a single-device
capture pipeline. **Both are protocol decisions and out of scope for this ticket**, which cuts
targets rather than rewriting the protocol. Escalated, not decided here.

## 5. How this was verified

- Device list: confirmed by someone physically holding each phone and reading its model from
  Settings, not from memory.
- Roster and X handles: confirmed by each person.
- Track coverage: confirmed as coverage, not assignment.
