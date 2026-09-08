# EntryMap prototype — accessibility audit

**Target:** `design/phone-app-prototype.html` — 4,620 lines, working copy as of 2026-09-05 12:52. 26 screens + 8 sheets.
**Viewport:** 390×844 (the file's `@media (max-width:767px)` "real-phone mode" — no bezel, `100dvh`, the app *is* the screen).
**Method:** served over `python -m http.server` from `design/`, driven in the browser pane. Every screen and sheet visited via the app's own navigation and via `showScreen()`. Evidence gathered from the live DOM: computed styles, WCAG relative-luminance contrast math with alpha compositing, accessibility-tree reads, `elementFromPoint` hit-testing of every control, focusable-element sweeps per screen, live-region diffing over time, and both preference axes (Text size × High contrast × Reduce motion) exercised on all 26 screens.

**Read-only. No file under `design/` was modified except this report.** This supersedes the 2026-09-04 audit of the 3,545-line snapshot; where a previous finding is now fixed or still open, it is marked.

---

## Verdict

The **content layer is excellent** and the **presentation layer is largely correct**. Text contrast, colour independence, touch targets, reduced motion, text scaling, alt text and the list-view text equivalent are all genuinely good — several of them better than most shipped products. Confirming that is real value and it is set out in full below.

The failures are almost entirely **behavioural**: what happens when a screen changes, when a sheet opens, when something goes wrong, and when a state exists only as a CSS class. A screen-reader user can read every screen in this app. They frequently cannot tell **which screen they are on**, **that anything happened**, or **why the button they just pressed did nothing**.

For an app whose users are disabled people, the single most serious defect is #2: **two publish actions are silently blocked with the explanation delivered only through a `<div>` that no assistive technology will ever read.**

- **10 blocking defects**
- **18 improvements**
- **11 things confirmed correct** (section at the end — please do not regress these)

---

## Blocking defects

Ordered by harm to a disabled user attempting a core task.

---

### B1 · Every screen change is silent, and focus is dropped on the floor

**Screens:** all 26. **Elements:** `showScreen()` (line 3683), `.screen{display:none}` (line 78).

**What a user experiences.** A screen-reader user taps "Allow camera". The camera screen appears. Nothing is announced. Focus is now on `<body>`, because the button they activated was inside a container that is now `display:none`. They must Tab from the top of the document to find out where they are — and there is no heading or landmark telling them. A keyboard-only user has the same problem 26 times over: every navigation resets them to the document start.

**Measured evidence.**

`showScreen()` announces only the screen's `aria-label`:

```js
const scr=document.getElementById(id);
if(scr && scr.getAttribute('aria-label')) announceUI(scr.getAttribute('aria-label'));
```

**12 of 26 screens have no `aria-label`, so nothing is announced at all:**
`screen-map`, `scan-primer`, `scan-capture`, `scan-processing`, `scan-review`, `scan-done`, `ob-welcome`, `ob-location`, `ob-needs`, `claim-find`, `claim-confirm`, `claim-track` — i.e. **the entire scan flow, the entire onboarding, the entire claim flow, and the home screen.**

Walked live: Profile → `startScan()` → primer → capture → processing → review → done. After all six transitions:

| step | `#sr-announce` content | `document.activeElement` |
|---|---|---|
| scan-primer | `"Profile"` (stale, from 4 screens earlier) | `#list-toggle` (now hidden) |
| scan-capture | `"Profile"` | `BODY` |
| scan-processing | `"Profile"` | `BODY` |
| scan-review | `"Profile"` | `BODY` |
| scan-done | `"Profile"` | `BODY` |

`showScreen()` never moves focus. No screen has `tabindex="-1"` on a container to receive it.

**Fix.** (a) Give every `.screen` an `aria-label`. (b) In `showScreen()`, after the class swap, move focus to the new screen's first heading (or a `tabindex="-1"` wrapper) rather than announcing into `#sr-announce` — a focus move announces the screen *and* fixes the keyboard start position in one action. Keep `announceUI` only for screens that have no heading. (c) Give `scan-capture` and `screen-profile` a heading (see I5).

---

### B2 · The toast is not a live region — and it is the only channel for two blocked publishes

**Screens:** app-wide; critically `claim-confirm` and `ow-photos` / `ow-review`. **Element:** `#toast` (line 2316), `toast()` (line 4582).

**What a user experiences.** A blind business owner fills in the claim form, presses **Submit claim**, and *nothing happens*. No error, no announcement, no focus move, no change they can perceive. The reason — "Please confirm you're authorized to manage this listing" — is written into a `<div>` with no role and no `aria-live`, shown for 2.8 seconds, and then removed. The same is true of "Replace or crop the flagged photo first", which blocks publishing an entrance update. This is a dead end reachable only by sighted users.

**Measured evidence.**

```html
<div class="toast" id="toast"></div>
```
No `role`, no `aria-live`, no `tabindex`, no dismiss control. `toast()` sets `textContent` and clears it after 2800 ms. A sibling live region *does* exist (`#sr-announce`, `role="status" aria-live="polite"`, line 2317) and `announceUI()` is used correctly elsewhere — **`toast()` simply never calls it.**

Live probe, `claim-confirm`, authorisation box unchecked, **Submit claim** pressed:

```
screenAfter:            "claim-confirm"   (blocked)
toast:                  "Please confirm you're authorized to manage this listing"
toast role / aria-live: null / null
#sr-announce:           "Manage entrance photos"   ← stale, unrelated
#claim-authz aria-invalid:      null
#claim-authz aria-describedby:  null
focus moved to:         (unchanged)
```

Live probe, `ow-photos`, **Publish update** with the face-flagged photo present:

```
screenAfter:  "ow-photos"   (blocked)
toast:        "Replace or crop the flagged photo first"
#sr-announce: ""
```

At the app's own **Larger** text setting the toast is also visually truncated: `white-space:nowrap`, `max-width:92%`, measured `scrollWidth 380 > clientWidth 359` — the tail of the message is cut off. *(Flagged in the 2026-09-04 audit; still open.)*

**Fix.** (a) Route `toast()` through `announceUI()` so every toast is announced once. (b) For the two blocked publishes, do not use a toast at all: render an inline error adjacent to the offending control, set `aria-invalid="true"` and `aria-describedby` on it, and move focus to it. (c) `white-space:normal` on `.toast`.

---

### B3 · The processing checklist tells a screen reader all three checks are already done

**Screen:** `scan-processing`. **Elements:** `.checkitem .ci-dot` (lines 1707–1710, CSS 486–492).

**What a user experiences.** The scan is running. A sighted user sees three empty circles that fill in one at a time. A screen-reader user, at t=0, before any check has completed, hears: **"✓ Doorway framed. ✓ Entry path visible. ✓ Photo quality checked."** The visual and non-visual presentations say the opposite of one another, and the non-visual one is wrong.

**Measured evidence.** The tick is a literal text node hidden by colour only:

```css
.checkitem .ci-dot{ … color:transparent; }
.checkitem.done .ci-dot{ … color:var(--marigold-ink); }
```
```html
<div class="checkitem" id="ck-1"><span class="ci-dot">✓</span>Doorway framed</div>
```

Accessible-text walk of `.checklist` at t=0, no `.done` classes present:

```
"✓ | Doorway framed | ✓ | Entry path visible | ✓ | Photo quality checked"
```

The same transparent-`✓` pattern leaks in two more places: `.persona .p-ring` (line 361) — every unselected need button announces as e.g. *"Wheelchair, Step-free entry, ramp, wide door, ✓"* while reporting `aria-pressed="false"` — and `.tl-dot` on the claim timeline (line 895).

**Also on this screen:** the pending checklist text is **2.47:1**. `.checkitem{opacity:.42}` composites `--ink #241F3A` over `--ground #EDEBFA` to `#9995A9` at 14.25 px / weight 800 (not "large text", so 4.5:1 applies). *(Flagged 2026-09-04; the reduced-motion path was fixed — `.scanscreen.reduced .checkitem{color:var(--faint)}` measures 6.34:1 — but the normal path was not.)*

**Fix.** (a) `aria-hidden="true"` on `.ci-dot`, `.p-ring` and `.tl-dot`, and carry the state in ARIA instead: give each `.checkitem` `role="listitem"` inside a `role="list"` and append a visually-hidden " — done" when `.done` lands, or simply `aria-hidden` the whole checklist and let `#proc-live` narrate. (b) Replace `opacity:.42` on `.checkitem` with an explicit colour that clears 4.5:1 (`--faint #575170` already does, at 6.34:1 — the reduced-motion rule proves it).

---

### B4 · Match state never reaches the pin, and 64 pins sit in front of every other map control

**Screen:** `screen-map`. **Elements:** `.pinbtn` aria-label (line 2626), `.halo` (lines 96–104), `#pins` DOM position (line 1225).

**What a user experiences.** With "Wheelchair" selected, ten pins acquire a match halo. Royal Blue Grocery is a **Good match, 3 of 3 needs**. A screen-reader user moving across the map hears only *"Royal Blue Grocery — Scanned on-site."* The match — the single thing the user set their needs to learn — is delivered exclusively as a 3 px ring around the pin. Separately, a keyboard user landing on the map must press Tab **64 times** before reaching Search, the list toggle, Filters or My needs.

**Measured evidence.**

```js
b.setAttribute('aria-label', p.name + ' — ' + tierName(p.tier));
```
That is the whole accessible name. From the live accessibility tree with a persona active:

```
button "Royal Blue Grocery — Scanned on-site"    ← has class "halo good"
button "Which Wich — Scanned on-site"            ← has class "halo partial"
```

Halo pins: 10. Pins whose name mentions the match: 0. Freshness and distance are likewise absent from the pin.

The visual halo *is* line-style differentiated (`solid` / `dashed` / none), so it is not colour-alone for sighted users — but the halo colours measure 4.58:1 (good, `#1B7A3D`) and 6.35:1 (partial, `#0E5E66`) against the ground, i.e. two dark rings that differ mainly in dash pattern at 3 px.

Tab order: `#pins` is the first child of `#screen-map .screen-body`, so all 64 `.pinbtn`s precede `.apphead`, `.map-ctls`, `.map-fabs`. Total focusables on the map screen: **82**.

The **list view is the mitigation and it is excellent** (see W4) — but its toggle is 64 tab stops away.

**Fix.** (a) Compose the pin's `aria-label` from the same sentence `renderList()` already builds — name, entrance, tier, match, freshness, distance. The function exists; reuse it. (b) Move `#pins` after the header/controls in DOM order, or give the pin layer `role="group"` with a skip link, so Search and the list toggle come first. (c) Consider `aria-label` on the good-match pin including "Good match" so the existing `.pin-label` chip is not the only carrier.

---

### B5 · Sheets: focus never enters, never returns, is never trapped, and Escape does nothing

**Sheets:** all 8 (`sheet-card`, `sheet-needs`, `sheet-filters`, `sheet-receipt`, `sheet-trust`, `sheet-correct`, `sheet-privacy`, plus `#search-ov`). **Element:** `openSheet()` (line 3067).

**What a user experiences.** A keyboard user presses **Filters**. The sheet slides up and the scrim dims the map. Their focus has not moved — it is still on the Filters button *behind* the scrim. Tab walks them through the map controls underneath, which they cannot see and cannot use. Escape does not close the sheet. There is no way out except finding the ✕ by tabbing forward through the whole sheet.

**Measured evidence.**

```js
function openSheet(id){
  document.querySelectorAll('.sheet').forEach(s=>{if(s.id!==id)s.classList.remove('on')});
  document.getElementById(id).classList.add('on');
  scrim.classList.toggle('on', id!=='sheet-card');
}
```
No focus move, no `aria-modal`, no `inert` on the background, no focus return in `closeSheets()`.

Live probe, "My needs" sheet opened via the FAB:

```
sheet open:                    true
role:                          "dialog"
aria-modal:                    null
document.activeElement:        BUTTON#nav-map   ← never moved
focusables outside the sheet:  76               ← all still reachable
```

Escape probe on `#sheet-filters` — dispatched at `document` and at the sheet: `before: open`, `after: open`. The only `Escape` handler in the file is on `#search-in` (line 3422).

Search is the one exception and it is half-right: `openSearch()` focuses `#search-in` after 50 ms ✓, but `closeSearch()` leaves focus on the now-`hidden` input rather than returning it to `#search-btn`.

**Credit where due:** closed sheets are correctly removed from the tab order — `.sheet{visibility:hidden}` with a delayed transition (lines 220–229). That is the right mechanism and it works.

**Fix.** (a) On open, move focus to the sheet's heading or close button. (b) Trap Tab within the sheet while the scrim is on (or set `inert` on `.phone > :not(.sheet.on)`), and add `aria-modal="true"`. (c) Add a document-level `Escape` handler calling `closeSheets()`. (d) In `closeSheets()`, restore focus to the element that opened the sheet. (e) `closeSearch()` should return focus to `#search-btn`.

---

### B6 · Saved entrances, My scans and My corrections destroy their rows' button role

**Screens:** `screen-saved`, `screen-contrib` (both tabs). **Elements:** `renderSaved()` line 3563, `scanRowHTML()` line 3761, `renderCorrections()` line 3510.

**What a user experiences.** Every row in these three screens is a `<button>` carrying `role="listitem"`. ARIA role overrides the implicit role, so a screen reader announces *"Royal Blue Grocery, 241 W 3rd St, Scanned on-site… list item"* — not "button". The user is not told the row is actionable, and in browse mode it will not be offered as a control. Tapping a saved entrance to open its card is the entire purpose of the screen.

**Measured evidence.**

```html
<button class="prof-row saved-row" role="listitem" data-saved-open="…" aria-label="…">
```

Live DOM inspection:

| container | container role | children |
|---|---|---|
| `#saved-list` | `list` | 2 × `BUTTON` with `role="listitem"` |
| `#your-scans` | `list` | 4 × `BUTTON` with `role="listitem"` |
| `#corr-list` | `list` | 3 × `BUTTON` with `role="listitem"` |
| `#list-rows` | `list` (real `<ul>`) | `LI` > `BUTTON`, no role override ✓ |

The list view already demonstrates the correct pattern in the same file.

**Fix.** Wrap each row in `<li>` inside a `<ul role="list">` — as `renderList()` does — and drop `role="listitem"` from the buttons.

---

### B7 · Non-text contrast: seven control indicators below 3:1, and the focus ring fails on the two dark screens

**Screens:** app-wide; focus ring specifically on `scan-capture` and `ob-welcome`/`ob-splash`.

**What a user experiences.** A low-vision user cannot see whether a toggle is on or off without reading the label, cannot see the edge of any text field or unselected chip, and cannot see the scan progress ring fill. On the camera screen the focus ring is a dark purple outline on a dark aubergine field — and **turning High contrast on makes it worse, not better.**

**Measured evidence.** All ratios computed from the live tokens, alpha composited. WCAG 1.4.11 requires 3:1 for user-interface component state indicators and boundaries; 2.4.11/1.4.11 requires 3:1 for focus indicators.

| # | Indicator | Colours | Ratio | Need |
|---|---|---|---|---|
| 1 | `.toggle` off track vs card | `#D9D5EC` / `#FFFFFF` | **1.43** | 3.0 |
| 2 | `.toggle` knob vs its own track | `#FFFFFF` / `#D9D5EC` | **1.43** | 3.0 |
| 3 | Field / chip border, all forms | `#E6E2F4` / `#FFFFFF` | **1.27** | 3.0 |
| 4 | `.p-ring`, `.tl-dot`, `.ci-dot` outline | `#C9C2E2` / `#FFFFFF` | **1.71** | 3.0 |
| 5 | Processing ring fill vs its track | `#F0A32F` / `#DDD8F0` | **1.52** | 3.0 |
| 6 | Processing ring track vs ground | `#DDD8F0` / `#EDEBFA` | **1.18** | 3.0 |
| 7 | Scanned-on-site pin vs map ground | `#F0A32F` / `#EDEBFA` | **1.79** | 3.0 |
| 8 | Estimated pin fill vs map ground | `#FFFFFF` / `#EDEBFA` | **1.18** | 3.0 |
| 9 | Estimated pin stroke vs map ground | `#5B8DEF` / `#EDEBFA` | **2.75** | 3.0 |
| 10 | **Focus ring on `scan-capture`** | `#7053C5` / `#241F3A` | **2.80** | 3.0 |
| 11 | **Focus ring on `scan-capture`, High contrast on** | `#0E0B1C` / `#241F3A` | **1.23** | 3.0 |
| 12 | Focus ring on `ob-welcome` / `ob-splash` | `#7053C5` / `#1E1543` | 3.00 | 3.0 (exactly at threshold) |

Rows 10–11 come from `.phone :focus-visible{outline:3px solid var(--purple)}` (line 938) and `.phone.hc :focus-visible{outline-color:var(--ink)}` (line 1182). The HC override is written for light backgrounds and inverts the intent on the two dark screens. Confirmed visually: the ring around `#cancel-x` on the capture screen is a purple outline on a dark purple field.

Rows 7–9 mean **the middle tier's pin — the one the whole product turns on — is the least distinguishable object on the map.** The Owner pin passes (`#7053C5` / ground = 4.79). High contrast does not help: at `--ground:#E4E1F6` the marigold pin measures 1.64.

The one place HC does help: `.toggle` off becomes `#8E88A8` = **3.37:1** ✓, which shows the fix is already understood — it just is not the default.

**Fix.** (a) Darken `.toggle` off state to the HC value or add a border. (b) Give `.field select/textarea/input`, `.filtchip`, `.searchfield` and `.state-card` a boundary at ≥3:1 (e.g. `#8E88A8`). (c) Add a contrasting outline or a darker stroke to the marigold and estimated pins against `--ground`. (d) Make the focus ring background-aware: a two-tone ring (white outer + purple inner) works on every surface; at minimum override `:focus-visible` on `#scan-capture`, `#ob-welcome`, `#ob-splash` and the HC variants of all three. (e) Darken the processing ring track, or place the fill against the page rather than the track.

---

### B8 · The bottom nav's current tab is exposed to nothing, and is a 1.05:1 hue change visually

**Element:** `.navbar` (line 2299), `.navbtn.on` (line 199).

**What a user experiences.** A screen-reader user cannot tell which tab they are on. A low-vision user cannot either — the only difference between the selected and unselected tab is `#4B2E9E` vs `#4A4463`, two colours of near-identical luminance, with no underline, pill, weight change or icon fill.

**Measured evidence.**

```
selected (--purple-ink #4B2E9E) vs unselected (--sub #4A4463) = 1.05 : 1
```

Live attribute inspection of all three nav buttons:

```
nav-map:     aria-current null, aria-selected null, aria-pressed null
nav-scan:    aria-current null, aria-selected null, aria-pressed null
nav-profile: aria-current null, aria-selected null, aria-pressed null
```

The `.on` class is the *only* representation of the current tab, in either channel.

**Fix.** (a) `aria-current="page"` on the active nav button (and remove it from the others). (b) Add a non-colour visual cue — a filled icon, a top indicator bar, or a weight change — since 1.05:1 is not a perceivable difference for anyone.

---

### B9 · The card sheet's three positions are a keyboard-only affordance with no exposed state and a 26 px handle

**Element:** `#sheet-card` (line 2168), `#card-grip` (line 1169), `setCardPos()` (line 2692).

**What a user experiences.** The peek/medium/full handle is the only way to reveal the rest of a place card. It is **390 × 26 px** — well under 44 px in height — and it exposes no expanded state, so a screen-reader user is told "Expand card — tap or drag the handle" but never which of the three positions they are in or that more content became available.

**Measured evidence.**

```
#card-grip bounding box:  390 × 26      (no pseudo-element hit expansion)
aria-expanded at peek:    null
aria-expanded at medium:  null
aria-expanded at full:    null
```
`.sheet-grip-btn{min-height:26px;padding:8px 0 0}` (line 683).

The `aria-label` *does* change per position (verified across all three) — good — but a changing label on the control is not a state on the region, and nothing announces that the card's content grew.

Separately: `#sheet-card` declares `role="dialog"` but is deliberately **non-modal** — `openSheet()` explicitly suppresses the scrim for it (`scrim.classList.toggle('on', id!=='sheet-card')`), and 93 focusables remain outside it. `role="dialog"` sets a modal expectation the sheet does not honour.

**Fix.** (a) Give `.sheet-grip-btn` `min-height:44px` (padding, not visual size — the 5 px grip bar can stay). (b) Add `aria-expanded` reflecting peek(false)/medium/full(true) plus `aria-controls` pointing at `#card-content`, and announce the position change through `#sr-announce`. (c) Change `#sheet-card`'s role to `region` (or `complementary`) with its `aria-label`, and keep `dialog` for the seven sheets that do dim the map.

---

### B10 · Two selection controls expose no state at all; one of them is colour-alone visually too

**Screens:** `sheet-filters` (Freshness), `claim-find` (which entrance you manage).

**What a user experiences.** In Filters, the Any / 7 days / 30 days control announces as three plain buttons — a screen-reader user cannot tell which is active, and cannot tell that pressing one changed anything. In the claim flow, the choice of *which of three Royal Blue Grocery entrances you are claiming* is shown by border colour only, with no ARIA and no second visual cue.

**Measured evidence.**

```
#filt-fresh                role: null   (no radiogroup, no group)
  button "Any"      .sel   aria-pressed: null, role: null
  button "7 days"          aria-pressed: null, role: null
  button "30 days"         aria-pressed: null, role: null

.claim-result[0]  .sel=true   border rgb(112,83,197)   aria-pressed/checked: null
.claim-result[1]  .sel=false  border rgb(230,226,244)  aria-pressed/checked: null
.claim-result[2]  .sel=false  border rgb(230,226,244)  aria-pressed/checked: null
```

Selected-vs-unselected border contrast: 4.43:1 — visible, but it is the *only* differentiator; there is no tick, fill or label change.

This is inconsistent with the rest of the file, which gets this right: the need chips, feature chips, persona buttons, Save, the three text-size buttons and both map control toggles all carry `aria-pressed`, and all seven switches carry `role="switch"` + `aria-checked`.

**Fix.** (a) `#filt-fresh` → `role="radiogroup"` with `role="radio"` + `aria-checked` on each button (or `aria-pressed`, matching the neighbouring chips). (b) `.claim-result` → `role="radio"` + `aria-checked` inside a `role="radiogroup"`, and add a visible tick or filled indicator to the selected row.

---

## Improvements

Real defects, but they degrade the experience rather than blocking a task.

**I1 · Onboarding does not isolate — the covered bottom nav is focusable.** On `ob-splash`, `ob-welcome`, `ob-location` and `ob-needs` (z-index 52/58) the `.navbar` (z-index 45) is opaquely covered but remains in the tab order. Measured on `ob-welcome`: 5 focusables, of which 3 are `nav-map` / `nav-scan` / `nav-profile`; `elementFromPoint` at `#nav-map`'s centre returns `DIV.wl-actions`, confirming it is fully obscured. Activating the invisible "Map" skips onboarding with no feedback. *Fix:* `inert` on `.navbar` while an `.obscreen` or `.splash` is active.

**I2 · Decorative glyphs are exposed as text and are below 3:1.** `.chev "›"` (13 instances), `.d-arrow "→"` on the owner diff, `▾` on the location pill and the `♥` in match chips are all read aloud and all measure **2.62:1** (`#A29BC4` on white). High contrast fixes `.prof-row .chev` only (line 1175) — the chevrons in `#sheet-card`, `ow-listing` and the `.d-arrow` still fail in HC. The `→` matters semantically: it is the only indicator of *direction* in "Seen in 5 scans → Yes". *Fix:* `aria-hidden="true"` on all of them; give `.d-arrow` a visually-hidden "changes to" and a colour clearing 3:1.

**I3 · The drawn map's street labels leak into the accessibility tree.** `#map-ground` and `#mini-map` are not `aria-hidden`, so `groundSVG()`'s `<text class="street-label">` elements surface as five bare generics at the top of the map region: `"W 2ND ST" "W 3RD ST" "W 4TH ST" "LAVACA ST" "COLORADO ST"`. `#ow-mapground` **is** `aria-hidden="true"` — the pattern is right, just applied in only one of three places. *Fix:* `aria-hidden="true"` on `#map-ground` and `#mini-map`.

**I4 · Seven `aria-label`s on `<div>`s with no role are silently dropped** (`aria-prohibited-attr`): `#chiprow` "Active filters", `#list-view` "Entrances as a list", `#nearby` "Nearby matches", `#proc-chips` "Features identified", `.preview`, `.intro-tips` "How to scan", `.wl-tiers` "What the pins mean". *(5 flagged 2026-09-04; now 7.)* *Fix:* add `role="group"` / `role="region"` / `role="list"` as appropriate.

**I5 · Headings are thin and out of order.** `screen-profile` — the app's hub — has **no heading at all**; its six section titles (`My needs`, `Places & contributions`, `Display & access`, `Privacy & notifications`, `For business owners`) are `<div class="sectionlabel">`. `scan-capture` and `ow-listing` also have no heading. The card sheet has none — `.card-name` is a `<div>` and `.chips-title` ("Seen at this door", "Couldn't confirm yet") are `<div>`s. Only the three onboarding screens have an `<h1>`; all 22 others start at `<h2>`, and sheets start at `<h3>`. A screen-reader user cannot navigate any of these screens by heading. *Fix:* `<h1>` per screen, `<h2>` for `.sectionlabel`, `<h2>`/`<h3>` for `.card-name` and `.chips-title`.

**I6 · The capture coach is an unbounded polite live region.** `#coach` is `aria-live="polite"` and `startCoach()` rotates four messages on `setInterval(…, 1700)` with no stop condition while the capture screen is up (lines 3667–3676). Observed changing twice during a single screenshot pass. A screen-reader user trying to find the shutter button is interrupted every 1.7 s indefinitely. *Fix:* announce the coach once on entry and thereafter only on a real state change; or drop `aria-live` and expose the guidance as static text under the viewfinder. WCAG 2.2.2 also asks for a pause mechanism for auto-updating content lasting over 5 s.

**I7 · Feature chips are disclosures with no disclosure semantics.** `.fchip[data-ev]` toggles `.evidence` with the confidence percentage and the reason ("Step-free entry · confidence 62% — Near ground-level views show the concrete entry pad meeting the brick pavers…"). Measured: `aria-expanded: null`, `aria-controls: null`, `.ev-box` has no `aria-live`, focus does not move. The best content on the card is undiscoverable non-visually. *Fix:* `aria-expanded` + `aria-controls` on the chip; the evidence box gets `id` and is placed immediately after the chip group.

**I8 · Confidence is dots-only.** `.dots` renders 1–3 filled `<i>` elements with no text. On card chips, on `scanRowHTML`'s tail (which is `aria-hidden`) and on `.ow-scanline` the confidence level never reaches a screen reader. The card *tiles* do say "High / Medium / Building" ✓ — the chips do not. *Fix:* a visually-hidden "confidence: high/medium/low" beside each `.dots`.

**I9 · Two touch targets under 44 px.** `#card-grip` 390×26 (covered in B9) and `#search-clear` 34×34 (line 700). Everything else passes — see W6. *Fix:* `min-height:44px` / `width:44px;height:44px` with the visual disc unchanged.

**I10 · Ambiguous accessible names in the owner photo manager.** Three buttons named "Replace" and two named "Remove", with the distinguishing text (`1 · Approach from the sidewalk`) in a sibling span outside the accessible name. *Fix:* `aria-label="Replace photo 1, Approach from the sidewalk"` etc.

**I11 · List-view rows are announced twice.** Each `.lrow` has a complete sentence `aria-label`, and its inner spans are *not* `aria-hidden`, so element-by-element navigation replays name, address, tier, match, freshness, features and distance a second time. `renderSaved()` and `scanRowHTML()` get this right with `aria-hidden="true"` on `.rowmain` — `renderList()` does not. *Fix:* `aria-hidden="true"` on `.l-main` and `.l-dist`.

**I12 · The distance slider announces a number, not a distance.** `#filt-dist` has `aria-label="Distance"` but no `aria-valuetext`, so it reads "1" rather than "1 mile"; the visible `#filt-dist-label` is a detached span. *Fix:* set `aria-valuetext` in the same `input` handler that updates the label.

**I13 · The tab list has no roving tabindex.** `#tab-scans` / `#tab-corrections` both stay in the tab order (`tabindex: null` on both). Arrow-key navigation *is* implemented ✓. *Fix:* `tabindex="-1"` on the unselected tab.

**I14 · The "needed" badge is CSS generated content.** `.fchip.needed::after{content:"needed"}` — computed `content: "needed"`, but it does not appear in `textContent`. Chrome folds `::after` into the accessible name; not every AT does. This badge is the link between a feature and the user's own stated need. *Fix:* render "needed" as a real element or a visually-hidden span.

**I15 · The app's "Larger" text setting is only +16%.** `.phone[data-textsize="larger"]{font-size:17.4px}` against a 15 px base. WCAG 1.4.4 expects content to survive 200%. At a real 200% (root 30 px) the match legend measured `right: 550px` against a 390 px frame — clipped. Within the app's own three settings, however, **nothing clips or overlaps on any of the 26 screens** (see W3). *Fix:* raise the top step, and give `.match-legend` `flex-wrap:wrap` so it reflows rather than clipping.

**I16 · Timed content with no user control.** The splash auto-advances at 1200 ms; the toast auto-dismisses at 2800 ms and cannot be paused, extended or re-read; processing auto-advances to review roughly 1 s after the "Checks complete" announcement, with no focus move, so a screen-reader user can be mid-sentence when the screen changes. *Fix:* per B2 make toasts announce and persist longer (or add a dismiss); hold the processing→review transition until the announcement has been given time, and move focus into the review screen.

**I17 · `<label for>` pointing at a `<button>`.** "Add a photo (optional)" is `<label for="correct-photo-btn">` on a button; `for` only labels form controls, so the label is orphaned and the button's name is just "Choose a photo". *Fix:* make it a `<div class="chips-title">` and `aria-describedby` the button, or `aria-label` the button fully.

**I18 · `role="progressbar"` on a `display:contents` host.** `#proc-progress` (line 1688) carries `role="progressbar"`, `aria-valuenow` and `style="display:contents"`. `display:contents` on a role-bearing element has a history of dropping the node from the accessibility tree; the value is also repainted every animation frame, which is a lot of churn for something no AT is asked to announce. *Fix:* put the role on the `.ringwrap`/`.procbar` element itself and throttle the value updates.

---

## Confirmed correct — please do not regress these

This file has had serious accessibility work done and most of it holds under measurement.

**W1 · Text contrast is excellent everywhere, in both modes.** An automated sweep of every text-bearing element across all 26 screens and 7 sheets, with alpha compositing, returned **28 failures in normal mode and 15 in High contrast — and every single one is a decorative glyph** (`›`, `→`, the transparent `✓`), not content. Sampled token pairs:

| | ratio | | ratio |
|---|---|---|---|
| `--ink` on white | 15.76 | `--sub` on white | 9.14 |
| `--sub` on `--ground` | 7.77 | `--sub` on tiles `#F8F7FD` | 8.58 |
| Estimated chip | 9.13 | Scanned chip | 7.10 |
| Owner chip | 8.24 | Good match chip | 8.02 |
| Partial match chip | 6.64 | Not-yet-seen chip | 9.13 |
| **Amber freshness** on `--amber-wash` | **6.91** | Amber on white | 7.65 |
| Marigold button text | 6.61 | Street labels | 10.65 |
| **Welcome hero** tagline `#A99AE0` on `#1E1543` | **6.74** | Welcome wordmark `#7CC4FA` | 8.95 |
| Capture screen body text | 13.41 | Capture screen emphasis | 15.76 |

High contrast raises `--sub` to 13.78 and `--purple-ink` to 13.25. There is no body-text or subdued-text contrast defect anywhere in this app.

**W2 · Reduce motion genuinely stops everything.** Verified by computed style with the Profile toggle on:

```
sheet transition      0.32s → 1e-05s
map pan               → 1e-05s
screen-in animation   → 1e-05s
checkitem transition  → 1e-05s
ring stroke           0.25s → 1e-05s
coach swap            → 1e-05s
progress bar fill     → 1e-05s
```

The processing ring is not merely frozen but **replaced**: `ringwrap` goes `display:none`, the determinate `.procbar` appears at 100%, all three checks land at once, and the "Checks complete" announcement still fires. The pin drop and ripple are guarded by `isReduced()`. `isReduced()` correctly ORs the OS media query with the in-app toggle, and `applyPrefs()` reflects the OS setting back into the toggle's `aria-checked`. This is a genuinely well-built implementation.

**W3 · Text scaling within the app's own settings is clean.** All 26 screens probed at Default and Larger with High contrast on: no clipping, no overlap, no unreachable control. The map overlays hold (`chiprow` right edge 316 px, `match-legend` 378 px, `legend` bottom 285 px vs FAB top 582 px — no collision). `ow-listing` looked like it clipped until measurement showed the inner `.sheet-scroll` scrolls correctly (1198 / 621). The Welcome hero, which has no scroller, still fits at Larger (footer bottom 814 vs frame 844). The one exception is the toast (B2).

**W4 · The list view is a complete, well-authored text equivalent of the map.** Each of the 64 rows carries a full sentence: *"Sweetgreen. 200 W 2nd St. Scanned on-site. Good match. Seen 2 days ago. 100 ft. Seen: Step-free entry, Wide door, Easy-grip handle, Clear approach."* It uses the correct `<ul role="list"><li><button>` structure, has a real `<h2>` with a live count, and the toggle updates both `aria-pressed` and `aria-label` and correctly hides the map-only zoom and locate controls. This is the single best piece of accessibility work in the file — and it is what makes B4 an omission rather than a catastrophe.

**W5 · The three-position card genuinely changes what is exposed.** Verified by walking the accessible text at each position:

- **Peek** — name, entrance, distance, tier, match with counts, position hint.
- **Medium** — adds the per-need breakdown, freshness, confidence, and the seen-at-this-door chips.
- **Full** — adds photos, provenance rows, "Couldn't confirm yet", and all actions; the position hint correctly disappears.

Hidden positions are `display:none`, so they are properly absent from the tree rather than merely invisible. The copy itself is exemplary — *"Couldn't confirm yet: Ramp or bevel · Handrails · Auto-door button · Access signage — not spotted in this scan"* is honest, non-punitive and fully non-visual.

**W6 · Touch targets pass almost universally, including the clever ones.** Hit-tested with `elementFromPoint` at ±21 px:

- `.toggle` — 52×31 box, but `::before{inset:-8px}` gives a **68×47 real hit area**; all four probe points return the toggle ✓
- `.achip` — 108×32 box, `::before{inset:-6px}` gives **44 px height**; all four probes hit ✓
- Card controls: every button 44–52 px tall, 155–354 px wide ✓
- Owner selects 88×44 ✓, photo buttons 190×44 ✓, `.searchfield` 48 ✓, `.persona` 66 ✓, `.claim-result` 60 ✓, `.lrow` 64 ✓, `.pinbtn` and `.cluster` 44×44 ✓, `.ctl-btn` 44×44 ✓, `.shutter` 76 ✓
- The 20×20 radios and checkbox in the claim flow are wrapped in `<label class="verify-opt">` (56 px) and `<label class="authz">` (44 px), so the label is the target ✓

Only two failures across the whole app (I9).

**W7 · Colour is never the sole carrier of tier, and rarely of anything else.** The three pin tiers are genuinely shape-differentiated — dashed outline + italic *i* / solid marigold with a segmented ring + person glyph / solid purple with a store glyph and a fused check badge — so they survive greyscale. Freshness carries text ("Seen 12 years ago — help us re-check"), match carries text in every list, chip and card, confidence carries a dot *count*, the flagged photo carries a written note, the owner diff carries a strikethrough, and the "needed" marker carries the word. The one real colour-alone state left is the claim result (B10) and the nav tab (B8).

**W8 · ARIA state is correct wherever it is present.** `role="switch"` + `aria-checked` on all seven toggles (location, high contrast, reduce motion, five notification groups) and all update on click ✓. `aria-pressed` on personas, filter chips, feature chips, Save, the three text-size buttons, the list toggle and the zoom toggle — all verified toggling ✓. `role="tablist"` / `role="tab"` / `aria-selected` / `aria-controls` / `role="tabpanel"` / `aria-labelledby` on Contributions, with arrow-key navigation implemented ✓. The Save button changes both `aria-pressed` and its visible label.

**W9 · The processing announcement is well judged.** `#proc-live` (`role="status" aria-live="polite"`) fires **once**, at completion: *"Checks complete. 3 features identified. Review before publishing."* The individual checks are deliberately not announced. That is the correct noise trade-off — announcing each of three checks 1.5 s apart would be chatter. `announceUI()` also uses the correct clear-then-set-after-30 ms technique so repeat messages are re-announced.

**W10 · Alt text and SVG hiding are handled thoughtfully.** Every `pinSVG()`, `markSVG()` and illustration is `aria-hidden="true"`. The meaningful graphics carry `role="img"` + `aria-label`: the Texas flag ("Texas"), `.ow-check` ("Owner attestation complete" / "Published"), `.ow-tick` ("seen on-site" / "confirmed by the owner"). Photo alt text is descriptive and honest — *"Doorway with the patio — Royal Blue Grocery, W 3rd St entrance (a face may be visible)"*, *"Entrance photo 2 of Royal Blue Grocery"*.

**W11 · Every form control is correctly labelled.** `claim-role`, `claim-email`, `claim-phone`, `correct-what`, `correct-which`, `correct-note`, `edit-note` and all four `ow-sel-*` selects have real `<label for>` associations; `search-in`, `claim-search` and `filt-dist` have `aria-label`. `<html lang="en">` is set. Closed sheets, hidden overlays and hidden file inputs are all correctly removed from the tab order.

---

## Punch list, in priority order

1. **Announce every toast** — route `toast()` through `announceUI()`, and replace the two blocked-publish toasts with inline errors carrying `aria-invalid` / `aria-describedby` plus a focus move. *(B2)*
2. **Announce and focus every screen change** — `aria-label` on the 12 screens missing one; move focus into the new screen in `showScreen()`. *(B1)*
3. **Stop the processing checklist lying** — `aria-hidden` the transparent `✓` glyphs in `.ci-dot`, `.p-ring` and `.tl-dot`; fix the 2.47:1 pending state. *(B3)*
4. **Put the match, freshness and distance into the pin's `aria-label`** — reuse the sentence `renderList()` already builds; move `#pins` behind the map controls in DOM order. *(B4)*
5. **Give sheets focus management** — focus in, trap, Escape to close, focus back out; `aria-modal` on the seven modal sheets, `role="region"` on the non-modal card. *(B5, B9)*
6. **Fix the focus ring on dark backgrounds** — 2.80:1 normally and 1.23:1 in High contrast on the camera screen. A two-tone ring fixes every surface at once. *(B7 rows 10–12)*
7. **Raise the seven sub-3:1 control indicators** — toggle track, field/chip borders, dot outlines, ring track/fill, and the Estimated and Scanned pins against the map ground. *(B7 rows 1–9)*
8. **Drop `role="listitem"` from the row buttons** in Saved, My scans and My corrections; wrap them in `<li>` as the list view does. *(B6)*
9. **Expose the current nav tab** — `aria-current="page"` plus a non-colour visual cue for a state that is currently a 1.05:1 hue shift. *(B8)*
10. **Add state to the Freshness segment and the claim result rows** — radiogroup semantics, and a visible tick on the selected claim row. *(B10)*
11. **`aria-expanded` + a 44 px target on the card handle**, and `aria-expanded` / `aria-controls` on the feature chips. *(B9, I7)*
12. **`inert` the navbar during onboarding**; `aria-hidden` `#map-ground` and `#mini-map`; `role` on the seven labelled `<div>`s. *(I1, I3, I4)*
13. **Real headings** — an `<h1>` per screen, `<h2>` for `.sectionlabel`, and a heading for the card name; `screen-profile` currently has none. *(I5)*
14. **Quiet the coach live region**, un-hide the confidence dots as text, and let `.toast` wrap. *(I6, I8, B2c)*
15. Remaining polish: `aria-hidden` on `›`/`→`/`♥`/`▾`; `aria-valuetext` on the distance slider; distinct names for the Replace/Remove buttons; `aria-hidden` the list-row inner spans; roving tabindex on the tabs; the `::after "needed"` badge as a real element; `role="progressbar"` off the `display:contents` host; a larger top text step. *(I2, I10–I15, I17, I18)*

---

## Evidence notes

- All contrast ratios computed in-page from live `getComputedStyle` values using the WCAG relative-luminance formula, with translucent backgrounds composited against their opaque ancestor before measurement. Non-text ratios are stated against the surface the indicator actually sits on.
- Touch targets measured with `getBoundingClientRect` **and** confirmed by `elementFromPoint` probes at ±21 px from centre, so pseudo-element hit expansion (`.toggle::before`, `.achip::before`) is credited rather than penalised.
- Focus and tab-order findings come from a per-screen sweep of every focusable element with visibility inheritance walked to the root, plus live `document.activeElement` reads across real transitions.
- Live-region findings come from diffing region contents over time and from reading the region attributes directly.
- One automated result was discarded as a probe artefact: the "SNEAKER POLITICS" sign inside the doorway illustration reports 1:1 because it is SVG `<text>` over an SVG `<rect>` sibling, which HTML ancestor-walking cannot see. Rendered, it is white on `#7053C5` and fine.
- Camera capture is blocked in this browser pane, so the scan flow was exercised on its staged fallback path — the same path any user without a granted camera takes.
