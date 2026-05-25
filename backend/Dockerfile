# Multi-stage build to keep the runtime image lean.
# Stage 1 installs deps with uv into a venv; stage 2 copies only what's needed.

FROM python:3.12-slim AS builder

# Copy uv from its official image — faster than pip-installing it.
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app

# Cache deps layer separately from source code for fast rebuilds.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy source and finalize install (project itself is installed as editable).
COPY . .
RUN uv sync --frozen --no-dev


FROM python:3.12-slim AS runtime

# Run as non-root for basic container hardening.
RUN useradd --create-home --shell /bin/bash app
WORKDIR /app

# Bring over the prepared venv + source from builder.
COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app

EXPOSE 8000

# Default command — overridden by docker-compose for dev (which adds --reload).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
