# Round 5 brief: make the build look like the boards

Assembled from the approved boards, the interaction and motion specification, the interaction
conformance audit, and the product owner's direct instructions. Written before dispatch so that
nothing given mid-round is lost, per the directive-ledger discipline.

Round 5 owns `design/phone-app-prototype.html` alone. It runs after Round 4's token and asset
adoption lands, because the dark chrome is built from the official indigo tokens.

---

## 1. The chrome, which is the largest single change

Every board screen has **solid deep-indigo bars top and bottom**. The build has a floating white
pill over the map and a white bottom bar.

- **Header.** A solid `indigo900` bar. On the map it carries the two-tone wordmark at the left,
  the location pill, and a menu button. On every other screen it carries a centred screen title
  with a back chevron at the left. This replaces the floating pill entirely.
- **Bottom navigation.** A solid `indigo900` bar. Labels white. Map and Profile icons white. The
  scan control is a marigold ring, raised, as on the boards.
- **Consequence to exploit:** the logo's real sky blue `#69B7FF` is legible on indigo and was not
  on white. Use it. This is the light blue the product owner asked for twice and which could not
  be answered while the chrome was white.

## 2. Marigold is the action colour, and the build has missed the rule

On the boards, marigold is the primary button wherever the action *gets us data*: "Scan an
entrance", "Re-check entrance", "Allow camera". The secondary beneath it is a purple outline.
The build uses purple for these.

Apply the rule: marigold primary for capture and re-check actions; violet primary for everything
else; outlined secondary throughout. Marigold on the bottom bar's scan control follows the same
logic and must not read as the Scanned on-site tier.

## 3. Restore Estimated to a real pin

The build renders Estimated as a roughly 14px dashed ring with no teardrop and no glyph, routed
through a `ring` tier. `tokens/pin-hierarchy.json` states that context may scale a pin but never
change its tier encoding, and the boards draw Estimated as a white-filled teardrop with a dashed
outline and an italic information mark.

**The density argument that motivated the ring is already answered:** the conformance audit
measured clustering absorbing 55 of 64 marks at overview. So restore the correct artwork, which
already exists in the file as the `est` tier, and let clustering carry the calm.

Adopt the official sizes at each context: overview 32/36/40, street 40/44/48, selected 52/56/60,
receipt 24/28/32, cluster 48, live scan drop 64, with the specified z-index and overlap order.

## 4. The card

Freshness and Confidence become two tiles side by side, each with a leading icon, above the
feature rows. The evidence receipt opens from a full-width outlined button and is its own card
listing photographed date, neighbour count, owner count and the state record as icon rows.

## 5. The logo mark

Replace the drawn mark with `design/logo-mark.png`, cropped from the approved artwork. The asset
library's own mark is a degraded reproduction: it drops the white disc and draws the middle arc
in the same violet as the pin body, so it shows one colour above the entry instead of three. Do
not use it. Use the two-tone wordmark on the header, sky blue and white on indigo.

## 6. Interaction conformance

From the audit: **20 violations, 19 numeric drifts, 21 confirmations.** The three worth fixing
first are the Estimated re-encoding above, the complete absence of an unavailable control state,
and the card sheet not following the drag.

- **Unavailable state.** Zero elements carry `disabled` or `aria-disabled` and no CSS exists for
  one. The spec names five control states; the build has four. Unavailable is pale lavender with
  a deep-indigo label and never grey, and tapping it explains what is needed.
- **Card sheet.** Add a one-to-one drag with release velocity influencing the destination. Stops
  measured at 20.9 / 41.9 / 85.1 against a spec of 18 / 54 / 92. Snap 320ms on the named curve.
  The map takes a 7% indigo veil only at full height; the existing scrim is 42% and never applies
  at the full stop.
- **Numbers to correct:** pin drop 700ms to 620ms, and its two marigold ripples to one sky-blue
  one. Focus ring stays 3px but becomes sky at 3px offset rather than purple at 2px. The outgoing
  screen moves 12px left to 88% opacity, which it currently does not do at all. Peer navigation
  gains the 8px upward settle. Chip stagger 220ms to 60ms.
- **Reduced motion must become replacement, not shortening.** The current implementation is two
  blanket rules setting every duration to 0.01ms. Nothing is left mid-flight today, but only
  because eight of eleven keyframes happen to declare a fill. The processing path is genuinely
  re-authored and is the model the rest should follow.

## 7. Do not regress

Every Round 1 accessibility behaviour, re-verified rather than assumed: screen names and focus
movement, live-region announcements, sheet focus trap and Escape, pin accessible names carrying
match state, correct roles, and the measured non-text contrast. The Round 2 tip anchoring and
type scale. The Round 3 map ground, elevation, spacing and consistency work. Pure ASCII outside
base64. One self-contained file, no external scripts.

**The rule that must not break:** no trust pin is ever recoloured to communicate selection,
match, freshness or provenance. The audit confirmed this holds today. It is the spec's strictest
prohibition and the easiest thing to break while restyling.

## 8. One open question, not for the implementer to decide

The boards draw the Texas flag beside map pins on three of four panels; the token spec says the
state record is receipt provenance only and never on a pin, and our canon withdrew that accessory
because icon soup around pins was the original complaint. Default to **no flag on the map**.
Flagged to the product owner rather than settled silently.

---

## Verification

Serve over http, drive at 390x844, walk all 26 screens. Print the pin contrast table against the
map ground's modal and worst tones in both contrast modes. Zero console errors, zero duplicate
ids, every target 44x44, no horizontal scroll, reduced motion and text scaling at both settings.

Then rescore the rubric in place with evidence and append a Round 5 entry. The bar is nothing
below 3 and an average of 3.5 or better; say honestly whether it is met and what remains outside
design's reach.
