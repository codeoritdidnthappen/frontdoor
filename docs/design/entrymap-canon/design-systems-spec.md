# EntryMap — design systems spec (type · spacing · elevation · motion)

> **Purpose.** Round 0 of `design-rubric.md` found that four systems exist informally and are
> applied inconsistently, holding sections 1–5 at 2s. This document defines those four systems as
> concrete CSS custom properties, states the rule for applying each, and gives a mapping from every
> current usage to its new token. It also covers the two craft items scored at 2: touch feedback on
> rows and chips (5.3) and one icon grid at one stroke width (5.4).
>
> **Precedence.** `product-interaction-design.md` is canon; `ui-reference-spec.md` carries measured
> decisions. This document serves both and overrides neither. Where a system would change something
> either document fixes (pin anatomy, tier wording, sheet positions, processing beats, the honest
> colour rules), the canon wins and the system bends.
>
> **Colour is out of scope and untouched.** Blue = estimated · marigold = scanned · purple = owner ·
> green only for needs-match · amber only for freshness ageing · no red anywhere. Rubric 3.1 and 3.5
> already score 4. Nothing below changes a hue, a wash, or an ink token. Where a shadow or border
> currently carries a colour, the colour is preserved verbatim and only the geometry is unified.
>
> **Two things this round must not regress.**
> 1. **Reduced motion (4.5 / 7.10 = 4).** Every transition and animation added here is a CSS
>    `transition` or `animation`, so both existing kill-switches cover it automatically. §4.7 lists
>    the three places where that is not sufficient and says what to do instead.
> 2. **Accessibility behaviour, owned by another agent this round.** Focus rings, `aria-invalid`
>    borders, live regions, focus order, form-control borders and the `.inline-err` component belong
>    to the a11y round. This spec never reassigns a `:focus-visible` shadow and never replaces a
>    border that carries a control boundary. Those exclusions are named at each point.

**Audit basis.** `design/phone-app-prototype.html`, 4,695 lines, read 2026-09-05 while the a11y
agent was mid-edit (its `.inline-err`, `.needed-badge` and `18.9px` larger-text changes are already
reflected in the counts). CSS block lines 11–1273; markup 1275–2398; script 2399–4695. Counts cover
all three regions. Twenty-six screens, seven sheets.

---

## 0. Where the tokens live

All four systems are declared in the existing `:root` block (line 13) alongside the colour tokens.
Three of the four are **unitless or px** and therefore unaffected by the text-size setting; the type
scale is deliberately **em-based** so that `.phone[data-textsize]` (15px → 16.2px → 18.9px) keeps
working. That behaviour is verified at 7.11 = 4 and must be preserved: **no font-size in this spec is
expressed in px**, with the six documented exceptions in §1.6.

---

# 1. Type scale

## 1.1 Actual inventory

Measured across CSS, inline `style=` attributes and template strings in the script.

**`font-size` — 209 occurrences, 40 distinct values.**

| value | n | value | n | value | n |
|---|---|---|---|---|---|
| `.78em` | 20 | `.85em` | 6 | `1.5em` | 3 |
| `.8em` | 20 | `.74em` | 6 | `1.02em` | 2 |
| `.95em` | 18 | `1.05em` | 6 | `1.25em` | 2 |
| `.72em` | 17 | `.68em` | 5 | `1.15em` | 2 |
| `.86em` | 13 | `20px` | 5 | `1.2em` | 1 |
| `.9em` | 10 | `14px` | 3 | `1.45em` | 1 |
| `.84em` | 10 | `.94em` | 3 | `1.55em` | 1 |
| `.76em` | 10 | `.98em` | 3 | `2.1em` | 1 |
| `.82em` | 9 | `1.3em` | 3 | `2.35em` | 1 |
| `.88em` | 8 | `.75em` | 1 | `.7em` | 1 |
| `.92em` | 8 | `13px` `15px` `16.2px` `18.9px` `10px` `10.5px` `19px` `17px` `11px` | 1 each |

Twenty-nine of the forty are em values inside a 0.68 – 2.35 range: an average gap of 6% between
adjacent values, which is below the threshold at which a size difference reads as intentional. That
is the whole of criterion 1.1.

**`font-weight` — 208 occurrences, 4 distinct values.**

| weight | n | share |
|---|---|---|
| `900` | 94 | 45% |
| `700` | 53 | 25% |
| `800` | 48 | 23% |
| `600` | 5 | 2% |

900 is the single most common weight in the file and is applied to a 0.68em uppercase micro-label
(`.tile .t-label`), a 0.72em chip (`.tierchip`), a 0.95em button (`.btn`), a 1.25em card title
(`.card-name`) and a 2.35em wordmark (`.splash-word`) alike. That is criterion 1.2 exactly: when the
heaviest weight is on everything, it distinguishes nothing.

**`line-height` — 48 occurrences, 11 distinct values.**
`1.45` (19) · `1.4` (11) · `1.2` (3) · `1.5` (3) · `1` (3) · `1.25` (2) · `1.15` · `1.35` · `1.55` ·
`1.22` · `1.3` (1 each). Of the 198 CSS rules that set a `font-size`, only 42 also set a
`line-height`: **156 sized rules inherit `normal`** (≈1.36 for Nunito) regardless of how large or
small their text is.

Display sizes carry body leading: `.scan-h` 1.45em/1.2, `.ob-h` 1.55em/1.2, `.wl-h` 1.5em/1.22,
`.card-name` 1.25em/1.15, `.prof-name` 1.15em/none, `.flowhead h2` 1.15em/none, `.sheet-h`
1.2em/none, `.prof-avatar` 1.3em/none. Criterion 1.4.

**`letter-spacing` — 19 occurrences, 10 distinct values.**
`.06em` (5) · `-.01em` (3) · `.02em` `.05em` `.08em` (2 each) · `.13em` `.14em` `-.005em` `-.025em`
`-.028em` (1 each). Direction is right — negative on display, positive on caps — but five different
caps values do one job.

**`font-variant-numeric` / `font-feature-settings` — 0 occurrences.** No tabular numerals anywhere.
Criterion 1.5 = 1.

**Font resources available.** `Nunito:ital,wght@0,400;0,600;0,700;0,800;0,900;1,600;1,700`
(line 10). 600, 800 and 900 are all really loaded — the three-weight scale below needs no new
webfont request and no synthesised weight.

## 1.2 The scale

Eight size steps, three weights. Every step names size, weight, line-height and letter-spacing, so a
step can be applied as one declaration block and nothing is left to judgement.

```css
:root{
  /* ---- size (em, relative to .phone's 15px root — never px) ---- */
  --fs-display: 2.3em;   /* 34.5px @15 */
  --fs-h1:      1.5em;   /* 22.5px */
  --fs-h2:      1.2em;   /* 18px   */
  --fs-h3:      1.05em;  /* 15.8px */
  --fs-body:    0.95em;  /* 14.3px */
  --fs-sub:     0.86em;  /* 12.9px */
  --fs-meta:    0.78em;  /* 11.7px */
  --fs-micro:   0.7em;   /* 10.5px */

  /* ---- weight (exactly three; 900 is a reserved resource) ---- */
  --fw-body:    600;
  --fw-strong:  800;
  --fw-display: 900;

  /* ---- leading: tightens as size rises ---- */
  --lh-display: 1.0;
  --lh-h1:      1.1;
  --lh-h2:      1.15;
  --lh-h3:      1.22;
  --lh-body:    1.5;
  --lh-sub:     1.45;
  --lh-meta:    1.35;
  --lh-micro:   1.25;
  --lh-row:     1.3;    /* single-line row labels that may wrap to two */

  /* ---- tracking ---- */
  --ls-display: -0.025em;
  --ls-h1:      -0.02em;
  --ls-h2:      -0.015em;
  --ls-h3:      -0.01em;
  --ls-flat:     0;
  --ls-caps:     0.08em;   /* uppercase micro labels */
  --ls-caps-wide:0.14em;   /* two brand/map marks only — see 1.6 */
}
```

Step ratios: 2.3 → 1.5 is 1.53 (a deliberate jump to the brand tier); 1.5 → 1.2 → 1.05 → 0.95 →
0.86 → 0.78 → 0.7 runs at a steady 1.10–1.14. Every adjacent pair is separated by at least 10%,
which is the point at which a size difference reads as a decision rather than an accident.

**Applying a step.** Each step is one block:

```css
.t-h2{ font-size:var(--fs-h2); font-weight:var(--fw-display);
       line-height:var(--lh-h2); letter-spacing:var(--ls-h2); }
```

Author these eight blocks once and have components extend them, or paste the four declarations into
each component rule. Either is acceptable; what is not acceptable is a component setting `font-size`
from the scale and leaving `line-height` and `letter-spacing` unset, because that is how 156 rules
ended up inheriting `normal`.

## 1.3 Weight rules

Three weights, each with a stated job.

**`--fw-display: 900` is reserved.** It may appear only on: a step at `--fs-h3` or larger, the
wordmark, the primary action label on a screen, and a live count that the user is being asked to
read as a headline (`.counter-line`, `.ow-tierline`). That is the whole permitted list. Target: **21
call sites, down from 94.**

**`--fw-strong: 800`** carries every row label, button label (other than the one primary), chip,
tier chip, section label, nav label, meta line, tabular value and link. It replaces 800 where it
already is (48 sites) and takes the ~73 sites demoted from 900.

**`--fw-body: 600`** carries all reading copy: paragraphs, sub-lines under a row label, captions,
notes, quotes, form values. It replaces the 53 sites at 700 and the 5 at 600. **700 disappears from
the file.**

The rule in one line: *900 says "this is the thing"; 800 says "this is a control or a label"; 600
says "this is something to read."*

**Contrast note.** Weight does not enter WCAG contrast maths, so the verified 7.1 = 4 result is
unaffected by the arithmetic. But 700 → 600 does thin the body stroke perceptibly. The body inks
are `--sub` #4A4463 at 8.4:1 and `--ink` #241F3A at 15:1 on white — both well clear of the 7:1
product floor — so the change is safe. Do not extend it to `--faint` #575170 (7.0:1), which is
already at the floor: `.scanscreen.reduced .checkitem` is the only user of `--faint` and stays at
`--fw-strong`.

## 1.4 Size mapping — every current value to its step

Grouped by current value. Applying this table is a mechanical find-and-replace per selector list.

