# EntryMap prototype — accessibility re-audit, Round 7

_Produced by the a11y-auditor agent on 2026-09-05 and saved verbatim by the orchestrator; the agent declined to write the file itself._

**File tested:** `design/phone-app-prototype.html` at commit `eb056fe`
**md5 of the bytes tested: `87f681d8778e8d2cecf01d693ffae6fc`** (7,200 lines, 26 screens + 7 sheets + search overlay)

**Provenance note, important.** Mid-audit the working copy changed — Round 8 preparation was committed (`658d5fc`), and `design/phone-app-prototype.html` on disk became `d05c8aef347251cf07367c50570af4cd`. The auditor therefore extracted `eb056fe` to a scratch directory, served it on `http://127.0.0.1:8791/`, verified the served bytes hash to `87f681d8…`, and **re-ran every headline measurement against that pinned copy**. Every number below is from the pinned `eb056fe` build unless marked otherwise.

**Method.** Served over `python -m http.server`, driven at 390×844 (`@media (max-width:767px)` real-phone mode, `matchMedia` confirmed, `#phone` measured 390×844). Every screen and sheet entered through the app's own controls where a control exists. Evidence from the live DOM: WCAG relative-luminance maths with alpha compositing and paint-order reconstruction via `elementsFromPoint`; `document.activeElement` sampled across real transitions; live-region mutation observers with timestamps; `requestAnimationFrame` sampling for sub-frame timing. Reduced motion, high contrast and text size were toggled **through the app's own switches, mid-flow**, not by setting classes.

**Live copy cross-check:** `https://frontdoor-measure.fly.dev/app` — same tokens (`--ink #1E1142`, `--ground #FFFFFF`, `--tap 48px`, `--purple #4F34DB`), 27 screens (one extra: `claim-workspace`). It reproduces the high-contrast map-ground blank (N5) independently, so that one is not a local artefact.

---

## Verdict

Round 7 closed **all ten** blocking defects from the previous audit and **fourteen of eighteen** improvements. The two things that were most wrong last time — silent screen changes and silently blocked publishes — are now among the best-built parts of the file. The contrast work is genuinely finished: **zero** text/ground pairs below the package's 7:1 floor in either contrast mode, and **zero** focus indicators below 3:1 in normal mode.

What is left is thinner and lives in seams. The three that matter are a **~5% intermittent focus-return failure** on sheet close, a **100%-reproducible loss of the place card** when you close a sheet opened from it, and a **capture coach that auto-updates every 1.7 s forever and which reduced motion does not stop**.

- **3 blocking defects**
- **15 improvements**
- **16 things confirmed correct** and re-measured — protect these

Round 6's reduced-motion catastrophe (0/12 → 12/12 sheet focus failures) has **not** returned. Focus entered the sheet on **60 of 60** open events across both motion modes, and on 12 of 12 with reduced motion + high contrast + Larger text all on simultaneously.

---

# Part 1 — Status of every prior finding

## Blocking defects — 10 of 10 fixed

