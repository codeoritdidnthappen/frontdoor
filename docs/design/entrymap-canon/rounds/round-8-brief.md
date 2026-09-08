# Round 8 brief: make every mark on the map readable without asking, and remove the ones that are not

Assembled from the directive log's pass 3 (D36, D37, both decided by the owner at 21:40 on
2026-09-05) and from the three Round 7 re-audits, which are appended below as they land. One
implementer, alone, on `design/phone-app-prototype.html`. Do not start while any re-audit is
still measuring the file.

---

## 1. A new Estimated mark, with no dash (D37, option 1)

The library dashes both the Estimated pin outline (`pins/estimated.svg`, `7 6`) and the
partial-match halo (`halos/partial-match.svg`, `15 9`). Two meanings on one line style, shipped
side by side. The owner: "the dashes around the estimates and it also meaning partial is
confusing. maybe estimated needs a new icon?"

Draw a new Estimated mark. Constraints that already stand:

- Tier is carried by **shape and fill**, never by colour alone (3.1, the trust ladder).
- The outline stays sky700 `#1B6599`: the library's sky400 fails 1.16:1 on the block edge and
  2.02:1 on its own white fill (3.9). Re-measure the new mark on every ground tone in both
  contrast modes and print the table.
- The italic "i" glyph is part of the current asset; the confidence dots are removed (see §2).
  Decide about the glyph on evidence, not habit.
- Pin sizes per zoom stay on `pin-hierarchy.json`; a new silhouette must still read at 32px.
- Halos are untouched: solid good, dashed partial, dotted unknown. After this round, a dash on
  the map means partial match and nothing else.
