# EntryMap prototype — graphic design critique

Reviewed against the six approved boards (`design/board-refs/entrymap-assets/01–06`), the approved
logo (`07`), and the 107-asset library (`asset-library/`). The build was served over HTTP and driven
at 390×844 across all 26 screens plus every sheet, both map zoom levels, and the scan and correction
flows walked end to end rather than jumped to by id.

This is a judgement, not a conformance check. The boards are the target, not the ceiling; drift that
made something better is called out as such.

---

## 1. What is genuinely good, and why

**The evidence ladder is drawn, not merely stated.** Three tiers are carried by *shape first* —
dashed blue teardrop with a serif italic `i`, solid marigold teardrop with a figure, purple teardrop
with a storefront and a check badge — and the same three marks reappear identically on the welcome
tiles, the map legend, the trust popup, the card badge, the list rows, the contributions list, and
the owner header. A user can learn the system on screen one and never be re-taught. This is the
hardest thing the boards asked for and it is the thing the build does best. Colour is never load-
bearing alone: the count of filled confidence dots and the literal word always ride along.

**The My Needs sheet and screen are the best-composed surfaces in the build, and they improve on the
board.** Board 01-03 gave each persona an icon, a label and a radio. The build adds a sub-line —
"Wheelchair / Step-free entry, ramp, wide door" — which converts a preference list into an
explanation of what the choice actually does. Five rows of identical width, identical internal
rhythm, one strong left icon column, one clean right control column. This is what the rest of the
app should look like.

**`ow-review` (Review changes) is an invention with no board panel, and it is the most professionally
designed information screen here.** Struck-through old value → arrow → lavender pill new value, with
`WHAT CHANGES` and `PROVENANCE AFTER PUBLISHING` as the two section headers. It makes an abstract
promise ("nothing publishes until you confirm") into something you can see. Keep it exactly as it is.

**The Accessibility screen's text-size control demonstrates itself** — three `A` glyphs at 14/17/20px
in a segmented group — and the live `PREVIEW` entrance card below it responds to the settings. That
is a designer's idea, not an engineer's, and it is executed cleanly.

**The Freshness / Confidence tile pair on the place card is the strongest single component in the
build.** Small-caps eyebrow, bold value, quiet sub-line, two equal tiles side by side. Board-faithful
and better set than the board.

**The map ground, at the zoomed-out level, genuinely reads as a place.** Warm cream blocks, lavender
parcels, a pale sage strip, thin white streets, and vertical street labels running up Congress,
Lavaca and Colorado. It has more warmth and more of Austin in it than the boards' cool blue-grey
ground did. This is real drift-for-the-better, and it is invisible at the default zoom (see 2.2).

**The dashed blue "Not yet seen is never a mark against the place" panel on `ow-overview`** is not on
any board. Blue is the unknown-tier colour, the dashed border is the unknown-tier line style, and the
sentence is the product's ethics in one line. Right tone, right system, right place.

**The five outline illustrations read as one hand.** `door`, `saved`, `offline`, `camera` and
`thanks` share white fill, a `purple-ink` outline at 2.1–2.4px held at ~0.6 opacity, a lavender disc
backdrop, a single marigold accent and a single sky-blue accent. That discipline is real and rare.

**The search overlay and the list view are clean, consistent with each other, and consistent with the
map rows.** The list view is not on any board and it earns its place.

---

## 2. Fix before showing this to anyone

Ordered by how much the fix improves the product.

### 2.1 The selected map pin paints on top of every sheet

**Screens:** `sheet-correct` (Suggest a correction), the empty-area invite on `screen-map`.

The selected pin (`.pinbtn.lvl1.selected`) takes a lift z-index to raise it above its neighbours, and
that lift escapes the map's stacking context. Measured: the pin's SVG sits at x 126.7, y 386.6,
57×49 — directly on top of the `WHAT CHANGED?` label and the first select of the correction form. On
the empty-area card the same pin lands on the word "entrances" in "No entrances mapped here yet."

**Why it matters:** it is the single most obviously *broken*-looking thing in the build, and it is on
the two screens most likely to be walked in a demo of the community loop. Nothing else here reads as
a bug; this reads as a bug.

**Change:** scope the selected-pin lift to a z-index inside `#map`'s own stacking context (give `#map`
`isolation: isolate` or a base `z-index`), so `.selected` can never exceed the sheet layer.

### 2.2 The default map is 52 identical rings, and the legend teaches a mark the map does not draw

**Screen:** `screen-map`, default zoom.

