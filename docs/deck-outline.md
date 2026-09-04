# Demo Day deck outline (TICK-103)

Structure only. No numbers are typed into this file — every figure is a named placeholder
pointing at the artifact that will supply it once numbers freeze on **2026-09-07**. Do not fill
a placeholder before then; filling early is exactly the "remeasure to fix a slide" failure #10
and #73 warn against.

Placeholder convention: `{{name: source artifact}}`. Before the deck is filled, every
placeholder in this file must resolve to a committed, regenerable artifact — never a
hand-typed or remembered number (per #10 AC1, #73 AC "every number... traceable").

Rubric order locked by #73 AC1 / #10 AC2 (Track 2): **research question → approach → technical
demo → what we learned and where it goes next.** Timing budget: **10 minutes total**, budgeted
below per section; rehearsal (TICK-104) is where the budget gets checked against a clock.

Pivot note, stated once here and carried through every slide below: the research question this
deck answers is **screening accuracy** — can a photo screen entrance accessibility features
(ramp/bevel, handrails, accessible hardware, signage) reliably — which **supersedes** the
original metrology MAE-on-threshold-rise question, pending Amendment A-3's CHANGES.log entry
(the pivot decision of 2026-09-01, flagged in issue #67 and still unlogged as of this skeleton).
Until A-3 is committed, PRD.md §2's pre-registered MAE question is the pre-pivot record, not the
live one; this deck follows the pivot per the #73 comment marking the Arm-A-only criteria as
superseded.

---

## Section 1 — Research question (budget: 1.5 min)

**Title:** What are we actually asking?

**Job of the slide:** State the current research question in one sentence, and name that it
supersedes the original one — so a reviewer who read the PRD doesn't spend Q&A on a question
this project no longer asks.

**Content:**
- Current question: can a single ordinary phone photo screen an entrance for visible
  accessibility features (ramp/bevel, handrails, accessible door hardware, signage) reliably
  enough to be useful — as measured against human-labeled ground truth?
- Explicit supersession line: this replaces the original pre-registered question ("how
  accurately can threshold rise be measured from a single photo, MAE ≤ 0.25\" on the sealed
  split") per the team's pivot decision (2026-09-01, issue #67), pending Amendment A-3.
- {{pivot_date_and_amendment_id: CHANGES.log Amendment A-3 entry, once committed — until then, cite issue #67 comment thread directly per the #73 comment's instruction}}

**Speaker-note stub:** Say the old question and the new one out loud, in that order, so the
supersession is heard, not just shown. Do not let this become an apology — the pivot is a
scoping decision, framed the same way D-030 (Arm C cut) is: stated plainly, with what was lost.

---

## Section 2 — Amendments (budget: 1 min)

**Title:** What changed since pre-registration, and when

**Job of the slide:** Report every amendment to the pre-registration as an amendment — with date
and reason — because the pre-registration's own rule (PRD.md §2) requires it, and because #10
and #73 both flag this as the thing most likely to get silently dropped under deadline.

**Content (one row per amendment):**
- **A-1** — stratification analysis plan (capture angle becomes the confirmatory continuous
  model; four other variables move to dev-split-exploratory). Date: 2026-08-29. Reason: sealed
  split sample size cannot support five-way confirmatory stratification.
  {{a1_text_and_date: CHANGES.log "AMENDMENT to the pre-registration" entry, 2026-08-29 section, and PRD.md §2}}
- **A-2** — Arm-A-only pass/fail bar. Date: 2026-08-29. The original entry says the unnamed-arm
  criterion could otherwise be scored against whichever arm looked best after unsealing. It was
  committed before first capture and before any image was processed.
  {{a2_text_and_date: CHANGES.log "Decision-log gap" section, A-2 entry recovered from commit 13e735a}}
- **A-3 — PENDING.** The 2026-09-01 pivot from metrology (caliper/LiDAR, MAE bar) to plain-photo
  screening. Requested as a formal amendment in the #67 thread; not yet committed to
  CHANGES.log as of this skeleton. This slide must not claim A-3 is logged until it is — if it
  is still pending at rehearsal, say so on the slide rather than backfilling a date.
  {{a3_text_and_date: CHANGES.log Amendment A-3 entry — DOES NOT YET EXIST, check before fill; if absent at freeze, the slide says "pending" and cites issue #67 instead}}

**Speaker-note stub:** This is the slide the second reviewer (per #73's Testing section) checks
line by line. Do not summarize the amendments from memory in the room — read the date and reason
off the slide, because that's the whole point of writing them down.

---

## Section 3 — Approach (budget: 2 min)

**Title:** How the screening engine works, and why the split protects it

**Job of the slide:** Explain the approach (photo capture protocol → screening engine →
per-criterion verdicts) and answer "how do we know you didn't peek?" on the same breath, since
#73 AC requires the split discipline explained, not relegated to an appendix.

**Content:**
- Capture: 5-6 views per entrance (head-on, both obliques, near, far, hardware close-up),
  1x lens, no crop, condition tags recorded at capture. Source: docs/capture-protocol.md.
- Screening: per-criterion verdicts aggregated across the view set per entrance (a single photo
  leaves "not visible" indistinguishable from "absent" too often).
- **Split-discipline explanation ("how do we know you didn't peek?"):** dev / calib / sealed
  three-way split, assigned deterministically from a committed seed at entrance creation,
  immutable thereafter (D-023, src/frontdoor/split.py). Sealed entrances are captured normally
  and never opened, inspected, or assessed before the freeze. Unsealing is a single, audited,
  command-line-only act that appends to SEAL_AUDIT.log before any sealed byte is read — the
  answer is not our word, it's a git-tracked artifact.
  {{seal_audit: SEAL_AUDIT.log git history — commit hash, timestamp, and operator of the one unsealing run}}
  {{split_seed_and_proportions: src/frontdoor/split_seed.json + split.py, sealed/calib/dev share actually realized over the captured entrance IDs}}

**Speaker-note stub:** This slide carries the project's single integrity claim. Point at
SEAL_AUDIT.log's commit hash on screen — don't just assert the split held, show the artifact
that proves it, live if the deck software allows a linked screenshot.

---

## Section 4 — Honest-claims framing (budget: 0.5 min)

**Title:** What this product does and does not say

**Job of the slide:** State, in the plainest possible terms, that every output is a
visible-feature observation, never a measurement or a compliance determination — so the audience
calibrates trust correctly before seeing the demo, and Q&A doesn't have to relitigate scope.

**Content:**
- The product screens **visible feature presence** — ramp/bevel, handrails, accessible door
  hardware, signage — from plain photos.
- It never claims a measurement (no inches, no angles reported as ground truth), an ADA
  compliance determination, or a legal conclusion.
- "Not visible in the photos" is recorded and shown as **not visible**, never coerced into
  "absent." The two are different claims and the UI/deck must never blur them.
- Source of this framing: capture-protocol.md (TICK-090) and the #67 pivot thread's carried-over
  framing note.
  {{honest_claims_wording: docs/capture-protocol.md lines 7-12, quoted verbatim on the slide}}

**Speaker-note stub:** If asked "so is this ADA-compliant or not," the answer on this slide is
the answer to give verbatim: the product does not make that determination, full stop.

---

## Section 5 — Plain-language hook (budget: 0.5 min)

**Title:** The one-line pitch

**Job of the slide:** Give the audience a single, memorable sentence that hooks interest without
claiming anything the measured accuracy report doesn't support — per #73's added AC that a hook
is allowed only if it stays inside the measured claim.

**Content:**
- Candidate line (draft, to be checked against the frozen accuracy report before use — if the
  measured accuracy is low, this line must be softened or dropped in favor of the negative-result
  framing in Section 8):
  > "A phone camera can tell you whether an entrance has a ramp about as often as a person
  > glancing at the same photo would — no tape measure required."
- Guardrail printed on the slide itself, not just in speaker notes: this line claims nothing
  beyond {{measured_accuracy_headline: screening_eval report, top-line per-criterion accuracy
  figure}} — if the frozen number doesn't support "about as often as a person," the line is
  rewritten to whatever the number actually supports before Sep 9.

**Speaker-note stub:** Say this line first, before the research-question slide even, if
rehearsal timing allows — it's the hook, not the thesis. But never say it without having checked
it against the frozen number that week.

---

## Section 6 — Technical demo (budget: 2.5 min)

**Title:** Watch it screen a real entrance

**Job of the slide(s):** Walk a live screening of an entrance, with an honest labeled fallback if
live fails — and label every single moment as live or canned as it happens, not after.

**Content:**
- **Live-vs-canned labeling note (on-screen, per #73's added AC):** every demo moment carries a
  visible on-screen tag — "LIVE" or "CANNED (recorded {{backup_capture_date: TICK-104 backup
  recording metadata / capture timestamp}})" — shown at the moment that moment is displayed, not
  narrated after the fact and not left to the presenter's memory. Build the tag into the slide
  itself or the screen-recording overlay so it survives even if the presenter forgets to say it.
- Live attempt: photo (or live capture) of an entrance run through the screening engine; per-
  criterion verdicts shown as they resolve.
  {{live_demo_entrance_id: TICK-104 rehearsal log — entrance ID used, or "TBD day-of" if genuinely live}}
- Backup: pre-recorded run captured before Sep 9, shown only if the live attempt fails, per PRD
  §10 / EPIC-07 AC on the fallback chain.
  {{backup_recording_ref: TICK-104 deliverable — file path or link to the captured backup}}

**Speaker-note stub:** Rehearse the failure path, not just the happy path — TICK-104 owns this,
but the deck should never be the first place the fallback is exercised.

---

## Section 7 — What we learned (budget: 1.5 min)

**Title:** What the frozen numbers say

**Job of the slide:** Report the frozen accuracy figures, split by dev/exploratory vs.
sealed/confirmatory, with the split discipline visible on the same slide (not an appendix), and
with exploratory results explicitly labeled exploratory on the slide itself.

**Content:**
- Per-criterion screening accuracy, sealed split (confirmatory):
  {{accuracy_per_criterion: screening_eval report, generated by TICK-100's notebook from
  committed inputs}}
- Per-condition breakdowns (lighting, occlusion, entrance type) — **labeled EXPLORATORY on the
  slide**, dev split, not a confirmatory claim:
  {{exploratory_condition_breakdown: screening_eval report, dev-split section — must carry an
  on-slide "exploratory" label per #73 AC}}
- Split discipline repeated in one line (per #73 AC: not relegated to appendix): sealed
  entrances never opened before freeze; see Section 3 / SEAL_AUDIT.log.
- If the primary result is negative (accuracy below what's useful): see Section 8, this slide
  becomes the finding-framed negative-result slide instead of a pass/fail scorecard.

**Speaker-note stub:** Read the split label out loud for every number that isn't sealed-
confirmatory. This is the slide most likely to get "well, actually" from someone who knows the
split existed for a reason.

---

## Section 8 — Negative-result contingency (budget: fits inside Section 7's 1.5 min if triggered; do not add time)

**Title (used only if triggered):** What the frozen number actually shows

**Job of the slide:** If the sealed accuracy comes back low, replace the "results" framing with
a **finding**, with error attributed to conditions — never buried, never presented as a
generic failure. This is a fallback structure, prepared now, filled only if the Sep 7 freeze
requires it.

**Content (fallback structure, use verbatim in place of Section 7 if triggered):**
1. State the frozen number plainly: {{negative_headline_accuracy: screening_eval report}}.
2. State the finding as a finding: "Under [condition], single-photo screening of [criterion]
   does not reach a reliable call; the failure mode is [X]." Fill from
   {{failure_mode_breakdown: screening_eval report, per-condition error attribution}}.
3. Attribute error to specific conditions, not to "the model" in general — lighting, occlusion,
   viewing angle, criterion visibility — sourced from the same per-condition breakdown as
   Section 7's exploratory slide.
4. State what a positive result would have required, and what's next (feeds into Section 9).
- This structure exists because #10 and #73 both require a negative result to be presentable,
  not hidden: "a result showing single-image measurement cannot reach the bar is a valid and
  presentable outcome," carried into the pivot as the same standard for screening accuracy.

**Speaker-note stub:** If this slide is live, say the number first, before any hedge. The
project's credibility rests on this being reported the same way a positive result would be.

---

## Section 9 — Where it goes next (budget: 1 min)

**Title:** Where this goes from here

**Job of the slide:** Close the "what we learned and where it goes next" rubric item with
concrete next steps conditioned on the Section 7/8 outcome — not a generic roadmap slide.

**Content:**
- If positive: what scaling the screening engine or dataset would take next.
- If negative (Section 8 triggered): what would need to change (more views per entrance, a
  different criterion set, human-in-the-loop confirmation) to close the gap named in the finding.
- One line on what stays out of scope regardless of outcome: no compliance determinations, no
  consumer map, no legal conclusions — the honest-claims framing from Section 4 doesn't expire
  when the demo ends.

**Speaker-note stub:** Keep this to next steps that follow *from the frozen number*, not a wish
list — a reviewer will ask "why that, and not something else" and the answer should be the
number on the previous slide.

---

## Section 10 — Per-person build-in-public numbers (budget: 0.5 min)

**Title:** Build in public — the numbers, per person

**Job of the slide:** Present the graded per-person build-in-public numbers (TICK-116), since
#10/#73 both require these included, not summarized as a team total (PRD §11 grades per person).

**Content:**
- Table, one row per team member (David, James, Emily, Ruben — TEAM.md §1), columns: engagements,
  new followers, build-in-public post count, outside-team repost count, against the graded floors
  (150+ engagements / 25+ followers / 5+ posts / 1+ outside repost).
  {{per_person_bip_numbers: per-person tracker — issue #82 once it exists; until then, the dated
  comments on the post tickets (#76, #77, and equivalents for Emily/Ruben) per the #67 thread's
  interim convention}}
- Note on the slide if the tracker (#82) never materialized before freeze: cite the interim
  per-ticket comment convention explicitly rather than presenting a table with silently
  reconciled numbers.

**Speaker-note stub:** This is a graded requirement, not a nice-to-have close — don't let it get
cut for time. It fits in the 30 seconds budgeted; rehearse it at that length specifically.

---

## Timing budget summary

| Section | Minutes |
|---|---|
| 1. Research question | 1.5 |
| 2. Amendments | 1.0 |
| 3. Approach (incl. split discipline) | 2.0 |
| 4. Honest-claims framing | 0.5 |
| 5. Plain-language hook | 0.5 |
| 6. Technical demo (incl. live/canned labeling) | 2.5 |
| 7. What we learned (or 8. Negative-result, mutually exclusive with 7) | 1.5 |
| 9. Where it goes next | 1.0 |
| 10. Per-person build-in-public numbers | 0.5 |
| **Total** | **10.0** |

Q&A: 5 minutes, not counted above (per #10/#73 "10 minutes plus 5 of Q&A").

Verification per #73's Testing section: this outline is checked by a timed dry run in front of a
team member who did not build the slides — 10 minutes or under, every rubric item present, every
number traceable — with a second reviewer specifically checking the amendments slide (Section 2)
and the split-discipline explanation (Section 3). That rehearsal is TICK-104; this document is
its input, not its substitute.
