# TICK-090 — field capture protocol

James captures every entrance on his iPhone 17 Pro. This is the sole field protocol, so the result
is one consistent dataset. It is written for the doorstep — read the checklist at the bottom if
you only have thirty seconds.

Per the team's pivot (2026-09-01), frontdoor screens **visible feature presence** — ramp/bevel,
handrails, accessible door hardware, signage — from plain photos. This protocol produces no
measurements and makes no compliance determination. "Not visible in the photos" is never recorded
or treated as "absent." What this protocol has to guarantee is comparability: every entrance
produces the same view set, framed the same way, so the screening engine is looking at the same
kind of input no matter who captured it.

Validation note: this is TICK-090; it gets pilot-tested by TICK-092 (#66) before TICK-093 (#67)
scales up capture. Anything ambiguous in here gets fixed after the pilot, not guessed at now.

## The kit: one phone, and nothing else

**Every entrance in this dataset is shot on the same device** — James's iPhone 17 Pro
(`iPhone18,1`) with LiDAR (D-036). Not "a team phone", not whichever is to hand. One physical
device, so the findings can say plainly what hardware the result was measured on; analysis applies
D-040's alias normalization before grouping `device_model`.

**No caliper. No reference card. No tape measure.** There is no instrument reading to take at the
door: ground truth for this study is what James can establish from his original photos and
recollection, recorded retrospectively as presence labels after dataset closeout, not what anything
measured. These labels are separate from capture and upload. If you find yourself wanting to
measure a step, that is the earlier version of this project and it is not what we are collecting.

**Depth delivery is enabled automatically** and needs nothing from you. The measured configuration
delivered relative stereo data, which the app persists as `DepthFloat32` when supported. Capture
validation still requires intrinsics, and depth is never used to produce a verdict.

> If that phone will not launch the app, capture does not happen that day — nothing is shooting
> alongside it. That is why the launch check below is the first line of the checklist and not the
> last.

## Before you shoot: assign the entrance ID

Every entrance gets a canonical ID before you take a single photo: `E-` plus exactly three digits
(`E-014`, not `e14` or `E-14`). Assign and write it down — on the capture device, in the filename,
wherever your recording step is — before you start. Never reconstruct the ID afterward from memory
or photo order.

## Is this entrance even capturable?

Check before you spend time on it:

- Is there a public vantage point you can shoot from?
- Are the sightlines to the entrance actually open?
- Can you get people out of frame in a reasonable amount of time?

If the answer to any of these is no, this is a **skip**, not a problem to force your way through.
See "Skip and failure classes" below.

## The view set: all 6 photos, every completed entrance

1. **Head-on** — square to the entrance, doorway centered.
   [photo: to be added after the pilot — TICK-092]
2. **Oblique, left** — angled from the left, entrance still fully in frame.
   [photo: to be added after the pilot — TICK-092]
3. **Oblique, right** — angled from the right, entrance still fully in frame.
   [photo: to be added after the pilot — TICK-092]
4. **Near, ~1.5 m** — close enough that hardware and surface detail start to read.
   [photo: to be added after the pilot — TICK-092]
5. **Far, ~3-4 m** — far enough to show the full approach path leading up to the entrance.
   [photo: to be added after the pilot — TICK-092]
6. **Hardware close-up** — the door handle, lock, lever, or push plate, filling the frame.
   [photo: to be added after the pilot — TICK-092]

All six named views are the complete set. If one genuinely cannot be captured, record the entrance
as skipped with the reason; the phone does not enable **Finish capture** or labeling on five.

## Fixed geometry — the one thing that must never vary

- **1× main lens only.** No digital zoom.
- **No crop.** Not at capture, not afterward. What the sensor sees at 1× is what gets kept.

Everything else — angle, lighting, occlusion — is deliberately **not** controlled. Do not chase
"the good angle" or wait for better light. Realistic, uncontrolled capture is the condition this
product is built to be evaluated under. Consistency in geometry, variety in everything else.

## What must be in frame

Across the view set (not necessarily every single shot), the set as a whole must show:

- The full entrance
- The approach path leading up to it
- The door hardware, clearly, at least in the close-up
- **The ground at the threshold** — at least one view (the far view is the natural one) must show
  where the approach meets the doorway at ground level, with the base of the door frame and the
  surface in front of it in frame. Pilot finding (TICK-092): when no view covers the ground plane,
  the ramp/bevel and handrail criteria come back "not visible" or flip between "not visible" and
  "absent" across views — the engine is answering honestly about framing, not about the entrance.

## What to skip — and what gets reshot on the spot

- **No interiors.** Stop at the threshold. Don't shoot through an open door into the space beyond
  it.
- **Identifiable people: blur-first (TICK-257).** Ingest now detects faces and irreversibly
  blurs them automatically, so a face in a shot is a blur problem the pipeline handles, not a
  reshoot. Reshoot only when a person **physically occludes the entrance** — that is an occlusion
  problem, not a privacy one, and no amount of blurring puts the doorway back in frame. If the
  occlusion won't clear in a reasonable wait, treat the entrance as a skip (see below).
- **Verify the processed glass — never rely on the raw preview.** Storefront
  doors are mirrors: the pilot (TICK-092) lost 17 of 65 shots to identifiable faces, mostly *in
  the door glass* — reflections of passers-by, people inside seen through the pane, and the
  photographer's own reflection — none noticed at capture, which is exactly why a human check was
  never going to be the only fix. Ingest detects and irreversibly blurs faces (reflections and
  through-glass included), and the screening model audits its own input. A `face_visible` or
  `unknown` audit quarantines the image; only an explicit `clear` passes. Verify the processed
  output before retaining it, paying particular attention to glass. Never keep or send the raw
  original as a fallback when processing or verification fails.
  (Shooting from a slight angle still keeps your own reflection out of the shot, which is good
  craft, but it does not replace checking the processed output.)

## Record at capture — not from memory later

Two things get written down at the entrance, at the moment of capture, never reconstructed
afterward:

- **Entrance ID** (`E-NNN`)
- **Distance** to the entrance, in metres — roughly is fine, per shot
- **Lighting** — exactly one of: **direct sun**, **overcast**, **shade**, **low light**,
  **artificial**
- **Occlusion** — *how much* of the entrance is blocked, exactly one of: **none**, **partial**,
  **heavy**. A parked van across the doorway is heavy; a planter clipping one edge is partial.

These are the tags the app offers, and this list and the app's pickers are the same list on
purpose: a tag written here that the app cannot accept is a tag that gets silently changed at the
door. If what you see genuinely does not fit — a doorway lit by a shop window at dusk, say — pick
the closest and say what you actually saw in the entrance notes. The stratification needs one
vocabulary; the notes are where the honest detail goes.

**Surface** is not asked for on a screening capture. It is a metrology-mode field, and guessing at
it here would put a value in the record that nobody looked at.

### Imported photos (capture_mode "imported")

Photos taken outside the app and imported later (#31, D-034) are legitimate captures, but tags
that this protocol says to record *at the entrance* cannot be reconstructed afterward. Pilot
finding (TICK-092): the pilot set came off a camera roll, so per-shot distance did not exist and
was backfilled as a nominal 2.5 m. For imported captures: lighting and occlusion may be recorded
from the photos themselves (they are visible in them); **distance is recorded only if it was
actually noted in the field — otherwise it is entered as the nominal 2.5 m, and the entrance
notes must say the distance is nominal.** Depth is null on imported captures; that costs nothing
(TICK-023 AC5) but means the later depth comparison excludes them.

## You don't need permission — but don't make it a fight

Storefronts and their entrances are publicly observable from the sidewalk. You don't need anyone's
permission to photograph one.

If a shopkeeper objects anyway: explain briefly what this is (a photo survey of entrance
accessibility features — no measurements, nothing identifying published). If they still object
after that: **stop immediately, delete that entrance's photos on the spot, and record the entrance
as skipped (shopkeeper objection).** Don't argue it further. It's one entrance out of forty-plus.

## Skip and failure classes — record them, don't force past them

An entrance that can't be captured under this protocol is a **documented outcome**, not a failure
on your part. Record the entrance and the reason, using one of these classes (or add a short
free-text reason if none fits):

- No public vantage point
- Sightlines blocked
- People unavoidably in frame (can't clear in a reasonable wait)
- Shopkeeper objection
- Identifiable-person reshoot failed (couldn't get a clean retake)

Do not substitute a lesser view set, a worse angle, or a cropped shot to force a difficult entrance
into the dataset. A skipped entrance is honest data. A forced, non-compliant capture is not.

## Before you leave: launch the app on James's iPhone 17 Pro

Not "check the profile date" — **launch it**. Free-provisioning builds expire after seven days
(D-025, R-7), and a profile can also be invalidated for reasons that have nothing to do with expiry:
an Apple ID re-auth, a device re-pair, a Mac that has forgotten the certificate. Launching is the
only check that covers all of them, and the failure reads like a build error rather than an expiry.

If it does not launch, re-sign **before leaving**. A capture day lost to signing is a whole day of
entrances, and there are not many left. Schedule and steps: [signing-calendar.md](signing-calendar.md).

## Checklist — read this at the door

- [ ] **App launches on James's iPhone 17 Pro** — done before leaving, not at the entrance
- [ ] Entrance ID assigned (`E-NNN`), written down before shooting
- [ ] Vantage point, sightlines, and people situation checked — capturable, or logged as a skip
- [ ] All 6 views captured: head-on, both obliques, near (~1.5 m), far (~3-4 m), hardware close-up
- [ ] 1× lens, no zoom, no crop, on every shot
- [ ] Full entrance + approach path + hardware covered across the set
- [ ] No interiors; people occluding the entrance reshot; processed blur output verified,
      especially in glass (TICK-257)
- [ ] Condition tags (lighting, occlusion) recorded now, at the entrance
- [ ] Tap **Finish capture** after all six named views, then explicitly label all four presence
      criteria before viewing any screening result
- [ ] If skipped: entrance and reason recorded before moving on

## When an estimate can be trusted

When can a number from this door be believed, and past which angle or
distance should it not?

TICK-075 was going to answer that from the sealed split. It did not run —
there is no caliper (A-3, D-036). What follows is the predicted budget that
run would have been compared against (`docs/rise-error-budget.json`,
TICK-041). Status: **predicted before data; not an observed result**.
Full table: [findings.md](findings.md). Use `fx = 2807.7` (James's iPhone),
not the 2934.1 example.

**Arm A (paused).** Predicted error on a 0.5″ rise, δ = 5 px: at 2 m it stays
under 0.25″ through 30° and goes over by 45°; at 3 m it is already over
head-on. The JSON has no 2.5 m row. F-004's **2.5 m** cap is analytical-series
guidance for a measurement attempt, not a sealed result. The far screening
view (~3-4 m) is allowed to sit past that because screening does not measure
rise.

**Screening.** A presence call depends on the six-view set actually showing
the feature — including the ground at the threshold. If it does not, the
answer is **not visible**, never **absent**. Glass doors, heavily bevelled
or rounded thresholds, and occlusion in the ROI are documented failure
classes (see above), not reasons to skip a capturable entrance.
