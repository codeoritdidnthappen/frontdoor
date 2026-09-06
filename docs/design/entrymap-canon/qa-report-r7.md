# EntryMap prototype — adversarial re-audit after Round 7

**Target:** `design/phone-app-prototype.html` at commit `eb056fe` ("Round 7: take the map kit, adopt the canonical palette, score the floors")
**md5 of the file tested:** `87f681d8778e8d2cecf01d693ffae6fc`
(working tree byte-identical to `git show eb056fe:design/phone-app-prototype.html`; both `http://127.0.0.1:8765` and the preview proxy served the same md5)
**Driven at:** 390 × 844 over `http://127.0.0.1`, never `file://`
**Also driven:** the live build at `https://frontdoor-measure.fly.dev/app`, md5 `1e111e8540c000921301b66637091477`, 7,597 lines vs the design source's 7,200
**Previous report:** `design/qa-report.md` (Rounds 4–6 in flight). Every defect in it was re-driven, not read off a commit message.

**Counts:** 13 previous defects re-checked — **8 fixed, 4 still open, 1 changed shape, 0 regressed.** 9 previous audit findings re-checked — **5 fixed, 4 still open.** **9 new defects** found in Rounds 6–7 and at their seams. **1 of the 3 honest-criteria checks fails.** 4 of my own findings were withdrawn as instrument artifacts and are recorded below rather than dropped.

---

## Method, and two things wrong with the instrument

Screens were driven with real keyboard input (`Tab`, arrow keys) and with synthesised pointer sequences. The Browser pane's native click pipeline was wedged again — `left_click` timed out at 30 s — so taps were synthesised. That was calibrated against the app's own semantics before anything was believed:

- Clicks carry `detail: 1`. The card handle reads `e.detail === 0` as *keyboard* activation (`grip.addEventListener('click', e => { if(e.detail===0) stepCard(+1) })`), so a naive synthetic click double-steps it.
- `pointerdown` focuses the nearest focusable ancestor, as a browser does. Without this, every focus-return measurement is wrong.
- Drag gestures space their `pointermove` events in **real time**. My first drag harness fired all moves at one timestamp, which made `closeSheets`' velocity projection see ~120 px/ms and close the sheet on a 120 px downward drag. That produced a "drag down at full closes the card" finding that is not true. **Withdrawn.**

Two environment problems bit harder, and both matter for anyone re-running this:

1. **A concurrent agent was driving the same browser tab.** Its instrumentation (`__ringProbe`, `__sweep`, `__hcSweep`, `__A`) was walking every screen on an async loop underneath my measurements. Everything before the isolation point was re-run in a fresh tab. If you re-run this, check `Object.keys(window).filter(k=>k.startsWith('__'))` is empty first.
2. **My own harness clobbered the app's global `esc()`.** For several minutes the filter chips appeared to render the literal string `"true"` instead of their labels — because `esc(v.label)` was resolving to my helper, not the app's HTML escaper. **Withdrawn.** The app's `esc()` is intact and correct.

### Withdrawn findings (all four)

| Claimed | Why it was wrong |
|---|---|
| Filter chips render the label `"true"` | My harness overwrote the app's global `esc()`. |
| Drag-down 120 px at the full stop closes the card | Synthetic drag had zero elapsed time → infinite release velocity. |
| Closing the map card strands focus on `H2.card-name` (6/12 pins) | `requestAnimationFrame` in this pane fires **892 ms** after being scheduled (measured, twice). `closeSheets` restores focus on a frame. Widening the sample window to 1.8 s and instrumenting `focusWhenReady` gave **14/14 correct returns** across Escape, close button and scrim, and 3/3 for the Filters, Needs and Trust sheets. On a device rAF is ~16 ms. |
| Processing runs with no announcement | I watched `#sr-announce`; processing uses a second live region, `#proc-live`. It announces "Checks complete. 3 features identified. Review before publishing." — byte-identical to Round 1. |

One residual note that is *not* a defect but is worth a line: Round 6's comment argues against depending on a clock, and Round 7's focus-return then depends on a frame instead. Where frames are not being produced, focus sits inside a `visibility:hidden` sheet for exactly as long as that lasts. It cannot be reached by an interacting user, so it is recorded, not filed.

---

# Part one — every defect from the previous report, re-driven

| # | Previous finding | Status now |
|---|---|---|
| S1 | Reduce Motion breaks focus into every sheet (12/12 land on `<body>`) | **FIXED** |
| S2 | "Open now" and "Distance" inert; a `role="switch"` lying to a screen reader | **FIXED** |
| S3 | "7 days" and "30 days" functionally identical | **FIXED** |
| S4 | Dragging the card up at the top stop collapses it to peek | **FIXED** |
| S5 | Claim submits with no contact, then promises an email | **FIXED** |
| S6 | Search overlay claims `aria-modal` and traps nothing | **FIXED** |
| S7 | Keyboard-focused pins draw a stray focus artifact | **STILL OPEN** (recoloured, same shape) |
| S8 | Verify-options overflow at the largest text size | **FIXED** |
| S9 | A completely empty correction submits | **FIXED** |
| S10 | A very long search query blows out the results pane | **FIXED** |
| S11 | The no-results state contradicts itself with "0 entrances · 0 businesses" | **FIXED** |
| S12 | `scan-processing` has no in-screen exit | **STILL OPEN** |
| S13 | Backgrounding is entirely unhandled | **STILL OPEN** (code-read; camera still blocked here) |