Counted in the DOM: 64 markers — 52 `Estimated`, 11 `Scanned on-site`, 1 `Owner-confirmed`. The 52
estimated markers render as a plain 14px circle ring, evenly scattered across the whole viewport;
they are the dominant visual texture of the app's home screen, and they carry no information a user
can act on. Meanwhile the 11 amber pins collapse into an overlapping heap around W 3rd St — five pins
whose tips and domes physically collide — and the single owner-confirmed pin, the most valuable
marker on the map, is smaller in visual weight than the pile above it.

Two further problems compound this:

- **The legend contradicts the map.** The legend's first row draws the library's `estimated` asset —
  a dashed teardrop with a serif `i`. That mark appears nowhere on the default map, where estimated
  is a ring. The legend is teaching a vocabulary the map does not speak.
- **The clustering already exists and is not used here.** Zoom out and the build produces handsome
  dashed purple count-clusters (2, 3, 4, 5). The machinery is built; the default view just doesn't
  reach for it.

**Why it matters:** board 02-01 put three pins on the map and let the ground breathe, because the
board's argument is "pins communicate evidence source and strength." Sixty-four markers, fifty-two of
them identical and mute, communicate density. The eye goes to the amber heap first — which is an
accident of overlap, not a designed priority — and the owner-confirmed pin, which is the whole point
of the trust ladder, goes third.

**Change:** cluster at the default zoom too, using the cluster mark that already exists; render
`estimated` at default zoom as the library's dashed teardrop at reduced size and reduced opacity so it
recedes rather than repeats; and let the owner-confirmed pin keep its full scale while its neighbours
step down.

### 2.3 The welcome screen's skyline is the only drawing in the app that isn't part of the family

**Screen:** `ob-welcome`.

The skyline is not one of the seven illustrations. It is a bespoke inline SVG: six flat rectangles in
three purples, no outlines at all, with 8px square windows in sky-blue and marigold scattered at
random heights, plus two pale grey boxes at two building bases. Measured, it sits at x 26, width 338
inside a 390 screen — so the city has hard vertical edges 26px in from both sides, floating in
aubergine.

Specifically:
- **It shares no drawing language with the seven.** No white fill, no `purple-ink` 2.1px outline, no
  lavender disc, no line discipline. It is the only flat-fill drawing in the product and it is on the
  screen with the highest impression count.
- **The windows have no floor rhythm.** Building 1 has two windows at one height; building 2 has four
  at three heights; building 5 has three at two. Real windows form a grid. These read as confetti.
- **There is no door.** In a product called EntryMap, the first illustration a user sees contains no
  entrance. Board 01-01's opening illustration is a street with a highlighted yellow door — the
  product's subject, made the focal point.
- **It doesn't bleed.** The 26px inset is the hero's own padding leaking onto a full-width element.

**Change:** replace it with the `street` drawing re-cut for the aubergine (its colours are already
tokens and will re-tint), full-bleed to the screen edges, cropped so the shopfront row sits on the
white card's top edge, with one lit yellow doorway. See §4 for why that also fixes the aubergine
argument.

### 2.4 Demo scaffolding is showing in shipped copy

**Screens:** the place card (`Owner update · today (staged for demo)` — on the card's *primary*
provenance row, in the headline position), `claim-track` (`Open My Business (staged)` — a button
label), `screen-profile` (`Workspace ready — staged for this demo`).

**Why it matters:** every other piece of copy in this build is carefully written. Three lines of
build-time scaffolding in the middle of it tells a viewer they are looking at a draft, on the exact
screens meant to demonstrate polish.

**Change:** move the staging note out of the string and into a dev-only affordance, or delete it.

### 2.5 Placeholder data reads as broken data

**Screens:** the estimated card ("Oct 2014", "Last scanned 12 years ago", "Seen 12 years ago" in the
list view), `screen-map` list rows (`[solidcore] Downtown Austin` — literal square brackets read as
an unresolved template token even though it is the real brand name).

**Change:** age the estimated fixture to something plausible (14–18 months, which is what "aging"
means in the freshness system anyway) and strip or restyle the bracketed name.

### 2.6 Two trailing-punctuation errors on visible screens

`scan-capture`: "Scanning near W 3rd St ·" — a trailing middot with nothing after it.
`ow-review`: "· 1 still needs a change" — a leading middot on a line that starts a paragraph.

Small, but these are the kind of thing that decides whether a viewer believes the rest was checked.

### 2.7 The place card is a stack of rows, and the wrong row wins

**Screen:** `sheet-card` at full height.

The card is the product's most important object and it is currently a scroll, not a composition.

- **The eye goes to the photographs first.** Two full-colour photographs — warm reds, greens, a
  rainbow flag — sit in the middle of an otherwise purple/marigold/off-white card. They are the
  highest-chroma, highest-contrast thing on the screen, and neither of them clearly shows the
  *entrance*. Board 02-04's card had no photography at all; every element was a drawn asset, and the
  freshness tile was the first thing you saw. In the build, freshness is third.
