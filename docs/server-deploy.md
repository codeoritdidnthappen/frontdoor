# Deploying the measure server (TICK-062, #50)

`POST /measure` and `GET /health` on Fly.io. One image, and **the same image runs on a laptop** —
that is what makes step 3 of D-016's fallback chain a fallback rather than a different system
demoed under pressure.

Host decision and its cost: **D-031** (CHANGES.log), which amends D-026 for the server host only.
Object storage stays on the R2 free tier.

## What runs

| | |
|---|---|
| Image | the repo's `Dockerfile`, unchanged — `python:3.11-slim`, Flask + gunicorn |
| Machine | `shared-cpu-1x`, 256 MB, `min_machines_running = 1` |
| Measured footprint | **69 MiB** serving `/health` under a 256 MB cap |
| Region | `sjc` — near the WNAM buckets |
| Arms served live | A and A′. B is `unavailable` (no depth model), C is `cut` (D-030) |
| Cost | ~$2/month. Cancel after the Showcase, 2026-09-11 |
| **Live URL** | **https://frontdoor-measure.fly.dev** |
| Deployed | 2026-09-02, machine `0803444b2dd568`, region `sjc` |

There are no model weights in the image and nothing is downloaded at start-up, so the laptop
fallback needs no network beyond the pull it already did.

## One-time setup

```
brew install flyctl
fly auth login                      # interactive, opens a browser
fly launch --no-deploy --copy-config --name frontdoor-measure
```

`--copy-config` uses the committed `fly.toml`. Say **no** to Postgres, Redis and any other add-on:
the server holds no state.

### Cap the spend before deploying — with the mechanism Fly actually has

D-026 requires that billing cannot start silently. On a paid plan that is no longer satisfied by
having no card. An earlier revision of this section instructed setting a "monthly spend limit" in
the Fly dashboard — **Fly.io documents no such setting**: there is no spend limit, cap, or budget
control on a Fly organisation. The closest real hard-stop is **prepaid credits**: buy a fixed
credit balance and do not attach usage billing beyond it — the account suspends when the balance
reaches zero, which is a hard stop, not an alert. Fly's billing alert emails exist but are
**advisory only**; they notify, they do not stop anything.

So the real procedure is:

1. Fly dashboard → the organisation → **Billing** → buy a small block of **prepaid credits**
   (5 USD is ample against a ~2 USD/month machine; the app is destroyed after the Showcase).
2. Enable the billing alert email as an early warning — understanding it is advisory, not a cap.
3. Record the credit purchase (amount and date) in this file, below.

**Prepaid credit balance:** _record amount and date when purchased._

~~**Spend limit set:** 2026-09-02, before the first deploy, with the billing alert enabled.~~
**Recorded in error** — Fly offers no spend-limit setting, so this line cannot have described a
real control; it is struck rather than deleted so the record stays honest.

> **D-031's stated mechanism needs amending — owed to its author (see PR #200 review F1).**
> D-031 says D-026's no-silent-billing clause is "replaced by an explicit spend limit on the Fly
> organisation plus a billing alert". No such limit exists; the entry should be amended to name
> prepaid credits (hard stop at zero balance) as the mechanism. That amendment is the decision
> author's to make in CHANGES.log, not this runbook's.

### Credentials

