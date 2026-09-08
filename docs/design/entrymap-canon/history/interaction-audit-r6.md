# Interaction and motion audit

The build measured against `design/board-refs/entrymap-assets/asset-library/INTERACTION-MOTION-SPEC.md`,
its two token files (`tokens/interaction-motion.css`, `tokens/interaction-motion.json`),
`tokens/pin-hierarchy.json`, and the state assets under `svg/`. No round has been scored against
this spec before; `design/design-rubric.md` section 4 was written before it existed.

**What was measured, and how.** The prototype was served over HTTP and driven at 390&times;844.
Every number below was read out of the running page &mdash; `getComputedStyle`, `getAnimations()`
timings, `getBoundingClientRect()`, and instrumented flows &mdash; not read off the source and
believed. Where the spec names a number, the build's number is printed beside it.

**Basis.** The working tree of `design/phone-app-prototype.html` as of this audit
(md5 `8815db68c67c9a4a97b22064ffe60874`, 1,365,516 bytes), which is HEAD `25ea3de` plus 551
insertions and 359 deletions from an in-flight asset-fidelity pass by another agent. That file
was frozen to a scratch copy and served from there, so nothing shifted mid-measurement. The
in-flight pass is a colour and pin-artwork pass; two of its changes are already visible in the
measurements below and are credited where they land (the sky-blue focus ring on the header and
bottom navigation; the estimated tier's sky700 dash colour).

**Nothing in the build was changed. This is a report only.**

---

## Summary

| | Count |
|---|---:|
| Outright violations | 20 |
| Numeric drift | 19 |
| Confirmed conforming | 21 |

The three worth fixing first are at the end, in the punch list.

---

## Part 1 &mdash; Outright violations

A required behaviour, state or prohibition that the build does not have at all. Ordered by severity.

### V1. There is no unavailable state anywhere in the build

**Spec.** &ldquo;Every actionable control has five states &hellip; Unavailable: pale-lavender fill and
deep-indigo label &hellip; Unavailable controls never become gray.&rdquo;

**Build.** The fifth state does not exist. Measured on the running page:

```
document.querySelectorAll('[disabled],[aria-disabled]').length   ->  0
cssText().match(/:disabled|\[disabled\]|aria-disabled/g)         ->  null  (0 rules)
```

Zero elements carry a disabled attribute, and the stylesheet has no rule for one. The behavioural
half of the clause is partly served &mdash; the two publish gates let you press the control and
then explain inline what is missing, which is the spec's &ldquo;tapping explains what is needed&rdquo;
and is a better answer than a dead button &mdash; but there is no visual affordance at all, so a
user cannot tell before pressing that a control is not yet available. The prohibition on grey is
satisfied vacuously.

**Change that would conform.** Add an `aria-disabled="true"` treatment on `.btn` and the other
control classes using the asset's own values from `controls/primary-unavailable.svg`: fill
`#E2DAFF` (`--lavender200`), label `#17103D` (`--indigo900`), border the same as the fill. Keep the
control focusable and pressable so the existing inline explanation still fires.

### V2. The Estimated tier is re-encoded on the map, not merely scaled

**Spec.** Fixed trust encoding: Estimated is a &ldquo;hollow dashed pin with italic `i`&rdquo;.
`pin-hierarchy.json` opens with the crux: &ldquo;Trust tier and contextual prominence are
independent. Context may scale a pin but never changes its tier encoding.&rdquo;

**Build.** On the map, `est` is routed through `pinSVG('ring', 14)` and renders as a dashed circle
with no teardrop and no glyph:

```html
<svg width="33.43" height="33.43" viewBox="0 0 40 40">
  <circle cx="20" cy="20" r="7" fill="#FFF" fill-opacity=".72"
          stroke="var(--blue-edge,#1266A6)" stroke-width="2.75"
          stroke-dasharray="3.1 2.6"/>
</svg>
```

The `40`-unit box is drawn at 33.43px, so the visible ring is `33.43 &times; (14+2.75) / 40` &asymp;
**14px**. The size table confirms it is by design: `const LEVEL = { owner:{size:40}, scan:{size:30},
est:{size:14} }`. The build's own `visual-language.md` section 15 already names this as the conflict;
this audit confirms it live.

The correctly-encoded estimated pin **already exists in the file** &mdash; `pinSVG('est', &hellip;)`
draws the dashed teardrop with the italic `i` and the three empty confidence dots, and is used in the
legend, the card, the list rows and the welcome screen. It is only the map that substitutes the ring.

**Change that would conform.** Call `pinSVG('est', 40)` on the map and let clustering carry the
density work. The clustering already works: at overview, 17 clusters absorb 55 of the 64 marks
(9 pins left on screen), which is the reconciliation section 15 proposed.

### V3. The card sheet does not follow the drag, and ignores release velocity

**Spec.** &ldquo;Sheets follow the drag gesture one-to-one &hellip; Release velocity influences the
destination stop.&rdquo;

**Build.** There is no `pointermove` handler on `#sheet-card`. `pointerdown` records `y0`;
`pointerup` applies a fixed &plusmn;28px threshold and steps exactly one stop:

```js
sh.addEventListener('pointerup',e=>{
  const dy=e.clientY-y0;
  if(dy>28) stepCard(-1);
  else if(dy<-28) stepCard(+1);
  else if(tapOnGrip) stepCard(+1);
});
```

The sheet is motionless under the finger for the whole gesture and then jumps one stop. A fast flick
from peek cannot reach full; a slow 200px drag and a 29px twitch do the same thing.

**Change that would conform.** Add a `pointermove` handler writing `translateY` from the delta, and
on release compute `dy/dt` and select the stop the velocity projects onto rather than the adjacent one.

### V4. The map is never veiled at full height, and the veil that exists is 42%

**Spec.** &ldquo;The map dims with a 7% deep-indigo veil only at full height.&rdquo;

**Build.** Measured with the card at its full stop: `document.querySelector('.scrim')
.classList.contains('on')` is **`false`**. The card sheet never dims the map at any stop. The scrim
that exists, used by the modal popups and the receipt sheet, is
`background: rgba(23, 20, 31, 0.42)` &mdash; **42%**, against the spec's 7%, and its colour
`#17141F` is not `--indigo900` `#17103D`.

**Change that would conform.** Bind a `rgba(23,16,61,.07)` veil to `#sheet-card[data-pos="full"]`
only, and restate the modal scrim on `--indigo900`.

### V5. The outgoing screen does not move at all on hierarchical navigation

**Spec.** &ldquo;Current screen moves 12 px left and fades to 88% opacity.&rdquo;

**Build.** Screens are swapped by display:

```css
.screen        { position:absolute; inset:0; display:none; flex-direction:column; }
.screen.active { display:flex; }
```

The only screen exit rules in the file are `#scan-processing.leaving .scan-body{opacity:0}`,
`.splash.leaving`, and `.achip.leaving` &mdash; nothing for the general case. The departing screen
vanishes on the frame the destination appears. Half of the spec's hierarchical transition is absent,
and the 88% opacity the spec puts on the *outgoing* screen has instead been applied to the *incoming*
one, which starts at `opacity: 0` and fades up.

**Change that would conform.** Hold the outgoing `.screen` for the transition duration with a
`screen-exit` keyframe (`translateX(0) -> translateX(-12px)`, `opacity 1 -> .88`) before setting
`display:none`, and mirror it for back.

### V6. Peer navigation crossfades but does not settle up 8px

**Spec.** &ldquo;Content crossfades and settles upward by 8 px.&rdquo;

**Build.** Verified live &mdash; tapping Profile sets `data-dir="lat"` and runs:

```css
@keyframes screen-lat { 0% { opacity: 0; } 100% { opacity: 1; } }
```

Opacity only. There is a `settle-in` keyframe in the file that does exactly the 8px rise the spec
asks for, but it is scoped to `#scan-review`, `.wl-card`, `.wl-hero` and `.ob-body` &mdash; never to
peer navigation.

**Change that would conform.** Add `transform: translateY(8px) -> none` to `screen-lat`, or point the
`lat` direction at the existing `settle-in` keyframe (which travels 10px; trim to 8).

### V7. The bottom-navigation indicator does not move, and sits above the tab

**Spec.** &ldquo;Bottom-navigation selection indicator moves beneath the destination.&rdquo;

**Build.** The indicator is a per-tab pseudo-element that simply appears on whichever tab is active:

```css
.navbtn.on::before { content:""; position:absolute; top:-6px; left:24%; right:24%;
                     height:4px; border-radius:0 0 4px 4px; background:currentcolor; }
```

`top:-6px` places it **above** the tab, and because it belongs to the tab rather than the bar it
cannot travel &mdash; it blinks out of one tab and into another. There is no transition on it.

Separately, the bar diverges from `navigation-states/*.svg`, which draws the active state as a filled
90&times;58 r18 pill (violet600 for Map and Profile, indigo900 for Scan) with white contents. The build
uses a coloured top bar and a per-tab ink instead (`#1D5FA8` map, `#6E4A00` scan, `#4A4463` profile).
That divergence is defended in the rubric (3.6) as a directive from the product owner about the
bottom bar carrying the logo palette, so it is recorded here rather than counted as a violation.

**Change that would conform.** One indicator element owned by `.navbar`, positioned by `transform:
translateX()`, transitioned over 180ms, and rendered below the label rather than above the icon.

### V8. The pin drop ends with two marigold ripples, not one sky-blue one

**Spec.** &ldquo;&hellip; settles with one sky-blue ripple.&rdquo;

**Build.**

```css
.rippler { width:34px; height:34px; border-radius:50%;
           border:3px solid var(--marigold);
           animation: ripple var(--dur-ripple) var(--ease-enter) 2; }
```

`--dur-ripple` is 1000ms and the iteration count is **2**, so the ripple runs for two full seconds
after a 700ms drop, in **marigold** rather than sky blue. The token file's own
`.entrymap-pin-ripple` is 520ms, one iteration, `3px solid var(--entrymap-sky)`.

**Change that would conform.** `border-color: var(--sky400)`, iteration count `1`, and bring the
duration back toward the token's 520ms so the tail does not outlast the drop by 3&times;.

### V9. The cluster mark impersonates the owner-confirmed tier and carries no composition arcs

**Spec.** &ldquo;Mixed cluster: 48 px deep-indigo count marker with sky-blue, marigold, and violet
composition arcs. A cluster never impersonates a trust tier.&rdquo;

**Build.** `pinSVG('cluster')` draws a white disc with a **violet** dashed outer ring and a
**violet-ink** count:

```js
'<circle cx="24" cy="24" r="22.4" stroke="var(--purple,#5B35F5)" stroke-dasharray="2.4 6"/>'
'<circle cx="24" cy="24" r="17"   stroke="var(--purple-ink,#4020B5)" stroke-width="2.8"/>'
'<text  ... fill="var(--purple-ink,#4020B5)">' + count + '</text>'
```

Violet is the owner-confirmed tier colour, so a cluster of 4 estimated places is drawn in the colour
of the highest tier &mdash; exactly the impersonation the clause forbids. There are no composition
arcs, so the mix is invisible; the build already computes that mix for the aria-label
(`"4 entrances here (4 estimated)"`), so the data is on hand.

The size is right: measured **48.0px**, matching `clusterPx: 48` exactly.

**Change that would conform.** Restate the count and rim on `--indigo900`, and draw the outer ring as
three arcs proportioned to the tier counts already computed for the label.

### V10. &ldquo;Suggest a correction&rdquo; is missing from the evidence receipt

**Spec.** &ldquo;&lsquo;Suggest a correction&rsquo; remains visible at the end of every receipt.&rdquo;

**Build.** Measured on the open `#sheet-receipt`: `/Suggest a correction/i.test(innerText)` is
**`false`**. The sheet ends on `.rcpt-foot` &mdash; &ldquo;Sources, dates, and confidence &mdash; not
a badge.&rdquo; The control is present on the card (`cardHasCorrection: true`), so it is only the
deeper receipt that drops it &mdash; which is the surface a user reaches precisely when they want to
dispute something.

### V11. Receipt expansion is instantaneous, with no height animation

**Spec.** &ldquo;Receipt height animates over 240 ms without moving the selected chip offscreen.&rdquo;

**Build.** The chip anchoring half is correct and was measured: tapping a feature chip left it at
`y = 301.99` before and `y = 301.99` after, with the receipt opening beneath it. But the expansion is
a display toggle with no animation:

```css
.receipt-note    { display: none; }
.receipt-note.on { display: block; }
```

`getComputedStyle(box).transition` returns `null` because the element is not in the layout until it
is shown. Height goes 0 to full in one frame.

**Change that would conform.** Animate `grid-template-rows: 0fr -> 1fr` (or a measured max-height)
over `240ms`, keeping the chip's own position untouched as it already is.

### V12. There are no haptics anywhere in the build

**Spec.** Light haptic on press; medium haptic on the Scan control and at capture; &ldquo;Haptics
remain available unless disabled by the operating system.&rdquo;

**Build.** `(src.match(/vibrate|haptic/gi) || []).length` is **0**. The Vibration API is never called
and the intent is not recorded anywhere in the file.

There is a legitimate reason a browser prototype might skip this &mdash; `navigator.vibrate` is
unsupported in iOS Safari &mdash; but the spec asks for it, three states in the button table depend on
it, and the build neither attempts it nor says why not.

### V13. Confidence dots do not fill left to right

**Spec.** &ldquo;Confidence dots fill from left to right, 70 ms apart.&rdquo;

**Build.** Static opacity, no animation, no stagger:

```css
.dots i   { width:7px; height:7px; border-radius:50%; background:currentcolor; opacity:.25; }
.dots i.f { opacity:1; }
```

### V14. Outlined checks do not draw

**Spec.** &ldquo;Outlined checks draw over 180 ms.&rdquo;

**Build.** `.ci-dot` changes `border-color`, `background-color` and `color` over `--dur-base` (220ms).
Nothing in the file uses `stroke-dasharray` / `stroke-dashoffset` to draw a check path; the token
file's `.entrymap-check-draw` (dasharray 32, 180ms) has no counterpart in the build. The check is
faded in, not drawn.

### V15. Toasts cannot be swiped away

**Spec.** &ldquo;Toasts &hellip; can be swiped away.&rdquo;

**Build.** No pointer or touch listener is attached to `#toast`. The only dismissal is the timer.

### V16. The stale-claim clock rotation does not exist

**Spec.** &ldquo;A stale claim gains a muted-amber clock rotation of 20 degrees and returns to rest.&rdquo;

**Build.** The only `rotate()` in the stylesheet is `rotate(-90deg)` on the progress ring's SVG. There
is no 20&deg; clock gesture. The copy half of the clause is met &mdash; the ageing language describes
time, not the place (&ldquo;Scanned 14 months ago &mdash; re-check&rdquo;, &ldquo;the estimate stays
honest about its age&rdquo;) &mdash; and it is carried in amber. Only the motion is missing.

### V17. The freshness clock overlay never appears on a pin

**Spec.** &ldquo;Freshness adds a muted-amber clock marker. It does not recolor the pin.&rdquo;
`pin-overlays/freshness-clock.svg` is a 40-unit marigold disc with a white 3px rim and an indigo clock hand.

**Build.** No clock marker is drawn on any map pin in any state. Freshness reaches the card, the list
rows and the aria-label in amber, and it correctly never recolours the pin &mdash; the prohibition
half holds &mdash; but the specified overlay is absent, so freshness is invisible on the map itself.

### V18. The selected-pin overlay is missing; selection is carried by scale and by dimming everything else

**Spec / `pin-hierarchy.json`.** &ldquo;Selection raises a pin 6 px, scales it approximately 12%, and
adds a white keyline.&rdquo; The overlay entry: &ldquo;white keyline + indigo outer line + 12% lift;
preserve tier colour and icon.&rdquo; `pin-overlays/selected-keyline.svg` is a white 8px ring inside
an indigo 3px ring.

**Build.**

```css
.pinbtn.selected .pin      { transform: translateX(-50%) scale(1.22); }
.pinbtn.selected.lvl3 .pin { transform: translate(-50%,-50%) scale(1.5); }
.pinbtn.recede             { opacity: .8; }
```

No keyline, no outer line, no 6px lift &mdash; and the selection is communicated as much by receding
every *other* pin to 80% as by growing the selected one. The colour prohibition is respected (nothing
is recoloured), but the specified overlay is not drawn.

### V19. The selected pin's screen position is not preserved as the sheet opens

**Spec.** &ldquo;Preserve the selected pin's screen position as the sheet opens&rdquo; and
&ldquo;Opening from a selected entrance visually originates near that pin.&rdquo;

**Build.** Measured on one pin through a full open:

| Moment | Pin screen y |
|---|---:|
| Before open | 380.3 |
| Card at peek | 539.0 |
| Card at full | 198.9 |

The pin travels 159px down, then 340px up. `revealSelected()` deliberately pans the map to keep the
pin above the sheet, which serves the *intent* (the pin stays visible) but is the opposite of the
clause as written. The sheet itself slides up from the bottom edge (`translateY(105%) -> 0`); it does
not originate near the pin.

### V20. Four beats of the live scan sequence are missing

The overall duration is right &mdash; see C13 &mdash; but four named beats are absent.

- **Capture (0&ndash;100 ms): no white shutter wash.** The only capture treatment is
  `.shutter:active{transform:scale(.93)}`. The screen goes straight to processing. The frozen frame
  itself is captured correctly.
- **&ldquo;A single soft violet highlight crosses the photo.&rdquo;** No sweep exists. The token
  file's `.entrymap-processing-sweep` (a violet 18% gradient, 1100ms, one iteration) has no
  counterpart in the build. The spec's real constraint here is *do not loop it and do not add
  sparkles* &mdash; the build satisfies that by having nothing, but the beat is not there.
- **The checklist does not match the spec's four events.** Spec: Doorway framed / Entry path visible /
  **Entrance features checked** / Photo quality checked. Build: Doorway framed / Entry path visible /
  Photo quality checked, with a fourth slot holding &ldquo;Double-checking&rdquo;, hidden unless the
  agreement gate is on. &ldquo;Entrance features checked&rdquo; is missing and
  &ldquo;Double-checking&rdquo; is not in the spec's list.
- **Map return (7,360&ndash;7,600 ms): the photo card never contracts toward its map location.** The
  flow goes from processing to a `scan-review` screen. The contraction toward the map exists only
  later, on the `scan-done` mini-map, and only as the pin drop.

---

## Part 2 &mdash; State assets

Measured against `svg/chip-states`, `svg/field-states`, `svg/navigation-states`, `svg/sheet-states`
and `svg/feedback`. These are fidelity findings, not motion findings, and the two that matter are
called out first.

### A1. &ldquo;Needs attention&rdquo; on a field is drawn in the same purple as focus and selection

`field-states/needs-attention.svg` uses a **marigold** `#FFBF24` 2.5px border plus a marigold dot and
helper text &mdash; a colour reserved for &ldquo;this needs you&rdquo;, deliberately not red.

The build uses purple for it:

```css
[aria-invalid="true"]           { box-shadow: 0 0 0 2px var(--purple); }
.authz[data-invalid="true"]     { outline: 2px solid var(--purple); outline-offset: 4px; }
```

`--purple` is `#5B35F5`, which is also the focus-ring colour and the selection colour throughout the
build. The no-red rule is honoured, but a field needing attention now looks like a field that is
focused. The asset's marigold answer is available in the palette already.

### A2. The field &ldquo;filled&rdquo; state does not exist

`field-states` ships four: empty (lavender200 border), filled (violet800 border + a check icon at the
right edge), focused (violet800 border + a 3px sky ring), needs-attention (marigold). The build has
empty and focused only; a filled field looks identical to an empty one &mdash; border stays
`--edge`, no check icon.

### A3. Other divergences, recorded without a severity claim

| Asset | Asset says | Build does |
|---|---|---|
| `chip-states/filter-selected` | indigo900 fill, white label, sky400 dot with an indigo check | `.filtchip.sel` &mdash; purple-wash fill, purple border, purple-ink label, plus a `.sel-dot` |
| `chip-states/filter-focus` | sky400 3px outer ring + violet600 2.5px border | purple 3px ring + a white 6px halo |
| `chip-states/feature-aging` | white with a **marigold** border | `.fchip` is tinted by **tier** (`est` / `scan` / `owner`), not by freshness |
| `chip-states/feature-unknown` | lavender100 fill, dashed sky400 border, &ldquo;Not yet seen / Be the first to scan&rdquo; | `.unknown-row` &mdash; blue-wash fill, dashed blue border; **copy matches exactly** (see C11) |
| `controls/primary-pressed` | fill deepens violet600 -> violet800 **and** scales .97 | scale .97 only; no `:active` rule anywhere changes `background` on `.btn`, and **zero** `:active` rules change `box-shadow` |
| `feedback/*-toast` | indigo900 card, coloured icon disc, a bold title line and a detail line | one line of plain text on `--ink`; no icon, no title/detail split |
| `feedback/camera-permission-dialog` | &ldquo;Allow camera access / Only the doorway is captured.&rdquo; + a marigold &ldquo;Allow camera&rdquo; | primer copy is close in substance; the **denial** screen offers &ldquo;Choose an existing photo&rdquo; where the spec names &ldquo;Open settings&rdquo; and &ldquo;Keep exploring&rdquo; |
| correction completion | spec: reads &ldquo;Suggestion sent&rdquo;, with a compact receipt animation | reads &ldquo;Thanks &mdash; we'll review your note with the community.&rdquo;; no receipt animation |
| `sheet-states/{peek,half,full}` | three named stops | three named stops, `data-pos="peek|medium|full"` &mdash; **structurally conforming**; the heights drift (D8) |
| `navigation-states/keyboard-focus` | sky400 3px ring on the tab | sky400 ring on `.apphead` and `.navbar` &mdash; **conforming**, and newly so from the in-flight pass |

---

## Part 3 &mdash; Numeric drift

The right shape, the wrong number. Nothing here is a missing behaviour.

### D1. The build has two general durations where the spec names nine

Read from `:root` on the running page:

```
--dur-fast 160ms   --dur-base 220ms
--dur-settle 900ms --dur-check 1500ms --dur-drop 700ms --dur-ripple 1000ms
--ease-enter  cubic-bezier(.2,.7,.2,1)
--ease-exit   cubic-bezier(.4,0,1,1)
--ease-spring cubic-bezier(.2,.9,.3,1.2)
```

Counted across the whole committed stylesheet, the only literal time values that remain are those
six plus `0s` &times;6, `0.01ms` &times;4 and `0.25s` &times;2 (the progress arcs). That consolidation
is a real achievement and rubric 4.2 scores it 4 &mdash; but it collapses distinctions the spec draws.

| Spec | Spec value | Build value |
|---|---:|---:|
| Press | 100ms | 0ms (`:active { transition:none }`) |
| Focus ring | 120ms | 0ms (no transition on `outline`) |
| Release | 180ms | 160ms |
| Peer navigation | 180ms | 220ms |
| Check draw | 180ms | 220ms, and it fades rather than draws (V14) |
| Toast enter | 220ms | 220ms transform / 160ms opacity |
| Receipt expand | 240ms | 0ms (V11) |
| Screen transition | 260ms | 220ms |
| Sheet snap | 320ms | 220ms in, 160ms out |
| Map camera | 450ms | 220ms |
| Pin drop | 620ms | 700ms |

Every ordinary-feedback value sits inside the spec's 90&ndash;320ms band. The map camera at 220ms is
the one that is *below* where the spec wants it &mdash; a geographic move reads as a jump rather than
a camera.

### D2&ndash;D4. Button states

- **D2. Press scale.** `scale(0.97)` at three rule sites covering most controls, but `.shutter` is
  `0.93` and `.nav-scan .ring` is `0.95`. Three values where the spec names one. Both exceptions are
  defended in rubric 5.3 as physically larger controls.
- **D3. Release has no spring.** The release runs on `--ease-enter` `cubic-bezier(.2,.7,.2,1)`,
  whose control points never exceed 1 &mdash; there is no overshoot. The spec asks for &ldquo;a soft
  spring&rdquo;. The build has a spring curve (`--ease-spring`) but scopes it to `dropIn` and `pinTap`
  only.
- **D4. Focus ring.** Width **3px** &check;. Offset **2px** against the spec's 3px. Colour
  `--purple` `#5B35F5` on `.phone :focus-visible`, `--sky400` `#69B7FF` on `.apphead` and `.navbar`
  only, `--lavender100` on the three dark screens. The spec asks for sky blue throughout. It appears
  instantly rather than over 120ms &mdash; arguably correct, since the spec's own accessibility
  section says keyboard focus &ldquo;must not rely on motion&rdquo;.

### D5&ndash;D7. Transitions

- **D5. Hierarchical.** 220ms (spec 260); destination enters from **12px** (spec 24px); easing
  `cubic-bezier(.2,.7,.2,1)` against the spec's named `cubic-bezier(.2,.75,.25,1)`.
- **D6. Peer.** 220ms (spec 180).
- **D7. Sheet snap.** 220ms in, 160ms out, on `--ease-enter`. The spec names
  `cubic-bezier(.22,.9,.28,1.08)` &mdash; a 1.08 overshoot that exists nowhere in the build. The
  asymmetry (out faster than in) is a deliberate craft choice defended in rubric 4.2 and is not
  contradicted by the spec.

### D8. Sheet stops

Measured on the 844px phone with the card at each stop:

| Stop | Spec | Build height | Build % |
|---|---:|---:|---:|
| Peek | 18% | 176.3px | **20.9%** |
| Half / medium | 54% | 353.8px | **41.9%** |
| Full | 92% | 718.0px | **85.1%** |

The middle stop is the furthest off, 12.1 points low. The full stop is capped by
`#sheet-card{ bottom:86px; max-height:calc(100% - 126px) }`, which reserves the bottom navigation;
reaching 92% needs the sheet to overlay the bar.

### D9&ndash;D14. Map and pins

- **D9. Map camera.** 220ms against 450ms.
- **D10. Pin drop.** `--dur-drop` **700ms** against 620ms. Easing
  `cubic-bezier(.2,.9,.3,1.2)` against the token's `cubic-bezier(.2,.9,.25,1.2)` &mdash; the same
  spring with one control point moved 0.05.
- **D11. Pin sizes on the map.** Measured SVG heights, identical at both zoom levels:

  | Tier | Spec overview | Spec street | Build (both) |
  |---|---:|---:|---:|
  | Estimated | 32 | 40 | **~14** (33.4px box, 14px ring) |
  | Scanned on-site | 36 | 44 | **30** |
  | Owner-confirmed | 40 | 48 | **40** |

  Two problems beyond the numbers: the build has **one** size set where the spec has two, so zoom
  changes clustering but not scale; and because the estimated ring's *box* is 33.4px against the
  scanned pin's 35.3px width, the two tiers read as nearly the same footprint on screen even though
  the spec puts a 4px step between them in the other direction.
- **D12. Selected sizes.** Selection scales `1.22` (`1.5` for the estimated ring), against the spec's
  ~12%, and applies no 6px lift.

  | Tier | Spec selected | Build |
  |---|---:|---:|
  | Estimated | 52 | 14 &times; 1.5 = **21** |
  | Scanned on-site | 56 | 30 &times; 1.22 = **36.6** |
  | Owner-confirmed | 60 | 40 &times; 1.22 = **48.8** |
- **D13. Card and receipt sizes.** Spec 24 / 28 / 32. Build varies by call site: search rows 20/22,
  list rows 22/26, nearby rows 24/28, legends 20/24. The nearby rows are closest; owner is 28 where
  the spec says 32.
- **D14. Live scan drop.** `pinSVG('scan', 34)` &mdash; **34px** against the spec's 64px. On the real
  map the same drop plays at the pin's ordinary 30px.

### D15&ndash;D19. Everything else

- **D15. Chip stagger.** `c.style.animationDelay = (i * 220) + 'ms'` &mdash; **220ms** apart against
  the spec's 60ms, 3.7&times; too slow. The spec allots 240ms for the whole chip entrance
  (7,120&ndash;7,360); at 220ms the third chip only starts at 440ms.
- **D16. Toast.** Rises **20px** (spec 12). Anchored `bottom:104px` above an 86px navigation bar, an
  **18px** clearance (spec 12). Dwell **4,200ms** (spec 3,000&ndash;4,000).
- **D17. Photo settle.** `.ring-photo` goes `scale(1.14) -> none` over `--dur-settle` **900ms**. The
  spec's frame-confirmation beat is a **3%** contraction over **100&ndash;380ms**. The build's is
  14% over 900ms &mdash; nearly 5&times; the contraction over 3&times; the time.
- **D18. Touch targets.** The build standardises on **44&times;44** (the WCAG 2.5.5 AAA figure); the
  spec and `interaction-motion.json` both say **48&times;48**. Measured on the map screen: 89 of 115
  visible interactive elements are under 48 in one dimension. Two are genuinely under 44 &mdash; one
  `.sheet-close` at 40&times;40 and the `.toggle` at 52&times;31. The 64 pins measure 0&times;0 on the
  button itself but carry a 44&times;44 `::before` hit area.
- **D19. Scan beat map.** Instrumented from the shutter press:

  | Event | Spec window | Measured |
  |---|---|---:|
  | Processing screen | 100&ndash;380ms | 33ms |
  | &ldquo;Doorway framed&rdquo; | within 380&ndash;7,000ms | 2,528ms |
  | &ldquo;Entry path visible&rdquo; | ,, | 4,027ms |
  | &ldquo;Photo quality checked&rdquo; | ,, | 5,446ms |
  | Chips populate | 7,120&ndash;7,360ms | 5,510ms |
  | Review | ~7,600ms | **7,430ms** |

  The total lands inside budget. The internal shape differs: the build front-loads a 1,000ms settle
  and spends 1,500ms per check, so the last check lands 1.5s early and the chips sit on screen for
  nearly two seconds before the screen changes.

---

## Part 4 &mdash; What already conforms

Three rounds of motion work stand behind this build, and confirming what holds is part of the value.
Each of the following was measured, not assumed.

**The prohibitions all hold.**

1. **No red.** 58 distinct hex values in the stylesheet. Converting each to HSL, exactly one falls in
   the red hue band, and it is `#523022` (h 17&deg;, s 41%, l 23%) &mdash; the high-contrast marigold
   ink, a brown. There is no red anywhere in the build.
2. **No grey.** Zero hex values with saturation &le;8% between lightness 12 and 95.
3. **No shaking, no failure-shaped motion.** The eleven keyframes are `dropIn`, `ripple`,
   `settle-in`, `pinTap`, `splashIn`, `splashOut`, `chipIn`, `chipOut`, `screen-fwd`, `screen-back`,
   `screen-lat`. None is a shake, a wobble or a rejection gesture. Offline scans fold into a
   &ldquo;Saved for later&rdquo; card with no shake and no negative grade, as the spec asks.
4. **No trust pin is recoloured to communicate selection, matching, freshness or provenance.**
   This is the spec's hardest prohibition and the build holds it on all four counts, checked
   individually:
   - *Selection* changes `transform` only &mdash; `scale(1.22)`, no fill or stroke change.
   - *Match* is drawn by `matchHalo()` as an **external** ring at r50 around the pin head; the pin
     body's fill and stroke are untouched. On the estimated ring the halo is a separate circle at
     r13.4 outside the r7 ring.
   - *Freshness* never touches the pin at all.
   - *Provenance* &mdash; the Texas flag appears at exactly one site, beside the state-record line in
     a receipt, with the code comment &ldquo;the ONLY place the Texas flag appears&rdquo; and the
     row's own subtitle reading &ldquo;informs the receipt, never the pin tier&rdquo;.

   The one nuance: `.pinbtn.recede{opacity:.8}` composites non-selected pins at 80% over the ground,
   which shifts their apparent colour. That is a prominence change, not a tier re-encoding, and the
   contrast of the receded state was measured in a previous round (rubric 3.4) and clears 3:1.

**The trust system's independent carriers hold.**

5. **Match halo line styles match the library exactly.** Solid for good (indigo900 with a quiet
   sky400 inner ring), dashed for partial (violet600), dotted for unknown (sky700) &mdash; the same
   line-style-first encoding as `halos/*.svg`, and the app prints the words as well, so colour is
   never the only carrier.
6. **Cluster size is exact.** Measured 48.0px against `clusterPx: 48`.
7. **Render order is correct in relative terms.** Measured z-index: cluster 5 < estimated 10 <
   scanned 20 < owner 30 < selected 900. The absolute values differ from the token's
   10/20/30/40/50/60/70, but no pair is inverted and the live drop sits on top of everything.
8. **Texas provenance is receipt-only** (see 4 above).

**Navigation and structure.**

9. **Screen transitions are directional, and the direction is real.** `data-dir` reads `fwd` after
   `goScreen`, `back` after `goBack`, `lat` after a bottom-nav tab &mdash; verified live. Back
   genuinely reverses forward: `screen-back` is `screen-fwd` mirrored on the x axis.
10. **The sheet has exactly three named stops**, `data-pos="peek|medium|full"`, matching
    `sheet-states/{peek,half,full}.svg` structurally, with content revealed progressively
    (`.cs-medium`, `.cs-full`) rather than all at once.
11. **The chip stays anchored while its receipt expands beneath it.** Measured y 301.99 before and
    301.99 after.
12. **Independent provenance lines appear together.** The receipt writes every row in one pass; none
    is revealed sequentially.
13. **The bottom navigation's keyboard focus is sky400**, matching
    `navigation-states/keyboard-focus.svg`.

**Copy and honesty.**

14. **The unknown-feature invitation is the spec's copy verbatim:** &ldquo;Not yet seen &mdash; be
    the first to scan.&rdquo;
15. **Checklist items correspond to real completed processing steps.** The tick is out of the
    accessibility tree until the check lands and the announced text agrees with the visible text; the
    build does not show fake progress labels. It also holds at 96% rather than lying when a live
    upload is still outstanding.
16. **Ageing copy describes time, not the place** &mdash; &ldquo;Scanned 14 months ago &mdash;
    re-check&rdquo;, &ldquo;the estimate stays honest about its age&rdquo;.

**Timing and the scan.**

17. **The scan lands inside its budget.** 7,430ms from shutter to review, against a ~7,600ms target
    and an 8,000ms ceiling.
18. **Every ordinary feedback duration sits inside the 90&ndash;320ms band** (160 and 220), and the
    four narrative constants are named and scoped to the scan sequence.
19. **Progress is the only thing that eases linearly.** Three `linear` values in the stylesheet: the
    two progress arcs' `stroke-dashoffset` and the progress bar's `width`. Zero `ease-in`, zero
    `ease-out`.

**Accessibility behaviour the spec names.**

20. **Processing announces through a polite live region** &mdash; `#proc-live`, one of four polite
    regions in the build, and completion is announced once.
21. **Every actionable control has a press treatment and a visible focus ring.** 44 of the 47
    elements carrying `cursor:pointer` have an `:active` rule; the three that do not are `.pinbtn`
    (which has the `pinTap` squash instead) and two native inputs whose containing rows press around
    them. Focus never relies on motion.

---

## Part 5 &mdash; The two things most likely to be wrong

The brief named these two specifically, because both predate the spec. Answered directly.

### Is any pin recoloured to show selection, match, freshness or provenance?

**No.** Checked all four independently; the evidence is in Part 4, item 4. Selection is a transform;
match is an external ring whose line style is the carrier; freshness never reaches the pin; the Texas
flag appears at exactly one site and the code says so. This is the spec's strictest prohibition and
the build is clean on it.

What the build gets wrong on pins is a different thing: it **re-encodes** a tier (V2, Estimated drawn
as a 14px ring instead of a dashed pin with an italic `i`) and it **omits** two specified overlays
(V17 freshness clock, V18 selected keyline). Those are failures of the encoding table and the overlay
list, not of the recolouring prohibition.

### Does every animation have a genuine instant equivalent under reduced motion, or merely a shorter one?

**Merely a shorter one &mdash; and it happens to work, for reasons the rule itself does not guarantee.**

The entire reduced-motion implementation is two identical blanket rules, one on the media query and
one on an in-app class:

```css
@media (prefers-reduced-motion: reduce) {
  *, ::before, ::after { animation-duration:.01ms !important;
                         animation-iteration-count:1 !important;
                         transition-duration:.01ms !important; }
}
.phone.rm *, .phone.rm ::before, .phone.rm ::after { /* identical */ }
```

That is the definition of shortening rather than replacing. Measured with the in-app toggle on and
the OS setting off: screen animation duration `1e-05s`, sheet transition `1e-05s`, button transition
`1e-05s` &mdash; the two paths agree, which is itself worth crediting, because an in-app preference
that silently failed to reach the CSS would be worse than having none.

**Every animation was then checked individually for whether 0.01ms actually leaves it in the correct
final state. None is currently left mid-flight.** But that outcome rests on two properties the rule
does not enforce:

- Eight of the eleven keyframes declare `both` or `forwards` fill, so a 0.01ms run reaches frame 100%
  and stays. Correct by construction.
- The three that declare **no fill** &mdash; `dropIn`, `pinTap`, `ripple` &mdash; revert to their
  underlying style, which in each case happens to be the correct resting state. And two of the three
  are additionally removed in JS: `${isReduced() ? '' : '<span class="rippler"></span>'}` never
  creates the ripple element, and the `.pin-drop` class is never added. **Those two are genuine
  instant equivalents**, and they are the model the rest should follow.

Add one keyframe without a fill mode whose start state is not the resting state, and it will break
silently with no test to catch it.

Three of the spec's positive reduced-motion requirements are not met by a blanket:

- **&ldquo;Screen transitions become instant crossfades no longer than 80 ms.&rdquo;** The build
  gives 0.01ms and therefore no crossfade at all. Technically inside the 80ms ceiling; the crossfade
  the clause asks for is gone.
- **&ldquo;Checks and confidence dots appear in their final states.&rdquo;** Vacuously satisfied,
  because neither is animated in the first place (V13, V14). Fixing those two will create a
  reduced-motion obligation that does not exist today.
- **`animation-iteration-count: 1 !important` is unconditional and global.** Harmless right now
  because nothing in the build loops &mdash; but it silently caps any future indeterminate indicator
  at a single pass, which is a correctness bug rather than a motion preference.

**The one part that is genuinely re-authored, and is the best thing in the build's motion system:**
processing under reduced motion is not a faster animation, it is a different presentation. The ring
is removed (`display:none`), a determinate bar replaces it, `checkitem` transform and transition are
stripped, the checks land, the announcement fires, and the flow completes to Review. That is exactly
what the spec asks for &mdash; &ldquo;retains the checklist and textual progress but removes sweeps,
scaling, and rotation&rdquo; &mdash; and it is the pattern the rest of the build needs.

One structural safeguard is confirmed holding: **zero `transitionend` / `animationend` listeners.**
All five textual matches in the file are inside comments explaining why they are avoided. At 0.01ms
those events can fire before a listener attaches; nothing in the build can hang on one.

---

## Punch list, in priority order

1. **Restore the Estimated pin on the map (V2, D11).** It is the only place the build changes a tier's
   encoding rather than its prominence, the spec forbids it outright, and the correct artwork already
   exists in the file &mdash; `pinSVG('est', 40)` is one call-site change. Clustering already absorbs
   55 of 64 marks at overview, so the density argument that motivated the ring is answered.
2. **Add the unavailable state (V1).** Five states per control is the spec's first table; the build
   has four everywhere. `#E2DAFF` fill and `#17103D` label, from `controls/primary-unavailable.svg`.
   Keep the control pressable so the existing inline explanation still fires.
3. **Make the sheet follow the finger (V3), and veil the map at full (V4).** The sheet is the most
   handled surface in the product and is currently a threshold switch. Add `pointermove` tracking and
   velocity-aware snapping; bind a 7% `#17103D` veil to `[data-pos="full"]` only.
4. **Fix the pin drop's tail (V8).** One sky-blue ripple, not two marigold ones. Two lines.
5. **Give the outgoing screen its 12px exit (V5) and peer navigation its 8px settle (V6).** Both are
   half-implemented; the missing halves are one keyframe each.
6. **Restate the cluster on indigo with composition arcs (V9).** A violet cluster reads as an
   owner-confirmed mark; the tier mix is already computed for the aria-label.
7. **Draw the two missing pin overlays (V17 freshness clock, V18 selected keyline).** Both assets
   ship in `pin-overlays/`.
8. **Put &ldquo;Suggest a correction&rdquo; at the end of the evidence receipt (V10)**, animate the
   receipt expansion over 240ms (V11), and draw the outlined check rather than fading it (V14).
9. **Re-time against the spec's table (D1, D5&ndash;D10, D15, D17).** Adding `--dur-press` 100,
   `--dur-focus` 120, `--dur-screen` 260, `--dur-sheet` 320, `--dur-map` 450 and the two named
   easings (`cubic-bezier(.2,.75,.25,1)`, `cubic-bezier(.22,.9,.28,1.08)`) is mechanical. It costs
   the two-duration consolidation rubric 4.2 scored a 4 for, and that trade should be an explicit
   decision rather than a side effect.
10. **Replace the reduced-motion blanket with declared end states** for anything whose resting state
    is not its underlying style, and drop the global `animation-iteration-count:1`. The processing
    path already shows how; follow it.
11. **Decide the touch-target figure (D18)** &mdash; the build is consistently 44, the spec and token
    say 48. Also fix the two genuine outliers: a 40&times;40 `.sheet-close` and the 52&times;31 toggle.
12. **Record a position on haptics (V12).** Either call `navigator.vibrate` behind a capability check
    or write down why a browser prototype does not, so the omission is a decision rather than a gap.

---

## How far the build is from the spec, plainly

Further than the rubric's section-4 fours suggest, and closer than the violation count suggests.
Both halves of that are true and they are not in tension.

The rubric scored motion against &ldquo;is this a coherent system?&rdquo; and the answer is genuinely
yes: two durations, three easings, one press treatment per shape, directional screen pushes, a
reduced-motion path that survives, and no `transitionend` anywhere. That work is real and this audit
did not find it wanting on its own terms.

This spec asks a different question &mdash; &ldquo;is it *this* system?&rdquo; &mdash; and the answer
is not yet. The build's motion language was designed in-house and then met a specification it was
never measured against, so almost every number is close but nominated by a different authority. That
is what the 19 drift items are, and they are cheap: they are a token file and a search-and-replace.

The 20 violations are not cheap, and they split into two kinds. Ten are **missing behaviour** &mdash;
no unavailable state, no drag tracking, no screen exit, no haptics, no dot fill, no check draw, no
swipe dismissal, no clock rotation, and two absent pin overlays. Each is a discrete addition to a
build that already has the surface to hang it on. The other ten are **decisions that conflict**: the
Estimated tier's re-encoding, the cluster's violet, the 42% scrim, the two marigold ripples, the
indicator above the tab rather than beneath it. Those need someone to choose, because in several
cases the build's version was chosen deliberately and defended in writing.

What is not broken is the part that would have been expensive to fix. No trust pin is recoloured for
any of the four forbidden reasons. There is no red, no grey, and no failure-shaped motion anywhere.
The scan lands inside its time budget with an honest checklist. The reduced-motion path completes
every flow. Those are the load-bearing commitments, and three rounds of work put them there before
this spec arrived to ask for them.

Call it two-thirds of the way. The remaining third is mostly bounded, mechanical work plus about ten
decisions that need an owner rather than an engineer.
