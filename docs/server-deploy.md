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

### Set the spend limit before deploying

D-026 requires that billing cannot start silently. On a paid plan that is no longer satisfied by
having no card, so it is replaced by an explicit cap (D-031):

1. Fly dashboard → the organisation → **Billing** → set a **monthly spend limit** (5 USD is ample
   against a ~2 USD machine).
2. Enable the billing alert email.
3. Record the date it was set in this file, below.

**Spend limit set:** 2026-09-02, before the first deploy, with the billing alert enabled.

### Credentials

Never baked into the image (#50 AC). Set them as secrets, which Fly stores encrypted and injects at
run time:

```
fly secrets set \
  FRONTDOOR_IMAGES_BUCKET=frontdoor-image \
  FRONTDOOR_IMAGES_ACCESS_KEY=... \
  FRONTDOOR_IMAGES_SECRET_KEY=... \
  FRONTDOOR_S3_ENDPOINT=https://<accountid>.r2.cloudflarestorage.com \
  FRONTDOOR_S3_REGION=auto
```

Take the values from `.env` (gitignored). **The server gets the images credential only** — never the
depth one. That is D-020: the loader and the server must not be able to read depth.

## Deploy

```
fly deploy
fly status
curl https://frontdoor-measure.fly.dev/health      # -> {"status":"ok"}
```

## Verify, before Demo Day rather than on it

**1. The endpoint answers from a phone on cellular** (#50 AC — not from laptop wifi):

Turn wifi off on the phone, then open `https://frontdoor-measure.fly.dev/health` in Safari.
HTTPS matters: iOS App Transport Security refuses plain HTTP, which is why `force_https` is set.

**2. The host and the laptop run the same image digest** (#50 AC):

```
fly image show                                     # digest on the host
docker build -t frontdoor-server . && docker inspect --format='{{index .RepoDigests 0}}' frontdoor-server
```

Record both here and confirm they match. If they differ, the fallback is not a fallback.

**Host digest:** `sha256:a20ca31a250970669988974385c950a1df72025f8ed7ae2e9ad4933533fb637a`
(deployment `01M1HRE8MS93JZTJPTEYJV32M5`, 2026-09-02)
**Laptop digest:** _record when the image is pulled and cached on the demo laptop, before Demo Day._

A local `docker build` does **not** reproduce the host digest and is not expected to — Fly builds
remotely and the digest covers its own layer metadata. The check that matters is that the laptop
**pulls the deployed image** rather than rebuilding it:

```
fly auth docker
docker pull registry.fly.io/frontdoor-measure:deployment-01M1HRE8MS93JZTJPTEYJV32M5
docker inspect --format='{{index .RepoDigests 0}}' \
  registry.fly.io/frontdoor-measure:deployment-01M1HRE8MS93JZTJPTEYJV32M5
```

That digest must equal the host digest above. Rebuilding locally gives a *different* image that
merely came from the same source, which is the thing D-016's step 3 is supposed to rule out.

**3. The laptop fallback works, offline**, with the venue wifi turned off:

```
docker run --rm -p 8080:8080 -e PORT=8080 frontdoor-server
curl http://127.0.0.1:8080/health
```

Pull and cache the image on the laptop **before** Demo Day (#50 AC). Do not fetch it on venue wifi.

## The fallback chain (D-016)

1. cellular to the host
2. venue wifi to the host
3. this image on a team laptop, phone tethered to it
4. the pre-recorded measurement captured Sep 8

Steps 1–3 are the same image, so a fallback changes the network path and nothing else.

## After the Showcase

Destroy the app so the spend stops:

```
fly apps destroy frontdoor-measure
```

The dataset lives in R2 and the repo, not on this host — it holds no state and nothing is lost.