### → `--fs-display` (2.3em / 900 / 1.0 / -0.025em) — 2 sites
| now | selectors |
|---|---|
| `2.35em` | `.splash-word` |
| `2.1em` | `.wl-word` |

The two brand lockups differ by 12% today for no reason; one value.

### → `--fs-h1` (1.5em / 900 / 1.1 / -0.02em) — 6 sites
| now | selectors |
|---|---|
| `1.55em` | `.ob-h` |
| `1.5em` | `.ob-word`, `.wl-h`, `.ob-mark .ob-word` |
| `1.45em` | `.scan-h` |
| `1.3em` | `.prof-avatar` (initials in a 56px circle — display, not copy) |

Leading tightens from 1.2/1.22 to 1.1. `.ob-h` shrinks 3%, `.scan-h` grows 3%; neither reflows.

### → `--fs-h2` (1.2em / 900 / 1.15 / -0.015em) — 4 sites
| now | selectors |
|---|---|
| `1.25em` | `.card-name` |
| `1.2em` | `.sheet-h` |
| `1.15em` | `.prof-name`, `.flowhead h2` |

`.card-name` keeps its 1.15 leading almost exactly (→1.15). `.sheet-h`, `.prof-name` and
`.flowhead h2` gain a leading value for the first time.

### → `--fs-h3` (1.05em / 900 / 1.22 / -0.01em) — 10 sites
| now | selectors |
|---|---|
| `1.05em` | `.list-view h2`, `.map-empty .me-h`, `.empty-box .e-h`, `.preview .pv-name`, `.state-card .sc-h` |
| `1.02em` | `.wordmark`, `.rung .r-name` |
| `.98em` | `.persona .p-name`, `.lrow .l-name`, `.ow-tierline` |

`.lrow .l-name` grows 7%. That is intended: the list view is the non-map equivalent for
screen-reader and map-averse users (canon, "Finding a business"), and its row title should sit at
the same step as the section head above it.

### → `--fs-body` (0.95em / weight per role / 1.5 or `--lh-row` / 0) — 38 sites
| now | selectors |
|---|---|
| `.95em` | `.fab-needs`, `.fab-filters`, `.tile .t-value`, `.btn`, `.checkitem`, `.counter-line`, `.prof-row .rowlabel`, `.cluster`, `.srow .s-name`, `.sgroup .sg-head`, `.nudge .n-h`, `.searchfield input`, `.cr-name`, `.tl-name`, `.ow-scanline .rowlabel`, `.ow-editrow label`, `.ow-review .rv-h` |
| `.94em` | `.softlist`, `.ob-p`, `.wl-p` |
| `.92em` | `.btn-textlink`, `.field select`, `.field textarea`, `.field input[type=email\|tel\|text]`, `.scan-p`, `.verify-opt .vo-name`, `.ow-feat`, `.ow-sel select`, `.ow-diffrow .d-name` |
| `.9em` | `.locpill`, `.correct-btn`, `.rcpt-row`, `.dist-label`, `.privacy-line`, `.lib-link`, `.ow-locked .lk-main`, `.ow-photo .ph-btn`, `.ow-stackrow .st-main`, `.ow-taxlink` |

Use `--lh-body` (1.5) for the paragraphs (`.ob-p`, `.wl-p`, `.scan-p`, `.softlist`) and `--lh-row`
(1.3) for the single-line labels and controls. Body copy at 14.3px/1.5 inside a 358px content column
gives 52–68 characters, inside the 45–75 band that keeps 1.3 at 3.

### → `--fs-sub` (0.86em / `--fw-body` / 1.45 / 0) — 51 sites
| now | selectors |
|---|---|
| `.88em` | `.prov-row .pr-main`*, `.nophoto`, `.rcpt-back`*, `.filt-reset`*, `.scan-target`, `.authz`, `.photo-add`*, `.ow-review .rv-row` |
| `.86em` | `.prov-row .pr-sub`, `.sheet-p`, `.inline-err`, `.preview .pv-body`, `.notif-intro`, `.policy-line`, `.next-list li`, `.state-card .sc-p`, `.ow-review .rv-row .rv-sub`, `.ow-nochange`, `.ow-saving .sv-label` |
| `.85em` | `.locpill .chevd`, `.unknown-row`, `.rung .r-body`, `.map-empty .me-p`, `.toast`, `.empty-box .e-p` |
| `.84em` | `.receipt-note`, `.filtchip`*, `.seg button`*, `.recent-chip`*, `.intro-tips span`, `.ow-diffrow .d-change`, `.ow-diffrow .d-note` |
| `.82em` | `.nb-name`, `.fchip`*, `.evidence`, `.rcpt-row .rc-sub`, `.quarantine-note`, `.nudge .n-p`, `.tax-box`, `.prof-row .rowvalue`, `.ow-photo .ph-name` |
| `.8em` | `.card-sub`, `.need-breakdown`, `.rcpt-foot`, `.prof-sub`, `.needchip`, `.list-view .l-cap`, `.lrow .l-sub`, `.a11y-note`, `.preview .pv-sub`, `.ow-notseen`, `.ow-stackrow .st-sub` |

`*` = interactive; takes `--fw-strong`, not `--fw-body`.

`.inline-err` is a11y-owned — take the size step, leave its colour, icon and `.on` behaviour alone.

Five `.8em` selectors are **not** in this list and go down to `--fs-meta` instead, because they are
numerals in a dense meta row, not copy: `.srow .s-dist`, `.lrow .l-dist`, `.cr-dist`,
`.checkitem .ci-dot`, `.under8`. Two more `.8em` selectors go to `--fs-micro`: `.ob-kicker` and
`.wl-tag`, which are uppercase kickers. See below.

### → `--fs-meta` (0.78em / `--fw-strong` / 1.35 / 0) — 43 sites
| now | selectors |
|---|---|
| `.8em` | `.srow .s-dist`, `.lrow .l-dist`, `.cr-dist`, `.checkitem .ci-dot`, `.under8` |
| `.78em` | `.fab-filters .fcount`, `.persona .p-sub`, `.filt-caption`, `.privacy-sub`, `.coach`, `.vc-notseen`, `.ob-foot`, `.srow .s-sub`, `.lrow .l-feats`, `.nudge .n-age`, `.cr-sub`, `.verify-opt .vo-sub`, `.guardrail`, `.tl-sub`, `.tabfoot`, `.state-card .sc-note`, `.ow-feat .fseen`, `.ow-locked .lk-sub`, `.ow-locked .lk-lock`, `.ow-flagnote` |
| `.76em` | `.done-legend .lg`, `.prof-row .rowsub`, `.achip`, `.srow .s-feats`, `.lrow .l-meta`, `.rowmeta`, `.preview .fresh`, `.ow-attest`, `.ow-scanline .rowsub`, `.ow-stackrow .st-tail` |
| `.75em` | `.field label` (uppercase — takes `--ls-caps`) |
| `.74em` | `.match-legend`, `.nb-match`, `.upload-note`, `.pos-hint`, `.sgroup .sg-count`, `.priv-line` |
| `.72em` | `.legend .lg`, `.nb-dist`, `.navbtn`, `.nav-scan` |

Sub-lines that are prose rather than meta (`.persona .p-sub`, `.cr-sub`, `.tl-sub`,
`.verify-opt .vo-sub`, `.ow-locked .lk-sub`, `.ow-scanline .rowsub`, `.prof-row .rowsub`,
`.srow .s-sub`, `.guardrail`, `.tabfoot`, `.filt-caption`, `.ob-foot`, `.privacy-sub`,
`.upload-note`, `.vc-notseen`) take `--fw-body`, not `--fw-strong`.

### → `--fs-micro` (0.7em / `--fw-strong` / 1.25) — 23 sites
Uppercase members take `--ls-caps` (0.08em); the rest take `--ls-flat`.

| now | selectors |
|---|---|
| `.8em` | `.ob-kicker` (caps), `.wl-tag` (caps — but see 1.6) |
| `.72em` | `.tierchip`, `.matchchip`, `.chips-title` (caps), `.needed-badge`, `.photostrip .ps-tag`, `.charcount`, `.blur-tag`, `.sectionlabel` (caps), `.mstat`, `.legend-cta`, `.nearby-title` (caps), `.status-chip`, `.wn-h` (caps) |
| `.7em` | `.upd-badge` |
| `.68em` | `.tile .t-label` (caps), `.live-chip` (caps), `.wl-tier b`, `.preview .pv-label` (caps), `.ow-photo .ph-tag` |

Micro is the floor. Nothing in the product goes below 0.7em (10.5px at the default text size,
12.7px at "larger"). Anything currently smaller grows into it.

### Letter-spacing consolidation
- Every uppercase micro label → `--ls-caps` (0.08em). Replaces `.05em`, `.06em` (5 sites) and
  `.08em`: 9 sites, one value.
- `.02em` on `.ow-photo .ph-tag` → `--ls-caps` as well (it is an uppercase tag).
- `-.005em` on `.wl-tier b` → `--ls-flat` (0). At 0.7em, negative tracking is invisible and harmful.
- `.13em` on `.wl-tag` and `.14em` on `.street-label` → `--ls-caps-wide`. These are the two
  deliberately wide-tracked marks (the welcome tagline and the map street labels); one shared value.
- `.02em` on `.stage-caption` → 0. It is desktop stage chrome, outside the phone.

## 1.5 Tabular numerals — criterion 1.5, currently 1

```css
.tnum{ font-variant-numeric: tabular-nums lining-nums;
       font-feature-settings: "tnum" 1, "lnum" 1; }
```

Apply as an added class on the elements below, not globally: tabular figures are wider and worse for
running prose, so this is a per-component decision.

**Distances (5).** `.nb-dist`, `.srow .s-dist`, `.lrow .l-dist`, `.cr-dist`, `.dist-label` — all
render `distLabel(p)` output ("0.3 mi", "450 ft") and stack vertically in scannable columns.

**Counts (7).** `.fab-filters .fcount`, `.sgroup .sg-count`, `.cluster` (place count on a pin),
`.counter-line`, `.charcount`, `.ow-stackrow .st-tail`, `.wl-tier b` is not a count — excluded.
Also the "N of M needs" arithmetic, which the canon requires be readable as arithmetic:
`.nb-match`, `.mstat`, `.matchchip`, `.need-breakdown`.