- **The Freshness and Confidence tiles are constructed identically but coloured differently.**
  "Updated today" is near-black; "Medium ●●○" is purple. Two adjacent halves of one component, one
  loud and one quiet, for no reason. The purple half wins, so the louder of the pair is Confidence —
  and Freshness is the thing a returning user actually checks.
- **On the estimated card the same pair breaks apart entirely**: Freshness becomes a filled marigold
  tile with marigold text, Confidence stays a pale lavender tile with purple text. Same component,
  two different container treatments, on adjacent screens.
- **The feature icons are missing.** The library's eight feature icons — step-free-entry, wide-door,
  easy-grip-handle, ramp-visible, auto-door-button, accessibility-signage, clear-approach — are among
  the most characterful assets in the system, and board 02-04 used them as row-leading glyphs on the
  card. The build's card substitutes text-only chips with dots. The icons *do* appear on
  `ow-overview` and `ow-edit`, so they are wired up; they are simply absent from the screen where
  most users will meet them.
- **The chips hug their content**, so "Handrails ●●○" and "Clear approach ●●●" are different widths
  with a large hole at the right of the row. On `scan-review` the same chips are centre-stacked at
  three different widths, zigzagging on both edges. On `ow-listing` they are laid out as a tidy 2×2
  grid of near-equal widths. One component, three layouts, three screens.
- **A chrome instruction lives in content space.** "Tap or drag the handle for more · swipe down to
  close" sits between the badge and the tiles, in a third grey, occupying a full line of the card's
  most valuable real estate — and the handle it refers to is not drawn in the peek or half states
  (the filters sheet and the `ow-listing` preview both draw one).
- **The provenance rows use three different sub-line colours** in three consecutive, structurally
  identical rows: purple, amber, grey. The block twitches.
- **The AI row uses a four-point sparkle** — a generic AI-product cliché in a system that otherwise
  draws specific, purposeful glyphs. The library already has an `estimated` mark for that rung.
- **The card's bottom slices a sentence.** With no bottom padding and no scrim, the last visible line
  is cut mid-glyph at the nav bar's edge, and the Map tab's light-blue active indicator lands on top
  of the text.

**Change, in order:** move the photo strip below the provenance rows or reduce it to one thumbnail;
give both tiles the same value colour; restore the feature icons and lay the chips as a fixed 2-column
grid; delete the handle instruction and draw the handle; unify the provenance sub-lines to one grey;
replace the sparkle with the estimated mark; add bottom padding equal to the nav height plus a fade.

### 2.8 The estimated card decorates everything and quiets nothing

**Screen:** `sheet-card` for an estimated place.

In one scroll: a filled marigold Freshness tile; a filled marigold "Could you take another look?"
card; a marigold pill *inside* that card; a marigold "Re-check entrance" button; a blue dashed panel
saying "No photo yet — be the first to scan"; a purple provenance row; a second blue dashed panel
saying "Not yet seen — be the first to scan"; and another marigold button below it.

Three separate calls to the same action, two nearly identical blue dashed panels 200px apart, and
four consecutive marigold surfaces with no neutral ground between them. There is nowhere for the eye
to rest and no way to tell which thing is the point.

**Change:** keep exactly one re-check CTA (the amber card), make Freshness a pale tile like every
other Freshness tile, and merge the two blue panels into one line inside the features section.

### 2.9 The scan processing screen has no bottom and no counter

**Screen:** `scan-processing`.

In the real flow the ring fills with the captured frame and a marigold arc, which is good. Two
problems survive:
- **There is no number in the ring.** Board 03-03's ring holds a large "7 / sec". The build's ring
  holds an image and no time, so the screen's central promise — that this takes seven seconds — is
  made only by a 12px grey line 200px below it.
- **The bottom 250px is empty.** Title at 60, ring at 170–330, checklist at 400–520, caption at 560,
  then nothing until the nav bar at 758. Board 03-03 filled the frame with three carded rows, "…"
  progress indicators, and the reduced-motion note. The build's three rows are bare circles and grey
  labels with no cards and no icons, so they read as an unfilled form rather than progress.
- **Navigating to this screen at rest shows a hollow grey donut and three empty grey circles** — a
  real risk if anyone drives the prototype by screen id during a demo.

**Change:** put the elapsed/remaining seconds in the ring, restore the icons and card treatment on the
three rows, and pull the block up so the checklist sits in the lower third rather than floating.

### 2.10 Body text renders at six different sizes for the same role