| # | Prior finding | Status | Evidence measured now |
|---|---|---|---|
| **B1** | Every screen change silent, focus dropped | **Fixed** | All 26 `.screen` elements are `<section tabindex="-1">` with an `aria-label`. `showScreen()` calls `scr.focus({preventScroll:true})`. Walked Profile → primer → capture → processing → review: `document.activeElement` was the labelled `SECTION` after **every** transition (previously `BODY` on 4 of 5). |
| **B2** | Toast not a live region; two publishes silently blocked | **Fixed** | `toast()` now calls `announceUI(msg)`. Both blocked publishes replaced by inline errors. Claim: `#claim-authz` gets `aria-invalid="true"`, `aria-describedby="claim-authz-err"`, focus moves to the checkbox, `#sr-announce` = *"Claim not submitted. Please confirm you're authorized to manage this listing."* Owner photos: `aria-invalid` on the offending `.ph-btn` **and** `#photos-publish`, focus moves to *"Crop photo 3, Doorway with the patio, to the doorway"*, announced in full. Toast also now `white-space:normal` — at Larger text it wraps to 71 px tall, `scrollWidth 358 = clientWidth 358`, no truncation. Dismiss timer 2800 → 4200 ms plus swipe-to-dismiss. |
| **B3** | Checklist announces three completed checks before any has run | **Fixed** | `<ul class="checklist" role="list">`, every `.ci-dot` `aria-hidden="true"`, each `<li>` carries `<span class="sr-only ck-state"> — not checked yet</span>`. Accessible text at t=0 is *"Doorway framed — not checked yet"* ×3. Sampled the real run at 300/1200/2400/3600/4800/5600 ms: the `.done` class and the state text flip **together, every time**. The `.p-ring` and `.tl-dot` leaks are gone too. |
| **B4** | Match never reaches the pin; 64 pins ahead of every control | **Fixed** | Pin `aria-label` is now the full `renderList()` sentence. Tab order on the map: `#locpill, #search-btn, #head-profile, .achip, #legend, #list-toggle, #zoom-toggle, #locate-btn, #fab-needs, #fab-filters, …` then pins. Total focusables 82 → **43**. A labelled skip link (`#skip-pins`) works and announces *"Skipped the map pins. Bottom navigation."* |
| **B5** | Sheets: no focus in, no return, no trap, no Escape | **Fixed** (one residual, see N1/N2) | All six modal sheets: `role="dialog" aria-modal="true"`, focus lands on `H3.sheet-h` within 50 ms, `setBackgroundInert(true)` leaves **0** focusables outside, Tab and Shift+Tab wrap inside, Escape closes. Focus return to opener verified 9/9 across Escape × Close × scrim on three sheets. |
| **B6** | Row buttons carry `role="listitem"` | **Fixed** | `#saved-list` and `#your-scans` are `UL role="list" > LI > BUTTON`, no role override anywhere. |
| **B7** | Seven sub-3:1 indicators; focus ring fails on dark screens | **Fixed, all 12 rows** | Toggle off track `#D9D5EC` 1.43 → `#706887` **5.23**; field/chip borders 1.27 → **5.23** at 2 px. All three pin tiers carry a ≥3:1 keyline against every map ground. Focus ring is genuinely two-tone and measures ≥3:1 on all four sides for **149 of 149** controls in normal mode. |
| **B8** | Current nav tab exposed to nothing; 1.05:1 hue change | **Fixed** | `aria-current="page"` plus a 70 × 4 px `#76BCFD` indicator bar at **8.55:1** against the `#1E1142` navbar. |
| **B9** | Card grip 390×26, no `aria-expanded`, `role="dialog"` on a non-modal card | **Fixed** | `#card-grip` is **390 × 48**. `aria-expanded` false/true/true across peek/medium/full. `#sheet-card` is now `role="region" aria-label="Place details"`. Each position change announces what was added. |
| **B10** | Freshness segment and claim rows expose no state | **Fixed** | `#filt-fresh` is `role="group"` with `aria-pressed`. `#claim-results` is `role="radiogroup"` with `role="radio"`, `aria-checked`, roving `tabindex`, arrow keys, and a visible filled tick. |

## Improvements — 14 of 18 fixed, 4 partial

| # | Prior finding | Status |
|---|---|---|
| **I1** | Navbar focusable under onboarding | **Fixed** — `#navbar` gets `inert` on any `ob-*` screen. |
| **I2** | Decorative glyphs exposed and under 3:1 | **Fixed** — chevrons are `aria-hidden` SVG with no text node. |
| **I3** | Map street labels leak into the tree | **Fixed** — `#map-ground`, `#mini-map`, `#ow-mapground` all `aria-hidden`. |
| **I4** | Seven `aria-label`s on roleless generics | **Fixed** — zero remaining. |
| **I5** | Headings thin and out of order | **Partial** — 19 of 26 screens still have no `<h1>`. See N7. |
| **I6** | Coach is an unbounded polite live region | **Partial** — `aria-live` removed, one announcement on entry. Visible text still rotates every 1.7 s. See N3. |
| **I7** | Feature chips are disclosures with no semantics | **Fixed**, one bug — `id="ev-box"` is duplicated. See N6. |
| **I8** | Confidence is dots-only | **Fixed** — `.dots` `aria-hidden` with a `.sr-only` sibling. |
| **I9** | Two targets under 44 px | **Fixed** — `#card-grip` 390×48; `#search-clear` hit area 48×48. |
| **I10** | Ambiguous Replace/Remove names | **Fixed** — all six distinct. |
| **I11** | List rows announced twice | **Fixed** — inner spans `aria-hidden`. |
| **I12** | Slider announces a number | **Fixed** — `aria-valuetext="Within 500 feet"`. |
| **I13** | No roving tabindex on tabs | **Fixed**. |
| **I14** | "needed" badge is CSS generated content | **Fixed** — a real element inside `textContent`. |
| **I15** | Larger text is only +16% | **Partial** — 15 / 16.2 / **18.9 px** (+26%). See N14. |
| **I16** | Timed content with no user control | **Partial** — toast and processing gap fixed; splash and coach unchanged. |
| **I17** | `<label for>` pointing at a `<button>` | **Fixed**. |
| **I18** | `role="progressbar"` on `display:contents` | **Fixed**. |