**Freshness (11).** `.tile .t-value`, `.rowmeta .fresh`, `.preview .fresh`, `.nudge .n-age`,
`.ow-feat .fseen`, `.prov-row .pr-sub`, `.lrow .l-meta`, `.ow-attest`, `.rcpt-row .rc-sub`,
`.under8`, `.statusbar`.

**Total: 27 elements** (31 selectors counting the four match-arithmetic ones).

The freshness set is the important one. The canon's freshness vocabulary is entirely numeric —
"Scanned 8 months ago", "Last checked 11 months ago", "2 days ago" — and these strings sit in stacked
rows in the list view, the saved list and the card tiles. Proportional figures make an 8 and a 1 sit
at different widths, so the same phrase does not align down a column. That is what criterion 1.5 is
about.

> **QUESTION.** Google-served Nunito's `tnum` coverage is not verified. If `tnum` is absent the
> declaration is inert and no harm is done, but the alignment goal is not met. Verify with
> `document.fonts` / a rendered-width test on a `0`–`9` string. If unsupported, the fallback is
> **not** a font swap: give the five distance selectors and the freshness column
> `min-width` + `text-align:right` and accept that inline freshness phrases stay proportional.
> This choice belongs to whoever implements, and needs one measurement, not a design decision.

## 1.6 Px sizes — the six that stay, and why

Every other size in the file is em-based off `.phone`'s 15px root so the text-size preference scales
it. Nine px sizes exist. Six are legitimate; three are defects.

**Legitimate — keep as px:**
- `.phone{font-size:15px}` and its two `[data-textsize]` overrides (16.2px, 18.9px) — this *is* the
  root the scale hangs from.
- `.tsize-btn:nth-child(1..3)` at 14/17/20px — the text-size picker's own preview. It must not scale
  with the setting it controls.
- `.stage-caption{13px}` — desktop stage chrome outside the phone.

**Defects — convert to the scale:**
- `.pin-label{10px}` → `--fs-micro`. This is the "Good match" chip on the selected pin: product
  content, and today it does not grow when a user raises text size.
- `.street-label{10.5px}` → keep px. **Exception:** it is an SVG `fill`-styled label inside a
  drawn map whose geometry is computed in px; scaling it would break the map layout. Keep 10.5px
  and note it as the one intentional non-scaling piece of content type.
- `.sheet-close`, `.ob-back`, `.flowhead .backbtn`, `.ow-banner .backbtn` at 20px and `.cancel-x` at
  19px → these are the `✕` and `‹` glyphs, sized to fill a 44px button. Replace with a single
  `--icon-glyph: 20px` constant (5 sites, one value) and treat as iconography, not type. See §6 on
  the raw-glyph question, which is criterion 5.6 and not this spec's to solve.
- `.tl-dot{14px}` and `.achip .x{11px}` → glyph sizes inside fixed-size circles; same treatment,
  `--icon-glyph-sm: 12px`.

## 1.7 Type — expected result

| criterion | now | after | why |
|---|---|---|---|
| 1.1 real scale | 2 | 4 | 40 values → 8 steps; every on-screen size traces to a step |
| 1.2 weight carries hierarchy | 2 | 4 | 4 weights → 3; 900 from 94 sites to 21, reserved by rule |
| 1.3 line length | 3 | 3 | unchanged; body at 14.3px/1.5 stays in the 52–68 char band |
| 1.4 leading | 2 | 4 | leading defined at every step; display drops to 1.0–1.15, body rises to 1.5 |
| 1.5 tabular numerals | 1 | 4 | 27 numeral-bearing elements get `.tnum` (subject to the §1.5 question) |
| 1.6 tracking | 3 | 4 | 10 values → 5 tokens; one caps value, one wide-caps value, four display values |

---

# 2. Spacing scale

## 2.1 Actual inventory

525 spacing declarations containing **714 numeric tokens** across `padding` (126), `padding-top`
(13), `padding-bottom` (2), `padding-left` (1), `padding-right` (4), `margin` (33), `margin-top`
(198), `margin-bottom` (8), `margin-left` (10), `margin-right` (2) and `gap` (128).

**Forty distinct numeric values.**

| px | n | px | n | px | n | px | n |
|---|---|---|---|---|---|---|---|
| 0 | 91 | 8 | 61 | 18 | 15 | 40 | 1 |
| 1 | 24 | 9 | 22 | 20 | 8 | 44 | 1 |
| 2 | 44 | 10 | 72 | 22 | 12 | 48 | 1 |
| 3 | 18 | 11 | 13 | 24 | 1 | 52 | 1 |
| 4 | 42 | 12 | 87 | 26 | 8 | 54 | 1 |
| 5 | 21 | 13 | 7 | 28 | 1 | 56 | 1 |
| 6 | 56 | 14 | 52 | 30 | 3 | 58 | 1 |
| 7 | 8 | 16 | 21 | 34 | 2 | 60 | 3 |
| | | 17 | 4 | 36 | 2 | 64 · 70 · 96 · 100 · 104 · 110 | 10 |

`padding` alone has **74 distinct shorthand combinations** in 126 declarations — nearly one unique
value per use. The rubric's "mostly a 4px grid but with strays" is generous: 5, 7, 9, 10, 11, 13, 14,
17, 18, 22, 26, 30, 34 account for 261 of the 714 tokens, 37% off-grid.

## 2.2 The scale

```css
:root{
  --sp-0: 0;
  --sp-1: 2px;    /* hairline nudge: a sub-line under its label, a badge inset */
  --sp-2: 4px;    /* glyph to text inside a chip or badge */
  --sp-3: 6px;    /* tight inline: chip to chip, dot to dot */
  --sp-4: 8px;    /* standard inline: icon to text, control to control */
  --sp-5: 12px;   /* row rhythm: between rows, card internal padding */
  --sp-6: 16px;   /* block: between two related groups */
  --sp-7: 24px;   /* section: between two unrelated groups */
  --sp-8: 32px;   /* screen rhythm: hero to content */
  --sp-9: 48px;   /* rare: the scan hero's breathing room */
}
```

Ten steps: 2·4·6·8 at the bottom where a 2px difference is visible, then a 4pt grid (12·16·24·32·48)
above it. Every adjacent pair differs by at least 2px and at most 16px.

**The mapping rule, stated once: round to the nearest step; on an exact tie, round up.** Rounding up
on ties is deliberate — the reference calls for "airy spacing," and every tie in this file (3, 5, 7,
10, 14, 20, 28, 40) resolves upward, so the rule is uniform and needs no per-case judgement.

## 2.3 Value mapping — every stray to its step

| now | → | token | sites | now | → | token | sites |
|---|---|---|---|---|---|---|---|
| 0 | 0 | `--sp-0` | 91 | 12 | 12 | `--sp-5` | 87 |
| 1 | 2 | `--sp-1` | 24 | 13 | 12 | `--sp-5` | 7 |
| 2 | 2 | `--sp-1` | 44 | 14 | 16 | `--sp-6` | 52 |
| 3 | 4 | `--sp-2` | 18 | 16 | 16 | `--sp-6` | 21 |
| 4 | 4 | `--sp-2` | 42 | 18 | 16 | `--sp-6` | 15 |
| 5 | 6 | `--sp-3` | 21 | 20 | 24 | `--sp-7` | 8 |
| 6 | 6 | `--sp-3` | 56 | 22 | 24 | `--sp-7` | 12 |
| 7 | 8 | `--sp-4` | 8 | 24 | 24 | `--sp-7` | 1 |
| 8 | 8 | `--sp-4` | 61 | 26 | 24 | `--sp-7` | 8 |
| 9 | 8 | `--sp-4` | 22 | 28 | 32 | `--sp-8` | 1 |
| 10 | 12 | `--sp-5` | 72 | 30 | 32 | `--sp-8` | 3 |
| 11 | 12 | `--sp-5` | 13 | 34 | 32 | `--sp-8` | 2 |
| | | | | 36 | 32 | `--sp-8` | 2 |
| | | | | 40 | 48 | `--sp-9` | 1 |

**The two changes that will be visible.** `10 → 12` (72 sites) and `14 → 16` (52 sites) together
account for 124 of the 714 tokens and will make the interface slightly roomier. That is the intended
direction and matches the reference's "airy spacing." Nothing in the file relies on 10 or 14 for
geometric fit — the fit-critical values are in the exclusion list below.

## 2.4 Layout constants — not part of the rhythm scale

Values ≥ 44px are anchored to fixed chrome (status bar, app head, bottom nav) rather than to
rhythm, and belong in their own family. Today there are 17 such tokens at 12 distinct values, which
is why four screen types have four different bottom paddings that all mean "clear the nav bar."

```css
:root{
  --chrome-status: 46px;   /* .statusbar height — existing */
  --chrome-nav:    86px;   /* .navbar height — existing */
  --inset-x:       16px;   /* screen side padding */
  --inset-sheet:   18px;   /* sheet side padding */
  --pad-top:       58px;   /* content screens: clears status bar */
  --pad-top-hero:  70px;   /* scan + onboarding screens */
  --pad-top-map:  104px;   /* below the app head — .map-top, .map-ctls, .list-view */
  --pad-bottom:   104px;   /* clears the 86px nav with --sp-6 to spare */
}
```

Collapses:
- top paddings `54 / 58 / 60 / 64 / 70` → `--pad-top` (58) for `.screen-body`, `.search-ov`,
  `#scan-capture .scan-body`; `--pad-top-hero` (70) for `.scan-body` and `.ob-body`.
- bottom paddings `96 / 100 / 104 / 110` → `--pad-bottom` (104), four values to one. This also fixes
  a real defect: `.screen-body` pads 96px against an 86px nav, leaving only 10px of clearance, while
  `.ow-sheet .sheet-scroll` pads 110px. Both become 104.
- side paddings `12 / 14 / 16 / 20 / 22 / 26` → `--inset-x` (16) on screen bodies and
  `--inset-sheet` (18) on sheet scrolls. `.ob-body`'s 26px and `.wl-card`'s 26px stay as
  `--inset-onboard: 26px` — the onboarding screens are single-column narrative and are meant to be
  narrower. One extra constant, stated rather than scattered.

## 2.5 Geometry, excluded from both families

These are not spacing. They are optical centring and hit-area expansion, and must not be rounded.

