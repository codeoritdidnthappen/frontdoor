# EntryMap prototype — adversarial QA sweep and four-round change audit

**Target:** `design/phone-app-prototype.html`
**Driven at:** 390×844, served over `http://127.0.0.1` (not `file://`)
**Primary revision under test:** working tree at md5 `270f0858b436b66ba898736b78518e19` (at commits `b636147` → `3d5a79a`)
**Every defect below re-confirmed against:** working tree at md5 `b5144030e73dbe9ffb919c67beb7ab11` (HEAD `e938c61`, Round 6 in flight)

The file was rewritten **five times underneath this sweep** (`d74b67c` → `3ffabf8` → `270f085` → `b514403`, with Round 4 committing as `b636147` mid-audit). Every finding was therefore re-verified against the latest bytes before being written down. Two audit claims and one file-level property were measured twice, at both ends of that drift, and are reported with both numbers.

## Method and its one limitation

Screens were walked with real keyboard input and with pointer/touch event sequences dispatched into the page. **The Browser pane's native click pipeline was wedged for the whole session** — `left_click` timed out at 30s on every tab, every coordinate, with zero console errors, zero running animations and a live JS context. Screenshots and keyboard input worked throughout. Clicks were therefore synthesised.

That matters, so it was calibrated rather than assumed. Two early "defects" turned out to be harness artifacts and were withdrawn:

- A naive synthetic `click` carries `detail === 0`, which this app deliberately reads as *keyboard* activation (`grip.addEventListener('click', e => { if(e.detail===0) stepCard(+1) })`). That double-stepped the card sheet. Fixed by emitting `detail: 1`, as a real finger does.
- Synthetic clicks do not focus their target, so the card's focus-return looked broken. Fixed by focusing on `pointerdown`, as browsers do.

After calibration the harness reproduces real tap semantics. Everything below was then confirmed by a second, independent signal — computed styles, ARIA state, screenshots, or the source — never by the harness alone. Findings that could not be behaviourally confirmed are marked as such.

---

# Part one — QA defects

## S1 · HIGH · Reduce Motion silently destroys focus management on every sheet in the app

The single most serious defect found. Enabling **Reduce Motion** — the app's own accessibility setting — stops focus moving into any sheet that opens. Focus is left on `<body>`.

**Reproduction**
1. Onboard through to the map.
2. Profile → Accessibility → turn **Reduce motion** on.
3. Return to the map. Tap any pin (or Filters, or My needs, or the trust legend).
4. Inspect `document.activeElement`.

**What happened** — measured at HEAD, 6 opens per surface:

| Surface | Reduce Motion OFF | Reduce Motion ON |
|---|---|---|
| Entrance card (pin tap) | 0/6 land on `<body>` | **6/6 land on `<body>`** |
| Filters sheet | 0/6 | **6/6** |
| My needs sheet | 0/6 | **6/6** |
| Trust legend sheet | 0/6 | **6/6** |

An earlier 10-trial run on the pre-Round-4 revision gave 0/10 vs 8/10 — the defect got *worse*, not better, across the drift.

**What should have happened** — focus lands on the sheet's heading (`.sheet-h` / `.card-name`), as it does with the setting off. This is round one's B5/B9 behaviour, and it is exactly what `openSheet` intends.

**Mechanism** (verified by computed style, not inferred):

- `.sheet` encodes its closed-state guard as a *delay*, not a duration:
  `transition: transform var(--dur-fast) var(--ease-exit), visibility 0s var(--dur-fast);` — line 569. Closed, the sheet computes `transition-delay: 0s, 0.16s`.
- Both reduced-motion blocks — `.phone.rm *` (line 1254, the in-app toggle) and `@media (prefers-reduced-motion: reduce)` (line 1750, the OS preference) — force `animation-duration`, `animation-iteration-count` and `transition-duration` to `.01ms !important`, and **neither touches `transition-delay`**. `grep -c "transition-delay:0s !important"` returns **0**.
- So under Reduce Motion the transform snaps instantly while the 160 ms visibility delay survives, and the sheet's subtree is still `visibility: hidden` when `openSheet`'s fixed **40 ms** focus timer fires (line 4437).
- `HTMLElement.focus()` on a `visibility:hidden` element is a **silent no-op**. Nothing retries, and nothing checks whether focus actually landed.