---

# Part 2 — Contrast, measured

## 2a · Text on its ground — the 7:1 floor

| Mode | Text/ground pairs | Below 4.5:1 | Below 7:1 (**package floor**) | Lowest ratio |
|---|---|---|---|---|
| Normal | **269** | **0** | **0** | **7.38:1** |
| High contrast | **272** | **0** | **0** | **7.38:1** |

The floor in both modes is one pair: **white on `--violet600 #4F34DB` = 7.38:1**, every `.btn.primary` label, `#fab-needs-label` and `.ph-tag`. It clears 7:1 by 0.38, and **high contrast does not raise it**.

| Element | Normal | High contrast |
|---|---|---|
| Screen title `--ink #1E1142` on white | **17.30** | 19.33 |
| Body `--sub #463B63` on white | **10.16** | 17.30 |
| Body `--sub` on `--wash-quiet #F9F7FD` | 9.56 | 15.34 |
| Body `--sub` on `--blue-wash #E6F3FF` | 9.02 | 15.34 |
| **Primary button label**, white on `#4F34DB` | **7.38** | **7.38** |
| Marigold feature chip `#6B4014` on `#FFF0D4` | **7.88** | 12.28 |
| Tier chip "Scanned on-site" on `#FDB327` | 9.60 | 9.60 |
| "Not yet seen" `#1C4B7E` on `#E6F3FF` | **7.90** | 9.57 |
| Location pill white on `--chrome-fill #3E325C` | 11.57 | 11.57 |
| Current nav label `#76BCFD` on `#1E1142` | 8.55 | 8.55 |

**Assessment: pass.** The previous audit's 28 "failures" were all decorative glyphs, now `aria-hidden` SVG.

## 2b · Pins against the new map ground

Three surfaces sit under a pin: **road `#FFFFFF`**, **land `#F5F2FC`**, **block `#E8E1F7`**. Every pin carries three white lift strokes beneath the body.

| Indicator | vs road | vs land | vs block | Floor |
|---|---|---|---|---|
| Owner pin fill `#4F34DB` | 7.38 | 6.67 | **5.81** | 3.0 ✓ |
| Scanned keyline `#1E1142` 4 px | 17.30 | 15.64 | **13.63** | 3.0 ✓ |
| Estimated stroke `#1B6599` 4 px | 6.24 | 5.64 | **4.91** | 3.0 ✓ |
| Cluster disc `#1E1142` | 17.30 | 15.64 | **13.63** | 3.0 ✓ |
| Good-match halo `#1E1142` solid | 17.30 | 15.64 | **13.63** | 3.0 ✓ |
| Partial-match halo `#4F34DB` dashed | 7.38 | 6.67 | **5.81** | 3.0 ✓ |
| Halo backing disc `#CFBCEE` | 1.74 | 1.57 | 1.37 | decorative only |

**Every pin tier and halo state clears 3:1 against every ground.** Previous audit had rows at 1.18, 1.79 and 2.75. Fully fixed.

Good vs partial halo colour alone is 2.34:1, differentiated by line style and legend, so colour is not the sole carrier. See N8.

## 2c · Non-text UI indicators