| site | value | what it is |
|---|---|---|
| `.pinbtn` | `margin:-22px 0 0 -22px` | centring a 44px button on a coordinate |
| `.rippler` | `margin:-17px 0 0 -17px` | centring a 34px ripple |
| `.cluster` | `margin:-22px 0 0 -22px` | centring a 44px cluster |
| `.toggle::before` | `inset:-8px` | expanding a 52×31 track to a 47px hit area |
| `.achip::before` | `inset:-6px` | expanding a 32px chip to a 44px hit area |
| `.sheet-grip` | `margin:10px auto 2px` | the `auto` is centring; the 10/2 map normally |
| `.ow-stackrow.new` | `margin:6px -14px; padding:8px 14px` | negative bleed to full card width |
| `.nav-scan` | `margin-top:-26px` | the scan button's deliberate rise above the bar |
| `.list-view h2` / `.l-cap` | `margin:0 60px …` | clearing the map-controls stack |
| `.flowhead h2` | `margin-right:44px` | balancing a 44px back button |
| `.card-head` | `padding-right:40px` | clearing the 44px close button |
| `.chiprow` | `padding-right:52px` | clearing the map-controls stack |

Thirteen sites, 17 tokens. Leave them, and add a one-line comment at each saying what it is anchored
to, so a later pass does not "fix" them.

## 2.6 Proximity before boxes — criterion 2.3

The rubric flags "several boxes do work proximity could do." The concrete list, with what it looks
like now and what it becomes. The rule behind all of them: **a box earns its keep only when it
changes surface (content leaving the lavender ground for a white card), carries a state (the amber
freshness tile), or holds a scroll boundary. Grouping alone is proximity's job.**

| component | now | becomes |
|---|---|---|
| `.rung` ×3 ("How trust grows") | each rung is a `#F8F7FD` box, radius 14, padding 12 | three rows on the sheet's own white, separated by `--sp-7`, pin glyph as the leading column. Three boxes inside one white sheet is a box inside a box; the vertical rhythm already groups them. |
| `.need-breakdown` | `#F8F7FD` box, radius 12, padding 9/12 | text block indented to the chip column, `margin-top:var(--sp-5)`, no fill. It is a per-need breakdown of the chip directly above it — adjacency already says so. |
| `.receipt-note` | `#F8F7FD` box, radius 12, margin 8/0 | inline sub-line inside the `.prov-row` it belongs to, `margin-top:var(--sp-1)`, `--fs-meta`. It currently detaches from its row. |
| `.whatsnext` | `2px solid #E6E2F4` box, radius 16, padding 14 | heading at `--fs-h3` + `.next-list`, separated by `--sp-7` from what precedes. A border that duplicates a heading. |
| `.policy-line` | white box + `0 2px 10px` shadow, radius 14 | a row: icon + text, `min-height:48px`, `--sp-4` gap, hairline above. A single line of copy in a shadowed card claims a surface change that has not happened. |
| `.tax-box` · `.state-card .sc-note` · `.ow-flagnote` · `.priv-line` · `.guardrail` · `.a11y-note` | six different treatments of "a quiet supporting note": three filled + rounded (10/12px radius, three paddings), three borderless | one `.note` component: `display:flex; gap:var(--sp-4); font:--fs-meta/--fw-body; color:var(--sub); line-height:var(--lh-sub)`, no fill, no border, `margin-top:var(--sp-5)`. The `.tax-box` and `.priv-line` purple-wash variants keep their purple ink (colour rule) but lose the fill. Six treatments → one. |
| `.ow-editlist` · `.ow-diff` · `.ow-stack` · `.ow-review` | white card + shadow, and *also* `border-bottom:1px solid #F2F0FA` on every inner row | keep the card (it is a real surface change from the lavender ground) and **drop the inner row hairlines** where rows are already separated by `--sp-5`. Card + divider + gap is three redundant grouping signals. |
| `.tile` ×2 | `#F8F7FD` box, radius 14 | **keep.** `.tile.aged` swaps the fill to `--amber-wash` to carry freshness ageing — the box is the state carrier, which is exactly when a box is earned. |
| `.preview` | `#F8F7FD` box in accessibility settings | **keep.** It is a preview *of a card*, so the box is the subject. |
| `.evidence` · `.ow-note-card` | `#F8F7FD` fill + 3px left border | keep the 3px left border (it reads as "quoted evidence"), drop the fill. The border alone carries it. |

Net: **nine boxes removed or merged, four kept with a stated reason.**

## 2.7 Optical alignment — criterion 2.6, currently 2

Not deliberately handled today. Three rules, mechanical:

1. **Icon columns in rows.** `.prof-row .rowicon`, `.rcpt-row .rc-icon`, `.ow-stackrow .st-icon`,
   `.cr-icon`, `.persona .p-icon` are fixed-width flex columns (34/30/32/38px) followed by text.
   Set `justify-content:center` on all of them (three of the five already have it) so the glyph
   centres in its column rather than sitting flush-left inside it.
2. **Circular glyph containers.** `.tl-dot`, `.ow-tick`, `.checkitem .ci-dot`, `.next-list .nl-dot`,
   `.persona .p-ring` hold a `✓` or a numeral inside a circle. A checkmark is optically low; add
   `padding-bottom:1px` to the flex centring so it sits on the circle's optical centre.
3. **Pin tips.** `.pinbtn` centres a 44px button on the coordinate, but a map pin's meaning is its
   *tip*, not its centre. The pin SVG is 36×44 with the tip at the bottom edge, so the button should
   be offset `margin:-38px 0 0 -22px` (tip on the coordinate) rather than `-22px`. **This changes
   where every pin sits by 16px** and must be checked against `revealSelected()`'s `limit`
   calculation, which reads `b.style.top`.
   > **QUESTION.** Is the current 6px visual offset intentional (pins reading as "hovering over" the
   > point) or an accident? The canon says selected pins rise 4–6px, which suggests the resting
   > state should be tip-on-point. I have not changed it; flagging for a decision.

---

# 3. Elevation scale

## 3.1 Actual inventory

**59 `box-shadow` declarations, 24 distinct values.**

| value | n | used by |
|---|---|---|
| `var(--shadow)` = `0 10px 30px rgba(36,31,58,.16)` | 18 | `.wordmark` `.locpill` `.hamb` `.legend` `.match-legend` `.fab-needs` `.fab-filters` `.nb-card` `.big-icon` `.scanscreen.light .cancel-x` `.mini-map` `.ob-back` `.achip` `.ctl-btn` `.search-bar .searchfield` `.nearby-title` `.map-empty` `.ow-banner` |
| `0 2px 10px rgba(36,31,58,.07)` | 14 | `.prof-card` `.srow` `.sgroup` `.recent-chip` `.lrow` `.flowhead .backbtn` `.bizhead` `.empty-box` `.policy-line` `.ow-editlist` `.ow-photo` `.ow-review` `.ow-diff` `.ow-stack` |
| `inset 0 0 0 2px var(--purple)` | 3 | `.btn.saved` `.state-card .btn.ghost` `.btn.outline` |
| `0 -12px 40px rgba(36,31,58,.25)` | 2 | `.sheet` `.ow-sheet` |
| `0 -10px 34px rgba(36,31,58,.22)` | 1 | `#sheet-card` |
| `0 -14px 34px rgba(15,8,45,.34)` | 1 | `.wl-card` |
| `0 6px 18px rgba(240,163,47,.45)` | 1 | `.nav-scan .ring` |
| `0 6px 24px rgba(240,163,47,.5)` | 1 | `.shutter` |
| `0 1px 5px rgba(36,31,58,.14)` | 1 | `.seg button.sel` |
| `0 1px 4px rgba(0,0,0,.25)` | 1 | `.toggle::after` |
| `0 0 0 4px rgba(112,83,197,.22), var(--shadow)` | 1 | `.cluster` |
| `inset 0 0 0 2px #E3DEF5` | 1 | `.wl-actions .btn.ghost` |
| `inset 0 0 0 2px var(--purple), 0 2px 10px …` | 1 | `.ow-photo.flag` |
| `0 0 0 2px var(--match-green)` | 1 | `.fchip.needed` |
| `inset 0 0 0 1.5px var(--marigold-edge)` | 1 | `.procbar-fill` |
| `0 0 0 3px var(--purple-wash)` | 1 | `.sheet-grip-btn:focus-visible .sheet-grip` |
| `0 0 0 2px var(--purple)` | 1 | `[aria-invalid="true"]` |
| `0 0 0 6px rgba(255,255,255,.92)` / `rgba(20,14,44,.9)` / `#0E0B1C` | 3 | `:focus-visible` variants |
| `0 0 0 1.5px #2E2947, …` | 2 | the two high-contrast patches |
| `0 24px 70px …, 0 3px 10px …` | 1 | `.phone` (desktop stage chrome) |
| `none` | 2 | `.sgroup .srow` `.phone` (mobile) |

**The defect the rubric names.** Three different shadows describe the same surface level. `.sheet`,
`#sheet-card` and `.ow-sheet` are all "a sheet docked at the bottom" and cast `-12px/40px/.25`,
`-10px/34px/.22` and `-12px/40px/.25` respectively. Two different marigold glows describe the same
action ring (`.nav-scan .ring` and `.shutter`). Two different knob shadows describe the same knob
(`.toggle::after` and `.seg button.sel`). Meanwhile `.nb-card` (a card floating over the map) and
`.lrow` (a card resting on the ground) — genuinely different levels — differ only by opacity.

**Nine hairline borders** also carry surface separation at three colours: `#F2F0FA` (7 sites:
`.prov-row`, `.rcpt-row`, `.prof-row`, `.ow-feat`, `.ow-editrow`, `.ow-diffrow`, `.ow-stackrow`),
`#EEEBF7` (`.prov`), `#E3E0F0` (`.navbar`).

## 3.2 The scale

Four levels. **Elevation is a claim about how far a surface sits from the map plane. It is never
used for emphasis.** That is the rule; everything else follows from it.