## S1 · FIXED — reduced motion no longer breaks sheet focus

**Reproduction** — Onboard to the map → Profile → Accessibility → **Reduce motion** on → back to the map → open Filters / My needs / the trust legend / any pin, six times each, and read `document.activeElement`.

**Measured, clean tab, RM on:** 0/24 land on `<body>`. Filters 6/6 `H3.sheet-h`, My needs 6/6, trust legend 6/6, entrance card 6/6 `H2.card-name`. Control with RM off: 8/8 correct.

Round 6 fixed both halves. `transition-delay:0s !important` and `animation-delay:0s !important` were added to the `.phone.rm *` block (line ~1603), *and* the separate `@media (prefers-reduced-motion: reduce)` block was deleted in favour of one class driven by `isReduced() = RM_MEDIA.matches || rmPref`, with a `change` listener — so the OS setting and the in-app toggle can no longer disagree. `openSheet` no longer waits 40 ms; `focusWhenReady` waits on the element actually being focusable. This is the right fix at both levels.

*One structural consequence worth naming:* honouring the OS preference is now entirely JavaScript-mediated. There is no CSS-only path. If the script fails, `prefers-reduced-motion: reduce` has no effect at all. That is a deliberate trade for coherence and I am not filing it, but a future round should not delete `RM_MEDIA` without noticing.

## S2 · FIXED — one control wired, one removed

**Reproduction** — Map → Filters → Reset → drag **Walking distance** across its range, reading "Show N places".

| Distance | Result |
|---|---|
| Any distance (1000) | Show 64 places |
| Within 800 feet | Show 58 places |
| Within 600 feet | Show 44 places |
| Within 400 feet | Show 22 places |
| Within 300 feet | Show 11 places |
| Within 200 feet | Show 5 places |

`filtDist` is a real state variable, `filterPass` tests it (`distFt(p) > filtDist`), it appears in `anyFilter()`, `filterCount()` and the removable chip row ("Within 200 ft ✕"). The **"Open now"** switch is gone from the markup entirely — `grep -ci "open now"` returns one hit, and it is the comment explaining the removal. A switch that lied has been deleted rather than hidden, which is the better of the two fixes.

## S3 · FIXED — the two freshness windows are now two windows

**Reproduction** — Filters → Reset → tap each freshness segment.

| Freshness | Result | `aria-pressed` |
|---|---|---|
| Any | Show 64 places | Any=true, 7=false, 30=false |
| 7 days | **Show 7 places** | Any=false, 7=true, 30=false |
| 30 days | **Show 12 places** | Any=false, 7=false, 30=true |

`filterPass` now asks `ageDays(p.date) > Number(filtFresh)`. Round 6 also re-dated the pilot scans across a fortnight so the two windows have something to separate. Exclusive `aria-pressed` across the group is correct.

## S4 · FIXED — the sheet is a real gesture now

**Reproduction** — Map → tap a pin → tap the handle twice to reach **full** → drag up, drag down, at real gesture speed (moves spaced ≥16 ms apart; see the instrument note).

| Gesture at | Result |
|---|---|
| full, drag up 150 px | **full** (no-op) |
| full, drag up 400 px | **full** (no-op) |
| full, drag down 150 px | medium |
| medium, drag up 150 px | full |
| full, drag down 600 px | closed |

Round 6 replaced the modulo wrap on the drag path with a `pointermove` that tracks the finger one-to-one, an upward bound of `s.full - sh.offsetHeight` so the sheet stretches toward full rather than lifting off, and a release that projects `sh.offsetHeight - dy - v*PROJECT_MS` onto the nearest of the three stops. The handle's `aria-label` no longer over-promises: it now says "tap to return to peek" at the full stop.

## S5 · FIXED — the confirmation now names the channel it collected

**Reproduction** — Profile → Start a claim → pick a listing → Continue.

| Input | Result |
|---|---|
| Everything empty, Submit | Blocked. `aria-invalid="true"` on the checkbox, focus moves there, announced. |
| Authorization ticked, both fields empty | Blocked. `#claim-contact-err` on, focus on `#claim-email`, `aria-invalid="true"`, `aria-describedby="claim-contact-err-text"`, announced "Claim not submitted. Add the work email we should send the link to." |
| Email = `"     "` (whitespace) | Blocked (`.trim()`). |
| Channel switched to **Call the business**, email filled, phone empty | Blocked on the *phone*, `aria-invalid` moves to `#claim-phone`, the email's `aria-invalid` is cleared. Error text changes to the phone wording. |
| Phone filled, Submit | Lands on `claim-track`, which reads **"We'll call the business's listed phone when your workspace is ready."** |

The rule is scoped exactly to the selected channel, so a phone claimant is never asked for an email. Markup in the email field (`<img src=x onerror=…>`) is accepted as a value but never echoed anywhere.

## S6 · FIXED — the search overlay now traps what it claims to

**Reproduction** — Map → search icon. With the overlay open, enumerate every focusable outside it and call `.focus()` on each.

