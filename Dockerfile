# TICK-062. One image for the hosted demo and the laptop fallback.
# No credentials, no depth-model weights. Bind PORT at run time.
FROM python:3.11-slim

WORKDIR /app

# The commit this image was built from, so the running server can say what it is (#337). Passed
# by the deploy -- `--build-arg FRONTDOOR_COMMIT=$(git rev-parse HEAD)`. Left as "unknown" when
# nobody passed it, because a wrong answer here is worse than no answer: the whole point is to be
# able to trust what /version says.
ARG FRONTDOOR_COMMIT=unknown
ENV FRONTDOOR_COMMIT=$FRONTDOOR_COMMIT

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src

# The map dataset and the open-licensed provenance files. These are read at request time
# from paths relative to the working directory, so they have to be in the image. Without
# them the build succeeds, the server starts, and /map/data answers 200 with an empty pin
# list and a dataset_error -- indistinguishable from a working map unless somebody reads
# the body. That is what production served until TICK-337.
COPY data/precatalogue.json /app/data/precatalogue.json
COPY data/external /app/data/external
# The curated on-site publication (TICK-333): a committed dataset file like the
# pre-catalogue, read at request time from a path relative to the working
# directory, so it is copied in for the same reason. It is NOT the runtime scan
# store below -- that one lives on the volume and this one ships in the image,
# and /map/data reads both.
COPY data/published_scans.jsonl /app/data/published_scans.jsonl

RUN pip install --no-cache-dir ".[server]"

ENV PORT=8080
# Five things this app writes at run time, and the container filesystem is replaced on every
# deploy. The four below are pointed at the volume declared in fly.toml, so what a phone
# published outlives the next deploy. The fifth is knowingly ephemeral -- see below.
#
# This comment used to say scans were the only state written here. They were not, and the claim
# was load-bearing: it is what made an ephemeral claims path look like nothing was missing.
ENV FRONTDOOR_SCANS=/data/scans.jsonl
# Owner claims. Losing these is not a lost record, it is a lost credential: the claim carries the
# only bearer token for an approved workspace, so a deploy 404s every workspace that existed --
# while `owner_confirmed`, which a claim authorised, persists in the scan store on the volume.
# The map goes on showing Owner-confirmed pins backed by claims that no longer exist, and
# `load_claims` answers a missing file with an empty list, so nothing anywhere reports it.
ENV FRONTDOOR_CLAIMS=/data/claims.jsonl
# Community corrections (TICK-387). A person photographs a door that has changed, writes what
# they saw and presses Send. Before this line existed there was no endpoint at all and the note
# died in the browser; an ephemeral path here would be the quieter version of the same defect --
# the note is received, the sender is told so truthfully, and the next deploy erases it with
# nothing anywhere reporting that a queue of unread reports went away.
ENV FRONTDOOR_CORRECTIONS=/data/corrections.jsonl
# One assessment per photograph (TICK-435). The verdict is a function of the image because
# this file says what the image already got; on the ephemeral filesystem every deploy would
# empty it, and the same photograph would be re-sampled and could come back with a different
# answer -- the exact defect the store exists to end, arriving on a release cadence instead of
# a per-request one. It holds digests and verdicts only: no image bytes, of either kind.
ENV FRONTDOOR_ASSESSMENTS=/data/assessments.jsonl
# NOT redirected: `POST /labels` appends to data/labels.csv inside the container and those rows
# are lost on the next deploy. That is a known and documented limitation of the first phone-label
# version (TICK-282, docs/server-deploy.md), not an oversight of this line -- download them before
# a redeploy. Named here so the list above stays honest about what is and is not durable.
EXPOSE 8080

# exec, so gunicorn is PID 1 and a stop signal reaches it instead of the shell. The shell
# stays in the picture only to expand $PORT, which the host assigns at run time.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 2 --timeout 30 frontdoor_server.wsgi:app"]
