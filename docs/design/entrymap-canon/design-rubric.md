# EntryMap design rubric

The bar: a product that looks like it was made by people who care, for people who are
usually given software that does not care. Not decorated. Considered.

Scored 0-4 per line. 0 absent, 1 present but wrong, 2 acceptable, 3 good, 4 nothing to add.
A round is finished when nothing sits below 3 and the average is 3.5 or better.
Every score needs a named screen as evidence. "Looks fine" is not a score.

Revision history lives at the bottom. Update the scores in place each round.

---

## 1. Typography

| # | Criterion | Score | Evidence |
|---|---|---|---|
| 1.1 | A real type scale, not ad-hoc sizes. Every size on screen traces to a defined step. | 4 | Round 2: 177 selectors mapped onto the spec's 8 steps. **0** literal `font-size` values in `em` remain anywhere in the file (was 29 distinct values). The 8 remaining `px` sizes are exactly the spec's legitimate set: the 15px root and its two `[data-textsize]` overrides (16.2 / 18.9), the text-size picker's own 14/17/20 preview (it must not scale with the setting it controls), the 13px desktop stage caption outside the phone, and `.street-label` at 10.5px, the one deliberate non-scaling piece of content type because the map geometry is computed in px. The eight steps are also authored once as `.t-display` &hellip; `.t-micro`. **Round 4 (asset library):** the scale survives the face change unaltered &mdash; the eight steps are `em`-relative, so moving from Nunito to Atkinson Hyperlegible Next changed no size. Re-measured over all 26 screens at both text-size settings: **0** clipped text nodes, **0** horizontal overflow. **Round 6:** the 4 above was not earned, and this line is the clearest case of a round scoring what it changed rather than measuring what remained. The eight steps were `em`, which is a MULTIPLIER on whatever font-size the container happens to carry, so a step nested inside another step compounded. Measured across all 26 screens by walking every selector in the stylesheet that declares `font-size:var(--fs-*)` and reading the computed size of every element it matches: seven roles rendered at **nineteen distinct pixel sizes** &mdash; `--fs-sub` at 12.9 / 12.255 / 11.467 / 11.094 / 9.861 and `--fs-body` at 14.25 / 12.9 / 12.667 / 12.255, which puts one role's smallest instance below the step beneath it. The steps now multiply one anchor (`--root-fs`, the only font-size the text-size preference moves) and are declared on `.phone` beside it. Re-measured the same way: **eight distinct sizes for eight steps**. The one role showing two values is `--fs-h1`, at three sites that explicitly declare `--fs-h2` inline &mdash; a local override, not compounding. Default rendering of a top-level element is unchanged; only the arithmetic nobody wrote is gone. |
| 1.2 | Weight carries hierarchy. No more than three weights doing real work; 900 is not the default. | 4 | **Round 4 re-pitched the ladder onto the new face and re-measured it.** Atkinson Hyperlegible Next's variable axis runs 200-800, so 600/800/900 becomes **500 / 650 / 800** &mdash; still exactly three weights, and the top one is still a reserved resource. 650 and 800 are not arbitrary: the library's own assets set badge labels at 650 and state headings at 750, so the two upper steps are the weights the approved boards are drawn in. Measured in the browser over all 26 screens on every text-bearing leaf element inside the phone: **500 on 125, 650 on 211, 800 on 61**, and weight 700 on 4 &mdash; those 4 are the UA bolding `<b>`, not a rule, the same 4 Round 2 measured. CSS still contains **0** literal `font-weight` values. *Superseded Round 2 evidence:* 900 on 21 declarations, 800 on 112, 600 on 71; measured 900 went 234 of 506 (46%) to 95 of 565 (17%). |
| 1.3 | Line length stays readable, roughly 45-75 characters for body copy. | 3 | Held at 3 on a Round 3 measurement rather than left "unchanged". The main reading column is right: `--fs-body` 14.3px / `--lh-body` 1.5 in a 358px column gives 52-68 characters. But sampling every multi-line paragraph across all 26 screens gives a median of **35 characters per line**, because most supporting copy sits in a narrower sub-column beside a 36px icon box and a chevron. That is under the band, and the spacing pass widened it only slightly. Fixing it is a layout decision about whether row sub-copy may use the full width, not a token change. Recorded rather than rounded up. |
| 1.4 | Line height rises for body copy and tightens for display sizes. | 4 | Round 2: leading is named at every step and applied with the size, never left to inherit `normal`. Display 1.0, h1 1.1, h2 1.15, h3 1.22, body 1.5, sub 1.45, meta 1.35, micro 1.25, plus `--lh-row` 1.3 for one-line row labels that may wrap to two. |
| 1.5 | Numerals align in tabular contexts (freshness, counts, distances). | 4 | **Round 4 caught a live regression here and fixed it.** Round 2's 4 rested on a measurement of the FACE: Nunito's default figures are tabular, so no `font-variant-numeric` was needed and the proposed `.tnum` class would have been a no-op at all 27 sites. Atkinson Hyperlegible Next's figures are **proportional**: measured in the browser at 40px/650, ten `1`s render 174.00px and ten `0`s render 263.21px &mdash; an **89.21px spread** that would have silently pulled every freshness, count and distance column out of line. The face supports `tnum`; `font-variant-numeric:tabular-nums` is now set once on `body`, and the same measurement is **0.00px** across all three weights. Set at the root rather than at 27 sites because root is exactly the scope the old face gave for free. |
| 1.6 | Letter-spacing tightens on display sizes and opens on small caps labels. | 4 | Round 2: 10 ad-hoc values collapse to 5 tokens &mdash; four negative display values (-0.025 / -0.02 / -0.015 / -0.01em), `--ls-caps` 0.08em on every uppercase micro label (replacing .05, .06 and .08em across 9 sites), `--ls-caps-wide` 0.14em on the two deliberately wide-tracked marks (welcome tagline, map street labels), and `--ls-flat` 0 elsewhere. The one negative value at 0.7em, which was invisible and harmful, is gone. **Round 4 (asset library):** unchanged; the five tracking tokens are face-independent and re-measured clean. |
## 2. Hierarchy and layout

| # | Criterion | Score | Evidence |
|---|---|---|---|
| 2.1 | One clear primary action per screen; secondary actions visibly subordinate. | 4 | Round 2, board section 4. Three button ranks now differ in kind, not only in tint: primary is the only filled control (solid purple, or marigold on the camera ask &mdash; the one moment the product asks rather than offers), secondary is white with a 2px purple border and never a grey fill, tertiary is plain purple text. The grey-lavender `.btn.ghost` fill and the grey `.btn.quiet` fill are both gone. `--fw-display` is reserved for the primary label, so the rank is carried by weight as well as by fill. **Round 5** applies the boards' action rule, which the build had half-applied: marigold is the primary wherever the action *gets us data* (Scan an entrance, Scan this entrance, Re-check entrance, Allow camera, Publish scan) and violet is the primary everywhere else, with an OUTLINED purple secondary beneath it rather than a plain text link. "Not now" under Allow camera and "Maybe later" under Re-check entrance were tertiary text and are now the board's outlined rank, so a marigold primary always sits above a secondary of the same weight class. The bottom bar's Scan control keeps marigold and cannot be read as the Scanned-on-site tier: it is an outlined ring with a camera aperture on indigo, where the tier is a filled teardrop with a person glyph and an indigo rim. Its glyph was `#784410` on indigo900 &mdash; a brown on a near-black, left behind by Round 4's chrome change &mdash; and is now marigold400 at 11.6:1 on the bar. |
| 2.2 | Spacing follows one scale; no arbitrary gaps. | 4 | Round 3. Forty distinct values, 37% of them off-grid, become a **10-step scale** (0&middot;2&middot;4&middot;6&middot;8&middot;12&middot;16&middot;24&middot;32&middot;48) plus **7 layout constants** for the fixed chrome. Nearest step, ties round up, applied mechanically to CSS and to every inline style. Measured on the committed file: **611** numeric values across `padding` / `margin` / `gap`, of which **574 resolve to a token** and **12 raw `px` remain** &mdash; and all twelve are the documented geometry sites (the scan button&rsquo;s -26px rise above the bar, the 40px and 52px clearances for the card close button and the map-control stack, the two 60px list-header margins, the 44px back-button balance, two optical nudges at -3px and -2px, and `.ow-stackrow.new` whose -14px bleed must equal its 14px padding). Each is commented with what it is anchored to, so a later pass does not "fix" it. The four bottom paddings that all meant "clear the nav bar" (96 / 100 / 104 / 110) collapse to `--pad-bottom` 104, which also closes a real defect: `.screen-body` was padding 96px against an 86px nav. |
| 2.3 | Related things are grouped by proximity before they are grouped by a box. | 4 | Round 3, on the stated rule: *a box earns its keep only when it changes surface, carries a state, or holds a scroll boundary; grouping alone is proximity's job.* **Nine boxes removed or merged, four kept with the reason written into the file.** The three &ldquo;How trust grows&rdquo; rungs are now three rows on the sheet's own white separated by `--sp-7` (three boxes inside one white sheet is a box inside a box); `.need-breakdown` indents under the chip it breaks down; `.receipt-note` became the sub-line of the `.prov-row` it had been detaching from; `.whatsnext` lost the border that only repeated its heading; `.policy-line` stopped being a shadowed white card holding one line of copy. **Six treatments of &ldquo;a quiet supporting note&rdquo;** &mdash; `.tax-box`, `.state-card .sc-note`, `.ow-flagnote`, `.priv-line`, `.guardrail`, `.a11y-note`, three of them filled and rounded at three different paddings and three borderless &mdash; are now **one** component; the purple ones keep their purple ink and lose only the fill. The four owner cards dropped their inner row hairlines, because card + divider + row rhythm is three signals for one grouping. Kept, each with its reason: `.tile` (the fill carries freshness ageing, so the box *is* the state), `.preview` (it is a preview *of a card*, so the box is the subject), and `.evidence` / `.ow-note-card` (the 3px left rule reads as a quotation; only the doubled fill went). |
| 2.4 | The eye reaches the most important thing first on every screen. | 4 | Round 2. The map had no reading order at all: 64 identical pins. It now has four levels that encode evidence strength and nothing else &mdash; 1 owner pin at 40px, 9-11 scanned at 30px, the rest as 14px dashed rings, and numbered discs for density. Counted at default zoom: 1 level-1, 9 level-2, 48 level-3 rings, 1 disc holding 6. The few purple marks read first, the marigold next, the rings as ground texture. |
| 2.5 | Density suits the job: the map is calm, the card is informative, settings are scannable. | 4 | Round 2, measured the same way before and after (sum of each mark's rendered geometry bounding box, over the 390x844 map viewport): **34,321px&sup2;, 11.3% of the map &rarr; 14,905px&sup2;, 4.9%** &mdash; a 57% reduction in drawn mark area with **every one of the 64 places still on screen** (58 marks + 1 disc of 6). Zoomed out, estimated collapses entirely: 8 full pins + 14 discs holding 56 = 64, so the wide view answers "where has anyone actually been" instead of "where are there doors". Ceiling of 12 full pins at phone width is respected (10 drawn). |
| 2.6 | Optical alignment where geometric alignment looks wrong (icons in rows, pin tips). | 4 | Round 2, both halves fixed and measured. **Pin tips:** the button is now a zero-size anchor on the projected coordinate and the art hangs from it by the tip; across all 58 pins the drawn tip's offset from the coordinate is max &#124;dx&#124; = 0.00px, max &#124;dy&#124; = 0.00px (previously the pin was placed by its box origin with no compensating transform, so it pointed roughly a storefront's width away from what it marked). Level-3 rings, which have no tip, are centred instead. **Row icons:** seven different leading-icon boxes (26/30/32/34/34/38/38px, two different radii, two different fills) collapse to one 36px box at radius 11 on `--icon-box`, so labels align down every column. **Round 3 closed the third rule in design-systems-spec 2.7:** the six circular glyph containers that hold a tick or a numeral (`.tl-dot`, `.ow-tick`, `.ci-dot`, `.nl-dot`, `.p-ring`, `.cr-mark`) now carry `padding-bottom:1px` on their flex centring, because a checkmark is optically low and geometric centring makes it sit high in its circle. Three privacy rungs that were carrying an inline 34px / radius-10 / `#fff` icon box now use the one `--icon-box`, so that column aligns with every other. |

## 3. Colour and depth

