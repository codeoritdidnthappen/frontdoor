# Bundled fonts

The design layer asks for four faces by PostScript name. `UIAppFonts` in `ios/project.yml`
registers them by file name, and `EntryMapTypography.Face` names both — a pytest guard
(`tests/test_ios_design_system.py`) fails if the two lists ever stop matching.

Drop these four files here:

| File | Family | Weight | Used for |
|---|---|---:|---|
| `AtkinsonHyperlegibleNext-Regular.ttf` | Atkinson Hyperlegible Next | 400 | body and callout |
| `AtkinsonHyperlegibleNext-SemiBold.ttf` | Atkinson Hyperlegible Next | 600 | labels, buttons, captions |
| `AtkinsonHyperlegibleNext-Bold.ttf` | Atkinson Hyperlegible Next | 700 | headings and the display step |
| `NunitoSans-ExtraBold.ttf` | Nunito Sans | 800 | the wordmark, when it is set in type rather than drawn |

Both families are under the SIL Open Font License. Atkinson Hyperlegible Next is published by the
Braille Institute; Nunito Sans is on Google Fonts. Take the static instances, not the variable
files — `Font.custom(_:size:relativeTo:)` addresses a single named instance, and a variable font
registered here resolves to its default weight for every face.

**The files are not committed.** They are third-party binaries with their own licence text, and
the repository has no vendored-binary convention to hang them on; that call belongs to whoever
owns the licence question, not to this change.

## Until they are here

`Font.custom` falls back to the system face **silently** when a PostScript name does not resolve.
So an app built without these files renders in San Francisco at the right sizes, weights, leading
and tracking, and nothing in the log says otherwise. That is deliberate — a missing font should not
be a crash — but it does mean "the type looks like iOS" is the symptom to watch for, and the first
thing to check on a Mac is that these four files are here and that their PostScript names match
`EntryMapTypography.Face`. Confirm each with:

```
fc-scan --format "%{postscriptname}\n" AtkinsonHyperlegibleNext-Regular.ttf
```

or by opening the file in Font Book and reading the PostScript name field.

The token file names the family as "Atkinson Hyperlegible" — the first release. The faces above are
Atkinson Hyperlegible **Next**, its successor, which is what the native app was asked for. If the
two ever have to be told apart in copy, the token file is the one that is behind.
