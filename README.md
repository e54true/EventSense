# EventSense

A market event analysis platform that tracks structured macro and corporate events from
official US sources, uses LLMs to forecast their impact on a watchlist of US equities,
and automatically validates predictions against real price movements.

> **Status**: Milestone 1 (Foundation). See [EventSense_Spec.md](EventSense_Spec.md) for
> the full engineering spec and [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md) for the
> per-milestone implementation notes (繁體中文).

---

## Quick start

### Prerequisites
- Docker Desktop (or OrbStack / Colima)
- A FRED API key — register at https://fred.stlouisfed.org/docs/api/api_key.html (free)

### Run

```bash
# 1. Copy env template and fill in your FRED key
cp backend/.env.example backend/.env
# edit backend/.env, set FRED_API_KEY=...

# 2. Bring up the stack
docker compose up --build

# 3. In another terminal, trigger a FRED CPI fetch
curl -X POST http://localhost:8000/api/v1/events/_admin/trigger-fred-cpi

# 4. List the events
curl http://localhost:8000/api/v1/events | jq
```

Browse interactive API docs at http://localhost:8000/docs.

### Local development (without Docker)

Useful for running tests / linters quickly.

```bash
cd backend
uv sync                       # installs deps into .venv/
uv run pytest                 # run tests
uv run ruff check .           # lint
uv run ruff format .          # format
uv run mypy app/              # type check
```

For the actual app you still need PostgreSQL + Redis running — easiest is
`docker compose up postgres redis` and then `uv run uvicorn app.main:app --reload`
locally.

---

## Architecture (current)

```
┌──────────────┐     ┌──────────────┐
│  FastAPI     │ ──→ │  PostgreSQL  │
│  (port 8000) │     │  (port 5432) │
└──────┬───────┘     └──────────────┘
       │
       │ calls
       ▼
┌──────────────┐
│  FRED API    │
└──────────────┘

Redis is running but not yet exercised (Milestone 2 adds Celery).
```

Full target architecture is documented in [EventSense_Spec.md §4](EventSense_Spec.md).

---

## Repo layout

```
.
├── backend/         # Python app
│   ├── app/         # FastAPI + SQLAlchemy code
│   ├── alembic/     # DB migrations
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── docker-compose.yml
├── EventSense_Spec.md       # Full spec
└── IMPLEMENTATION_LOG.md    # Per-milestone notes (繁體中文)
```