```css
:root{
  /* level 0 — resting: on the surface it belongs to. no shadow. */
  --hairline: #EDEAF7;

  /* level 1 — raised: content sitting ON the lavender ground */
  --elev-1: 0 1px 2px rgba(36,31,58,.05), 0 2px 8px rgba(36,31,58,.07);

  /* level 2 — floating: controls that stay legible while the map moves beneath them */
  --elev-2: 0 2px 6px rgba(36,31,58,.10), 0 10px 24px rgba(36,31,58,.14);

  /* level 3 — overlay: surfaces that take over interaction */
  --elev-3-dock: 0 -1px 0 rgba(36,31,58,.06), 0 -8px 28px rgba(36,31,58,.20);
  --elev-3-dark: 0 -1px 0 rgba(15,8,45,.10), 0 -8px 28px rgba(15,8,45,.34);
  --elev-3-free: 0 2px 8px rgba(36,31,58,.12), 0 16px 40px rgba(36,31,58,.24);
}
.phone.hc{
  --hairline: #C9C4DC;
  --elev-1: 0 0 0 1.5px #2E2947, 0 1px 2px rgba(36,31,58,.05), 0 2px 8px rgba(36,31,58,.07);
  --elev-2: 0 0 0 1.5px #2E2947, 0 2px 6px rgba(36,31,58,.10), 0 10px 24px rgba(36,31,58,.14);
  --elev-3-dock: 0 0 0 1.5px #2E2947, 0 -1px 0 rgba(36,31,58,.06), 0 -8px 28px rgba(36,31,58,.20);
  --elev-3-dark: 0 0 0 1.5px #2E2947, 0 -1px 0 rgba(15,8,45,.10), 0 -8px 28px rgba(15,8,45,.34);
  --elev-3-free: 0 0 0 1.5px #2E2947, 0 2px 8px rgba(36,31,58,.12), 0 16px 40px rgba(36,31,58,.24);
}
```

Each level is two shadows: a tight contact shadow that anchors the object, and a wide ambient one
that gives it distance. That two-part construction is what makes the same level read the same on a
white sheet and on the lavender map, which is the failure criterion 3.3 is measuring.

Every level rises in both blur and opacity, so the ordering is legible: .07 → .14 → .20/.24.

## 3.3 Level assignment — which component, and why

### Level 0 — resting (no shadow; `--hairline` where a boundary is needed)
Anything already on the surface it belongs to.

`.tile` · `.rung` · `.evidence` · `.note` (the merged §2.6 component) · `.ow-note-card` ·
`.persona` · `.filtchip` · `.fchip` · `.seg` · `.field select|textarea|input` · `.verify-opt` ·
`.claim-result` · `.state-card` · `.needchip` · `.tierchip` · `.matchchip` · `.mstat` ·
`.status-chip` · `.upd-badge` · every row separated by a hairline.

*Why:* these sit inside a sheet or a card that has already made the surface change. A chip on a
white sheet is not above the sheet; it is part of it.

**Hairline consolidation:** the nine borders at `#F2F0FA` / `#EEEBF7` / `#E3E0F0` all become
`1px solid var(--hairline)`. Nine sites, one value, and the high-contrast override becomes one token
redefinition instead of the current single `.phone.hc .prof-row` patch that leaves six other row
types un-darkened in high contrast.

### Level 1 — raised (`--elev-1`)
Content cards resting on the lavender `--ground`, and nothing else.

`.prof-card` · `.srow` · `.lrow` · `.sgroup` · `.recent-chip` · `.bizhead` · `.empty-box` ·
`.ow-editlist` · `.ow-photo` · `.ow-review` · `.ow-diff` · `.ow-stack` · `.flowhead .backbtn` ·
`.ow-mapground` cards.

*Why:* the lavender ground is the app's floor. A card on it is one step up — enough to read as a
distinct object, not enough to look like it is floating.

Replaces `0 2px 10px rgba(36,31,58,.07)` at all 14 sites. `.policy-line` leaves this list and drops
to level 0 per §2.6.

> **Not applied to:** `.state-card`, `.whatsnext`, `.claim-result`, `.verify-opt`. These currently
> use a `2px solid #E6E2F4` border, which the a11y audit measures at 1.27:1 and which the a11y agent
> is fixing at criterion 7.2. **Elevation must not replace a border that is being repaired as a
> non-text contrast indicator.** Leave their borders alone; they sit at level 0 with whatever border
> the a11y round gives them.

### Level 2 — floating (`--elev-2`)
Controls and cards that sit above the map and stay legible while the map moves beneath them.

`.wordmark` · `.locpill` · `.hamb` · `.legend` · `.match-legend` · `.ctl-btn` · `.fab-needs` ·
`.fab-filters` · `.nb-card` · `.achip` · `.cluster` · `.nearby-title` · `.map-empty` · `.ow-banner` ·
`.mini-map` · `.big-icon` · `.ob-back` · `.scanscreen.light .cancel-x`.

*Why:* these are the only things in the product whose background is not under their control. The map
is drawn beneath them in white streets, pale buildings and aubergine labels, so they need a shadow
strong enough to separate from any of it. Everything at this level shares one property: it overlays
`#map`.

Replaces `var(--shadow)` at 17 of its 18 sites. `.cluster` keeps its purple selection ring composed
in front: `box-shadow: 0 0 0 4px rgba(112,83,197,.22), var(--elev-2)`.

> **`.search-bar .searchfield` leaves this level.** It is a form control, not a floating object. It
> should sit at level 1 with the border treatment the a11y round gives every other form control.
> Flagging rather than prescribing, since form-control borders are a11y-owned this round.

### Level 3 — overlay (`--elev-3-*`)
Surfaces that take over interaction: they either raise a scrim or dock over the whole screen.

| component | token | why |
|---|---|---|
| `.sheet` (needs, filters, receipt, correct, privacy) | `--elev-3-dock` | scrimmed; owns interaction |
| `#sheet-card` | `--elev-3-dock` | docks over the map at all three positions. It raises no scrim by design (the canon requires the selected pin stay visible), but it owns the interaction, so it belongs at the same level. Today it is 12% lighter than `.sheet` for no stated reason. |
| `.ow-sheet` | `--elev-3-dock` | the public-listing preview: the same card, docked |
| `.wl-card` | `--elev-3-dark` | same geometry, deeper cast because it sits on the `#1E1543` aubergine hero |
| `.sheet.popup` ("How trust grows") | `--elev-3-free` | free-floating, scrimmed, not edge-docked |
| `.toast` | `--elev-3-free` | z-index 70, above everything, currently has **no** shadow at all |
| `.navbar` | none + `border-top:1px solid var(--hairline)` | permanently docked chrome, not a temporary overlay. A shadow would imply it can leave. |

Four sheet shadows become two tokens with one geometry.

## 3.4 Two families that are not elevation

Collapsing these stops them competing with the elevation ladder.

```css
:root{
  --ring-action: 0 4px 14px rgba(240,163,47,.42); /* the marigold action glow */
  --ring-select: inset 0 0 0 2px var(--purple);   /* selected / saved state */
  --ring-quiet:  inset 0 0 0 2px #E3DEF5;         /* ghost button on white */
  --ring-needed: 0 0 0 2px var(--match-green);    /* needs-match only — colour rule */
  --knob:        0 1px 3px rgba(36,31,58,.26);    /* a physical knob on a track */
}
```

- `--ring-action` → `.nav-scan .ring`, `.shutter` (two values → one; both are "the capture action,"
  and the canon calls for one marigold accent ring, not two intensities).
- `--ring-select` → `.btn.saved`, `.state-card .btn.ghost`, `.btn.outline`, `.ow-photo.flag`
  (composed: `var(--ring-select), var(--elev-1)`).
- `--ring-quiet` → `.wl-actions .btn.ghost`.
- `--ring-needed` → `.fchip.needed`. Green stays confined to needs-match.
- `--knob` → `.toggle::after`, `.seg button.sel` (two values → one).

**Focus rings are excluded and untouched.** `.phone :focus-visible`, the three dark-screen variants,
`.sheet-grip-btn:focus-visible .sheet-grip`, and `[aria-invalid="true"]` belong to the a11y round
(criteria 7.2 and 7.5). Do not fold them into the elevation tokens; do not let an elevation
`box-shadow` on a component override a focus ring — where both apply, the focus rule must win, which
it already does by specificity.

`.procbar-fill`'s `inset 0 0 0 1.5px var(--marigold-edge)` is a non-text contrast fix from the a11y
round. Leave it.

## 3.5 Elevation — expected result

| criterion | now | after |
|---|---|---|
| 3.3 elevation is consistent | 2 | 4 — 24 shadow values → 4 levels + 5 named non-elevation rings; the same surface level reads the same on white and on the map; high contrast outlines every level instead of eleven hand-picked components |

---

# 4. Motion scale

## 4.1 Actual inventory

**26 `transition` declarations, 22 distinct; 11 `animation` declarations, 9 distinct; 8 keyframes;
4 easing curves.**

Durations in use: `.15s` · `.2s` ×2 · `.22s` · `.25s` ×4 · `.28s` ×3 · `.3s` ×3 · `.32s` ×2 ·
`.36s` · `.38s` · `.42s` ×2 · `.45s` · `.5s` ×4 · `.55s` ×4 · `.7s` ×2 · `.8s` · `.9s` · `.95s` ·
`1s`. **Nineteen distinct durations.** Criterion 4.2 asks for "roughly 150–250ms for UI"; ten of the
nineteen are above 300ms, and four of those are ordinary UI rather than narrative.

Easings: `cubic-bezier(.2,.7,.2,1)` (8) · `cubic-bezier(.3,.9,.3,1)` (5) ·
`cubic-bezier(.2,.9,.3,1.2)` (1, dropIn overshoot) · `cubic-bezier(.3,.9,.3,1.15)` (1, pinTap
overshoot) · `ease-out` (6) · `ease-in` (2) · `linear` (3). Criterion 4.3 is right that it is
"mostly one curve," but two general-purpose curves are doing the same job.

**What does not move at all.** These are criterion 4.1 — "motion explains a relationship":

| interaction | today |
|---|---|
| screen change, 15 of 26 screens | `display:none` → `display:flex`. A hard cut. |
| screen change, 11 of 26 screens | `screen-in .28s` — an 8px fade-rise with no direction |
| card sheet Peek ⇄ Medium ⇄ Full | `display:none` on `.cs-medium` / `.cs-full`; the sheet's height jumps instantly |
| list ⇄ map toggle | `lv.hidden = !listOpen`. A hard cut. |
| chip selection (all six chip types) | background, border and colour swap with no transition |
| touch feedback on 36 of 44 interactive elements | nothing |
| `.sheet.popup` origin | scales from `.96` at the screen centre — explains nothing about where it came from |