**Measured:** 83 candidates outside `#search-ov`, **0 accepted focus**. `[inert]` node count went from 0 to 47. `openSearch()` now calls `inertOutside(searchOv)` — which walks the ancestor chain and inerts siblings at each level, because the overlay lives inside `#screen-map` and so could not be passed to `setBackgroundInert` — plus a Tab trap mirroring the sheet trap. Focus enters the field, Escape closes, focus returns to the opener.

## S7 · STILL OPEN — the stray pin focus artifact, now in Round 7's blue

**Reproduction** — Map (default state) → `Tab` about twenty times with a real keyboard until `document.activeElement.className` contains `pinbtn`.

**Measured on a genuinely keyboard-focused pin (`:focus-visible === true`):**

```
box:        0 × 0
outline:    solid 2.667px rgb(27, 101, 153)   offset 2.667px
box-shadow: rgba(255,255,255,0.92) 0 0 0 6px
::before:   48px × 48px, solid 2.667px        <- the intended ring
```

A ~12 × 12 px white halo with a blue outline is still painted around the zero-size anchor at the pin's tip, *in addition to* the correct 48 px ring on the pseudo-element. Same for `.cluster`.

**Cause is unchanged and is still a specificity collision.** `.pinbtn:focus-visible{outline:none}` (line 553) and `.cluster:focus-visible{outline:none}` (line 1357) are both specificity (0,2,0); `.phone :focus-visible` (line 1878) is also (0,2,0) and is declared later, so it wins. Round 7 changed the colour of the artifact from violet to `--brand-blue-ink` while re-authoring the palette and did not notice the rule was dead. Fix is one character: `.phone .pinbtn:focus-visible` / `.phone .cluster:focus-visible`.

**Severity: MEDIUM.** Visible to anyone demonstrating keyboard navigation, which on this product is a likely thing to demonstrate.

## S8 · FIXED — nothing squashes at the largest text size

**Reproduction** — Accessibility → text size **Larger** (`data-textsize="larger"`, root font-size 18.9 px) → Profile → Start a claim → Continue.

| Element | Content needs | Box gets |
|---|---|---|
| `.verify-opt.sel` | 90 px | **94 px** |
| `.verify-opt` | 71 px | **75 px** |
| `.authz` | 48 px | 48 px |

A sweep of every element on all 26 screens at the largest size found **zero** material squash. (Six hits are noise: five `.toggle` knobs, whose absolutely-positioned child exceeds the box by design, and three `H1` line-height roundings of 3–4 px.) Nothing clips vertically; every long screen scrolls.

## S9 · FIXED — the empty correction is refused, properly

**Reproduction** — Map → pin → expand to full → **Suggest a correction** → **Send suggestion** with nothing selected and nothing typed.

**What happens:** the sheet stays open, `#correct-note` gets `aria-invalid="true"` and `aria-describedby="correct-err-text"`, focus moves to it, the inline error reads "Tell us what you noticed, or add a photo, so the note has something to review.", and `#sr-announce` says "Correction not sent. Tell us what you noticed, or add a photo." Whitespace-only is also refused. `maxlength="300"` still bounds the note.

## S10 · FIXED — long queries wrap

**Reproduction** — Map → search → paste 5,000 characters with no spaces.
`#search-body`: `scrollWidth 358`, `clientWidth 358`. `overflow-wrap` now computes `anywhere` on `.sheet-p`. Previously 43,114 px of horizontal scroll.

## S11 · FIXED — the no-results state no longer contradicts itself

A query with no matches renders only the invite: *"No entrances mapped for "zzzqqqxyz" yet. Be the first to help neighbors plan ahead."* plus a Scan CTA. The "0 entrances · 0 businesses" header is gone. Singular/plural is still correct on the results header ("1 entrance · 1 business"); a broad query renders 56 rows without incident.

## S12 · STILL OPEN — `scan-processing` has no exit of its own

The screen carries no cancel, no back, no close. The bottom nav is present and not inert, and all three routes out cancel the scan timers cleanly (verified: left at 1.2 s, idled 2.5 s on Profile, no stale-timer yank). Escapable, not a trap, but the only screen in the app with no control of its own.

## S13 · STILL OPEN — no backgrounding handler

`grep -c "visibilitychange\|pagehide\|pageshow\|document.hidden"` returns **0**. `stopCamera()` is still reachable only from `showScreen` and three explicit call sites. Backgrounding on `scan-capture` therefore still appears to leave the stream live, against that screen's own privacy copy. **Not confirmed behaviourally** — camera access is blocked in this environment, so `camStream` was never non-null. Flagged for a real-device check.

Positively: `runProcessing` keeps its timer-based watchdog for throttled `requestAnimationFrame`, which I can now confirm matters — rAF was measured at **1 fps** in a hidden tab here, and the watchdog is what stops the ring hanging.

---

# Part two — new defects, Rounds 6–7

## N1 · HIGH · Tapping a cluster does nothing, and its own label promises otherwise

**Screen id:** `screen-map`. **Reproduction**

1. Onboard through to the map. Do not change any filter.
2. The default map draws **12 individual pins and 9 clusters** (the largest reads "14").
3. Tap any cluster. Wait 2.5 s.

**What happened** — nothing changes. Pins 12 → 12, clusters 9 → 9, `#zoom-toggle` still `aria-pressed="false"`. No toast, no announcement. Repeated taps do nothing. The cluster's own accessible name is:

> "14 entrances here (3 scanned on-site, 11 estimated) — **zoom in to see each one**"