Sampled computed styles: the same "row sub-line" role renders at **14.25px, 12.9px, 12.667px,
12.255px, 11.7px and 11.467px** on different screens. The cause is that the scale is expressed in
`em` (`--fs-body: 0.95em`, `--fs-sub: 0.86em`, `--fs-micro: 0.7em`) and those multiply against
whatever nested container they land in — which is why sizes like 11.115px and 12.255px exist at all.
No type scale contains an 11.115.

`screen-profile` alone uses **twelve distinct size/weight pairs**. `ow-overview` uses ten.

**Why it matters:** this is the invisible reason the app reads as slightly less crisp than the boards
even where the layout is right. A reader can't feel a 0.6px difference consciously, but they feel
that "sub-line" doesn't mean one thing.

**Change:** set the scale in `rem` (or explicit px per role) so a role has one size everywhere, and
cut the profile screen's twelve pairs to five or six.

### 2.11 The tier badge has five different treatments

Counted across screens: filled marigold pill with dark text (`ow-overview` header, `ow-listing`);
pale marigold tint pill (`screen-a11y` preview, the recheck pill); outlined white pill with a purple
glyph (card peek, "Good match"); filled purple pill with white text (card full state); blue dashed
outlined pill with a `+` (estimated card). The same "Owner-confirmed" badge is an outlined white pill
in the card's peek state and a filled purple pill in the same card's full state.

**Why it matters:** the badge is the trust ladder's smallest and most-repeated unit. Five treatments
means it stops being a unit.

**Change:** pick two — filled for the place's own tier, outlined for anything descriptive — and apply
them everywhere, including across a single card's own states.

### 2.12 The trust popup is transparent over live content, with no scrim

**Screen:** `sheet-trust` ("How trust grows"), reachable from the map legend and from Profile.

The panel is translucent and does not dim what is behind it, so amber pins and the street label
"W 3RD ST" read straight through the body copy. Opened from Profile it renders over the settings
list, and both texts are simultaneously legible and both are unreadable. Every other sheet in the
build dims correctly, so this is an outlier, not a house style.

Two more faults: it opens overlapping the legend card it came from, so "How trust grows ›" appears
twice, 25px apart; and its three pins are at three different heights (30/34/36px), so the left column
is ragged where every other icon column in the app is aligned.

**Change:** give it the same scrim and opacity as the other sheets, position it clear of its opener,
and normalise the three pins to one optical height rather than one bounding-box height.

### 2.13 The claim timeline centres each item beside a straight rail

**Screen:** `claim-track`.

"Submitted / Just now — done", "Business match / Just now — done" and "Ownership review / In
progress" each have their sub-line centred *under their own title* rather than sharing a left edge.
Beside a perfectly straight vertical rail with three circles on it, the text block wanders. Board
05-04 has one left edge for all six lines. A timeline's entire graphic argument is a strong left
edge; this discards it.

**Change:** left-align all titles and sub-lines to a single edge offset from the rail.

### 2.14 Sheets and screens are cut by the nav bar with no allowance

The filters sheet's "Show N places" button is below the fold at 390×844 — the action the sheet exists
for cannot be seen without scrolling. The place card slices a sentence. `screen-corr-done` hides
"See my corrections" behind the scan FAB. `ow-review` and `ow-photos` clip a row mid-height.
The status bar has no scrim on light screens, so scrolled content passes over "9:41" and the battery.

**Change:** a sticky footer on the filters sheet; bottom padding of nav height + 16 on every scroll
container; a light scrim or blur behind the status bar on light chrome.

### 2.15 "Nothing saved yet — Save lives on every card."

**Screen:** `screen-profile`.

"Save" is meant as a button name. Without quotes or capitalisation the sentence parses as a claim
that saving saves lives. In a product about accessibility this is a sentence you do not want on a
screenshot.

**Change:** `Nothing saved yet — "Save" appears on every card.`

---

## 3. The seven illustrations, judged independently

All seven were rendered at 180–560px and inspected against the boards. The author's own rating of the
street scene as weakest is correct, and the reason is precisely diagnosable.

| # | Drawing | Used on | Verdict |
|---|---------|---------|---------|
| 1 | `door` | scan primer | **Survives.** Best of the set |
| 2 | `saved` | saved empty state | **Survives.** Most inventive |
| 3 | `thanks` | correction submitted | **Survives with a fix** |
| 4 | `offline` | states card 1 | **Survives, but it is #1 with a sticker** |
| 5 | `camera` | states card 2 | **Would not survive.** The lens is wrong |
| 6 | `street` | empty-area invite | **Would not survive.** Perspective is asserted |
| 7 | `map` | onboarding + states card 3 | **Would not survive.** Off-family, and it mis-sells the map |