## 4.2 The scale

```css
:root{
  /* durations */
  --dur-fast: 160ms;   /* feedback and in-place state change */
  --dur-base: 220ms;   /* a thing travels: sheet, screen, position, view */

  /* easing — two curves */
  --ease-enter: cubic-bezier(.2,.7,.2,1);   /* arriving / settling: decelerate */
  --ease-exit:  cubic-bezier(.4,0,1,1);     /* leaving: accelerate */

  /* narrative exceptions — named, scoped, and nowhere else */
  --ease-spring: cubic-bezier(.2,.9,.3,1.2); /* pin drop and pin tap only */
  --dur-settle:  900ms;   /* processing: the captured image settles into the ring */
  --dur-check:  1500ms;   /* processing: one named check */
  --dur-drop:    700ms;   /* the pin lands */
  --dur-ripple: 1000ms;   /* the landing ripple, ×2 */
}
```

Both UI durations sit inside the rubric's 150–250ms band. Nineteen durations become two, plus four
narrative constants that exist only inside the scan sequence — which criterion 4.4 already scores 4
and which this spec does not re-time. `--dur-settle` is 900ms rather than the current 1000ms only so
it matches `.ring-photo`'s existing `opacity .9s`; the JS `PROC_SETTLE=1000` beat is canon and stays.

`linear` remains permitted for progress and nothing else: `.ring-fg` / `.ring-rim`
(`stroke-dashoffset`) and `.ow-saving .procbar-fill` (`width`). That is criterion 4.3's exemption
and it is already correct.

**Why three curves and not two.** `--ease-enter` and `--ease-exit` are the system. `--ease-spring`
is a deliberate exception in exactly the same sense that the processing sequence is the duration
exception: the canon calls for pins that "squash slightly on tap" and a scan completion that is "the
largest motion moment," and both need overshoot. It is scoped to two rules — `.pin-drop .pin` and
`.pinbtn.selected .pin` — and appears nowhere else. Today two near-identical overshoot curves
(`1.2` and `1.15`) do that job; one does.

## 4.3 Duration mapping — every current value