**What should have happened** — the cluster resolves, or it does not advertise that it will.

**Cause.** The handler is `b.addEventListener('click',()=>{ setZoom(false); })`. `zoomedOut` is `false` on the default map, so `setZoom(false)` is a no-op that re-renders the same layout. There is no intermediate zoom level: `mapLayout` has exactly two, `CELL = zoomedOut ? 72 : 60`. From the overview level the tap does work (11 clusters → 9), but the 14-member cluster survives both levels, so **there is no zoom at which those 14 entrances can be reached by tapping the map.** They remain reachable via the list view and search, so this is not data loss — it is a control that reports an affordance it does not have, which is the same class of defect as the old "Open now" switch.

**On the live build this is far worse.** `frontdoor-measure.fly.dev/app` carries 221 places and draws **12 pins and 41 clusters** at street level (largest: 15), **12 pins and 14 clusters** at overview (largest: 36). 209 of 221 places — 95% — cannot be opened from the map at any zoom. The map that an audience sees is mostly numbered discs that do not respond. Neither side is "wrong": the port is faithful, and the design source simply under-represents the data density it will run against, which is why design-side testing under-states this.

**Severity: HIGH.** It is the most tappable thing on the primary screen, and the more real data you load the worse it gets.

## N2 · MEDIUM-HIGH · Tapping a cluster drops focus to `<body>`

**Screen id:** `screen-map`. **Reproduction** — Map → `Tab` to a cluster (or tap one) → read `document.activeElement` after 2.5 s.

**What happened** — `BODY`, at both zoom levels, including the case where the zoom *does* change.

**What should have happened** — the same treatment `openCard` gets. `closeSheets` re-finds the opener by `data-id` after the map re-renders and falls back to the labelled screen so focus is "never left on `<body>`" (its own comment). The cluster path has none of that: `setZoom` calls `renderMap()`, which destroys the focused button, and nothing restores anything.

A screen-reader user who activates a cluster is put on `<body>` with no announcement of what, if anything, happened. Combined with N1 that is: no visible change, no audible change, and no focus.

## N3 · HIGH · 45 of 64 places tell the user the entrance was "last scanned", when it has never been scanned

**Screen id:** `screen-map` → entrance card. **Reproduction**

1. Map → open any **Estimated** pin whose evidence is older than 24 months (45 of the 64 places; e.g. "Austin Budget Office", "Live BEE HIVE").
2. Expand the card.

**What happened** — the re-check nudge reads:

> Could you take another look?
> 🕑 **Last scanned 11 years ago**
> A fresh photo helps everyone plan with confidence.

and three lines away the same card reads *"No photo yet — be the first to scan"*, *"Not yet seen — be the first to scan."*, and *"Estimated by AI from street imagery · Jan 2016"*.

**What should have happened** — an estimated place has never been scanned. The date is the street-imagery date. The copy should say what the freshness row already says ("street imagery"), not "scanned".

**Cause.** `cardHTML`, line ~4707: the nudge is gated on `if(p.tier==='est' && aged)`. It is shown **only** on the tier where "scanned" is never true. `ageLabel(p.date)` is correct; the word before it is not.

**Reach:** 45 of 64 places in the design build (70%), **192 of 221 on live** (87%). Identical copy on both sides.

**Severity: HIGH,** because this product's entire premise is that the trust tier is honest. This is the one place in the build where a lower tier describes itself as a higher one.

## N4 · MEDIUM · The receipt for a scanned place publishes a negative accessibility verdict about a named business

Covered in full as **H1** under the honest-criteria checks below, because it fails one of the three stated criteria outright. Listed here so the defect count is not understated.

## N5 · MEDIUM · An estimated place silently drops any feature the model actually checked and did not find

**Screen id:** entrance card. **Reproduction**

1. Map → open "Austin Budget Office" (`est` tier). Its raw data is `handrails: absent`, everything else `not_visible`.
2. Read the card.

**What happened** — the card's "Not yet seen — be the first to scan." softlist reads:

> Step-free entry · Ramp or bevel · Auto-door button · Easy-grip handle · Clear approach · Access signage · Wide door

Seven of the eight features. **Handrails is absent from the list**, and appears nowhere else on the card. The pin's accessible name says "Nothing confirmed yet."

**What should have happened** — either handrails appears in the "not yet seen" list, or it gets the treatment a scanned place gives it. On the `scan` tier the same value renders correctly and non-negatively:

> **COULDN'T CONFIRM YET** — Ramp or bevel · Handrails · Auto-door button · Access signage — not spotted in this scan. Help us take another look.

**Cause.** `cardHTML` gates that block on `if(p.tier!=='est' && checked.length)`. `normV` maps `absent → 'checked'`, and `unknown` is computed as `!p.f[k] || p.f[k].v==='unknown'` — so on the est tier a `checked` feature belongs to neither bucket and is rendered nowhere.

**Reach:** 33 of 52 estimated places (63%) drop at least one feature this way. The list that claims to enumerate what has not been seen silently omits something that *was* looked at.

## N6 · LOW-MEDIUM · "Show 1 places", "Show 0 places" — the filter button never pluralises

**Screen id:** `sheet-filters`. **Reproduction** — Map → Filters → Reset → select all eight chips → drag Walking distance to 200 ft.

**What happened** — the primary button reads **"Show 1 places"**. Add the 7-day freshness window and it reads **"Show 0 places"**.