**1 · `door` — survives.** A symmetric portico: pediment, two columns, two hanging lanterns, two
potted shrubs, three steps, a yellow four-panel door with a handle dot. Consistent 2.1px stroke,
confident symmetry, and it puts the marigold on the *door* — the product's subject. Faults are minor
and all about small-size behaviour: the lanterns become blobs below ~120px, the shrub canopies are a
single amorphous cloud path, the door's panel lines are drawn at 0.24 ink opacity so at card size the
door reduces to a plain yellow rectangle, and the three step slabs have no side faces so the base
reads flat. Raise the panel opacity to ~0.35 and give the top step a 4px side face and this holds
beside board 03-01 without apology.

**2 · `saved` — survives, and it is the only piece of constructed 3-space in the set.** A door swung
open at an angle, the leaf's outer face catching the light, a pale-blue interior, and a marigold
bookmark tilted -11° with its own shadow ellipse. The tilt and the swing are real drawing decisions.
Two faults: the leaf has no edge thickness, so it reads as a flat card rather than a slab; and the
bookmark's shadow ellipse sits at a *different height* from the door's own base shadow, so the
drawing has two ground planes. Give the leaf a 4px edge and put both shadows on one line.

**3 · `thanks` — survives, with one placement fix.** Door plus a tilted note card with a purple check
disc. The fault is that the door has a shadow ellipse and the note card has none, so one object is on
the ground and the other is floating; and the purple check disc is placed exactly on the door/card
overlap, so it belongs to neither object. Move the check onto the note card's top-left corner where
it clearly belongs, and give the card a small shadow.

**4 · `offline` — survives as a reduction, but it is not a new drawing.** It is `door` with the
lanterns and shrubs removed and a dashed cloud added. Two faults: the cloud's dash pattern (9 6) is
at a much coarser scale than any other dashed stroke in the system, and the three small "signal"
dashes beneath it become specks at the 104px size it is actually used at. Rendered at 104px in the
states card, the cloud also overlaps the door's cornice in a way that doesn't read as depth.

**5 · `camera` — would not survive.** The body is fine: rounded rect, viewfinder bump, a marigold
flash tab, a sky-blue detail window, a good white highlight arc at the top-left of the lens. The lens
is the problem, and it is the focal point. It is built from four concentric circles plus **six radial
spokes drawn through the centre**. Aperture blades are angled chords; radii through the centre make a
hubcap or a pinwheel. The result reads as a toy camera in a product where the camera is the primary
verb. Board 03-01's camera has concentric rings and a blue glass dot and no spokes. Replace the six
radii with five or six angled chords set off-centre, or delete them and keep the rings.

**6 · `street` — would not survive, and the reason is exactly the "implied rather than constructed
perspective" the author named.** The diagnosis:

- **The ground plane is in one-point perspective and everything standing on it is in flat elevation.**
  The pavement is a trapezoid (`M14 134h252l14 28H0z`) splaying toward the viewer. Every building,
  every shopfront, every window and every door is drawn orthographically with zero vanishing lines,
  no side planes, no receding sills. The two systems meet at the storefront base and contradict each
  other — which is what makes the buildings read as a flat sticker propped on a perspective floor.
- **The three pavement joint lines don't share a vanishing point.** `M60 134l-6 28` leans left,
  `M124 134l-2 28` is nearly vertical, `M198 134l5 28` leans right. They imply a VP that nothing else
  in the drawing agrees with. They were eyeballed, not projected.
- **The crosswalk stripes run parallel to the picture plane** at a constant length and spacing, on a
  ground plane that is splaying. If the pavement recedes, the stripes must too.
- **The awning is the only crafted element and it sits alone.** Its scalloped valance is built from
  `q` curves with three shading strokes — genuinely nice — surrounded by nothing but axis-aligned
  rectangles. So the drawing's one moment of craft looks pasted on.
- **The figure is drawn in a different medium.** A 4.6r head, a 6px torso stroke, 4.6px legs and a
  3.4px arm gesture, all with round caps at 0.6 opacity — a chunky, capped mark in a scene of thin
  outlines on light fills. It has no feet, no ground-contact shadow, and it is roughly the height of
  the shop's door opening — except the shopfront has no door opening.
- **In a product called EntryMap, the street scene contains no entrance.** The marigold — the accent
  reserved in every other drawing for the door — is spent on the awning. The board's street scene
  spends it on a doorway, which is why the board's version reads as *about* something.
- **Both trees are amputated at the frame** with no compositional reason, and they are the same
  four-lobe blob used in the `map` drawing, so the two weakest illustrations share their weakest mark.

**Change:** either commit to flat elevation (make the pavement a horizontal band and drop the joint
lines), or commit to perspective and build the shopfront with a receding side plane, a sill line
converging on one VP, and stripes that foreshorten. Then move the marigold from the awning to a door,
give the figure the scene's line weight, and re-draw the trees with a trunk that forks.

