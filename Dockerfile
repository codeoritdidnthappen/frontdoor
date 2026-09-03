# TICK-062. One image for the hosted demo and the laptop fallback.
# No credentials, no depth-model weights. Bind PORT at run time.
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src

RUN pip install --no-cache-dir ".[server]"

ENV PORT=8080
EXPOSE 8080

# exec, so gunicorn is PID 1 and a stop signal reaches it instead of the shell. The shell
# stays in the picture only to expand $PORT, which the host assigns at run time.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 2 --timeout 30 frontdoor_server.wsgi:app"]