**What should have happened** — "Show 1 place". The app pluralises correctly everywhere else it counts (`1 entrance · 1 business`, `5 neighbors`, `n===1?'':'s'` in the processing announcement), which makes this the odd one out.

**Cause.** `updateFiltShow()`, line 5406: `textContent = 'Show ' + filtCount() + ' places'`.

**Why it is worth fixing before a demo:** it is the largest, highest-contrast text on the sheet an audience is most likely to drive, and reaching it takes four taps.

## N7 · LOW-MEDIUM · The skip link counts clusters as pins, and offers to skip zero of them

**Screen id:** `screen-map`. **Reproduction** — `Tab` from the top of the map and read the skip link's accessible name; then apply a filter that returns nothing and read it again.

**What happened** — default map: *"Skip the **21** map pins and go to the bottom navigation"* — but there are 12 pins and 9 clusters. On the live build: *"Skip the **53** map pins"* for 12 pins and 41 clusters. With a zero-result filter applied: *"Skip the **0** map pins and go to the bottom navigation"*, offered to a keyboard user as the first stop on an empty map.

**Cause.** `renderMap`: `pinsEl.querySelectorAll('.pinbtn,.cluster').length`, with no zero case and no distinction between a mark you can open and a mark you cannot.

## N8 · LOW · `setGate2` is still unreachable, so the fourth processing beat and its caption cannot occur

Carried forward from A8 and re-confirmed at Round 7. `function setGate2(on)` is defined and **called from nowhere**; `gate2` is `false` for the life of the page. Consequences, measured through a full scan: `#ck-4` ("Double-checking") stays `hidden`, `#proc-caption` is permanently "Usually under 8 seconds", and `procRun.extend()` — the whole re-basing branch that exists so an extension never rewinds the ring — is dead code. Round 6 rewrote `runProcessing` around readiness and preserved the extension machinery without noticing nothing can trigger it.

## N9 · LOW · Stale comments left by the two rounds that changed the numbers underneath them

- `renderMap`, above the pin loop: *"`--mh` drives the **44x44** tap target and the label offset"*. `--tap` is **48 px** since Round 7 and the measured `::before` is 48 × 48.
- Line 264: `--track:#867F99; /* DERIVED: indigo900 -> white 46.2%; 3.00:1 on the worst light surface */`. Measured, `#867F99` is **3.45:1** against the kit land `#F5F2FC` and **3.81:1** against white. The self-documented figure is stale in the safe direction, but the previous report flagged this token as the thinnest surviving margin in the build and a future round reading "3.00" will treat it as untouchable when it has 15% of headroom.

---

# Part three — the three honest-criteria checks

## H1 · **FAILS** — a public negative verdict is rendered, about a named business, in three taps

**Criterion:** no public negative verdict anywhere.

**Screen ids:** `screen-map` → `sheet-card` → `sheet-receipt`. **Reproduction**

1. Onboard to the map.
2. Open **Austin Transit Partnership** (`door-09`) — one of the twelve individual pins on the default map, also the first row of the list view.
3. Expand the card and tap **See the evidence receipt** (or the photo strip).
4. Read the body paragraph.

**What happened** — the receipt renders, in plain body text at full size:

> "The doors have good graspable pull handles, but they sit on a raised concrete landing with a railing across the front and no visible ramp, **so a wheelchair user likely cannot get to the door directly.**"

**What should have happened** — the app's own model forbids exactly this. `normV` maps `absent → 'checked'` with the comment *"seen, not spotted — never rendered negative"*, and the card for this same door renders those features as *"COULDN'T CONFIRM YET … not spotted in this scan. Help us take another look."* The receipt then contradicts the card about the same door, in the direction the rule prohibits.

**Scope, measured across the whole dataset.** Seven places carry negative-verdict prose in `p.note`, which `cardHTML`/`receiptHTML` render verbatim through `esc()` at line 4942:

| Place | Tier | Rendered text |
|---|---|---|
| **Austin Transit Partnership** | scan | "…no visible ramp, so a wheelchair user likely cannot get to the door directly." |
| DeSano Pizzeria Napoletana | scan | "…there is no automatic door button or accessibility signage…" |
| CardVault by Tom Brady | scan | "…there is no automatic door button or accessibility signage…" |
| Royal Blue Grocery | scan | "…there is no automatic door button and no accessibility signage…" |
| Cathy's Cleaners and Alterations | scan | "…there is no automatic door button and no accessibility signage…" |
| Bill's Oyster | scan | "…there is no automatic door button, no accessibility signage…" |
| RedFarm | scan | "…there's no automatic door button or accessibility signage…" |

Royal Blue Grocery is the pilot door the entire owner workspace is bound to — the one an owner demo lands on.

**Identical on the live build** (`places.filter(p => /cannot/i.test(p.note))` → `["Austin Transit Partnership"]`, same string). Neither side is wrong relative to the other; the design source is the origin.

**What is clean:** the *renderable* per-feature evidence strings are fine. Of the 14 `f.e` values on `present` features that match a negative-word regex, all 14 are positive findings phrased with a negative word ("no riser shadow", "no shadowed riser edge"). The `e` strings attached to `absent` features — including "so no handrails serve it" — are never rendered, because only `present` features get a chip with `data-ev`. The defect is confined to `p.note`, and to seven records.