**7 · `map` — would not survive as a member of this set, and it also mis-sells the product.** Two
separate failures:

- **Style.** It is the only drawing with no white fill, no purple-ink outline, no lavender disc and
  no marigold. It is blue-on-blue with white street strokes. Set beside `door` or `saved` it does not
  read as the same hand; it reads as a stock map thumbnail. Its one good instinct is the -11°
  rotation, which gives it life. Two of its six tree blobs sit on top of white street strokes —
  trees in the roadway.
- **It is a promise the app doesn't keep.** `ob-location` shows this cool blue rotated map as "your
  map", and the real map — cream, lavender, sage, orthogonal — looks nothing like it. The published-
  scan screen proves the point: its mini-map is the app's *actual* ground and it is immediately more
  convincing. Replacing `map` with a small crop of the real map ground would fix both faults at once.

**On "one hand":** five of the seven are one hand, and it is a good hand. But three of those five are
the *same door* with different props (`door`, `offline`, `thanks`), so the family has less range than
it appears to. The remaining two (`street`, `map`) are a second and third hand. Add the welcome
skyline — flat fills, no outline at all — and the app ships four drawing styles.

---

## 4. The welcome screen's aubergine: does the departure earn itself?

**Verdict: the decision is right and the execution does not yet pay for it. Keep the aubergine; spend
the space better.**

The screen is measured at 418.5px of aubergine hero (49.6%) over 425.5px of white card (50.4%).

**What the departure genuinely earns:**
- **Brand continuity.** The splash, the welcome hero, the map's app bar, the capture screen and the
  nav bar are all `#17103D`. Opening on the logo's own field establishes the app's chrome colour
  before the user meets any chrome. The board's light welcome could not do that.
- **A real dark→light handoff.** The white card rising into the aubergine makes the product feel like
  it is *opening*, which is the right emotional note for "access starts before you arrive."
- **It solves a status-bar problem.** On aubergine the white status glyphs are correct; on the
  board's light ground they would need a second treatment.

**What it fails to earn:**
- **Half the first screen carries one logo, one four-word eyebrow, and wallpaper.** The skyline is
  the app's only flat-fill drawing, has no doorway, has randomly placed windows, and is inset 26px
  from both edges so the city floats with hard vertical edges. Board 01-01 spent the equivalent area
  on an illustration that showed the *subject*: a street with a highlighted yellow door. The build
  traded a subject for a mood and did not get enough mood back.
- **The mark is shown three times in five seconds.** The splash stacks the pin mark above a
  horizontal lockup that contains a second pin; then the welcome shows the lockup again.
- **The lockup isn't locked.** In the welcome lockup the pin's tip falls well below the wordmark's
  baseline and the pin is roughly twice the wordmark's cap height. In the app bar's lockup the
  proportion is different again. One of the two is wrong; neither matches the approved logo's own
  stacked proportion.
- **The tier tiles are the right idea in the wrong voice.** Teaching the evidence ladder on screen one
  is a genuine improvement on the board, which taught it nowhere. But as three small passive tiles
  below the headline and below the purple Sign in button, they are read *last* and read as ornament.
  Measured, all three tiles are 110×86.3 with labels starting at y 602 — but "Estimated" is one line
  (13.1px tall) and the other two are two lines (26.3px), so the row's optical bottom is ragged even
  though the boxes align.
- **The headline fills its measure.** The H1 spans x 28.9 → 361.1 inside a 390px card. It is text set
  to fit, not set to read, and the sub-head below it drops "needs." alone onto a second line.

**The one change that would make the departure earn itself:** replace the skyline with the `street`
drawing re-tinted for the dark ground, full-bleed, cropped so the shopfront row meets the card's top
edge, with **one lit yellow doorway**. A dark ground's single greatest capability is making one warm
light source read, and the product's subject is a lit doorway you can get into. Then break the
headline across two lines to a ~280px measure, and lift the tier tiles above the buttons so they are
read second rather than last.

---

## 5. Where the eye goes first, screen by screen (the ones that are wrong)

