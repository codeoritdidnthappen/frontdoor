# Interaction and motion audit — Round 7 re-measure

_Report produced by the interaction-conformance agent on 2026-09-05 and saved verbatim by the orchestrator; the agent declined to write the file itself._

## Basis and method

**File under test.** `design/phone-app-prototype.html`, md5 **`87f681d8778e8d2cecf01d693ffae6fc`**, 1,460,004 bytes. That md5 is identical for `eb056fe:design/phone-app-prototype.html`, for the current working tree, and for `4a42dfb` (today's HEAD) — the ten commits since eb056fe do not touch this file. Every number below describes that one snapshot, copied to a scratch directory and served from there, so nothing could shift mid-measurement. The copy's md5 was re-verified against the repo file after the last measurement: unchanged.

**How.** Served over HTTP (`python -m http.server`) at 390×844, never `file://`. All numbers are read off the running page: `getComputedStyle`, `getAnimations()` with `effect.getTiming()`, `getBoundingClientRect()`, `MutationObserver`-instrumented flows, and real mouse/keyboard input.

**One methodological note that matters.** The shared Browser pane was being driven by another agent during the first pass (the page advanced through a new screen roughly every 900 ms with no input, and picked up a `phone rm` class never set here), and a background tab does not render, so transitions there froze mid-flight. Both effects produced impossible readings. That route was abandoned and everything re-run in a private Playwright Chromium instance, which is where all figures below come from. Reduced motion was measured with the browser's own `prefers-reduced-motion: reduce` emulation, not the in-app toggle.

**Deployed copy.** `https://frontdoor-measure.fly.dev/app` returns 200 / 1,481,787 bytes, md5 `1e111e8540c000921301b66637091477` — a *generated* port (`src/frontdoor_server/app.html`), not byte-identical to the design file. Spot-checked constants agree (18/54/92% stops, the 7% veil token, `--dur-drop:620ms`, `CLUSTER_PX = 48`, `overview: {est:32`). The measurements describe the design file.

**Nothing in the build or the rubric was changed. This is a report only.**

---

## Counts

| | Previous (20/19/21) | Now |
|---|---|---|
| Previous violations closed | — | **15** |
| Previous violations partly closed | — | **2** (V7, V19) |
| Previous violations still open | — | **3** (V12, V17, V20) |
| Previous drift closed | — | **14** |
| Previous drift partly closed | — | **3** (D16, D18, D19) |
| Previous drift still open | — | **2** (D2 documented, D17) |
| **New violations** | — | **4** (N1, N4, N8*, N11) |
| **New drift / structural findings** | — | **7** (N2, N3, N5, N6, N7, N9, N10) |
| Confirmed conforming | 21 | **31** measured this round |

\*N8 was half of a Part-2 asset item last round; the other half is now fixed, so the remainder counts as a live violation rather than a fidelity note.

**Standing totals against the spec today: 9 violations (3 carried, 2 partial, 4 new), 12 drift items.**

## The worst three

1. **Unknown match has no halo on the map (new, N1).** The spec and the accessibility checklist both require good/partial/unknown to stay separable as solid/dashed/dotted outlines. Measured across the map: 0 rendered instances of `match-unknown` anywhere in the document. `matchHalo('unknown')` exists and draws the correct dotted sky700 ring, but `renderPins` passes `null` for unknown, and the map legend now *documents* the omission — "not yet seen — no halo". What carries it instead is `.pinbtn.recede { opacity: .8 }`: 5 pins dimmed to 0.8 with a needs profile set and nothing selected. So the only visual carrier of "we have no evidence about your needs here" is a 20 % dim and the absence of a mark. The accessible name still says it; the sighted, non-AT reader gets dimming.
2. **The freshness clock still never reaches a pin (V17, carried).** 0 of 12 map pins carry a clock or amber marker, while three of the places on screen read "Seen 12 years ago — help us re-check" and "Seen 8 years ago — help us re-check" in their accessible names. Freshness is fully present in cards, list rows and the aging nudge (which now has its 20° clock turn, V16 fixed) — the map is the one surface where age is invisible.
3. **Reduced motion has no CSS fallback (new, N2), and it also deletes the scan's pacing (new, N3).** There is no `@media (prefers-reduced-motion: reduce)` rule anywhere in the file — the CSSOM was enumerated: the only `@media` is `(max-width: 767px)`. The entire reduced-motion contract now hangs on a `.phone.rm` class written by `applyPrefs()`. Measured with OS reduce on: first-contentful-paint at **296 ms**, `.rm` class applied at **388 ms** on a warm run and **804 ms** on a cold one — a 92–500 ms window in which the full-motion rules are the only rules. Separately, `defer(ms, fn)` and `after()` return 0 under reduce, so the scan runs **420 ms** end-to-end instead of 7,439 ms, and the deliberate `PROC_CHIPS+600` hold that exists "so 'Checks complete' is spoken before the screen changes" is skipped exactly when a screen-reader user is most likely present.

---

## Part 1 — Previous violations, status now

**V1. Unavailable state — FIXED.** `.btn[aria-disabled="true"]` renders `background rgb(232,225,247)` (`#E8E1F7`, lavender200), `color rgb(30,17,66)` (indigo900), `box-shadow inset 0 0 0 2px` the same lavender. Live instance found by sweeping all 26 screens: `#btn-claim-submit` on `claim-confirm`. It stays focusable (`tabIndex ≥ 0`, `BUTTON`) and `pointer-events: auto`, so the inline explanation still fires; `.btn[aria-disabled="true"]:active` keeps the 0.97 press. The grey prohibition holds — saturation of `#E8E1F7` is well above the grey band.

**V2. Estimated re-encoded — FIXED.** The `ring` tier is gone. Measured on the running map, the `lvl3` pin's SVG is a teardrop with `fill: var(--card,#FFFFFF)`, `stroke-dasharray: "7 6"`, a `<text>` node reading `i`, and three r4.5 dots all `#FFFFFF` (0 of 3). Drawn height 40 px at street, 32 px at overview, 52 px selected.

**V3. Sheet drag and velocity — FIXED.** Real mouse input, 8 moves of 25 px: sheet `transform` read back as `matrix(1,0,0,1,0,-25)` … `(0,-200)` and `getBoundingClientRect().top` 581.1 → 406.1, i.e. one-to-one to the pixel. Slow release from −200 px settled to `medium`; a fast flick up from peek reached **full**; a fast flick down from full reached **peek** (skipping medium); a fast flick down from peek **closed** the sheet. Velocity is projected forward 140 ms and snapped to the nearest stop.

**V4. Veil — FIXED.** `#map-veil` background is `rgba(30, 17, 66, 0.07)` — 7 %, indigo900. Opacity measured at each stop: peek **0**, medium **0**, full **1**. Bound to `.phone[data-card="full"]`.

**V5. Outgoing screen exit — FIXED.** `screen-exit-fwd` runs on the departing `<section>` (`#screen-profile.screen.screen-out`), 260 ms, `cubic-bezier(.2,.75,.25,1)`, `fill: both`. Sampled mid-flight: opacity `1 → 0.92592 → 0.891285 → 0.882151 → 0.880027`, transform `translateX(0) → −7.408 → −10.87 → −11.78 → −11.997 px`. Spec: 12 px left, 88 % opacity. `screen-exit-back` mirrors it.

**V6. Peer settle — FIXED.** `screen-lat` keyframes are `translateY(8px) → none` with opacity 0 → 1, duration `var(--dur-peer)` = **180 ms**, and the outgoing screen crossfades out under `screen-exit-lat` at the same 180 ms.

**V7. Bottom-nav indicator — PARTLY FIXED.** It is now one element (`#nav-ind`) owned by the bar, and it travels: x **44.4 → 275.4** with `transition: left 0.18s, width 0.18s, background-color 0.18s`. The "beneath the destination" half is still unmet: measured `indicator.top = 765.0`, `tab.top = 765.0`, `tab.bottom = 828.0`, `indicator.height = 4` — the bar sits flush with the *top* edge of the destination tab, above icon and label, not beneath them.

**V8. Pin-drop tail — FIXED, with one residual.** `.rippler` measured: `animation: 0.52s cubic-bezier(.2,.7,.2,1) ripple`, `animation-iteration-count: 1`, one `.rippler` element in the DOM. Two marigold seconds became one 520 ms pass. Residual drift: border colour `rgb(27,101,153)` = `#1B6599` sky700, where the token file's `.entrymap-pin-ripple` names `--entrymap-sky` = `#76BCFD` sky400.

**V9. Cluster impersonation — FIXED.** Measured 48.00 × 48.00 px, `z-index: 10`. Circles: `#fff` bleed, then `var(--indigo900,#1E1142)` disc with a white 1.8 stroke; count `<text fill="#FFFFFF">`; arcs `var(--sky400)`, `var(--marigold)`, `var(--purple)` proportioned to the mix. Neither the disc nor the count is any tier's colour. Labels carry the mix in words: "14 entrances here (3 scanned on-site, 11 estimated) — zoom in to see each one".

**V10. "Suggest a correction" in the receipt — FIXED.** `#sheet-receipt` innerText tail measured: "… Sources, dates, and confidence — not a badge. **Suggest a correction**".

**V11. Receipt expansion — FIXED.** `.evidence.ev-box.on` transition measured as `grid-template-rows 0.24s`, `margin-top 0.24s`, `padding 0.24s` — 240 ms exactly. Chip anchoring holds: the tapped chip's `y` was **395.34** before and **395.34** after.

**V12. Haptics — STILL ABSENT, now a recorded decision.** Zero `navigator.vibrate` calls. The file states the reasoning (iOS Safari has no Vibration API; the demo would behave differently on two devices in the same room; the intent belongs in the native shell). The spec clause remains unimplemented, but it is now a decision on the record rather than a gap.

**V13. Confidence dots — FIXED.** `dot-fill` measured at `0.15s` with `animation-delay` `0s / 0.07s / 0.14s` across the three dots — 70 ms apart, left to right, ending at `rgb(79,52,219)`. _(Orchestrator note: the dots are being removed in Round 8 by owner decision D38.)_

**V14. Outlined checks — FIXED.** Captured live during processing: `.checkitem.done .ci-dot svg path` → `animation-name: check-draw`, `duration 0.18s`, `fill both`, `stroke-dasharray 21px`, offset animating to 0. It draws now; it does not fade.

**V15. Toast swipe — FIXED.** Pointer handlers on `#toast`: any movement past 24 px in any direction, or a tap, calls `dismissToast()`; the timer is cleared.

**V16. Stale clock — FIXED.** `@keyframes stale-clock { 0% rotate(0) → 45% rotate(20deg) → 100% rotate(0) }` applied to `.nudge .n-age svg` over `var(--dur-map)`; it returns to rest, and the copy still describes time.

**V17. Freshness clock on a pin — STILL ABSENT.** See "worst three". 0 of 12 pins carry it.

**V18. Selected keyline — FIXED.** Selection injects exactly two external circles, measured on the live SVG: `circle r=65 stroke=var(--indigo900) stroke-width=3` and `circle r=59 stroke=#FFFFFF stroke-width=7`, both outside the head (r≈36), drawn behind the tier body. The tier fill is byte-identical before and after selection (`var(--marigold,#FDB327)` on the scan pin), so the no-recolour rule holds through the fix.

**V19. Selected pin's screen position — MOSTLY FIXED.** All 12 pins clicked one at a time from a clean state. Eleven moved exactly **−12.0 px** in centre-y (411.4→399.4, 432.8→420.8, 361.4→349.4, …), which is the 6 px lift plus half the 44→56 px growth — the *anchor* is unmoved and `#map` transform stayed `none`. The twelfth (The Ashton, centre-y 587.4, the only one the peek sheet would have reached) panned the map by 17.4 px. Against last round's 159 px down then 340 px up, this is effectively solved; the residual is that one 17 px pan and the fact that the sheet still enters from the bottom edge (`translateY(105%) → 0`) rather than originating near the pin.

**V20. Four scan beats — STILL MISSING, all four.**
- No white shutter wash: the only capture treatment is `.shutter:active{transform:scale(.93)}`; instrumented, `screen:scan-processing` fires **5 ms** after the shutter click.
- No single violet highlight crossing the photo: 0 elements matching `[class*=sweep]`, no counterpart to the token's `.entrymap-processing-sweep`.
- Checklist still reads `['Doorway framed','Entry path visible','Photo quality checked','Double-checking']`. The spec's third item, "Entrance features checked", is absent and "Double-checking" is not in the spec's list.
- No map-return contraction at 7,360–7,600 ms: processing goes straight to `scan-review`; the contraction toward the map exists only later, as the mini-map drop.

---

## Part 2 — Previous drift, status now

**D1. Duration set — CLOSED.** `:root` now carries thirteen durations, read from the running page: `--dur-press 100ms, --dur-focus 120ms, --dur-fast 160ms, --dur-peer 180ms, --dur-base 220ms, --dur-receipt 240ms, --dur-screen 260ms, --dur-sheet 320ms, --dur-map 450ms, --dur-ripple 520ms, --dur-drop 620ms, --dur-settle 900ms, --dur-check 1500ms`, plus `--ease-screen cubic-bezier(.2,.75,.25,1)` and `--ease-sheet cubic-bezier(.22,.9,.28,1.08)`. Every spec row in the old table now matches except focus (see N6) and the two the spec does not name.

**D2. Press scale — UNCHANGED, documented.** 0.97 across ~30 selectors, 0.93 on `.shutter`, 0.95 on `.nav-scan .ring`. Three values where the spec names one; both exceptions are argued in the file as physically larger controls.

**D3. Release spring — CLOSED.** Measured on a real press of `#ob-signin`: released transition `0.18s cubic-bezier(0.22, 0.9, 0.28, 1.08)` — 180 ms with a 1.08 overshoot.

**D4. Focus ring — CLOSED.** CSS declares `outline: 3px solid var(--brand-blue-ink); outline-offset: 3px`. Colour measured live: `rgb(118,188,253)` = `#76BCFD` sky400 on the dark screens, `#1B6599` sky700 (`--brand-blue-ink`) on light — sky in both cases, no purple left. *Instrumentation caveat:* this browser reports **any** declared 3 px outline as `2.66667px`; proven with a control probe (`<div style="width:3px;outline:3px solid red">` measured `width: 3`, `outlineWidth: 2.66667px`), so the 3/3 is the build's value, not a miss.

**D5. Hierarchical — CLOSED.** `screen-fwd` measured at **260 ms**, `cubic-bezier(0.2, 0.75, 0.25, 1)`, keyframes `translateX(24px) → none`.

**D6. Peer — CLOSED.** 180 ms.

**D7. Sheet snap — CLOSED.** `#sheet-card` transition measured `transform 0.32s cubic-bezier(0.22, 0.9, 0.28, 1.08), height 0.32s (same)`. Note the sheet's *initial* appearance still uses `.sheet.on` at 220 ms in / 160 ms out; the spec's 320 ms is the snap between stops, so this is consistent.

**D8. Sheet stops — CLOSED, exactly.**

| Stop | Spec | Build height | Build % |
|---|---:|---:|---:|
| Peek | 18 % | 151.92 px | **18.00 %** |
| Medium | 54 % | 455.75 px | **54.00 %** |
| Full | 92 % | 776.48 px | **92.00 %** |

At full the sheet takes `bottom: 0` and overlays the 86 px bar — a decision the file records explicitly.

**D9. Map camera — CLOSED.** `#map` transform transition measured at **450 ms** on selection and recentre.

**D10. Pin drop — CLOSED.** `dropIn` measured `620 ms`, `cubic-bezier(0.2, 0.9, 0.25, 1.2)` — the token's curve to the third control point.

**D11–D14. Pin sizes — CLOSED.** Full table in Part 4.

**D15. Chip stagger — CLOSED.** `c.style.animationDelay = (i*60)+'ms'`.

**D16. Toast — PARTLY CLOSED.** Rise is now **12 px** (`transform: translateY(12px) → 0`) over **220 ms** ✓. Dwell is still **4,200 ms** against the spec's 3,000–4,000. Anchored `bottom: 104px` over an 86 px bar.

**D17. Photo settle — UNCHANGED.** `.ring-photo` still goes `scale(1.14) → none` over `--dur-settle` **900 ms**. Spec's frame-confirmation beat is a 3 % contraction inside 100–380 ms.

**D18. Touch targets — MOSTLY CLOSED.** `--tap` is now **48px** and the pin hit area measured **48 × 48** (`::before`). Swept every one of the 26 screens: **144** interactive elements, **12** under 48 px in a dimension, and the same 12 under 44 — 8 switch `.toggle`s at 52×31, 3 native checkboxes at 20×20 on `claim-confirm` (each inside a row that is itself the target), 1 active filter chip at 103×32. The 40×40 `.sheet-close` outlier is gone. Note the in-file Round 5 note still says the build "stays at 44"; the token says 48 and the measurements agree with the token, so that note is now stale.

**D19. Scan beat map — PARTLY CLOSED.** Instrumented from the shutter click:

| Event | Spec window | Measured |
|---|---|---:|
| Processing screen | 100–380 ms | **5 ms** |
| "Doorway framed" | 380–7,000 ms | 2,509 ms |
| "Entry path visible" | ,, | 4,009 ms |
| "Photo quality checked" | ,, | 5,442 ms |
| Chips populate | 7,120–7,360 ms | **5,509 ms** |
| Review | ≈7,600 ms | **7,439 ms** |

Total is inside budget (< 8,000 ms ceiling). The internal shape is unchanged: 1,000 ms settle, 1,500 ms per check, chips ~1.9 s before the screen turns.

**Field-state carry-overs (last round's A1/A2), both unchanged.** Needs-attention is still `box-shadow: 0 0 0 2px var(--purple)` / `outline: 2px solid var(--purple)` — `#4F34DB`, the same colour as focus and selection, where the library's `needs-attention.svg` is marigold. There is still no "filled" field state.

---

## Part 3 — New findings

**N1 (violation). Unknown match draws no halo; dimming carries it.** Detailed in the worst three. Evidence: `match-unknown` renders 0 times; 5 pins at `opacity: 0.8`; legend text "Wheelchair: good · partial · not yet seen — no halo". In the list view the same state *does* keep a dotted carrier (`.mstat.unknown{border:2px dotted}` — "Not yet seen"), so the encoding exists everywhere except the map.

**N2 (structural). Reduced motion has no CSS media-query path.** Detailed above. It is safe today only because the sole animation live in the pre-class window is the splash entrance (sampled at t=137 ms: `animation-name: splashIn`, `opacity: 0`), and because the class does land. A JS error before `applyPrefs()`, or a slower boot, gives an OS-reduce user the full motion system with no fallback. Round 5's blanket had the opposite failure mode (shortening rather than replacing) but could not fail *open*.

**N3 (structural). Reduced motion removes the scan's pacing, not just its motion.** `defer(ms, fn) → setTimeout(fn, isReduced() ? 0 : ms)` and `after(reduced ? 0 : PROC_CHIPS+600, …)`. Measured: 7,439 ms normally, **420 ms** under reduce, with all three checks landing at once and the single polite announcement written 39 ms after the shutter. The spec asks reduced motion to "retain the checklist and textual progress"; the text is retained, the progression is not, and the announce-then-hold that the code itself documents as necessary is the thing that gets dropped.

**N4 (violation). A cluster can cover a pin.** Pairwise overlap computed from measured geometry (head radius = 0.42 × drawn height): pin-to-pin overlap respects the build's own 10 % rule (worst 0.100 at street, 0.097 at overview), but cluster-to-pin is untested by the collision pass — **43.3 %** of the Ashton pin is covered by a 48 px cluster at overview (centres 20.1 px apart), and 21.0 % of the DeSano pin at street. The spec's clause is "overlapping unselected pins cluster before they become visually illegible"; the mark that is supposed to resolve density is itself creating it.

**N5 (structural, mitigated). A new `animationend` dependency.** Last round's confirmation was "zero `transitionend`/`animationend` listeners". `holdLeaving()` now attaches one — but attaches it *before* the class that starts the animation, keeps a 280 ms watchdog, and is skipped entirely under reduced motion. Stress-tested with 12 interleaved peer navigations at 40 ms intervals: exactly **1** `.screen-out` at any sample, **0** stranded afterwards, **0** leftover `inert`, and a click 40 ms into a transition navigated normally (`screen-profile → screen-a11y`), so the "a transition never delays input" clause holds.

**N6 (drift). `--dur-focus: 120ms` is declared and never used.** No rule transitions `outline`. Arguably correct — the spec's own accessibility section says focus must not rely on motion — but the token now asserts a timing the build does not implement.

**N7 (observation). The modal scrim inherited the map's 7 %.** `.scrim` background measured `rgba(30, 17, 66, 0.07)`. The spec scopes 7 % to the map at full height; a modal dialog now separates itself from its background by 7 % of indigo. Nothing in the spec forbids it; it is a thin separation for a modal.

**N8 (violation, carried from A3). "Shadow compresses" on press is unimplemented.** 0 `:active` rules touch `box-shadow`. Measured on a real press: `#ob-signin` fill deepens `rgb(79,52,219) → rgb(56,35,155)` (violet600 → violet800 ✓) and scales to 0.97 over 100 ms ✓, but `.fab-filters` and `.ctl-btn` hold `rgba(30,17,66,0.1) 0 2px 6px, rgba(30,17,66,0.14) 0 10px …` unchanged through the press.

**N9 (drift). Explainer pins use a fourth size set.** The "How trust grows" rungs draw at 34 / 36 / 38 px — not overview, street, selected or receipt. Every other call site now resolves through `pinPx(tier, context)`.

**N10 (observation). Focus return is keyboard-correct, mouse-approximate.** Keyboard route: pin focused → Enter → sheet opens with focus on `H2.card-name` → Escape → focus back on `BUTTON.pinbtn.lvl2` ("Sweetgreen…") ✓ exactly as the checklist asks. Mouse route: real click on the pin → Escape → focus lands on `SECTION.screen.active` ("Map of entrances near 2nd and Colorado") rather than the pin.

**N11 (violation). Filter-change motion is not implemented.** The spec's map-camera section asks for affected pins to crossfade over 180 ms and newly relevant pins to rise 4 px while their halos draw. Nothing in the build does either; filter changes re-render the pin layer.

---

## Part 4 — Pin hierarchy, per tier, per context

Drawn SVG height measured with `getBoundingClientRect()`; the `height` attribute agrees with the rect in every case. (Rect *width* runs larger — 47.11 / 51.81 / 56.52 at street — because the viewBox carries 8 units of halo bleed on each side; the pin box is the height.)

| Context | Tier | Spec (`pin-hierarchy.json`) | Measured | z measured | Spec z |
|---|---|---:|---:|---:|---:|
| Overview | Estimated | 32 | **32** | 20 | 20 |
| Overview | Scanned on-site | 36 | **36** | 30 / 50 (matched) | 30 / 50 |
| Overview | Owner-confirmed | 40 | **40** | 40 | 40 |
| Street | Estimated | 40 | **40** | 20 | 20 |
| Street | Scanned on-site | 44 | **44** | 30 / 50 (matched) | 30 / 50 |
| Street | Owner-confirmed | 48 | **48** | 40 | 40 |
| Selected | Estimated | 52 | **52** | 60 | 60 |
| Selected | Scanned on-site | 56 | **56** | 60 | 60 |
| Selected | Owner-confirmed | 60 | **60** | 60 | 60 |
| Receipt / card | Estimated | 24 | **24** | — | — |
| Receipt / card | Scanned on-site | 28 | **28** | — | — |
| Receipt / card | Owner-confirmed | 32 | **32** | — | — |
| Mixed cluster | — | 48 | **48.00 × 48.00** | 10 | 10 |
| Live scan drop | — | 64 | **64** | `auto` | 70 |

Twelve of twelve size cells are exact. Six of the seven z-layers are exercised on the map and exact. The seventh is declared (`PIN_Z.live = 70`) but never exercised: the drop plays on the `scan-done` mini-map as `.minipin.pin-drop`, which is the only mark in that container, so its computed `z-index` is `auto`.

Selection carries the 6 px lift (`matrix(1,0,0,1,−35.33,−6)`, `(−32.97,−6)`, `(−30.62,−6)` for owner/scan/est) plus a real size step rather than a `scale()`. The spec is internally inconsistent here — `MAP-IMPLEMENTATION.md` says "approximately 12 % scale" while the size table says 52/56/60, which is +25 % to +30 % — and the build follows the table. That is the right resolution and it is recorded as conformance, not drift.

---

## Part 5 — Sheet stops, snap, veil

- Stops **18.00 / 54.00 / 92.00 %** (151.92 / 455.75 / 776.48 px on 844) — exact.
- Snap **320 ms** on `cubic-bezier(0.22, 0.9, 0.28, 1.08)`, applied to both `transform` and `height`.
- Drag is one-to-one under real input; release velocity is projected 140 ms forward and snapped to the nearest stop, with a downward projection past 0.55 × peek closing the sheet.
- Veil opacity by stop: **0 / 0 / 1**, colour `rgba(30, 17, 66, 0.07)`, `z-index: 42` (under the sheet at 48, over the pins).
- Explicit controls exist beside the gesture: the grip is a `BUTTON` labelled "Expand card — tap or drag the handle; swipe down to close", with ArrowUp/ArrowDown handlers, plus a Close button.

---

## Part 6 — Reduced motion, measured separately

The whole build was run under browser-level `prefers-reduced-motion: reduce` — pin select, three sheet stops, receipt expand, peer nav, hierarchical nav and back, and a complete scan through to the pin drop — with a per-frame recorder over `document.getAnimations()`.

**The set of animations that ran in that entire pass:**

```
rm-fade | 80ms | delay 0 | .screen-body
rm-fade | 80ms | delay 0 | .screen-body.has-flowhead
rm-fade | 80ms | delay 0 | .scan-body
```

Nothing else. That is replacement, not shortening, and it is the strongest single result in this round.

**Why it is sound by construction, not by luck.** The file has 18 keyframes: `dropIn, ripple, dot-fill, check-draw, settle-in, pinTap, splashIn, splashOut, chipIn, chipOut, rm-fade, stale-clock, screen-fwd, screen-back, screen-lat, screen-exit-fwd, screen-exit-back, screen-exit-lat`. Every non-`.rm` animation rule (23 of them) was mapped to a `.phone.rm` counterpart: **18/18 keyframes explicitly answered** — each either `animation: none !important` with the resting state asserted (`.pinbtn.selected .pin` gets `transform: translateX(-50%) translateY(-6px)` written out; `.dots i.f` gets its final `background-color`; `.checkitem.done path` gets `stroke-dasharray: none; stroke-dashoffset: 0`), or replaced by a different presentation (`rm-fade`, the determinate processing bar), or removed (`.rippler{display:none}`). Last round's three no-fill keyframes that "happened to" land correctly are now asserted.

**Delays are gone too.** `.phone.rm *, ::before, ::after { transition-duration: 0s !important; transition-delay: 0s !important; animation-delay: 0s !important }`. Measured: `#sheet-card` `transition-duration 0s`, `transition-delay 0s`, `visibility: visible`, focus lands on `H2.card-name`. The Round 5 hazard (a visibility guard written as a delay, leaving `focus()` a silent no-op on a hidden subtree) is closed by rule rather than by browser behaviour, and `openSheet()` waits on focusability rather than a clock.

**The global `animation-iteration-count: 1 !important` is gone** — every CSS rule was searched for the property and none found.

**What is still left mid-flight or racing.**
- The 92–500 ms window before `.rm` is applied (N2). No `@media` copy exists to cover it.
- The scan collapses to 420 ms and the announcement hold is skipped (N3).
- `showScreen()` skips the exit entirely under reduce (`out: 0` measured), and `.phone.rm .screen.screen-out{animation:none;opacity:1;transform:none}` is declared anyway so no other path can strand a screen at 88 %. That is belt and braces and it is correct.
- The one `animationend` listener is never reached under reduce, by construction (N5).

Against the spec's four reduced-motion clauses: screen transitions are an 80 ms opacity-only crossfade — inside the ceiling and, unlike last round, actually a crossfade ✓. Sheets appear at their destination stop with no spring ✓ (18/54/92 % and veil 1 at full, all measured under reduce). Processing keeps the checklist and swaps the ring for a determinate bar (`ring: not found`, `bar: block w=100%`) ✓. Checks and dots appear in their final states, asserted rather than inherited ✓. The completed pin appears with no bounce and no ripple: `.pin-drop` present, `animation-name: none`, `.rippler` count **0** ✓.

---

## Part 7 — The prohibitions, each checked separately

1. **No red — PASSES.** All 26 screens walked with each made active in turn, collecting `color`, `background-color`, four border colours, `outline-color`, `fill`, `stroke`, `caret-color`, `text-decoration-color` from every element with a client rect: **57 distinct rendered colours, 0** in the red band (hue ≤ 15° or ≥ 345°, S ≥ 25 %, L 20–75 %). Static sweep of the whole 1.4 MB file finds exactly one red-band hex, `#BF0A30` — inside a comment recording that the Texas flag's heraldic red and blue were removed. `texasFlagSVG()` renders in `var(--ink,#1E1142)` and `#FFFFFF`.
2. **No grey — PASSES.** Same sweep: **0** rendered colours with S ≤ 8 % at L 12–95. Zero in the stylesheet, zero in the file.
3. **No trust pin recoloured for selection — PASSES.** The selected scan pin's body path is `fill="var(--marigold,#FDB327)"` before and after selection, character for character; selection adds only the two external rings.
4. **No trust pin recoloured for match — PASSES.** Halos are external circles at r50/r38 around a head of r≈36. The body fill is untouched on all six matched pins.
5. **No trust pin recoloured for freshness — PASSES (vacuously).** Freshness never reaches a pin at all (which is V17).
6. **No trust pin recoloured for provenance — PASSES.** The Texas mark appears at exactly one site, the state-record line inside a receipt; `sheet-receipt` for a non-Texas place contains no Texas string, and no pin SVG references it.
7. **The lavender halo disc is on match state only — PASSES.** All 12 pins enumerated: 6 carry `circle r=47 fill=var(--lavender-path,#CFBCEE) opacity=.55`, and those are exactly the 6 that carry a `match-good` or `match-partial` halo. The other 6 carry neither. The disc is drawn behind the pin, so it does not tint the mark.
8. **A cluster never impersonates a trust tier — PASSES.** Indigo900 disc, white ring, white count; the three arcs are supplementary and proportional, and the mix is spoken in full in the accessible name.
9. **Unavailable never becomes grey — PASSES.** `#E8E1F7` on `#1E1142`.
10. **No shaking or failure-shaped motion — PASSES.** 18 keyframes, none a shake, wobble or rejection. The only rotation in the file is `stale-clock`, 20° out and back. Offline scans still fold into a "Saved for later" card.
11. **Fixed trust encoding intact — PASSES.** Estimated: hollow, `stroke-dasharray 7 6`, italic `i`, 0 of 3 dots. Scanned on-site: marigold solid, person glyph, 2 of 3. Owner-confirmed: violet solid, storefront plus a separate outlined tick, 3 of 3. _(Round 8 changes the Estimated mark and removes the dots by owner decision.)_
12. **Progress is the only thing that eases linearly — PASSES.** Eight `linear` occurrences: two progress arcs (`stroke-dashoffset .25s linear`), the saving bar (`width .8s linear`), the reduced-motion crossfade, and four gradients. **Zero** `ease-in`, `ease-out` or bare `ease`.
13. **Ordinary feedback stays in the 90–320 ms band — PASSES.** Every general-purpose token (100, 120, 160, 180, 220, 240, 260, 320) is inside it; everything outside (450 camera, 520 ripple, 620 drop, 900 settle, 1500 per check) is named and scoped to the map or the scan.

---

## Punch list, in priority order

1. **Draw the dotted unknown halo on the map (N1).** `matchHalo('unknown')` already produces the library's dotted sky700 ring; `renderPins` passes `null`. One call-site change plus a legend edit. Reconsider whether `.recede` at 0.8 should also carry match state when a positive mark is available.
2. **Put the freshness clock on the pin (V17).** `pin-overlays/freshness-clock.svg` ships; three places on the default map are 8–12 years old and say so in their accessible names while showing nothing.
3. **Give reduced motion a CSS floor (N2).** A short `@media (prefers-reduced-motion: reduce)` block that mirrors the `.phone.rm` essentials — or applying the class in an inline head script before first paint — closes a 92–500 ms window and removes the single point of failure.
4. **Stop `defer()` from deleting the scan's pacing (N3).** Reduced motion should keep the checklist cadence and the announce-then-hold; only the sweep, scale and rotation should go. As written, the clause that protects screen-reader users is the one reduce turns off.
5. **Test clusters against pins in the collision pass (N4).** 43 % of a pin covered at overview is the exact failure the clustering rule exists to prevent.
6. **Finish the four scan beats (V20).** The shutter wash and the single violet sweep are two small additions; "Entrance features checked" is a string; the map-return contraction is the one real piece of work.
7. **Move the nav indicator beneath the tab (V7)** and compress a shadow on press (N8) — both are single rules.
8. **Close the small numbers:** toast dwell 4,200 → 3,000–4,000 (D16); photo settle 900 ms / 14 % → 100–380 ms / 3 % (D17); ripple border sky700 → sky400 (V8 residual); explainer rungs 34/36/38 → a named context (N9); the 8 toggles at 52×31 and the filter chip at 103×32 → 48 (D18); either use `--dur-focus` or delete it (N6).
9. **Decide the needs-attention colour (A1, carried).** It is still the focus/selection violet where the library says marigold, so a field that needs you looks like a field that is focused.
10. **Update the stale in-file note** that says the build "stays at 44" on touch targets; `--tap` is 48 and the measurements agree with the token.

## How far the build is from the spec, plainly

Round 5 through 7 closed **29 of the 39** items the last audit raised, and closed them properly — not by moving a number until it matched, but by taking the kit's own drawing (the cluster, the selection keyline, the estimated teardrop), by rebuilding the gesture rather than re-tuning its threshold, and by replacing the reduced-motion blanket with eighteen individually declared end states. Twelve of twelve pin-size cells are exact. Three of three sheet stops are exact to two decimal places. The veil is 7 % at one stop and nothing at the other two. Every prohibition a test could be constructed for holds, including the two that are easiest to break while restyling: no pin is recoloured for any of the four forbidden reasons, and the lavender disc Round 7 introduced is on match state and only match state.

What is left is smaller but not cosmetic. Three things are genuinely missing from the surface a user reads — the dotted unknown halo, the freshness clock, and four beats of the scan — and in the first two cases the map is now the only place in the product where a state that exists everywhere else is invisible. The reduced-motion path is the best-engineered part of the build and also the one with the most interesting remaining hole: it is correct by construction *once the class lands*, and there is no longer anything underneath it if that ever fails. And one new regression is worth naming plainly: the map's clustering, which is what earned the estimated pin its full size back, does not test itself against the pins it is meant to protect.

Call it five-sixths of the way, with the remaining sixth concentrated in three or four places rather than spread thin. Round 8 is already in flight against this same surface — the estimated-tier and dot findings above describe a mark that is about to change, and should be re-measured after that lands.
