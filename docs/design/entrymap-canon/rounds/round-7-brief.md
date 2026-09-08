# Round 7 brief: close the ledger's nowhere list

Assembled from `design/directive-log.md`, the directive ledger's second pass. Its "nowhere" list
is things the owner asked for that no brief, no rubric line, no ticket and no running agent
covers. Round 7 closes the ones that are design's to close.

Two of the eight were fixed before this brief was written — the skills now ask at decision points,
and the specialist agents now exist as definitions rather than as hand-written briefs. The rest
follow.

---

## 1. Rebuild the map ground from the map kit, not by hand

**This is the most important item and it is a correction to my own instruction.**

Round 6 was briefed to rebuild the ground from a colour table I sampled off a board, because that
brief was written **before** the handoff package existed. The package ships
`map-kit/svg/base-map.svg` and its siblings as real layers, using the canonical tokens: land
`#F5F2FC`, blocks `#E8E1F7`, and the rest.

So Round 6 is re-deriving by hand what already exists as artwork. **This surface has now been
aimed at a reasoned target instead of the real one three times.** Take the kit.

Use the kit's layers directly: base map, blocks, street labels, pin placement, empty area, before
and after profile, selected business, mixed cluster, and its safe-area and pin-anchor guidance.
Where the kit and the build disagree, the kit wins. Where the kit is silent, say so rather than
inventing.

Re-measure every pin against the kit's ground, modal and worst tone, in both contrast modes. A
near-white ground raises the floor for the estimated pin's outline, which is the only marker with
no halo behind it.

## 2. Adopt the canonical palette from the package

All six colours the build currently uses are superseded. Take them from
`asset-library/tokens/variables.css` and verify against the package manifest — **do not
transcribe them from any table, including one in this brief.**

Adopt the added steps as named roles rather than deriving them inline: the second indigo and
violet, the sky and amber for light surfaces.

**Make `lavender-path` a distinct role from the two UI lavenders**, and score it. Their
conflation *is* the "everything reads purple" defect, and today it exists in the briefs only as
an explanation, so the next palette change can silently re-merge them.

## 3. Score the floors the package sets, rather than noting them

The package's accessibility checklist specifies **48px targets** and a **7:1 body-contrast
floor**. The rubric still measures targets against 44 and treats 7:1 as an observation. Prose
does not get scored; move both into criteria and re-measure everything against them.

## 4. Screen-by-screen parity against the package's own exports

The package ships `screen-exports/` — 25 individual screens cropped from the approved boards,
each with a crop manifest. Board parity has so far been judged by eye against six composite
panels.

Score each build screen against its export. Where the build has a screen the package does not,
say so; where the package has one the build lacks, that is a gap worth naming rather than
silently accepting.

## 5. Fold the directive log into the rubric

`design/directive-log.md` section 3 holds seven criteria already drafted in the rubric's format
and voice: 3.9, 3.10, 6.8, 7.13, 7.14, 9.11, and an amendment to 3.1 and 3.8. Paste them in and
score them. They were left unscored deliberately, because recording intent and judging
implementation are different jobs.

## 6. Resolve which asset library is canonical

Rubric lines 3.1 and 3.8 cite the earlier `entrymap-assets/` as their strongest colour evidence.
That library is superseded, and its brand mark is the defective one. Re-cite against
`entrymap-build-ready/asset-library/` and say in the evidence that the earlier one is superseded,
so nobody re-adopts it later.

## 7. Record the hybrid decision in the design canon

The native and web boundary lives only in a GitHub ticket. Nothing under `design/` mentions it,
so a reader of the design canon cannot tell which surfaces are being designed for what. Add it to
`visual-language.md`, briefly, pointing at the ticket for detail.

---

## Then re-run the specialists, which is the other half of the job

The agents now exist as definitions: `qa-adversary`, `a11y-auditor`, `interaction-conformance`,
`design-critic`, `incentives-analyst`. Each has run **once**, against a build that has changed
several times since.

Re-run QA, accessibility and interaction conformance against Round 7's actual result. Do not
accept the round's own report as evidence: two of five spot-checked claims from earlier rounds
were materially false and both erred toward success.