| now | → | site |
|---|---|---|
| `.15s` | `--dur-fast` | `.pinbtn .pin` transform |
| `.2s` ×2 | `--dur-fast` | `.toggle` background, `.toggle::after` left |
| `.22s` | `--dur-fast` | `.sheet.popup` opacity |
| `.25s` ×4 | `--dur-base` / `--dur-fast` | `.map-fabs` bottom → base; `.scrim` opacity → fast; `.coach` opacity → fast; `.ring-fg` stroke-dashoffset → **unchanged**, it is progress |
| `.28s` ×3 | `--dur-base` | `.sheet.popup` transform ×2, `screen-in` |
| `.3s` ×3 | `--dur-fast` | `.under8` opacity, `#scan-processing .scan-body` opacity, `.toast` |
| `.32s` ×2 | `--dur-base` | `.sheet` transform + visibility delay |
| `.36s` | `--dur-base` | `pinTap` |
| `.38s` | `--dur-base` | `#map` transform — **must equal the card sheet's duration**; see §4.5 |
| `.42s` ×2 | `--dur-base` | `settle-in` on `#scan-review`, `splashOut` |
| `.45s` | `--dur-base` | `chipIn` |
| `.5s` ×4 | `--dur-base` | `settle-in` on `.wl-card` / `.wl-hero` / `.ob-body`; `.ring-fill` and `.ring-center` opacity stay narrative → `--dur-settle` |
| `.55s` ×4 | `--dur-check` × 0.37 → **`--dur-base`** | `.checkitem` and `.ci-dot` reveal. These are inside the narrative sequence but they are *reveals*, not beats; 220ms keeps each check crisp while the 1500ms beat spacing is unchanged |
| `.7s` ×2 | `--dur-drop`, `--dur-settle` | `dropIn`; `splashIn` → `--dur-drop` (it is the brand's one arrival) |
| `.8s` | unchanged | `.ow-saving .procbar-fill` width — progress, linear |
| `.9s` / `.95s` | `--dur-settle` | `.ring-photo` opacity / transform |
| `1s` | `--dur-ripple` | `.rippler` |

## 4.4 Screen change — where a screen went

Today: 15 screens cut, 11 fade-rise 8px with no direction. Motion must say whether the user went
deeper or came back.

```css
@keyframes screen-fwd { from{opacity:0; transform:translateX(12px)} to{opacity:1; transform:none} }
@keyframes screen-back{ from{opacity:0; transform:translateX(-12px)} to{opacity:1; transform:none} }
@keyframes screen-lat { from{opacity:0} to{opacity:1} }

.screen.active .screen-body,
.screen.active .scan-body,
.screen.active .ob-body { animation: screen-fwd var(--dur-base) var(--ease-enter) both; }
.phone[data-dir="back"] .screen.active .screen-body,
.phone[data-dir="back"] .screen.active .scan-body,
.phone[data-dir="back"] .screen.active .ob-body { animation-name: screen-back; }
.phone[data-dir="lat"]  .screen.active .screen-body,
.phone[data-dir="lat"]  .screen.active .scan-body,
.phone[data-dir="lat"]  .screen.active .ob-body { animation-name: screen-lat; }
```

**Direction is set by the three existing navigation functions**, which already know:

| function (line, as read) | sets | reason |
|---|---|---|
| `goScreen(id, tab)` (3914) | `phoneEl.dataset.dir='fwd'` | pushes a back crumb: the user went deeper |
| `goBack()` (3922) | `dataset.dir='back'` | pops the crumb: the user came back |
| the three bottom-nav handlers (just below `goBack`) | `dataset.dir='lat'` | Map / Scan / Profile are peers; a lateral tab move fades, it does not push |
| `showScreen(id)` called directly (splash → welcome, scan-flow steps) | `dataset.dir='fwd'` default | the scan flow is a forward sequence |

Set the attribute **before** calling `showScreen`, since the animation starts when `.active` lands.
Applies to all 26 screens. `#ob-splash` keeps its own `splashIn` / `splashOut` pair — the launch
sequence is a separate, already-correct moment (criterion 4.6 = 3, "splash only").

The 12px travel is deliberate: 8px (today) reads as a fade with a wobble, and 24px reads as a
carousel. 12px is the smallest distance at which direction is legible.

## 4.5 Sheets — open, close, and the card's three positions

### Open and close

```css
.sheet{
  transform: translateY(105%);
  visibility: hidden;
  transition: transform var(--dur-fast) var(--ease-exit),
              visibility 0s var(--dur-fast);
}
.sheet.on{
  transform: translateY(0);
  visibility: visible;
  transition: transform var(--dur-base) var(--ease-enter),
              visibility 0s 0s;
}
.scrim{ transition: opacity var(--dur-fast) var(--ease-enter); }
```

Three changes, all small:
1. 320ms → 220ms in, 160ms out. **A sheet leaves faster than it arrives.** That asymmetry is what
   makes a dismissal feel obedient rather than sluggish, and it is why the curve differs by
   direction.
2. `--ease-exit` on the closed state, `--ease-enter` on `.on`.
3. **The `visibility` guard's delay must track the duration it is paired with** — `var(--dur-fast)`
   on the closed rule, `0s` on `.on`. The comment at line 239 explains why this guard exists
   (percentage transforms sticking at a stale pixel value on mobile); it is load-bearing and must
   survive verbatim in structure, only the number changes.

The sheet already slides from the edge it docks to, which is the correct answer to "where did it
come from." No change there.

### The popup — where it actually came from

`.sheet.popup` ("How trust grows") scales from `.96` at the screen centre, which says nothing. It is
opened by `button.legend` on the map, so it should grow from that button.

```css
.sheet.popup{
  transform-origin: var(--pop-x, 50%) var(--pop-y, 50%);
  transform: translateY(-50%) scale(.92);
  opacity: 0;
  transition: transform var(--dur-fast) var(--ease-exit),
              opacity var(--dur-fast) var(--ease-exit),
              visibility 0s var(--dur-fast);
}
.sheet.popup.on{
  transform: translateY(-50%) scale(1);
  opacity: 1;
  transition: transform var(--dur-base) var(--ease-enter),
              opacity var(--dur-base) var(--ease-enter),
              visibility 0s 0s;
}
```

`openSheet(id, opener)` (line 3189) **already receives the opening element** — the a11y round added
that parameter for focus return. When the target is `#sheet-trust`, read
`opener.getBoundingClientRect()` against the popup's own box and write `--pop-x` / `--pop-y` as
percentages. One added block in one function, and the plumbing is already there.

### The card sheet's three positions — Peek ⇄ Medium ⇄ Full

Today `#sheet-card[data-pos="peek"] .cs-medium, …{display:none}` removes content from flow, so the
sheet's height snaps. The fix animates the height without needing to know the content height:

```css
#sheet-card .cs-medium,
#sheet-card .cs-full{
  display: grid;
  grid-template-rows: 1fr;
  transition: grid-template-rows var(--dur-base) var(--ease-enter);
}
#sheet-card[data-pos="peek"]   .cs-medium,
#sheet-card[data-pos="peek"]   .cs-full,
#sheet-card[data-pos="medium"] .cs-full{ grid-template-rows: 0fr; }
#sheet-card .cs-medium > *,
#sheet-card .cs-full   > *{ min-height:0; overflow:hidden; }
```

The `0fr → 1fr` grid-row technique animates to intrinsic height with no measurement. It replaces the
three `display:none` rules at lines 711–713 (`#sheet-card[data-pos="peek"] .cs-medium, …`).

**Three consequences the implementer must handle:**

1. **The map pan must travel with the sheet.** `#map{transition:transform .38s …}` becomes
   `transform var(--dur-base) var(--ease-enter)` so `panMap()` and the sheet move as one gesture
   rather than two. This is what makes the pin visibly "step aside for" the sheet instead of
   teleporting.
2. **`revealSelected()` reads `sh.offsetHeight` mid-transition** (line 2800; called from
   `setCardPos`, line 2777) and will now read an in-between value. Call it once immediately (so the
   pan starts together with the sheet) and once again after the transition, using a timer rather
   than `transitionend`: `setTimeout(revealSelected, isReduced() ? 0 : 220)`. See §4.7 for why not
   `transitionend`.
3. > **QUESTION — a11y coordination.** Collapsed sections are currently removed from the
   > accessibility tree by `display:none`. With `0fr` + `overflow:hidden` they remain in the tree
   > and a screen reader would read the whole card at Peek. The correct fix is `visibility:hidden`
   > on the collapsed children plus `aria-hidden`, but focus and announcement behaviour is the
   > a11y agent's this round (criteria 7.3, 7.4, 7.8). **Do not ship the position animation without
   > agreeing this with that work.** If the two cannot be sequenced, keep `display:none` and accept
   > a snap at the position change; every other motion item here is independent of it.

## 4.6 Chips, the list toggle, and the map

### Chip selection

Six chip types change state with no transition and no press feedback: `.filtchip`, `.fchip`,
`.persona`, `.seg button`, `.recent-chip`, `.achip`.

```css
.filtchip, .fchip, .persona, .seg button, .recent-chip, .achip, .tsize-btn{
  transition: background-color var(--dur-fast) var(--ease-enter),
              border-color     var(--dur-fast) var(--ease-enter),
              color            var(--dur-fast) var(--ease-enter),
              transform        var(--dur-fast) var(--ease-enter);
}
.filtchip:active, .fchip:active, .persona:active,
.seg button:active, .recent-chip:active, .achip:active, .tsize-btn:active{
  transform: scale(.96);
  transition: none;              /* press-down is instant; release eases back */
}
```

`scale(.96)` is the canon's "filter chips compress gently."

**Active-filter chips (`.achip`) appearing above the map** already have a matching keyframe:
`chipIn` (currently `.45s`, used by `.proc-chips .fchip`). Reuse it at `--dur-base` for `.achip`
entry in `renderChipRow()`, so a chip visibly arrives when a filter is applied rather than blinking
into existence. On removal, run the reverse (`opacity 1→0`, `scale 1→.96`) over `--dur-fast` with
`--ease-exit` before the DOM removal.

### List ⇄ map — the same places, laid flat

`setListOpen(on)` currently toggles `lv.hidden`. Replace with a class plus a deferred `hidden`, the
same pattern the sheets already use:

```css
.list-view{
  opacity: 0; transform: translateY(8px);
  transition: opacity var(--dur-fast) var(--ease-exit),
              transform var(--dur-fast) var(--ease-exit);
}
.list-view.on{
  opacity: 1; transform: none;
  transition: opacity var(--dur-base) var(--ease-enter),
              transform var(--dur-base) var(--ease-enter);
}
```

In `setListOpen`: add/remove `.on` immediately; set `lv.hidden = true` after `--dur-fast` when
closing (with the reduced-motion guard from §4.7), and clear `hidden` before adding `.on` when
opening. The list keeps leaving the accessibility tree when closed, which criterion 7.7 relies on.

The relationship the 8px rise states: the list is the map's content re-presented, not a different
place. It rises into view and settles back down; it does not slide in from a side, because it did
not come from anywhere.

### Map FABs

`.map-fabs{transition:bottom .25s}` → `--dur-base`. This is the FAB row lifting when the nearby rail
appears; it should travel on the same clock as everything else that travels.

## 4.7 Reduced motion — currently 4, and must stay 4

Two kill-switches exist and both must survive verbatim:

```css
@media (prefers-reduced-motion: reduce){
  *,*::before,*::after{ animation-duration:.01ms !important;
                        animation-iteration-count:1 !important;
                        transition-duration:.01ms !important }
}
.phone.rm *,.phone.rm *::before,.phone.rm *::after{ /* same three */ }
```

Everything added in §4 is a `transition` or an `animation`, so both switches cover it with no new
work. **Three places where that is not enough:**

1. **Never use `transitionend` or `animationend` to set final state.** At a 0.01ms duration the
   event can fire before a listener attaches, leaving the element stuck. Every deferred step in this
   spec — `lv.hidden = true` after the list closes, the second `revealSelected()` after the card
   position settles, the `.achip` DOM removal after its exit — uses
   `setTimeout(fn, isReduced() ? 0 : <duration>)`. `isReduced()` already exists (line 2421) and
   correctly ORs the media query with the Profile toggle.
2. **The scan sequence's reduced path is already correct and is not touched.**
   `.scanscreen.reduced` swaps the ring for `.procbar`, sets `.checkitem{transition:none}` and
   `.scan-body{transition:none}`, and `owPublish()` sets `bar.style.transition='none'` before
   jumping the bar to 100%. Nothing in §4 touches `.scanscreen.reduced`, `.procbar`, `.ringwrap` or
   the `runProcessing` timings. `--dur-check` and `--dur-settle` are declared for documentation; the
   JS constants `PROC_SETTLE=1000` and `PROC_CHECK=1500` remain the source of truth for the beats.
3. **Do not zero the `--dur-*` tokens as a reduced-motion strategy.** The existing
   `transition-duration:.01ms !important` overrides them anyway, and a token override would also
   silently kill the two `linear` progress transitions that must keep running so the user can still
   see work happening — which is precisely the distinction criterion 4.5 measures ("removes
   animation without removing meaning or feedback").

**Verification after implementing:** with Reduce Motion on, walk splash → welcome → needs → map →
pin → card at all three positions → filters → list → scan → processing → review → published →
profile → owner workspace, and confirm (a) every screen still arrives, (b) the processing bar still
advances, (c) no element is left mid-transition, (d) every `:active` state still gives feedback,
since a press state is feedback, not animation, and must not be removed.

## 4.8 Motion — expected result

| criterion | now | after |
|---|---|---|
| 4.1 motion explains a relationship | 2 | 4 — screens push and pop by direction; the popup grows from its opener; the card's positions animate; the list rises and settles; the map pans with the sheet |
| 4.2 durations consistent and short | 2 | 4 — 19 durations → 2 UI values (160/220ms) + 4 named narrative constants |
| 4.3 easing consistent and physical | 3 | 4 — 7 easings → 2 curves + 1 scoped spring; `linear` only on the two progress transitions |
| 4.4 the processing sequence earns its length | 4 | 4 — untouched |
| 4.5 reduced motion | 4 | 4 — protected by §4.7 |
| 4.6 nothing animates on load unasked | 3 | 3 — unchanged; the splash remains the only load animation |

---

# 5. Touch feedback — criterion 5.3, currently 2

## 5.1 What exists

**44 distinct interactive components** (selectors with `cursor:pointer` or `cursor:grab`). **Eight
have press feedback:**

`.fab-needs` `.fab-filters` (`scale(.97)`) · `.nav-scan .ring` (`scale(.95)`) · `.shutter`
(`scale(.93)`) · `.cluster` (`scale(.95)`) · `.btn` (`scale(.98)`) · `.sheet-close`
(`background:#f0eef8`) · `.ow-photo .ph-btn` (`background:#F1EFFA`).

**Thirty-six have none**, including every row and every chip — exactly what the rubric says.

The eight that do exist use five different scale values (.93/.95/.97/.98) and two ad-hoc wash
colours.

## 5.2 The rule

Two press treatments, chosen by shape, not by importance.

```css
:root{ --press-wash: #F1EFFA; --press-wash-ground: #E6E2F4; }
.phone.hc{ --press-wash: #E0DAF2; --press-wash-ground: #D5CEEA; }
```

**Compact controls (buttons, chips, pills, circular controls) — scale.**
`:active{ transform: scale(.97); transition: none; }` and a release transition of
`transform var(--dur-fast) var(--ease-enter)`. One value, .97, replacing the current four.

Applies to: `.locpill` · `.hamb` · `.ctl-btn` · `.achip` · `.recent-chip` · `.filtchip` · `.fchip` ·
`.seg button` · `.tsize-btn` · `.search-clear` · `.flowhead .backbtn` · `.ob-back` · `.cancel-x` ·
`.ow-banner .backbtn` · `.btn-textlink` · `.filt-reset` · `.rcpt-back` · `.correct-btn` ·
`.lib-link` · `.ow-taxlink` · `.sheet-grip-btn` — plus the eight existing, normalised to .97.
Exceptions kept at their current values because they are physically larger: `.shutter` (.93) and
`.nav-scan .ring` (.95) — a 76px shutter needs a deeper press to read as one.

**Full-width rows — wash.** Scaling a row that spans the screen looks like a rendering fault.
`:active{ background-color: var(--press-wash); transition: none; }` with a release transition of
`background-color var(--dur-fast) var(--ease-exit)`.

Applies to: `.prof-row` · `.srow` · `.lrow` · `.nb-card` · `.prov-row` · `.persona` ·
`.claim-result` · `.verify-opt` · `.authz` · `.ow-editrow` · `.photo-add` · `.photostrip` ·
`button.legend` · `.navbtn` · `.ow-sel select`. Rows sitting on the lavender ground (`.srow`,
`.lrow`, `.claim-result`) use `--press-wash-ground` so the press is visible against a
non-white start.

**`.pinbtn` is excluded** — it already has `pinTap`, which is the canon's squash-and-rise and is
better feedback than either treatment.

**Press-down is instantaneous (`transition:none`), release eases out.** Feedback that fades in is
not feedback. This asymmetry is the same one the sheets use and is deliberate.

## 5.3 Count

36 new `:active` rules; 6 existing ones normalised to the two values; 2 kept as documented
exceptions. Under reduced motion, `transform` and `background-color` presses both survive — the
kill-switch zeroes durations, and a `transition:none` press has no duration to zero. §4.7's
verification step (d) checks this.

---

# 6. Icon grid — criterion 5.4, currently 2

## 6.1 Actual inventory

**118 `stroke-width` attributes, 15 distinct values.** The rubric says "2.2 and 2.4"; the real
spread is wider:

| width | n | width | n | width | n |
|---|---|---|---|---|---|
| `2` | 32 | `2.4` | 5 | `2.5` | 2 |
| `2.2` | 18 | `2.3` | 5 | `1.4` | 2 |
| `2.1` | 17 | `2.6` | 4 | `1.7` | 1 |
| `1.9` | 14 | `3` | 3 | `2.8` | 1 |
| `1.8` | 8 | `4` | 3 | `5` | 3 |

Nine of those (`3`, `4`, `5`) are structural — the frame-guide corners, the pin silhouettes, the
logo mark. **The remaining 109 are icons, at 12 different stroke widths.**

**117 `viewBox` attributes**, of which **98 are `0 0 24 24`** — the grid is already there in all but
name. The rest are illustrations and the pin/logo art on their own canvases.

**Terminals are already consistent:** `stroke-linecap="round"` on 72, `stroke-linejoin="round"` on
45, and **zero** occurrences of `butt`, `square`, `miter` or `bevel`. That half of criterion 5.4 is
already correct and needs no work.

**Eighteen distinct render sizes** on the 24-grid: 11 · 12 · 13 · 14 · 15 · 16 · 17 · 18 · 19 · 20 ·
22 · 23 · 24 · 26 · 28 · 36 · 38 · 40. The most common is 17px (24 uses), then 20px (11) and 19px
(10). Three sizes within 3px of each other is not a system.

## 6.2 The grid

```
canvas      24 × 24 viewBox
live area   20 × 20, centred (2px keyline on all four sides)
stroke      2, always
terminals   stroke-linecap="round"  stroke-linejoin="round"
fill        none; stroke="currentColor"
alignment   strokes on whole units; a 2-wide stroke centred on a whole unit renders on the half-pixel
```

```css
:root{
  --icon-xs: 12px;   /* inline in a chip, badge or meta line */
  --icon-sm: 16px;   /* row leading icons, legend swatches */
  --icon-md: 20px;   /* the workhorse: nav, controls, feature chips */
  --icon-lg: 24px;   /* hero and empty-state glyphs */
  --icon-glyph:    20px;  /* the ✕ / ‹ text glyphs in 44px buttons (see §1.6) */
  --icon-glyph-sm: 12px;  /* glyphs inside small circles: .tl-dot, .achip .x */
}
```

## 6.3 Mapping

**Stroke:** every icon `stroke-width` becomes `2`. 109 attributes, of which 32 already say `2`, so
**77 change**. The nine structural strokes (`3` on the frame guide, `4` on the pin outlines, `5` on
the logo arcs) and the CSS `stroke-width:8` on `.ring-bg` / `.ring-fg` are not icons and are
excluded — they belong to the pin and ring components, which the canon specifies directly.

**Size:** 18 render sizes → 4.

| now | → |
|---|---|
| 11, 12, 13 | `--icon-xs` (12) |
| 14, 15, 16, 17 | `--icon-sm` (16) |
| 18, 19, 20, 22 | `--icon-md` (20) |
| 23, 24, 26, 28 | `--icon-lg` (24) |
| 36, 38, 40 | keep — these are illustration-scale marks in `.big-icon`, `.state-card .sc-icon` and `.cr-icon`, not icons in a row |

The 17px → 16px move is the largest single change (24 sites) and shrinks nothing perceptibly.

**Optical weight across sizes — the decision and why.** A 2-unit stroke on a 24 grid rendered at
12px draws 1px; at 24px it draws 2px. Per-size stroke compensation (making the 12px icon use
`stroke-width="4"` so it also draws 2px) was considered and **rejected**: it puts twelve different
numbers back in the file, which is precisely the defect being fixed, and it is optically wrong —
a small icon *should* carry a lighter stroke, the same way small type carries a lighter weight. One
stroke width in the source grid, four render sizes, is the system. The rubric's complaint is that
two icons at the *same* size use 2.2 and 2.4; a single source value removes that entirely.

**Cross-reference, not in scope.** Criterion 5.6 (raw glyphs: `✕`, `▾`, `‹`, `♥`, the `.d-arrow`
strike-through arrow) scores 1 and is a separate fix. The `--icon-glyph` constants above give those
glyphs one size each, which is worth doing regardless of whether they are later replaced by SVG. If
they are replaced, they join `--icon-md` and `--icon-xs` and the two glyph constants can be deleted.

---

# 7. Open questions

Marked here rather than guessed. Each needs one decision or one measurement, not a design pass.

1. **`tnum` in Google-served Nunito (§1.5).** Needs a rendered-width measurement, not a judgement.
   If absent, the fallback is `min-width` + right-alignment on the distance and freshness columns,
   not a font change.
2. **Pin tip vs pin centre (§2.7).** `.pinbtn` centres a 44px button on the coordinate, so a pin's
   tip sits ~16px below the point it names. Intentional or accidental? The canon's "selected pins
   rise 4–6px" implies the resting state should be tip-on-point. Fixing it touches
   `revealSelected()`'s `limit` maths.
3. **Card-sheet position animation vs the accessibility tree (§4.5).** Replacing `display:none` with
   `0fr` grid rows keeps collapsed content in the a11y tree. This must be sequenced with the a11y
   agent's focus and announcement work, or deferred. Every other motion item is independent of it.
4. **`.search-bar .searchfield` at elevation 2 (§3.3).** It is a form control wearing a floating
   shadow. It should drop to level 1 and take the border treatment the a11y round gives every other
   form control — but form-control borders are a11y-owned this round, so I have not prescribed it.
5. **Body weight 700 → 600 (§1.3).** Contrast maths is unaffected and the body inks sit at 8.4:1 and
   15:1, well above the 7:1 product floor. But a 200-unit weight drop across 53 selectors is a
   visible change of character in a rounded humanist face. Worth one side-by-side look at the card
   and the list view before committing, since the reference mock's warmth partly comes from weight.
6. **`--sp-5` at 12px absorbs 179 of 714 tokens (10, 11, 12, 13).** That is a lot of the interface
   resolving to one value. It is the correct nearest-step answer and I would ship it, but if the
   result reads flat, the remedy is to split row-internal padding (`--sp-5`) from between-row gap
   (`--sp-6`) per component, not to reintroduce a 10px step.

---

# 8. Summary — the four systems and what they touch

| system | now | becomes | call sites |
|---|---|---|---|
| **Type** | 40 font sizes · 4 weights · 11 line-heights · 10 letter-spacings · 0 tabular figures | 8 size steps · 3 weights (900 reserved to 21 sites) · leading defined at every step · 5 tracking tokens · `.tnum` on 27 numeral-bearing elements | **493** declarations (209 size + 208 weight + 48 leading + 19 tracking in CSS, + 9 inline), across **210 rules**; **+31** new `.tnum` selectors |
| **Spacing** | 40 distinct values · 74 distinct `padding` shorthands · 37% off-grid | 10-step scale (2·4·6·8·12·16·24·32·48) + 8 layout constants + 13 excluded geometry sites; nearest step, ties up; 9 boxes replaced by proximity | **525** declarations / **714** numeric tokens; the two visible moves are 10→12 (72) and 14→16 (52) |
| **Elevation** | 24 distinct shadows · 3 different sheet shadows · 2 marigold rings · 2 knob shadows · 3 hairline colours · HC outlines 11 hand-picked components | 4 levels (resting · raised · floating · overlay) as 6 tokens + 5 named non-elevation rings + 1 hairline; HC redefines the level tokens so every elevated surface is outlined | **59** shadow declarations + **9** hairline borders + **2** HC rules deleted = **70** |
| **Motion** | 19 durations · 7 easings · screens cut · card positions snap · list toggle cuts · chips have no transition | 2 UI durations (160/220ms) + 4 named narrative constants · 2 curves + 1 scoped spring · directional screen push/pop · popup grows from its opener · card positions animate · list rises · chips transition | **45** CSS sites (26 transition + 11 animation + 8 keyframes) + **7** JS entry points (`showScreen` `goScreen` `goBack` `openSheet` `setCardPos` `setListOpen` `renderChipRow`) |
| *craft:* **touch feedback** | 8 of 44 interactive components, at 5 different scale values | 2 treatments (scale .97 for compact, wash for rows), press instant, release eased | **36** new `:active` rules + 6 normalised |
| *craft:* **icon grid** | 12 icon stroke widths (1.4–2.8) · 18 render sizes | one 24-grid, `stroke-width:2`, round terminals (already correct), 4 render sizes | **77** stroke attributes changed of 109 icons; **18** render sizes → **4** |

**Total: roughly 1,300 declaration sites**, almost all of them mechanical find-and-replace once the
tokens are declared. The four token blocks themselves are about 70 lines added to `:root`.

**Suggested order.** Elevation first (self-contained, 70 sites, no interaction with the a11y round).
Then spacing (mechanical, no behaviour change). Then type (largest, but purely declarative). Motion
last, because §4.5's card-position work needs the a11y round's focus and announcement decisions to
have landed. Touch feedback and the icon grid can be done at any point; neither depends on anything
else here.

---

*Written 2026-09-05 against `phone-app-prototype.html` at 4,695 lines, read while the accessibility
round was mid-edit. Counts are exact as of that read. This document changes no file but itself.*

---

# Decisions on the open questions

Settled so the implementation round is not blocked. Two were measured rather than reasoned.

**1. Tabular figures: no work needed.** Measured in the browser with Nunito loaded from Google:
ten `1`s and ten `8`s render at identical width with no `font-variant-numeric` applied
(difference 0.00px at 40px/700). Nunito's default figures are already tabular, so the proposed
`.tnum` class would be a no-op. **Drop all 27 sites.** Rubric line 1.5 is therefore already
satisfied by the typeface and should be rescored to 4 with this measurement as its evidence,
not implemented and then rescored.

**2. Pin anchoring: fix it.** Pins are placed with `left`/`top` and no compensating transform,
on a 36x44 viewBox whose tip is at the bottom centre. A pin that does not point at the thing it
marks is a correctness defect on a map product, not a polish item: at phone scale the reported
offset is roughly the width of a storefront, so the pin can sit over its neighbour. Anchor the
tip: translate by -50% horizontally and -100% vertically, and update `revealSelected()` in the
same change since it computes from the same box.

**3. Card-position animation: defer to a later round.** Animating the three-position card sheet
with a `0fr → 1fr` grid row keeps collapsed content in the accessibility tree, which directly
contradicts the round now closing the screen-reader defects. Accessibility correctness wins.
Revisit once the focus and announcement work has landed and can be re-tested against it, and
until then let the card positions change without a height animation.

**4. Ordering.** Elevation, then spacing, then type, then motion, as the spec proposes. Motion
is the only one that depends on the accessibility round, and it is last.

**5. Scope boundary with the accessibility round.** Focus rings, `aria-invalid`, inline error
styling and form-control borders stay owned by that round and are not touched here, even where
they carry a shadow or a border that would otherwise be unified.

**6. Colour is untouched.** Where a shadow or border carries a hue, the hue is preserved
verbatim and only the geometry is unified. The palette rules are settled and are not in scope
for any round of this loop.
