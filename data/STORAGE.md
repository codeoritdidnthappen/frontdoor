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
| `frontdoor-image` | loader, server, harness | capture upload |
| `frontdoor-depth` | harness only | capture upload |

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

Two tokens, never one:

1. **Loader / server** — Object Read (and Write, for upload) on
   `frontdoor-image` only. This is `FRONTDOOR_IMAGES_*`.
2. **Harness** — Object Read on both buckets. This is the images token
   plus `FRONTDOOR_DEPTH_*`.

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
python -m frontdoor.storage verify
```

That command must print `loader-denied-on-depth`. Run it again from the
evaluation host once #50 exists. The denial is the requirement; if verify
succeeds without it, the depth token leaked onto the loader credential.
