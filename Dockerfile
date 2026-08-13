# Goal A Engine — one image, four doors: run | mcp | status | dashboard.
# The command word picks the process (docker-entrypoint.sh); config comes from
# the environment ONLY — no .env, no secret, in any layer. tests/ ships in the
# image on purpose: the suite must stay green inside the container too.
FROM python:3.13-slim

WORKDIR /app

# Dependencies first, from the lock, as their own cached layer.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

# The engine — a named allowlist, never `COPY .` (a tree copy could smuggle
# local state or credentials into a layer).
COPY pyproject.toml docker-entrypoint.sh Dockerfile .dockerignore ./
COPY src/ src/
COPY scripts/ scripts/
COPY tests/ tests/
COPY db/ db/

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

# Never root at runtime; /app stays writable for the pipeline's lock file.
RUN useradd --create-home app && chown -R app:app /app
USER app

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["run"]
