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

## Then publish the sealed entrances to the map

The 18 sealed entrances are withheld from the public map for one reason only: assessing them
before the freeze would mean having seen their results, which is the contamination this whole
procedure exists to prevent. Once the run above has exited cleanly and its report is committed,
that reason is spent. The evidence was collected at the door like every other entrance, and
keeping it off the map after the freeze would understate what we know for no remaining benefit.

So this is not a separate initiative anyone has to remember. It is the last step of freeze day.

Sealed entrances, withheld until this point:

    E-002  E-005  E-006  E-011  E-014  E-015  E-016  E-021  E-028
    E-029  E-032  E-036  E-039  E-044  E-046  E-052  E-059  E-064

Run the same publication path #333 established for the other 46, with the sealed identifiers now
permitted, and open it as its own pull request so the moment is auditable. Order matters and is
not negotiable: **the evaluation report is committed first, then the entrances are published.**
Publishing before the report would leave the seal broken with nothing recording what it found.

The published records are ordinary Scanned on-site records. They carry their capture dates, they
pass through the same never-downgrade and Green-or-Gray gates, and nothing about them is marked
as having been sealed. The seal was a procedure for protecting an evaluation, never a property
of the doorway.

If the run above did **not** exit cleanly, publish nothing. An aborted unsealing leaves the
question of contamination open, and the map can wait for the answer.

## Out of scope here

- Tuning, re-fitting, or picking a variant after seeing the numbers.
- Presenting a post-hoc sealed finding as confirmatory.
- Changing the pre-registered success criterion. Amendments are logged as amendments.
- Practicing `--include-sealed` on any earlier day.

## Where the images come from (TICK-342, #342)

The run needs the capture photographs. There are two ways to give it them, and the choice is
made with one flag.

**From R2, the default.** Nothing to pass. This is the committed design — `data/STORAGE.md`:
*"Bytes live here; records live in git"* — and it is what #23's release artifact needs.

**From a local directory**, when the bytes are on the machine running the evaluation and not yet
in the bucket:

```sh
python -m frontdoor.screening_eval --manifest data/manifest.csv \
    --labels data/labels.csv --out <dir> --images /path/to/photographs
```

Each capture is located by **its own sidecar's `image.path`**, not by guessing at filenames, so
whatever layout the photographs are already in is the layout that works.

Three things hold either way:

- **The manifest still decides what the bytes must be.** Every capture is hashed and compared to
  `image_sha256`; a directory holding different pixels fails the run rather than quietly scoring
  something else.
- **The seal is enforced on both paths.** A sealed capture is refused unless the run is the
  audited `--include-sealed` one. This is not inherited from the storage layer — `DatasetLoader`
  hands an injected reader the bytes before `storage.get` is reached, so the local reader refuses
  sealed captures itself.
- **The pre-flight checks whatever source you chose**, before the audit line, and its refusal names
  that source. A missing file says the directory; a missing object says the bucket.

`--images` removes the upload from the evaluation's critical path. It does not replace it: the
dataset should still reach R2.
