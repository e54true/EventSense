# Multi-stage build to keep the runtime image lean.
# Stage 1 installs deps with uv into a venv; stage 2 copies only what's needed.

FROM python:3.12.7-slim AS builder

# Pinned uv version so the image is reproducible (vs ":latest" drifting).
COPY --from=ghcr.io/astral-sh/uv:0.5.18 /uv /usr/local/bin/uv

WORKDIR /app

# Cache deps layer separately from source code for fast rebuilds.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy source and finalize install (project itself is installed as editable).
COPY . .
RUN uv sync --frozen --no-dev


FROM python:3.12.7-slim AS runtime

# curl is needed for the HEALTHCHECK below; tini gives us proper signal
# forwarding so Ctrl-C / Railway's SIGTERM cleanly reach uvicorn / celery.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tini \
    && rm -rf /var/lib/apt/lists/*

# Run as non-root for basic container hardening.
RUN useradd --create-home --shell /bin/bash app
WORKDIR /app

# Bring over the prepared venv + source from builder.
COPY --from=builder --chown=app:app /app /app

# PORT default — Railway / Render / Fly all inject their own $PORT at runtime
# which overrides this; the default lets `docker run` work standalone for local
# smoke tests. (Docker rejects comments inside a multi-line ENV continuation,
# so this comment lives outside.)
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

USER app

EXPOSE 8000

# Healthcheck so Railway / k8s know when to mark the container ready.
# Uses the existing /api/v1/health endpoint, with short interval during
# startup and grace period for cold boot + first migration.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl --fail --silent http://localhost:${PORT}/api/v1/health || exit 1

# tini as PID 1 — forwards signals properly so worker/beat shutdown cleanly.
# Shell form for ${PORT} expansion. Railway/Vercel override the start command
# per service (see DEPLOYMENT.md); this default is for `docker run` smoke tests.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