| Screen | Eye goes to | Should go to |
|---|---|---|
| `ob-welcome` | The purple Sign in button | The headline, then the illustration's door |
| `screen-map` | The amber pin heap (an accident of overlap) | The owner-confirmed pin / the user's position |
| `sheet-card` full | The two colour photographs | Freshness |
| `screen-profile` | The full-width purple "Sign in to save" | "My Needs" (the returning user's own state) |
| `screen-map` list view | The purple feature run-on at the bottom of each row | The business name and its tier pin |
| `scan-capture` | The empty white shutter and the nav FAB, competing | The viewfinder and its coach chip |
| Estimated card | Nothing wins; four marigold surfaces fight | The single re-check CTA |
| `claim-find` at rest | The empty two-thirds of the screen | The search field, then results |

---

## 6. Polish — worth doing, but not before showing it

- **`ow-edit`: "Yes" and "No" are the same purple.** The row's answer therefore carries no glance
  value. Board 06-02 differentiated affirmative from "Not sure". Give "No"/"Not sure" the neutral ink.
- **`ow-edit`: the select chevron sits ~40px right of its value.** They should touch so the pair reads
  as one control; right now the chevron looks like a stray triangle at the card edge.
- **`ow-edit`: the Texas record row uses a generic document glyph.** The library ships a `texas-record`
  mark (restated in brand colours). It is the only piece of local provenance in the whole system and
  it has been swapped for a receipt icon.
- **`screen-profile`: the "My scans" icon tile is cream-and-amber in a column of eight lavender
  tiles.** Tier colour has escaped into a navigation list where the semantic doesn't apply, and it
  pulls the eye to a row that isn't the most important one.
- **`screen-profile`: the "MY NEEDS" card holds one row and a trailing divider with nothing under
  it.** A hairline that separates a row from empty space.
- **`screen-profile`: the tax-credit note is purple, unboxed, and two lines**, so it is louder than
  the card heading's own supporting copy. Board 05-01 put it in a tinted sub-panel in dark navy.
  `claim-confirm` sets the equivalent note in quiet grey — two treatments for one kind of note.
- **`screen-states`: card 1 is bordered and tinted; cards 2 and 3 are plain white.** The difference
  reads as an accident, not a hierarchy, and there is no reason the offline state should be featured.
- **`screen-states`: card 1's text is top-aligned against a taller illustration**, leaving a ~70px
  hole under the copy before the purple paragraph.
- **`screen-states` and the list view: purple is doing paragraph duty.** Purple is the link and primary
  colour; using it for three-line body blocks means the least skimmable text is the loudest.
- **`scan-capture`: two near-identical marigold-ringed circles are stacked 370px apart** — the shutter
  (empty white) and the nav FAB (with the camera glyph). The one with the camera icon is the tab; the
  empty one is the action. Put the glyph in the shutter and let the FAB step back on this screen.
- **`scan-capture`: the viewfinder is a floating rounded card with 60px side margins.** Board 03-02's
  viewfinder is full-bleed. Floating it makes it look like a preview thumbnail rather than a camera,
  and the close × is half-clipped by its rounded corner.
- **`scan-capture` / `scan-review`: the camera-denied fallback contains a text overflow.** "SOLIDCORE
  DOWNT…" — an ellipsis inside an illustration, on the screen whose caption reads "This is exactly
  what neighbors will see." Set the sign to a short name that fits, or scale the type to the plate.
- **`scan-primer`: the decorative camera disc looks exactly like the app's most clickable control**
  (white disc + marigold ring) and it amputates the illustration's steps. Board 03-01 drew the camera
  *into* the scene. Either draw it in, or move it clear of the drawing.
- **`scan-primer`: four text blocks under one headline** — grey subhead, three amber-bulleted items,
  a bold purple line, a small grey paragraph — in four colours and three sizes. The board had a
  subhead and one lock line. Nothing here is clearly the point. Also: marigold bullets spend a
  semantic colour on decoration.
- **`scan-done`: the legend wraps 2 + 1** ("Estimated | Scanned on-site" then "Owner-confirmed" alone,
  centred). Lay it as a 3-column grid so it holds at 390.
- **`scan-done`: the success check is dark brown on cream.** Every other confirmation in the system
  uses the purple `check-outline`. And the announcement line is purple, two lines, and mixes a per-
  place fact with a global stat across a middot.
- **`screen-corr-done`: four different bolding patterns in four consecutive lines** — mid-sentence,
  lead-clause, mid-sentence, quoted string. The block looks speckled. Pick one pattern.
- **`screen-corr-done`: the four bullet glyphs are 12px and align to the x-height, not the cap
  height**, and they are four unrelated icons used as bullets on a screen that already has a strong
  illustration. Drop them or align them.
- **`sheet-correct`: "Send suggestion" is a half-width purple blob at the left with "Cancel" as a text
  link far to the right**, leaving a large hole between. Board 04-02 stacked them full-width. Either
  stack them or give the pair equal widths.
- **Filters sheet: chips hug their content**, so every row has a hole at the right and "Stroller" sits
  alone on row 3. Board 02-02 used an equal-width 2-column grid. Also the sheet has both a grip and an
  ×, with ~50px of dead space between them and the title.
- **`ow-published` and `ow-overview`: the header pairs a pin that already carries a check badge with a
  second, larger standalone check circle.** This is board-faithful (06-01, 06-04) but it was a weak
  detail on the board too: two checks of different sizes and stroke weights reading as two unrelated
  stickers. On `ow-overview` the pin is amber and the check is purple, which makes it worse.
- **`ow-published`: the provenance card has an unaligned right column.** Row 1 has nothing at the
  right, row 2 has "2 of 3 ●●○" floating against a four-line block, row 3 has "Read-only" against a
  three-line block. Three rows, three vertical positions, no column.
- **`ow-photos`: "Replace" is a purple link and "Remove" is body-black**, sitting adjacent as a pair
  of actions. And the three thumbnails are three different heights because they preserve aspect,
  so the left column is ragged.
- **`ow-photos`: the "face may be visible" warning is purple** — the link colour — on a purple-bordered
  card. Board 06-03 used an amber ⚠ for exactly this. The one row that needs attention doesn't differ
  in hue from a link.
- **`ob-location`: 200px of void** between the body copy and the buttons, and a tiny "YOUR LOCATION"
  eyebrow floating 90px below the back button with nothing attached to it.
- **`claim-find` at rest: two-thirds of the screen is empty**, and its "Continue" sits at the *top*
  under the helper line while every other screen's primary sits at the bottom.
- **Header chrome is inconsistent across the app**: circle-back + centred title (claim, owner),
  circle-back + eyebrow + H1 (`ob-location`, `ob-needs`), floating × with no bar (`scan-primer`),
  full dark app bar (`screen-map`). Four header patterns across 26 screens.
- **`screen-notif` is the only settings list with no icon column**, so its rows start at the card edge
  while Profile's start 76px in. Sibling screens, different left rhythm.
- **`screen-contrib` rows carry four colours each** — purple confidence dots, amber tier badge, blue
  privacy line, grey meta — with no separators. Three rows, twelve coloured elements, no colour
  meaning the same thing twice within a row.
- **The system aphorisms are everywhere.** "Freshness describes time, never the place. Trust pins only
  upgrade." / "Pins only move up…" / "You edit what you observe…" — each is well written, and there
  is one at the bottom of nearly every screen in the same 11.7px grey. As a set they read as the
  designer explaining the system to the user, repeatedly. Keep three; delete the rest.
- **The map legend sits top-left over the densest part of the map**, clipping street labels and the
  pin field, and it cannot be dismissed. Board 02-01 put it bottom-left in dead space.
- **"My needs" is a filled primary-purple pill on the map**, next to "Filters" in white. A filter
  toggle is wearing the app's primary-action weight, and it pulls the eye to the bottom-left corner.
- **The scan FAB's outer glow** bleeds onto the map, onto `scan-review`'s Publish button, onto
  `screen-corr-done`'s secondary button and onto `ow-overview`'s closing paragraph. On the boards the
  scan tab is a marigold ring on the dark bar with no glow; the glow here reads as an unread badge.

---

## 7. Finished product, or good prototype?

**This is a very good prototype with several screens that are finished-product work, and it is not yet
a finished product.** The gap is narrower than it usually is at this stage, and it is specific.

What is already at product quality: the trust ladder as a visual system; the My Needs sheet; the
Review-changes diff screen; the Accessibility screen with its self-demonstrating control and live
preview; the Freshness/Confidence pair; the owner Entrance-features card; the search and list views;
and five of the seven illustrations. If those were the only screens shown, no one would call this a
prototype.

What separates it from finished, concretely, is four things and not a hundred:

1. **Two visible rendering faults.** The selected pin painting on top of sheets, and demo scaffolding
   in shipped strings. Neither is a design decision; both are the kind of thing a viewer uses to
   decide how much of the rest to trust.
2. **Components that don't hold their shape across screens.** The tier badge has five treatments; the
   feature chips have three layouts; the Freshness/Confidence pair has two container treatments; body
   text has six sizes for one role; headers have four patterns. Every one of those is right somewhere
   and wrong somewhere else, which means the system exists and hasn't been enforced. That is the
   single largest difference between this and the boards — the boards are internally consistent
   because they were drawn once; the build is inconsistent because it was assembled in passes.
3. **The home screen doesn't yet show what the boards promised.** The map ground is better than the
   board's, and 52 identical rings bury it. The one screen a user spends the most time on is the one
   where the least restraint was applied.
4. **The first impression is the weakest drawing in the build.** The aubergine is a good decision
   carrying a flat, doorless skyline that belongs to no illustration family. Everything else about
   the welcome screen is competent; the thing occupying half of it is not.

Fix §2.1 through §2.6 and this stops looking like a prototype in about a day. Fix §2.7 through §2.11
and the app starts looking like it was designed by one person rather than assembled by several. The
illustrations in §3 and the welcome in §4 are the difference between "this is finished" and "someone
cared about this."