| # | Criterion | Score | Evidence |
|---|---|---|---|
| 3.1 | The palette carries meaning, and meaning only. Blue estimated, marigold scanned, purple owner, green match, amber ageing, no red. | 4 | Held through the new map ground, which is the hardest test it has faced. The ground echoes the whole palette on **saturation, not hue**: no ground tone exceeds chroma 43 while the least saturated marker colour is chroma 95, so a marker is always the most saturated thing within its own radius; no ground element is ever a lone disc or a teardrop (canopy is only ever four or more overlapping lobes, a kerbside band, or a filled grove); and any lobe whose centre lands within 26px of a full pin is dropped before it is emitted, so nothing decorative can sit inside a marker halo. No red anywhere. Round 3 also **settled the estimated blue**, which two committed files disagreed about: `design/pins-and-icons.html` specified #2C63C9, `design/map-hierarchy.html` used #3F79DC, and the shipped teardrop's token read #3F79DC while its own inline fallback read #2C63C9. One token now &mdash; `--blue-edge:#2C63C9`, the gallery's value, the one the level-3 ring already shipped as, and the one that drops the ground's luminance floor from 0.691 to 0.510 and so makes this ground possible at 3:1. `--blue-pin` is gone. Round 2's halo judgement (green, not the gallery's purple) stands unchanged. **Round 4 (asset library):** **the palette is now the approved one, not an approximation of it.** Eleven values from `asset-library/tokens/variables.css` are the only authored colours in the file; every other colour is one of them or a documented two-step mix of two of them. The five the owner flagged all moved: ink #241F3A &rarr; indigo900 #17103D, purple #7053C5 &rarr; violet600 #5B35F5, sky #7CC4FA &rarr; sky400 #69B7FF / sky700 #1266A6, marigold #F0A32F &rarr; marigold400 #FFBF24, lavender #EDEBFA &rarr; lavender100 #F2EEFF. Meaning is unchanged and the tiers are unchanged. The one retirement is the match halo: Round 2 chose green because purple already meant owner-confirmed, and the library supersedes that with three approved halos that carry the state in LINE STYLE first &mdash; solid indigo900 good, dashed violet600 partial, dotted sky700 unknown. `--match-green` is gone. Live hex literals in the file: **81**, every one traceable to the official palette; the four legacy values that still appear (#BF0A30, #002868, #5A4BE0, #C4D0F6) appear only inside comments recording what was removed. **Round 6:** **the palette carried meaning and also carried a purple cast over everything.** `--ground` was mapped onto `lavender100`, so lavender was not an accent, it was the app. Measured over all 26 screens as a share of painted area: **50.6% lavender, 55 elements, 14 of them a `.screen-body`**, against a board whose screen body behind cards measures `#FDFDFD`. `--ground` is now `--white`, which is one of the eleven official values and therefore survives the palette change that is coming; lavender is left where the boards actually use it. Re-measured: **0.9% of painted area, 42 elements, none of them a screen body** &mdash; leading icon boxes, the profile avatar, a selected chip, the privacy note. Every contrast figure in this file was solved against lavender100 and white is lighter, so all of them rise and none falls; measured before and after over all 26 screens, the set of text nodes under 7:1 is **identical** (32, minimum 6.42:1, all white on violet600) and the set under 4.5:1 is empty in both. | **ROUND 7.** Re-cited, because the strongest colour evidence on this line pointed at a superseded file. The library it named, `board-refs/entrymap-assets/asset-library/`, **is superseded in full** by `board-refs/entrymap-build-ready/asset-library/` and must not be re-adopted: its palette differs from the canonical one on **ten of eleven values** (counted, not quoted &mdash; the ledger and the Round 7 brief both say six), and its `svg/brand/mark-primary.svg` is the defective mark that drops the white disc behind the doorway, which is the defect the owner reported at 17:00. The build now takes all twelve authored colours from `entrymap-build-ready/asset-library/tokens/variables.css`, cross-checked against `tokens/design-tokens.json` (same twelve values) and against `PACKAGE-MANIFEST.json`, whose recorded sha256 for `variables.css` (`6032F179...D9BDDFFB`) matches the bytes on disk. The meaning map is unchanged &mdash; sky700 estimated, marigold400 scanned, violet600 owner, indigo900/violet600/sky700 for the three match line-styles, amber700 ageing, no red &mdash; so this stays a 4 on a canonical source instead of a retired one. **Round 8:** The Estimated mark is redrawn as gallery-4 candidate J1, which the owner chose: a SOLID sky700 teardrop, white fill, and a doorway glyph (two rounded posts, one lintel, three threshold dots). The dashed `7 6` outline and the italic serif "i" are gone from the build &mdash; **0** occurrences of `stroke-dasharray="7 6"` anywhere in the file, verified by grep, and **0** italic-`i` text nodes on any surface that draws the tier (map at both zooms, trust ladder, card, receipt, list, onboarding tiles). The tier is still carried by shape and fill and never by colour: white fill + sky700 outline + doorway, against marigold400 + camera and violet600 + storefront. The card's Estimated tier CHIP also stops using a dash (`.tierchip.est` 2px dashed sky400 &rarr; 2px solid sky700), because its own code comment justified the dash with "dashed is what the Estimated pin uses" and that is no longer true; the chip still prints the word and carries the sparkle glyph, so nothing there is colour-alone either.
| 3.2 | No screen is monotone; each has a considered accent relationship. | 4 | Round 2's seven illustrations are unchanged and re-verified; Round 3 answered the one surface they could not reach. The map was a flat lavender canvas &mdash; one block tone, one street width, no implied light, trees as scattered dots &mdash; and it is now **Terrain's colour on Relief's light**: warm sand ground, sage canopy, marigold plazas, and cool lavender towers standing among warm putty low-rise, so a block reads as buildings of different eras rather than one slab. Depth comes from the four things the canon asks for and not from a drop shadow: a real road hierarchy (16 / 11 / 8 / 4.5px), footprints in five tones **ramped by mass** so the variation reads as building size rather than noise, one light direction applied to every footprint as a two-step cast shadow plus a lit top-and-left edge, and landcover as areas. Measured on the drawn SVG at 390x844: **1,711 shapes from 15 ground tones**, where the old ground drew 128 from 4. **Round 6:** the accent relationships are now readable as accents. Selection was the loudest offender: `.persona` and `.verify-opt` are full-width rows and were filled edge to edge with lavender when selected, so a form of five choices read as a block of purple. The board fills a selected CHIP and marks a selected ROW with a filled violet disc and a violet keyline on white. Split accordingly &mdash; rows go white, chips keep the wash &mdash; and the error box, which was also lavender, is white with its violet keyline, so the one thing that must be noticed is no longer the same weight as the calmest thing on the screen. The state carrier is unchanged in every case (the filled disc plus `aria-pressed`/`aria-checked`), so 3.5 is untouched. |
| 3.3 | Elevation is consistent: the same surface level always reads the same. | 4 | Round 3. **24 distinct shadows become 4 levels** carried by 6 tokens, plus 5 named rings that were never elevation in the first place. Each level is two shadows &mdash; a tight contact shadow that anchors the object and a wide ambient one that gives it distance &mdash; which is exactly what makes one level read the same on a white sheet and on the map ground; opacity rises .07 &rarr; .14 &rarr; .20/.24 so the ordering is legible. Measured in the browser over every element inside the phone, **11 distinct `box-shadow` values are painted**, and they are: `--elev-1` (14 cards resting on the lavender ground), `--elev-2` (18 things that float over the map), `--elev-3-dock` (`.sheet`, `#sheet-card`, `.ow-sheet` &mdash; one docked sheet drawn three different ways), `--elev-3-dark` (`.wl-card` on the aubergine hero), `--elev-3-free` (the trust popup and the toast, which had **no shadow at all**), `--ring-action` (two marigold glows for one action), `--ring-select`, `--ring-quiet`, `--knob` (two knob shadows for one knob), and the two progress rims the accessibility round owns and this round did not touch. Across **60 `box-shadow` declarations** there is no hand-written elevation value anywhere inside the phone. High contrast now **redefines the level tokens centrally**, so a surface is outlined because of the level it is at; previously two rules hand-picked 11 components and every other elevated surface was missed. `.search-bar .searchfield` left level 2 &mdash; it is a form control, not a floating object. |
| 3.4 | Contrast passes on every text and non-text indicator, including in high contrast mode. | 4 | **Re-measured from scratch in Round 4, because a palette swap is exactly how measured contrast gets silently undone.** The tone under every marker is hit-tested against the ground SVG's own paint list. Normal contrast, for estimated dashed outline &middot; scanned body rim &middot; owner body fill &mdash; **modal ground tone 4.55 / 13.42 / 4.83**, **worst tone anywhere 4.45 / 13.13 / 4.73**, and **receded to 80%** by a selection or a needs profile, **3.27 / 8.03 / 3.63** modal and **3.23 / 7.93 / 3.57** worst. High contrast: **11.70 / 17.83 / 6.42** modal, **9.20 / 14.02 / 5.05** worst, **6.47 / 9.68 / 4.41** and **5.51 / 8.23 / 3.70** receded. The two match halos measure with the marks they share a colour with (good = indigo900, partial = violet600). All 24 figures clear 3:1, and **22 of the 24 are better than the Round 3 figure they replace** &mdash; Round 3's worst tone was 4.14 / 4.37 / 4.15 and receded 3.08 / 3.13 / 3.02, so every worst-case and every receded figure improved, in both contrast modes. The two that did NOT improve are the estimated outline and the owner fill on the MODAL tone in normal contrast: 4.55 against Round 3's 4.74, and 4.83 against 5.35. Both are the cost of taking the library's colours (sky700 is slightly lighter than the retired #2C63C9, violet600 slightly lighter than #7053C5); both remain over 3:1 by a wide margin, and both buy a better floor where it actually binds, which is the worst tone and the receded state. Text: measured over all 26 screens in four modes &mdash; normal, high contrast, and each at the largest text setting &mdash; **0 failures in all four**, minimum non-large ratio **6.42:1**, which is white on logo violet, the exact pairing and the exact ratio the library's own report signs off for bold control labels. The only value the round had to raise was the marigold button label: at #5F371B it measured 6.21:1 on marigold400, and it is now #533021 at 7.02:1. Focus rings, read from the CSSOM because `:focus-visible` cannot be forced from script: violet600 on its white halo 6.42:1, lavender100 on its indigo900 halo 15.66:1, sky400 on indigo900 in the new dark chrome 8.33:1, and in high contrast #0E0A25 on white 19.29:1 and white on #0E0A25 19.29:1. | **ROUND 7.** Re-measured from scratch after the palette swap, because that is exactly how measured contrast gets silently undone. Two sweeps of the running page, both across all 26 screens in all four modes (standard/high-contrast x default/larger). The visible-ink sweep walked every rendered text node and composited each background up the ancestor chain: **1,303 samples, 0 below 7:1, minimum 7.38:1**. The static sweep did the same for every text-holding element in the document whether rendered or not, and was repeated at the end of the round: **1,012 and then 1,464 samples (the count varies with how much of the app has been visited), 0 below 7:1 both times, minimum 7.38:1**. Non-text: `--edge` is re-solved as the lightest step off indigo900 that clears 3:1 on white, on lavender100 and on **every tone the map-kit ground paints**, the binding constraint being the kit's own block edge `#CFBCEE` at 3.02:1; on white it is 5.25:1. The full pin table is under 3.9. **Round 8:** The new Estimated mark re-measured on every tone the ground actually paints (read from the live `#map-ground`, not from the token file), in both modes. Outline sky700 `#1B6599` vs land `#F5F2FC` **5.64**, block `#E8E1F7` **4.91**, block edge `#CFBCEE` **3.59**, place accent `#76BCFD` **3.08**, white road **6.24**, own white fill **6.24**. High contrast swaps `--blue-edge` to `#1C3D6F`: **9.76 / 8.50 / 6.21 / 5.33 / 10.79**, own fill **10.79**. Floor **3.08:1**, above the 3:1 non-text minimum on every ground in both modes, and unchanged from the mark it replaces because only the geometry moved. The match-legend's "not yet seen" swatch was dotted sky400 (1.83:1 on the legend's white) and is now dotted `--match-unknown` sky700, **6.24:1**, the same token as the halo it keys.
| 3.5 | Colour is never the only carrier of state. | 4 | Tiers carry shape, match carries text. **Round 8:** Re-checked after the confidence dots came off the pins. Tier is shape + fill (teardrop/white/doorway, teardrop/marigold/camera, teardrop/violet/storefront + tick badge); match is halo LINE STYLE plus words in the legend and in every pin's accessible name; confidence is a word ("Confidence high / medium / low") in `placeSentence()` and dots + a word on the card. Nothing added this round is carried by hue. |
| 3.6 | The wordmark is always two-tone and matches the approved logo &mdash; "entrymap in the top right is not the correct with the light blue and white" &mdash; and the bottom bar carries the logo's palette, "dark blue and light blue and yellow", not purple on purple. | 4 | **Closed in Round 4, and the reason it could not close before is now clear.** Rounds 1-3 rendered the wordmark as two coloured `<span>`s and had to invent an on-light pairing, because on a WHITE pill the logo's light blue is unavailable at any legible ratio. Board 02 shows why that was the wrong problem: the map header on the approved boards is not a white pill, it is a solid indigo900 bar, and the wordmark on it is the on-dark variant &mdash; light blue "entry", white "map". Round 4 ships the board. **The wordmark is the library asset** (`asset-library/svg/brand/wordmark-on-dark.svg`, path and text data verbatim, background rect dropped because here the real surface is behind it, `textLength` added so the lockup cannot overflow if Nunito Sans has not loaded) at all three sites the owner named: splash, welcome and the map header. **The chrome is the board's**: `.apphead` is a full-width indigo900 bar and `.navbar` is the same indigo900. **The bottom bar is now literally "dark blue and light blue and yellow"** &mdash; indigo900 ground, sky400 on the active Map tab (8.33:1, the pairing the library's report approves), marigold400 on the Scan ring, lavender200 on the inactive labels (13.33:1), and active state still carried by the rule above the tab and by the weight, so the 1.05:1 hue-only problem does not return. The light blue also reaches LIGHT chrome, where before Round 4 there was no correct answer and now there is one: sky700 #1266A6, the library's own on-light sky, on the Estimated tier throughout and on every informational cue. Two side effects worth naming: the status bar now follows the chrome (`data-chrome`), which incidentally fixed a live defect &mdash; on the welcome and capture screens it was painting `--ink` on a dark ground; and the pushed-screen title rows (`.flowhead`) are deliberately NOT converted, because they sit inside the scrolling body and making them a fixed dark bar is layout surgery this round did not need. That is the one remaining gap between the build and the boards, and it is named rather than hidden. **Round 5 corrects the mark itself, and that correction matters more than the wordmark did.** Round 4 adopted `asset-library/svg/brand/mark-primary.svg` on the reasonable assumption that the library's own file was canonical. Measured against `board-refs/entrymap-assets/07-entrymap-approved-logo.png` &mdash; the artwork actually approved, shipped in the same package &mdash; that asset is a degraded reproduction of it: it drops the WHITE DISC behind the doorway and draws the MIDDLE ARC in violet600, the same violet as the pin body the arc sits on, so the arc is invisible and the mark shows ONE colour above the entry instead of three. Its PNG exports carry the identical defect. That is the product owner's complaint, "I can't see the 3 colors above the entry", and it was a property of the asset rather than of our reproduction of it. `design/logo-mark.png` &mdash; the mark cropped from the approved artwork with the background keyed out, resampled to 320px and quantised to 32 colours, 5.8 kB &mdash; is embedded as a data URI and is now what every display-size site draws: splash (104px), welcome lockup, map header lockup. Verified by eye against the approved logo at 3x: sky blue, WHITE and marigold are all three visible above the entry, on a white disc, over the violet doorway and its lavender threshold. **No hand-drawn copy of the mark survives in the file**, so nothing is left that can drift from the approved art. The wordmark pairing, the chrome and the bottom bar are unchanged from Round 4 and re-verified. |
| 3.7 | The map ground has depth and uses more of the icon colours: "use more of the icon colors within the map and the map is so flat." Saturation, not hue &mdash; a marker is always the most saturated thing in its own radius. | 4 | Round 3 built it, as the recommended combination: **Terrain's colour on Relief's light**. All four sources of depth are in the app, not just the rule. **Road hierarchy:** Congress, Guadalupe, Lavaca and Cesar Chavez primary at 16px, the numbered cross streets secondary at 11px, Colorado minor at 8px, four service alleys at 4.5px, each street casinged so it reads as a channel carved into the block rather than a white stripe laid over it; the three unlabelled arterials got their labels. **Block variety:** footprints split from the block, gapped by a 1.1px party wall, in five tones. **Implied light:** one direction for the whole map, as Relief's two-step cast shadow plus a lit top-and-left edge on every footprint, with the tonal ramp keyed to footprint **mass** so the variation reads as buildings of different sizes rather than as noise. **Landcover:** a grove, kerbside tree bands, courtyard clumps and marigold plazas as real areas. The colour answer is Terrain's: warm sand ground, sage canopy, marigold plazas, cool lavender towers standing among warm putty low-rise. Measured: **1,711 shapes from 15 ground tones** where the old ground drew 128 from 4. The saturation rule is enforced rather than described &mdash; no ground tone exceeds chroma 43 against the least saturated marker's 95, no ground element is ever a lone disc, and any canopy lobe within 26px of a full pin is dropped before it is emitted. Contrast re-measured against every tone a marker can land on: see 3.4. **Round 4 (asset library):** the ground survived the palette swap and is now **derived from the official palette rather than sitting beside it**. The library ships no map-ground tokens, so each of the 17 tones is re-solved as a two-step mix &mdash; an official base carried toward white (which sets chroma) then toward indigo900 (which sets lightness) &mdash; targeting the Round 3 tone's exact CIE lightness and chroma. Bases: marigold400 for the sand, putty and plaza family; lavender200 for the cool towers; and, for the canopy, a 50/50 marigold400 + sky400 mix, because the approved palette contains no green and those are the only two official hues that make one. The honest finding is that Round 3's warm family was ALREADY on the marigold hue line at very low chroma, so eight of the seventeen tones came back byte-identical and the rest moved by one or two steps of 255. The saturation rule is restated against the new markers: the loudest ground tone is the plaza at CIE chroma 16.3 while the least saturated marker colour is now sky700 at 40.9, a ratio of 0.40 against Round 3's 0.45. The luminance floor moved in our favour: sky700 needs 0.4715 where #2C63C9 needed 0.4789, and the darkest tone drawn anywhere is 0.7235. **Round 6:** **lowered from 4, on measurement rather than opinion.** The ground Round 3 built is internally excellent and aimed at the wrong target: the board's map is near-white with a faint blue-violet cast (`#F9F9FC` / `#FAF9FC` sampled from panel 1, ~85% of pixels in a cool near-white band) and the build's is warm cream (`#EFE8DA` ground, `#E5DCCF` shading, `#F8EACC` plazas), several steps darker and noticeably yellow. Everything structural in the 4 above still holds &mdash; road hierarchy, implied light, landcover as areas, block-to-block variety &mdash; and only the temperature and the value range are wrong. **Deliberately not hand-tuned this round.** The incoming handoff package ships a `map-kit` with a pale-lavender land base and high-contrast streets as usable layers; re-solving fifteen ground tones by hand now, days before that arrives, is how a sixteenth ground gets invented. The rebuild is the kit's job, with the pin contrast table re-measured against it (a near-white ground raises the contrast floor for the estimated pin's outline, which is the one marker with no halo, so Round 4's table does not carry over). | **ROUND 7.** Raised from Round 6's self-lowered **3**. Round 6 declined to hand-tune this surface a fourth time and left it for the kit, correctly. The ground is now emitted from the map kit's layer stack &mdash; land, blocks, roads, places, labels, in the kit's order, on the kit's values &mdash; and the warm sand `#EFE8DA` is gone. It uses the icon colours the line asks for: the tree canopy is the kit's `places` layer, sky400 at .34, which is the "white and blue" the owner named; the road casing and the block edge are lavender-path `#CFBCEE`; the land carries the kit's violet600 dot pattern at .045. Saturation still separates marker from ground: the most saturated ground paint is sky400 at 34% over lavender, while the least saturated marker ink is sky700 at full strength. Depth is now the kit's: flat blocks with an edge, roads carved as casing-under-fill, and footprints as outlines only &mdash; no cast shadows, no lit edges, no marigold plaza, because the kit's blocks layer has none of those and the board shows none of them either.
| 3.8 | "Make sure the palettes and styles match throughout." One palette and one set of component styles on every screen, not a per-screen dialect. | 4 | Round 3. The four systems this line was waiting on all landed &mdash; spacing (2.2, now 4), grouping (2.3, now 4), elevation (3.3, now 4) and radius (23 distinct values to one five-step ladder) &mdash; and the score is the floor of what it audits, so it moves with them. Beyond those, a deliberate sweep of all 26 screens, done by inventorying every declaration in the stylesheet by property and by selector rather than by looking at screens, found and fixed **twenty distinct classes of "the same thing drawn two ways"**: 24 shadows, 23 radii, 6 border widths for one control edge, 3 hairline colours plus a fourth undeclared grey `#D8CCF3`, 4 alphas of translucent white across 12 floating surfaces, 6 row heights, an undeclared quiet fill `#F8F7FD` at 5 sites, a fourth ink `#6C6486` on the chevrons, a literal `#4A4463` on the diff arrow, a literal `#2A1A5E` progress rim, 6 treatments of a quiet note, 3 treatments of a quoted note, 5 press scales and 2 ad-hoc press washes, two docked-sheet top radii, two legends at two radii, two pills written as pixel radii, three privacy rungs carrying an inline icon box instead of `--icon-box`, a form control wearing the floating map shadow, 40 spacing values, and 19 durations with 7 easings. The estimated-tier blue was the sharpest find: two committed files specified different hexes and the shipped teardrop's token disagreed with its own inline fallback (3.1). **Round 4 (asset library):** this is the line the round was called for, and it is the strongest evidence it has had. The build's palette was an approximation of the logo assembled by hand; it is now the approved library, with **eleven authored colours** and everything else derived from them by a stated rule. What moved: 100 source lines of legacy hex swept onto the official palette; `--teal-ink`, `--match-green`, `--match-ink`, `--match-wash`, `--brand-amber`, `--street`, `--block` and `--tree` retired; `--amber-ink` and `--marigold-ink` collapsed into one colour (they were #6B4F00 and #6E4A00 &mdash; two names for one hue); every shadow `rgba` re-based from the retired #241F3A onto indigo900; the desktop stage behind the phone, which was three greys, re-derived onto lavender. **Thirty icon names are now the library's own drawings** and the twenty-seven that stay are the ones it has no equivalent for, re-expressed on the library's 32 grid so both families paint at the same 2.3 stroke (5.4). The three pins, the three match halos, the tier badges, the confidence dots, the freshness pill, the five provenance marks, the Texas record and the brand marks are the library's assets. The two remaining deviations from the boards are named, not hidden: the pushed-screen title rows are still light (3.6), and the six state illustrations stay ours (5.1, 5.2). **Round 6:** two more dialects closed. **Two lavender families, not one:** the handoff package distinguishes "UI lavender" (a surface accent) from "lavender path" (the map pin's base), and one family was serving both, so a palette swap could only move them together. They are separated by role &mdash; `--ui-lavender-1/2` and `--lavender-path` &mdash; with both still pointing at the current official values, so each is a one-line swap when the package lands and the two can no longer be conflated. Nothing below the token block reaches past those names into `lavender100/200`. **One veil, not two:** the file carried a 42% modal scrim and a separate 7% card veil. Both read `--veil` now, at the interaction spec's 7%, and the card's veil is bound to the full stop only &mdash; measured opacity 0 at peek, 0 at medium, 1 at full. **One touch target:** 48px, written once as `--tap` where ~60 literal `44px` values used to be. Components were re-measured rather than assumed: the graphic critique counted five tier-badge treatments, three feature-chip layouts and four header patterns, and driving all 26 screens and all seven sheets and comparing computed background, border, radius, padding, size and weight finds **one** `.tierchip` component with two rendered fills (filled marigold for Scanned, hollow dashed sky for Estimated, which the pin hierarchy requires), **one** `.fchip` layout across 7 instances, and **one** `.flowhead` across 12 screens beside the map's `.apphead`. Those counts were fixed by Rounds 4 and 5; the critique's numbers are stale, not wrong when written. | **ROUND 7.** Re-cited alongside 3.1: the canonical library is `board-refs/entrymap-build-ready/asset-library/` and the older `board-refs/entrymap-assets/asset-library/` is **superseded**, including its brand mark. One palette across every screen is now verifiable rather than asserted: after the swap the file contains **zero** occurrences of any of the ten retired values (`#17103D`, `#211054`, `#5B35F5`, `#4020B5`, `#69B7FF`, `#1266A6`, `#FFBF24`, `#9A5700`, `#F2EEFF`, `#E2DAFF`) outside the one comment block that records what moved &mdash; 150 literal occurrences were rewritten, and every remaining derived value in the file was re-solved on the canonical bases rather than left where a retired base put it.
| 3.9 | The map ground is built from the handoff package's `map-kit` layers, not hand-tuned to match them: "the background map and pins are still wrong", "the board in the other one is white and blue". The kit ships the base map, blocks and labels as real SVG on the canonical tokens; a re-derived ground is how the same surface went wrong twice. | 4 | **Round 7 takes the kit.** Verified before use rather than trusted: the `land`..`labels` span is byte-identical across all eight kit variants (sha256 of that 2,027-byte span is `8a37232b1a052240` in every one), and all eight files match the sha256 recorded for them in `PACKAGE-MANIFEST.json`. *A real inconsistency inside the package, found while checking, and corrected on re-measurement:* `map-kit/map-kit-manifest.json` carries **one** sha256 per variant, and it is the PNG's (8 of 8 match the PNG bytes, 0 of 8 the SVG); the field names two files and hashes one, because `render-map-kit.ps1` overwrites it from the rendered PNG. Nothing is stale &mdash; the earlier reading of `base-map.svg` as `A26EEC8E...` was the PNG's hash. The top-level manifest matches all sixteen files. Recorded in `design/package-defects.md`. Values taken from `base-map.svg` and now in `:root`: land `#F5F2FC` plus a violet600 dot pattern at .045 on an 18px grid (6px at CSS scale), blocks `#E8E1F7` with a `#CFBCEE` stroke at 3/1170 (1 CSS px), roads `#CFBCEE` at .55 and width 62 **under** white at width 48 (so the casing is now the kit's 62/48 ratio, not a hand-picked kerb), places `#76BCFD` at .34, labels `#1E1142` at weight 700. **Where the kit is silent, this file says so rather than inventing:** the kit has no street hierarchy (its four roads are one width), no building footprints, no plaza, no courtyard, no high-contrast variant and no answer for pan or zoom. The footprints are kept as outline-only strokes because the approved board shows them (`screen-exports/png/map-default.png`) while the kit does not; high contrast stays Round 6's simplification, re-toned onto the canonical lavenders. **One stated deviation:** the kit's label size is 24/1170, i.e. 8 CSS px, which is below this file's `--fs-micro` floor of 10.5px and below what the package's own checklist can accept at 200%; the size stays 10.5px and everything else about the label &mdash; ink, weight, tracking, casing halo, width-and-opacity hierarchy &mdash; is the kit's. **The cluster and the selection keyline came from the kit too:** `mixed-cluster.svg` draws an indigo900 disc with a white ring and a white count and the arcs inside it, where the build drew a white disc with an indigo rim and the arcs outside; `selected-business.svg` nests the selection ring **outside** the match halo at 2.15x and 2.37x the head radius, where the build nested it inside. Both are restated to the kit. **One place the kit is wrong and the artwork is trusted instead:** `asset-library/svg/pins/estimated.svg` draws the Estimated outline in sky400 `#76BCFD`, which measures 1.83:1 on the kit's own land, 1.36:1 on its darkest filled tone and **2.02:1 against the pin's own white fill** &mdash; the mark would have no discernible boundary anywhere, which the package's own checklist forbids. The approved board draws that outline in a fully saturated blue (sampled `#0033F5` off `map-default.png`, 5.86:1 on the land). The board is trusted; the token used is sky700 `#1B6599`, which is dark like the board's, is in the canonical twelve, and is what the same asset already uses for its italic i and its confidence-dot strokes. **The pin table, re-measured against the kit ground in both contrast modes** (each mark against the tone it is drawn on; modal tone is the land, worst filled tone is the place accent over a block, worst tone of any kind is the 1px block edge): Estimated outline sky700 &mdash; land **5.64**, blocks 4.91, casing-on-block 4.15, place-on-block **4.19**, block edge **3.59**, road 6.24, and 6.24 against its own white fill. Scanned rim indigo900 &mdash; land 15.64, worst filled 11.62, block edge 9.95, and 9.60 against its own marigold fill. Owner fill violet600 &mdash; land 6.67, worst filled 4.95, block edge 4.24, white rim on it 7.38. Cluster disc indigo900 &mdash; 15.64 / 11.62 / 9.95. Match halos &mdash; good indigo900 15.64 land, partial violet600 6.67, unknown sky700 5.64. Selected keyline indigo900 15.64. Every boundary-carrying mark clears 3:1 on every tone the ground paints, including the worst. In high contrast the ground is white land, white blocks with an indigo900 hairline and lavender200 roads: Estimated outline 10.79 on the field, Scanned rim 17.30, Owner fill 7.38, unknown halo 6.24 &mdash; the only sub-3 figures are marks sitting on the 1px indigo hairline itself, which is a line beside the mark and not the mark's field. |
| 3.10 | `lavender-path` and the UI lavenders are separate roles and are never one family. The pin base is `#CFBCEE`; the UI surfaces are `#F5F2FC` and `#E8E1F7`; the default screen body is neither. Conflating them is the mechanism of "so many of the pop ups are purple still?", not a symptom of it. | 4 | **Round 7 makes it a structural rule, not a comment.** Round 6 separated the names but pointed all three at the same two values, so a swap could still merge them. Now there are **three authored lavenders with three disjoint jobs**: `--lavender-path #CFBCEE` is MAP ONLY (block edge, road casing, and the soft needs-match disc under a pin), `--ui-lavender-1 #F5F2FC` is UI ONLY (accent wash) and `--ui-lavender-2 #E8E1F7` is UI ONLY (accent stroke). Counted in the source: **3** uses of `--lavender-path`, all three in map paint; **5** of `--ui-lavender-1` and **8** of `--ui-lavender-2`, none of them in map paint; and **0** UI rules reaching past the roles into the raw tokens &mdash; the four that still did (`#nav-profile.on`, the two `.seg`-family rules, and the high-contrast `--ground` and `--match-wash`) were routed through the roles this round. The only two rules in the file that name a raw lavender are `--g-land` and `--g-block`, because the kit names exactly those two values for the ground and nothing should sit between the kit and the paint. Cross-checked both ways: **no pin colour is used as a surface and no surface colour as a pin** &mdash; `--lavender-path` never reaches a card, sheet, chip or body, and neither UI lavender reaches `groundSVG` or `pinSVG`. The default screen body is `--white`, which is a third thing again. A future palette adoption swaps three values and cannot silently re-merge the families. |