**Severity: HIGH.** This is the single worst finding in this sweep. It is not a rendering bug, it is prose in the shipped payload that states a named business is unusable by a wheelchair user, on a product whose stated rule is that it never publishes a negative verdict.

## H2 · **PASSES** — `not_visible` is never rendered as absent

**Reproduction** — open a `scan` place with all three raw states present. `DeSano Pizzeria Napoletana` has `step_free_entry: present`, `ramp_present / handrails_present / auto_door_button / accessible_signage: absent`, `door_width_adequate: cannot_tell`.

| Raw | `normV` | Rendered as |
|---|---|---|
| `present` | `present` | **SEEN AT THIS DOOR** — Step-free entry, Easy-grip handle, Clear approach |
| `absent` | `checked` | **COULDN'T CONFIRM YET** — Ramp or bevel · Handrails · Auto-door button · Access signage — "not spotted in this scan. Help us take another look." |
| `cannot_tell` / `not_visible` | `unknown` | **"Not yet seen from these photos."** — Wide door |

Three distinct buckets, three distinct wordings, none negative, and `not_visible` never lands in the `absent` bucket. The pin's accessible name lists only what was seen. On the `est` tier the invite becomes "Not yet seen — be the first to scan." The one gap is the opposite direction and is filed as N5.

## H3 · **PASSES** — no trust pin is recoloured, and the Texas record never decorates a pin

**Pin invariance, measured at runtime.** For each tier I rendered six variants — plain, selected, match good, match partial, match unknown, selected + match — and extracted the fill/stroke/stroke-width of every filled `path` plus the three confidence dots:

| Tier | Distinct body signatures across all 6 variants | Body |
|---|---|---|
| est | **1** | `fill #FFFFFF · stroke --blue-edge #1B6599 · 4` |
| scan | **1** | `fill --marigold #FDB327 · stroke --marigold-edge #1E1142 · 4` |
| owner | **1** | `fill --purple #4F34DB · stroke #FFFFFF · 4` |

Selection is a size change, a 6 px lift and a keyline drawn **outside** the head (white r59, indigo r65, against a head radius of 36). Match is a ring at r50 whose primary carrier is line style — solid, dashed, dotted — not colour, and the words are printed too. Freshness touches nothing on the pin (`renderMap` has no aged/stale branch). Provenance touches nothing on the pin. Non-match recession is `opacity:.8` and nothing else. In High Contrast the pin fills are byte-identical (`rgb(79,52,219)`, `rgb(253,179,39)`).

**Cluster:** indigo900 disc, white ring, white count. None of those is any tier's colour, so a cluster cannot impersonate a tier. The count, not the arc ring, is the carrier, and the mix is spoken in full in the accessible name.

**Texas record.** `TABS_PLACE.tabs = {year:2019}` is set on `door-04` only. It is referenced in exactly three render sites — the card's provenance row, the receipt row, and the owner listing's state row — and in none of them does it touch `pinSVG`, `renderMap`, or any pin class. Driven: the receipt shows it as one row reading *"Texas accessibility inspection on record · 2019 — independent state record — informs the receipt, never the pin tier"*. The map pin for `door-04` is byte-identical to every other `scan` pin. **Passes cleanly.**

---

# Part four — change audit: what Rounds 6 and 7 did to the file

## A1 · Round 7's numeric claims, re-derived from the file rather than believed

| Claim in the Round 7 commit | Re-measured | Verdict |
|---|---|---|
| 7:1 body-contrast floor, "0 … below the floor, minimum 7.38:1" | Independent sweep: **925 body-text samples** (403 across all 26 screens, 522 across map overlays, five sheets, the receipt, the list view and the search overlay). **0 below 7:1. Minimum exactly 7.38:1.** | **TRUE** |
| "White on the primary violet rises … to 7.38:1" | `--purple` is `#4F34DB`; white against it computes **7.378:1** | **TRUE** |
| Same floor holds in High Contrast | Re-ran the 26-screen sweep with `.phone.hc`: **0 below 7:1, minimum 7.38:1**; 2,596 of 4,000 sampled elements change colour, so HC is a real mode, not a no-op | **TRUE** |
| "48 × 48 targets (0 of 882), after fixing the filter Reset at 45.8 × 48" | `#filt-reset` measures **48 × 48**. My sweep of every visible interactive target across 26 screens plus the map, five sheets, the list view and the search overlay found **227 targets, 3 below 48**: the radio and checkbox inputs in `claim-confirm`, drawn at 20 × 20 inside `<label>` wrappers of 94 / 75 / 48 px, so the effective target is compliant. The eight `label[for]` elements at 15–19 px all point at controls ≥48 px. | **TRUE in substance**, but **882 is not reproducible** from live geometry — I count 227. A round that states a count should say what population it counted. |
| "`lavender-path` … only the map may use" | `grep -c "var(--lavender-path"` returns **3**: `--g-block-edge`, `--g-road-edge`, and the match-halo disc in `pinHalo`. All three are map. Zero UI rules resolve it. | **TRUE** |
| "Two pre-existing defects found and fixed: … turning on High Contrast before opening the map left the map blank" | HC on → navigate to the map: `#map-ground` renders **61 shapes**, 12 pins, 9 clusters. Not blank. | **TRUE** |
| "Two pre-existing defects … closing the map card left focus stranded" | 14/14 correct focus returns across Escape, close button and scrim, once rAF latency is accounted for | **TRUE** |

