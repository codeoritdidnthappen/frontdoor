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
| **`prototype.html`** | **The reference build.** 26 screens, every state, nine rounds of work, self-contained — open it in a browser, no server needed. When a document and this file disagree about what something looks like, this file is what was measured. Start here. |
| `design-systems-spec.md` | The scales: type, spacing, elevation, motion, with a mapping from every value the build used before them. What to implement against when building a screen from scratch. |
| `ui-reference-spec.md` | Screen-by-screen reference for the surfaces the prototype covers. |
| `graphic-critique.md` | A designer's judgement against the targets, as distinct from conformance. Where the build reads unfinished and why. |
| `incentives-audit.md` | Who benefits from misrepresenting this product, and how its rules can be gamed. The angle no design or code review covers. |
| `galleries/` | Options drawn and measured before a choice was made, kept because the reasoning is in them. `estimated-mark-4-chosen.html` holds the mark that shipped, with its contrast measured on every ground tone in both contrast modes. `tagline.html` records why colour is unavailable on the welcome headline. `pins-and-icons.html`, `map-ground.html`, `map-hierarchy.html`, `map-ui-directions.html`, `map-ui-hybrids.html` and `illustrations.html` are the earlier rounds' options — the pin set, four map grounds measured against the approved board, the size and halo hierarchy, and the drawn illustrations. |
| `rounds/` | The briefs for rounds 5 through 9 — what each round was asked to do, and the constraints it had to hold. Useful when a decision looks arbitrary. |
| `history/` | The audits from before round 7, kept because a fixed defect is evidence about what breaks here. The `-r7` files supersede them; these say what the build was like before. |

## If you are implementing a screen

Open `prototype.html` in a browser and drive the screen you are building. It is the only
artefact where the states, the transitions, the empty cases and the accessible names all
exist together. Then read `design-systems-spec.md` for the scales and `visual-language.md`
for the rules below.

A note for the native app specifically: the prototype is a web build, so its layout is a
reference for hierarchy, spacing rhythm, state coverage and copy — not a pixel target to
match. Where SwiftUI's own idiom disagrees with a web layout, the idiom wins and the
tokens stay.

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