| Indicator | Normal | High contrast | Floor |
|---|---|---|---|
| Toggle OFF track vs card | **5.23** | **5.76** | 3.0 ✓ |
| Toggle ON track vs card | **7.38** | **12.73** | 3.0 ✓ |
| Input / select border 2 px | **5.23** | **4.54** | 3.0 ✓ |
| Filter chip (off) border | **5.23** | **5.76** | 3.0 ✓ |
| Nav current-tab bar vs navbar | **8.55** | **8.55** | 3.0 ✓ |
| **Processing ring fill vs track** | **2.12** | — | 3.0 ✗ (N10) |
| **Feature chip marigold border vs card** | **1.80** | **1.80** | 3.0 ✗ (N11) |
| **Map ctl / FAB disc vs map ground** | 1.00–1.27 | 1.26 | 3.0 ✗ (N9) |

## 2d · Focus indicators

| Mode | Controls | Sides below 3:1 | Worst whole-ring |
|---|---|---|---|
| **Normal** | **149** | **0 of 149** | **4.91:1** |
| **High contrast** | **149** | **2 of 149**, one side each | 1.12 bottom edge only; other three sides 15.23 |

The two HC exceptions are `#btn-claim-submit` and `#photos-publish`, whose bottom ring edge meets the `#1E1142` dock with no white companion shadow on that path.

**Correction to the auditor's own working notes:** measuring the outline alone made `ob-welcome`'s two buttons look like a 2.02:1 / 1.00:1 failure, which would have been the headline. It is not — the 6 px `#1E1142` shadow ring carries it at **17.30:1** in both modes.

---

# Part 3 — Target sizes against the 48 px floor

Effective hit area, `getBoundingClientRect` unioned with any pseudo-element that expands the box. **189 distinct interactive controls** measured.

| Bucket | Count |
|---|---|
| ≥ 56 px on the short side | 28 |
| 48–55 px | 159 |
| 44–47 px | **0** |
| < 44 px | **3** (2 signatures) |

The three exceptions are native inputs on `claim-confirm`, each 20 × 20 px, each wrapped in a `<label>` that is the real target (358 × 65.6 and 358 × 48). **The 48 px floor passes, 189 of 189 by effective target.**

Previously-failing controls now: `#card-grip` **390 × 48**; `#search-clear` hit area **48 × 48**; `.pinbtn` and `.cluster` **48 × 48** via `::before`; `.toggle` **52 × 48**.

---

# Part 4 — Focus order and destination

## 4a · Into every sheet

| Sheet | Focus at 50 ms | Focusables outside | Tab wraps | Esc closes |
|---|---|---|---|---|
| `sheet-needs` | `H3.sheet-h` | **0** | ✓ | ✓ |
| `sheet-filters` | `H3.sheet-h` | **0** | ✓ | ✓ |
| `sheet-trust` | `H3.sheet-h` | **0** | ✓ | ✓ |
| `sheet-receipt` | `H3.sheet-h` | **0** | ✓ | ✓ |
| `sheet-correct` | `H3.sheet-h` | **0** | ✓ | ✓ |
| `sheet-privacy` | `H3.sheet-h` | **0** | ✓ | ✓ |
| `sheet-card` (non-modal by design) | `H2.card-name` | 34 (intended) | n/a | ✓ |
| `#search-ov` | `INPUT#search-in` | 10 (own) | ✓ | ✓ |

**Focus entered on 60 of 60 open events** across both motion modes, and 12 of 12 with reduced motion + high contrast + Larger text simultaneously.

## 4b · Out of every sheet — the matrix

`n=5` per cell, `sheet × {Escape, Close, scrim} × {RM off, on}`.

| | Escape | Close | Scrim | Total |
|---|---|---|---|---|
| **RM off** — needs / filters / trust | 1 fail / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | **1 of 30** |
| **RM on** — needs / filters / trust | 1 fail / 1 fail / 0 | 0 / 0 / 0 | 0 / 0 / 0 | **2 of 30** |

**60 trials, 3 focus-return failures (5%). Reduced motion does not change the rate.** In every failure `activeElement` was `H3.sheet-h` — the heading of the sheet that had just closed. See N1.

## 4c · Into and out of every screen

