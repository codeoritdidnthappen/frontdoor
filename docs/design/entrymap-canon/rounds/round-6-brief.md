# Round 6 brief: the things a designer would fix before showing anyone

From `design/graphic-critique.md`, plus the QA and change audit when it lands. Written before
dispatch so nothing is lost while Round 5 holds the file.

Round 5 already owns: the brand mark, marigold as the action colour, restoring the Estimated
pin, the card's freshness and confidence tiles, the dark title bars, and the interaction spec's
20 violations. **Do not duplicate those.** Everything below is additional.

---

## Two visible rendering faults

**1. The selected pin paints on top of sheets.** Its lift z-index escapes the map's stacking
context, so a purple pin sits over the correction form's first select and over the empty-state
headline. Reproduces by walking the real flow, not only by jumping to a screen. This is the most
visible defect in the build and it is a stacking-context bug, not a z-index number to raise.

**2. Fifty-two identical estimated rings at default zoom.** Clustering exists and works, and is
only applied at the zoomed-out level. Eleven amber pins collide into a heap, and the legend
teaches a dashed-teardrop mark that appears nowhere on the default map. Round 5 restores the
correct Estimated artwork; this is the separate problem that clustering must also run at default
zoom.

## Demo scaffolding in shipped copy

`(staged for demo)` appears on the card's primary provenance row. `Open My Business (staged)` is
a visible label. This is exactly the class the product owner asked about: things the build should
not include. Remove the words; keep the behaviour honest by other means if a caveat is genuinely
needed.

## Components do not hold their shape across screens

The critique counted: **the tier badge has five treatments, the feature chips three layouts,
headers four patterns.** Round 3's consistency sweep worked property by property, which caught 20
classes of drift but could not see this, because each instance is internally consistent and only
differs from its siblings. This needs a component pass, not a property pass: one tier badge, one
feature chip, one header, used everywhere.

## The type scale is em-relative and compounds

The same body role renders at **14.25, 12.9, 12.667, 12.255, 11.7 and 11.467 pixels** on
different screens, because em steps multiply inside nested containers. Profile alone uses twelve
size and weight pairs. This is the invisible reason the build reads slightly less crisp than the
boards even where the layout is correct. Anchor the scale so a step means one size everywhere.

## The illustrations: four survive, three do not

- **Keep:** the door, saved, thanks and offline drawings.
- **`camera`** is a hubcap, not an aperture: six radii through the centre.
- **`street`** has a one-point-perspective ground under flat-elevation buildings, three pavement
  joints that share no vanishing point, a figure drawn in a different stroke weight, and — in a
  product called EntryMap — **no entrance**, with the marigold spent on an awning.
- **`map`** is off-family and mis-sells the product: it promises a blue rotated map when the app
  delivers a cream orthogonal one.

Also worth knowing: five of the seven are one hand, but three of those five are the same door
with different props, so the set has less range than its count suggests.

## The welcome screen

The aubergine decision is right and the execution does not yet pay for it. The screen earns brand
continuity, a real dark-to-light handoff and a status-bar solution, then spends half its height on
a logo shown for the third time in five seconds and a doorless skyline.

The critique's single suggested fix: re-tint the `street` drawing for the dark ground, run it
full-bleed, and give it one lit yellow doorway. That requires fixing `street` first, which is the
weakest drawing in the build and currently carries the first impression.

## The place card

The photographs win the eye over the verdicts. The Freshness and Confidence pair is coloured
asymmetrically for no reason. The library's feature icons are absent from the one screen most
users actually meet. The bottom slices a sentence.

---

## What the critique credited, and Round 6 must not damage

The trust ladder as a shape-first system that holds across all 26 screens. The My Needs sheet,
which improves on the board by adding a sub-line saying what each choice does. `ow-review`, an
invention with no board panel and the most professionally designed information screen in the
build. The Accessibility screen's self-demonstrating text-size control. And the zoomed-out map
ground, which reads more like Austin than the boards' cooler version.

---

## The map ground is the wrong temperature, and this is a correction to my own decision

The product owner has raised the map twice. Measured against the board rather than argued:

| | Board (sampled from panel 1) | Build |
|---|---|---|
| Ground / blocks | `#F9F9FC` and `#FAF9FC` — near-white, faintly cool | `#EFE8DA` warm cream |
| Block shading | barely present | `#E5DCCF` warm grey-beige |
| Plazas | none visible at this scale | `#F8EACC` warm cream-yellow |
| Overall | 85% of pixels sit in a cool near-white band | noticeably darker and yellow |

The board's map is **almost white with a faint blue-violet cast**. The build's is warm cream and
several steps darker. That difference is what "the background map is still wrong" means, and it
is not subtle once the two are side by side.

**How it happened, so it is not repeated.** Round 3 produced four ground variants and recommended
"Terrain's colour on Relief's light" — warm sand ground, sage canopy, marigold plazas. I approved
that without checking it against the board, which is the actual error: the recommendation was
internally reasoned and simply aimed at the wrong target. Round 4 then re-solved those tones onto
the official palette and reported that eight came back byte-identical "because Round 3's warm
family was already on the marigold hue line". That was a true observation about the *tones* and it
carried the wrong decision forward intact.

**What Round 6 must do.** Rebuild the ground cool and light to match the board: near-white blocks
with a faint violet cast, white streets, the light blue tree clusters the board uses, and shading
steps small enough that the map reads as a pale field rather than a textured one. Keep everything
structural that Round 3 earned — the road hierarchy, the implied light direction, the landcover
areas, the block-to-block variety — and change only the temperature and the value range.

**Re-measure every pin against the new ground.** A near-white ground raises the contrast floor for
the estimated pin's outline, which is the marker with no halo. Round 4's table was measured on the
warm ground and does not carry over. Print the new table.

---

## From the QA sweep and change audit: the defect that outranks everything else here

**Reduce Motion breaks focus into every sheet in the app.** Measured: 0 of 12 failures with the
setting off, **12 of 12 with it on** — the entrance card, filters, needs and the trust legend.
Focus is left on the document body.

The mechanism is a seam, which is why four rounds of per-round verification missed it. Both
reduced-motion blocks force `transition-duration` to `.01ms` and never touch `transition-delay`.
The sheet's stale-transform guard is expressed *as* a delay: `visibility 0s var(--dur-fast)`. So
the subtree is still `visibility:hidden` when the fixed 40ms focus timer fires, `focus()` silently
no-ops, and nothing retries. One round owned the motion, another owned the focus, neither owned
both.

For modal sheets it is worse: all 26 screens are inert, so a screen-reader user is parked on the
body with no announcement and no way back. The operating system's own setting triggers it, so a
user never has to open our settings to hit it.

On a product for disabled people, turning on the accessibility setting breaks the accessibility
behaviour. Fix this first, and fix it by making the reduced-motion path a genuine replacement
rather than a shortening — which is separately already required — and by making the focus move
wait on readiness rather than on a fixed timer.

## Controls that report state they do not have

- **Open now** and **Distance** are wired to nothing. The filter function reads three inputs and
  there is no state variable for either. `Open now` is a `role="switch"` reporting
  `aria-checked="true"` while changing no result. That is a lie told to a screen reader.
- **7 days** and **30 days** produce identical results, 12 places each.
- Dragging the card **up** while it is already full collapses it to peek, because a tap-cycle
  modulo wrap is applied to a directional gesture.
- The claim form submits with no email and no phone, then says "We'll email you."

## Two round reports were materially false, in the flattering direction

Spot-checked five claims from previous rounds. The heaviest font weight is on **28** sites, not
the 21 reported. Hand-drawn icons number **27**, not the four reported. Pin-tip accuracy checked
out exactly. The pure-ASCII property held for four rounds and **broke after Round 4** — nine
bytes, three literal glyphs inside JavaScript string comparisons.

Treat round self-reports as claims to verify, not as evidence. Two of five were wrong and both
erred toward success.

## What survived deliberate attack, and must not be damaged

The owner face-flag gate is genuinely solid: an ungated route into the review screen exists via
Edit entrance, and the publish path re-checks independently, bounces back and names the offending
photo. No injection anywhere. Eighteen interleaved navigation taps never produced two active
screens. The largest text size clips nothing on any of 26 screens. And no Round 1 accessibility
behaviour was removed by Rounds 2 to 4 — which is exactly why the Reduce Motion defect matters:
the worst problem in the build is invisible to per-round review because it lives in a seam rather
than in a diff.

---

## Everything reads purple, because lavender is the default surface