## 4. Motion

| # | Criterion | Score | Evidence |
|---|---|---|---|
| 4.1 | Motion explains a relationship: where a thing came from, where it went. | 4 | Round 3. Fifteen of the 26 screens cut outright and the other eleven fade-rose 8px with no direction. Screens now **push and pop by direction** &mdash; `screen-fwd` +12px, `screen-back` -12px, `screen-lat` a plain fade, 12px being the smallest travel at which direction is legible &mdash; and the direction is written by the three navigation functions that already knew it. Verified: `data-dir` reads `fwd` after `goScreen`, `back` after `goBack`, `lat` after a bottom-nav tab. The trust popup **grows from the control that opened it** instead of scaling from the screen centre, which said nothing: with the legend focused, `--pop-x` / `--pop-y` measure **20.2% / -61.7%**, which is the legend's centre expressed in the popup's own coordinate space (read from `offsetLeft`/`offsetTop`, because `transform-origin` percentages are against the untransformed box). The list **rises 8px and settles**, because it is the map's content re-presented rather than a different place, and it still leaves the accessibility tree when closed. An active-filter chip **arrives** with `chipIn` on first appearance (measured: class `achip arriving`, animation `chipIn`, 220ms) and does not re-animate on later re-renders; on removal it runs the reverse before the DOM removal. The map pan now travels on the sheet's own clock, so the selected pin visibly steps aside for the card instead of teleporting. **Round 5 gives the transition its other half.** Round 4 animated only the ARRIVING screen and swapped the departing one on `display`, so the spec's "current screen moves 12 px left and fades to 88% opacity" did not exist at all, and the 88% it names for the outgoing screen had been applied to the incoming one instead. The departing screen is now held under `.screen-out` for exactly one transition and given its own exit; back reverses it exactly &mdash; measured mid-flight going back, `translateX(+8.79px)` heading to +12 and `opacity 0.912` heading to .88, the mirror of forward. Peer navigation gained the specified 8px upward settle. The class is `.screen-out`, not `.leaving`, because three other things in this file already own `.leaving` for their own exits and a generic screen rule on that class would have silently overwritten them. |
| 4.2 | Durations are consistent and short: roughly 150-250ms for UI, longer only for narrative beats. | 4 | Round 3. **Nineteen distinct durations become two**: `--dur-fast` 160ms for feedback and in-place state change, `--dur-base` 220ms for anything that travels. Both sit inside the criterion's band. Four narrative constants are named and scoped to the scan sequence, which criterion 4.4 already scores 4 and this round did not re-time (`--dur-settle` 900, `--dur-check` 1500, `--dur-drop` 700, `--dur-ripple` 1000). Counted in the committed CSS, the only time values that remain are those six, `0s` &times;6 (the sheets' visibility guards), `.01ms` &times;4 (the two reduced-motion kill-switches) and three progress durations the criterion exempts. Sheets are **220ms in and 160ms out** &mdash; a sheet leaves faster than it arrives, which is what makes a dismissal feel obedient rather than sluggish, and the visibility guard's delay tracks the duration it is paired with. **Round 5 re-times against the approved specification, and the trade is deliberate.** The two-duration consolidation was real work and this line scored it a 4, but the conformance audit asked a different question &mdash; not "is this a coherent system?" but "is it THIS system?" &mdash; and every number was close and nominated by us. Nine durations now, each a figure the spec states: press 100, focus 120, fast 160, peer/release 180, base 220, receipt 240, screen 260, sheet snap 320, map camera 450, plus the four narrative constants (settle 900, check 1500, drop 620, ripple 520). Every ordinary-feedback value sits inside the spec's own 90&ndash;320ms band; the two above this line's 250ms are the sheet snap at the top of that band and the map camera, which the spec calls a "geographic ease" and which at 220ms read as a jump rather than a camera. Press was `transition:none` &mdash; 0ms, a snap rather than a press &mdash; and is now 100ms on the exit curve; release was 160ms on a curve with no overshoot and is now 180ms on the one curve in the file that overshoots. Measured on the running page: `--dur-drop` 620ms, `--dur-ripple` 520ms, chip stagger 0/60/120ms (was 0/220/440), shutter to review 7.11s against a ~7.6s target and an 8s ceiling. |
| 4.3 | Easing is consistent and physical; nothing linear except progress. | 4 | Round 3. Seven easings &mdash; two general-purpose curves doing the same job, two near-identical overshoots at 1.2 and 1.15, plus `ease-out`, `ease-in` and `linear` &mdash; become **two curves plus one scoped spring**: `--ease-enter` for arriving and settling, `--ease-exit` for leaving, and `--ease-spring` on `dropIn` and `pinTap` only, which is where the canon asks for overshoot. Counted in the committed CSS: exactly **three** `cubic-bezier` values, **zero** `ease-out`, **zero** `ease-in`, and **four** `linear` &mdash; the two progress arcs' `stroke-dashoffset` and the two progress bars' `width`, which is the criterion's own exemption. **Round 5** adds the spec's two named curves &mdash; `cubic-bezier(.2,.75,.25,1)` for screen transitions, `cubic-bezier(.22,.9,.28,1.08)` for the sheet snap and the button release &mdash; and moves `--ease-spring` onto the token file's `cubic-bezier(.2,.9,.25,1.2)`, one control point from where it was. Five curves, all named, none duplicated in role; `linear` still on progress only. |
| 4.4 | The processing sequence is the one deliberate narrative moment and it earns its length. | 4 | The self-drawing ring with named checks. |
| 4.5 | Reduced motion removes animation without removing meaning or feedback. | 4 | Re-verified in Round 3 after the motion system landed, and the rule that protects it is now structural rather than a habit: **no deferred step anywhere uses `transitionend` or `animationend`**, because at the 0.01ms duration the kill-switch imposes those events can fire before a listener attaches and leave an element stuck. A `defer(ms, fn)` helper collapses the wait to 0 under reduced motion and is deliberately *not* the existing `after()`, whose timers live on `scanTimers` and would be cancelled by a nav action &mdash; which would have left the list view hidden-but-focusable. With Reduce motion on: sheet and chip transition durations read `1e-05s`, `#ringwrap` is `display:none`, the determinate bar is visible at 100%, all three checks land, the checklist text agrees, and the flow completes to Review. Every `:active` press survives, because a `transition:none` press has no duration to zero. *Round 2 evidence:* re-verified in Round 2 after the pin animations were rewritten for the new anchor: with Reduce motion on, `#ringwrap` is `display:none`, checkitem transition is 1e-05s, the determinate bar reads 100%, all three checks land, the live region still says "Checks complete. 3 features identified.", and the checklist text agrees ("Doorway framed &mdash; done"). The flow completes to Review. **Round 4 (asset library):** re-verified: the in-app Reduce motion toggle still puts `.rm` on the phone and the screen-change animation computes to `none`; no animation was added this round. **Round 5 re-scores this honestly and then earns it back.** The conformance audit's verdict was exact: Round 4's implementation was two identical blanket rules setting every animation and transition to `0.01ms`, which is shortening rather than replacement, and nothing was left mid-flight only because eight of the eleven keyframes happened to declare a fill mode &mdash; add one keyframe with no fill whose start state is not its resting state and it breaks silently with no test to catch it. Three of the spec's positive requirements were also unmet by a blanket: "screen transitions become instant crossfades no longer than 80 ms" became no crossfade at all, and `animation-iteration-count:1 !important` silently capped any future indeterminate indicator at one pass, which is a correctness bug rather than a motion preference. The two cases are now split, because they are not the same problem. **Transitions** keep one blanket at `0s`, sound by construction: a transition's end state IS the element's computed style. **Animations** are replaced one at a time &mdash; every keyframe in the file is named and given an explicit answer, either `none` with its resting state asserted, or a different presentation: screen changes get a real 80ms `rm-fade` crossfade, the pin appears with no drop and no ripple, chips and settles are simply there. The iteration-count override is gone. And there is now ONE copy of the answer: `applyPrefs()` sets `.rm` from `isReduced()`, which is `RM_MEDIA.matches || rmPref`, so the operating-system setting and the in-app toggle reach the same rules through the same class and cannot diverge. Measured with the toggle on: `.rm` present, screen body `rm-fade 0.08s`, button and sheet transitions `0s`, **zero** `.screen-out` elements created at all, and the full scan flow completes to Review with **zero** unfinished animations. **Round 6:** **the mechanism this line depended on is gone, replaced rather than patched.** The rule above protected deferred steps from `transitionend` by using timers instead &mdash; but a timer is a GUESS about when an element becomes usable, and the guess is what broke. Reduced motion zeroed `transition-duration` and never touched `transition-delay`, while `.sheet` and `.popup` write their stale-transform guard AS a delay (`visibility 0s var(--dur-fast)`); with a near-zero duration the sheet stayed `visibility:hidden` past the fixed 40ms focus timer, `focus()` on a hidden element is a silent no-op, and nothing retried. Measured with the pre-Round-5 `.01ms` value re-injected: sheet visibility `hidden` at 40ms and at 353ms, focus on `<body>`, every time. Round 5's move from `.01ms` to `0s` makes the browser skip the transition and accidentally fixes the trigger &mdash; luck, one edit from returning. Both halves are closed now: the reduced-motion block zeroes `transition-delay` and `animation-delay` as well, and every deferred focus waits on READINESS &mdash; `focusWhenReady()` asks whether the element is laid out and unhidden, focuses, verifies focus landed, retries on animation frames for up to a second, re-tests on every frame whether the app has navigated, and falls back to the labelled container, which always takes focus. Measured, 12 sheet opens per condition, driven by real pointer sequences: **0/12 land on `<body>` with Reduce Motion off, 0/12 with it on, and 0/12 in both settings with the `.01ms` regression re-injected.** Held to a harder case than the real one: with the sheet forced to stay hidden for 500ms, focus lands the frame it becomes visible instead of never. **Round 8:** **Two places where the setting was still deleting information rather than motion, both measured on the live build.** (1) The processing screen: reduced motion called `finish()` synchronously, so the whole check ran in **4.9ms** with all three checks landing in the same frame, against **7,419ms** and 2,510.8 / 4,009.6 / 5,442.0ms with motion. It now runs the same cadence on timers &mdash; measured after: **2,504.9 / 4,006.5 / 5,505.7ms**, review at **7,111.5ms** &mdash; and drops only the sweep (the ring is already `display:none` under `.scanscreen.reduced`), the settle scale and the rotation. (2) The `PROC_CHIPS+600` hold, whose own comment says it exists so "Checks complete" is spoken before the screen changes, was skipped under reduce: the announcement landed **27.8ms AFTER** the review screen was active. It now lands **1,577.5ms BEFORE** it (motion mode: 1,878.5ms before). (3) The capture coach rotated forever in both modes &mdash; measured **4 changes in 7.2s** with reduced motion on. It is now replaced, not shortened: all four lines shown statically, **0 changes in 9s**, no interval started. |
| 4.6 | Nothing animates on load that the user did not ask for. | 3 | Held at 3, and defended rather than left alone. The screen-push animation added this round could easily have become a second load animation, so the map body and the splash body are both excluded by rule (`#screen-map .screen-body, #ob-splash .ob-body{animation:none}`) and the splash keeps its own `splashIn` / `splashOut` pair. Measured on a cold load: **zero** elements inside the active screen have a running animation once the splash has left. It stays a 3 because the splash still animates on load without being asked, which is the criterion as written. |

## 5. Craft details

| # | Criterion | Score | Evidence |
|---|---|---|---|
| 5.1 | Empty states say what to do, not that something is empty. | 4 | Round 2. The copy was already right; the drawing was missing. The saved-list empty state now opens on the "empty shelf" illustration above "No saved entrances yet &mdash; save an entrance from its card and we'll tell you when its information changes", and the map-empty invite opens on the street scene above "No entrances mapped here yet / Be the first to help neighbors plan ahead", with a marigold **Scan an entrance** beside an outlined **Try another area**. Neither says a place or a person failed. **Round 4 (asset library):** the library's six state assets were read and deliberately **not** adopted, and the reason is a measurement rather than a preference: each bakes its headline at 17px and its sub-copy at 12px into the SVG, which cannot move with the text-size setting and would fail 7.11, cannot be announced, and would duplicate the HTML copy the screens already carry; each also draws its own card frame, doubling the card the screen already draws. Their artwork content is a lavender disc with one small glyph, which is a simpler thing than the seven drawings this line scores. What the library DID change here is the palette they are drawn in &mdash; every colour in all seven is now an official token &mdash; and the pins that appear inside them, which are the library's. |
| 5.2 | Loading, offline and permission-denied states are designed, not default. | 4 | Round 2. All three states screen cards carry their own finished drawing at one size (offline storefront with a cloud, camera, map), replacing three 52px glyph discs; the scan primer opens on the storefront doorway; the correction-submitted screen opens on the note-and-tick drawing. Every one is drawn from tokens, so it re-tints itself in high contrast rather than being redrawn. **Round 4 (asset library):** same call as 5.1 for the permission, processing, offline and published states: the artwork stays ours because the library's bakes 12px copy into the SVG; the palette is now official. |
| 5.3 | Touch feedback on every interactive element. | 4 | Round 3. **Two treatments, chosen by shape rather than by importance.** Compact controls (buttons, chips, pills, circular controls) scale to `.97`; full-width rows take a wash, because scaling a row that spans the screen looks like a rendering fault, and rows sitting on the lavender ground use a darker wash so the press is visible from a non-white start. Press-down is instantaneous and the release eases out &mdash; feedback that fades *in* is not feedback. Counted in the committed CSS: **47 components carry `cursor:pointer` or `cursor:grab`, and 44 have an `:active` treatment.** The three that do not are named exceptions: `.pinbtn`, which has `pinTap` &mdash; the canon's squash-and-rise, better feedback than either treatment &mdash; and the two native inputs on the claim screen, which sit inside `.authz` / `.verify-opt` rows that press around them. The eight presses that already existed used five different scale values (.93 / .95 / .97 / .98) and two ad-hoc wash colours; all are normalised, with the 76px shutter (.93) and the 72px scan ring (.95) kept deeper because they are physically larger. **Round 5** adds the fifth state the spec's first table names and the build did not have &mdash; Unavailable &mdash; and puts the spec's numbers on the two the build did have: press 100ms, release 180ms with a real overshoot. See 9.3. |
| 5.4 | Icons share one grid, weight and terminal style. | 4 | **Round 4 moved the grid to the library's.** Thirty names are now the library's own path data verbatim &mdash; 20 UI icons, 8 feature icons, the community provenance mark and the Texas record &mdash; on its 32 grid. The 27 that stay are the ones the library ships no equivalent for and they are named in the source: the map's own controls (list, zoom-in, zoom-out, locate, back), the bare tick that sits inside a filled selection disc (the library has only the OUTLINED check, which is the owner badge and means something else), bookmark, share, upload, external, phone, directions, plus, minus, text-size, the five persona glyphs, the three settings glyphs, lock, bell, sparkle, warning, and handrails. Those 27 are re-expressed on the 32 grid by scaling the 24-grid path 4/3 with `stroke-width:1.725`, which paints at exactly **2.3** &mdash; the library's own UI-icon weight &mdash; so a legacy icon and a library icon are indistinguishable in weight. The library's feature icons ship at 2.2 and are levelled up to 2.3, because this line asks for one weight. Round 4 also found that the library dedupes what we drew twice: `provenance/owner-source` IS `ui-icons/storefront`, `photo-source` IS `photo`, and `public-record` IS `receipt`. |
| 5.5 | Copy is plain, specific and human; no jargon, no cheerfulness the moment does not earn. | 4 | Consistently strong. Unchanged. |
| 5.6 | Nothing is ASCII-fragile: no raw glyph that breaks without the right charset. | 4 | Still **0** non-ASCII bytes outside the base64 payloads, verified by scanning the file with the payloads stripped. Round 4 went further, because the font swap exposed a second failure mode the charset rule does not catch: a glyph that is safely escaped can still have no glyph in the UI face. Measured over all 26 screens, **19 of 402 text nodes fell out of Atkinson Hyperlegible Next into Arial** &mdash; every back button (U+2039), every close button (U+2715), every row chevron (U+203A), the location pill's triangle (U+25BE), the "My needs" heart (U+2665), the processing and timeline ticks (U+2713), and the eight decorative dingbats in `FEATS` (U+2913, U+27CB, U+2562, U+25C9, U+2310, U+21E2, U+267F, U+21D4). All of them are drawings now, from the library where it ships one. Re-measured: **402 of 402 text nodes render in the UI face; 0 fall back.** **Round 5**: three genuine non-ASCII characters still remained &mdash; one U+2039 and two U+2715 inside the `paintStaticIcons` comparisons Round 4 added to replace those very glyphs with drawings. They are escapes now. Re-verified with the base64 payloads stripped: **0** bytes above U+007E anywhere in the file. |
| 5.7 | **Every mark on a pin or in place of a pin is taught where it is seen.** The confidence dots and the cluster count are readable without explanation: "what are the numbers on the map? why do the icons have 3 circles above each of them?" (directive ledger pass 3, draft 5.x) | 3 | **Round 8, first scoring.** Two untaught marks, two different answers. The three confidence dots are **removed** (D38, "the three circles above each icon is stupid"): `pinDots()` is deleted and **0** call sites remain, so no pin at any zoom in any tier draws them, and the information moved to where it is explained &mdash; the card's Confidence tile, and now `placeSentence()`, which did not carry it before (12 of 12 pins say "Confidence high / medium / low"). The numbered disc **stays** and is taught twice: a legend row drawn by the same `pinSVG('cluster')` the map uses, and a rung in "How trust grows" that says it is not a tier and what the number counts. The match halos are keyed too, including the dotted "not yet seen" state, whose legend line previously documented its own absence. **Not a 4, and here is what is left:** the selection keyline (white + indigo rings) and the lavender disc that appears under a matched pin are drawn on the map and keyed nowhere &mdash; the keyline is self-caused so a user can infer it, the lavender disc cannot be inferred. Round 9. |
| 5.8 | **One line style, one meaning.** A dashed stroke means exactly one thing on the map: "the dashes around the estimates and it also meaning partial is confusing." (directive ledger pass 3, draft 5.y) | 3 | **Round 8, first scoring.** On the map the criterion is met and measured: with a needs profile applied, the only broken line styles drawn inside `#map` are `stroke-dasharray="17.9 10.7"` (partial-match halo, 4 instances) and `"1.2 13.1"` (unknown-match halo, 6 instances). The other three dasharrays present (`96.25 2.40`, `63.36 35.28`, `30.48 68.16`) are the cluster mix arcs, which use the property to draw an arc rather than a dash. **0** occurrences of the Estimated pin's old `7 6` outline remain in the file. The halos' own line styles were not touched: solid good, dashed partial, dotted unknown. **Not a 4:** off the map, a dashed border still does double duty. Counted in the stylesheet: **3** declarations where dashed means partial match (`.sw.partial`, `.matchchip.partial`, `.mstat.partial`) and **6** where it means an empty slot (`.nb-thumb.ph`, `.status-chip.photo` and four placeholder boxes). Dotted is clean at 3 for 3, all meaning unknown match. `.tierchip.est` was a tenth &mdash; a dashed sky pill that appears over the map inside the card, justified in its own comment by the pin's dash &mdash; and is now solid. The six placeholder dashes are a Round 9 item; they are a different register, but they are the same line style. |

## 6. Product truth

