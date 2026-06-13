# EventSense

A market event analysis platform that tracks structured macro and corporate events from
official US sources (FRED, SEC EDGAR, FOMC, Yahoo Finance), uses LLMs to forecast their
impact on a watchlist of US equities, and automatically validates predictions against
real price movements.

> **Status**: Milestones 1–9 shipped to production on Railway; M9.5 production
> hardening, M9.6 accuracy overhaul (release-date anchoring, per-window
> scoring, prompt v3 + consensus voting, terminal UI), M9.7 simulated
> trading P&L, and M9.8 Fed speeches/testimony ingestion complete. M10 (auth +
> watchlist), M11 (observability), M12 (polish), M13–M14 (AWS migration via
> Terraform) are not yet started. See
> [EventSense_Spec.md](EventSense_Spec.md) for the full engineering spec and
> [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md) for per-milestone implementation
> notes (繁體中文).

---

## Highlights

- **Async backend** — FastAPI 0.115, SQLAlchemy 2.0 async, asyncpg, Pydantic v2.
- **DB-driven state-machine pipeline** — events flow `FETCHED → ANALYZED → outcomes`
  via row status, not Celery chains, so worker restarts can't drop state.
- **Ingestion adapters** — FRED (macro releases in ALFRED vintage mode —
  events anchor on the true first-release date and carry derived surprise
  metrics like CPI MoM/YoY and NFP payroll change), SEC EDGAR (8-K filings,
  with document-body download), FOMC (statements + dot plot + Fed
  speeches/testimony from the Board RSS feeds, with speaker/role extraction
  and body download), Yahoo Finance (prices + earnings + fundamentals).
  Top-10 US companies watchlist; late additions track forward-only (no
  history backfill).
