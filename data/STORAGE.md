# Capture object storage

TICK-012 / D-018 / D-020 / D-026.

Bytes live here; records live in git (`data/manifest.csv`). The core
metrology library has no credential and performs no I/O of its own.

## Provider

**Cloudflare R2**, S3-compatible, free tier:

| | |
|---|---|
| Storage allowance | 10 GB / month |
| Projected volume | 2–5 GB (40–60 entrances × 3–4 angles × 2 distances) |
| Headroom | comfortable against 10 GB; 5 GB would be marginal |
| Egress | free |
| Billing | free-tier ceiling **only if no payment method is attached**. Do not add a card. |
| Region | Buckets live in `WNAM` (Western North America), confirmed via `get_bucket_location`. Not to be confused with `FRONTDOOR_S3_REGION`, which is `auto` — that is the S3 API's region parameter, which R2 expects, and says nothing about bucket location. The evaluation host region is still open (#50). |

R2 API tokens are scoped **per bucket**, not per prefix. Two buckets is
therefore the D-020 layout, not a prefix inside one bucket.

## Buckets

| Bucket | Who may read | Who may write |
|---|---|---|
| `frontdoor-image` | loader, server, harness | server, on behalf of capture upload |
| `frontdoor-depth` | **harness only** | server, on behalf of capture upload (**write-only token**, D-033) |

