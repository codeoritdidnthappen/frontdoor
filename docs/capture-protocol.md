# TICK-090 — field capture protocol

Four people are capturing 40-60 entrances over a few days. This is the one protocol all four
follow, so the result is one dataset instead of four. It is written for the doorstep, on a phone —
read the checklist at the bottom if you only have thirty seconds.

Per the team's pivot (2026-09-01), frontdoor screens **visible feature presence** — ramp/bevel,
handrails, accessible door hardware, signage — from plain photos. This protocol produces no
measurements and makes no compliance determination. "Not visible in the photos" is never recorded
or treated as "absent." What this protocol has to guarantee is comparability: every entrance
produces the same view set, framed the same way, so the screening engine is looking at the same
kind of input no matter who captured it.

Validation note: this is TICK-090; it gets pilot-tested by TICK-092 (#66) before TICK-093 (#67)
scales up capture. Anything ambiguous in here gets fixed after the pilot, not guessed at now.

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

## The view set: 5-6 photos, every entrance, no exceptions

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

Six views is the target; five is acceptable if one genuinely cannot be captured (say, an
obstruction that only affects one angle) — note which one and why in the entrance record.

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

## What to skip — and what gets reshot on the spot

- **No interiors.** Stop at the threshold. Don't shoot through an open door into the space beyond
  it.
- **No identifiable people.** If a person is identifiable in a shot — face visible, recognizable —
  that shot is retaken immediately. It is never kept "just in case" and never fixed later. If you
  can't get a clean retake in a reasonable wait, treat the entrance as a skip (see below).

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

## Before you leave: launch the app on every device going out

Not "check the profile date" — **launch it**. Free-provisioning builds expire after seven days
(D-025, R-7), and a profile can also be invalidated for reasons that have nothing to do with expiry:
an Apple ID re-auth, a device re-pair, a Mac that has forgotten the certificate. Launching is the
only check that covers all of them, and the failure reads like a build error rather than an expiry.

If it does not launch, re-sign **before leaving**. A capture day lost to signing is a whole day of
entrances, and there are not many left. Schedule and steps: [signing-calendar.md](signing-calendar.md).

## Checklist — read this at the door

- [ ] **App launches on every device going out** — done before leaving, not at the entrance
- [ ] Entrance ID assigned (`E-NNN`), written down before shooting
- [ ] Vantage point, sightlines, and people situation checked — capturable, or logged as a skip
- [ ] 5-6 views captured: head-on, both obliques, near (~1.5 m), far (~3-4 m), hardware close-up
- [ ] 1× lens, no zoom, no crop, on every shot
- [ ] Full entrance + approach path + hardware covered across the set
- [ ] No interiors, no identifiable people (any violation reshot on the spot)
- [ ] Condition tags (lighting, occlusion) recorded now, at the entrance
- [ ] If skipped: entrance and reason recorded before moving on