- The legend row for Estimated is redrawn with the mark. Every place the old mark appears
  (legend, onboarding tier tiles, the trust ladder sheet, the card's tier badge, welcome screen
  tiles) changes together, or the ladder stops holding across screens (the critique's credit).

Deliver the mark as a gallery first if more than one candidate is plausible; the owner has asked
to see options before they land.

## 2. Take the confidence dots off the pins; teach the cluster count (D36 + D38)

The owner first chose to keep the dots and add a legend row (D36, option 1), then, looking at
the live map again: "the three circles above each icon is stupid" (D38). D38 wins.

- **Remove the three confidence dots from every pin at every zoom level**, in every tier and
  every state, and from every place the pin artwork is echoed (legend, onboarding tier tiles,
  the trust ladder sheet, the card's tier badge, the welcome tiles). A pin carries tier by
  shape and fill, match by halo line style, and nothing else.
- Confidence stays where it is explained: the card's Confidence tile and the pin's accessible
  name (`placeSentence()`). Nothing about the confidence *data* changes; only the pin stops
  drawing it.
- The `pinDots()` path and the library's dot geometry are removed from the build, not hidden,
  so a later round cannot switch them back on by accident.
- Add the **cluster row** to the trust legend: the numbered disc, "N places here — tap to
  open". The legend must stay one screen at the largest text size.
- Make the cluster disc's accessible name say what the number is, if it does not already.

**The owner chose J1** (2026-09-05, 23:5x), from `design/estimated-mark-gallery-4.html`: the
teardrop with a **solid** sky700 outline, white fill, and the owner's own glyph — two rounded
vertical posts and one short lintel, with three small dots across the open threshold. No door
leaf, storefront, checkmark, question mark or warning symbol. The gallery's asset source is
copyable from that page; take it verbatim rather than redrawing it.

Geometry as drawn and measured there: library frame 96x104, head centre 48/41.3, path
`M32 60V22h32v38` with round caps and joins at stroke 4 (the pin outline weight), three r2.2 dots
at x 40/48/56 on y 60, all sky700 `#1B6599`.

Two things the gallery measured that this round must carry:

- At 32px on a 1x display the three threshold dots read as a faint broken line rather than three
  countable dots, and the posts' round caps square off on the pixel grid. Posts and lintel stay
  distinct. If the owner later judges those dots to be the clutter the confidence dots were, J3
  is the same mark with one attribute removed; do not pre-empt that, but keep the dots in their
  own group so removing them is one line.
- The outline's floor is 3.08:1 against the sky400 place accent, the same for every candidate,
  mitigated by the build's white lift strokes (6.24:1). Re-measure on the real ground anyway.

Galleries 1 to 3 are superseded for this decision and stay in the repo as the record of what was
tried and rejected.

## 3. Score the two new criteria

Paste 5.x (every mark is taught where it is seen) and 5.y (one line style, one meaning) from
`design/directive-log.md` pass 3 into the rubric's map section and score them against the
result, with the measurements.

## 4. Do not

- Do not touch the match halos' line styles.
- Do not recolour any trust pin for selection, match, freshness or provenance.
- Do not adopt `estimated.svg` from either package; it is the asset being replaced.
- Do not widen into the re-audit findings below unless they are marked for this round.

---

## Round 7 re-audit findings marked for this round

From `design/a11y-audit-r7.md`. It closed **10 of 10** prior blocking defects and 14 of 18
improvements, and the contrast work is finished: zero text pairs below the package's 7:1 floor in
either mode, zero pins or halos below 3:1 on any ground, 189 of 189 controls at the 48px floor by
effective target. Three new blocking defects are this round's.

**9. A sub-sheet closes its parent card and drops focus to the pin (a11y N2, 100% reproducible).**
`openSheet()` captures the opener as `if(!openSheetId && active && active!==document.body)
sheetOpener=active` — verified at the line. A sheet opened while another is open is treated as a
hand-off, so the evidence receipt and the correction sheet inherit the **pin** as their opener.
Closing either returns focus to the pin and `closeSheets()` clears every sheet including the card.
A blind user who expands a card to full, reads the provenance and opens the receipt loses the
entire card and every action on it. Card to sub-sheet is a **stack**, not a hand-off: keep an
opener stack, pop one level on close, restore the card at the position it held, and return focus
to the button that opened the sub-sheet.

**10. Focus return strands the user on a closed sheet's heading, about 1 close in 20 (a11y N1).**
60 close trials, 3 failures, `activeElement` left on `H3.sheet-h` inside a `visibility:hidden`
sheet: nothing to read, nothing to activate, Tab restarts from the document top. The rate is the
same with reduced motion on and off, so this is a general race, not a motion seam.
`focusWhenReady()` polls a frame budget and then falls back — but on the failing runs neither the
opener nor the fallback took focus. Make the fallback unconditional (a `[tabindex="-1"]` labelled
section is always focusable) and **assert after**: if focus is still inside a closed sheet, force
it. Intermittent means a keyboard user cannot learn around it.

**11. The capture coach rotates forever and reduced motion does not stop it (a11y N3, WCAG 2.2.2).**
Confirmed at the call site: `startCoach()` branches on `isReduced()` only to skip the `.swap`
fade; `setInterval(…, 1700)` keeps changing the text in both modes. So the setting makes the
change instant instead of stopping it, on the one screen where the user must hold still and aim a
camera. Under reduced motion, stop the rotation and show the guidance statically — replace, do not
shorten, exactly as the processing ring already does. Independently, the rotation needs a pause,
stop or hide mechanism, or it should stop after one cycle.

**12. Two small ones with measured numbers.** Under reduced motion the "Checks complete"
announcement fires **20ms after** the app has already left the processing screen (a11y N4); fire it
before the navigation or drop it. And toggling high contrast is the only action in the app that
blanks the map ground, for 39 to 79ms, reproduced on the live build (a11y N5) — `applyPrefs()`
re-renders the ground while the map is `display:none`; re-render on the map's own visibility
instead.

**Do not** act on a11y N6 (duplicate `ev-box` id). It was checked against `eb056fe` and is false:
the id appears once. It stays in the report as a record of the audit's reliability.

Everything else on the accessibility punch list is Round 9.



From `design/interaction-audit-r7.md` (verified independently at the three call sites named). The
audit closed 29 of 39 previous items; these are what Round 8 owns. **Everything else on its punch
list is deferred to Round 9** so this round stays the size of its brief.

**5. Draw the dotted unknown halo on the map (N1, violation).** `renderPins` computes
`const match = m && m.state!=='unknown' ? m.state : null`, so the unknown state is deliberately
dropped and `match-unknown` renders zero times on the map, while `matchHalo('unknown')` already
draws the library's dotted sky700 ring correctly and the list view keeps a dotted carrier for the
same state. What stands in for it today is `.pinbtn.recede{opacity:.8}` — a 20% dim. Pass the
state through, and correct the legend line that currently *documents* the omission ("not yet seen
— no halo"). Reconsider whether `recede` should still dim once a positive mark exists.

**6. Give reduced motion a CSS floor (N2, structural).** There is no
`@media (prefers-reduced-motion: reduce)` rule in the file at all: the only media query is
`(max-width:767px)`, and the whole reduced-motion contract hangs on a `.phone.rm` class written by
`applyPrefs()`. Measured: first paint at 296ms, class applied at 388ms warm and **804ms cold** — a
92 to 500ms window in which an OS-reduce user gets the full motion system, with nothing underneath
if `applyPrefs()` ever throws. Either mirror the `.phone.rm` essentials in a real media query, or
set the class from an inline head script before first paint.

**7. Stop reduced motion deleting the scan's pacing (N3, structural).** `defer()` and `after()`
return 0 under reduce, so the scan runs **420ms instead of 7,439ms**, all three checks land at
once, and the `PROC_CHIPS+600` hold — whose own comment says it exists "so 'Checks complete' is
spoken before the screen changes" — is skipped. Reduced motion should drop the sweep, the scale
and the rotation, and keep the cadence and the announce-then-hold. As written, the clause that
protects screen-reader users is the one the setting turns off.

**8. Test clusters against pins in the collision pass (N4, violation).** Pin-to-pin overlap
respects the build's 10% rule (worst 0.100), but cluster-to-pin is untested: **43.3%** of one pin
is covered by a 48px cluster at overview, 21.0% of another at street. The mark that exists to
resolve density is creating it.

**Note for whoever measures Round 8:** this audit describes the Estimated mark and the confidence
dots as they were. Both change in this round, so re-measure the tier rows rather than carrying
these figures forward.

