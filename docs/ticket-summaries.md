# Ticket summaries

## #18 / TICK-010 — Capture sidecar schema and validator

PR: [#97](https://github.com/codeoritdidnthappen/frontdoor/pull/97)

Defined the JSON shape of the per-capture sidecar (ARCHITECTURE.md §4) as a JSON
Schema, plus a validator function that rejects a record missing any required
field, an invalid enum, or an unknown key.

**Files created**
- `src/frontdoor/capture_sidecar.schema.json` — the schema
- `src/frontdoor/sidecar.py` — `validate_sidecar()`
- `tests/test_sidecar_schema.py` — 31 tests
- `pyproject.toml`, `src/frontdoor/__init__.py`, `.gitignore` — packaging scaffolding

**Input:** one sidecar record (dict/JSON object) — capture, entrance and device
IDs, image/depth file info with hashes, intrinsics, gravity, card placement,
optional ROI, caliper ground truth, capture conditions, split.

**Output:** nothing on success; raises `jsonschema.ValidationError` naming the
offending field on failure.

## #19 / TICK-011 — Split seed and deterministic assignment tool

PR: [#98](https://github.com/codeoritdidnthappen/frontdoor/pull/98)

Committed a fixed seed and a tool that assigns each entrance to `dev`, `calib`
or `sealed` from a hash of its ID and the seed alone — deterministic, so any
team member or third party gets the same split without a lookup table.

**Files created**
- `src/frontdoor/split_seed.json` — the committed seed
- `src/frontdoor/split.py` — `assign_split()` + CLI (`python -m frontdoor.split`)
- `tests/test_split.py` — 7 tests
- `CHANGES.log` — entry recording the seed commit SHA
- `pyproject.toml`, `src/frontdoor/__init__.py`, `.gitignore` — same packaging scaffolding as #18

**Input:** an entrance ID string (e.g. `"E-014"`), as a CLI argument, a line on
stdin, or a Python call to `assign_split(entrance_id)`.

**Output:** one of `"dev"`, `"calib"`, `"sealed"` — printed as `entrance_id,split`
by the CLI, returned as a string by the function.

## #15 / TICK-003 — Roster, devices and work division

PR: [#100](https://github.com/codeoritdidnthappen/frontdoor/pull/100)

Recorded who is on the team, what capture hardware existed, and the assignment
rule that replaced self-assign-and-rotate. Closed O-1. A-1 and A-3 were
falsified at the time: two capture phones, one with LiDAR.

**Files created / updated**
- `TEAM.md` — roster, devices, work division, R-8 response rule
- `ARCHITECTURE.md` — A-1 / A-3 restated
- `CHANGES.log` — D-027 (tickets are assigned)

**Input:** facts about the four people and their devices.
**Output:** every open issue has an owner; field capture serialises onto James's
iPhone 16 Pro.

**Superseded 2026-09-04:** D-040 makes James's iPhone 17 Pro (`iPhone18,1`)
with LiDAR the sole capture, test, and demo phone.

## #17 / TICK-005 — Run tests on every pull request

PR: [#128](https://github.com/codeoritdidnthappen/frontdoor/pull/128)

GitHub Actions workflow that installs the dev extra and runs pytest on every
PR to `main`. A temporary red commit proved the workflow fails when tests fail,
then was reverted.

**Files created**
- `.github/workflows/tests.yml`
- `requirements-dev.txt` — `pip install -e ".[dev]"` so a broken extra fails CI

**Input:** a pull request targeting `main`.
**Output:** a `pytest` check that must be green before merge.

## #21 / TICK-013 — Append-only capture manifest

PR: [#129](https://github.com/codeoritdidnthappen/frontdoor/pull/129)

Committed `data/manifest.csv` as the sealed record of what was captured. One
row per capture, appended never edited. Hashes are SHA-256 of file bytes;
`split` must match the assignment tool.

**Files created**
- `data/manifest.csv` — header only
- `src/frontdoor/manifest.py` — `append_capture()`, `manifest_sha256()`
- `tests/test_manifest.py`
- `.gitattributes` — `eol=lf` so the digest is stable across machines

**Input:** capture id, entrance id, paths to image / depth / sidecar files.
**Output:** one CSV row, or `ManifestError` if the append would rewrite history,
disagree with the seed, or land on a truncated last line.

## #48 / TICK-060 — Stub POST /measure with the frozen response contract

PR: [#103](https://github.com/codeoritdidnthappen/frontdoor/pull/103)

Froze the HTTP contract before the metrology library exists, so rendering and
the real endpoint can share one schema. Stub returns placeholder rises flagged
`"stub": true`. Invalid sidecars return 400.

**Files created**
- `src/frontdoor_server/app.py` — Flask `POST /measure`, `GET /health`
- `src/frontdoor_server/measure_response.schema.json`
- `tests/test_measure_endpoint.py`

**Input:** multipart image + sidecar.
**Output:** JSON with per-arm rise, interval and pass/fail/abstain per ADA line.

## #84 / TICK-201 — QA: split determinism across devices

Closed without a PR. The Python tool side is covered by TICK-011 tests; the
cross-phone check needed the capture app (#29) and was refiled as [#109](https://github.com/codeoritdidnthappen/frontdoor/issues/109).
That follow-up was later closed; D-040 now retires cross-phone verification
because James's iPhone 17 Pro is the sole capture, test, and demo phone.

**Input:** the same list of entrance IDs on every team device and the Python CLI.
**Output:** identical `dev` / `calib` / `sealed` assignments, no UI to override.

## #87 / TICK-204 — QA: sidecar schema, manifest and hash verification

Closed without a PR. Schema and manifest exist (#18, #21) but the loader
(#22) does not, so the adversarial hash checks were refiled as [#104](https://github.com/codeoritdidnthappen/frontdoor/issues/104).

**Input:** real captures plus deliberately corrupted image / sidecar / manifest.
**Output:** loader raises, naming the capture, with no flag that disables hashing.

## #94 / TICK-211 — QA: server and demo rendering on James's iPhone 17 Pro

Closed without a PR. Depends on the real `/measure` implementation, deploy, and
in-app rendering (#49–#51), none of which had landed.

**Input:** real captures on James's iPhone 17 Pro against the deployed server.
**Output:** server bytes match the library; abstain renders; network failure
does not drop the local capture.

## #101 / TICK-214 — Constrain sidecar SHA-256 fields to 64 hex characters

PR: [#117](https://github.com/codeoritdidnthappen/frontdoor/pull/117)

Sidecar `image_sha256` / `depth_sha256` / `sidecar_sha256` must be exactly 64
lowercase hex characters. A trailing newline or extra junk is rejected.

**Files updated**
- `src/frontdoor/capture_sidecar.schema.json` — `pattern` on hash fields
- `tests/test_sidecar_schema.py`

**Input:** a sidecar record.
**Output:** validation error if a hash field is not 64 lowercase hex chars.

## #102 / TICK-215 — Enforce captured_at as a real RFC 3339 timestamp

PR: [#121](https://github.com/codeoritdidnthappen/frontdoor/pull/121)

`captured_at` is a UTC RFC 3339 timestamp, not an arbitrary string. The
pattern is anchored so a trailing newline is rejected.

**Files updated**
- `src/frontdoor/capture_sidecar.schema.json`
- `tests/test_sidecar_schema.py`

**Input:** a sidecar `captured_at` value.
**Output:** accept `2026-08-30T14:22:31Z`; reject a trailing newline or a
non-timestamp.

## #105 / TICK-217 — Canonical entrance ID form

PR: [#118](https://github.com/codeoritdidnthappen/frontdoor/pull/118)

One spelling per entrance: `E-` plus exactly three digits. Case and surrounding
whitespace are canonicalised; everything else is rejected, so a mistype cannot
silently land an entrance in a different split.

**Files updated**
- `src/frontdoor/split.py` — `canonical_entrance_id()`
- sidecar `entrance_id` pattern
- `CHANGES.log` — the form decision
- `tests/test_split.py`

**Input:** an entrance ID string (argv, stdin, or Python).
**Output:** `E-014`, or `InvalidEntranceId`.

## #106 / TICK-218 — CLI argv and stdin assign the same split

PR: [#119](https://github.com/codeoritdidnthappen/frontdoor/pull/119)

`python -m frontdoor.split E-014` and the same ID on stdin now hash the same
canonical form. Previously argv and stdin could disagree.

**Files updated**
- `src/frontdoor/split.py`
- `tests/test_split.py`

**Input:** entrance IDs as CLI arguments or stdin lines.
**Output:** identical `entrance_id,split` lines either way.

## #107 / TICK-219 — Remove the public seed override from assign_split

PR: [#120](https://github.com/codeoritdidnthappen/frontdoor/pull/120)

`assign_split` can only hash against the committed seed. A test-only helper
keeps the override off the public API so AC-6 cannot be bypassed.

**Files updated**
- `src/frontdoor/split.py` — `_assign_split_with_seed` is test-only
- `tests/test_split.py`

**Input:** an entrance ID.
**Output:** the split for the committed seed; `TypeError` if a caller passes
`seed=`.

## #108 / TICK-220 — Stop ignoring SEAL_AUDIT.log

PR: [#127](https://github.com/codeoritdidnthappen/frontdoor/pull/127)

The seal audit log matched the boilerplate `*.log` gitignore rule and would
never have been committed. A negation rule and a test pin the artefacts
ARCHITECTURE.md requires to stay trackable.

**Files updated**
- `.gitignore` — `!SEAL_AUDIT.log` (CHANGES.log already had a negation)
- `tests/test_gitignore.py`

**Input:** the paths named in ARCHITECTURE.md §7–§8.
**Output:** `git check-ignore` returns not-ignored for each of them.

## #110 / TICK-222 — Abstentions must be explainable

PR: [#122](https://github.com/codeoritdidnthappen/frontdoor/pull/122)

The `/measure` response contract can now carry an abstain explanation and can
express an absent arm. Abstain is a decision with a reason, not a missing
measurement.

**Files updated**
- `src/frontdoor_server/measure_response.schema.json`
- `tests/test_measure_endpoint.py`

**Input:** a measurement response, including abstain.
**Output:** schema accepts an explanation on abstain and omits a cut arm;
rejects a silent abstain.

## #111 / TICK-223 — Reject inverted intervals and impossible rises

PR: [#122](https://github.com/codeoritdidnthappen/frontdoor/pull/122)

The response schema no longer accepts an interval whose low > high, or a rise
no threshold would produce.

**Files updated**
- `src/frontdoor_server/measure_response.schema.json`
- `tests/test_measure_endpoint.py`

**Input:** a `/measure` JSON body.
**Output:** validation error on inverted intervals or impossible rises.

## #114 / TICK-226 — Vendor the QA agent

PR: [#123](https://github.com/codeoritdidnthappen/frontdoor/pull/123)

Copied the QA agent skill into `.claude/skills/qa-agent` so verification runs
from this repo rather than a machine-local skill path.

**Files created**
- `.claude/skills/qa-agent/` — `SKILL.md`, `QA_WORKFLOW.md`, `agent.py`

**Input:** none (vendored skill).
**Output:** the QA workflow is in the repo.

## #115 / TICK-227 — Vendor the ticket agent

PR: [#124](https://github.com/codeoritdidnthappen/frontdoor/pull/124)

Same for the ticket agent: the backlog conventions live in-tree.

**Files created**
- `.claude/skills/ticket-agent/` — `SKILL.md`, `TICKET_WORKFLOW.md`, `agent.py`

**Input:** none (vendored skill).
**Output:** ticket format and workflow are in the repo.

## #125 / TICK-228 — Anchor sidecar SHA-256 so a trailing newline is rejected

PR: [#126](https://github.com/codeoritdidnthappen/frontdoor/pull/126)

JSON Schema `$` matches before a trailing newline under Python's `re.search`.
Hash patterns now use `(?![\s\S])` so `"abc…\\n"` is rejected, matching the
fix later applied to `captured_at` and `entrance_id`.

**Files updated**
- `src/frontdoor/capture_sidecar.schema.json`
- `tests/test_sidecar_schema.py`

**Input:** a sidecar hash field with a trailing newline.
**Output:** `jsonschema.ValidationError`.

## #20 / TICK-012 — Object storage with a quarantined depth prefix

PR: [#140](https://github.com/codeoritdidnthappen/frontdoor/pull/140)

Named Cloudflare R2 as the free-tier provider (10 GB, two buckets because
tokens scope per bucket) and shipped the S3 client the loader and harness
will use. Images and depth never share a credential. Live buckets are created
in the Cloudflare dashboard; `python -m frontdoor.storage_probe verify` is the
check that the loader token is denied on depth.

**Files created / updated**
- `src/frontdoor/storage.py` — `image_store()`
- `src/frontdoor/depth_access.py` — `depth_store()` *(moved by TICK-057: reading depth is a
  separate import, so the quarantine can be tested)*
- `src/frontdoor/storage_probe.py` — `verify` *(moved by TICK-057: it reads depth)*
- `tests/test_storage.py`
- `data/STORAGE.md` — layout, who may read what, how to create the buckets
- `.env.example` — the two credential sets; no secrets
- `CHANGES.log` — provider decision
- `ARCHITECTURE.md` §9 — two buckets, not a prefix
- `pyproject.toml` — `boto3`; `moto` in the dev extra

**Input:** environment variables for two S3-compatible buckets; `verify` takes
no arguments.
**Output:** image put/get succeeds with the loader credential; the same
credential is denied on the depth bucket (`StorageDenied`).