Capture uploads go **through the server** (TICK-029, #33), not straight from the phone: no R2
credential ships inside the app. The server holds read+write on `frontdoor-image` and
**write-only** on `frontdoor-depth`, so it can store a depth map and can never read one back.

Both buckets are private. Do not enable public access.

Object key is `<partition>/<capture_id>`, where the partition is `open/`
or `sealed/` (D-007, #182). The partition is in the key so that this layer can
refuse a sealed read without consulting the manifest — see **What the seal
covers** below. Build keys with `frontdoor.storage.storage_key()`; a key with
no partition prefix is refused rather than assumed open.

Sidecars are not stored here —
they are committed at `data/sidecars/<capture_id>.json`, next to the
manifest, and hashed in `sidecar_sha256`. The dataset loader (TICK-014)
verifies image and sidecar hashes on every read.

## What the seal covers

`ObjectStore.get` refuses any key under `sealed/` unless the caller passes
`allow_sealed=True`, which only the audited `python -m frontdoor.eval
--include-sealed` run does. Writes are not refused — capture upload has to be
able to store sealed captures.

**This is a code-level refusal, not a provider-level one.** Anyone holding the
images token can still reach sealed bytes with a raw `boto3` client, because R2
scopes API tokens per bucket and not per prefix (D-026), so no token policy can
express "this credential may not read `sealed/`". Closing that would need a
third bucket, and it is not closed today.

So the guarantee is: **no code path in this repository reaches a sealed capture
without writing a `SEAL_AUDIT.log` line first.** It is not: sealed bytes are
unreachable. Someone who sets out to bypass it can. The seal is an integrity
mechanism for honest use, backed by an audit trail — which is what D-007 needs
it to be, but it is worth stating in the words that are actually true.

## Credentials

Three tokens, never one (D-020, D-033):

1. **Loader / server** — Object Read and Write on `frontdoor-image` only.
   This is `FRONTDOOR_IMAGES_*`.
2. **Server, depth ingest** — Object **Write only** on `frontdoor-depth`.
   No read, no list. This is `FRONTDOOR_DEPTH_WRITE_*`, and it is the only
   depth credential the server ever gets (D-033). A write-only token cannot
   be used to peek or to tune, which is the guarantee D-020 actually makes.
3. **Harness** — Object Read on both buckets. This is the images token
   plus `FRONTDOOR_DEPTH_*`. The harness is the only reader of depth.

**Reading depth means importing `frontdoor.depth_access`** (TICK-057). That module exists so the
question "who can read depth" has an answer you can check: while `depth_store()` sat beside
`image_store()`, every module that imported `frontdoor.storage` for an image carried a route to
depth, and nothing could tell the two apart. `tests/test_depth_quarantine.py` walks the real import
graph and fails the build if the metrology library, the dataset loader or the server ever reaches
it. The credential probe lives in `frontdoor.storage_probe` for the same reason — it reads depth,
so it cannot live in the module the server imports.

That is the second of the two barriers D-020 asks for. The first is the credential itself: the
loader's token is denied on the depth bucket by the provider, which `verify` proves.

The core metrology library gets neither. Copy `.env.example` to `.env`
and fill in the values; `.env` is gitignored and is read automatically by
`frontdoor.storage` (real environment variables take precedence, so CI and `export` still
work). Nothing else needs doing.

## Create the buckets

In the Cloudflare dashboard (R2):

1. Create buckets `frontdoor-image` and `frontdoor-depth` in WNAM.
2. Create an API token with Object Read & Write on `frontdoor-image` only.
3. Create a second API token with Object Read & Write on `frontdoor-depth` only.
4. Put the account endpoint (`https://<accountid>.r2.cloudflarestorage.com`)
   and both tokens in `.env`.
5. From a team laptop:

```
python -m frontdoor.storage_probe verify
```

That command must print `loader-denied-on-depth`. Run it again from the
evaluation host once #50 exists. The denial is the requirement; if verify
succeeds without it, the depth token leaked onto the loader credential.

## Deleting an object

`ObjectStore.delete(key)` classifies the key and nothing else. It will delete a `sealed/`
object as readily as an open one, and that is deliberate (#187). A refusal in `delete()`
stops our own code; it does not stop a console click, an SDK script holding the images
token, or a token that outlives the sprint — which is most of the ways the sealed split
actually gets lost. The control has to sit at the provider, so `delete()` stays as it is.

**R2 has no object versioning.** `PutBucketVersioning` and `GetBucketVersioning` are on
R2's unimplemented list and there is no `ListObjectVersions`, so a delete here is final and
there is nothing to restore from. #187 asked for versioning; it cannot be had. What R2 does
have is a **bucket lock**: a rule that refuses deletes *and* overwrites under a key prefix,
for a period or indefinitely, applying to objects already stored as well as new ones. That
makes losing a sealed object impossible rather than recoverable, which is what D-007 needs
— the sealed split is opened once, on 2026-09-07, and there is no second attempt.

Stated as plainly as **What the seal covers**: whoever holds the Cloudflare login can
remove the rule and then delete. A lock stops the stray click and the stale token, not
someone who means it.

## Lock the sealed partition

Applied 2026-09-03 on both buckets — see the recorded result below. In the Cloudflare dashboard (R2), for **both**
buckets:

1. Open the bucket → **Settings** → **Bucket lock rules** → **Add rule**.
2. Name `lock-sealed-indefinite`, prefix `sealed/`, retention indefinite. **Save changes**.

Or with wrangler, if you have it and a Cloudflare login. Cloudflare documents the add
command only as `wrangler r2 bucket lock add <BUCKET_NAME> [OPTIONS]` and does not spell the
options out, so check `npx wrangler r2 bucket lock add --help` before running it rather than
trusting the flag names here — the dashboard steps above are the reliable path:

```
npx wrangler r2 bucket lock add --help          # confirm the flags first
npx wrangler r2 bucket lock list frontdoor-image
npx wrangler r2 bucket lock list frontdoor-depth
```

`wrangler r2 bucket lock set <BUCKET_NAME> --file <FILE_PATH>` takes the whole rule set as
JSON and is the documented alternative if the flags prove awkward.

Bucket locks are a Cloudflare API, not part of the S3 surface `frontdoor.storage` speaks,
so this is dashboard or wrangler — `python -m frontdoor.storage` cannot set one.

**The prefix is `sealed/`, not empty.** A bucket-wide rule breaks `python -m
frontdoor.storage_probe verify`: it writes `open/_frontdoor_probe` and deletes it on every run,
so under a bucket-wide lock the cleanup fails silently the first time and the overwrite
fails loudly the second. That trades the D-020 and D-033 denials for a probe key nobody
needs kept.

Then confirm it, on a throwaway key **under the locked prefix** — a rule proven on some
other prefix is not the rule that matters. There is no restore, so the check is not
delete-then-restore but delete-then-still-there, and the delete's return is not the answer;
the read-back is:

```
python
>>> from frontdoor.storage import image_store
>>> s = image_store()
>>> k = "sealed/_frontdoor_lock_probe"
>>> s.put(k, b"lock probe")
>>> s.delete(k)                     # may raise, may return quietly — neither is proof
>>> s.get(k, allow_sealed=True)     # b'lock probe' means the lock held
```

`allow_sealed=True` because `get` refuses a `sealed/` key otherwise; storage writes no
audit line, that is `eval`'s job. Repeat with `from frontdoor.depth_access import depth_store`
if you hold the harness token -- the depth reader lives there, not in `frontdoor.storage`
(TICK-057). The probe object is then undeletable for as long as the rule stands — that is the
proof, and it costs ten bytes.

**Applied and verified, 2026-09-03 (#187).** Rule `lock-sealed-indefinite`, prefix
`sealed/`, retention indefinite, on `frontdoor-image` and `frontdoor-depth` both. Created
through the dashboard; the buckets are on our own Cloudflare account.

The delete-then-still-there check, run against the locked prefix on each bucket:

```
=== frontdoor-image ===
  put    sealed/_frontdoor_lock_probe  -> ok
  delete -> refused: ObjectLockedByBucketPolicy
  get    -> b'lock probe'   ==> LOCK HELD

=== frontdoor-depth ===
  put    sealed/_frontdoor_lock_probe  -> ok
  delete -> refused: ObjectLockedByBucketPolicy
  get    -> b'lock probe'   ==> LOCK HELD
```

R2 refused the delete loudly rather than returning quietly, which is more than the check
required -- the read-back is what proves it, and the refusal only makes it legible. Both
probe objects are now permanently undeletable and stay where they are: that is the standing
evidence the rule is on, and it costs twenty bytes.

**Against the free tier.** A lock rule stores no bytes and costs no operations, and a
locked object is billed as ordinary storage against the same 10 GB in **Provider** above
(R2 bills GB-month — peak stored bytes per day, averaged over the month). With no
versioning there are no versions to accumulate, which was the free-tier worry in #187. The
real one is the other direction: locked bytes cannot be deleted, so you cannot delete your
way back under 10 GB. Projected volume is 2–5 GB and only the sealed partition is locked,
so the headroom holds, but for `sealed/` it is now one-way. **Still no payment method** —
D-026 requires that billing be incapable of starting silently, and for object storage that
is still the absence of a card (D-031 moved the *server* to a paid host and left storage on
the free tier by name). A lock rule does not need one; if something asks for a card or a
plan upgrade, stop.
