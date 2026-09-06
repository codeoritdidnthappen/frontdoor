# Defects found in the build-ready handoff package

Findings against `design/board-refs/entrymap-build-ready/`, each verified against the bytes
on disk rather than read off a report. For whoever maintains the package generator.

## 1. The map-kit manifest records one hash per variant, and it is the PNG's

`map-kit/map-kit-manifest.json` lists eight variants, each with an `svg` path, a `png` path and
a single `sha256`. Measured across all eight:

| Compared against | Matches |
|---|---|
| the variant's PNG bytes | 8 of 8 |
| the variant's SVG bytes | 0 of 8 |
| top-level `PACKAGE-MANIFEST.json` for the same 16 files | 16 of 16 |

So nothing is stale. The field is **ambiguous**: it names two files and hashes one. The cause
is in the tools. `handoff/tools/build-map-kit.mjs` writes the manifest, then
`handoff/tools/render-map-kit.ps1` (line 36) adds `sha256` per variant with `-Force` from the
rendered PNG. Any earlier SVG hash is overwritten and the SVG is left without one.

An earlier note in this repo (rubric line 3.9, Round 7) called this "a stale sha256 list". That
was a misreading of the same numbers and is corrected there.

**Fix in the generator:** emit `svgSha256` and `pngSha256` per variant, or a `files` map keyed
by path, and have the renderer add to it rather than replace. The top-level manifest is
already correct and can stay the verification source until then.

## 2. The library's Estimated pin outline fails the package's own checklist

`asset-library/svg/pins/estimated.svg` draws the outline in sky400 `#76BCFD`. Against the kit's
own land it measures 1.83:1, against its darkest filled tone 1.36:1, and against the pin's own
white fill 2.02:1. The package's accessibility checklist requires a discernible boundary at
3:1. The approved board draws that outline in a saturated dark blue (sampled `#0033F5` off
`screen-exports/png/map-default.png`, 5.86:1 on the land). The build follows the board and uses
sky700 `#1B6599`.

**Fix in the library:** re-export `estimated.svg` with the outline on sky700, which is already
in the canonical twelve.

## 3. The earlier package's brand mark is a degraded reproduction

`entrymap-assets/asset-library/svg/brand/mark-primary.svg` (the earlier, superseded package)
drops the white disc behind the doorway and draws the middle arc in the same violet as the
surface behind it, so the mark shows one colour where the approved logo shows three. Its
raster exports carry the same defect. The build crops the mark from the approved artwork
instead (`design/logo-mark.png`). Recorded in `visual-language.md` §17; listed here so the
build-ready package is checked for the same regression before anyone adopts its mark.
