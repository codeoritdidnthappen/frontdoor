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

`--copy-config` uses the committed `fly.toml`. Say **no** to Postgres, Redis and any other add-on.
The first phone-label version writes ephemeral CSV state inside the application container; the
limitations below explain what must be copied before a replacement or redeploy.

### Checking what a deployment can actually do

`GET /ready` answers the question `/health` does not: whether a scan taken on a phone will be
assessed, and whether its photograph will be stored.

```json
{"ready": false, "subsystems": {"screening": true, "photo_storage": false, "map_dataset": true,
 "scan_store": true}, "degraded": ["photo_storage"]}
```

`photo_storage` is the one that matters most, because its failure is invisible. Without those
credentials the endpoint still answers, the assessment still succeeds, and the image simply does
not persist. That is how `FRONTDOOR_UPLOAD_KEY` went missing for days: nothing was broken enough
to notice. The deploy workflow reads this endpoint and warns on each degraded subsystem, and
fails the run outright when the model key is absent, since nothing works at all without it.

Each subsystem is **verified, not assumed** (#353). The first version of this endpoint checked the
presence of exactly what had failed before, and every one-notch variant walked straight through it:

| subsystem | what it proves | why presence was not enough |
| --- | --- | --- |
| `screening` | either `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` is set | the engine accepts either, so checking only one reported a working deployment as broken. Still presence-only: the cheapest way to verify a model key is a billed model call, on every probe |
| `photo_storage` | one bounded `HEAD` on the bucket succeeds | a revoked key or a deleted bucket leaves every variable set, and is symptomatically identical to the missing credential this endpoint was written for |
| `map_dataset` | the file parses **and** holds at least one row | a present-but-unparseable file passed the old `stat()` while `/map/data` served zero pins |
| `scan_store` | the store is readable and no record in it was skipped | a store nobody has written to yet is fine; a missing *directory* is the unmounted volume, and an unparseable line is a contributor's scan that is off the map for good |

The storage probe is the one check that leaves the process, so it is bounded (2 s timeouts, no
retries) and its answer — success or failure — is cached for 30 seconds. A storage outage costs
one request per half minute rather than one per caller, and the endpoint stays cheap enough to
poll. Nothing here mutates: proving the volume is *writable* would mean writing to the only state
this app keeps, which is a worse trade than missing a read-only mount, and `append_scan`'s refusal
to create its own parent directory is what catches the mount itself.

It reports presence and status, never values, and never names the missing variable: a status is
enough for an operator and useless to anyone else. To find out which credential is missing, look
at the secrets on the host, or at the server log — the probe records the provider's own message
there, where it is not public.

### Installing the app on a phone

There is no paid Apple developer account on this project, so TestFlight and the App Store are
both closed: free provisioning builds run only on a cabled device and expire in seven days. The
app reaches a phone through the browser instead.

`GET /app` is a real installable app, not a bookmark. `/app-manifest.json` gives it a name, an
icon, a standalone display mode and the brand background; `/app-sw.js` caches the page shell so
it opens with no signal. Together they mean **Share, then Add to Home Screen** in Safari installs
EntryMap with its own icon and no browser chrome.

The service worker caches the page, the icon and the manifest, and nothing else. Screening,
map and photo responses are never cached: a stale verdict is a wrong answer about somebody's
front door, which is worse than no answer. A test pins that allowlist.

Both files are served from the app's own origin, and the worker is served with `no-cache` and
`Service-Worker-Allowed: /`, so a redeploy reaches phones that already installed.

### Redeploying from CI

`.github/workflows/deploy.yml` deploys this app on manual dispatch only, never on merge: Actions
tab, **deploy**, **Run workflow**, and a one-line reason that the run records alongside the commit
and the actor. It runs `flyctl deploy --remote-only`, then fails the run unless `/health`, `/app`
and `/app-icon.png` all answer 200, so a green run means the path a phone uses is actually serving.
A concurrency group keeps two deploys off the same machine.

It needs one repository secret, created once by whoever holds the Fly account:

```sh
fly tokens create deploy -a frontdoor-measure
```

Paste the value into **Settings → Secrets and variables → Actions → New repository secret** as
`FLY_API_TOKEN`. It is a deploy-scoped token, not an account token: it can push a release to this
one app and nothing else. Without it the workflow stops on its first step and says so rather than
failing somewhere confusing. Local `fly deploy` from a logged-in machine keeps working unchanged.

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

**D-044 amends D-031.** The no-silent-billing mechanism is prepaid credits (hard stop at zero
balance) plus an advisory billing alert, not a Fly spend limit. Evidence: PR #200 review F1. This
runbook already named that mechanism; the decision record now matches it.

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
  FRONTDOOR_DEPTH_INGEST_URL=https://frontdoor-depth-ingest.<account>.workers.dev \
  FRONTDOOR_DEPTH_INGEST_KEY=... \
  FRONTDOOR_UPLOAD_KEY=... \
  ANTHROPIC_API_KEY=...
```

Take the values from `.env` (gitignored). **The server gets no R2 depth credential.** Cloudflare
R2 permanent API tokens offer Object Read & Write or Object Read only, not Object Write only, so
D-039 replaces D-033's impossible permanent token with an isolated Worker. The Worker receives a
validated stream over its authenticated PUT-only HTTP surface and writes through its R2 binding.
`FRONTDOOR_DEPTH_ACCESS_KEY` / `FRONTDOOR_DEPTH_SECRET_KEY` remain on the harness and must **not**
be set on Fly.

Deploy the Worker first. **Deploy, then set the secret** -- `wrangler secret put` attaches to a
Worker that already exists, so the reverse order has nothing to attach to:

```
cd workers/depth-ingest
npx wrangler deploy
npx wrangler secret put FRONTDOOR_DEPTH_INGEST_KEY   # reads the value from stdin
```

Use the same independently generated service key on the Worker and Fly; it is not the phone's
`FRONTDOOR_UPLOAD_KEY`. Record the deployed `workers.dev` URL in `FRONTDOOR_DEPTH_INGEST_URL`.

**Deployed 2026-09-03 (TICK-251, #218):**

```
FRONTDOOR_DEPTH_INGEST_URL=https://frontdoor-depth-ingest.frontdoor-depth-ingest.workers.dev
```

Verified live against the real bucket, not against a stub: an authenticated PUT of an `open/`
probe returned 201 and the bytes read back through `frontdoor.depth_access` with a matching
SHA-256; repeating it returned 409 without overwriting; a bad credential returned 401 and created
no object; `GET` returned 405. The probe object was deleted afterwards, which is why it is an
`open/` key -- #187 locked `sealed/` against deletion indefinitely, so a sealed probe could never
be cleaned up.

**Call it with `http.client`, not `urllib`.** `frontdoor_server.depth_ingest.put_depth` already
does. Cloudflare's edge answers `urllib`'s `Python-urllib/3.x` User-Agent with `403 error code:
1010` before the Worker runs at all, which reads as a Worker rejection and is not one. Sending no
User-Agent, as `http.client` does, is fine.

The Worker's `wrangler.jsonc` binds `DEPTH_BUCKET` directly, so there is no R2 access key to copy
to Fly or into the Worker environment.

**Merging a Worker change does not ship it.** `workers/depth-ingest` is deployed by hand, so the
code on `main` and the running Worker can disagree. After changing anything under that directory:

```
cd workers/depth-ingest
npm ci
npx wrangler deploy
```

Build from a checkout of `main`: a stale branch ships the old code and still reports success. The
encrypted secret survives a deploy and does not need setting again. To go back, take the previous
id from `npx wrangler versions list --name frontdoor-depth-ingest` and run
`npx wrangler rollback <version-id>`.

`FRONTDOOR_UPLOAD_KEY` is the shared secret for `POST /upload` and `POST /labels`, the phone's
write-only capture and human-label endpoints (TICK-029, #33; TICK-282, #309). The capture app
sends it as `X-Frontdoor-Upload-Key`; the same value goes into the
app's build setting of the same name, which is why it is not committed. **Unset means the endpoint
refuses every request** — an ingest path that accepts anonymous writes into the dataset bucket
because a deploy forgot a variable is worse than one that is switched off. This key grants ingest
only: it is not an R2 credential and cannot read any bucket.

### Future-capture labels (TICK-282)

`POST /labels` accepts one completed entrance-level human label record and appends four rows to
`/app/data/labels.csv` in the running application container. This first version deliberately has
no database, volume, backup, or automatic repository sync. **Those accepted runtime labels are
lost when the container is replaced or the app is redeployed.** Download them before either event
if they need to survive. The frozen 53-entrance artifact remains the repository's
`data/labels.csv` and is completed separately under #302.

`ANTHROPIC_API_KEY` is required for the pivot's own endpoint: without it, `POST /screen` returns
**503 "screening unavailable"** — `screen_view.py`'s engine gate (`_get_engine`) returns `None`
when neither `ANTHROPIC_API_KEY` nor `ANTHROPIC_AUTH_TOKEN` is set, by design, so the rest of the
server still boots and serves. The key was missing from earlier revisions of this block, which is
why the live host 503s on `/screen` (PR #200 review F3).

**Running the server locally reads `.env`.** `frontdoor_server/wsgi.py` calls
`frontdoor.storage.load_local_env()` before building the app, so the variables above can sit in
the gitignored `.env` and be picked up by `gunicorn frontdoor_server:app` or
`flask --app frontdoor_server.wsgi run`. Real environment variables still win, so the container
is unaffected. Two caveats worth knowing before debugging a key:

- It happens **on import of the entrypoint**. Building the app yourself with
  `create_app()` — as the tests do — does not load `.env`, deliberately: several tests delete a
  variable to assert the keyless behaviour, and loading `.env` there would hand it back and make
  them pass or fail depending on the developer's machine. Running `create_app().run(...)`
  directly in a REPL will therefore 503 on `/screen` with a perfectly good key in `.env`.
- A key that is present but of the wrong **type** fails differently. An *identity-linked* API key
  returns 400 `anthropic-workspace-id is required...`, surfacing as a 502
  `screening engine failure`, not a 503. Use a standard workspace key from
  console.anthropic.com; the engine sends no workspace header.

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

### Scan persistence (TICK-262)

`POST /screen/publish` is the consent step after `/screen`: the same blur → audit → integrated
assessment, and then — only when the face audit answered exactly `clear` — it stores the
**processed** image bytes and appends one scan record. It needs two things beyond `/screen`:

- **Object storage** — the same images-bucket credential the `/upload` path already uses
  (`FRONTDOOR_IMAGES_BUCKET` / `FRONTDOOR_IMAGES_ACCESS_KEY` / `FRONTDOOR_IMAGES_SECRET_KEY`,
  plus `FRONTDOOR_S3_ENDPOINT` / `FRONTDOOR_S3_REGION`). No new credential. Scan images land
  under `open/scans/<place>/<uuid>.jpg`; `GET /scan/photo/scans/<place>/<uuid>.jpg` serves them
  back (unauthenticated — every stored byte is face-blurred and EXIF-stripped by construction,
  and only keys under the `scans/` prefix resolve).
- **`FRONTDOOR_SCANS`** — path of the append-only JSONL scan-record store, default
  `data/scans.jsonl` (relative, like the map dataset — same caveat: point it at a **mounted
  volume** in `fly.toml`'s `[env]`, or the records vanish with the machine's rootfs on the next
  deploy).

`GET /map/data` merges the store into the pre-catalogue automatically; no scan store, or an
unreadable one, changes nothing. If storage is down or misconfigured, publish degrades to a 503
`assessed-but-not-published` response that still carries the verdicts — nothing is dropped
silently, and no credential material ever appears in a response.

### What the running server writes, and where it survives

Three stores, and the difference between them is the difference between a durable record and a
silent loss. `Dockerfile` redirects the first two onto the volume `fly.toml` mounts at `/data`;
a test pins that list against both files.

| Store | Variable | In the image | Survives a deploy |
|---|---|---|---|
| Community scans | `FRONTDOOR_SCANS` | `/data/scans.jsonl` | yes |
| Owner claims | `FRONTDOOR_CLAIMS` | `/data/claims.jsonl` | yes |
| Future-capture labels | `FRONTDOOR_LABELS_PATH` | not set — `data/labels.csv` in the container | **no**, by design (TICK-282) |

**Claims lost is a credential lost, not a record lost.** The claim record holds the only bearer
token for an approved workspace, so an unmounted claims path means every redeploy 404s every
workspace that existed and no claimant can get back in. Worse, the `owner_confirmed` flag that
an approved claim authorises lives in the *scan* store, which is on the volume — so the map goes
on showing Owner-confirmed pins backed by claims that no longer exist. And `load_claims` answers
a missing file with an empty list, exactly as it answers a store with no claims in it, so
nothing anywhere reports the difference. That was live until this was set.

`FRONTDOOR_CLAIM_CODES` (default `data/claim_codes.json`) is read-only team-issued config, not
run-time state. It is **not** copied into the image, so the `in_store_code` claim channel is
unavailable on the host; `listed_phone` and `business_email` are unaffected. Ship that file if
in-store codes are wanted live.

### EntryMap app page (TICK-247)

**`GET /app`** — `https://frontdoor-measure.fly.dev/app` — is the phone-web scanner: the map, the
place cards, and the scan flow, served as one self-contained page (`src/frontdoor_server/app.html`,
~1 MB with its photos embedded). Every call it makes is **same-origin**: the shutter posts to
`/screen` (assess only), "Publish scan" posts to `/screen/publish` with the place reference
(`place_id`, or `lat` + `lng` + `name` from the phone's fix and the name the user confirms), the
card loads the stored photo from `/scan/photo/<key>`, and the map merges `/map/data` at load so
scans published from other phones appear. No CORS is involved.

The page itself needs nothing — it loads with no key and no storage, and `/map/data` returning a
`dataset_error` only means the embedded pins show. **Live publishes need what `/screen/publish`
needs**: `ANTHROPIC_API_KEY` (or the page shows the 503 "screening unavailable" detail on the
review screen) **and the object-storage credential plus `FRONTDOOR_SCANS`** above (or a publish
comes back assessed-but-not-published, which the page shows as "saved for later"). When the phone
cannot reach the server at all, the page falls back to a simulated scan and labels it *Simulated*
everywhere it appears; it never presents that as a publish.

The page is served from the image, so **a change to `app.html` ships with the next
`fly deploy --ha=false`** and the phone picks it up within the page's five-minute `max-age`
(force-reload sooner). Re-record the digests after that deploy, as below.

### /screen sizing note — measure before Demo Day

The **69 MiB** footprint in the table was measured serving `GET /health`. It says nothing about
`/screen`'s worst case: up to **64 MB of multipart upload buffered in memory**, base64-encoded
(+33%) and sent as **one integrated vision call carrying up to 6 image blocks**, on a **256 MB**
machine — with gunicorn's 30 s timeout in front of the model call.

> **Superseded 2026-09-04 — the measurement below was taken before `faceblur` existed.** That
> release did not load OpenCV. The current one decodes, blurs and re-encodes every `/screen`
> image, and at 256 MB a **single 200 KB PNG** now OOM-kills the worker:
>
> ```
> Out of memory: Killed process 644 (gunicorn) total-vm:572864kB anon-rss:140000kB
> ```
>
> The client gets a **502 with an empty body** — Fly's proxy filling in for an app that died
> mid-request — so it is not the JSON error contract and the cause shows only in `fly logs`.
>
> The machine is now **512 MB** (`fly.toml`, not `fly scale` — see below), and the same request
> returns **200 in 6.4 s**. The figures below are kept because their *reasoning* still holds; the
> numbers do not.
>
> **`fly scale memory` alone does not stick.** It is reverted by the next `fly deploy`, which is
> what happened on 2026-09-04: the machine was scaled to 512, a deploy silently put it back to
> 256, and the OOM returned looking like a new fault. The value belongs in `fly.toml`.

**Measured 2026-09-03** on release `deployment-01M1MFVVXFFMPFN9XJKD49QZ8P`, in a container capped
at 256 MB exactly as the host is, with six real captures (2.7–2.8 MB each, 17.2 MB of multipart):

| | |
|---|---|
| Idle, serving `/health` | **69.3 MiB** — the table's 69 MiB still holds |
| Peak during a 6-photo `/screen` | **186.3 MiB of 256 MB (73%)** |
| Cost of one in-flight request | **~117 MiB above idle** |
| End-to-end | **17.3 s**, HTTP 200 |

**Those numbers were measured on the previous build, which fanned the six views out into
overlapping per-view model calls.** `/screen` now sends all views in **one integrated call**
(TICK-245): there is no thread fan-out — the memory profile is the N buffered uploads plus their
base64 copies alive at once inside a single request body. Peak memory should land near the
186 MiB above, since the same six payloads are in memory either way (held by one request body
instead of six concurrent calls), but the latency changes shape: one call replaces six
overlapping ~13 s calls, and the offline eval's median was **~7.2 s per entrance** on the new
default model — inside gunicorn's `--timeout 30` with no reliance on call overlap. Re-measure
both numbers on the first deploy of the integrated build and update this table.

### Two `/screen` requests at once kill the worker — measured 2026-09-03

The container runs `--workers 1 --threads 2`, so two requests can be in flight. Two 6-photo
uploads fired together on the 256 MB cap:

```
[ERROR] Worker (pid:7) was sent SIGKILL! Perhaps out of memory?
[INFO]  Booting worker with pid: 23
```

`docker inspect` confirms `OOMKilled: true`. **Both requests are lost with no error response** —
curl sees the 100-continue and then the connection dies, so there is no status code and nothing
in the JSON error contract. The gunicorn master survives and boots a replacement worker, and the
service is healthy again seconds later: `/health` 200, and a single 6-photo request still returns
200 in 17.5 s.

**It died 0.8 s in, while the uploads were still being buffered — before the vision calls
finished.** So this is not about the model at all. Two 17 MB multipart bodies plus their base64
copies exceed the cap on their own, and `MAX_REQUEST_BYTES` allows 64 MB *per request*, four
times what six real captures need.

On stage this reads as the demo hanging and then failing with no message, and recovering by
itself just after someone has started apologising. One presenter and one curious onlooker in the
audience is enough to cause it.

**Pick one before Demo Day and record it here:**

| Option | Effect | Cost |
|---|---|---|
| `--threads 1` in the Dockerfile CMD | the second request queues instead of racing | a concurrent request waits ~17 s |
| Lower `MAX_REQUEST_BYTES` toward what six captures actually need (~20 MB) | bounds the buffering that causes this | rejects uploads the API would refuse anyway |
| A 512 MB machine | headroom | money, and it only moves the threshold |

`--threads 1` is the smallest change that turns a silent crash into a slow answer, which is the
right trade for a demo with one operator.

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

**1. The endpoint answers from James's iPhone 17 Pro on cellular** (#50 AC — not from laptop wifi):

Turn wifi off on James's iPhone 17 Pro, then open `https://frontdoor-measure.fly.dev/health` in Safari.
HTTPS matters: iOS App Transport Security refuses plain HTTP, which is why `force_https` is set.

**2. The host and the laptop run the same image digest** (#50 AC). One command:

```
python -m frontdoor_server.deployment verify
```

It asks **three** sources and requires all three to agree: what the host is serving right now
(`fly image show`), what this machine has in its docker cache (`docker inspect`), and what
`data/deployment.json` records. That matters because the failure mode is a redeploy nobody wrote
down — the record stays internally consistent while the laptop holds last week's image, so
comparing the file to itself reports success in exactly the case worth catching.

`verify --recorded-only` does that weaker file-only comparison, for a machine without `flyctl` or
`docker`. It prints a warning saying so, because it proves nothing about what is deployed.

Currently recorded, both verified on 2026-09-03:

**Host digest:** `sha256:d1d3e6f594983ac4c44a213d6dc2c164aa3b408e312c0b0e3863d2503c5e75c6`
(release `deployment-01M1MFVVXFFMPFN9XJKD49QZ8P`)
**Laptop digest:** identical — pulled and cached on a team Mac, not rebuilt.

**After every deploy, re-record both.** A new release is a new digest, and the cached laptop image
is then stale — which is exactly the state that looks fine until the fallback is needed:

```
fly image show --app frontdoor-measure             # the host's digest and release
fly auth docker
docker pull registry.fly.io/frontdoor-measure:<release>
docker inspect --format='{{json .RepoDigests}}' \
  registry.fly.io/frontdoor-measure:<release>
```

**Read the `registry.fly.io/...` entry, not the first one.** An image tagged for more than
one repository carries several `RepoDigests`, and position 0 is not guaranteed to be the Fly
one -- `deployment.py` scans for the `registry.fly.io/frontdoor-measure@` prefix rather than
indexing, and this command now prints the same list it reads. Take the part after `@`:
pasting the whole `registry.fly.io/frontdoor-measure@sha256:...` string into
`data/deployment.json` is rejected as not a digest. Then run
`verify` — it re-reads both systems itself, so the paste is a record, not the check.

A local `docker build` does **not** reproduce the host digest and is not expected to — Fly builds
remotely and the digest covers its own layer metadata. Rebuilding locally gives a *different* image
that merely came from the same source, which is the thing D-016's step 3 exists to rule out. The
laptop must **pull**.

**3. The laptop fallback works, offline**, with the venue wifi turned off — using the PULLED image,
not a rebuilt one:

```
docker run --rm -p 8080:8080 -e PORT=8080 \
  registry.fly.io/frontdoor-measure:deployment-01M1MFVVXFFMPFN9XJKD49QZ8P
curl http://127.0.0.1:8080/health
```

Verified 2026-09-03 on the pulled image for release
`deployment-01M1MFVVXFFMPFN9XJKD49QZ8P`: `/health` 200, `GET /screen` 200 (the demo page),
`POST /upload` 401 (closed, no key set), **92.2 MiB** resident.

> Re-measure this after every deploy rather than carrying the previous release's numbers
> forward. The digests above prove the laptop HOLDS the deployed image; only running it
> proves the laptop can SERVE it, and those are the two different claims D-016 step 3 needs.

That is **not** the 69 MiB recorded for the host above, and the difference is worth a sentence
rather than being presented as one measurement. Same image, different measurement: the host figure
is Fly's own reading of a 256 MB machine, this one is `docker stats` on a Mac with 7.7 GB, where
the allocator has no reason to be frugal. Both are well under the cap and neither is a regression —
but the number that governs the cap is the host's, and `/screen`'s worst case is **now measured**:
186.3 MiB peak on a 256 MB machine, in the sizing note above.

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

The image dataset lives in R2 and the frozen label artifact lives in the repo. Future-capture
labels written by `POST /labels` are temporary container state and must be downloaded before the
app is destroyed, replaced, or redeployed or they are lost.

## Which commit is running (TICK-337, #337)

`GET /version` answers, with no credentials:

```sh
curl -s https://frontdoor-measure.fly.dev/version
# {"commit":"<40-hex>"}
```

`/health` deliberately still returns only `{"status": "ok"}` — it is the D-016 fallback chain's
liveness probe, and a cheap check should not grow a second job.

**The commit is baked in at build time.** The CI deploy passes it; a local deploy must too, or the
server will honestly report `unknown`:

```sh
fly deploy -a frontdoor-measure --build-arg FRONTDOOR_COMMIT=$(git rev-parse HEAD)
```

`unknown` is not a soft failure. It means the running image cannot be identified, and the drift
check treats it as an error rather than letting it compare equal to anything.

**Before trusting any live probe, check for drift:**

```sh
python -m frontdoor_server.deployment drift          # against HEAD
python -m frontdoor_server.deployment drift origin/main
```

It exits non-zero and names both sides when the server is not running what your checkout says.

Why this exists: on 2026-09-05 the host served the previous day's image for a full day while `main`
moved on. A bug that had already been fixed and merged was still live, was probed, and was reported
a second time as a new defect. Nothing in the system could say what was running.