Seven of seven Round 7 claims spot-checked hold, one with a caveat about an unreproducible population figure. That is a marked improvement on the previous audit, where two of five were materially false.

## A2 · Previous audit findings, re-derived

| # | Previous audit finding | Status |
|---|---|---|
| A1 | The reduced-motion blanket omits `transition-delay` | **FIXED** — both delay properties zeroed; the duplicate `@media` block deleted |
| A2 | Round 2's `outline:none` for pins was dead on arrival | **STILL OPEN** — see S7; Round 7 recoloured the artifact without seeing it |
| A3 | Two of five spot-checked round claims materially false | **UNCHANGED, and now contradicted by the file itself.** Heaviest font weight: 25 `var(--fw-display)` + 3 SVG `font-weight="800"` = **28** sites, against the claimed 21. Hand-drawn icons: `ICONS` holds **27** entries against `LIB_ICONS`' 30, zero overlap — against the claimed 4. The file's own comment now says "the twenty-seven that remain here", so the file is honest and only the round report is wrong. |
| A4 | Zero-non-ASCII regressed (9 bytes) | **FIXED** — 0 bytes > 127 in the whole file. `t === '‹'` / `'✕'` are now `'‹'` / `'✕'`, matching the 155 escapes used everywhere else |
| A5 | `.ow-locked .lk-icon` declared twice; `.saved-row .rowicon{width}` beaten by `flex-basis` | **FIXED** — the duplicate `background:#fff` is gone, only the shared `--icon-box` rule remains; `.saved-row .rowicon` is now `{background:none}` alone |
| A6 | Dead CSS whose markup a later round removed | **FIXED** — `.persona .p-ring`, `.state-card .sc-icon`, `.ob-word` family and `.receipt-note` all return 0 occurrences |
| A7 | Round 2's canonical type scale bypassed everywhere | **STILL OPEN** — `.t-display` 0 uses, `.t-h1` 0, `.t-h2` 0, `.t-h3` **1**, `.t-body` 0, `.t-sub` 0, `.t-meta` 0, `.t-micro` 0. The `.sel-row` rule has been deleted, which is the only movement. Eight declared steps, one heading. |
| A8 | Dead JS and dead data | **STILL OPEN** — `setGate2` still uncalled (filed as N8). `FEATS[k].ic` is still never read: all ten consumers of `FEATS` read `.label`. Orphan ids `correct-photo-title`, `mybiz-sub`, `claim-search` all still referenced by nothing. |
| A9 | Contradictory contrast documentation | **FIXED** — both stale luminance arguments are gone. The `--track` comment is now stale in the other direction; filed as N9. |

## A3 · Categories that came back clean under attack

Recorded because a clean category is a result, and because these are the load-bearing parts of the demo.

- **The owner face-flag publish gate is still unwalkable.** Reached `ow-review` directly via `showScreen('ow-review')` — bypassing Manage photos entirely — and triple-tapped **Publish update**. The gate re-checks independently, bounces to `ow-photos`, moves focus to `BUTTON.ph-btn`, and announces *"Update not published. Photo 3, Doorway with the patio, may show a face. Replace it or crop it to the doorway before publishing."* Zero publishes.
- **No injection anywhere.** `<img src=x onerror="window.__pwn=1">`, `"><script>…</script>`, `'"--><svg onload=alert(1)>` fed to search: `window.__pwn` and `window.__pwn2` both `undefined`, node count *decreased* by 96 (fewer results), and the payload is echoed back as literal text inside the invite copy.
- **Rapid and interleaved taps never desynchronise state.** 24 nav taps with zero settle time across Map/Scan/Profile → exactly one `.screen.active`, correct `aria-current="page"` on one tab only.
- **Sheet races resolve to one sheet.** `#fab-filters` and `#fab-needs` tapped in the same task → exactly one sheet `on`, scrim on, 35 inert nodes, focus on the correct heading. Escape → 0 sheets, **0 inert**, focus restored.
- **Opening a sheet and navigating in the same task is clean.** `#fab-filters` then `#nav-profile` → screen-profile, 0 sheets, 0 inert, scrim off, focus on the screen.
- **Double-tapping a pin opens exactly one card.**
- **Every toggle keeps `aria-checked` and its class in sync.** 22 stateful controls across all 26 screens were driven and reverted; **0** changed their reported state without changing anything else. One notification switch driven 10× consecutively stayed consistent.
- **Leaving a scan mid-flow is clean** — exited `scan-processing` mid-run, idled 2.5 s on Profile, no stale-timer yank, timers cancelled.
- **Zero-result filtering invites rather than shames.** All eight chips + 200 ft + 7 days → 0 pins, `map-empty` on, "No entrances mapped here yet. Be the first to help neighbors plan ahead.", full removable chip row.
- **The claim gate is intact and accessible** — see S5.

## A4 · Behaviour a later round undid — nothing found

I looked specifically for the highest-risk class. `git diff 2d61070..eb056fe` shows Round 7 deleted no event handler, no `setAttribute`, no `aria-*`, no `.focus()`, no `announceUI` and no `inert` call. The two functions it rewrote (`pinHalo`, `gc`) are both drawing code, and the halo change is an explicit, argued correction of Round 6 against the shipped exports. `announce()` and its single call site in `finish()` are byte-identical across `896895c` → `b636147` → `e0fceb6` → `eb056fe`. Round 6's rewrite of `runProcessing` from timers to readiness preserved the announcement, the watchdog and the progress semantics.