The product owner's screenshot of `claim-confirm` makes it plain: the screen body, the field
group containers, the selected radio and checkbox rows, and the error box are all lavender, and
only the inputs themselves are white. The effect is a purple screen with white slots in it.

Measured against the board:

| | Board | Build |
|---|---|---|
| Screen body behind cards | `#FDFDFD` — effectively white | `--ground: #F2EEFF` lavender |
| Map above an open sheet | `#C7C6D5` | our scrim computes to `#9A97AC` |

**Two separate mistakes, both mine to own.**

**The body should be near-white.** `lavender100` is a real token in the approved library, but the
boards use it as an *accent wash*, not as the default surface. Round 4 mapped `--ground` onto it
and every screen inherited a purple cast. Make the default body near-white; use lavender only
where the board actually uses it, which is a selected chip, a quiet wash behind a note, and the
faint cool tint of the map.

**The scrim is roughly twice as heavy as the board's.** Ours is 42% of deep indigo, which over a
near-white map computes to `#9A97AC`. The board measures `#C7C6D5`, which is about a 20% veil.
The interaction spec is stricter still: a 7% veil, and only at the full sheet height. Take the
spec's number, and stop veiling at the peek and half stops entirely.

**Selection states should not fill a whole row with lavender.** The board's selected control is a
filled violet disc with a white tick plus a violet border on an otherwise white row. Ours tints
the entire row, which is what makes a form of five choices read as a block of purple.

## Possible second defect in the same screenshot

The screenshot shows the screen doubled: two status bars, two back chevrons, and a ghosted copy
of the content offset to the left. That is either a mid-transition capture of the new outgoing
screen movement, which would be harmless, or an outgoing screen that is never removed, which
would be a real defect. Reproduce it before deciding, and if it is real it outranks everything in
this section.

---

## The incoming handoff package changes the palette again, and settles three open questions

`design/board-refs/BUILD-READY-HANDOFF-DESIGN.md` is the design for the full handoff package the
product owner is generating. It names a **canonical palette that differs from the one Round 4
adopted**, so Round 4's token values are already superseded.

| Role | Round 4 adopted | Handoff canonical |
|---|---|---|
| Deep indigo | `#17103D` | `#1E1142` |
| Violet | `#5B35F5` | `#4F34DB` |
| Sky blue | `#69B7FF` | `#76BCFD` |
| Marigold | `#FFBF24` | `#FDB327` |
| UI lavender | `#F2EEFF` | `#F5F2FC` |
| UI lavender, second step | `#E2DAFF` | `#E8E1F7` |

Every one differs. **Wait for the package rather than retyping these by hand** — it ships a
manifest with hashes and a verification step, and hand-transcribing six colours from prose is how
a seventh palette gets invented. But do not deepen the current values either: this is why the
purple problem must be fixed by *reducing where lavender is used*, not by hand-picking a new
lavender.

Note also the distinction the handoff draws and the build does not: **"UI lavender"** at
`#F5F2FC` and `#E8E1F7` is for surfaces, while **"lavender path"** `#CFBCEE` is the pin's base.
The build currently uses one lavender family for both.

**Three open questions are settled by this document, in our favour:**

1. **"Texas state information is provenance, not a trust tier and not a map-pin decoration."** The
   conflict between the boards drawing a flag beside map pins and the token spec saying receipt
   only is resolved: no flag on the map. The default taken was correct.
2. **"Evidence strength affects tier size within each map context."** The size hierarchy is
   sanctioned. The earlier rule that context may scale a pin but never change its *encoding* means
   exactly that — size is allowed, re-encoding Estimated as a glyphless ring is not. Both halves
   of Round 5's pin work are confirmed correct.
3. **"Estimated: hollow, dashed sky pin, italic information symbol, no check."** Confirms restoring
   the real pin, and names the symbol.

**Two requirements the build currently misses:**

- **Targets are 48px, not 44.** Every audit so far has measured against 44. Re-measure.
- **Body contrast targets 7:1**, which the build mostly meets but has not been held to as a floor.

**And one thing to expect:** the package ships a `map-kit` with "map base with pale-lavender land
and high-contrast streets". That is independent confirmation that the ground should be pale and
cool, and it will arrive as usable layers rather than as a description, so the ground rebuild
should use the kit rather than being hand-tuned first.
