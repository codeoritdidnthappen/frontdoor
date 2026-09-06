# EntryMap visual language

Extracted from the six concept boards in `board-refs/entrymap-design-mockups/ui-concept-boards/`,
which are the canonical visual source, read against the current build. The boards predate the
rename, so they show the old wordmark; everything else in them stands.

This document exists because "make it stunning" is not actionable and "match board 03, panel 2"
is. Each section says what the boards do, what the build currently does, and the gap.

The overall character: **light, airy, generous**. Soft illustration, white cards on a pale
lavender ground, one confident purple, marigold reserved for action and the scanned tier.
Nothing is cramped and nothing is decorated. The single exception is the welcome hero, which
is now the logo's own deep aubergine, because the logo is newer canon than the boards and
because an all-lavender opening was the specific thing that read as flat.

---

## 1. Illustration

**Boards.** Soft two-tone line illustrations with real depth: a storefront with columns,
lanterns, potted plants and a yellow door, sitting inside a pale lavender circle. Street scenes
with buildings, trees and a figure. Line weight is light, fills are pale blue and lavender, and
the one saturated element is a marigold door or awning that draws the eye.

**Build.** Flat rectangles with square windows. Correct in structure, absent in charm.

**Gap — the largest single one.** The illustrations are the product's warmth. Every one needs
rebuilding as a real drawing: consistent 2px line weight, two pale fills plus one marigold
accent, sitting in a soft circular or rounded field. This applies to the scan primer, the
location primer, the empty states and the onboarding art.

## 2. Cards and rows

**Boards.** White, radius roughly 16px, a hairline lavender border rather than a heavy shadow,
generous internal padding. A row is: leading line icon in a consistent box, label, trailing
control or chevron, with hairline dividers between rows inside one card.

**Build.** Cards rely on shadow rather than border, padding is tighter, dividers are
inconsistent.

**Gap.** Adopt border-plus-soft-shadow at one elevation level, raise padding, and make every
row use the same leading-icon box so labels align down the column.

## 3. Selection

**Boards.** Unselected is an empty ring on white. Selected is a filled purple disc with a white
tick, **and** the whole row gets a pale purple tint with a purple border. The state is legible
from across the room.

**Build.** Selection is mostly a tint or a border, and the tick treatment varies.

**Gap.** One selection component, used everywhere: needs picker, filters, notification toggles.

## 4. Buttons

**Boards.** Primary is solid purple, full width, radius roughly 12px, generous height.
Secondary is **white with a purple border**, never a grey fill. Tertiary is plain purple text.
The one deliberate exception is the camera permission, where the primary is **marigold**,
because it is the moment the product asks for something rather than offers something.

**Build.** Secondary was a grey-lavender fill; the welcome now uses the outline. The marigold
permission button is not implemented.

**Gap.** Outline secondary everywhere, and marigold for the camera ask specifically.

## 5. Pins

**Boards.** Chunky and confident. A filled teardrop with a white glyph inside: an information
mark for estimated, a person for scanned on-site, a storefront for owner-confirmed, with the
owner pin carrying a separate outlined tick. Each sits on a soft white halo that lifts it off
the map. Estimated is a dashed outline rather than a fill, which reads as provisional at a
glance.

**Build.** Pins are small and thin-stroked, and read as generic markers rather than as three
distinct tiers.

**Gap.** Increase size and weight, put the real glyph inside each, add the halo, keep the
dashed treatment for estimated.

**Superseded on the dash, 2026-09-05 (D37, then D43).** The owner: "the dashes around the
estimates and it also meaning partial is confusing. maybe estimated needs a new icon?" The
partial-match halo is dashed too, so one line style carried two meanings side by side. Round 8
replaced the mark with gallery-4 candidate J1: the same white-filled teardrop at the same
sizes, but a SOLID sky700 outline and the owner's own doorway glyph (two rounded posts, one
lintel, three dots across the open threshold) in place of the italic information mark. After
Round 8 a dash on the map means partial match and nothing else. Everything else in this
section still stands: size, weight, glyph-inside, halo. The rest of this document's
"Estimated" passages are the record of what was tried, not the current mark.