**Why this is the worst finding here:** the population that turns Reduce Motion on overlaps heavily with screen-reader and keyboard users, and the same break is triggered by the *OS-level* setting — a user whose phone has Reduce Motion on system-wide gets it without ever opening the app's settings. For the four **modal** sheets it is worse still: `setBackgroundInert(true)` marks all 26 screens inert, so a screen-reader user is parked on `<body>` with the entire app inert and no announcement of what opened. Keyboard users recover on their first Tab (the tab trap pulls them in); screen-reader users get nothing.

**Note for the audit half:** a careful static read of this file concludes reduced motion is *coherent* — one blanket `*` rule for the in-app pref mirroring one for the OS pref, no duplication, no round-one behaviour deleted. That conclusion is correct as far as it goes, and the build's worst defect still lives underneath it. See A1.

---

## S2 · HIGH · "Open now" and "Distance" are inert — two of the five filter controls do nothing

**Reproduction**
1. Map → **Filters**.
2. Toggle **Open now** on. Drag **Distance** from 1 mile to 0.25 mi.
3. Watch the "Show N places" button, then tap it.

**What happened** — the count never moves, and the applied result is unchanged:

| Action | "Show N places" |
|---|---|
| baseline | Show 64 places |
| all 3 feature chips on | Show 3 places |
| **+ Open now ON** | Show 3 places |
| **+ Distance 1 mi → 0.25 mi** | Show 3 places |

**What should have happened** — the count and the applied filter respond to all five controls.

**Confirmed in source, at HEAD.** `filterPass` reads three inputs and no others:

```js
function filterPass(p){
  for(const f of filtFeats){ if(!(p.f[f]&&p.f[f].v==='present')) return false; }
  if(filtFresh!=='any' && p.tier==='est') return false;
  if(personas.size){ const m=matchOf(p); if(m.state==='unknown') return false; }
  return true;
}
```

There is no state variable for either control anywhere in the file — `grep -c "filtOpen\|filtDist"` returns **0**. Their handlers only paint themselves: the Open-now switch toggles its own `class`/`aria-checked`; the distance slider updates its label and `aria-valuetext`. Both are also excluded from `filterApplied` and from the filter-count badge, so neither ever appears in the active-filter chip row either.

**Demo risk:** high. "Open now" is the single most obvious thing an audience member reaches for, and it is a `role="switch"` that reports `aria-checked="true"` while changing nothing.

---

## S3 · MEDIUM · "7 days" and "30 days" freshness filters are functionally identical

**Reproduction:** Filters → Reset → tap each freshness segment in turn.

| Freshness | Result |
|---|---|
| Any | Show 64 places |
| **7 days** | **Show 12 places** |
| **30 days** | **Show 12 places** |

**What should have happened** — two differently-labelled time windows produce two different result sets.

**Cause:** `filterPass` collapses both to a single tier test — `if(filtFresh!=='any' && p.tier==='est') return false` — which asks only "is this an estimate?", never how old the evidence is. The segment presents three choices and implements two.

---

## S4 · MEDIUM · Dragging the card sheet *up* at its top stop collapses it to the bottom stop

**Reproduction**
1. Map → tap a pin → tap the handle twice to reach **full**.
2. Swipe/drag **upward** on the sheet (any distance past the 28 px threshold — tested at 120, 140, 150 and 400 px).

**What happened** — the card jumps `full → peek`, its smallest state. Confirmed at both revisions and at every drag distance.

**What should have happened** — an upward drag at the topmost stop is a no-op (or rubber-bands). Dragging up is a request for *more*, and it delivers the minimum.

**Cause:** `stepCard` applies a modulo wrap that is correct for tap-cycling but wrong for a directional gesture:

```js
function stepCard(dir){
  const i=CARD_POS.indexOf(cardPos);
  if(dir>0){ setCardPos(CARD_POS[(i+1)%3]); }   // full (2) -> (2+1)%3 = 0 = peek
  ...
}
```

Both the tap path and the drag path call `stepCard(+1)`. Tap-cycling `full → peek` is intended and is announced correctly by the handle's own label; the drag inherits the wrap it should not have. Also note the handle's `aria-label` advertises "tap **or drag** the handle", but there is no `pointermove` handler — the sheet never tracks the finger, it only threshold-tests on `pointerup`.

---

## S5 · MEDIUM · The claim form submits with no email and no phone, then promises an email

