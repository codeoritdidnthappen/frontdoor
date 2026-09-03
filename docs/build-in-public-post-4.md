# Post 4 — what pre-registration cost us

Ticket: TICK-113 ([#79](https://github.com/codeoritdidnthappen/frontdoor/issues/79))

Status: ready to publish. Publication URLs and engagement counts belong in
[`build-in-public-tracker.md`](build-in-public-tracker.md) only after the posts exist.

## Thread

### 1

> Pre-registration did its job on Frontdoor—even though our original experiment didn't. We committed to test whether a single photo could measure an entrance threshold within 0.25" MAE. Then we chose not to collect the caliper ground truth needed to test it. 🧵

### 2

> The tempting move would be to swap in an easier metric, score whichever model looked best, or call our new photo-screening study a substitute. We did none of those. The measurement hypothesis is untested—not failed, not passed, and not quietly rewritten.

### 3

> We also cut our no-reference-object Arm C. Not because data showed it was weak: the decision gate arrived before implementation and measurements existed. That is a schedule result, not a model result, and we're reporting it that way.

### 4

> Pre-registration cost us the tidy ending we wanted. It bought something more important: a visible line between what we planned, what changed, and what the evidence can actually support. Frontdoor is now testing plain-photo feature screening as a separate study.

## Publication notes

- Publish the four posts as one thread from David's `@codehappened` account.
- Attach no ablation chart: no measurement-arm results exist, so a chart would be illustrative
  rather than evidence.
- Do not quote sealed-split results; this thread uses none.
- After publication, record the thread URL and engagement count in
  [`build-in-public-tracker.md`](build-in-public-tracker.md). The four-account posting and evidence
  cadence remain tracked by [#215](https://github.com/codeoritdidnthappen/frontdoor/issues/215).

## Fact check

- `PRD.md` §2 records the original 0.25-inch MAE criterion and says it is untested after the
  decision not to collect caliper ground truth.
- `CHANGES.log` D-030 records that Arm C was cut without measured dev-split error; the decision was
  caused by the lapsed schedule gate, not model evidence.
- `CHANGES.log` A-3 records plain-photo feature screening as the product and keeps the metrology
  study separate.
- `CHANGES.log` D-036 records that no caliper ground truth is collected in this window.
