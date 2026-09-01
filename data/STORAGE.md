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
| Region | `WNAM` (Western North America). The evaluation host region is still open (#50); match it when that lands. |

R2 API tokens are scoped **per bucket**, not per prefix. Two buckets is
therefore the D-020 layout, not a prefix inside one bucket.

## Buckets

| Bucket | Who may read | Who may write |
|---|---|---|
| `frontdoor-image` | loader, server, harness | capture upload |
| `frontdoor-depth` | harness only | capture upload |

Both buckets are private. Do not enable public access.

Object key is the `capture_id` (no prefix). Sidecars are not stored here —
they are committed at `data/sidecars/<capture_id>.json`, next to the
manifest, and hashed in `sidecar_sha256`. The dataset loader (TICK-014)
verifies image and sidecar hashes on every read.

## Credentials

Two tokens, never one:

1. **Loader / server** — Object Read (and Write, for upload) on
   `frontdoor-image` only. This is `FRONTDOOR_IMAGES_*`.
2. **Harness** — Object Read on both buckets. This is the images token
   plus `FRONTDOOR_DEPTH_*`.

The core metrology library gets neither. Copy `.env.example` to `.env`
and fill in the values; `.env` is gitignored.

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