| # | Criterion | Score | Evidence |
|---|---|---|---|
| 6.1 | No public negative verdict anywhere, in any state. | 4 | Held through the owner surfaces. |
| 6.2 | Every claim shows its evidence and its date. | 4 | Provenance stack. **Round 6:** the 4 was true of the receipt and false of the card. Every scanned place was dated `2026-09-02` and `freshLabel()` returned the string "Seen 2 days ago" for the whole tier without reading the field &mdash; a date that would have said 2 days whatever the data said, on the product whose whole claim is that a line can say where it came from. The label is derived from `p.date` now (`ageDays()` against one named `APP_TODAY`), the pilot sweep is dated across the fortnight it took, and the card, the pin's accessible name and the list all read the same derived value: measured, 2 / 2 / 2 / 2 / 4 / 6 / 11 / 14 / 17 / 21 / 24 days and "Updated today" for the owner. **Demo scaffolding is out of shipped copy:** `(staged for demo)` on the card's primary provenance row, on the owner-attestation receipt line and on the state-record line, and `Open My Business (staged)`. The receipt still names each source and its date; it no longer narrates the demo. **And the claim confirmation stops promising a message it never collected** &mdash; see 7.5. |
| 6.3 | Trust tier is never a filter, and never granted by a source that did not earn it. | 4 | Enforced. |
| 6.4 | Nothing implies measurement or legal compliance. | 4 | Vocabulary holds. |
| 6.5 | The state record is provenance and never a filter: "what about the texas verified? the filter is awkward for that one too." Nobody needs a record; they need a doorway they can use. | 4 | Directive ledger, scored against HEAD. `FILT_FEATS` is exactly `step_free`, `width`, `hardware` &mdash; three needs, no record. The Texas inspection appears in three honest places and nowhere else: a provenance row on the card that opens the receipt, the receipt row that is the one and only site of the flag glyph, and a read-only row on the owner's edit screen ("Owners edit observations, not state records"). It never alters a pin tier and there is no state-records map layer. This satisfies the same rule as 6.3: if a person may not filter to Owner-confirmed, they certainly may not filter to weaker evidence about a different tenant. **The owner asked this at 19:27 on 2026-09-05 and was never told it was already true.** |
| 6.6 | "Nothing is 100% verified, which to me looks bad. How does a person get that?" The map must not read as a product that knows nothing &mdash; without inventing a rung above Owner-confirmed. | 2 | Directive ledger, scored against HEAD. **This directive conflicts with a settled rule and is recorded rather than dropped.** A "100% verified" tier would be a compliance claim from photographs, which 6.4 forbids and which is the whole honesty position; so the literal ask cannot be built. The complaint underneath is fair and has two answers already in hand, neither of which is scheduled in any design round: (1) 11 of 64 places show as Scanned on-site while the operator photographed all 64 &mdash; the map understates itself, and publishing the rest is the owner's own instruction "publish the scan results for all 64 before demo day"; (2) confidence &mdash; agreement between independent sources &mdash; is already on the card as dot-triples and in the overview line "Neighbors and a state record agree", and can say "three sources agree" without a new rung. Score is 2 because the honest ceiling is reachable and not reached. |
| 6.7 | Step-free is answered where it matters, or honestly marked unanswered: "how to fix the step-free problem". It is the criterion people most need and the one street imagery evidences worst. | 3 | Directive ledger, scored against HEAD. The design surface is honest already: a place with no observation reads "Not yet seen &mdash; be the first to scan", a scan that did not see the feature reads "not spotted in this scan", and neither is a negative verdict (6.1). What is missing is coverage, not copy: the two fixes named in visual-language section 13 &mdash; on-site scans, which show the ground plane, and gated monocular depth, which took step-free from 88.5% to 96.2% on held-out entrances &mdash; are engine work with no design round attached. A 4 needs the estimated tier to stop going quiet on the column that matters most. **Correction, 2026-09-05:** the depth figure did not survive confirmation on unread photos (96.2% collapsed to 80%, below vision alone at 86.5%; `eval/out/enhancement-table.md`), so depth is dropped, not pending. Vision alone commits on 52 of 52 held-out entrances with 0 abstains, which is the actual defect. The product owner chose to add `step_free_entry` to the engine **with an abstain path** (frontdoor #368); the engine work is dispatched. |

| 6.8 | The product has **two surfaces and one design system**: "how to get this in the app as well rather than remaining a web view" &rarr; "okay lets do hybrid." Capture, privacy and upload are native; map, card and discovery are native; the web app stays as the no-install route and is not a fallback to be retired. The boundary is written in the design canon, not only on a ticket. | 3 | **Round 7 writes it into the canon.** Before this round, `grep -i "emily\|wliang\|swift\|hybrid"` across `design/*.md` returned nothing; the decision existed only on GitHub #367 and #275 and in conversation, so a reader of the design canon could not tell which surfaces were being designed for what. `design/visual-language.md` now carries a **Surfaces** section recording the native/web split, the rule that a token, asset or motion value changed for one surface is changed for both, and a pointer to #367 for the detail. **Held at 3, not 4, and the reason is outside design's reach:** the Swift design-system PR carries the superseded palette on all ten values that moved, it was flagged on the PR rather than ticketed, and the correction still has no ticket and no owner. One design system across two surfaces is written down but not yet true in the other surface's code. |

## 7. Accessibility behaviour

This product is for disabled people. A defect here is a product defect, not a checklist miss.
Content accessibility and behavioural accessibility are scored separately because this file
is strong at the first and weak at the second.

All Round 1 evidence below was measured in the browser at 390x844, served over
`python -m http.server`, on the working copy as committed.

| # | Criterion | Score | Evidence |
|---|---|---|---|
| 7.1 | Text contrast passes everywhere, in both normal and high contrast. | 4 | Unchanged and not regressed. The decorative glyphs that were the only failures (`>`, `->`, the transparent tick) are now `aria-hidden`, and the two that stay visible were raised from 2.62:1 to 4.6:1. Checklist pending text went 2.47:1 -> 6.34:1 (`--faint` on the ground). **Round 4 (asset library):** re-measured after the palette swap, over all 26 screens in four modes (normal, high contrast, and each at the largest text setting): **0 failures in every mode**. Minimum non-large ratio **6.42:1** in all four, which is white on logo violet &mdash; the library's own approved pairing for bold control labels, at the library's own ratio. Only two pairings in the whole build sit under the library's 7:1 body-text bar and both are control labels rather than body copy; every text ink the build uses for reading (`--ink`, `--sub`, `--faint`, `--blue-ink`, `--marigold-ink`, `--purple-ink`) was derived against a 7:1 target on lavender100 and measures 8.00 / 8.00 / 7.05 / 7.03 / 7.01 / 8.82. | **ROUND 7.** Re-measured on the canonical palette and **the 7:1 target is now met everywhere**, which it was not before. The six reading inks this line last quoted were solved against lavender100 alone; they are re-solved against every light surface a reading ink can land on in this file (white, lavender100, `--wash-quiet`, `--press-wash`, lavender200, `--blue-wash`, `--marigold-wash`), and the figures quoted are now the WORST of the seven, not the best: `--sub` **8.02**, `--faint` **7.01**, `--blue-ink` **7.01**, `--marigold-ink` **7.00**, `--purple-ink` **8.79**, `--ink` **13.63**. The two control labels that used to sit under 7:1 are gone: white on the primary violet was 6.42:1 at 20 sites and is 7.38:1 at the same 20, and the marigold button label, whose derived ink had been solved on the retired `#FFBF24` and measured 6.43:1 on the canonical `#FDB327`, is now indigo900 at 9.60:1 &mdash; the package's own answer for scan controls. See 7.14.
| 7.2 | Non-text indicators pass 3:1: toggle tracks, form borders, pins against the map, focus rings. | 4 | Every indicator the audit measured now passes in **both** modes. Normal / high contrast: toggle track 3.37 / 6.66, form and chip borders 3.37 / 6.66, dot outlines 3.37 / 6.66, scanned-pin rim 5.04 / 8.04, estimated-pin stroke 3.59 / 8.09, progress track vs ground 3.29 / 3.02, progress-arc rim vs track 3.39 / 3.39, nav current-tab bar 9.62 / 13.25. Four tokens (`--edge`, `--track`, `--marigold-edge`, `--ring-rim`) carry all of it. **Round 4 (asset library):** re-measured. The tokens that carry 1.4.11 were all re-derived from the official palette against their stated targets and all pass: `--edge` #8C889F 3.42:1 on white and 3.01:1 on lavender100, `--edge-strong` #77728D 4.51:1 on the brightest street, `--track` #86839A 3.01:1 on the ground, `--blue-edge` sky700 4.45:1 on the worst ground tone, `--marigold-edge` indigo900 13.13:1, `--ring-rim` indigo900 4.86:1 on the track and 10.81:1 on marigold400. The new dark chrome adds two: the location pill and the round buttons on the indigo900 bar carry a #78748E hairline at **3.98:1** against the bar, with white content on a #373158 fill at 12.05:1. The tier-tinted hairlines on badges and chips (sky400 on white 2.14:1, marigold400 fills) are **the library's own badge idiom** &mdash; its Estimated badge is literally a #69B7FF hairline on white &mdash; and each of those components carries a text label and a glyph, so neither the control nor its state is identified by that hairline; they were at the same ratios before this round. **Round 8:** Re-measured for the three marks this round touched. The J1 Estimated outline floors at **3.08:1** (place accent) in normal mode and **5.33:1** in high contrast &mdash; full table under 3.4. The dotted unknown-match halo now actually renders on the map (**6** of 12 pins with a wheelchair profile applied; it rendered **0** times before) and is drawn in the same sky700 as the outline, so it carries the same floor. `.sw.unknown` moves from sky400 (1.83:1) to `--match-unknown` (**6.24:1**). `.tierchip.est`'s border moves from sky400 (1.83:1) to sky700 (**6.24:1**). Every indicator this round changed measures at or above 3:1. *Not changed and still low, named rather than hidden:* `.matchchip.unknown` and `.mstat.unknown` keep a dotted sky400 hairline at 1.83:1 &mdash; the same labelled-component case this row already excuses, left alone because it was outside the brief, and now the only place a dotted line is drawn in a colour the halo it echoes does not use. |
| 7.3 | Every screen announces what it is when it becomes active. | 4 | All 26 screens now carry an `aria-label` (12 had none) and `tabindex="-1"`; `showScreen()` moves focus onto the screen, which is a labelled region, so the name is announced by the focus move. Walked all 26: `focusIsScreen: true` on every one. |
| 7.4 | Focus moves sensibly on every screen and sheet change, and returns on close. | 4 | Screen change: `document.activeElement` is the new screen on all 26 (was `BODY`). Sheet open: focus lands on the sheet heading (`H3.sheet-h`; the card sheet lands on `H2.card-name`). Sheet close: focus returns to the opener - Filters FAB after Escape, and the originating **pin** after the card closes, re-found by id across the re-render. `closeSearch()` returns focus to `#search-btn`. A nav token abandons the restore if the app navigated instead. **Round 6:** every deferred focus in the file waits on readiness now rather than on a clock &mdash; into a sheet, back to its opener, and into the search field. See 4.5 for the mechanism and the numbers. Two asymmetries the change audit recorded are closed with it: `openSheet`'s deferred focus is guarded by `navToken` (it was guarded only by the sheet's class, leaving a window where a pending sheet-focus could land after a screen had taken focus), and the focus-restore re-finds a re-rendered pin on a frame rather than at a guessed 20ms. Measured: closing the card returns focus to the exact pin that opened it, by `data-id`, after the map re-render; navigating away while a sheet is open abandons the queued focus and lands on the new screen with 0 inert nodes left behind. | **ROUND 7.** **A real defect was found on this line and fixed.** Reproduced from a clean load, 6 trials out of 6, at Round 6 HEAD (`c8ed0bf`) and again here before the fix: open the map card from a pin, press its **Close** button, and focus does not come back to the pin &mdash; with motion it stays on the card's now-off-screen `<h2>`, and with reduced motion it lands on `<body>`, which is a total focus loss. Calling `closeSheets()` directly returns focus correctly, so the return path itself was sound; the card's own drag/position machinery clears `openSheetId` before the `data-close` handler runs, so `wasOpen` read false and the whole branch was skipped. This is the seam class exactly: neither the round that wrote the return path nor the round that wrote the card's drag stops could have caught it alone. The branch now also runs when focus is demonstrably stranded (inside a sheet that is no longer `.on`, or on `<body>`), and `resolve()` tolerates a null opener. Re-measured after, 6 trials from a clean load in both motion modes: **5 of 6 return to the exact opening pin and 6 of 6 land on a labelled focusable element; 0 land on `<body>`.** Sheet open is unchanged and re-verified in both motion modes: focus lands on the sheet heading (`H2.card-name` for the card, `H3.sheet-h` for the modal sheets). Escape still closes, still clears every `inert` flag (0 left behind) and still lands on the labelled active screen. **Round 8:** **Two defects the Round 7 audit found here are closed, and one could not be reproduced.** (a) *A sub-sheet closed its parent card* (N2). Reproduced 1/1 at HEAD: expand a card to full, open the evidence receipt, close it &mdash; the card was gone and focus was on the pin. `openSheet()` now keeps an opener STACK; the three close affordances (close buttons, scrim, Escape) pop one level while every navigation call site still closes the lot. Measured after, two levels deep (card &rarr; receipt &rarr; correction): Escape restores the receipt with focus on `#rcpt-correct`, the scrim then restores the card **at the `full` position it held** with focus on `[data-act="receipt"]`, and closing the card returns focus to the pin. (b) *Focus stranded on a closed sheet's heading about 1 close in 20* (N1). **I could not reproduce it: 0 failures in 74 post-fix close trials** &mdash; 20 card open/close cycles with reduced motion on, then 27 with motion and 27 with reduced motion across the card, trust, needs and filters sheets and three close methods (close button, Escape, scrim). At Round 7 HEAD I ran a further 83 close trials at open-waits of 0 to 320ms and saw 0 failures there too, so the audit's 1-in-20 rate did not reproduce on this machine either before or after. The fix is shipped anyway and is now unconditional rather than gated on `isFocusable(fallback)`, with a post-condition `assertFocusPlaced()` that runs a few frames after every return. Proven by forcing the exact failure &mdash; focus on `H3.sheet-h` inside a sheet with `.on` removed: `focusIsStranded()` reads true and focus is moved to `#screen-map`, a labelled `tabindex="-1"` section. `window.__focusAsserts` stayed at **0** through every unforced trial, so the assert is a net, not a crutch.
| 7.5 | Blocked actions and errors are announced, not only shown. | 4 | `toast()` now routes through `announceUI()` - every toast reaches `#sr-announce` (verified: region text matches toast text). Submit claim unchecked: screen holds, `aria-invalid="true"`, `aria-describedby="claim-authz-err"`, inline error shown, focus on `#claim-authz`, announced "Claim not submitted...". Publish with the face-flagged photo (from both `ow-photos` and `ow-review`): inline error naming photo 3, `aria-invalid` on the publish button **and** on the Crop control, focus on Crop, announced. Checking the box / cropping clears all of it. **Round 6:** two more blocked actions now say so. **The claim form** submitted with both contact fields empty and landed on "We'll email you when your workspace is ready", having collected no address. It validates the channel the radio group actually selects &mdash; so someone verifying by phone is not asked for an email &mdash; in the same shape as the authorisation gate that already worked: measured, empty submit holds on `claim-confirm`, shows the inline error, sets `aria-invalid` and `aria-describedby`, moves focus to `#claim-email` (or `#claim-phone`), and announces "Claim not submitted. Add the work email we should send the link to." With a value it proceeds, and the confirmation names the channel it collected. **An empty correction** submitted and was recorded in My corrections as a dated source with no observation in it &mdash; on a product where a correction becomes a line on somebody's evidence receipt. It now needs a note or a photo (a photo IS the observation), with the same describe / show / focus / announce shape. Neither gate was added by disabling a button: both controls stay pressable and explain, which is what the interaction spec asks Unavailable to do. |
| 7.6 | What is announced matches what is shown, at every moment. | 4 | The transparent tick is `aria-hidden` in all three places (`.ci-dot`, `.p-ring`, `.tl-dot`). The checklist is a real list whose per-item state text is written by `setCheckState()` at the moment the class lands. At t=0: "Doorway framed - not checked yet ..." (was "tick Doorway framed tick Entry path visible tick Photo quality checked"). Sampled through a full run: **zero** frames where announced-done != visual-done. |
| 7.7 | Every state a sighted user gets from the map is available as text. | 4 | One `placeSentence()` now feeds both the list row and the pin. 64/64 pins name their match state: "Royal Blue Grocery. 241 W 3rd St. Scanned on-site. Good match, 3 of 3 needs. Seen 2 days ago. 300 ft. Seen: Step-free entry, Wide door, Easy-grip handle, Clear approach." Was "Royal Blue Grocery - Scanned on-site". **Round 8:** Three gaps closed as the pins lost their dots. (a) **Confidence.** The brief said confidence "stays" in `placeSentence()`; checked before removing the pin dots, it was **not there** &mdash; removing them would have deleted the only sighted and the only spoken carrier at once. `placeSentence()` now says "Confidence high / medium / low" using the same thresholds `dotTriple()` uses on the card. Measured: **12 of 12** pins name it. (b) **The cluster disc.** Its name said "8 entrances here" without saying that 8 is what the disc displays; it now reads "3 places grouped here &mdash; the disc shows the count (1 scanned on-site, 2 estimated) &mdash; tap to zoom in". (c) **The unknown match state**, which the map drew as a 20% dim and the match legend documented as "not yet seen &mdash; no halo", now draws its dotted ring and the legend keys it with a swatch. |
| 7.8 | Keyboard alone completes every flow; Escape closes what it opens; nothing behind a scrim is reachable. | 4 | Escape closes the search overlay and all 8 sheets. With a modal sheet open: `aria-modal="true"`, background `inert` (live regions exempted), **0** focusables reachable outside the sheet (was 76), Tab trapped. Tab order on the map: search, list toggle, zoom, locate and both FABs at indexes 1-9, then a "Skip the 64 map pins" control, then the pins (first pin at index 10; was index 0 with 64 pins ahead of search). Scan flow walked with real Tab presses: primer -> Close scan -> Allow camera -> capture -> Cancel scan -> Capture photo. No element anywhere in the app has a click handler without a native control under it (swept: 0 non-native clickables), so Enter/Space activation is the UA's. **Round 6:** the 4 covered `.sheet` and did not cover the one surface that made the claim in markup without keeping it. `#search-ov` carries `role="dialog" aria-modal="true"`, and measured while open it left **72 focusable elements reachable behind it and 0 `[inert]` nodes in the document** &mdash; Tab walked straight out into the map, the FABs and the bottom nav while a screen reader was being told the rest of the app was gone. The same defect class as a switch reporting a state it does not have, in the one place the claim is made to assistive technology only. It was a gap rather than a regression: `openSearch` was byte-identical to Round 1. The overlay is not a child of `.phone` &mdash; it lives inside the map screen's body &mdash; so `setBackgroundInert` would have inerted its own ancestor; `inertOutside()` walks the ancestor chain and inerts the siblings at every level, and only ever clears the flags it set, so it cannot undo a sheet's. Measured now: focus lands in `#search-in`, **0** focusables outside, 10 inside, Tab cycles, Escape closes, inert clears on close, and the sheets' own inert (35 nodes) still works unchanged. |
| 7.9 | Roles are correct and never destroy a native one. | 4 | 0 `button[role="listitem"]` in the document. Saved, My scans and My corrections are `UL role="list"` > `LI` > `BUTTON`, matching the list view. Seven labelled `<div>`s got a real role; 0 remain. The non-modal card sheet is `role="region"`, not `dialog`. Freshness is a labelled group with `aria-pressed`; the claim result is a `radiogroup` of `radio`s with a roving tabindex, arrow keys and a visible tick. |
| 7.10 | Reduced motion removes animation without removing feedback. | 4 | Re-verified after the changes: sheet, checkitem and ring transitions all 1e-05s, `#ringwrap` `display:none`, the determinate bar at 100%, all three checks landed, "Checks complete. 3 features identified." still announced, checklist text agrees. **Round 4 (asset library):** re-verified alongside 4.5. **Round 6:** see 4.5 for the measurement (0/12 in both settings, including with the pre-Round-5 CSS re-injected). The four animations added this round each have an explicit reduced-motion answer in the same block, and two of them are the spec's own words: confidence dots and outlined checks "appear in their final states" (asserted, not shortened), the stale clock rests, the receipt opens at its destination height, and the navigation indicator arrives beneath the new tab rather than travelling to it. Measured with Reduce Motion on: dot `animation-name none` with the filled background asserted, check path `stroke-dashoffset 0px` with no dasharray, evidence box at its full 60px in one frame. **Round 8:** **The contract now has a floor under it.** Before this round there was no `@media (prefers-reduced-motion: reduce)` rule anywhere in the file (verified: `hasRMMedia` false) &mdash; the whole contract hung on a class written by `applyPrefs()` near the bottom of a 1.4MB document. *Honest correction to the audit:* over 5 cold-fetch loads on this machine `applyPrefs()` ran **41.8 to 57.2ms BEFORE** first paint, so I could not reproduce the reported 92-500ms window; the structural exposure is real regardless (progressive paint on a slower device, or `applyPrefs()` throwing). Two mechanisms close it. The class moved from `.phone` to `<html>` and is set by an inline `<head>` script before `.phone` is parsed &mdash; the `.phone.rm` selectors became `.rm .phone` &mdash; 28 textual occurrences rewritten, of which **26** are CSS selectors across **17** rules and 2 were prose in comments &mdash; at identical specificity, so there is still exactly **one** copy of the rules. And a real `@media` block mirrors the universal transition rule as a second floor; forced on in the live CSSOM it takes the card sheet from `transition-duration 0.32s / transition-delay 0.32s` (the `visibility` guard) to **0s / 0s**, which is the precise seam a delay-only reduced-motion rule would leave open. Verified end to end by setting `.rm` on `<html>` with `applyPrefs()` never told about it: pin transition **0s**, and **20/20** card opens and closes with focus landing inside the sheet and returning to the pin. |
| 7.11 | Text scaling to the largest setting clips nothing. | 4 | Top step raised from 17.4px (+16%) to 18.9px (+26%). Swept all 26 screens at Default, Larger, and Larger + high contrast: the set of overflow findings is **identical** across all three and every entry is a `.sr-only` element or clipped map geometry - no visible text clips. The toast, the one failure in Round 0, now wraps: 358px wide, 3 lines, `scrollWidth == clientWidth`. **Round 4 (asset library):** re-measured at the largest setting in both contrast modes after the face change: **0** clipped text nodes and **0** horizontal overflow across all 26 screens. **Round 6:** the 4 was measured for CLIPPING, which was genuinely zero, and missed SQUASHING, which was not. `.screen-body` is a column flex container, so its children inherit `flex-shrink:1` and are compressed below their content while `overflow:visible` spills the text onto the control beneath. Measured at the largest text size: `.verify-opt` on `claim-confirm` given 52px for 78px of content, `.ow-locked` 134 for 143, and `.flowhead` 58 for 70 on four owner screens. The items simply do not shrink now &mdash; the body already scrolls, which is the correct answer to "more content than screen". Re-swept all 26 screens at all three text sizes: **0 clipped, 0 squashed controls**; the three remaining entries are 3px line-box overflows on headings (`.scan-h`, `.wl-h`, `.ob-h`) where the font's natural line box exceeds a 1.15 leading, which is typography, not layout, and 4px on `.checklist`. |
| 7.12 | Touch targets meet 48x48 including expanded hit areas &mdash; the handoff package's figure, not the 44 every audit before Round 6 measured against. | 4 | The two failures are fixed. `#card-grip` 390x44 (padding grew, the 5px grip bar did not). `#search-clear` keeps its 34px disc with a `::before{inset:-5px}` hit area: all four `elementFromPoint` probes at +/-21px hit the button. **Round 4 (asset library):** re-measured across all 26 screens in all four modes: **0** targets under 44x44, counting a wrapping `<label>` as the target for the native radio and checkbox controls it wraps. **Round 6:** **the bar moved and the build was re-measured against it, not credited for the old one.** Swept all 26 screens counting a wrapping `<label>` as the target for the native control it wraps, and reading `::before` insets as part of the hit area: **51 controls under 48x48** at the start of this round (1 under 44). The figure was written out literally at about sixty sites, which is why it could not be raised in one move; it is `--tap` now. Re-swept the same way: **1 remaining**, the native radio inside `#vo-email`, whose label is 358x62 and toggles it. The pin and cluster hit discs went 44 to 48 with their offsets recentred on the token; the switch's hit area is 52x48, probed by `elementFromPoint` at 8px above and below the 31px track and correctly missing at 10px; the `.achip` and `.search-clear` insets went to -8 and -7. Raising the floor cost width in the one place the brief predicted &mdash; the map bar's location pill wrapped its place name to two lines &mdash; and the row gave the 8px back from its gap rather than the name giving it up: measured 140x48 pill, `scrollWidth == clientWidth`, one line, same 12px inset as every other header. | **ROUND 7.** Kept as the historical record; 7.13 is the line that now measures this. Re-verified unchanged.
| 7.13 | Touch targets meet **48x48**, which is the handoff package's floor, not the 44 every audit before Round 6 measured against. | 4 | **Round 7 scores the floor instead of noting it.** Measured on the running page across all 26 screens in all four modes (standard/high-contrast x default/larger), using the union of the control's own box, any `<label>` that activates it, and any `::before`/`::after` hit-area extension the stylesheet declares &mdash; because a rect-only measurement misses both, and a naive `elementFromPoint` probe over-reports by walking into ancestors. **810 control measurements across the 26 screens, 0 below 48x48 in either dimension.** That sweep only sees what a screen renders, so a second one opens all seven sheets (filters, needs, card, receipt, correction, trust, privacy) in the two mode extremes and measures inside them once each has actually settled: **14 sheet opens, 72 further control measurements, 0 failures**. **The second sweep found one real failure and it is fixed:** the filter sheet's `Reset` had `min-height:var(--tap)` and no `min-width`, and measured **45.8 x 48** open &mdash; 2.2px short, and invisible to a screen-only sweep because the sheet is closed there. It now carries `min-width:var(--tap)` and measures 48 x 48. Two readings that look like failures and are not, recorded so the number can be reproduced: a `.sheet-close` inside a *closed* popup measures 44.16 x 44.16 because `.sheet.popup` rests at `scale(.92)`, and the same button measures 44.16 mid-transition if it is read before the open finishes; settled and open it is exactly 48 x 48. Round 6's 48px work otherwise survives the palette and ground change intact. Two measurement notes, so the number can be reproduced rather than believed: `.toggle` is a 52x31 switch whose declared `::before` inset of -8.5px vertical makes the target 52x48, and the claim radios and the authorisation checkbox are 20x20 inputs inside full-width `<label>`s that activate them, which is what the union is for. Range inputs are excluded as continuous controls. The same sweep at Round 6 HEAD also reads 0, so this is a hold, not a gain &mdash; but it is now a scored line rather than prose. |
| 7.14 | **7:1 is a floor for body text, not an observation.** Every text ink used for reading clears it, in both contrast modes and at every text size. | 4 | **Round 7 holds it as a bar and the build now clears it.** At Round 6 HEAD the bar was not met: swept the same way, **43 instances at 15 distinct selectors** measured 6.42:1, all of them white on the retired violet `#5B35F5`, and a deterministic DOM count (every element whose own computed background is that violet and whose own computed colour is white) puts the true site count at **20** &mdash; not the 16 the Round 6 report and the Round 7 brief both quote, and not the 15 or 17 a visible-only sweep happens to catch depending on what has rendered. Re-counted before stating. The canonical violet `#4F34DB` lifts all 20 to **7.38:1**, which is Round 6's own prediction and is confirmed by the package's contrast report. After the swap: **1,303 visible-ink samples, and 1,012 then 1,464 static samples on two separate runs, all across 26 screens x 4 modes, 0 below 7:1 every time, minimum 7.38:1, 0 below AA at any size.** The derived inks were re-solved against the worst light surface in the system rather than against lavender100 alone, so a pressed surface or a wash cannot drop a reading ink under the floor (see 7.1 for the seven worst-case figures). **No deliberate exceptions remain to name:** the two control labels the previous entry held under the bar are both raised, not excused. |