**Reproduction**
1. Profile → **Start a claim** → **Continue**.
2. Leave **Work email** and **Business phone** completely empty.
3. Tick only "I'm authorized to manage this business listing" → **Submit**.

**What happened** — submission succeeds and lands on "Claim submitted", which reads:

> "We're reviewing your claim. **We'll email you when your workspace is ready.**"

No address was ever collected.

**What should have happened** — the form validates that the chosen verification channel has a value, or the confirmation stops promising a message it cannot send.

**Detail:** the authorization checkbox is the *only* validated field, and that gate works correctly and accessibly — empty submit sets `aria-invalid="true"`, shows the inline error, moves focus to the checkbox and announces "Claim not submitted…". Everything round one built here is intact. The gap is that no other field has any validation at all: no `required`, no `aria-invalid`, no `aria-describedby` on email or phone in any state.

---

## S6 · MEDIUM · The search overlay claims to be modal but traps nothing

`#search-ov` carries `role="dialog"` and `aria-modal="true"`. Measured while open at HEAD: **72 focusable elements reachable outside it** and **0 `[inert]` nodes** in the document.

**Reproduction:** Map → search icon → hold Tab. Focus walks straight out of the overlay into the map, the filter FABs and the bottom nav behind it.

**What should have happened** — the same treatment the `.sheet` components get: `setBackgroundInert(true)` plus the Tab trap.

Round one's B5 fix covered `.sheet` only, and `openSearch()` is byte-identical from round one to now — so this is a **pre-existing gap, not a regression**. Focus does move into the field, Escape closes, and focus returns to the opener; only the containment is missing.

---

## S7 · MEDIUM · Keyboard-focused map pins draw a stray focus artifact

**Reproduction:** Map → Tab to the skip link → Tab once more to land on the first pin.

**What happened** — measured on the genuinely keyboard-focused pin (`:focus-visible` confirmed true):

```
box: 0 × 0 at (155, 435)
outline:    solid 2.66667px rgb(91, 53, 245), offset 2px
box-shadow: rgba(255,255,255,0.92) 0 0 0 6px
```

A ~12×12 px white halo with a purple outline is painted around a zero-size box at the pin's tip anchor — *in addition to* the intended 44 px ring on the pin's `::before`.

**Cause — a cross-round specificity collision.** Round two rewrote `.pinbtn` into a zero-size anchor with its hit area on a pseudo-element, and wrote `outline:none` to suppress the artifact. That rule loses:

- `.pinbtn:focus-visible{outline:none}` — specificity (0,2,0)
- `.phone :focus-visible{outline:3px solid…; box-shadow:0 0 0 6px…}` — specificity (0,2,0), **declared later, so it wins**

`.cluster:focus-visible{outline:none}` is dead for the same reason. Round two verified its own concern (the `::before` ring renders correctly) and had no reason to re-check round one's global focus rule.

---

## S8 · LOW-MEDIUM · At the largest text size, the claim form's verify-options overflow onto the control below

**Reproduction:** Accessibility → text size **Larger** → Profile → Start a claim → Continue.

**What happened** — the "How should we verify you?" option cards do not grow with their text. The description overflows the card and collides with what follows:

| Element | Content needs | Box gets | Overflow |
|---|---|---|---|
| `.verify-opt.sel` ("Business email") | 78 px | 52 px | **26 px** |
| `.verify-opt` ("Call the business") | 59 px | 52 px | 7 px |
| `.authz` (authorization row) | 47 px | 44 px | 3 px |

**Cause:** `.screen-body` is `display:flex; flex-direction:column` and is overflowing (scrollHeight 909 > 844). `.verify-opt` is a flex item with `min-height:56px` and default `flex-shrink:1`, so it is compressed to its min-height while its content needs more; `overflow:visible` then lets the text spill onto the next control rather than clipping it.

**Scope is narrow, and that is worth saying plainly.** A sweep of every element on all 26 screens at the largest text size found only **3** instances of this squash, and only this one is material. Nothing anywhere clips vertically — every long screen has `overflow-y:auto` and scrolls correctly.

---

## S9 · LOW · A completely empty correction submits successfully

**Reproduction:** Map → pin → expand card to full → **Suggest a correction** → **Send** without selecting anything or typing anything.

**What happened** — lands on "Correction submitted", and the empty correction is recorded in Profile → My contributions → My corrections.

**What should have happened** — the send control is unavailable, or the form asks for at least one selection.

