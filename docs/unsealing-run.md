# Freeze-day unsealing run (TICK-080, #63)

Results freeze on **2026-09-07**. The sealed split is opened **once**, by a command already
exercised on the dev split (TICK-079, R-5). This is that command and the checklist around it.
It is not a rehearsal: typing `--include-sealed` *is* the run.

The study being scored is screening, not the arms. There is no per-arm MAE, no angle model, and
no `config/abstention.yaml` to freeze. Those belonged to the measurement study A-3 / D-036
removed; they are not missing pre-flight items.

## The command

Dry run (dev; already the TICK-079 command):

```
python -m frontdoor.screening_eval --manifest data/manifest.csv \
    --labels data/labels.csv --out reports/dry-run
```

Freeze day (sealed; only `--include-sealed` and `--out` change):

```
python -m frontdoor.screening_eval --manifest data/manifest.csv \
    --labels data/labels.csv --out reports/sealed --include-sealed
```

Type it in a real terminal. An import, a notebook, or `main(..., from_cli=False)` is refused
and writes nothing.

`--out reports/sealed` is load-bearing: the sealed report must not overwrite the dry-run
report, which is the evidence the command was exercised beforehand.

## Pre-flight — confirm, do not assume

Stop if any item fails. None of these opens the seal.

1. **Working tree is clean.** `git status --porcelain` is empty. A dirty tree aborts before
   any sealed byte is read; the recorded commit SHA would not describe the code that ran.
2. **This checkout is `main`, pulled.** The audit line names `HEAD`. Uncommitted runbook
   edits, leftover branches, and a stale `origin/main` are all the wrong SHA.
3. **`data/labels.csv` exists.** Operator presence labels completed under #302 with the workflow
   built by #168. Without it the runner
   cannot score. Do not invent labels, and do not look at sealed per-entrance results
   before this run.
4. **`data/dataset-closeout.json` is current.** The runner refuses a stale closeout (manifest
   hash drift) before images are read. Regenerating is `python -m frontdoor.dataset_closeout`
   if the committed file is behind the manifest; if the hashes already match, leave it.
5. **API key is present.** `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` in the environment
   or `.env`. A keyless start prints the missing-key message and touches nothing.
6. **Storage config resolves.** The audit line records the image bucket and endpoint, never
   credentials. `.env` is gitignored, so a clean tree alone does not mean two runs read the
   same bytes.
7. **Spend cap.** The eval runner uses `EVAL_MAX_USD_PER_RUN` ($20), not the live `/screen`
   default ($1). 76 eligible sealed captures at $0.05/image is $3.80; the $1 default would
   abort after the audit line. Do not lower the cap on the morning.
8. **Operator name.** `SEAL_AUDIT.log`'s operator column is `getpass.getuser()`, not
   `git config user.name`. On this machine that is the OS login. There is no flag to
   override it. If a different string must appear in the log, that change lands in
   `seal_audit._operator` before freeze day, on a committed tree — not that morning.

## If it refuses before unsealing

Dirty tree, stale closeout, missing key, or `--include-sealed` from an import: fix the
named problem and start again. Nothing sealed has been read; `SEAL_AUDIT.log` is unchanged.
That is still one run, not a second one.

## If it crashes after unsealing

The audit line is written **before** the first sealed image. A crash, a spend-cap abort, or
a killed process after that point has already opened the seal.

- Commit and push `SEAL_AUDIT.log` the same day anyway.
- Do **not** type `--include-sealed` again to "check something".
- A recovery run is a **second unsealing**. Disclose it in `CHANGES.log`, in the findings,
  and in the deck. #63's "no second run" criterion is then failed honestly, not patched.

The runner already prints this on a spend-cap abort. The same rule applies to any other
failure past the audit line.

## After a clean exit

The report is `reports/sealed/screening_eval.json` and `reports/sealed/screening_eval.md`.
It must contain, from the sealed split: per-criterion accuracy against operator labels, the
not-visible rate, and the entrance-level call.

Commit the same day, on the tree that ran:

- `SEAL_AUDIT.log` — exactly one new line: timestamp, commit SHA, manifest SHA-256, the
  full command, operator, resolved bucket/endpoint
- `reports/sealed/screening_eval.json` and `reports/sealed/screening_eval.md`
- `CHANGES.log` — the result as stated, whichever way it goes, and this sentence:

  > The pre-registered rise criterion (MAE ≤ 0.25″ on the sealed split) is **untested**,
  > not relaxed (A-3, D-036).

Push the same day. Anything noticed in the sealed data afterwards is exploratory, never
confirmatory.

## Out of scope here

- Tuning, re-fitting, or picking a variant after seeing the numbers.
- Presenting a post-hoc sealed finding as confirmatory.
- Changing the pre-registered success criterion. Amendments are logged as amendments.
- Practicing `--include-sealed` on any earlier day.
