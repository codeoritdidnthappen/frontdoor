# Evidence boxes — pointing at the evidence without judging it

TICK-467 (#467). What `frontdoor.evidence_boxes` produces, where the geometry
lives, what a box is allowed to mean, what it costs, and the measurement that
chose how it is drawn.

## What this is

A verdict about a doorway answers *what*. This answers the next question, which
is *where*. Tapping "Handrails" on an evidence receipt draws a rectangle over
the photograph the detector found a handrail in.

It is the same detector that was measured as a **scorer** and dropped. Cropping
to detected door and handle regions and re-asking the model went 94.2% → 86.5%
on held-out photographs: zero fixes, four new errors, three of them a real
handle called *absent* because **no handle box was found** — the model read a
missing box as evidence of absence rather than abstaining. A coverage gate cut
four errors to one and the arm was still net negative. That evaluation's own
recorded conclusion was to keep box receipts as a diagnostic and not as a
scoring path. This is that diagnostic.

## The rule

> **A missing box is not an absent feature.**

It is not a slogan; it is the difference between the thing that failed and the
thing that ships. Three mechanisms hold it, none of them a comment:

1. **The detector cannot see a verdict.** `locate_evidence(frames, *, detector)`
   takes image bytes. There is no parameter a verdict can arrive through and no
   return value one can be read out of, and
   `tests/test_evidence_boxes_do_not_judge.py` reads the module's syntax tree
   and fails if it ever evaluates a name that reaches `frontdoor.screening`,
   `frontdoor.scan_records`, or the word *verdict* or *confidence*.
2. **A criterion with nothing found is absent from the mapping.** Not `null`,
   not `false`, not an empty box, not a zero score — there is no shape for "we
   looked and there is nothing there", because that shape is the bug.
3. **The interface says the sentence out loud.** When there is no box, the
   receipt prints *"we looked for this and couldn't point at it in these
   photos. That doesn't change the answer above"*, and the verdict beside it is
   the engine's, unedited. A reader shown a bare photograph would take it as a
   denial, so the interface never lets the photograph do the talking.

### Why a per-entrance flag and not a per-criterion `null`

"No box for handrails" has two readings a person at a door would hear very
differently: *we looked here and could not point at one*, and *nobody looked*.
The mapping alone says neither.

The flag that separates them is per **entrance** — `evidence_boxes_searched` on
the scan record — because every criterion is looked for on every entrance, so
one boolean carries the whole truth about the search. A per-criterion
"searched and empty" value would be precisely the shape that made this detector
worse than useless as a scorer, re-invented to say a sentence a flag already
says. The app gates the receipt's chips on that flag, so inside those chips
"we looked and couldn't point at it" is always true, and an entrance nobody ran
the detector on offers no chips and makes no claim at all.

Every criterion the receipt shows gets a chip, box or no box. Offering chips
only where a box exists would turn the row of chips itself into a verdict.

## When it runs

**Publish time only**, and opt-in even there:

```
python -m frontdoor.scan_publish --photos <root> --evidence-boxes
```

A live scan is already about nineteen seconds from shutter to verdict, which is
the product's worst measured number. Adding a minute of CPU to it would not be
a slower feature, it would be a different product. So the cost is confined
structurally rather than by intention, and
`tests/test_evidence_boxes_off_the_scan_path.py` pins three things: the publish
path calls it, neither request handler mentions it in any spelling, and a
process that has imported and built the server app has neither
`frontdoor.evidence_boxes` nor `torch` nor `transformers` in its module table.

`torch`, `transformers` and `pillow` are the `boxes` extra, imported lazily
inside the one function that needs them. A machine without them publishes
verdicts and no boxes, which is a supported outcome: the box is a courtesy, so
an entrance published without one is complete, not broken.

## Cost per published entrance

Measured on this repository's CPU (Windows, no GPU), running `locate_evidence`
over the twelve pilot entrances whose receipt photographs the app carries —
`google/owlvit-base-patch32`, two stored frames each, twelve queries per frame:

| | |
|---|---|
| model | `google/owlvit-base-patch32` (open weights, runs locally) |
| **API spend** | **$0.00 per entrance** — there is no model call to pay for |
| wall clock, 2 frames | **24.1 s** mean, 20.5 s min, 26.5 s max over 12 entrances |
| wall clock, per frame | **≈12 s** |
| projected, 5 views | **≈60 s** per entrance, the figure the ticket estimated |
| one-off | loading the detector, once per publish run, not per entrance |

The per-frame cost is roughly flat in the stored frame's size, because
`DETECT_MAX_SIDE` caps what the detector reads at 1024 on the long side and
OWL-ViT resizes to 768 internally regardless.

There is **no** API cost. The $0.0075 per door recorded against the dropped
scoring arm was its Claude re-ask on the crops; this module makes no such call
and never sees the model that answers verdicts.

Roughly a minute per entrance is fine in a batch nobody is waiting on and
unacceptable in a capture flow already at ~19 s shutter-to-verdict, which is
the entire reason for the placement above.

## Geometry

Boxes are in the pixel frame of the **stored** image bytes — the same frame
`blur_regions` reports in: privacy-processed, orientation applied, long side
capped at 2048 (TICK-453). Detection runs on a downscaled copy for speed and
every box is scaled back before it is returned, so no caller has to translate
between spaces and no geometry outlives the frame it was measured in.

Handing `locate_evidence` an original camera file rather than the stored bytes
draws the boxes in the wrong place, which is worse than drawing none. In
`scan_publish.assess_publishable` the stored frames are kept separately from
the reduced copies the model reads, for exactly that reason.

On screen the photograph is displayed through `object-fit:cover`, which scales
to fill and centre-crops the overflow. `placeEvidenceBox` inverts that fit from
the image element's own `naturalWidth`/`naturalHeight`, never from a number the
server sent, and redoes it on resize.

The record carries `{"frame", "x", "y", "w", "h", "label", "score"}` per
criterion, `frame` being the index into `image_keys` of the photograph the box
is on.

## Legibility, measured

A box drawn over a receipt photograph can land anywhere in the frame, and a
frontage photograph can be anything — white stucco in full sun, black glass at
dusk. A colour that looks right on one image is not an answer.

So every displayed pixel of all **335 photographs** in the pilot capture corpus
was swept through the exact `object-fit:cover` geometry the receipt uses, in
both of its layouts, at the sizes measured on the served page in a browser
(`.rcpt-shot` is 166×220 CSS px two-up and 339×220 one-up, at
devicePixelRatio 2). Reproduce with:

```
python docs/evidence-box-legibility.py --photos <capture corpus root>
```

The mark's cross-section is `photograph | halo | stroke | halo | photograph`,
so it is legible if **either** boundary is visible. Per displayed pixel the
sweep computes the halo against the photograph (outer), the stroke against the
halo (inner), and takes the larger. The threshold that applies to a mark rather
than to text is WCAG 2.1 SC 1.4.11 non-text contrast, 3:1; 4.5:1 is reported
beside it.

### Worst case over every displayed pixel

| layout | mark | photos <3:1 | photos <4.5:1 | naive stroke, no halo | photos <3:1 | photos <4.5:1 |
|---|---|---|---|---|---|---|
| two-up 166×220 | **4.65:1** | 0/335 | 0/335 | **1.00:1** | 335/335 | 335/335 |
| one-up 339×220 | **4.65:1** | 0/335 | 0/335 | **1.00:1** | 335/335 | 335/335 |

Per-photograph worst case ranges 4.65–4.88:1 with the halo and 1.00–1.06:1
without it.

### How much of a photograph is hostile to a bare stroke

A worst case is one pixel, so this is the share of displayed pixels under 3:1:

| layout | naive median | naive mean | naive max | with halo, max |
|---|---|---|---|---|
| two-up 166×220 | 38.4% | 38.3% | 55.8% | **0.0000%** |
| one-up 339×220 | 30.4% | 30.2% | 58.1% | **0.0000%** |

335 of 335 photographs have more than a tenth of their displayed pixels under
3:1 for a bare white stroke in the two-up layout; 303 of 335 have more than a
quarter. This is not a corner case, it is most of the corpus.

### Why the halo works, and it is not luck

The outer boundary — halo against photograph — **does** vanish: its worst case
is 1.00:1, on a pixel the colour of the halo's own ink. That is expected and it
is fine, because it is not the boundary carrying the mark.

The inner boundary has a **floor that does not depend on the photograph**. The
halo is indigo900 at 60%, so whatever is underneath contributes at most 40% of
it; the lightest halo that can exist is the one over pure white, and the stroke
is white. Sweeping every colour a pixel can be gives a minimum of **4.65:1 at
rgb(255,255,255)** — a constant, computable without a corpus, and the reason a
halo answers the arbitrary-photograph problem where a bare stroke cannot. The
corpus sweep agrees with it exactly, which is the check that the compositing
model matches what a browser does.

The construction is the doorway guide's own — a white mark inside an indigo900
halo at the same alpha — so the viewfinder and the receipt point at things the
same way.

## What is not here

**OCR.** The owner asked for it. Reading text is a different capability from
locating a feature, and our own measurement put RapidOCR at 66.7% precision and
34.6% recall for reading business names, which is not something to put on
screen. Accessibility signage is already one of the four criteria; if the box
lands on a sign, that is the answer.

**Anything that lets a box influence an assessment.** That was measured and it
made the product worse.

**Boxes on a pin or on the map.** Round 8's rule holds: this is an overlay on a
photograph and nothing else.

**Boxes on a pin published through `/map/data`.** Not a decision, a gap: a
published server pin's receipt carries no photograph today — the app only shows
photographs it has embedded, or the frame from the scan you just took — so a
box there would have nothing to draw on. Carrying receipt photographs onto
`/map/data` pins is separate work, and the record already holds the geometry
for when it lands.

## Coverage, and what is honestly unmeasured

The grounded-crops evaluation recorded a **door box on 26 of 26** pilot
entrances and a **handle box on 20 of 26**. Those two figures come from the
queries `"door"` and `"door handle"`, and only the second maps onto a criterion
here (`accessible_door_hardware`). The evaluation also ran `"ramp"`,
`"handrail"` and `"wheelchair symbol sign"`, but their coverage against ground
truth was never scored, so there is no published figure for the other three
criteria and this document does not invent one.

The display gate here is `MIN_SCORE = 0.10`, above the evaluation's own 0.08.
A scorer can weigh a weak box against other evidence; a pointer cannot — it is
drawn on a photograph with no hedge beside it, and a confident rectangle around
the wrong object costs more trust than an honest "we could not point at this
one".

## What the seeded demo actually shows, including the awkward case

The twelve seeded doors on the app page carry **real** detector output on the
exact photographs the receipt displays — the detector was run over those
`data:` URIs and its mapping written into the seed. Four of the twelve got a
box; eight say, chip by chip, that we looked and could not point at one. Nobody
made the numbers look better than they are, and the eight are not a defect:
they are the case the ticket exists for.

One of the four is the case worth demonstrating. On door-06 the finder returns
a `handrail` box at score 0.158 — around the diagonal brass tube that the
engine's own sentence, printed directly underneath, explains **is a door pull
and not a handrail**. The verdict beside it stays `absent`.

That is why the caption locates and never asserts: it says *"Handrails —
outlined in photo 1"*, not *"here it is"*. A caption that claimed the feature
would have the box contradicting the verdict on screen, which is the exact
failure this ticket was written to avoid. With locating language the same case
becomes the clearest thing on the receipt — *this is what we considered, and
this is why it was not enough* — and turns an abstention from a word into
something a person can look at.

Note also that the seeded frames are 360×480 receipt thumbnails, well under the
2048 a real publish works from, so this coverage is a floor rather than an
estimate of what the detector achieves on stored frames.

## Drawn size

A door handle really is small in a frontage photograph: one of the seeded boxes
is 13×17 stored pixels, about 6×8 CSS px once the receipt has cover-fitted a
360px-wide frame into a 166px column — and the mark itself is 14px thick
(5px halo, 2px stroke, each side). At that size a rectangle is not a rectangle.

So `placeEvidenceBox` grows a drawn box to a floor of 28 CSS px **about its own
centre**, and clamps it inside the photograph. It never shrinks one: a large
box is the detector's answer and is left alone. The pointer stays aimed where
the detector aimed it and becomes something an eye can land on.

The detector's own minimum, `MIN_BOX_FRACTION`, is a share of the frame's long
side rather than a pixel count, because "12 pixels" means two different things
on a 2048px frame and a 480px one — and on the smaller frame the old absolute
threshold silently discarded boxes that display *larger* than ones it kept on
the bigger.