The note field is correctly bounded (`maxlength="300"`), so long input is a non-issue here.

---

## S10 · LOW · A very long search query blows out the results pane horizontally

**Reproduction:** Map → search → paste 2,000+ characters with no spaces.

**What happened** — `#search-body` gains a horizontal scroll of **17,251 px** against a 358 px client width (43,114 px at 5,000 characters). The "No entrances mapped for…" message renders as one unbroken line running off-screen. `overflow-wrap` and `word-break` both compute to `normal` on `.sheet-p`.

**Contained, not catastrophic:** `#phone` is `overflow:hidden`, so the page itself never scrolls sideways and the Scan CTA stays in place. Cosmetic robustness rather than a break.

---

## S11 · LOW · The no-results search state contradicts itself

A query with no matches renders the friendly empty state *and*, immediately below it, a results header reading "**0 entrances · 0 businesses**". The count line sits outside the `if(!groups.length)` branch, so it always renders. Cosmetic.

---

## S12 · LOW · `scan-processing` has no in-screen exit

It is the only screen with zero navigation controls of its own — no cancel, no back. The bottom nav is present and not inert, so it is escapable, and every navbar route out of it cancels the scan timers correctly. Worth knowing before a live demo; not a trap.

---

## S13 · LOW · Backgrounding is entirely unhandled *(code-read only — not behaviourally verified)*

The file registers **no** `visibilitychange`, `pagehide`, `pageshow` or `document.hidden` handler anywhere. `stopCamera()` is called only from `showScreen()`, i.e. only on a screen change. Backgrounding the app while on `scan-capture` therefore appears to leave the camera stream live — which sits awkwardly against the privacy copy that screen displays. **Not confirmed behaviourally:** camera access is blocked in this environment, so `camStream` was never non-null. Flagged for a real-device check, not asserted.

Processing itself is well defended against backgrounding: `runProcessing` carries an explicit timer-based watchdog for throttled/frozen `requestAnimationFrame`, with a comment saying so.

---

## What held up under attack

Stated deliberately — these were attacked and did not break, and several are the load-bearing parts of the demo.

- **The owner face-flag publish gate is genuinely solid.** I tried to go around it rather than through it: Edit entrance carries `data-go="ow-review"`, whose delegated router applies no gate, so you can reach the review screen without ever visiting Manage photos. `review-publish` re-checks independently, bounces you to `ow-photos`, sets `aria-invalid`, moves focus to the button that fixes it, and announces *"Update not published. Photo 3, Doorway with the patio, may show a face…"*. Rapid triple-tap on publish publishes exactly once. The flagged photo is correctly **excluded** from the "public listing preview". Cropping clears the flag, clears the error, drops `aria-describedby` and moves focus to publish. Re-entering `ow-review` after publishing correctly resets the button, the progress bar and the saving overlay.
- **No injection anywhere I tried.** `<img src=x onerror=…>`, `"><script>…</script>`, and quote-breaking payloads were fed to search and to the correction note. All rendered as literal text, correctly escaped, and echoed back safely into My corrections. Zero nodes created, zero handlers fired.
- **Rapid and interleaved taps never desynchronise the screen state.** 18 interleaved Map/Scan/Profile taps with no settle time, and hammering the nav mid-scan-transition, always settled to **exactly one** `.screen.active` with the correct tab carrying `aria-current="page"`.
- **Leaving a scan mid-flow is clean.** Exiting `scan-processing` at 1.2 s and idling 6 s on Profile produced no stale-timer yank. All three navbar routes out of the scan cancel the timers.
- **Toggling Reduce Motion mid-processing does not break the state machine** — the in-flight run keeps its captured schedule and completes to review normally. (The setting only takes effect on the next run; a minor inconsistency, not a break.)
- **Toggles survive repeated driving.** Notification switches driven 5× and 10× consecutively kept `aria-checked` and the `.on` class in sync — 0 mismatches.
- **All 26 screens** carry `tabindex="-1"` and an `aria-label`; there is a single choke-point (`showScreen`) that focuses the screen on every navigation, with the class toggle ordered before the `focus()` in the same synchronous task.
- **The largest text size holds.** No vertical clipping on any of the 26 screens.
- **Rotation is graceful** — landscape scales the whole device frame down and centres it; nothing clips, the navbar stays visible.
- Whitespace-only search input is correctly trimmed to the empty state. Singular/plural is correct ("1 entrance · 1 business").
- Closing the card returns focus to the exact pin that opened it, re-finding it by `data-id` after the map re-render.