## 8. Flows the product promises

A screen can score 4 on every line above and still not add up to a thing a person can
use end to end. This section scores the promises the product owner made out loud, so
that a flow he asked for cannot be finished in pieces and never assembled.

| # | Criterion | Score | Evidence |
|---|---|---|---|
| 8.1 | The scan is a walkable sequence, not a button: "did you also add a scanning screen walk through? a processing screen for the scans? how long would a live scan take?" | 3 | Directive ledger, scored against HEAD. Six beats exist and connect: primer (storefront illustration, "Only the doorway is captured", marigold **Allow camera**) &rarr; live viewfinder with the coaching chip &rarr; processing &rarr; review &rarr; publish &rarr; published. The processing screen answers "how long" in words, not just in motion: `#proc-caption` reads "Usually under 8 seconds", and "Usually under 15 seconds" when agreement gating adds the fourth check. Three named checks, a self-drawing ring and the feature chips are 4.4's work and hold. Two board beats are still missing and are why this is a 3: the countdown inside the ring, and the mini map with the three-tier legend on the published screen (visual-language section 7). |
| 8.2 | "The photos should also auto store the images." A scan keeps its photos with no save step, the app says so plainly, and the photos are what other people see on the card. | 3 | Directive ledger, scored against HEAD. What is there: the card renders a `.photostrip` of the place's own scan photos with "N of M photos &middot; tap for the receipt", and the receipt renders them full width, so a scanner's photo does reach other people (this closes the earlier "shouldn't the photos they take be on the photo when you click on it"). The offline path is designed &mdash; "Saved for later / Your scan will upload when you're back online". Privacy is stated as automatic: "Faces are auto-blurred and GPS is stripped at upload &mdash; you never have to do a privacy step." What is missing: **no screen on the ordinary online path tells the user the photo was kept, or where to find it again.** Publishing a scan says the scan published, not that the image is stored. A 4 needs one plain line on the published screen and a route back to the user's own photos. The object store behind it (buckets and keys handed over 2026-09-05 19:45) is build work outside this file, and no design round is waiting on it. |
| 8.3 | The app goes on a phone home screen and wears the logo mark there: "the logo should be the app image", "the image is just a door, not what we agreed it to be", "theres not an add to homescreen". | 3 | Directive ledger, scored against HEAD. `<link rel="apple-touch-icon" sizes="180x180">` points at the brand mark (`entrymap-touch-icon.png`), and `apple-mobile-web-app-capable` makes iOS Add to Home Screen give a standalone window, so the door image is gone and the mark is the icon. There is **no web app manifest**, so on Android the install prompt has no name, no icon and no theme colour, and the phone falls back to a screenshot. A 4 is a manifest carrying the same mark, the name EntryMap, the aubergine theme colour, and standalone display. |


## 9. Conformance to the approved interaction and motion specification

Added in Round 5. Sections 1&ndash;8 were written before
`board-refs/entrymap-assets/asset-library/INTERACTION-MOTION-SPEC.md` and its token
files existed, and they score the build on its own terms &mdash; "is this a coherent
system?" This section scores the other question, which the conformance audit
(`design/interaction-audit.md`, 20 violations / 19 numeric drifts / 21 confirmations)
asked first: **is it *this* system?** Every score here is measured on the running page.

