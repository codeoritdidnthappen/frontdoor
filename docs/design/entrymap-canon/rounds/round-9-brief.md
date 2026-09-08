# Round 9 brief: make the map reachable, then close the punch lists

The product owner asked, looking at the live map: *"When I click the numbers on the map, will it
zoom in and show the businesses?"* The answer today is no, and that is the first item. Then
everything the three Round 7 re-audits raised that Round 8 deferred, plus what Round 8 found and
left.

One implementer, alone, on `design/phone-app-prototype.html`. Measure everything; assert nothing.

---

## 1. Tapping a cluster must resolve it. This is the blocker.

**What happens now.** The handler is one line:

```js
b.addEventListener('click',()=>{ setZoom(false); });
```

`setZoom(false)` means "not zoomed out". At street zoom `zoomedOut` is already `false`, so the
call re-renders the identical map and destroys the focused button. The accessible name promises
*"tap to zoom in"*. Nothing zooms, nothing opens, and focus lands on `<body>`.

Clustering runs at **both** zoom levels, so a cluster at street zoom has no deeper level to
resolve into. QA measured the consequence on the live build: **41 clusters at street level, and
209 of 221 places unreachable from the map.** That is 95% of the product's content behind a
control that does nothing.

**What it must do instead, at every zoom level:**

- **Zoomed out:** zoom in *and* centre the map on that cluster's centroid, so the tap lands the
  user among the places it was standing for. Zooming without panning is why this looks fixed and
  is not.
- **At street zoom, where there is no deeper level:** open a sheet listing the cluster's members
  — each row the same `placeSentence()` the list view already builds, each tappable to open that
  place's card. Re-use `renderList()`'s row rather than inventing a second row.
- **Either way the tap must resolve.** After it, the user is either looking at separated pins or
  at a list of exactly those places. There is no path where a tap changes nothing.

Fix the accessible name to match whichever branch runs, and **keep focus**: today the re-render
destroys the focused element. Focus belongs on the sheet's heading, or on the map with an
announcement of what changed.

Then measure it: at each zoom level, tap every cluster and record what the user can reach. The
number to print is **how many of the 64 places are reachable from the map by tapping**, before
and after. Before is 12 of 64 at street zoom.

## 2. The rest of the accessibility punch list

From `design/a11y-audit-r7.md`. Round 8 took the three blocking ones. These are what is left, and
most are one rule each.

- **N9 — map controls have no boundary.** `.ctl-btn`, `#fab-needs`, `#fab-filters` are
  `rgba(255,255,255,.96)` discs with `border: 0px none`, measuring **1.00 to 1.27:1** against the
  three map grounds, and high contrast does not add one. Give them a 1 to 2px `--edge` hairline.
  They should read as controls, not as map labels.
- **N10 — the processing ring's fill against its track is 2.12:1.** The component is visible; how
  far along it is, is not. Darken the track or lighten the fill against it, and print the new
  figure.
- **N11 — the feature chip's marigold border is 1.80:1 in both modes.** The label clears 7.88:1,
  so the chip is identifiable and the boundary that says "pressable" is not. `--marigold-ink`
  gives 7.88:1.
- **N12 — two primary buttons' high-contrast focus ring has one invisible side**
  (`#btn-claim-submit`, `#photos-publish`, bottom edge 1.12:1 against the dock). Give
  `.btn.primary` the white companion shadow the other light-chrome controls already have.
- **N13 — the location pill truncates at Larger text** (`scrollWidth 118 > clientWidth 98`). It is
  the only clipped string in the build. Let it grow or wrap.
- **N15 — applying filters returns focus to the screen container**, where Escape and Close both
  return to `#fab-filters`. Three exits from one sheet, two behaviours.
- **N16 — pin and row labels contain a lowercase sentence start:** *"Owner-confirmed. **n**eeds
  not yet seen."* Reads as a stumble in every screen reader.
- **N17 — the evidence box appears silently.** A chip expands and nothing signals content
  arrived.
- **N7 — 19 of 26 screens have no `<h1>`** and start at `<h2>`. Promote each screen's title.
- **`.matchchip.unknown` and `.mstat.unknown` are dotted sky400 at 1.83:1** — named in the rubric
  at 7.2 and left out of Round 8's brief. Use the same `--match-unknown` the map's dotted halo now
  uses (6.24:1).

## 3. The rest of the interaction punch list

From `design/interaction-audit-r7.md`.

- **V20 — the four scan beats, still all four missing.** No white shutter wash; no single violet
  sweep across the photo; the checklist reads "Double-checking" where the spec says "Entrance
  features checked"; no map-return contraction. The first two are small additions, the third is a
  string, the fourth is the only real work.
- **V7 — the nav indicator sits above the destination tab, not beneath it.** Measured
  `indicator.top = tab.top = 765`, `tab.bottom = 828`.
- **N8 — "shadow compresses" on press is unimplemented.** Zero `:active` rules touch
  `box-shadow`; `.fab-filters` and `.ctl-btn` hold theirs through the press.
- **D16 — toast dwell is 4,200ms** against the spec's 3,000 to 4,000.
- **D17 — photo settle is 900ms at 14%** against the spec's 100 to 380ms at 3%.
- **V8 residual — the ripple border is sky700** where the token file names sky400.
- **N9 (interaction) — the explainer rungs draw at 34/36/38px**, a fourth size set outside
  `pin-hierarchy.json`. Resolve them through `pinPx()` like every other call site.
- **D18 — eight toggles at 52×31 and one filter chip at 103×32** are the last controls under the
  48px floor by visual box.
- **N6 — `--dur-focus: 120ms` is declared and never used.** Use it or delete it.

## 4. What Round 8 left

- **The floating column overruns the FAB row by 46.9 to 55.1px** with a needs profile applied.
  Round 8 reduced it from 50.7 to 62.3 and said plainly it did not close it. Close it.
- **Six placeholder `dashed` declarations** meaning "empty slot" keep rubric 5.8 at 3 rather than
  4. Either they are a real state with a real meaning, or they are not dashed.

## 5. Rescore, and say what the bar now is

Rescore every criterion this round touches, with measurements. Print the new average and name
every criterion still below 3.

The rubric currently sits at **3.819 over 72 criteria**, and the bar is missed by one line: **6.6
at 2**, which needs an owner-confirmed entrance to exist in the data. That is not design's to
move. Do not score it up. Name it as the escalation it is.

---

## Rules that do not move

No public verdict is negative. `not_visible` is never `absent`. No trust pin is recoloured for
selection, match, freshness or provenance. Halo line styles are solid, dashed, dotted and mean
good, partial, unknown — a dash means nothing else. Tier is shape and fill. Trust only goes up.
48px targets, 7:1 body text.

Do not accept your own report as evidence. Round 8 found the previous brief wrong about where
confidence lived, and was right to check. Do the same.