---

# Part two — change audit

Four rounds landed in hours: **R1** `896895c` accessibility · **R2** `b2803a3` (+`5cbb19f`) board fidelity · **R3** `afd2788` systems and consistency · **R4** `b636147` token adoption (committed mid-audit). Ordered by risk.

## A1 · HIGHEST · The reduced-motion blanket is incomplete, and it is why S1 exists

Both reduced-motion blocks force three properties and omit a fourth:

```css
/* line 1254 — in-app toggle */  .phone.rm *,…{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}
/* line 1750 — OS preference  */  *,…{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}
```

Neither sets `transition-delay`. That is invisible to inspection *of the reduced-motion feature itself* — the two blocks mirror each other perfectly, cover every keyframe rounds 3 and 4 added, and contain no duplication or contradiction. A static audit of reduced motion passes it, correctly.

It only becomes a defect in combination with a rule written elsewhere for an unrelated reason: `.sheet`'s stale-transform guard, which happens to express itself as `visibility 0s var(--dur-fast)` — a **delay**. Neither round owned both halves. This is precisely the damage class the brief predicted: each round verified its own concern, and the failure lives in the seam.

`.popup` (line 1201) carries the same `visibility 0s var(--dur-fast)` pattern and is exposed to the same interaction.

## A2 · HIGH · Round two's `outline:none` for pins was dead on arrival

Covered as S7. `.pinbtn:focus-visible{outline:none}` and `.cluster:focus-visible{outline:none}` are both (0,2,0) and both lose to the later `.phone :focus-visible`. Round two rewrote the pin geometry to a 0×0 anchor, wrote the suppression rule, verified its own `::before` ring looked right, and never saw that round one's global rule still won. Confirmed rendering at HEAD, not inferred.

## A3 · HIGH · Two of five spot-checked round claims are materially false

Verified twice — at the mid-sweep revision and again at HEAD. Both false claims are **unchanged**, and both are undercounts of the same flattering kind.

| Claim | Claimed | Actual (HEAD) | Verdict |
|---|---|---|---|
| Pin tips land on their coordinate with zero offset | zero | **0.0000 px horizontal, ≤0.002 px vertical**, at every emitted size | **TRUE** |
| Heaviest font weight reduced to **21** sites | 21 | **28** — 26 × `font-weight:var(--fw-display)` + 2 × SVG `font-weight="800"`; heaviest value is 800 | **FALSE** (+33%) |
| Hand-drawn icons down to **four** | 4 | **27** — the `ICONS` table the file itself labels *"OURS. The library ships no equivalent"* | **FALSE** (6.75×) |
| Zero non-ASCII outside base64 | 0 | was **0 bytes in the entire file** across R1–R4; now **9 bytes** at HEAD | **REGRESSED** — see A4 |
| All 26 screens take focus | 26 | **26/26** have `tabindex="-1"`; one choke-point focuses on every path | **TRUE**, with caveats |

On the pin claim: it holds for the tip-anchored marks (owner 40 px, scan 30 px, all mini-map sizes), and the level-3 "estimated" ring and the cluster disc are centre-anchored *by design* — the file documents both ("a ring has no tip"). The claim is true but scoped to marks that have tips.

On the focus claim: true, and structurally airtight — there is exactly one line in the app that changes which screen is visible, and it is inside `showScreen`, which always ends by focusing the screen. Four paths hand focus onward immediately afterwards (search field, card heading, OS file picker) — deliberate. One asymmetry is worth recording: `closeSheets`' deferred focus-restore is guarded by `navToken`, but `openSheet`'s 40 ms focus timer is guarded only by `sh.classList.contains('on')` and never checks `navToken`, leaving a ~40 ms window where a pending sheet-focus can land after a screen has taken focus.

## A4 · MEDIUM · The zero-non-ASCII property was true for four rounds and broke after Round 4

The file was **pure ASCII — 0 bytes > 127 in the entire file, base64 included** — at R1, R2, R3 and the Round-4 working tree. HEAD now has **9 non-ASCII bytes**, three literal characters, all in JS string comparisons in the icon-substitution pass:

```js
if(t === '‹'){                                    // U+2039, line ~4220
} else if(t === '✕'){                             // U+2715, line ~4223
if(el.textContent.trim() === '✕') …               // U+2715, line ~4229
```

