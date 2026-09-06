# The EntryMap design canon

This is the design record for the product's interface: what it should look like, why,
what was measured, and what is still wrong. It is the source the phone prototype and the
served `/app` page are built against, and the native capture app's design system
implements the same tokens.

It lives here so the repository holds the design itself rather than only the code that
applies it. A reader who wants to know why a pin is the size it is, or why no verdict is
ever red, should be able to find the answer without asking anyone.

## What each file is

| File | What it holds |
|---|---|
| `design-rubric.md` | **The spec.** 72 criteria scored 0 to 4 with named evidence, plus the round-by-round history. This is the loop's memory: rounds are briefed from it, never from conversation. |
| `visual-language.md` | The settled rules. Palette meaning, map hierarchy, the trust ladder, what a pin may and may not encode, the native and web surface split. |
| `product-interaction-design.md` | Flows and states across the product. |
| `directive-log.md` | Every instruction the product owner gave, in their own words, with where it stands. Its point is the "nowhere" list: things asked for that nothing covers. |
| `a11y-audit-r7.md` | Accessibility, measured. Contrast tables, target sizes, focus order, screen-reader behaviour, reduced motion. |
| `interaction-audit-r7.md` | The build measured against the interaction and motion specification. Durations, pin geometry, sheet stops. |
| `qa-report-r7.md` | Adversarial functional QA, plus what rapid successive rounds broke. |
| `package-defects.md` | Verified defects in the supplied handoff package, for whoever maintains its generator. |

## The rules that are not negotiable

These are the ones a change is most likely to break by accident.

**No public verdict is negative.** An assessment reports what a photograph shows. It
never concludes that a person cannot enter a place. Map states are "Verified Accessible"
or "Not Yet Checked" and nothing else.

**`not_visible` is not `absent`.** They are different claims and the interface keeps them
apart everywhere, in text and in the accessible name.

**Colour never delivers a judgement about a business.** There is no red and no green in
the palette. Tier is carried by shape and fill; match by halo line style. A trust pin is
never recoloured for selection, match, freshness or provenance.

**One line style, one meaning.** A dashed stroke on the map means partial match. Nothing
else may use a dash to mean something different.

**Trust only ever goes up.** Estimated, then scanned on site, then owner confirmed. A
place is never downgraded, and trust is never a filter.

**Floors, from the handoff package:** 48px touch targets, 7:1 contrast for body text.

## How the loop works, if you need to change something

One writer holds the prototype per round; everything else is read-only and produces a
report. Rounds are briefed from the rubric. After each round the accessibility, QA and
interaction agents re-measure the actual result, because a round's own report has been
measured erring toward success. Nothing is asserted that could be counted.

The bar is: nothing below 3, average 3.5 or better. As of Round 8 the average is 3.819
across 72 criteria and one criterion sits at 2. That one needs an owner-confirmed
entrance to exist in the data, which no design round can produce.