| # | Criterion | Score | Evidence |
|---|---|---|---|
| 9.1 | Trust encoding is fixed. Context may scale a pin; it never changes a tier's encoding. | 4 | Was **1**. Round 2 demoted Estimated from a pin to a ~14px dashed ring with no teardrop and no glyph, routed through a `ring` tier &mdash; the one place in the build that changed a tier's encoding rather than its size, and the thing `pin-hierarchy.json` opens by forbidding. The `ring` tier is **deleted**: `pinSVG` no longer has that branch and nothing calls it. Estimated is the library's white dashed teardrop with the italic `i` and its 0-of-3 dots at every zoom. The second, quieter version of the same move is also gone: the zoom-out rule used to send *every* estimated place into the counts, which is a tier not getting to be a pin one zoom level up. Collision and clustering do that work instead. Measured at overview: Estimated **32px**, drawn, present. Neither the fill, stroke nor glyph of any pin changes for selection, match, freshness or provenance &mdash; re-checked on all four, the spec's strictest prohibition, and it still holds. **Round 8:** Re-checked against the new artwork. The Estimated tier is still a teardrop at the token sizes (32 overview / 40 street / 52 selected / 24 receipt), still the only white-filled one, and the glyph change does not touch the encoding rule: no tier's fill, stroke or glyph moves for selection, match, freshness or provenance. The confidence dots that used to sit above every head are removed from the build, not hidden &mdash; `pinDots()` is deleted and **0** call sites remain &mdash; so a later round cannot re-enable them with a flag. |
| 9.2 | Contextual pin sizes, cluster size, render order and overlap follow the token table. | 4 | Was **1** (one size set where the spec has four; measured ~14 / 30 / 40 against 40 / 44 / 48). Measured now, on the running page, by SVG bounding box: street **40 / 44 / 48**, overview **32 / 36 / 40**, selected **52 / 56 / 60**, card and receipt **24 / 28 / 32**, cluster **48.0**, live scan drop **64**. Selection is a real size change plus the specified 6px lift and the library's white keyline inside an indigo outer line, not `scale(1.22)` on a 40px drawing. Render order is the spec's own numbers by name, not arithmetic on rank: cluster 10, Estimated 20, Scanned 30, Owner 40, needs-match 50, selected 60, live scan 70. The density constants moved with the artwork &mdash; spacing 22&rarr;46, overlap .40&rarr;.10 (the value at which two 44px pins 24px apart, the tightest real pair in the pilot block, go into a disc instead of covering each other's glyph), and the ceiling now counts all three tiers rather than exempting the one that used to be a ring. Result: **12 pins and 9 discs at street, 12 and 11 at overview, 52 of the 64 places counted rather than drawn.** The calm comes from clustering, which is where the spec puts it. **Round 8:** **Cluster-to-pin overlap was never tested, and it was worse than the audit reported.** The separation pass pushed discs away from `q.x, q.y` with radius `q.r` &mdash; the pin's TIP, not its drawn head, which sits 0.576 x size above it. Measured on the live build before the change, against the circle the pin actually paints: a disc covered **100.0%** of one 44px head at street and **95.8%** of a 36px head at overview (the audit said 43.3% / 21.0%). The pass now clears `headOf(it)`, and a post-condition absorbs any pin a clamped pass could not clear. Measured after, in five configurations (street and overview, with and without a needs profile, and with a pin selected): worst cluster-over-pin-head **0.0000** in every one, **0** pins absorbed, all **64** places still accounted for, and pin counts unchanged at 12 pins / 14 discs street and 12 / 8 overview. Pin-to-pin is untouched at 0.0844 street and 0.1226 overview on the drawn head, both inside the same-rank tolerance of 0.20. A side effect worth recording: the minimum centre-to-centre distance between two 48px tap targets rose from **7.1px to 27.5px** at street and **11.7px to 21.2px** at overview, and the count of target pairs closer than 44px fell from 12 to 8 and from 27 to 22 &mdash; better, but still not resolved, and a Round 9 item. |
| 9.3 | Every actionable control has all five states, including Unavailable, and Unavailable is never grey. | 4 | Was **0**, vacuously satisfying the no-grey rule: `document.querySelectorAll('[disabled],[aria-disabled]').length` was 0 and the stylesheet had no rule for one, so a control that was not yet usable looked exactly like one that was. The state is now `controls/primary-unavailable.svg`'s own values &mdash; lavender200 fill, indigo900 label at 11.98:1, keyline the same lavender so the control flattens rather than dimming &mdash; and it is `aria-disabled`, not the `disabled` attribute, so the control keeps its focus ring and its press. Wired to the two gates the build already knew about. Measured on claim-confirm with the authorisation box unchecked: Submit claim carries `aria-disabled="true"`, `background rgb(226,218,255)`, `color rgb(23,16,61)`, `tabIndex 0`; pressing it still opens the inline explanation, marks the checkbox invalid, moves focus onto it and announces &mdash; which is the spec's "tapping explains what is needed", and better than a dead button. |
| 9.4 | The card sheet follows the drag one-to-one, snaps by release velocity, and hits the named stops and veil. | 4 | Was **1**: no `pointermove` handler at all, a fixed &plusmn;28px threshold that stepped exactly one stop, and stops measured 20.9 / 41.9 / 85.1 against 18 / 54 / 92. Measured now: a 120px drag moves the sheet `matrix(1,0,0,1,0,-120)` &mdash; one-to-one under the finger; a slow 120px drag from peek lands at **medium**, a 100px flick in 24ms from peek lands at **full** (which the old threshold could not reach), a hard downward flick from peek **closes**, and a tap on the handle still cycles. Stops measured at each: **152px / 18.0%**, **456px / 54.0%**, **776px / 91.9%**. Snap 320ms on `cubic-bezier(.22,.9,.28,1.08)`. The map veil is a 7% indigo900 wash bound to the full stop only &mdash; measured opacity 0 at peek, 0 at medium, 1 at full &mdash; and the separate modal scrim is restated on indigo900 (it was `#17141F`, not a palette colour). Peek's padding yields to the declared height so that name, tier and match all still fit above the fold; the 44px handle target is what does not yield. A declared height can clip where a content-driven one grew, and at the largest text setting it did, so the non-full stops scroll rather than clip &mdash; measured at all three stops and all three text settings, the heights stay 18.0 / 54.0 / 91.9% and nothing is cut off. The handle remains the drag affordance: the gesture declines to start inside a scroll container that can actually scroll, which is what the card&rsquo;s own hint has always said. |
| 9.5 | Screen transitions carry both halves, at the spec's distances, durations and curve. | 4 | Was **2** &mdash; the incoming half only. See 4.1. Measured mid-flight: outgoing `screen-exit-fwd` **260ms** on `cubic-bezier(0.2,0.75,0.25,1)`, incoming `screen-fwd` the same, destination entering from **24px**, back the exact mirror, peer navigation `screen-exit-lat` at **180ms** with an 8px settle on the arrival. The departing screen is `inert` while it is only a departing image of itself, and the hold is cleared on a **timer**, never `transitionend` &mdash; the file still has zero `transitionend`/`animationend` listeners. **Round 6:** **one sentence of the evidence above is now false and is corrected rather than left standing:** the file no longer has zero `animationend` listeners. The departing screen was removed on a 280ms timer, 20ms past its own 260ms animation &mdash; a guess, and the class of guess that produced the worst defect in this build. It is removed on `animationend` now, with the timer kept as a watchdog for the cases the event never arrives, and the listener is attached BEFORE the class that starts the animation, which is what makes the event impossible to miss and is exactly the failure mode earlier rounds avoided by not using events at all. **The product owner's doubled `claim-confirm` screenshot was reproduced before being judged:** measured on the real path, the outgoing screen is present at 50ms and 150ms, offset `translateX(-10.4px)` at 0.896 opacity with its own dark `.flowhead` (which is the second status bar and second back chevron in the screenshot), and gone by 300ms &mdash; on every path including twelve interleaved navigations. It is a mid-transition capture of the exit Round 5 added, not a stranded screen, so it does not outrank anything. |
| 9.6 | Reduce Motion replaces animation rather than shortening it, from a single switch. | 4 | Was **2**. See 4.5. **Round 6:** see 4.5. The switch is still single (`isReduced()` &rarr; `.rm`), and it now also zeroes `transition-delay` and `animation-delay`, so "no motion" no longer means "no motion but keep the wait". **Round 8:** The switch is still single, and it is now also earlier than first paint (see 7.10). What changed here is what "replaces rather than shortens" means for two clauses that were still shortening: the processing checklist keeps its cadence and its announce-then-hold instead of collapsing to 4.9ms, and the capture coach shows all four guidance lines at once instead of changing them instantly forever. Both measured under 4.5. |
| 9.7 | A cluster never impersonates a trust tier, and shows the mix it holds. | 4 | Was **1**: the disc was drawn with a violet600 dashed rim and a violet800 count &mdash; the Owner-confirmed tier's own colour &mdash; so a disc holding four estimates was drawn in the colour of the highest tier, exactly what the clause forbids, and the mix was invisible although the build already computed it for the aria-label. Restated on indigo900, which is not any tier, with the tier mix drawn as three proportional arcs in sky700 / marigold400 / violet600 around the outside. One size, measured 48.0px, at the spec's z-index 10. The aria-label is unchanged and still prints the breakdown in words. | **ROUND 7.** Restated to the kit's own drawing. `map-kit/svg/mixed-cluster.svg` draws the marker as an indigo900 disc with a white ring, a white count, and the three composition arcs **inside** it at radius 70/76; the build drew a white disc with an indigo rim and hung the arcs outside, where the sky arc sat on the map ground at 1.83:1. Proportions are the kit's, scaled to the 48px cluster (disc r17, ring 1.8, arc radius 15.7, arc width 2.9), and the arcs now measure sky400 8.55:1, marigold400 9.60:1 and violet600 2.60:1 on the indigo disc. Neither the disc nor the count is any tier's colour, the count is still the carrier, and the aria-label still prints the mix in words. **Round 8:** The disc is now **taught** as well as honest. It gains a legend row (the disc, drawn by the same `pinSVG('cluster')`, labelled "8 places here") and a rung in the "How trust grows" sheet that says in words that it is not a tier and what the number counts. The accessible name says what the number is rather than only what is under it. The legend row cost 34px in a column that had none to spare, so the card's rhythm is compacted to pay for it &mdash; see 5.7 for the measured before/after and the residual overrun this round did not close.
| 9.8 | The pin drop's tail is one sky-blue ripple, and the drop is the spec's length. | 4 | Was **1**: two marigold passes of 1,000ms each, a tail that outlasted a 700ms drop by more than 3x and repeated the Scanned tier's own colour back at the reader. Measured now: `border-color rgb(18,102,166)` (sky700, the on-light sky, because the ripple is drawn over a map ground where sky400 is 1.63:1), `animation-iteration-count 1`, `animation-duration 0.52s`, drop `--dur-drop 620ms` on the token file's own spring. |
| 9.9 | Every remaining feedback clause of the specification is implemented. | 3 | Was **2**. **All five feedback clauses named in the previous entry are closed, measured on the running page.** *Confidence dots fill left to right, 70 ms apart:* `dot-fill` 150ms with delays 0 / 70 / 140ms, scoped to a sheet, the evidence box or the scan review &mdash; a surface the reader just opened, so 4.6 is not damaged; the empty step keeps its rim throughout, because the rim is what makes it visible, so it is the fill that arrives. *Outlined checks draw over 180 ms:* the tick is one path measured at 20.98 units in a 32 viewBox, carried by `stroke-dasharray:21` over 180ms &mdash; a mark being made rather than an image fading in; measured mid-draw at `stroke-dashoffset 2.99px`. *Toasts rise 12 px and can be swiped away:* the rise went 20px to the spec's 12px over the existing 220ms, and any drag past 24px or a tap dismisses; the message has already reached `#sr-announce` by then and the toast is never the only channel for anything, so this adds a shortcut rather than a requirement. *A stale claim gains a muted-amber clock rotation of 20 degrees and returns to rest:* the re-check nudge's clock turns 20 degrees and comes back over 450ms in the amber ink it was already drawn in &mdash; no colour added, and the copy already described time rather than the place. *Receipt height animates over 240 ms without moving the selected chip offscreen:* the evidence box was a `display` toggle and is now a one-row grid eased from `0fr` to `1fr` on `--dur-receipt` (a token that had been in the file with no consumer), so the real height animates without a magic max-height that could clip at the largest text size; measured 46px mid-transition, 60px settled, 0 closed, and the chips above it do not move. One of the three pin-adjacent items is closed too: the **bottom-navigation indicator travels** &mdash; a single element the bar moves, measured 44.4px &rarr; 275.4px over `--dur-peer` with the tab colour crossfading sky400 &rarr; lavender200, hidden for the scan tab, which has its own marigold ring. Each of the six has an explicit reduced-motion answer, two of them in the spec's own words (see 7.10). **Not a 4, and here is what is left:** the freshness clock overlay still never appears on a pin, and that is now a recorded decision rather than a gap (9.10); filter changes do not crossfade affected pins over 180ms, which is newly visible this round because the filters finally change the result set; and the selected pin's screen position is still not preserved as the sheet opens, which remains a deliberate divergence. |
| 9.10 | Where the specification is not followed, the divergence is a recorded decision rather than a silent gap. | 4 | Four are now written into the source beside the code they govern. **Haptics:** not called and not faked &mdash; `navigator.vibrate` is unimplemented in iOS Safari, which is the platform this demo is shown on, so a capability-checked call would fire on Android only and demo differently on two devices in the same room; the intent belongs in the native shell. **Touch-target figure:** the spec and `interaction-motion.json` say 48x48, the build stays at 44x44, the WCAG 2.5.5 AAA figure Round 1 measured every control against; raising the floor would reflow dense rows across 26 screens at two text sizes for a 4px gain over a published standard already met. Re-measured this round, the only controls under 44 are three NATIVE inputs on claim-confirm, each inside a row that is itself the 44+ target and toggles it. **The Texas flag on the map:** the boards draw it beside a pin on three of four panels, `pin-hierarchy.json` says receipt-only, and our own canon withdrew the accessory because icon soup around pins was the original complaint &mdash; defaulting to the token spec and flagging it to the product owner rather than settling it silently. **The full sheet stop overlays the bottom bar:** 92% of 844px is 776px and the bar is 86px, so they cannot both be on screen; the spec's number wins at the full stop only, and peek and medium stay docked above the bar. **Round 6:** the touch-target divergence is **withdrawn, not re-argued**: the build is at the spec's 48 (7.12), so that paragraph in the source is replaced by the token that implements it. Three divergences are recorded in its place. **The freshness clock overlay is deliberately not on the pin.** The spec names it and the library ships the asset, and it would not violate the recolouring rule &mdash; it is a badge, not a tint. It is held back because it needs a legend entry to be honest (the trust legend teaches three marks and this would be a fourth glyph with no key), because the product owner has twice rejected pin accessories and icon soup around pins was the original complaint, and because freshness already reaches the card, the rows and every pin's accessible name. Put to the product owner rather than settled silently. **The modal scrim is the spec's 7%, which is lighter than the board's own measurement.** The board measures the map under an open sheet at `#C7C6D5`, about a 20% veil; the interaction spec says 7%, and the round brief said to take the spec's number. Ours was 42%, computing to `#9691AE` over the old ground &mdash; twice the board and three times the spec. It is one `--veil` token now, so if the owner prefers the board's weight it is one line. What separates a modal sheet from its background is inert, the focus trap and `--elev-3-dock`, none of which depends on how dark the scrim is. **The palette is knowingly one version behind.** The handoff package names six values, all six different from the ones Round 4 adopted, and it ships a manifest with hashes and a verification step. Nothing was transcribed from prose this round; every colour change made here is structural (which token plays which role, and how much of the screen it covers) and survives the swap. The one figure this costs is body contrast: 16 text sites sit at 6.42:1 against the package's 7:1 floor, all of them white on violet600, and the package's darker violet (`#4F34DB`) is what raises them &mdash; which is a reason to wait for it rather than to invent a seventh violet. |


| 9.11 | Every screen the boards show exists in the build and matches its export: "are the mockup flows and visuals the same in our app?" Measured per screen against `board-refs/entrymap-build-ready/screen-exports/` and its crop manifest, not judged against the six full boards by eye. | 3 | **Round 7 turns the opinion into a count.** All 25 exports were read, a copy-and-control checklist was written from each one, and the checklist was run against the running build with the app reset between entries. **25 of 25 have a build screen or state; 0 are missing outright.** Sheets and states were opened through the app's own functions rather than assumed. Differences found, and they are differences rather than gaps: **(1)** `map-filters` &mdash; the export has an "Open now" switch and a "1 mile" distance label; the build has neither, and the switch was removed deliberately in Round 6 with the reason written beside the code. **(2)** `system-controls` &mdash; the export's camera card offers "Open settings", the build offers "Choose an existing photo", which is the useful alternative the package's own checklist asks for. **(3)** `onboarding-location` &mdash; the export's secondary is "Not now", the build's is "Choose an area instead", same reason. **(4)** `evidence-recheck` exists in full ("Could you take another look?", "Re-check entrance", "Maybe later") but **no seeded place is old enough to reach it** &mdash; 0 places over 180 days &mdash; so the state ships unreachable from the demo data. That is the one finding here that is worth acting on. **(5)** business names differ throughout (the exports use "Page & Spine Books", the build uses real Austin businesses), which is content, not structure. **(6)** the exports draw the confidence ladder as segmented arcs around the pin head where the asset library draws three dots; the build follows the asset library, per Round 4. **In the other direction, 8 build screens have no export at all** &mdash; `ob-splash`, `screen-saved`, `screen-contrib`, `screen-a11y`, `screen-notif`, `screen-corr-done`, `ow-review`, `ow-listing` &mdash; so a third of the build is not covered by the package's exports and cannot be scored against them. **Held at 3, not 4:** the checklist is textual and structural, not pixel-diffed, and one shipped state is unreachable from the seeded data. *One correction to my own working: an earlier pass of this probe reported the word "undefined" rendered in the evidence receipt and the correction sheet. That was the probe passing an id where the function takes a place object. The build renders neither. Re-checked before recording.* |

---

## Round log

**Round 0 (2026-09-05).** Baseline scored after the screen packs were folded in, the
welcome screen was rebuilt on the logo canvas, and a full screen-reader audit was run
(design/a11y-audit.md: 10 blocking defects, 18 improvements, 11 confirmations).

Average across all 44 criteria: **2.61**. Twenty-two criteria sit below 3.

Two distinct gaps, and they are not the same kind of problem.

*Craft.* Meaning, copy and honesty score 4s: the product's thinking is finished. What is
missing is that four systems exist informally and are applied inconsistently &mdash; type scale,
spacing scale, elevation scale and motion scale. That is a tractable, mechanical fix.

*Behaviour.* The accessibility scores split hard: content 4s, behaviour 0s and 1s. Everything
a screen reader is *told* is excellent; everything it should be told *when something happens*
is missing. Screen changes announce nothing, focus is dropped on every transition, two publish
gates fail in total silence, and the processing checklist announces success before any check
has run. On a product for disabled people this outranks every craft item.

Order of work: accessibility behaviour first, then the four design systems, then motion.

---

**Round 1 (2026-09-05).** Accessibility behaviour. All ten blocking defects in
design/a11y-audit.md closed, plus fifteen of the eighteen improvements and the ASCII sweep.

Recounted the sheet while scoring: there are **45** criteria, not 44, so the Round 0
figures restate as 2.53 average with 21 below 3. On that same count, Round 1 is
**2.53 -> 3.22**, and criteria below 3 go **21 -> 12**.

*What moved.* Section 7 went from an average of 1.75 to 4.00 and is the first section
with nothing below 3. The three that mattered most:

- **Silent refusals (7.5, 0 -> 4).** `toast()` now announces through the live region that
  was already there and never called. Both publish gates render an inline error beside the
  control that blocks them, mark it invalid, describe it, move focus onto it, and announce.
  The refusal is now the same event in both channels.
- **Screen changes (7.3/7.4, 1 and 0 -> 4).** Every screen has a name and takes focus. A
  keyboard user no longer restarts at the document top 26 times; a screen-reader user is
  told which screen they landed on.
- **The lying checklist (7.6, 0 -> 4).** The tick is out of the accessibility tree and the
  announced state is written when the check lands. Sampled across a full run there is no
  moment where the two channels disagree.

Also closed: match state, freshness and distance now reach the pin itself (7.7); sheets get
focus in, a trap, Escape and focus return, with nothing reachable behind the scrim (7.8);
the three row lists stopped destroying their buttons' role (7.9); every non-text indicator
clears 3:1 in both modes, including the focus ring on the two dark screens where high
contrast had been making it worse (7.2, 1.23:1 -> 15.76:1); both touch-target failures
(7.12). 5.6 went 1 -> 4 with the ASCII sweep and 3.4 went 3 -> 4 on the measured contrast.

*What did not move.* Nothing in sections 1, 2, 4 or 6 was touched this round, by design &mdash;
the type, spacing, elevation and motion scales are still informal, and that is the next
round's work. Fifteen of the eighteen improvements closed outright; three are only partly
closed and are named here rather than claimed:

- **I5 (headings).** Every screen that had none now has an `<h1>` and the section labels are
  real `<h2>`s, but `.chips-title` inside the card and the sheets is still a `<div>`, so
  heading navigation within a card is still shallow.
- **I6 (the capture coach).** It no longer interrupts every 1.7s &mdash; `aria-live` is gone and
  it announces once on entry &mdash; but the visible chip still rotates, so WCAG 2.2.2's pause
  mechanism for auto-updating content is not there.
- **I15 (200% text).** The app's own top step went +16% -> +26% and clips nothing at any of
  its three settings, but a real 200% root is a layout project, not a token change.

The `[proc]` `console.log` instrumentation stays: it is a development aid, not an error, and
the console is otherwise clean.

*Verification limit worth recording.* The browser pane could not synthesise Enter or Space
key activation, so keyboard *activation* is evidenced structurally &mdash; a sweep found zero
elements in the app with a click handler and no native control under them &mdash; rather than by
observing a keypress fire a handler. Focus movement, tab order, Escape and the trap were
all driven with real key events.

---

**Round 2 (2026-09-05).** Board fidelity and the type scale. Everything measured below was
driven in a browser at 390x844 over `python -m http.server`, walking all 26 screens.

**2.53 (R0) -> 3.22 (R1) -> 3.69.** Criteria below 3 go **12 -> 5**, and three whole
sections (1, 3, 5) now have nothing below 3.

*What moved.*

- **The map (2.4, 2.5, 2.6: 3/3/2 -> 4/4/4).** This was the round's real work. Sixty-four
  identical pins became a four-level hierarchy that encodes evidence strength and nothing
  else. Owner-confirmed is the largest full pin, scanned on-site is medium, estimated is
  demoted from a full teardrop to a 14px dashed ring with no glyph, and everything that
  yields becomes a numbered disc. Measured: drawn mark area fell from 11.3% of the map
  viewport to 4.9% while all 64 places stayed on screen. Zoomed out, estimated collapses
  entirely (8 pins + 14 discs holding 56). Selection scales the chosen pin up and steps the
  rest back by 20% without hiding anything; a needs profile lets matching places hold full
  opacity and take a match ring while the rest recede; **no mark anywhere says a place
  fails**. The density rules run on the real dataset: weaker levels yield on overlap, the
  ceiling of a dozen full pins holds (10 drawn), the selected place is exempt and always on
  top, and every mark keeps a 44x44 tap target whatever its drawn size.
- **Pin anchoring (part of 2.6).** Pins were placed by their box origin with no compensating
  transform, so they pointed roughly a storefront's width away from what they marked. The
  button is now a zero-size anchor on the projected coordinate; measured across 58 pins, the
  drawn tip lands on the coordinate with max offset 0.00px in both axes. `revealSelected()`
  was updated in the same change, since it reads the same box and that box now means the tip.
- **Type (1.1, 1.2, 1.4, 1.6: 2/2/2/3 -> 4).** 177 selectors onto 8 steps; zero literal
  `font-weight` and zero literal `em` font-sizes left in the file. The weight rule is the
  part that mattered: 900 went from 94 CSS sites to 21, and on screen from 46% of all
  text-bearing elements to 17%. Row labels dropped to 800 and reading copy to 600.
- **Icons (5.4: 2 -> 4).** The gallery's 36-icon set landed and every call site moved onto
  it, plus 12 glyphs that only existed by hand and were added to the same grid. Hand-written
  24-grid SVG blocks: 50 -> 4.
- **Illustrations (3.2, 5.1, 5.2: 3 -> 4).** All seven placed.
- **Components (2.1: 3 -> 4; 3.3: 2 -> 3).** One selection component everywhere &mdash; empty
  ring on white, filled purple disc with a white tick plus a tinted, purple-bordered row when
  selected &mdash; replacing the inverted solid blocks the needs picker and filter chips used.
  Cards took a hairline plus generous padding. Secondary buttons became white with a purple
  border; the camera permission is marigold.

*What did not move, and why.* Sections 4 (motion) and 2.2 / 2.3 / 5.3 are untouched on
purpose: the brief scoped this round to type only, leaving elevation, spacing and motion for
Round 3. 3.3 rose to 3 rather than 4 because resting cards now agree but sheets, pills and
FABs still carry four different shadows. Section 6 is unchanged at 4s. Section 7 was
re-verified, not re-scored.

*Three judgement calls made against the galleries, each recorded rather than quietly taken.*

1. **The match halo is green, not the gallery's purple.** `pins-and-icons.html` draws it in
   purple. In this product purple already means owner-confirmed and green means "matches your
   needs" and nothing else (3.1, settled in Round 0). Colliding those two would have cost more
   than it bought, so the halo's form is the gallery's verbatim and only the hue is ours.
2. **Level 3 is a new tier on `pinSVG`, not a gallery drawing.** The pin gallery has no
   glyph-less ring, because visual-language section 10 asks for one and the gallery predates
   it. Rather than keep two pin modules, `pinSVG('ring', size)` was added alongside the three
   the gallery ships, in the same idiom, on a new `--blue-pin` token chosen so the ring still
   clears 3:1 after the 20% recession a selection applies (3.37:1 measured).
3. **The welcome hero keeps its aubergine, and the street scene went to the map-empty
   state.** The illustration agent rates the street scene the weakest of the seven, and
   visual-language is explicit that the dark hero is newer canon than the boards. Replacing it
   would have contradicted the document this round is meant to follow. The drawing was not
   wasted: "No entrances mapped here yet / be the first" is a street with nothing marked on it,
   which is what that illustration is a picture of.

*Round 1 re-verified, nothing regressed.* All 26 screens still take focus on change
(26/26); 0 duplicate ids; 0 `button[role="listitem"]`; 58/58 pin accessible names still
carry match state, freshness and distance; `toast()` still reaches the live region; the
Filters sheet still lands focus on its heading, traps it (0 focusables reachable behind the
scrim), closes on Escape and returns focus to the FAB; the card sheet still returns focus to
the originating pin, re-found by id across the re-render. Reduced motion re-verified through
a full scan run. Text scaling swept at Default / Larger / Larger+high-contrast: the overflow
finding count is **17 at every setting, identical to the pre-round file at every setting** &mdash;
one new 2px flex finding on the location pill appeared and was fixed before commit. Non-text
contrast re-measured for the rebuilt pins (3.4). File is still 0 non-ASCII bytes, one inline
script, no external scripts. Console is clean on load and across the sweep.

*Known and unchanged.* Seven pins on the map have their 44x44 centre covered by floating map
chrome (the legend card, the FABs, the nav bar). That is the pre-existing overlay behaviour,
not a product of the new anchoring, and the list view is the canon-mandated equivalent path.
The two 20x20 inputs on the claim screen remain inside 44px+ labels, as in Round 1.

---

**Directive ledger pass (2026-09-05).** Not a round. No implementation, no rescoring of
any criterion another round owns. This pass reads the product owner's own messages in the
session and asks one question of each: *is this written down anywhere that gets scored?*

Why it exists, in his words: directives should not "get lost, overwritten, or not
completed." It had already happened once &mdash; the note about the wordmark colours was written
into visual-language *after* the round that should have implemented it was dispatched, so
that round never saw it and he raised it three times before it moved. Prose in a design
document is not a safeguard. Prose does not get scored, and an unscored intention is
exactly the thing that goes missing.

**Nine criteria added: 3.6, 3.7, 3.8, 6.5, 6.6, 6.7, 8.1, 8.2, 8.3.** The sheet goes from
45 criteria to 54. Every new line is scored against committed HEAD (5cbb19f / 55b9684),
not against the working copy, because Round 3 is editing the prototype as this is written.

*Already represented, and where.* "More hierarchy on the map, the pins are all the same
size, it looks messy" &rarr; 2.4 and 2.5, closed in Round 2. "Better design elements,
transitions, typography, hierarchy" &rarr; section 1 (type, closed), section 2 (hierarchy and
spacing, 2.2 and 2.3 open), section 4 (motion, open). "Production ready and a stand out
product" &rarr; the bar stated at the top of this file, and the finish rule: nothing below 3,
average 3.5 or better. "Make sure the processing visual is stunning yet simplistic" and
"some kind of animation showing its processing" &rarr; 4.4. "The extra symbols around the
original symbols is so confusing, it should be in a hierarchy" &rarr; 2.4 and visual-language
section 10. "Photos they take should be on the photo when you click on it for others to
see" &rarr; now scored inside 8.2, and satisfied.

*Recorded against a settled rule rather than dropped.* 6.6. "Nothing is 100% verified,
which to me looks bad" cannot be answered with a tier above Owner-confirmed, because that
would be a compliance claim from photographs and 6.4 forbids it. The nearest thing that
respects the rule is written into 6.6 and is genuinely available: publish the on-site scans
for all 64 places, and let source agreement carry what the ladder must not.

*What nothing is currently scheduled to deliver.* This list is the point of the pass.

1. **The bottom bar is missing the logo's light blue** (3.6). Deep blue, marigold and
   purple landed; #7CC4FA reaches no chrome outside the two dark screens, and he named it.
2. **Publishing the on-site scans for all 64 places** (6.6). Asked for directly &mdash; "publish
   the scan results for all 64 before demo day" &mdash; and again as "publish the sealed 18 after
   the freeze too". No design round owns it; it is the single largest reason the map reads
   as knowing less than it does.
3. **Step-free coverage** (6.7). The copy is honest; the evidence is thin. On-site scans
   and gated depth are the two fixes and both sit outside every design round.
4. **The countdown inside the processing ring, and the published screen's mini map with
   legend** (8.1). Named as missing in visual-language section 7 and never scheduled since.
5. **Telling the user their photo was stored** (8.2). "The photos should also auto store
   the images." Storage is being built; nothing on the published screen says so, and there
   is no route back to a scanner's own photos.
6. **A web app manifest** (8.3). Add to Home Screen works on iOS only.
7. **He was never told the Texas filter was already gone** (6.5). The change is real in the
   build and correct; it existed only as prose in visual-language section 13 and was never
   scored, so nothing could report it back to him.

*Outside this file, and flagged so it is not lost with it.* "Why don't you know the
storefront for doors 13 to 64? You are supposed to automatically assign them for the user."
That is the capture-to-place assignment pipeline, not a design surface, and it belongs in
the ticket tracker rather than in a rubric line. It is named here only because this pass is
the last place it could have gone missing.

---

**Round 3 (2026-09-05).** The map ground, and the three systems Round 2 deferred:
elevation, spacing, motion. Plus touch feedback and a palette-and-style consistency sweep
the product owner asked for by name. Everything below was driven in a browser at 390x844
over `python -m http.server`, walking all 26 screens.

**The sheet grew while this round was in flight.** Commit 2073c88 turned nine owner
directives into scored criteria, so the file is now **54 criteria, not 45**. Three of the
nine are Round 3's work and are rescored here (3.7 the map ground, 3.8 the palette-and-style
sweep, 3.6 re-verified); the other six are product and coverage work this round did not own
and did not touch. Restated on the 54-criterion sheet, Round 2's file scores **3.54** with
**8** criteria below 3.

**3.54 -> 3.83.** Criteria below 3 go **8 -> 1**.

**Is the bar met? Not quite, and it is worth being exact about why.** The average clears 3.5
comfortably. Every criterion this round owned is now at 3 or above, and every one of the
seven it was told to close is at 4. **One criterion remains at 2: 6.6**, the owner's "nothing
is 100% verified, which to me looks bad." That is not a systems defect and no amount of
elevation, spacing or motion moves it. The directive ledger already records why it is hard --
a rung above Owner-confirmed would be a compliance claim from photographs, which 6.4 forbids
and which is the whole honesty position -- and names the two answers that are real: publish
the 52 on-site scans the operator already took, and let confidence do the work the tier
cannot. Both are engine and data work, neither is scheduled, and neither belonged in a round
scoped to elevation, spacing and motion. **So: the average bar is met and the floor bar is
not, by exactly one criterion, and that criterion needs a product decision rather than a
design pass.**

Six other criteria stand at 3 rather than 4, each held there on a measurement rather than a
shrug: line length (1.3), the light blue still missing from light chrome (3.6), the splash
still animating on load (4.6), step-free coverage (6.7), and the three from the ledger that
need engine or manifest work (8.1, 8.2, 8.3).

*The map ground, and the regression it caught.* The brief called this the round's real work
and it was, but not for the reason it looked like. `design/map-ground.html` measured the
**shipped** ground breaking the contrast fix Round 1 landed: the tree dots were `#AFC2F2`
and `#C4D0F6`, scattered at random across exactly the blocks the estimated rings sit in, and
a ring landing on one measured **2.37:1** against a 3:1 floor. Decoration had quietly undone
an accessibility fix, and nobody would have seen it, because it only happens where a dot and
a ring collide. The rebuilt ground is **Terrain's colour on Relief's light** as recommended
-- warm sand ground, sage canopy, marigold plazas, cool lavender towers among warm putty
low-rise, with a two-step cast shadow and a lit top-and-left edge on every footprint and a
tonal ramp keyed to footprint mass -- on the derived road hierarchy (Congress, Guadalupe,
Lavaca and Cesar Chavez primary at 16px, the numbered cross streets secondary at 11px,
Colorado minor at 8px, four service alleys at 4.5px, with the three missing labels added).
The contrast is now hit-tested against the drawn SVG's own paint list rather than assumed,
and re-measured after every subsequent change in the round; the table is in 3.4. High
contrast **simplifies**: 1,711 shapes become 61, with zero circles and zero paths -- one
block tone, hard outlines, no shadow, no canopy, no plaza, and only the road hierarchy
surviving, because widths are structure and everything else was enrichment.

*The estimated blue, settled.* `pins-and-icons.html` said `#2C63C9` and `map-hierarchy.html`
said `#3F79DC`; worse, the shipped teardrop's token read `#3F79DC` while its own inline
fallback read `#2C63C9`, so the file disagreed with itself. Settled on **`#2C63C9`**: it is
the pin gallery's canonical value, it is what the level-3 ring -- the only marker that
touches raw ground with no white lift halo -- already shipped as, and it drops the ground's
luminance floor from 0.691 to 0.510, which roughly doubles the tonal range the ground may
use and is what makes this ground possible at 3:1 at all. `--blue-pin` is gone; one name.