Everywhere else the file uses `\uXXXX` escapes (155 of them) and HTML entities (106). These three are the exception.

**Functionally safe today** — the file declares `<meta charset="utf-8">` and the markup writes the matching glyphs as `&lsaquo;` / `&#x2715;`, which decode to the same characters, so the comparisons match and the drawn icons swap in. The risk is that this is now the only code in the file whose behaviour depends on literal source bytes surviving a re-save or a re-serve in another encoding; if that ever slips, the back and close buttons silently keep their font glyph. Low severity, but it is a real regression against a property the project had actually achieved.

## A5 · MEDIUM · Rules two rounds solved differently, both still present

- **`.ow-locked .lk-icon` is declared twice.** Round two folded the lock icon into the shared leading-icon box (`background:var(--icon-box)`, line ~889); round one's standalone `.ow-locked .lk-icon{background:#fff}` (line ~1518) survived. Same specificity, later wins — so this is the one box of six that ignores the design token.
- **`.saved-row .rowicon{background:none;width:34px}`** — the `width` half can never take effect. Round two's shared rule sets `flex:0 0 36px` on the same element, and for a flex item `flex-basis` beats `width`. Computed: `width:"34px"`, `flexBasis:"36px"`, renders 36. The `background:none` half still works.
- **Two focus-ring mechanisms now coexist.** Round one's comment above `.phone :focus-visible` says "**ONE rule** clears 3:1 on white, on the lavender ground AND on the two dark screens". Rounds 3/4 added a second, `!important` mechanism for the newly-dark app chrome. Both clear contrast comfortably (8.3:1 measured on the chrome), so this is **not** a defect — but round one's comment is now false, and the dark-screen inversion list was never extended to the map header that Round 4 darkened; the `!important` rule covers it by a different route.

## A6 · MEDIUM · Dead CSS whose markup a later round removed

| Selector | What happened |
|---|---|
| `.persona .p-ring` | R1 had the rule, a `.sel` variant and the markup. **R2 deleted all three.** R3 then re-introduced the selector inside a shared optical-alignment rule. No `.p-ring` markup exists anywhere. |
| `.state-card .sc-icon` | R1 had the rule plus three `<span class="sc-icon">` sites. **R2 removed all three markup sites**; the rule survived. |
| `.ob-word` (+ `.ob-mark .ob-word`, `.w-entry`, `.w-map`) | Present through R3. **R4 removed every one except the bare rule.** |
| `.receipt-note`, `.receipt-note.on` | Never had markup — dead in R1 too. Pre-existing. |

## A7 · MEDIUM · Round two's canonical type scale is bypassed everywhere it matters

The eight type steps are introduced with a comment claiming they are authored once as the canonical scale. Seven of the eight have **zero** uses:

`.t-display` 0 · `.t-h1` 0 · `.t-h2` 0 · **`.t-h3` 1** · `.t-body` 0 · `.t-sub` 0 · `.t-meta` 0 · `.t-micro` 0 · `.sel-row` 0

Rounds 2–4 instead apply `var(--fs-*)`/`var(--lh-*)`/`var(--ls-*)` inline on every component rule. The abstraction exists, is documented as the source of truth, and is used by exactly one heading ("Claim your door").

## A8 · LOW · Dead JS and freshly-authored dead data

- `function setGate2(on)` — defined, **never called**, in R1, R2, R3 and now. It is the only entry point to the `gate2` agreement-gating path, so the "Double-checking" fourth processing beat and the "usually under 15 seconds" caption are unreachable.
- The `FEATS` table's icon field is **never read** in any revision (`.label` is the only consumer). Round 4 nonetheless migrated all eight values from Unicode dingbats to library icon names — dead data, carefully re-authored.
- Orphan ids referenced by no JS, CSS, `aria-*`, `for` or `href`: `correct-photo-title`, `mybiz-sub`, `claim-search`. All three were already orphans in R1.

## A9 · LOW · Contradictory contrast documentation left by two rounds

Two incompatible luminance arguments for the *same* colour pair (`--blue-edge` against the ground tones) survive in the file: Round 4's says the floor is **0.4715** and the darkest tone drawn is **0.7235**; Round 3's, still in place further down, says **0.459** and **0.716**. The measured outcome is fine either way (4.45:1 worst case), so this is stale documentation, not a contrast failure — but a future round reading the wrong one has no way to tell which is current.