Never baked into the image (#50 AC). Set them as secrets, which Fly stores encrypted and injects at
run time:

```
fly secrets set \
  FRONTDOOR_IMAGES_BUCKET=frontdoor-image \
  FRONTDOOR_IMAGES_ACCESS_KEY=... \
  FRONTDOOR_IMAGES_SECRET_KEY=... \
  FRONTDOOR_S3_ENDPOINT=https://<accountid>.r2.cloudflarestorage.com \
  FRONTDOOR_S3_REGION=auto \
  FRONTDOOR_DEPTH_BUCKET=frontdoor-depth \
  FRONTDOOR_DEPTH_WRITE_ACCESS_KEY=... \
  FRONTDOOR_DEPTH_WRITE_SECRET_KEY=... \
  FRONTDOOR_UPLOAD_KEY=... \
  ANTHROPIC_API_KEY=...
```

Take the values from `.env` (gitignored). **The server never gets a depth credential that can
read.** It holds read+write on the image bucket and, per **D-033**, a **write-only** token on the
depth bucket — Object Write only, no read, no list — so it can store a depth map a phone uploads
and can never read one back. `FRONTDOOR_DEPTH_ACCESS_KEY` / `FRONTDOOR_DEPTH_SECRET_KEY` are the
harness's *read* token and must **not** be set on the server. That is D-020: nothing on the
metrology path may read depth.

Create the write-only token in the Cloudflare dashboard as a third R2 API token, scoped **Object
Write** on `frontdoor-depth` alone. Then prove the scope rather than trusting the dashboard:

```
python -m frontdoor.storage verify
```

It must print `loader-denied-on-depth` **and** `depth-write-denied-on-read`. If the second is
missing, the token can read and D-033's guarantee does not hold — fix the token before capture,
not after.

`FRONTDOOR_UPLOAD_KEY` is the shared secret for `POST /upload`, the capture-ingest endpoint
(TICK-029, #33). The capture app sends it as `X-Frontdoor-Upload-Key`; the same value goes into the
app's build setting of the same name, which is why it is not committed. **Unset means the endpoint
refuses every request** — an ingest path that accepts anonymous writes into the dataset bucket
because a deploy forgot a variable is worse than one that is switched off. This key grants ingest
only: it is not an R2 credential and cannot read any bucket.

`ANTHROPIC_API_KEY` is required for the pivot's own endpoint: without it, `POST /screen` returns
**503 "screening unavailable"** — `screen_view.py`'s engine gate (`_get_engine`) returns `None`
when neither `ANTHROPIC_API_KEY` nor `ANTHROPIC_AUTH_TOKEN` is set, by design, so the rest of the
server still boots and serves. The key was missing from earlier revisions of this block, which is
why the live host 503s on `/screen` (PR #200 review F3).

### The map dataset

`GET /map/data` reads the pre-catalogue dataset from the path in the **`FRONTDOOR_MAP_DATASET`**
env var (`map_view.py`), defaulting to `data/precatalogue.json` — a relative path that does not
exist in the image, because the Dockerfile copies only `pyproject` and `src/`. **Current live
symptom:** `GET /map/data` returns a payload with `dataset_error` set and an empty pin list — the
public map renders no pins. Two ways to fix it, pick one and record it here:

1. **Bake the dataset into the image** — add a `COPY` of the dataset file to the Dockerfile and
   set `FRONTDOOR_MAP_DATASET` (in `fly.toml`'s `[env]`) to that absolute path. Note this changes
   the image, which the laptop fallback then also carries — that is fine and even desirable.
2. **Point the env var at a mounted or packaged path** — a Fly volume or a path shipped by some
   other packaging step, with `FRONTDOOR_MAP_DATASET` naming it.

Either way, verify with `curl https://frontdoor-measure.fly.dev/map/data` and confirm
`dataset_error` is `null` and pins are present.

### /screen sizing note — measure before Demo Day

The **69 MiB** footprint in the table was measured serving `GET /health`. It says nothing about
`/screen`'s worst case: up to **64 MB of multipart upload buffered in memory**, base64-encoded
(+33%) and carried through **up to 6 sequential vision calls**, on a **256 MB** machine — with
gunicorn's 30 s timeout in front of multi-call model latency. Neither the peak memory nor the
end-to-end latency of a real worst-case `/screen` request has been measured. **Measure both
before Demo Day**, with a full 6-photo upload at the size cap, and record the numbers here.

**The offline-laptop fallback cannot serve `/screen` at all** — with the venue offline there is no
route to the model API. D-016's step 3 ("same image, phone tethered to the laptop") covers
`/measure` and `/map` only; "a fallback changes the network path and nothing else" is true of the
metrology surface, not of screening. Plan the demo accordingly.

## Deploy

```
fly deploy --ha=false
fly status
curl https://frontdoor-measure.fly.dev/health      # -> {"status":"ok"}
```

`--ha=false` matters: a bare `fly deploy` creates **two** machines by default for high
availability, which doubles the cost D-031 records (~$2/mo, one machine). If the app already has
two machines from an earlier deploy, bring it back to one:

```
fly scale count 1
```

Then **verify the machine count in the `fly status` output — it must list exactly one machine.**

## Verify, before Demo Day rather than on it

**1. The endpoint answers from a phone on cellular** (#50 AC — not from laptop wifi):

Turn wifi off on the phone, then open `https://frontdoor-measure.fly.dev/health` in Safari.
HTTPS matters: iOS App Transport Security refuses plain HTTP, which is why `force_https` is set.

**2. The host and the laptop run the same image digest** (#50 AC). One command:

```
python -m frontdoor_server.deployment verify
```

It reads `data/deployment.json` and is **red until the laptop has actually pulled the image** —
"not cached yet" and "cached and matching" must not look alike, because the point is to find out
now rather than in an atrium. Both digests are committed there, so this is a check rather than a
procedure someone remembers to run correctly.

Currently recorded, both verified on 2026-09-02:

**Host digest:** `sha256:6c3e21b3559c5bb9028f7569f941f253820d5d4530366d7d29c4d228f042ff03`
(release `deployment-01M1J5D5GAN1EA0MZYMQQTNHPS`)
**Laptop digest:** identical — pulled and cached on a team Mac, not rebuilt.

**After every deploy, re-record both.** A new release is a new digest, and the cached laptop image
is then stale — which is exactly the state that looks fine until the fallback is needed:

```
fly image show                                     # the host's digest and release
fly auth docker
docker pull registry.fly.io/frontdoor-measure:<release>
docker inspect --format='{{index .RepoDigests 0}}' registry.fly.io/frontdoor-measure:<release>
```

A local `docker build` does **not** reproduce the host digest and is not expected to — Fly builds
remotely and the digest covers its own layer metadata. Rebuilding locally gives a *different* image
that merely came from the same source, which is the thing D-016's step 3 exists to rule out. The
laptop must **pull**.

**3. The laptop fallback works, offline**, with the venue wifi turned off — using the PULLED image,
not a rebuilt one:

```
docker run --rm -p 8080:8080 -e PORT=8080 \
  registry.fly.io/frontdoor-measure:deployment-01M1J5D5GAN1EA0MZYMQQTNHPS
curl http://127.0.0.1:8080/health
```

Verified 2026-09-02 on the pulled image: `/health` 200, `POST /upload` 401 (closed, no key set),
**87.6 MiB** resident — the same answers the host gives.

Pull and cache the image on the laptop **before** Demo Day (#50 AC). Do not fetch it on venue wifi.

## The fallback chain (D-016)

1. cellular to the host
2. venue wifi to the host
3. this image on a team laptop, phone tethered to it
4. the pre-recorded measurement captured Sep 8

Steps 1–3 are the same image, so a fallback changes the network path and nothing else — **for
`/measure` and `/map`**. Step 3 cannot serve `/screen` (no route to the model API when offline);
see the /screen sizing note above.

## After the Showcase

Destroy the app so the spend stops:

```
fly apps destroy frontdoor-measure
```

The dataset lives in R2 and the repo, not on this host — it holds no state and nothing is lost.
