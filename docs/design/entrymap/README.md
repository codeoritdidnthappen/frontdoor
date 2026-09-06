# The EntryMap design system, in this repository

Everything in this directory is a copy of the **approved asset library** — the signed-off design
package for EntryMap. It is copied in rather than referenced, so the repository is self-contained
and a build never depends on a path outside it.

Nothing here is edited. When the library issues a new version, this directory is replaced wholesale
and `tests/test_ios_design_system.py` says which Swift constants have to move with it.

## Which version this is

**Library version `2026-09-05`** — the build-ready handoff package. Every file below was taken from
that package's own token files and verified against the SHA-256 in its package manifest before it
was copied in, rather than transcribed from any table describing it.

### What it replaces

It supersedes the library this directory previously held. **Ten of the eleven colours moved**;
only white did not. It also adds a twelfth, `lavenderPath`, which is a role the retired library did
not have at all.

| Token | Retired value | Current value |
|---|---|---|
| `indigo900` | `#17103D` | `#1E1142` |
| `indigo800` | `#211054` | `#28165A` |
| `violet600` | `#5B35F5` | `#4F34DB` |
| `violet800` | `#4020B5` | `#38239B` |
| `sky400` | `#69B7FF` | `#76BCFD` |
| `sky700` | `#1266A6` | `#1B6599` |
| `marigold400` | `#FFBF24` | `#FDB327` |
| `amber700` | `#9A5700` | `#8C5400` |
| `lavender100` | `#F2EEFF` | `#F5F2FC` |
| `lavender200` | `#E2DAFF` | `#E8E1F7` |
| `lavenderPath` | — (did not exist) | `#CFBCEE` |
| `white` | `#FFFFFF` | `#FFFFFF` (unmoved) |

Two other things changed with it. Every contrast ratio moved, and the report now sets a **7:1 floor
for body copy**; the pairing that previously sat at 6.42:1 — white on the logo violet — is 7.38:1
against the current violet and clears it. And the library no longer names a wordmark family,
because the wordmark is approved artwork that is never set as live text.

`lavenderPath` is the sampled entrance path, and it is **not** a UI surface. The web build spent one
lavender family on both jobs and every screen came out with a purple cast; the separation is the
fix, so nothing that paints a surface may reach for it.

## What is here

| File | What it fixes |
|---|---|
| `design-tokens.json` | The twelve official colours, the UI typeface, the three weights, the radius and spacing scales |
| `variables.css` | The same colours and family, as the web build consumes them |
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

Do **not** use `svg/brand/mark-primary.svg` or its PNG exports. That file was a degraded
reproduction: it omitted the white disc behind the doorway and stroked the middle of the three arcs
in the same violet as the pin it sat on, so it rendered one visible arc where the logo has three.
It was kept out of this directory for that reason. The current library ships no vector or
recoloured brand variants at all — only the approved raster artwork — so the warning now stands
against reintroducing one, and `tests/test_ios_design_system.py` enforces it.