Focus landed on the labelled `<section>` **26 of 26**, both motion modes.

## 4d · Reduced motion is a replacement, not a shortening

With the in-app switch on, every element on all 26 screens swept: `.sheet`, `#scrim`, `.btn`, `#toast` all `transition 0s delay 0s`; `.screen.active animation 0s`. The only survivor is `animation: 0.08s rm-fade` on the body wrappers — opacity only. The processing screen is replaced (ring `display:none`, determinate bar appears). `isReduced()` ORs the OS query with the in-app switch and `applyPrefs()` reflects OS state back into `aria-checked`.

---

# Part 5 — Blocking defects

## N1 · Focus return strands the user on a closed sheet's heading, roughly 1 close in 20

**Element:** `closeSheets()` → `focusWhenReady()` (line 5001), `H3.sheet-h`.

A keyboard or screen-reader user opens Filters, sets a filter, presses Escape. Most of the time focus returns to the Filters button. Roughly once in twenty it does not: focus stays on the sheet's `<h3>`, now inside a `visibility:hidden` container. Nothing to read, nothing to activate, and Tab restarts from the document beginning. Because it is intermittent, the user cannot learn to avoid it.

**Measured:** 60 close events, 3 failures, `activeElement = H3.sheet-h` in all three. Reproduced on `sheet-needs` and `sheet-filters`, via Escape and via Close.

`focusWhenReady` polls for `FOCUS_MAX_FRAMES` then falls back to `.screen.active` — but on the failing runs neither the opener nor the fallback took focus, so the guard is returning false in a window the retry budget does not cover.

**Fix.** Make the return unconditional rather than best-effort: after the budget expires, focus the fallback **without** re-testing `isFocusable` (a `[tabindex="-1"]` labelled section is always focusable), and assert afterwards — if `activeElement` is still inside a `.sheet:not(.on)`, force the fallback.

## N2 · Closing the evidence receipt or the correction sheet destroys the place card and drops focus onto the map pin

**Elements:** `openSheet()` opener capture (line 5059), `closeSheets()`.

A blind user opens a card, expands it to full, reads the provenance, and activates "See the evidence receipt". The receipt opens and reads well. They press Close. The receipt closes — **and so does the card**. Focus lands on the map pin. Everything they had just read, and every action on the card, is gone. Identical for "Suggest a correction".

**Measured — 100% reproducible, both sheets, both close methods:**

```
receipt open   → focus H3.sheet-h "Evidence receipt", sheets on: [sheet-receipt]
receipt close  → focus BUTTON.pinbtn.lvl2 "Sweetgreen…", sheets on: []
                 returnedToOpener ("See the evidence receipt"): false
```

Root cause:

```js
if(!openSheetId && active && active!==document.body) sheetOpener=active;
```

A sheet opened while another is already open is treated as a **hand-off**, so the receipt inherits the card's opener (the pin). Closing returns to the pin and `closeSheets()` clears every sheet including the card. Card → receipt is a **stack**, not a hand-off.

**Fix.** Keep an opener stack. On close, pop one level: re-open `#sheet-card` at its previous position and return focus to the button that opened the sub-sheet. If dismissing the whole stack is intended, announce it — silently destroying the user's context is the part that cannot stand.

## N3 · The capture coach auto-updates every 1.7 s forever, and reduced motion does not stop it

**Element:** `#coach`, `startCoach()`.

A user with a vestibular disorder or a cognitive disability turns Reduce motion on, then opens the scanner — the one screen where they must hold still, aim a camera and dwell. The guidance text changes every 1.7 seconds, indefinitely, with no way to pause, stop or hide it.

**Measured with Reduce motion on:**

```
t=0     #coach = "Center the full doorway"
t=4.2s  #coach = "Step back a little"
isReduced() = true
#coach aria-live = null
```

`setInterval(…, 1700)` with no stop condition and no `isReduced()` guard. WCAG **2.2.2 Pause, Stop, Hide** requires a mechanism for auto-updating content that starts automatically, lasts more than five seconds and is presented in parallel with other content. There is none.

The screen-reader half **is** fixed — `aria-live` is gone, one announcement on entry, nothing for the next 9 seconds. But that means a screen-reader user never hears the updated guidance either, so the rotation buys them nothing and costs everyone else motion.