## 6. The map itself

**Boards.** Building footprints in two or three pale tones so blocks have texture, tree
clusters as soft blue rosettes, street names set in small caps along the street, and a visible
distinction between street and block.

**Build.** Flat white blocks, thin lines, sparse trees.

**Gap.** Vary the block fills, thicken the streets slightly, and let the street labels sit
along the roads rather than floating.

## 7. The scan flow

**Boards, panel by panel.**

- **Primer.** Illustration in a lavender circle, a lock icon with "Only the doorway is
  captured", marigold "Allow camera", "Not now" as a text link.
- **Capture.** Real viewfinder with white corner brackets, a dark translucent coaching pill
  centred at the top ("Center the full doorway") and a second at the bottom ("Step back a
  little"), a dashed horizon line with a small centre circle, and a large marigold-ringed
  shutter.
- **Processing.** A large purple progress ring with the countdown inside it, then three named
  check rows, each a card with a circular icon and a progress indicator, then "Usually under 8
  seconds" and an explicit reduced-motion note.
- **Review.** The photograph, "Visually confirmed" with feature chips, then Retake as outline
  and Publish scan as solid purple.
- **Published.** A mini map showing all three tiers with a legend, and the provenance row.

**Build.** The self-drawing ring and named checks are implemented and are the strongest motion
in the product. Missing: the countdown inside the ring, the corner brackets and dual coaching
pills, the marigold shutter ring, and the mini map with legend on the published screen.

## 8. Typography

**Boards.** Two levels do most of the work: a bold two-line headline at roughly 24px with tight
leading, and a lighter grey subtitle at roughly 15px with generous leading. Row labels are
medium weight, not heavy. Weight 900 appears only in the wordmark.

**Build.** Weight 900 is used very widely, which flattens hierarchy, and display text carries
body leading.

**Gap.** Reserve the heaviest weight for the wordmark and headline numbers. Row labels drop to
600 or 700.

## 9. What the boards get right that the build must not lose

- 44px targets and 7:1 text contrast are called out on the boards themselves. They are part of
  the visual language, not a constraint applied afterwards.
- The Texas flag appears only as provenance, never as a badge.
- Pins communicate evidence source and strength, never a rating.
- "Sources, dates, and confidence — not a badge" is printed on board 02. That sentence governs
  every surface.

---

## 10. Map hierarchy and density

The map currently renders every place as the same pin at the same size. With sixty-four of them
in a few blocks the screen reads as noise: no focal point, no reading order, and no way to tell
at a glance which markers are worth attending to. Same-size pins also waste the one thing a map
has that a list does not, which is the ability to say what matters by how it looks.

**The hierarchy encodes evidence strength, and nothing else.** Not accessibility quality, not a
rating, not a recommendation. This is the board's own rule, printed on board 02: pins
communicate evidence source and strength. A bigger pin means we know more about that entrance,
never that the entrance is better. Stated that way the hierarchy is not only defensible, it is
the most honest thing the map can do, because the weakest evidence currently shouts as loudly as
the strongest.

**Four levels.**

| Level | Tier | Treatment | Why |
|---|---|---|---|
| 1 | Owner-confirmed | Full pin, largest, purple, storefront glyph, tick badge, halo | Rarest and strongest evidence: someone at the door attested to it |
| 2 | Scanned on-site | Full pin, medium, marigold, person glyph, halo | Somebody stood there and photographed it |
| 3 | Estimated | A small dashed ring, no glyph, no teardrop | It marks that a door is probably there without borrowing the visual weight of evidence |
| 4 | Cluster | One numbered disc | Density, not a place |

Level 3 is the change that does most of the work. Estimated is both the most numerous tier and
the weakest claim, and drawing it as a full pin is what makes the map look busy and overclaim at
the same time. As a quiet dashed dot it becomes texture: present, countable, tappable, and
clearly provisional.

**State modifiers, applied on top of the level.**

- **Selected** scales up and takes a stronger halo; everything else drops slightly in opacity.
  Nothing is ever hidden.
- **Needs match**, when a needs profile is set: matching places hold full opacity and take the
  match ring; non-matching recede in opacity only. Recession is not a negative verdict, and no
  mark is ever added to say a place fails.
- **Zoom out** collapses estimated entirely into cluster counts, leaving only levels 1 and 2 as
  pins, so the wide view answers "where has anyone actually been" rather than "where are there
  doors".

**Density rules.**

- Where two markers overlap by more than about 40%, the weaker level yields: an estimated ring
  merges into a cluster before a scanned pin does, and a scanned pin yields before an owner pin.
- Around a dozen full pins is the ceiling at phone width. Past that, cluster.
- The selected place is exempt from every rule above: it is always drawn, always on top.

The result is a reading order the eye follows without instruction. The few purple pins first,
the marigold ones next, and the estimated rings registering as ground texture rather than as
sixty-four competing items.

---

## 11. Map ground: depth and colour

Two complaints, and they are separate problems with a shared answer.

**"The map is so flat."** Every block is the same tone, every street the same width, and the
trees are token dots. There is no road hierarchy, no landcover, no implied light, and nothing
sits on top of anything else. A real map reads as a place because it has all four.

**"Use more of the icon colours within the map."** The ground is nearly monochrome while the
palette carries five hues, so the map looks unrelated to the product sitting on top of it.

**The constraint that shapes the answer.** Blue means estimated, marigold means scanned on-site,
purple means owner-confirmed, green means needs-match and amber means ageing evidence. Those
meanings are load-bearing and they live on markers. If the ground starts using the same hues at
the same strength, a green park becomes indistinguishable from a match halo and the palette
stops meaning anything.

So the rule is **saturation, not hue**. The ground may echo the whole palette, but only at a
saturation and value where it reads as terrain and never as state. A marker must always be the
most saturated thing within its own radius. Concretely: ground hues stay well below the
saturation of any semantic colour, and no ground element ever uses a semantic hue at full
strength, ever carries a marker's shape, or ever sits inside a marker's halo.

**Depth comes from four things, none of which is a drop shadow on the map.**

1. **Road hierarchy.** Primary streets wider and brighter than side streets, alleys thinner
   again. Currently every street is one width, which is most of why it reads as a diagram.
2. **Block variety.** Building footprints in several close tones rather than one, so a block
   reads as many buildings instead of one slab.
3. **Implied light.** A consistent soft edge on the same side of every footprint. One direction,
   applied everywhere, is what makes footprints sit on the ground rather than float on it.
4. **Landcover.** Plazas, tree canopy, and water if any is in frame, as real areas rather than
   scattered dots.

**What must survive.** The three pins keep their measured contrast against whatever ground is
chosen, at 3:1 or better; a richer ground is the most likely way to break the fix that just
landed, so it is re-measured, not assumed. High contrast mode still simplifies the ground rather
than enriching it. The ground never competes with the card sheet for attention, and street
labels stay legible at phone size.

---

## 12. The wordmark and the bottom bar

Two specific corrections from the product owner, both about the palette being absent from the
app's own furniture.

**The wordmark in the map header is wrong.** It renders as one flat colour. The logo is
two-tone: *entry* in light blue, *map* in white. The header pill is white, so white-on-white is
not available there and the light-background pairing has to be used instead: *entry* in a blue
dark enough to hold on white, *map* in the dark ink. Both halves must be legible and the
two-tone reading must survive. The onboarding mark already defines this pairing; the header
should use the same one rather than inventing a third.

The rule underneath: the wordmark is always two-tone, and which two tones depends on what it
sits on. On deep aubergine it is light blue and white. On white it is deep blue and dark ink.
It is never one colour.

**The bottom bar is monochrome and should not be.** It is purple on purple. The logo carries
deep blue, light blue, marigold and white, and none of that reaches the one component visible
on nearly every screen. Bring the palette into it.

The constraint is the same one that governs the map ground: on markers those hues carry
meaning, so in the navigation they must read as brand rather than as state. That is achievable
because the bar is persistent chrome and nothing in it represents a place. Keep the active tab
unambiguous, keep every label legible, and do not let the scan button's marigold ring read as
the scanned-on-site tier.

---

## 13. The state record is not a filter, and the top tier is not "verified"

Two related complaints, and both come from the same place: the map looks weak because nothing
reaches the top, and the state record sits awkwardly in a list of needs where it does not belong.

**The state record comes out of the filters.** Filters describe what a person needs to get
through a door: step-free entry, a wide door, easy-grip hardware. "Has a Texas accessibility
inspection on record" is not a need. Nobody needs a record. They need a doorway they can use,
and a record is a fact about a construction project from some year, attached to whoever the
tenant was then. Offering it as a filter invites people to filter by a proxy for quality, which
is precisely the trust-as-a-filter mistake the design already rejects for our own tiers. If we
will not let someone filter to Owner-confirmed, we certainly cannot let them filter to a state
record that is weaker evidence about the current door.

It stays where it is honest: a provenance line on the card, and a row in the evidence receipt.
Source and date, like every other line.

**There is no "100% verified", and the absence is deliberate.** The ladder runs Estimated,
Scanned on-site, Owner-confirmed, and it stops there because the next rung would be a compliance
claim we cannot make from photographs. That is the whole honesty position. But the complaint
underneath is fair: a map where almost nothing reaches the top rung reads as a product that
knows nothing.

The fix is not a new tier. It is two things that are already in hand.

1. **Publish the on-site scans.** 11 of 64 places show as Scanned on-site while the operator
   photographed all 64. That is the map understating itself, and #333 corrects it.
2. **Let confidence do the work the tier cannot.** Confidence is agreement between independent
   sources, and it is already on the card. A place with an on-site scan, an OpenStreetMap tag
   that agrees, and a state record on file is genuinely better evidenced than one with a single
   scan, and the card can say so without inventing a rung. Three sources agreeing is the
   strongest honest thing we can show.

**The step-free problem specifically.** Step-free entry is the criterion people most need and the
one street imagery evidences worst, so estimated places go quiet exactly where it matters. Also
already in hand:

- **On-site scans answer it.** A capture taken at the door shows the ground plane.
- **Depth answers it where the model alone struggles.** Monocular depth took step-free from
  88.5% to 96.2% on held-out entrances and caught all seven of the vision model's known misses.
  It is the one enhancement of four that earned a place, and it belongs in the engine, gated.

Between them, the criterion stops being the weak column. What is left unanswered stays "couldn't
confirm yet", which is the honest state and not a failure.

---

## 14. What the approved library specified about pins (SUPERSEDED by section 15)

Checked against the library rather than assumed, because the two things are easy to conflate.

**The library defines halos, and they mean needs-match, not evidence.** Three assets at a
common 104-unit box: good, partial and unknown. Its README is explicit that they communicate
state "through line style as well as color", which is the same colour-independence rule the
build already follows. It also fixes the pin-drop at 620ms, collapsing to the end state under
reduced motion.

**The library does not define a size hierarchy by tier.** All three pins are drawn at the same
scale: estimated and scanned on-site at 96 by 104, owner-confirmed at 112 by 104, and the extra
width is the tick badge, not added importance. Drawn from the library alone, every pin on the
map would be the same size, which is exactly the screen the product owner described as messy.

**So the two systems answer different questions and both are needed.**

| | Question it answers | Where it comes from |
|---|---|---|
| Halo, three line styles | Does this place fit *my* needs? | The approved library |
| Size, four levels | How much do we *know* about this entrance? | This project, from the "all the same size" complaint |

They compose without conflict: a small estimated ring can carry a good-match halo, and a large
owner pin can carry none. One is about the person looking, the other about the evidence held.

**The deviation, stated plainly.** Scaling the approved pin artwork by tier is a departure from
a library that draws them at one size. It is deliberate and it is the product owner's own
instruction. The artwork, the colours, the glyphs and the halo line styles all come from the
library unchanged; only the rendered size varies, and it varies on evidence strength, never on
how good an entrance is. If that deviation is ever revisited, the thing to preserve is the
reading order, not the specific sizes.


---

## 15. The approved pin hierarchy, and where our build conflicts with it

The complete production package adds `tokens/pin-hierarchy.json`, which section 14 was written
before. It supersedes that section, and it conflicts with what Rounds 2 and 3 built. The
conflict is worth stating exactly rather than resolving quietly, because both sides have a
real argument.

**What the library specifies.**

| Context | Estimated | Scanned | Owner |
|---|---|---|---|
| Overview | 32 | 36 | 40 |
| Street | 40 | 44 | 48 |
| Selected | 52 | 56 | 60 |
| Receipt | 24 | 28 | 32 |

Cluster 48, live scan drop 64. A full z-index order, from clusters at the bottom through the
tiers to matched, selected and the live drop on top. Overlays are specified too: selected is a
white keyline with an indigo outer line and a 12% lift that *preserves tier colour and icon*;
match is solid, dashed or dotted; freshness is a small amber clock that **never recolours the
pin**; the Texas record appears in the receipt and never on the pin face.

**The principle it opens with is the crux:** *"Trust tier and contextual prominence are
independent. Context may scale a pin but never changes its tier encoding."*

**Where our build breaks it.** Round 2 demoted Estimated from a pin to a 14px dashed ring with
no glyph. That is not a scale change, it is a change of tier encoding, which the library
forbids. Our spread is roughly three to one; the library's is 1.25 to one.

**But the library's spread alone does not solve the problem it was asked to solve.** Fifty-two
estimated places in three blocks, drawn at 32px, is still fifty-two full pins. That is the
screen that was called messy, and 32 against 40 will not separate it.

**The reconciliation, and it is available inside the library's own vocabulary.** Put the density
work where the library already puts it: clustering. The token set gives clusters a size and the
lowest z-index, and the package ships a `mixed-cluster` asset, so a cluster holding several
tiers is an anticipated state rather than an invention. Cluster aggressively at overview and the
visible mark count falls without any tier being re-encoded.

So: **adopt the library's sizes, z-index, overlap order and overlays exactly, restore Estimated
to a real pin, and move the calm-down from shrinking a tier to clustering.** That keeps the
approved encoding intact and still answers the original complaint, which shrinking never had to
be the only way to answer.

If clustering at overview does not calm the map enough on the real dataset, the honest next
lever is the zoom-level scale the library already defines, not a further deviation from it.

---

## 16. The updated boards change the app's chrome, and our build has it wrong

The boards in the final package are not the ones earlier sections were written against. They
show a structurally different app, and the difference is exactly what "use more of the icon
colours" was asking for. This section is the target; where it disagrees with sections 1 to 9,
this wins.

**The chrome is dark indigo, top and bottom.**

| | Board | Our build |
|---|---|---|
| Header | A solid deep-indigo bar across the top, carrying the two-tone wordmark at the left, the location pill, and a menu button | A floating white pill over the map |
| Bottom navigation | A solid deep-indigo bar, labels in white, the scan control a marigold ring | White, with coloured labels |
| Screen titles | Centred in the dark header with a back chevron beside them | Various |

That single change is most of the brand presence the build is missing. A white floating pill on
a pale map is the design of an app that is trying not to be noticed; the indigo bar is the
product asserting itself, and it is what makes the sky blue in the wordmark legible, which was
the specific complaint that could not be answered on white.

**Pins on the board.** Estimated is a white-filled teardrop with a dashed outline and an
italic information mark. *(Round 8: the dash and the italic "i" are both replaced &mdash; see
the supersession note in section 5. The teardrop, the white fill and the halo are unchanged.)* Scanned on-site is marigold with a dark person glyph, sitting on a soft
lavender halo disc. Owner-confirmed is violet with a white storefront glyph and a **separate
outlined tick badge floating clear at the upper right**, not merged into the pin. The halo is a
soft filled disc behind the pin, not a ring drawn around it.

**The card.** Freshness and Confidence sit side by side as two tiles, each with a leading icon,
above a list of feature rows with chevrons. The evidence receipt is its own card, opened from a
full-width outlined button, and it lists photographed date, neighbour count, owner count and the
state record as icon rows.

**One conflict to settle rather than absorb.** The boards draw the Texas flag on the map, beside
the scanned pin, on three of four panels, while `tokens/pin-hierarchy.json` says the state
record is "receipt provenance only; never placed on the pin face", and our own canon withdrew
the pin accessory deliberately because icon soup around pins was the original complaint. The
board's own caption says "Texas flag = provenance only", so the board is arguably illustrating
provenance rather than sanctioning a map accessory.

**Default to the token spec: no flag on the map.** It is the machine-readable rule, it agrees
with our canon, and the pin accessory is the thing that was already rejected once. Worth putting
to the product owner rather than deciding silently, because the boards are what he approved.


---

## 17. Do not adopt the asset library's brand mark

Recorded prominently because it has already cost an hour once and will cost it again.

The approved logo and the asset library's reproduction of it disagree, and **the library is the
one that is wrong**. The logo has three colours arcing above the doorway — sky blue left, **white**
centre, marigold right — over a white disc behind the doorway. `svg/brand/mark-primary.svg` drops
the disc and draws the middle arc in `#5B35F5`, the same violet as the pin body it sits on, so it
shows one colour above the entry instead of three and reads as a bucket rather than a doorway. Its
PNG exports at every size carry the identical defect.

Round 4 adopted it faithfully during the token pass. The product owner's first reaction on seeing
the result was that he could no longer see the three colours above the entry, which is exactly
what the asset does.

**Use `07-entrymap-approved-logo.png`.** `design/logo-mark.png` is that artwork cropped with the
background keyed out. If vector is needed, redraw from the image, and confirm three colours are
visible above the entry before calling it done.

This is flagged in the frontdoor repository too, on the native handoff ticket, so nobody adopting
the library there reproduces it.

## 18. Surfaces: the product has two, and one design system

Recorded here in Round 7 because until then it existed only on GitHub and in conversation:
`grep -i "emily|wliang|swift|hybrid"` across `design/*.md` returned nothing, so a reader of
the design canon could not tell which surfaces were being designed for what. Detail lives on
**frontdoor issue #367** (cross-linked on #275); this is the short version the canon needs.

**The decision.** "how to get this in the app as well rather than remaining a web view" ->
"okay lets do hybrid." Not a migration, and not a staged retirement of the web app.

**The boundary.**

| Surface | What runs there |
|---|---|
| Native | Camera capture, the privacy pass over a captured photo, and upload |
| Native | The map, the business card and discovery |
| Web | The whole product again, as the no-install route |

**The rule that keeps it one product.** The web app is not a fallback and is not scheduled to
be retired; a person who will not or cannot install anything gets the same product. Which
means: **a token, an asset or a motion value changed for one surface is changed for both, in
the same change.** There is one palette, one type scale, one spacing scale, one motion table
and one asset library, and they are the ones in
`design/board-refs/entrymap-build-ready/asset-library/`. A surface may differ in how it
implements a control; it may not differ in what a control means, what colour carries which
meaning, or how long anything takes.

**Two live consequences, both recorded rather than assumed fixed.**

1. The Swift design-system PR carries the **superseded** palette on all ten values that moved
   in Round 7. It was flagged on the PR. There is no ticket and no owner for the correction.
2. Anything native that adopts `asset-library/svg/brand/mark-primary.svg` reproduces the
   broken mark described in section 17. Section 17 applies to both surfaces.

**Section 5 amendment (Round 7).** Section 5 and the Round 6 reading of it say the trust pins
sit on "a soft lavender halo disc". Checked against the package's own screen exports, that is
a *state*, not a base: at the same 30x20px patch beside the Scanned pin,
`screen-exports/png/map-default.png` measures `#F6F5FD` (plain land, no disc) and
`screen-exports/png/map-filtered-results.png` measures `#D7D6FB` (a disc). The two differ only
in that a needs profile has been applied. The map kit agrees from the other side: none of its
eight variants draws a disc under a pin, and `after-profile.svg` fills the halo group with the
three ring halos instead. The disc is therefore drawn only when a match state is present. It
is the same disc for all three tiers, so it still carries no tier information and recolours
nothing.
