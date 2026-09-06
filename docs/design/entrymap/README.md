# The EntryMap design system, in this repository

Everything in this directory is a copy of the **approved asset library** — the signed-off design
package for EntryMap. It is copied in rather than referenced, so the repository is self-contained
and a build never depends on a path outside it.

Nothing here is edited. When the library issues a new version, this directory is replaced wholesale
and `tests/test_ios_design_system.py` says which Swift constants have to move with it.

## What is here

| File | What it fixes |
|---|---|
| `design-tokens.json` | The eleven official colours, the two typefaces, the three weights, the radius and spacing scales |
| `variables.css` | The same colours and families, as the web build consumes them |
| `interaction-motion.json` | Named durations, easings, control metrics, sheet stops, reduced-motion rules |
| `pin-hierarchy.json` | Pin size per tier per context, render order, overlay rules |
| `contrast-report.md` | The approved colour pairings and their WCAG 2 ratios |
| `interaction-motion-spec.md` | Control states, screen transitions, the live scan, Reduce Motion |
| `svg/` | The masters for the pins, halos, badges, feature icons, UI icons and provenance marks |

## How the native app uses it

`ios/FrontdoorCapture/UI/DesignSystem/` is the Swift port. It restates these values in Swift
because an iOS app cannot read JSON at layout time, and `tests/test_ios_design_system.py` reads
both sides on every pull request so the restatement cannot drift: colours, pin sizes, durations,
easings, sheet stops and every icon's path geometry are compared against the files above.

Where the port had to decide something the library does not state — a subdued-ink role, a keyline
colour, an elevation ladder, a type scale — the Swift says so at the point of the decision, with
what it was derived from. Those comments are the record; there is no second document to keep in
step with them.

## The brand mark

`docs/brand/entrymap-approved-logo.png` is the approved artwork, and
`ios/FrontdoorCapture/Resources/Assets.xcassets/EntryMapLogo.imageset/` holds it at 1x/2x/3x for a
128 pt lockup.

Do **not** use `svg/brand/mark-primary.svg` or its PNG exports. That file is a degraded
reproduction: it omits the white disc behind the doorway and strokes the middle of the three arcs
in `#5B35F5`, the same violet as the pin it sits on, so it renders one visible arc where the logo
has three. It is kept out of this directory for that reason.