*The three systems.*

- **Elevation (3.3, 3 -> 4).** 24 distinct shadows to 4 levels in 6 tokens, plus 5 named
  rings that were never elevation. 11 distinct values are painted across the whole app and
  every one is a token. High contrast redefines the level tokens centrally instead of
  hand-picking 11 components in two rules and missing everything else.
- **Spacing (2.2 and 2.3, 2 -> 4).** 40 values to a 10-step scale plus 7 layout constants;
  574 of 611 values resolve to a token and the 12 raw `px` that remain are the documented
  geometry sites, each commented with what it is anchored to. Nine boxes gave way to
  proximity, six treatments of "a quiet supporting note" became one, and three treatments of
  "a quoted note" became one.
- **Motion (4.1 and 4.2, 2 -> 4; 4.3, 3 -> 4).** 19 durations to 2 plus 4 named narrative
  constants; 7 easings to 2 curves plus 1 scoped spring. Screens push and pop by direction,
  the popup grows from its opener, sheets are 220 in and 160 out, the list rises and settles,
  chips arrive and leave.

*Touch feedback (5.3, 2 -> 4).* 44 of 47 interactive components now press, in two treatments
chosen by shape. The three that do not are named: the pin, which has something better, and
the two native inputs inside rows that press around them.

*The consistency sweep, which is the part with the interesting number.* Twenty distinct
classes of "the same thing looks different", found by inventorying every declaration in the
stylesheet by property and by selector rather than by looking at screens. Beyond the systems
above: **23 border-radius values** to five steps plus a pill, a circle and five named
geometries (69 declarations rewritten); **six border widths** for one control edge to one;
**three hairline colours** plus a fourth undeclared grey (`#D8CCF3`) to one token, with high
contrast darkening it centrally instead of patching `.prof-row` alone and leaving six other
row types light; **four alphas of translucent white** across twelve floating surfaces to
`--float-white`; **six row heights** (48/50/52/56/60/64) to three; an undeclared quiet fill
`#F8F7FD` at five sites to `--wash-quiet`; a fourth ink `#6C6486` on the chevrons and a
literal `#4A4463` on the diff arrow to `--sub`; a literal `#2A1A5E` progress rim to a token;
two docked-sheet top radii to one; two legends at two radii to one; the fabs' 26px and the
grip's 3px, which were pills written as numbers, to `999px`; the search field, which was
wearing the floating map shadow though it is a form control; and three privacy rungs carrying
an inline icon box instead of the one `--icon-box`.

*Deliberately not done.* The card sheet's three positions still change height without
animating. The `0fr -> 1fr` grid-row technique keeps collapsed content in the accessibility
tree, which would contradict the round that closed the screen-reader defects; decision 3 in
design-systems-spec defers it and this round honoured that. Every other motion item was
independent of it. `revealSelected()` is still called twice around the position change -- once
immediately so the pan starts with the sheet, once after it settles -- and the second call is
on a timer, never `transitionend`.

*Round 1 and Round 2 re-verified, nothing regressed.* All 26 screens take focus on change
(**26/26**); **0** duplicate ids; **0** `button[role="listitem"]`; **64/64** pin accessible
names still carry match state, freshness and distance; pin tips still land on their coordinate
at max |dx| = |dy| = **0.00px**; `toast()` still reaches the live region; all **7** sheets
close on Escape, the Filters sheet lands focus on its heading (`H3.sheet-h`), traps it (**0**
focusables reachable behind the scrim), is `aria-modal`, and returns focus to its opener;
`closeSearch()` still returns focus to `#search-btn`. Reduced motion re-verified through a
full scan run. Text scaling swept at Default / Larger / Larger+high-contrast: **81 overflow
findings at every setting, identical to the pre-round file at every setting**. The two-tone
wordmark still renders in two inks (`#1D5FA8` and `#4B2E9E`) and the bottom bar still carries
three different tab colours (`#1D5FA8` map, `#6E4A00` scan, `#4A4463` profile). Touch targets:
the only sub-44px controls are the two 20x20 claim inputs inside 44px+ labels, as since Round
1. **No horizontal scroll on any of the 26 screens** once the push animation settles -- the
2-4px seen mid-flight is the 12px travel itself, clipped by the phone's `overflow:hidden`.
File is **0 non-ASCII bytes**, one inline script, no external scripts, single self-contained
HTML. **Console is silent** across a full walk of all 26 screens plus high contrast, zoomed
out, the card at all three positions and the list toggle.

*Two places I went off-spec, recorded rather than quietly taken.*

1. **The hairline stays `#DCD6F2`, not the spec's `#EDEAF7`.** design-systems-spec 3.2 was
   written before Round 2 chose `#DCD6F2` for the card boundary. Adopting the lighter value
   would have visibly undone Round 2's card treatment, so the consolidation used Round 2's
   measured value for all nine sites instead. One token either way; the spec's intent is met
   and the newer decision wins.
2. **The merged note is `--fs-sub`, not the spec's `--fs-meta`.** Two of the six notes live on
   the accessibility settings screen, and shrinking supporting copy there is the wrong
   direction. Six treatments still became one, which is what the criterion measures.

*Known and unchanged.* The seven pins whose 44x44 centre is covered by floating map chrome
are pre-existing overlay behaviour with the list view as the canon-mandated equivalent path.
Line length in row sub-copy (1.3) is a layout question, not a token question, and is the one
criterion in the file where the measurement got worse-looking because it finally got taken
properly.
**Round 4 (2026-09-05) -- the approved asset library.** The product owner supplied
`design/board-refs/mockups-final/`: 63 editable SVG masters, PNG exports, official
design tokens, a contrast report, and six final boards. It supersedes the palette and
the marks the build had grown by hand. This round makes the build match the assets
instead of approximating them.

*What was adopted.* Eleven official colours are now the only authored colours in the
file; every other colour is one of them or a stated two-step mix of two of them. The
three tier pins, the three match halos, the tier badges, the confidence dots, the
freshness pill, the five provenance marks, the Texas record, thirty icons and the
brand mark and wordmark are the library's own path data. The map header and the bottom
nav are the boards' indigo900 chrome, which is what finally closed 3.6.

*What had to be derived, and why.* The library ships no token for a second or third
ink, for a tier ink that clears its own 7:1 body-text rule, for a washed tint, for a
non-text boundary, for a progress track, for press feedback, for the phone shell, or
for any of the seventeen map-ground tones. Each of those is now solved numerically as
a mix of two official colours against a stated contrast target, and the mix is written
into the source beside the value. Nothing kept its old hue.

*Two adaptations of library assets, both stated in the source.* The Estimated pin's
dashed outline is drawn in sky700 rather than sky400, because the library's own report
lists sky400 as the ON-DARK sky and it measures 1.63:1 on this map's ground &mdash; sky700
is the on-light sky the very same asset already uses for its italic i. The Scanned
pin's body rim is indigo900 rather than white, because marigold400 is 1.22:1 on the
worst ground tone and a white rim would leave the mark with no boundary; indigo900 on
marigold400 is what the library's own Scanned badge strokes that fill with.

*What the palette swap nearly broke, and what caught it.* Two regressions were found by
measurement and neither was visible: Atkinson Hyperlegible Next's figures are
proportional where Nunito's were tabular, which would have pulled every numeric column
out of line (89.21px over ten digits); and 19 of 402 text nodes fell silently out of
the UI face because it carries no glyph for the arrows, ticks and dingbats the chrome
was drawing with. Both are fixed. This is the risk the round was warned about and it
was real.

*The font.* Atkinson Hyperlegible is designed for low vision and is the better face for
this product on the merits. The original family ships only 400 and 700, which cannot
carry a three-weight ladder, so the variable "Next" cut (200-800) is used and the
ladder is re-pitched to 500 / 650 / 800 &mdash; the weights the library's own assets are
drawn in. Both it and Nunito Sans (which the official wordmark SVGs name) load from
Google Fonts alongside the existing arrangement; the file is still one self-contained
document with no local assets.

*Verified by measurement*, served over http at 390x844, across all 26 screens, in four
modes (normal, high contrast, and each at the largest text setting): 0 text-contrast
failures, minimum non-large ratio 6.42:1; 0 targets under 44x44; 0 horizontal overflow;
0 clipped text; 0 duplicate ids; 0 console errors on a cold load and after a full sweep
of every screen in both contrast modes; 402 of 402 text nodes in the UI face; digit
spread 0.00px. Pins against the drawn ground, normal and high contrast, modal and worst
tone and receded to 80%: 24 figures, all over 3:1, 22 of them better than the Round 3
figure they replace (the two that are not are the estimated and owner marks on the modal
tone in normal contrast, 4.55 and 4.83 against 4.74 and 5.35 -- every worst-case and every
receded figure improved).

**Average across all 54 criteria: 3.85** (3.8519, was 3.8333). 3.6 moved 3 to 4. Nothing else
moved, and nothing regressed.

*Is the bar met?* The bar is "nothing below 3 and the average 3.5 or better". The
average clears it comfortably and did before this round. **The bar is not met**, and
Round 4 did not aim to meet it: 6.6 still sits at **2** &mdash; there is no path in the
product by which a place reaches full confidence, which is a product decision the owner
has to make, not something a systems round can invent. Six more sit at 3 (1.3 line
length, 4.6 load animation, 6.7 step-free answered at the door, 8.1 scan sequence, 8.2
photo storage, 8.3 home-screen icon). Those seven are the whole remaining list, and none
of them is a palette or an asset problem.


**Round 5 (2026-09-05) -- the boards, the mark, and conformance to the approved
specification.** Round 4 adopted the asset library. This round adopted the thing the
library was a reproduction of, applied the boards' remaining structure, and measured the
build against `INTERACTION-MOTION-SPEC.md` for the first time in the rubric.

*The mark was wrong, and Round 4 adopted the wrong one.* Measured in the running page,
the library's `mark-primary.svg` renders its three arcs as sky, **violet**, marigold with
no white disc -- and the middle arc is the same violet600 as the pin body it sits on, so
it is invisible. One colour above the entry, not three. Its PNG exports carry the identical
defect. That is the product owner's complaint verbatim and it was a property of the asset,
not of our reproduction of it. `design/logo-mark.png`, cropped from
`07-entrymap-approved-logo.png` with the background keyed out, is embedded as a 5.8 kB
data URI and is now the mark at every display-size site. The drawn copy is deleted rather
than corrected, so there is nothing left that can drift.

*Estimated is a pin again.* The 14px ring is gone and so is the zoom rule that made the
same move one level up. Every context now draws the spec's size: 32/36/40 at overview,
40/44/48 at street, 52/56/60 selected, 24/28/32 in a card or receipt, cluster 48, live
drop 64, at the spec's z-index order. The density work moved to where the spec puts it --
clustering absorbs 52 of the 64 places at overview -- and the cluster no longer wears the
Owner-confirmed tier's violet.

*The dark chrome reached the other twelve screens.* Round 4 named `.flowhead` as the
remaining gap and Round 5 closes it: a pushed screen's title row is the board's indigo bar
with a centred title, a back chevron and a white status bar. The mechanism is worth
recording, because the obvious one does not work -- a sticky element is clamped to its
containing block's content box, so pulling the bar up with a negative margin puts it
straight back; the body gives up its top padding instead.

*Interaction conformance.* Eight of the audit's findings are closed with measured numbers
(section 9): the Estimated re-encoding, the contextual sizes and render order, the missing
fifth control state, the sheet's drag and stops and veil, the screen exit, Reduce Motion,
the cluster's impersonation, and the pin drop's tail. Nine of the numeric drifts are
retimed onto figures the spec states. Four divergences are recorded as decisions in the
source. Five feedback clauses and three pin-adjacent overlays are honestly open at 9.9.

*Two defects found by measurement that nobody had reported.* The card sheet's grip bar is
a `<span>` inside a `display:block` button, so it computed to `display:inline` and its
44x5 was ignored -- measured **0x0**. The sheet's own aria-label and its visible hint have
both been promising a handle that was never drawn, through every round. And the bottom
bar's Scan glyph was `#784410` on indigo900, a brown on a near-black, left behind when
Round 4 turned the chrome dark. Both fixed.

*Verified by measurement*, served over http at 390x844, all 26 screens walked in four
modes (normal, high contrast, and each at the largest text setting): **0** console errors
on a cold load and after a full sweep, **0** duplicate ids, **0** horizontal overflow in
any scroll container, **0** bytes above U+007E outside the base64 payloads. Touch targets:
the only controls under 44x44 are three native inputs whose containing rows are the target.
Pin contrast against the drawn ground, area-weighted census, normal and high contrast:
every identifying boundary clears 4.5:1 -- Estimated's dashed sky700 outline 4.95 modal /
**4.45 worst** (6.04 / 4.75 in high contrast), Owner's violet fill 5.26 / **4.73** (6.42 /
5.05), Scanned's indigo rim 14.62 / **13.13** (17.83 / 14.02), the cluster's indigo rim and
count and the selected keyline's outer line the same. The scan lands at **7.11s** against a
~7.6s target and an 8s ceiling. Reduce Motion completes every flow with zero unfinished
animations.

**Average across all 64 criteria: 3.84** (3.8438, was 3.8519 over 54). Ten criteria were
added, nine of them scoring 4 on work this round did; the average still moves down,
because 9.9 enters at 2 and section 9 is honest about what the earlier sections' fours
were never measuring. No existing score moved -- four criteria gained substantial new
evidence (3.6, 4.1, 4.2, 4.5) and two of those, 4.2 and 4.5, kept a 4 that the
conformance audit had shown was not yet earned, by earning it this round.

*Is the bar met?* The bar is "nothing below 3 and the average 3.5 or better". The average
clears it. **The bar is not met**, and it is worth being precise about which two lines fail
and why neither is a design problem this round could have solved.

- **6.6 (2)** -- "Nothing is 100% verified, which to me looks bad. How does a person get
  that?" There is no path in the product by which a place reaches full confidence, because
  the rung above Owner-confirmed does not exist and inventing one would break the trust
  ladder the whole product rests on. **This needs a product decision from the owner**, not
  a systems round: either a defined way an owner-confirmed entrance earns a further mark,
  or an explicit statement that Owner-confirmed IS the top and the interface should say so
  more loudly.
- **9.9 (2)** -- five feedback clauses and three pin overlays, listed above. These *are*
  within design's reach; they were outside this round's scope and are the natural first
  half of a Round 6.

Six lines remain at 3, unchanged: 1.3 (line length), 4.6 (load animation), 6.7 (step-free
answered at the door), 8.1 (scan sequence), 8.2 (photo storage), 8.3 (home-screen icon).

*What remains outside design's reach, plainly.* Three things. **The confidence ceiling
(6.6)** is a product decision, above. **Haptics (9.10)** cannot be demonstrated in a
browser on the platform this is shown on; it belongs to whoever builds the native shell.
And **8.1/8.2/8.3** -- the walkable scan, the automatic photo store and the home-screen
install -- are all held at 3 by the same boundary: a prototype can show the sequence, the
storage promise and the icon, but it cannot actually capture, upload, retain or install
anything. Those three become 4 when there is a backend and a shell, and not before.

---

**Round 6 (2026-09-05).** The round the brief ordered by damage: fix the accessibility
setting that broke accessibility, stop the whole app reading purple, and delete every
control that reports a state it does not have. Measured on the running page at 390x844
over `http://localhost`, with the Round 5 revision (`c8ed0bf`) served alongside as the
before.

**The Reduce Motion defect, and an honest correction to the brief that ordered it.** The
brief's mechanism is exactly right as a description of the code: `transition-delay` appears
zero times in the file, both the reduced-motion blocks override duration only, and `.sheet`
and `.popup` write their stale-transform guard *as* a delay. The consequence is real: a
sheet still `visibility:hidden` when a fixed 40ms timer calls `focus()`, which on a hidden
element is a silent no-op that nothing retries, with all 26 screens inert behind a modal
sheet. **It does not reproduce at HEAD**, and it is worth saying why rather than claiming a
fix. Driven with real pointer sequences, 12 sheet opens per condition: **0/12 land on
`<body>` with the setting off and 0/12 with it on**, at HEAD, before any change this round.
Round 5 rewrote the reduced-motion block from `transition-duration:.01ms` to `0s`, and a
zero duration makes the browser skip the transition altogether where a 0.01ms one runs it.
Re-injecting the pre-Round-5 value reproduces the defect precisely and completely: sheet
`visibility` reads `hidden` at 40ms *and* at 353ms, and focus is on `<body>` every time.
So Round 5 fixed the trigger by accident, one edit from returning, and left the mechanism
whole.

Fixed by construction rather than by luck, in both halves. The reduced-motion block now
zeroes `transition-delay` and `animation-delay` as well, so "no motion" no longer means "no
motion but keep the wait". And **every deferred focus in the file waits on readiness rather
than on a clock**: `focusWhenReady()` asks whether the element is laid out and unhidden,
focuses it, verifies focus actually landed, retries on animation frames for up to a second,
re-tests on every frame whether the app has navigated away, and falls back to the labelled
container, which always takes focus &mdash; so a modal sheet cannot park a screen-reader
user on `<body>` behind an inert app. It resolves in one frame when the surface is already
up, so the reduced-motion path is not slower than the animated one; it is the same path.

| Reduce Motion focus into sheets, 12 opens each | before | after |
|---|---|---|
| setting off | 0/12 on `<body>` | **0/12** |
| setting on | 0/12 on `<body>` | **0/12** |
| setting on, pre-Round-5 `.01ms` CSS re-injected | **12/12 on `<body>`** | **0/12** |
| sheet forced to stay hidden 500ms | never lands | **lands the frame it becomes visible** |

The same principle was applied to the other three animation-timed waits: the departing
screen is removed on `animationend` (listener attached before the class that starts the
animation) with the 280ms timer kept only as a watchdog; the card's post-snap map read
happens when the sheet's box stops changing rather than at a guessed 340ms; and the
focus-restore re-finds a re-rendered pin on a frame rather than at 20ms.

**The doubled `claim-confirm` screenshot was reproduced before being judged, as instructed.**
It is the harmless case. Measured on the real path: the outgoing screen is present at 50ms
and 150ms at `translateX(-10.4px)` and 0.896 opacity, carrying its own dark `.flowhead`
(which is the second status bar and the second back chevron in the screenshot), and is gone
by 300ms &mdash; on every path tried, including twelve interleaved navigations, after which
there is exactly one `.screen.active`, zero `.screen-out` and zero stranded `[inert]`. A
mid-transition capture of the exit Round 5 added, not a screen that is never removed.

**Purple, reduced structurally.** `--ground` was `lavender100`, so lavender was not an
accent, it was the app. Measured as a share of painted area over all 26 screens: **50.6%
lavender before, 0.9% after**; 55 lavender-painted elements before including fourteen
`.screen-body`, 42 after including none. `--ground` is `--white`, which is one of the eleven
official values and therefore survives the palette change that is coming; a hand-picked
near-white would not have. Selected full-width rows (the needs picker, the claim form's
verify options) go white with a violet keyline and the board's filled violet disc, while
chips keep the wash, because the board fills a chip and marks a row; the inline error box
stops being the same lavender as the calmest thing on the screen. The two lavender families
the handoff package distinguishes &mdash; "UI lavender" for surfaces, "lavender path" for
the pin's base &mdash; are separated by role (`--ui-lavender-1/2`, `--lavender-path`), both
still pointing at current values, so each is a one-line swap and they can no longer be
conflated; `--lavender-path` is a real consumer, not a name waiting for a palette, because
the pin now sits on the soft filled disc visual-language section 16 describes. The two veils
became one `--veil` at the spec's 7%, bound to the full stop only: measured opacity 0 at
peek, 0 at medium, 1 at full. **No colour was transcribed from the handoff prose.** Every
contrast figure in the file was solved against lavender100 and white is lighter, so all of
them rise: measured before and after, the set of text nodes under 7:1 is identical (32,
minimum 6.42:1, every one of them white on violet600) and the set under 4.5:1 is empty in
both.

**Controls that reported states they did not have.** *Open now* is **removed**, not hidden
and not stubbed: it was a `role="switch"` announcing `aria-checked` while changing no
result, and it could not be wired honestly, because EntryMap holds entrance evidence and no
place record carries opening hours &mdash; inventing hours to make a switch move would be a
worse defect than the inert switch on a product whose whole claim is provenance. *Distance*
is **wired**, in feet rather than miles: every place in the pilot is within 0.186 miles of
the located point, so a 0.25-to-2-mile slider could not have excluded a single one and
wiring it in miles would have produced a control that was technically connected and still
never changed an answer. Measured: Any 64 &rarr; 400 ft 22 &rarr; 200 ft 5 &rarr; Any 64.
*Freshness* asks how old the evidence is in days instead of asking "is this an estimate",
and the pilot sweep is dated across the fortnight it took rather than all on one day, so the
two windows are two answers: **7 days 7 places, 30 days 12**, from 12/12 before. *The claim
form* validates the channel the radio group actually selects, so the confirmation stops
promising an email it never collected and names the channel it did collect. *An empty
correction* no longer submits &mdash; it was being recorded in My corrections as a dated
source with no observation in it, on a product where a correction becomes a line on
somebody's evidence receipt. *The search overlay* declared `aria-modal="true"` and contained
nothing: 72 focusable elements reachable behind it, 0 inert nodes; now 0 reachable, 10
inside, Tab trapped, inert cleared on close.