The one thing Round 7 *did* silently carry forward is S7 — it recoloured a rule that has never had any effect. That is a seam defect, not a removal.

---

# Part five — design source vs the live build

Both were driven. The live page is a **generated superset**: `src/frontdoor_server/app.html`, produced by `tools/port_app_page.py` with wiring applied as an ordered transformation. Every Round 7 marker is present on both sides (`grep -c "ROUND 7"` → 10 and 10; `lavender-path` → 8 and 8; the dead `.pinbtn:focus-visible{outline:none}` → 1 and 1).

**Where they differ, and which side is wrong:**

| Difference | Which side is wrong |
|---|---|
| Live has 27 screens; the extra is `claim-workspace`, the wired owner workspace behind `GET /claim/<id>/workspace` | **Neither.** Server-owned surface, correctly absent from the design. |
| Live drops the `#claim-phone` field and hides `#claim-email` on the call route; validation is email-only | **Neither, and live is arguably better.** Its comment reasons that a typed phone number would be "input presenting itself as authority", so the call route uses the number the listing already carries. No null-deref: `claimPhone` is not referenced anywhere in the live JS. |
| Live adds an entrance-name field and datalist on the review screen, and a `.sim-tag` for unwired runs | **Neither.** Server contract. |
| Live carries 221 places against the design's 64 | **The design source is the weaker test surface.** Its 64-place dataset hides how badly N1/N2 scale. |
| N1 (dead cluster tap), N2 (focus to body), N3 ("Last scanned"), H1 (negative verdict), S7 (focus artifact), N6 (pluralisation) | **Both, identically. The design source is the origin, so fix it there and re-port.** |

I found no defect present on one side and absent on the other. The port is faithful.

---

# Verdict — is this stable enough to put in front of an audience?

**Not yet — but the gap is now four specific items, and two of them are one-line copy changes.**

Rounds 6 and 7 did real work. Eight of the thirteen defects in the previous report are genuinely fixed and were fixed at the mechanism, not at the symptom: reduced motion no longer keeps a delay it should not have and no longer has two copies of itself to drift apart; the card sheet is a tracked gesture rather than a modulo counter; the search overlay traps what it claims to trap; the claim form validates the channel it will actually use; nothing squashes at the largest text. Seven of seven Round 7 numeric claims spot-checked hold — including the 7:1 floor, which I re-derived independently at 925 samples and got the same 7.38:1 minimum to the second decimal. That is a real change from the previous audit, where two of five claims were false in the flattering direction, and it is worth saying plainly.

The build also survives being attacked. The owner face-flag gate cannot be reached around. Nothing injects. Twenty-four interleaved nav taps, racing sheets, double-tapped pins, opening a sheet and navigating in the same task — all settle to exactly one correct state with inert cleared and focus in the right place. Twenty-two stateful controls were driven and none of them lied about what they had done.

What stands between it and an audience:

**Must be true before it is shown:**

1. **H1 — the negative verdicts come out of the payload.** Seven `note` strings publish what the app's own model forbids, and one of them says a named transit agency's door "likely cannot" be reached by a wheelchair user. It is three taps from the default map, and the pilot door the owner demo is bound to carries a milder version of the same thing. On a product whose thesis is *we never publish a verdict*, this is the sentence that ends the demo. It is a data edit, not a code change.
2. **N3 — "Last scanned" stops appearing on places that have never been scanned.** 70% of the design dataset, 87% of live. One word, in one template literal, on the one tier where the word is always false — and it sits three lines above "be the first to scan" contradicting itself.
3. **N1 — clusters either open or stop saying they will.** On live, 95% of places are behind a cluster that does nothing. Either add a zoom level that resolves them, or make the tap open the list filtered to that cluster's members, or change the label. Any of the three is better than the current promise.
4. **N2 goes with it** — whichever fix N1 gets, the tap must land focus somewhere. `closeSheets` already contains the pattern to copy.

**Should be true:**

5. **N6** — "Show 1 places" is four taps from the map and is the biggest text on the sheet.
6. **S7** — two selectors gain `.phone ` and the stray focus artifact on every pin and cluster goes away. It is visible to anyone demonstrating keyboard navigation.
7. **N7** — the skip link should not offer to skip 0 pins, and should not call a cluster a pin.

**Can wait:** N5, N8, N9, S12, S13, and A7/A8's dead type scale, dead `FEATS.ic` field and three orphan ids. These cost the next round time; they cost the audience nothing. S13 still deserves a real-device check before anyone scans on stage, because it cannot be settled in this environment.

**One caveat on this verdict.** Four of my own findings were withdrawn during the sweep, three of them because the instrument was lying rather than the build: a global I clobbered, a drag with no elapsed time, and a `requestAnimationFrame` that fires 892 ms late in a pane that is not compositing. The last of those would have been reported as the build's worst accessibility regression if I had stopped at a 700 ms sample window and 12 trials, and it would have been wrong. Every reproduction above is written to be re-run against whatever ships; re-run them rather than trusting this file, and check for foreign globals in the tab before you start.
