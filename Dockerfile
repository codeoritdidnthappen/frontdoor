# TICK-062. One image for the hosted demo and the laptop fallback.
# No credentials, no depth-model weights. Bind PORT at run time.
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src

# The map dataset and the open-licensed provenance files. These are read at request time
# from paths relative to the working directory, so they have to be in the image. Without
# them the build succeeds, the server starts, and /map/data answers 200 with an empty pin
# list and a dataset_error -- indistinguishable from a working map unless somebody reads
# the body. That is what production served until TICK-337.
COPY data/precatalogue.json /app/data/precatalogue.json
COPY data/external /app/data/external

RUN pip install --no-cache-dir ".[server]"

ENV PORT=8080
# Community scans are the only state this app writes, and the container filesystem is
# replaced on every deploy. This points at the volume declared in fly.toml, so a scan
# published from a phone outlives the next deploy.
ENV FRONTDOOR_SCANS=/data/scans.jsonl
EXPOSE 8080

# exec, so gunicorn is PID 1 and a stop signal reaches it instead of the shell. The shell
# stays in the picture only to expand $PORT, which the host assigns at run time.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 2 --timeout 30 frontdoor_server.wsgi:app"]