**Fix.** Under `isReduced()`, stop the rotation and show the guidance as a static list — replace, don't shorten, as the processing ring already does. Independently, add a pause control or stop after one cycle, and announce a genuine state change rather than a timer.

---

# Part 6 — Improvements

**N4 · Under reduced motion the "Checks complete" announcement fires after the app has left the screen.** Traced with timestamps: `nav scan-processing` 6869 ms → `nav scan-review` 6884 ms → `#proc-live` = "Checks complete…" at **6904 ms**, 20 ms after focus already moved to the review screen. With motion off the ordering is correct (1.88 s gap). *Fix:* fire `#proc-live` before the navigation, or drop it.

**N5 · Toggling high contrast blanks the map ground for 2–4 frames.** `#map-ground` contains a single empty `<svg>` for **38.9 / 78.5 / 79.3 ms** after returning to the map. Plain navigation never blanks (sampled 0/40/80/160/320 ms across five runs). `applyPrefs()` re-renders while `#screen-map` is `display:none`, and `groundSVG()` correctly refuses to draw into a zero box, but nothing re-draws until the map is visible. **Reproduced independently on the live copy.** *Fix:* skip the re-render when the map is not laid out; re-render on the map's own visibility.

**N6 · WITHDRAWN by the orchestrator's spot-check — the id is not duplicated.** The audit reported two elements carrying `id="ev-box"`, one in `#ow-listing` and one in `#sheet-card`. Measured against the exact commit audited (`eb056fe`): `id="ev-box"` appears **once**, `aria-controls="ev-box"` once, and `class="…ev-box"` once. There is no duplicate and no misdirected `aria-controls`. Recorded rather than deleted, because a withdrawn finding is evidence about the audit's reliability. One of four claims spot-checked was false, and it erred toward reporting a defect rather than toward success.

**N7 · 19 of 26 screens have no `<h1>` and start at `<h2>`.** With: `screen-map`, `screen-profile`, `scan-capture`, `ob-welcome`, `ob-location`, `ob-needs`, `ow-listing`. Mitigated by every screen being a labelled focusable region, but heading navigation still starts at level 2 on three quarters of the app.

**N8 · Two dash languages on one map.** Estimated pin outline `7px, 6px`; partial-match halo `17.9px, 10.7px`. An Estimated pin with a partial match renders as two concentric dashed strokes meaning two unrelated things. At 32 px the rhythms are not reliably separable. _(Round 8 resolves this: the Estimated mark becomes solid.)_

**N9 · Floating map controls and FABs have no boundary against the map.** `.ctl-btn`, `#fab-needs`, `#fab-filters` are `rgba(255,255,255,.96)` discs with `border: 0px none`. Against the three grounds that is **1.00 / 1.11 / 1.27:1**; high contrast does not add a boundary. *Fix:* a 1–2 px `--edge #706887` hairline.

**N10 · Processing ring fill vs track is 2.12:1.** `#FDB327` on `--track #867F99`. The component is visible; **how far along it is** is not.

**N11 · Feature chip border is 1.80:1 in both modes.** `#FDB327` 2 px on the white card. Label is 7.88:1, so the chip is identifiable; the boundary that says "pressable" is not. *Fix:* border in `--marigold-ink #6B4014` (7.88:1).

**N12 · Two primary buttons' HC focus ring has one invisible side.** Bottom edge 1.12:1 against the dock; other three sides 15.23:1. *Fix:* give `.btn.primary` the white companion shadow.

**N13 · The map location pill truncates at Larger text.** `scrollWidth 118 > clientWidth 98`. The **only** clipped string in the entire build at Larger. `aria-label` carries the full text, so only sighted large-text users are affected.

**N14 · The top text step is +26%, not 200%.** 15 / 16.2 / 18.9 px. Layout survives the top step cleanly, so headroom exists.

**N15 · Applying filters returns focus to the screen container, not the Filters button.** Escape and Close return to `#fab-filters`; Apply does not. The change is announced, so nothing is lost, but two exits from one sheet behave differently.

