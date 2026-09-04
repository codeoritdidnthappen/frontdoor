# Demo Day deck outline (TICK-103)

Content pass, 2026-09-03. The skeleton's rule stands amended, not broken: no number on a slide
is hand-typed from memory — every figure below traces to a committed, regenerable artifact
(per #10 AC1, #73 AC "every number... traceable"). Two artifact families supply the numbers
now available:

- **the offline eval on the 12-entrance pilot set** — the screening engine's committed-verdict
  accuracy, abstention counts, latency, and the blur-cost comparison
  (`src/frontdoor/screening.py` header and config notes; engine landed in PR #240, eval runner
  `src/frontdoor/screening_eval.py`);
- **the live pre-catalogue run** — the Street View Estimated-tier numbers and the freshness
  findings (`python -m frontdoor.precatalogue run` output dataset; module landed with TICK-248).

**Sealed-split confirmatory figures do not exist yet and stay as placeholders** until the
**2026-09-07** freeze. Filling those early is exactly the "remeasure to fix a slide" failure #10
and #73 warn against. Placeholder convention for what remains: `{{name: source artifact}}`.

Rubric order locked by #73 AC1 / #10 AC2 (Track 2): **research question → approach → technical
demo → what we learned and where it goes next.** Timing budget: **10 minutes total**, budgeted
below per section; rehearsal (TICK-104) is where the budget gets checked against a clock.

Pivot note, stated once here and carried through every slide below: the research question this
deck answers is **screening accuracy** — can plain photos screen entrance accessibility features
(ramp/bevel, handrails, accessible hardware, signage) reliably — which **supersedes** the
original metrology MAE-on-threshold-rise question. **Amendment A-3 is now committed**
(CHANGES.log, taken 2026-09-02 by David, requested by James in #67 on 2026-09-01): one product,
target device an iPhone Pro with LiDAR, and the pre-registered MAE hypothesis is **untested in this
window** — not relaxed, not re-scored, untested. D-040 (2026-09-04) narrows current capture and demo
hardware to James's iPhone 17 Pro (`iPhone18,1`) alone. Every slide that touches results says so.

Claims discipline, product-wide (from the #73 product-model thread): never claim a measurement,
a compliance determination, or a legal status. The line that survives every slide: **"when it
commits it's 97% right; when it can't see, it says so"** — and the 97% carries its caveat
(Section 5) everywhere it appears.

---

## Section 1 — Research question (budget: 1.5 min)

**Title:** What are we actually asking?

**Job of the slide:** State the current research question in one sentence, and name that it
supersedes the original one — so a reviewer who read the PRD doesn't spend Q&A on a question
this project no longer asks.

**Content:**
- Current question, one sentence: **can photos from James's iPhone 17 Pro screen an entrance for visible
  accessibility features — ramp/bevel, handrails, accessible door hardware, signage — reliably
  enough to power a map disabled people can trust?** Measured against human-labeled ground
  truth.
- Who it's for, one line: **~70M US adults (28.7%) have a functional disability; only ~3-6M use
  wheelchairs** (CDC BRFSS 2022, persona research in the #73 thread). The generic wheelchair
  icon is the wrong abstraction, numerically — so the product filters by what *you* need.
- Explicit supersession line, spoken and shown: this replaces the pre-registered question
  ("threshold-rise MAE ≤ 0.25\" from a single photo, sealed split") per **Amendment A-3,
  committed 2026-09-02** (CHANGES.log; requested in #67 on 2026-09-01). The old hypothesis is
  **untested**, and Section 2 reports that as an amendment, with dates.

**Speaker-note stub:** Say the old question and the new one out loud, in that order, so the
supersession is heard, not just shown. Do not let this become an apology — the pivot is a
scoping decision, framed the same way D-030 (Arm C cut) is: stated plainly, with what was lost.

---

## Section 2 — Amendments (budget: 1 min)

**Title:** What changed since pre-registration, and when

**Job of the slide:** Report every amendment to the pre-registration as an amendment — with date
and reason — because the pre-registration's own rule (PRD.md §2) requires it, and because #10
and #73 both flag this as the thing most likely to get silently dropped under deadline.

**Content (one row per amendment, read off the slide, dates included):**
- **A-1** — stratification analysis plan (capture angle becomes the confirmatory continuous
  model; four other variables move to dev-split-exploratory). Date: **2026-08-29**. Reason:
  sealed split sample size cannot support five-way confirmatory stratification. Source:
  CHANGES.log "AMENDMENT to the pre-registration" entry + PRD.md §2.
- **A-2** — Arm-A-only pass/fail bar. Date: **2026-08-29**, committed before first capture and
  before any image was processed — otherwise the unnamed-arm criterion could have been scored
  against whichever arm looked best after unsealing. Source: CHANGES.log (A-2 record restored
  by PR #235 from commit 13e735a; D-022 is the decision-register cross-reference).
- **A-3** — the pivot, **committed 2026-09-02** (taken by David; requested by James in #67 on
  2026-09-01). One product — plain-photo screening on an iPhone Pro with LiDAR; the metrology arms
  are a later version. **D-040 (2026-09-04) fixes that phone to James's iPhone 17 Pro.** Consequence
  stated on the slide in A-3's own words: **"the primary
  hypothesis is not tested in this window"** — not relaxed, not re-scoped, not re-judged
  against a different arm. Source: CHANGES.log Amendment A-3 entry.

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
- Screening — **one integrated model call per entrance**, not per photo: all 5-6 views go into
  a single call that weighs them together, so the one oblique frame that shows a ramp's riser
  informs the verdict instead of being outvoted by frontal frames that hide it. Offline eval on
  the 12-entrance pilot set: per-image majority voting amplifies shared camera-position blind
  spots; the integrated call raised committed accuracy **~90% → 97%** and cut abstentions
  **38 → 4**. Latency: **~7s median per entrance** on the recommended sonnet-class model
  (matches the larger model's accuracy at ~2.5x cheaper). Source: `src/frontdoor/screening.py`
  module header and `ScreeningConfig` notes (engine PR #240).
- Privacy is part of the pipeline, not a manual step: automatic face blur (YuNet + classical
  union) at ingest, followed by an **independent vision auto-audit** of the blurred output. On
  the 17 hardest pilot photos (faces in door glass), **0/17 recognizable after blur** per the
  independent audit — and blurring cost **zero screening accuracy** (92% vs 93%, controlled
  comparison, offline eval). Source: PR #243 (TICK-257).
- **Split-discipline explanation ("how do we know you didn't peek?"):** dev / calib / sealed
  three-way split, assigned deterministically from a committed seed at entrance creation,
  immutable thereafter (D-023, src/frontdoor/split.py). The engine itself **refuses sealed
  entrances** in code (D-007, `screening.py`). Unsealing is a single, audited,
  command-line-only act that appends to SEAL_AUDIT.log before any sealed byte is read — the
  answer is not our word, it's a git-tracked artifact.
  {{seal_audit: SEAL_AUDIT.log git history — commit hash, timestamp, and operator of the one unsealing run, exists only after the freeze-day run}}
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
  hardware, signage — from plain photos. Chips are named by what was **seen** ("Ramp visible",
  "Lever handle"), never by legal status.
- It never claims a measurement (no inches, no angles reported as ground truth), an ADA
  compliance determination, or a legal conclusion.
- "Not visible in the photos" is recorded and shown as **not visible**, never coerced into
  "absent." The two are different claims and the UI never blurs them — abstention is a
  designed behavior, not a failure mode.
- **Never a public negative.** The trust ladder (Estimated → Scanned on-site →
  Owner-confirmed) only moves pins up; disagreements route to an internal scan queue, never to
  a public bad grade. Source: #73 product-model and tier-decision comments;
  docs/external-data.md never-negative guarantee (pinned by tests).
- What photos honestly cannot assess — door weight/opening force, button function, slope — the
  UI says so as explicit copy, not silence. Source: #73 persona-research comment.
- Framing source quoted on the slide: docs/capture-protocol.md lines 7-12 ("...produces no
  measurements and makes no compliance determination...").

**Speaker-note stub:** If asked "so is this ADA-compliant or not," the answer on this slide is
the answer to give verbatim: the product does not make that determination, full stop.

---

## Section 5 — Plain-language hook (budget: 0.5 min)

**Title:** The one-line pitch

**Job of the slide:** Give the audience a single, memorable sentence that hooks interest without
claiming anything the measured accuracy doesn't support — per #73's added AC that a hook is
allowed only if it stays inside the measured claim.

**Content:**
- The line:
  > **"When it commits, it's 97% right. When it can't see, it says so."**
- What backs each half, printed on the slide, small but present:
  - *97% right*: 75/77 committed verdicts correct, offline eval on the 12-entrance pilot set,
    human-adjudicated ground truth (`src/frontdoor/screening.py`, PR #240).
  - *says so*: 4 abstentions on that same eval — and on the Street View Estimated tier, a
    79.5% abstention rate (live pre-catalogue run), because distant imagery honestly can't see
    door hardware.
- Guardrail printed on the slide itself, not just in speaker notes: **prompt rules were derived
  on the same pilot set; the next capture batch is the held-out validation, and the published
  number is whatever survives it.** If the frozen sealed number disagrees, this line is
  rewritten to whatever that number supports before Sep 9.

**Speaker-note stub:** Say this line first, before the research-question slide even, if
rehearsal timing allows — it's the hook, not the thesis. But never say it without the caveat
half-sentence; the honesty is the brand.

---

## Section 6 — Technical demo (budget: 2.5 min)

**Title:** Watch it screen a real entrance

**Job of the slide(s):** Walk the three-beat demo arc from the #73 product-model comment, with
an honest labeled fallback if live fails — and label every single moment as live or canned as it
happens, not after.

**Content — three beats:**
1. **"The map already knows downtown."** Open the public map (rebuilt to the locked UI canon in
   PR #249): **212 businesses screened into the pre-catalogue at ~$0.03/business** (live
   pre-catalogue run), provenance stacked from **156 open-licensed Commons photos** (PR #254)
   and OSM community tags (PR #245). Three tier pins per the launch ladder; every pre-catalogue
   pin honestly marked Estimated with its imagery date.
2. **Scan an unknown door LIVE on stage.** Photo in → **~7 seconds** → pin drops with the
   per-criterion checklist filling in. This is the marketing pop, and the number behind it is
   Section 3's: 97% committed accuracy on the offline eval, abstention when it can't see.
   {{live_demo_entrance_id: TICK-104 rehearsal log — entrance ID used, or "TBD day-of" if genuinely live}}
3. **"Business owners, claim your door."** Owner funnel (TICK-259, #248): claim the entrance,
   confirm observations, earn the Owner-confirmed pin — free marketing to an underserved
   market, and the fix path may be substantially offset by the Section 44 Disabled Access
   Credit (up to $5,000/yr) and the Section 190 barrier-removal deduction (up to $15,000/yr) —
   framed on the slide as "may qualify — ask your accountant", never as tax advice (#73
   product-model comment).
- **Live-vs-canned labeling note (on-screen, per #73's added AC):** every demo moment carries a
  visible on-screen tag — "LIVE" or "CANNED (recorded {{backup_capture_date: TICK-104 backup
  recording metadata / capture timestamp}})" — shown at the moment that moment is displayed,
  not narrated after the fact. Build the tag into the slide or overlay so it survives even if
  the presenter forgets to say it.
- Backup if the live scan fails: the **map page `?demo=1` scan animation (PR #249)**, shown
  with the CANNED tag, plus the pre-recorded engine run.
  {{backup_recording_ref: TICK-104 deliverable — file path or link to the captured backup}}

**Speaker-note stub:** Rehearse the failure path, not just the happy path — TICK-104 owns this,
but the deck should never be the first place the fallback is exercised.

---

## Section 7 — What we learned (budget: 1.5 min)

**Title:** What the numbers say — and which numbers are frozen

**Job of the slide:** Report the accuracy figures with their split labels visible on the same
slide (not an appendix), exploratory results labeled exploratory on the slide itself, and the
untested pre-registered bar stated plainly.

**Content:**
- **Pilot / development numbers (labeled PILOT SET — NOT SEALED-CONFIRMATORY, on the slide):**
  offline eval on the 12-entrance pilot set, human-adjudicated ground truth — **97%
  committed-verdict accuracy (75/77), 4 abstentions**, ~7s median per entrance, single
  integrated call. **On-slide caveat, verbatim: "prompt rules were derived on this same set;
  held-out validation is owed on the next capture batch."** Source: `src/frontdoor/screening.py`
  (PR #240), eval runner `src/frontdoor/screening_eval.py`.
- **Estimated tier (labeled LIVE PRE-CATALOGUE RUN):** Street View imagery, same engine —
  **88.9% committed accuracy with 79.5% abstention** over 11 place_id-verified doors. The lone
  error traced to **2010 imagery predating a later-built ramp** — evidence decays, which is why
  tenant-turnover gating is designed in. The freshness guard also caught one business
  **CLOSED_PERMANENTLY while its signage is still up**, and one business **delisted from Google
  Places entirely** — our scans fill gaps Google has. Source: live pre-catalogue run output
  (`python -m frontdoor.precatalogue run`).
- **Privacy cost: zero.** Automatic blur + independent vision auto-audit; 0/17 recognizable on
  the hardest pilot photos; 92% vs 93% controlled accuracy comparison (offline eval; PR #243).
- **Sealed split (confirmatory) — filled at the Sep 7 freeze, not before:**
  {{accuracy_per_criterion: screening_eval report from the audited freeze-day run over the sealed split}}
  {{exploratory_condition_breakdown: screening_eval report, dev-split per-condition section — must carry an on-slide "exploratory" label per #73 AC}}
- The pre-registered MAE bar went **untested** (A-3, D-036) — said here as well as on Section 2,
  because this is the results slide and #73's AC puts it here.
- Split discipline repeated in one line (per #73 AC): sealed entrances never opened before
  freeze; see Section 3 / SEAL_AUDIT.log.

**Speaker-note stub:** Read the split label out loud for every number that isn't sealed-
confirmatory. This is the slide most likely to get "well, actually" from someone who knows the
split existed for a reason — and the pilot-set caveat is the answer, offered before it's asked.

---

## Section 8 — Negative-result contingency (budget: fits inside Section 7's 1.5 min if triggered; do not add time)

**Title (used only if triggered):** What the frozen number actually shows

**Job of the slide:** If the sealed accuracy comes back low, replace the "results" framing with
a **finding**, with error attributed to conditions — never buried, never presented as a
generic failure. Prepared now, filled only if the Sep 7 freeze requires it.

**Content (fallback structure, use verbatim in place of Section 7's sealed rows if triggered):**
1. State the frozen number plainly: {{negative_headline_accuracy: screening_eval report, freeze-day sealed run}}.
2. State the finding as a finding: "Under [condition], multi-view screening of [criterion]
   does not reach a reliable call; the failure mode is [X]." Fill from
   {{failure_mode_breakdown: screening_eval report, per-condition error attribution}}.
3. Attribute error to specific conditions, not to "the model" in general — lighting, occlusion,
   viewing angle, criterion visibility. The pre-catalogue's lone error is the template for this
   framing: not "the model was wrong," but "2010 imagery predates a later-built ramp."
4. High abstention is reported as designed behavior, not padded into failure or success: the
   Estimated tier's 79.5% abstention *is* "when it can't see, it says so."
5. State what a positive result would have required, and what's next (feeds into Section 9).
- This structure exists because #10 and #73 both require a negative result to be presentable,
  not hidden — carried from the metrology study into the screening study as the same standard.

**Speaker-note stub:** If this slide is live, say the number first, before any hedge. The
project's credibility rests on this being reported the same way a positive result would be.

---

## Section 9 — Where it goes next (budget: 1 min)

**Title:** Where this goes from here

**Job of the slide:** Close the "what we learned and where it goes next" rubric item with
concrete next steps that follow from the numbers on the previous slide — not a generic roadmap.

**Content:**
- **First, the owed validation:** the next capture batch is the held-out validation of the 97%
  pilot number; the published accuracy is whatever survives it. That batch is the very next
  step, said plainly.
- **Scale the supply side along the trust ladder:** the pre-catalogue run priced screening at
  ~$0.03/business — downtown density is a budget line, not a research question. Community scans
  upgrade Estimated pins to Scanned on-site; the owner funnel (TICK-259) upgrades to
  Owner-confirmed. The auditor tier is deliberately **cut from v1** (#73 tier decision: no
  supply, and an empty top shelf advertises what we lack) and returns as the roadmap line: "as
  licensed accessibility specialists join, their inspections light up a fourth ring" — with the
  Texas state-inspection records layer (TABS, `src/frontdoor/tabs.py` stub + PIA request path
  in docs/external-data.md) as a possible seed, labeled point-in-time if ever used.
- **Deepen the criteria where the personas point:** step-count class, threshold lip class,
  glass-door contrast markings, ramp handrails — all photo-assessable, all named in the #73
  persona research. Video capture modes (walk-by block pass, 10-second walk-up) are in flight.
- One line on what stays out of scope regardless of outcome: **no compliance determinations, no
  legal conclusions, no public negative verdicts, no measurement claims** — the honest-claims
  framing from Section 4 doesn't expire when the demo ends.

**Speaker-note stub:** Keep this to next steps that follow *from the numbers on Section 7* — a
reviewer will ask "why that, and not something else," and the answer should be the number on the
previous slide (the 79.5% abstention justifies on-site scanning; the $0.03 justifies scale; the
pilot-set caveat justifies the validation batch coming first).

---

## Section 10 — Per-person build-in-public numbers (budget: 0.5 min)

**Title:** Build in public — the numbers, per person

**Job of the slide:** Present the graded per-person build-in-public numbers (TICK-116), since
#10/#73 both require these included, not summarized as a team total (PRD §11 grades per person).

**Content:**
- Table, one row per team member (David, James, Emily, Ruben — TEAM.md §1), columns: engagements,
  new followers, build-in-public post count, outside-team repost count, against the graded floors
  (150+ engagements / 25+ followers / 5+ posts / 1+ outside repost).
  {{per_person_bip_numbers: docs/build-in-public-tracker.md (#82) scorecards, backed by the 2026-09-08 account screenshots the tracker requires — screenshots, not the file, are the evidence per the tracker's own rule}}
- The tracker exists (docs/build-in-public-tracker.md); its numbers must be second-person
  cross-checked against the live accounts before Demo Day, per #82 — an unverified tracker is
  worth less than none.

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
