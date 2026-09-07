# Bundled fonts

The four faces `EntryMapTypography.Face` asks for, by PostScript name. `UIAppFonts` in
`ios/project.yml` registers them by file name; the two lists and the PostScript names inside the
files are checked against each other by `tests/test_ios_design_system.py`.

| File | PostScript name | Family | Weight | Used for |
|---|---|---|---:|---|
| `AtkinsonHyperlegibleNext-Regular.ttf` | `AtkinsonHyperlegibleNext-Regular` | Atkinson Hyperlegible Next | 400 | body and callout |
| `AtkinsonHyperlegibleNext-SemiBold.ttf` | `AtkinsonHyperlegibleNext-SemiBold` | Atkinson Hyperlegible Next | 600 | labels, buttons, captions |
| `AtkinsonHyperlegibleNext-Bold.ttf` | `AtkinsonHyperlegibleNext-Bold` | Atkinson Hyperlegible Next | 700 | headings and the display step |
| `NunitoSans-ExtraBold.ttf` | `NunitoSans-ExtraBold` | Nunito Sans | 800 | the wordmark, when set in type rather than drawn |

Static instances, not variable files. `Font.custom(_:size:relativeTo:)` addresses a single named
instance, so a variable font registered here resolves to its default weight for every face — all
four steps would render identically and nothing would say so.

## Licences

Both families are under the SIL Open Font License, which permits bundling in an application and
requires the licence to travel with the font. `OFL-AtkinsonHyperlegibleNext.txt` and
`OFL-NunitoSans.txt` are here for that reason and are checked by the suite.

Atkinson Hyperlegible Next is published by the Braille Institute; Nunito Sans by Google Fonts.

## Provenance

Taken from the upstream repositories rather than a font site, so the bytes are traceable:

| File | Source |
|---|---|
| Atkinson faces | `googlefonts/atkinson-hyperlegible-next`, `fonts/ttf/` |
| `NunitoSans-ExtraBold.ttf` | `googlefonts/NunitoSans`, `fonts/ttf/` |

Google Fonts ships both families **variable-only**, which is why these come from upstream: the
static instances the bundle needs are not in `google/fonts`.

## What this fixed

Until these files were added the directory held only this README, and the app rendered in San
Francisco at the scale's sizes, weights, leading and tracking — silently, because `Font.custom`
falls back without a word. The guard that was supposed to catch it compared the `.ttf` names Swift
asks for against the `UIAppFonts` list, two lists that were both satisfied by files nobody had
added. `test_every_face_the_layer_names_is_present_and_resolvable` now reads the PostScript name
out of each file, which is the name that actually decides.

The web app is served the same two families from `src/frontdoor_server/fonts`, self-hosted for the
same reason: it used to fetch them from `fonts.googleapis.com` and degraded to `system-ui` on any
network that was slow or filtered.

## Checking a face by hand

```
fc-scan --format "%{postscriptname}\n" AtkinsonHyperlegibleNext-Regular.ttf
```

or open it in Font Book and read the PostScript name field.

The token file names the family as "Atkinson Hyperlegible", the first release. These are Atkinson
Hyperlegible **Next**, its successor, which is what the native app asks for. If the two ever have
to be told apart in copy, the token file is the one that is behind.