- **LLM analysis with typed structured output** — OpenAI + Anthropic through
  the [`instructor`](https://python.useinstructor.com) library; context-aware
  prompt (v3) injects macro indicators, trailing market state
  (momentum + realized vol), the model's own aggregated track record, and the
  exact scoring rules; emits separate 24h and 7d directional calls per ticker.
  High-stakes events (FOMC / CPI / NFP / GDP / earnings) get 3-sample
  self-consistency voting on the premium model.
- **Automated validation loop** — DB-polled validator computes directional
  alignment of raw returns at +24h / +7d with per-window neutral bands
  (±0.5% / ±1.5%); `/accuracy` reports rates alongside constant-strategy
  baselines (always-bullish/bearish/neutral) and a confidence-bucket
  calibration table.
- **Simulated trading P&L** — `/pnl` turns every validated call into a
  $100 paper trade (BULLISH long, BEARISH short, NEUTRAL stand-aside) and
  reports cumulative P&L, return on deployed capital, win rate, an equity
  curve, and an always-long-SPY same-stakes benchmark — accuracy translated
  into dollars, recomputed live as new outcomes validate.
- **Frontend** — Next.js 16 (App Router) + TypeScript + TanStack Query + Recharts +
  Tailwind, in a Bloomberg-terminal-inspired dark theme. Infinite-scroll
  timeline with source / ticker / type filters, event detail with price chart,
  accuracy dashboard with baseline comparison.

---

## Quick start

### Prerequisites
- Docker Desktop (or OrbStack / Colima)
- A FRED API key — register at <https://fred.stlouisfed.org/docs/api/api_key.html> (free)
- An OpenAI **or** Anthropic API key (the analyzer is no-op without one)

### Run the backend stack

```bash
# 1. Copy env template and fill in your keys
cp backend/.env.example backend/.env
# edit backend/.env, set FRED_API_KEY, OPENAI_API_KEY (or ANTHROPIC_API_KEY),
# and SEC_USER_AGENT (must contain your email per SEC's fair-access policy)

# 2. Bring up the stack (postgres + redis + api + worker + analyzer + beat)
docker compose up --build

# 3. Browse interactive API docs
open http://localhost:8000/docs

# 4. Trigger a manual FRED fetch (otherwise beat will pick it up on its schedule)
curl -X POST http://localhost:8000/api/v1/events/_admin/trigger-fred-cpi

# 5. List events
curl http://localhost:8000/api/v1/events | jq
```

### Run the frontend

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
# open http://localhost:3000
```

### Local development (no Docker)

Useful for running tests / linters quickly.

```bash
cd backend
uv sync                       # installs deps into .venv/
uv run pytest                 # run tests
uv run ruff check .           # lint
uv run ruff format .          # format
uv run mypy app/              # type check
```

For the app itself you still need PostgreSQL + Redis running — easiest is
`docker compose up postgres redis` and then `uv run uvicorn app.main:app --reload`
locally.

---

## Architecture

```
                        ┌──────────────────┐
                        │   Celery Beat    │  (schedules only — no I/O)
                        └────────┬─────────┘
                                 │ enqueue
                                 ▼
              ┌──────────────────────────────────────┐
              │           Celery Workers              │
              │  ┌─────────┬─────────────┬─────────┐ │
              │  │ fetch_q │ analyze_q   │ valid_q │ │
              │  │ (4)     │ LLM (2)     │ (4)     │ │
              │  └─────────┴─────────────┴─────────┘ │
              │    Fetchers     Analyzer    Validator│
              └─────┬──────────────┬───────────┬─────┘
                    │              │           │
                    ▼              ▼           ▼
            ┌─────────────┐   ┌─────────┐  ┌─────────────┐
            │ PostgreSQL  │   │  Redis  │  │  yfinance   │
            │ (source of  │   │ broker  │  │  prices →   │
            │  truth)     │   │ + cache │  │  outcomes   │
            └──────┬──────┘   └─────────┘  └─────────────┘
                   │ read
                   ▼
              ┌──────────┐         ┌──────────────────┐
              │ FastAPI  │ ◀────── │  Next.js (App    │
              │ REST API │         │  Router) frontend│
              └──────────┘         └──────────────────┘

External APIs called from workers:
  • FRED, SEC EDGAR, FOMC RSS, multpl.com, yfinance
  • OpenAI / Anthropic (analyzer)
```

Full target architecture and component responsibilities live in
[EventSense_Spec.md §4](EventSense_Spec.md).

---

## Tech stack

| Layer | Tools |
|---|---|
| Language | Python 3.12 |
| Web framework | FastAPI, Uvicorn |
| ORM / DB | SQLAlchemy 2.0 (async), asyncpg, PostgreSQL 16, Alembic |
| Validation / config | Pydantic v2, pydantic-settings |
| HTTP / retries | httpx, tenacity |
| Async pipeline | Celery 5, Celery Beat, Redis 7 (broker + cache) |
| LLM | OpenAI SDK, Anthropic SDK, [instructor](https://python.useinstructor.com) |
| Scraping | BeautifulSoup4, defusedxml |
| Market data | yfinance |
| Logging | structlog |
| Frontend | Next.js 16 (App Router), TypeScript, TanStack Query, Recharts, Tailwind |
| Tooling | uv, ruff, mypy (strict), pytest, pytest-asyncio, pre-commit |
| Container | Docker, Docker Compose |
| Hosting | Railway (backend + DB + Redis), Vercel (frontend) |
| CI | GitHub Actions |

---

## Repo layout

```
.
├── backend/                  # Python app
│   ├── app/
│   │   ├── adapters/         # FRED, SEC EDGAR, FOMC, yfinance, prices, indicators
│   │   ├── api/routes/       # events, predictions, accuracy, prices, indicators, health
│   │   ├── config/           # settings, fred_series, cik_map, watchlist
│   │   ├── db/               # models, session, Base
│   │   ├── llm/              # clients, router, schemas
│   │   ├── prompts/          # event_analysis_v*.txt (versioned)
│   │   ├── schemas/          # Pydantic request/response models
│   │   ├── services/         # context_builder, alignment, etc.
│   │   ├── scripts/          # one-shot maintenance (cleanup, dedupe, purge, reset_fred, recompute_alignment)
│   │   ├── tasks/            # Celery tasks (fetcher / analyzer / validator)
│   │   └── workers/          # Celery app + beat schedule
│   ├── alembic/              # DB migrations
│   ├── tests/                # unit + integration
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── Procfile              # Railway entrypoints
├── frontend/                 # Next.js app
│   ├── app/                  # Router pages (timeline, /events/[id], /dashboard)
│   ├── components/           # EventCard, PriceChart, OutcomesTable, etc.
│   └── lib/                  # typed API client
├── docker-compose.yml
├── EventSense_Spec.md        # Engineering spec
├── IMPLEMENTATION_LOG.md     # Per-milestone notes (繁體中文)
├── LEARNING.md               # Deeper concept notes (繁體中文)
└── DEPLOYMENT.md             # Railway deploy notes
```

---

## API surface (read-mostly)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/v1/events` | Paginated; filter by `source`, `ticker`, `event_type` |
| `GET` | `/api/v1/events/filters` | Distinct sources / event types / tickers (drives the filter bar) |
| `GET` | `/api/v1/events/{id}` | Event + predictions + outcomes + context + attached docs |
| `GET` | `/api/v1/predictions/{id}` | Single prediction + outcomes |
| `GET` | `/api/v1/accuracy` | Alignment rates by source / ticker / window / kind / model, plus constant-strategy baselines and confidence calibration |
| `GET` | `/api/v1/pnl` | Simulated P&L of staking $100 on every directional call (long/short), with equity curve, SPY same-stakes benchmark, and breakdowns by window / model / ticker / confidence |
| `GET` | `/api/v1/prices/{ticker}` | Snapshots for chart rendering |
| `GET` | `/api/v1/indicators` | Macro context (CPI, DGS10/DGS2, PE, CAPE) |
| `GET` | `/api/v1/health` | Liveness check |

Interactive docs: <http://localhost:8000/docs>.

---

## Status & roadmap

| Milestone | Status |
|---|---|
| M1 — Foundation | ✅ |
| M2 — Scheduled fetching | ✅ |
| M3 — Multi-source ingestion (SEC + FOMC) | ✅ |
| M4 — Prices + earnings | ✅ |
| M5 — LLM analysis | ✅ |
| M6 — Validation loop | ✅ |
| M7 — Frontend Sprint 1 | ✅ |
| M8 — Frontend Sprint 2 + CI | ✅ |
| M9 — Deploy (Railway) | ✅ |
| M9.5 — Production hardening + analyzer overhaul | ✅ |
| M9.6 — Accuracy overhaul (release-date anchoring, per-window scoring, prompt v3 + consensus) + terminal UI | ✅ |
| M9.7 — Simulated trading P&L (`/pnl` + dashboard panel) | ✅ |
| M9.8 — Fed speeches + testimony ingestion (Board RSS feeds) | ✅ |
| M10 — Auth + watchlist | ⏳ |
| M11 — Observability (Prometheus + Grafana) | ⏳ |
| M12 — Polish + ship | ⏳ |
| M13 — AWS infrastructure (Terraform) | ⏳ |
| M14 — AWS application migration + cutover | ⏳ |