**N16 · Pin and list-row labels contain a lowercase sentence start.** *"…Owner-confirmed. **n**eeds not yet seen."* Reads as a stumble in every screen reader.

**N17 · The evidence box appears silently.** No `aria-live`, focus does not move into it. `aria-expanded` means it can be found, but nothing signals content arrived.

**N18 · The splash still auto-advances at ~1.2 s** with no way to pause or extend.

---

# Part 7 — Confirmed correct, protect these

**W1** Text contrast clears 7:1 everywhere, both modes; 269/272 pairs, zero below, floor 7.38:1.
**W2** Every screen change announces itself and moves focus; 26 of 26, both motion modes.
**W3** Blocked actions are announced, with inline errors and a focus move — the previous audit's worst defect, comprehensively fixed.
**W4** The processing checklist tells the truth at every instant; class and screen-reader state flip together at all six sample points.
**W5** Sheet focus management is complete: dialog semantics, focus to heading, `inert` leaving 0 focusables outside, wrapping Tab, Escape, return on 57 of 60. Live regions and the toast are explicitly held out of `inert` — a detail most implementations get wrong.
**W6** Reduce motion is a real replacement; only an 80 ms opacity fade survives.
**W7** The 48 px target floor passes, 189 of 189 by effective target; nothing between 44 and 48.
**W8** The focus ring is two-tone and background-aware; 149 of 149 ≥3:1 on all four sides in normal mode.
**W9** Every pin tier and halo state clears 3:1 against every map ground.
**W10** The list view remains the best accessibility work in the file.
**W11** The three-position card genuinely changes what is exposed (4 → 10 → 20 accessible text nodes) and announces what was added.
**W12** Colour is never the sole carrier, on any state.
**W13** ARIA state is correct wherever present: 8 switches, 28 `aria-pressed`, a radiogroup with roving tabindex, WAI-ARIA tabs.
**W14** 271 SVGs, only 2 not hidden or labelled and both empty of text; 19 images, 0 missing `alt`.
**W15** Every form control labelled; zero dangling ARIA references; zero focusable elements inside `aria-hidden`; `<html lang="en">`.
**W16** The search overlay traps properly, inerting siblings at each ancestor level and removing only the flags it set.

---

# Part 8 — Counts

| | Count |
|---|---|
| Screens / sheets audited | 26 / 7 (+ search overlay) |
| Text-on-ground pairs measured | **269** normal, **272** high contrast |
| Text pairs below 4.5:1 | **0** / **0** |
| Text pairs below the 7:1 package floor | **0** / **0** |
| Lowest text ratio in the build | **7.38:1** (both modes) |
| Pin / halo / ground pairs measured | 30 |
| Pin or halo indicators below 3:1 | **0** |
| Non-text UI indicators measured | 23 |
| Non-text indicators below 3:1 | **3** |
| Focus indicators measured | **149** normal, **149** HC |
| Focus indicators below 3:1 (all sides) | **0** / **0** (2 have one side at 1.12) |
| Interactive controls measured for size | **189** |
| Controls below the 48 px floor by effective target | **0** |
| Sheet-open focus trials | **60** — 0 failures |
| Sheet-close focus-return trials | **60** — **3 failures** |
| Clipped strings at Larger text | **1** |
| Prior blocking defects fixed | **10 of 10** |
| Prior improvements fixed | **14 of 18** |
| New blocking defects | **3** |
| New improvements | **15** |

---

# The worst three

1. **N1 — focus return strands the user on a closed sheet's heading, 3 of 60 closes (5%), in both motion modes.** Nothing to read, nothing to activate, Tab restarts from the document top. Intermittent, so a keyboard user cannot learn around it.
2. **N2 — closing the evidence receipt or the correction sheet destroys the place card and drops focus onto the map pin. 100% reproducible.** Cause: `openSheet()` treats card → sub-sheet as a hand-off rather than a stack.
3. **N3 — the capture coach auto-updates every 1.7 s indefinitely with no pause, stop or hide, and reduced motion does not stop it.** A WCAG 2.2.2 failure on the one screen the user must dwell on.

Runner-up, same class of seam: **N5 — the high-contrast toggle is the only action in the app that blanks the map ground**, reproduced independently on the live build.