**The selected pin's stacking escape is fixed as a context, not a number.** `#map` was
`position:absolute` with `z-index:auto`, so it created a stacking context only while it was
mid-pan; unpanned, the selected pin's z-index 60 competed with everything inside the screen.
Measured before, with the map's transform cleared: the pin painted **over the dark app
header (z-43) and over the map controls (z-42)**. It did not reach the sheets or the navbar,
which sit outside `.screen`'s own z-index 2 &mdash; so the brief's "a purple pin sits over
the correction form's first field" is not reproducible at HEAD, and the escape underneath it
is real and visible against the chrome. `isolation:isolate` gives the map a stacking context
unconditionally, the `!important` came off the pin, and all four surfaces now paint above it.

**Clustering at default zoom was already correct** and is reported as measured, not as
fixed: at the street level the map draws **12 pins and 9 discs counting 52 of 64 places**,
not 52 near-identical estimated marks. Round 5's rewrite of `mapLayout` removed the
categorical zoom rule and made collision and clustering do the density work at both levels.
The same applies to three other claims this round was told to verify rather than trust: the
tier badge has **one** component with two tier-dependent fills, not five treatments; feature
chips have **one** layout across seven instances, not three; headers are **one**
`.flowhead` across twelve screens beside the map's own bar, not four patterns. Those counts
were fixed by Rounds 4 and 5, after the critique was written. And the file is **pure ASCII,
0 bytes above U+007E including the base64**, at HEAD and after.

**48, not 44.** Every audit before this one measured against 44. Re-swept all 26 screens
against 48, counting a wrapping `<label>` as the target for the native control it wraps and
reading negative `::before` insets as part of the hit area: **51 controls under 48x48
before, 1 after** &mdash; a native radio inside a 358x62 label that toggles it. The figure
was written out literally at about sixty sites, which is why it could not be raised in one
move; it is `--tap` now. It cost width in exactly the place the brief predicted: the map
bar's location pill wrapped its place name to two lines, and the row gave the eight pixels
back from its gap rather than the name giving them up.

**Then the type scale, which was carrying a 4 it had not earned.** The eight steps were
`em`, so a step nested inside another step compounded. Walking every selector that declares
`font-size:var(--fs-*)` and reading the computed size of every element it matches, across
all 26 screens: **nineteen distinct pixel sizes for seven roles** before &mdash; `--fs-sub`
at five different sizes, `--fs-body` at four, one of them smaller than the step below it
&mdash; and **eight for eight steps** after, once the steps multiply one anchor. The largest
text size gained a related fix: `.screen-body` is a column flex container, so its children
were being compressed below their content while `overflow:visible` spilled the text onto the
control beneath (`.verify-opt` given 52px for 78px of content). 0 clipped and 0 squashed
controls now, at all three text sizes.

**Rubric line 9.9's five feedback clauses are all closed**, each with an explicit
reduced-motion answer and two of those in the spec's own words: confidence dots fill left to
right 70ms apart, outlined checks draw over 180ms on a dash carried by the tick's measured
21-unit path, toasts rise the spec's 12px and can be swiped away, the stale re-check clock
turns 20 degrees and returns, and the evidence receipt's height eases over 240ms instead of
switching on a `display` toggle. The bottom-navigation indicator travels now too, 44.4px to
275.4px, instead of blinking between tabs.

**Five scores in this file were fours that had not been earned, and this round says so
rather than quietly re-earning them.** 1.1 (the scale compounded into nineteen sizes), 3.1
and 3.2 (the palette carried meaning and also carried a purple cast over half the painted
area), 6.2 (the card's freshness date was a string literal that would have said "2 days
ago" whatever the data said), 7.8 (the modal claim on the search overlay contained nothing),
7.11 (measured for clipping, which was zero, and never for squashing, which was not), and
7.12 (measured against a bar the handoff package had already moved). Each is now measured
before and after in its own row. This is the failure mode the QA sweep named: a round counts
what it changed rather than measuring what remains.

**One score goes down.** **3.7 (map ground) 4 &rarr; 3.** The ground Round 3 built is
internally excellent and aimed at the wrong target: the board's map is near-white with a
faint blue-violet cast and the build's is warm cream, several steps darker. Everything
structural about it is right and only the temperature and the value range are wrong. It is
deliberately **not** hand-tuned this round: the incoming handoff package ships a `map-kit`
with a pale-lavender land base and high-contrast streets as usable layers, and re-solving
fifteen ground tones by hand days before that arrives is how a sixteenth ground gets
invented. **9.9 goes 2 &rarr; 3.**

**Average across all 64 criteria: 3.84** (3.8438, unchanged to two places &mdash; 9.9 rising
two points is offset by 3.7 falling one).

*Is the bar met?* The bar is "nothing below 3 and the average 3.5 or better". The average
clears it comfortably. **The bar is not met, by exactly one line**, and that is one line
better than Round 5 left it.

- **6.6 (2)** &mdash; "Nothing is 100% verified, which to me looks bad. How does a person
  get that?" Unchanged, and unchanged for a reason this round could not remove. The literal
  ask is a rung above Owner-confirmed, which would be a compliance claim from photographs
  and is forbidden by 6.4 &mdash; the honesty position the whole product rests on. The fair
  complaint underneath it has two answers and **neither is design's**: the map understates
  itself because 11 of 64 places are published as Scanned on-site while the operator
  photographed all 64 (the owner's own instruction, "publish the scan results for all 64
  before demo day", is the fix and it is a data job), and the confidence language that
  answers it without a new rung is already on the card. Design can draw a ceiling; it
  cannot publish the evidence that reaches it.

*What remains outside design's reach, plainly.* Four things, one of them new. **The
confidence ceiling (6.6)**, above &mdash; a data job and a product decision. **The palette**:
the handoff package names six canonical values, all six different from the ones Round 4
adopted, and it ships a manifest with hashes and a verification step. Nothing was
transcribed from prose this round and nothing should be; every colour move made here is
structural and survives the swap. The one figure it costs is body contrast &mdash; 16 text
sites at 6.42:1 against the package's 7:1 floor, all of them white on violet600, and the
package's darker violet is what raises them. **The map ground (3.7)** waits on the same
package's `map-kit`, and the pin contrast table has to be re-measured against it, because a
near-white ground raises the contrast floor for the estimated pin's outline &mdash; the one
marker with no halo &mdash; and Round 4's table was measured on the warm ground. **Haptics,
and 8.1/8.2/8.3** &mdash; the walkable scan, the automatic photo store, the home-screen
install &mdash; are unchanged: a prototype can show the sequence, the promise and the icon,
but it cannot capture, upload, retain or install anything.

*And one thing that is inside design's reach and is deliberately not built.* The spec names
a freshness clock overlay for stale pins and the library ships the asset, and it would not
break the recolouring rule &mdash; it is a badge, not a tint. It is held back because the
trust legend teaches three marks and this would be a fourth glyph with no key, and because
icon soup around pins was the original complaint and the product owner has rejected a pin
accessory twice. Recorded on 9.10 and put to him, rather than settled silently.

---

**Round 7 (2026-09-05).** The round that stopped aiming at a reasoned target and took the
real one. Measured on the running page at 390x844 over `http://127.0.0.1`, with the Round 6
revision (`c8ed0bf`) served alongside as the before, and every number below re-taken from
that page rather than carried forward.

**The map ground, before and after.** Before: `--g-ground #EFE8DA`, a warm sand, with a
seventeen-tone family of putty footprints, two-step cast shadows, lit edges, a marigold
plaza and a green canopy `#DEE1D2` solved as a marigold+sky mix, "because the approved
palette contains no green". Three rounds had derived that surface by hand from something
other than the artwork: Round 3 from two reference sketches, Round 4 by solving the
sketch's CIE lightness onto the old palette, Round 6 from a colour table sampled off a
board. After: the kit's own five layers, in the kit's order, on the kit's values &mdash;
land `#F5F2FC` with a violet600 dot pattern at .045, blocks `#E8E1F7` with a `#CFBCEE`
edge, roads `#CFBCEE` at .55 under white at the kit's 62/48 casing ratio, places `#76BCFD`
at .34, labels `#1E1142` at 700. Seventeen ground tones become nine. The marigold plaza,
the green canopy and every cast shadow are gone, because the kit's blocks layer has none of
them and neither does the board. The tree canopy is the kit's `places` layer, which is what
"the board in the other one is white and blue" was pointing at. Full evidence and the pin
table on **3.9**; **3.7** rises from Round 6's self-lowered 3 to 4.

**The palette.** Ten of eleven values moved, not six. The ledger and this round's brief both
say six; counted against the block they replace, everything except `--white` changed, and a
twelfth token arrives that the old library had no equivalent for (`--lavender-path
#CFBCEE`). 150 literal hex occurrences were rewritten, every derived value in the file was
re-solved on the canonical bases, and zero occurrences of the ten retired values remain
outside the one comment that records what moved. The values were taken from
`entrymap-build-ready/asset-library/tokens/variables.css`, cross-checked against
`tokens/design-tokens.json` and against `PACKAGE-MANIFEST.json`, whose sha256 for that file
matches the bytes on disk. Nothing was transcribed from a prose table, including the one in
the brief &mdash; which is how the count came out different.

**What the canonical violet bought.** White on the primary violet was 6.42:1 at **20** sites
(Round 6 reported 16, the brief repeats 16, and a visible-only sweep catches 15 or 17
depending on what has rendered; the deterministic DOM count is 20). All 20 now measure
7.38:1. The marigold button's label, whose derived ink had been solved on the retired
`#FFBF24`, measured 6.43:1 on the canonical `#FDB327` and is now indigo900 at 9.60:1. After
both: **1,303 visible-ink samples, and 1,012 then 1,464 static samples on two runs, 26
screens x 4 modes, 0 below 7:1 every time, minimum 7.38:1.** Before, the same sweeps read 43 instances under the floor. **7.14**
is now a scored bar with no named exceptions left.

**Two floors are scored rather than noted.** 7.13 measures 48x48 across 810 control
measurements on the 26 screens plus 72 more inside all seven sheets, using the union of the
control box, any activating `<label>` and any declared `::before` hit extension. It found one
real failure that every screen-only sweep before it had missed, because the control lives in a
closed sheet: the filter sheet's `Reset` was 45.8 x 48. Fixed, and the count is now 0 of 882.
7.12 is kept as the historical 44px record.

**A defect between rounds, found and fixed.** Closing the map card with its Close button did
not return focus to the pin, at Round 6 HEAD and here, 6 trials out of 6 from a clean load:
with motion focus stayed on the card's off-screen `<h2>`, and with reduced motion it landed
on `<body>`. `closeSheets()` called directly returns focus correctly; the card's own drag
machinery clears `openSheetId` before the `data-close` handler runs, so the return branch
was skipped. Neither the round that wrote the return path nor the round that wrote the drag
stops could have caught it alone. After the fix, 6 trials in both motion modes: 5 of 6
return to the exact opening pin, 6 of 6 land on a labelled focusable element, 0 on `<body>`.
**A second pre-existing defect, also fixed:** turning High Contrast on from Accessibility
and then going to the map left the map blank &mdash; the ground SVG measured 54 bytes, the
empty-box guard &mdash; because the toggle re-rendered while `#screen-map` was still
`display:none` and a screen becoming visible is not a resize. One `ResizeObserver`, armed
once, redraws it the first time the element has a real box.

**Screen-by-screen parity, as a count instead of an opinion.** All 25 exports were read and
checked against the running build: 25 of 25 have a build screen or state, 0 missing; six
differences recorded on **9.11**, of which one is worth acting on (the `evidence-recheck`
state ships complete but unreachable, because no seeded place is older than 180 days); and
8 build screens have no export at all, so a third of the build cannot be scored this way.

**Re-verified rather than assumed, because a palette and a ground change is exactly how
these get silently undone.** Round 1: polite live region present, six modal sheets
`role="dialog" aria-modal="true"` and labelled, focus to the sheet heading on open in both
motion modes, background `inert` (35 siblings) with the scrim on, Escape closing and
clearing every `inert` flag to 0. Round 2: tip anchoring intact (`PIN_VB -8 1 112 95.1`,
zero-size anchor). Round 4: Atkinson Hyperlegible Next loaded, `font-variant-numeric:
tabular-nums` at the root, ten 1s against ten 0s at 40px/650 differ by **0.00px**. Round 5:
`PIN_SIZE` byte-matches `pin-hierarchy.json` on all twelve values, `PIN_Z` on all seven,
`CLUSTER_PX` 48, `setUnavailable` present. Round 6: `--tap` is 48px, the eight-step scale
still multiplies one `--root-fs`, the map keeps its unconditional `isolation:isolate`
stacking context. **And the rule that matters most on this surface:** no trust pin is
recoloured for selection, match, freshness or provenance &mdash; proved structurally rather
than by eye, by stripping the overlays and comparing the remaining tier art byte-for-byte
across 7 states x 4 sizes x 3 tiers: 84 of 84 identical.

**Where the kit is silent, and where it is wrong.** The kit has no street hierarchy, no
building footprints, no plaza, no courtyard, no high-contrast variant and nothing to say
about pan or zoom; those are named on 3.9 rather than invented. Two things inside the
package disagree with each other and both are recorded: `map-kit/map-kit-manifest.json`
records a single sha256 per variant that is the PNG's, leaving the SVG unhashed (corrected
from "stale" on re-measurement; see `design/package-defects.md`); and `asset-library/svg/pins/estimated.svg` draws the Estimated outline
in sky400, which is 2.02:1 against the pin's own white fill and 1.36:1 on the kit's darkest
filled tone, where the approved board draws it in a fully saturated blue. The artwork is
trusted over the asset and the token used is the canonical on-light sky.

**Deliberately not built.** The freshness clock overlay, again: it would need a legend entry
to be honest and pin accessories have been rejected twice. Left as a decision for the owner,
not settled here.

**Where the bar stands.** 70 criteria, average **3.843**, and **one line below 3**: 6.6, the
confidence ceiling, at 2 &mdash; unchanged, and unchanged for the same reason Round 6 gave.
Nothing on that line is design work: it needs owner-confirmed entrances to exist in the data
so the map stops reading as a product that knows nothing, without inventing a rung above
Owner-confirmed. **The bar is not met, and it is not met by exactly that one line.** Nine
lines sit at 3: 1.3 (line length, a measurement that is already right at the top of its
band), 4.6, 6.7 (step-free coverage, engine work), 6.8 (the hybrid boundary is now in the
canon but the Swift surface still carries the retired palette, with no ticket and no owner),
8.1/8.2/8.3 (capture, storage and install, which a prototype cannot finish), 9.9 and 9.11.
Of those, only 9.11 and 6.8 are movable by a design round; the rest are backend, shell, data
or another team's code. **That is the escalation, not the next iteration.**


**Round 8 (2026-09-05).** The round that made every mark on the map readable without asking,
and removed the ones that were not. Assembled from the owner's own decisions (D36, D37, D38,
D43) and from the three Round 7 re-audits, and deliberately narrow: eleven items, nothing
widened into the rest of either punch list.

**The Estimated mark is J1, taken verbatim from `design/estimated-mark-gallery-4.html`.** A
solid sky700 teardrop, white fill, and the owner's own doorway glyph &mdash; two rounded posts
and one lintel as `M32 60V22h32v38` with round caps and joins at stroke 4, and three r2.2 dots
at x 40/48/56 on y 60 across the open threshold. The dashed `7 6` outline and the italic serif
"i" are gone: **0** occurrences of either remain in the file. The dots are in their own
`<g class="est-threshold">` so that dropping to gallery candidate J3 is one line. Re-measured
against the tones the ground actually paints, in both contrast modes &mdash; land 5.64, block
4.91, block edge 3.59, place accent 3.08, white road 6.24, own fill 6.24; in high contrast
9.76 / 8.50 / 6.21 / 5.33 / 10.79. Floor **3.08:1**. The mark changed on every surface at once
(map at both zooms, trust ladder, card, receipt, list, onboarding tiles) because `pinSVG()` is
the single composition point; each surface was counted rather than assumed, and on every one
the doorway-path count equals the threshold-group count and the dashed and italic counts are
zero.

**The confidence dots are gone, and their meaning was rescued on the way out.** `pinDots()` is
deleted, not hidden: **0** call sites, no flag to switch it back on. Checked before deleting
it &mdash; the brief said confidence "stays" in `placeSentence()` and it was **not there**, so
removing the dots would have deleted the only sighted and the only spoken carrier in the same
edit. `placeSentence()` now says "Confidence high / medium / low" on the same thresholds the
card's tile uses; **12 of 12** pins carry it.

**The map now draws all three match states.** `renderPins` computed
`m.state !== 'unknown' ? m.state : null`, so `match-unknown` rendered **zero** times while
`matchHalo('unknown')` drew the library's dotted ring correctly and the legend line documented
the omission in words. All three draw now (measured with a wheelchair profile: 2 good, 4
partial, **6 unknown** across 12 pins), the legend keys the third with a swatch in the halo's
own token, and the 20% `recede` dim that stood in for it is removed, because a positive mark
and a dim for the same fact is one carrier too many.

**Clusters are tested against pins.** The separation pass existed and was aimed at the wrong
circle: the pin's tip, not its drawn head. Measured before, against the circle the pin
actually paints, a disc covered **100.0%** of one 44px head at street and **95.8%** of a 36px
head at overview &mdash; worse than the audit's 43.3% / 21.0%, not better. After: **0.0000** in
all five configurations tested, with all 64 places still accounted for and no pin absorbed.
Tap-target crowding improved as a side effect (minimum centre distance 7.1 &rarr; 27.5px at
street, 11.7 &rarr; 21.2px at overview) but is **not** resolved, and is named for Round 9.

**Reduced motion has a floor and keeps its pacing.** There was no
`@media (prefers-reduced-motion: reduce)` rule in the file at all. Two mechanisms now: the
class moved from `.phone` to `<html>` and is set by an inline `<head>` script before `.phone`
is parsed (26 CSS selectors across 17 rules rewritten `.phone.rm` &rarr; `.rm .phone` at
identical specificity, so there is still exactly one copy of the rules), and a real `@media` block mirrors the universal
transition rule as a backstop &mdash; forced on, it takes the card sheet from
`transition-delay 0.32s` to **0s**, which is the seam a duration-only floor leaves open.
*Correction to the audit:* on this machine, over 5 cold-fetch loads, `applyPrefs()` ran
**41.8-57.2ms before** first paint, so the reported 92-500ms window did not reproduce here;
the structural exposure is real anyway. And the setting stopped deleting the scan's pacing:
**4.9ms with every check in one frame** becomes 2,504.9 / 4,006.5 / 5,505.7ms with the
announce-then-hold restored, so "Checks complete" now lands **1,577.5ms before** the screen
changes instead of 27.8ms after it.

**Sheets stack, focus is asserted, and the coach stops.** A sub-sheet no longer hands off: the
card is a stack level, restored at the position it held, with focus returned to the control
that opened the sub-sheet (verified two levels deep). The focus fallback is unconditional and
followed by a post-condition that forces focus out of a closed sheet; it was proven by forcing
the exact failure and it fired **0** times in 74 unforced post-fix close trials &mdash; the 1-in-20
strand the audit reported did not reproduce here, in 74 post-fix trials or in 83 at HEAD. The capture coach ran forever in both modes
(4 changes in 7.2s with reduced motion on); it is now static under reduced motion (**0**
changes in 9s, no interval) and a single cycle otherwise, its last change at **4,461ms** so
the whole auto-update sits inside WCAG 2.2.2's five seconds without needing a control.

**What this round did not do, and what it found worse than described.** It did not touch the
match halos' line styles, did not recolour any pin for state, and did not adopt
`estimated.svg` from either package. It did not act on a11y N6 (the duplicate `ev-box` id),
which the brief records as false and which is still false: **1** occurrence. It did not sweep
all 189 controls for the 48px floor &mdash; only the 43 on the three surfaces it changed, all
of which pass. And it found a layout defect that predates it and that it has reduced but not
closed: with a needs profile applied, the map's floating column (filter chips + key card +
match strip) overran the FAB row by **50.7 / 54.3 / 62.3px** at the three text sizes at Round
7 HEAD. The new legend row costs 34px; compacting the card gives back 46, so the overrun is
now **46.9 / 49.4 / 55.1px** &mdash; smaller than it was found, at every size, with one more
mark taught. It is still an overrun, it is still wrong, and it is a Round 9 item: three
floating elements and a 48px FAB row do not fit in 196px of map.

**Two new criteria, both scored 3 rather than 4.** 5.7 (every mark is taught where it is seen)
because the selection keyline and the lavender match disc are still keyed nowhere. 5.8 (one
line style, one meaning) because the map is clean &mdash; the only broken strokes drawn inside
`#map` are the dashed partial halo and the dotted unknown halo &mdash; while off the map a
dashed border still means "empty slot" in 6 stylesheet declarations as well as "partial match"
in 3.

**Where the bar stands.** 72 criteria, average **3.819** (down from 3.843 because two new
criteria entered at 3, not because anything regressed; the 70 previously scored are unchanged
or better-evidenced). **One line below 3:** 6.6, the confidence ceiling, at 2 &mdash;
unchanged, and unchanged for the reason Rounds 6 and 7 both gave: it needs owner-confirmed
entrances to exist in the data, which is not design work. **The bar is not met, and it is not
met by exactly that one line.** Eleven lines sit at 3: 1.3, 4.6, 5.7, 5.8, 6.7, 6.8, 8.1, 8.2,
8.3, 9.9 and 9.11. Of those, 5.7, 5.8, 9.9 and 9.11 are movable by a design round; 6.7, 8.1,
8.2, 8.3 and 6.8 are engine, shell, data or another team's code, and 1.3 is already at the top
of its band. **6.6 remains the escalation.**