Also worth recording: `--track` moved from R1's `#847DA0` to `#86839A` and now self-documents **3.01:1**, measured 3.01:1. It passes with 0.01 to spare — the thinnest surviving margin from round one's contrast work.

## A10 · Categories that came back clean

Reported because a clean category is a result. **No** duplicate custom-property definitions (the 40 apparent ones all resolve to the legitimate `.phone.hc` override block). **No** duplicate or conflicting event handlers. **No** listener bound to a missing element, no dangling `getElementById`, no `aria-controls`/`aria-labelledby`/`aria-describedby`/`for` pointing at a missing id, no duplicate ids, zero console errors. `closeSheets`, `announceUI`, `toast`, `setBackgroundInert` and `visibleFocusables` are **byte-identical to round one**; `showScreen`, `openSheet` and `setCardPos` gained only additive visual code.

**And the finding that matters most about this list:** a rigorous static pass over rounds 1→4 found **no round-one accessibility behaviour removed or broken**. Every one of the ten defect classes R1 closed still works when driven — the claim gate, the photos gate, the processing announcements, the sheet focus return, the pin labels, the skip link, the list semantics, `aria-current`, the roving tabindex, the contrast tokens. That conclusion is correct.

The build's worst defect (S1) is still an accessibility regression, and it is invisible to that method, because it is not *in* any round's diff. It is an interaction between a rule round one wrote and a rule a later round left incomplete. Per-round verification cannot see it, and neither can a per-round audit — only driving the app with the setting turned on finds it.

---

# Verdict — is this stable enough to put in front of an audience?

**Not yet, but it is close, and the gap is small and specific.**

The build is in better shape than four rapid rewrites would predict. The demo spine holds up under deliberate attack: the owner face-flag gate cannot be walked around, user input cannot inject, rapid and interleaved tapping never desynchronises the screen state, leaving a scan mid-flow is clean, all 26 screens are labelled and take focus, and the largest text size does not clip anything. Nothing here crashes, hangs, or loses data.

What stands between it and an audience is a short list:

**Must be true before it is shown:**

1. **S1 is fixed.** Adding `transition-delay:0s !important` to both reduced-motion blocks addresses the trigger; having `openSheet` verify that focus actually landed (and retry, or focus the sheet itself) removes the whole fragile class. Right now, one setting in the app's own accessibility screen breaks focus into every sheet in the app, 12/12. If anyone demonstrates the accessibility settings — on a product whose entire premise is access — this is the thing that will be found, and it will be found in the most damaging possible context.
2. **S2 is fixed or the two controls are removed.** A `role="switch"` reporting `aria-checked="true"` while changing nothing is worse than no switch. Wiring distance and open-now into `filterPass` is small; hiding them until they work is smaller.
3. **S3 is fixed or the segment drops to two options.** Two labels, one behaviour, identical counts — easy to hit live by toggling between them.
4. **The claim confirmation stops promising an email it never collected (S5).** Either validate the contact field or change the copy.

**Should be true:**

5. S4 — the drag-up-collapses-to-peek wrap. It is one `if` and it is the most likely gesture in a card demo.
6. S7 — the stray pin focus artifact, visible to anyone demonstrating keyboard navigation.
7. S6 — the search overlay's missing inert/trap, if screen-reader behaviour is part of the story being told.

**Can wait:** S8–S13, and the whole of A5–A9 — the dead CSS, the unused type scale, the orphan ids, the contradictory comments. These are maintenance debt. They cost the *next* round time; they cost the audience nothing.

**One caveat on this verdict.** It describes a moving target. This file was rewritten five times during the sweep and is being edited now — Round 6 is in flight. Every defect above was re-confirmed against md5 `b5144030e73dbe9ffb919c67beb7ab11`, but that is already not the newest revision. **S1, S2, S3 and S4 should be re-run, not assumed fixed or assumed still broken, against whatever revision is actually demonstrated.** Reproductions are written to be repeatable for exactly that reason.

**A process note worth more than any single defect above.** Two of five spot-checked round claims were materially false in the same flattering direction (21 vs 28, four vs 27), and both had been reported as completed cleanups. Neither was a lie; both are what happens when a round counts what it changed rather than measuring what remains. Any round report that states a count should have that count re-derived from the file before it is believed — the measurement takes seconds and, in this sample, caught two errors in five.
