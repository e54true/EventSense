# EventSense — Engineering Specification

> **Audience**: This document is written for an AI coding agent (e.g. Claude Code) to implement the project.
> **Scope**: Full backend + minimal frontend MVP.
> **Owner**: A new-grad backend engineer building a portfolio side project.

---

## 0. Meta-Instructions for Claude Code

When implementing this project:

1. **Work incrementally**. Implement one milestone at a time (see §11). Stop after each milestone and produce a working, demoable state before moving on.
2. **Confirm before destructive changes**. Migrations, schema drops, dependency overhauls — ask first.
3. **Prefer simple solutions**. This is a learning project; choose the simplest stack that meets the requirements. Reject over-engineering.
4. **Write tests as you go**, not at the end. Each new feature ships with at least one happy-path test and one error-path test.
5. **Commit frequently** with conventional commit messages (`feat:`, `fix:`, `chore:`, `test:`, `docs:`).
6. **Document tech decisions**. Whenever you choose between two libraries or patterns, leave a short `# DECISION:` comment explaining why.
7. **Never commit secrets**. All API keys / DB passwords go through environment variables; provide a `.env.example`.
8. **Ask the user to make these decisions yourself** rather than guessing:
   - When you find a free-tier limitation that blocks a feature
   - When library versions conflict and require a major change
   - When the spec is ambiguous about behavior

---

## 1. Project Overview

**Name**: EventSense (placeholder — user may rename)

**One-line description**: A market event analysis platform that tracks structured macro and corporate events from official US sources, uses LLMs to forecast their impact on a watchlist of US equities, and automatically validates predictions against real price movements.

**Why it matters**: Standard news aggregators stop at "here's what happened." EventSense closes the loop with `event → LLM prediction → real-world outcome → accuracy tracking`. The resulting dataset is itself the product's differentiation.

**Non-goals**:
- Not a trading platform. No real-money orders. No trading signals.
- Not a general news aggregator. Only structured official sources.
- Not a charting tool. Charts exist only to visualize predictions vs outcomes.
- Not multi-market. US equities only in MVP.

---

## 2. Glossary

| Term | Meaning |
|---|---|
| **Event** | A single discrete occurrence from an official source (e.g. one CPI release, one 8-K filing, one FOMC statement). |
| **Prediction** | An LLM-generated forecast attached to an Event for one ticker: direction + magnitude + reasoning + confidence. |
| **Outcome** | The validated result of a Prediction at a specific time window (1h / 24h / 7d) using excess return vs SPY. |
| **Alignment** | Whether the Prediction's direction matched the realized excess return sign. Boolean per (Prediction, window). |
| **Watchlist** | Per-user list of tickers they care about. Notifications and personalized views key off this. |
| **Ticker** | An equity symbol. MVP scope: `NVDA, TSLA, AAPL, MSFT, GOOGL, META, AMZN, SPY, QQQ` + 5 user-configurable. |

---

## 3. User Stories (priority-ordered)

### P0 — Must have for MVP
1. As a user, I can see a timeline of recent market events with LLM analysis attached.
2. As a user, I can click any event to see its full detail, the prediction breakdown per ticker, and the realized outcomes (if validated).
3. As a user, I can view an accuracy dashboard showing LLM alignment rate by source, by ticker, by time window.
4. As an operator, the system ingests events from FRED, SEC EDGAR, FOMC, and earnings calendars on a schedule without manual intervention.
5. As an operator, the system automatically validates each prediction at the 1h / 24h / 7d windows.

### P1 — Important
6. As a user, I can sign up, log in, and configure a personal watchlist.
7. As a user, I receive a notification (in-app or email) when an event affects a ticker on my watchlist.
8. As an operator, I can view system health metrics (Prometheus + Grafana).

### P2 — Nice to have (skip if behind schedule)
9. As a user, I can compare two LLM models' accuracy side-by-side.
10. As a user, I can see "similar past events" for context.

---

## 4. Architecture

```
                       ┌──────────────────┐
                       │  Celery Beat     │   (scheduler)
                       └────────┬─────────┘
                                │ enqueue scheduled tasks
                                ▼
              ┌────────────────────────────────────┐
              │       Celery Workers (pool)         │
              │  - Fetcher  (FRED, SEC, FOMC, yf)  │
              │  - Analyzer (LLM prompt + parse)    │
              │  - Validator (price → outcome)      │
              └─────┬──────────────────────┬───────┘
                    │ read/write           │ broker
                    ▼                      ▼
            ┌──────────────┐       ┌──────────────┐
            │  PostgreSQL   │       │    Redis      │
            │  (primary DB) │       │  - broker     │
            │               │       │  - price cache│
            │               │       │  - rate limit │
            └──────┬────────┘       └───────────────┘
                   │ read
                   ▼
            ┌──────────────┐
            │   FastAPI     │   (REST + WebSocket)
            └──────┬────────┘
                   │ HTTP
                   ▼
            ┌──────────────┐
            │   Next.js     │   (App Router, server components)
            └──────────────┘

External APIs called by workers:
  • FRED API           (st. louis Fed economic data)
  • SEC EDGAR API      (corporate 8-K filings)
  • Fed FOMC RSS       (rate decisions)
  • yfinance (lib)     (prices, earnings calendar)
  • OpenAI / Anthropic (LLM analysis)
```

### Component responsibilities

- **Celery Beat** owns schedules only. It does not make HTTP calls itself.
- **Celery Workers** do all I/O and computation. They must be idempotent.
- **FastAPI** is read-mostly. The only write operations from the API are user actions (signup, watchlist edit). All event ingestion is worker-driven.
- **PostgreSQL** is the source of truth. Pipeline state lives in row status fields (DB-driven state machine, not Celery chain).
- **Redis** is broker + ephemeral cache. Never the source of truth for anything.

---

## 5. Tech Stack (locked-in)

```
Language:        Python 3.11+
Backend:         FastAPI 0.110+, SQLAlchemy 2.0 (async), Pydantic v2, Alembic
Async:           Celery 5.x + Celery Beat, Redis 7.x (broker)
Database:        PostgreSQL 16
HTTP client:     httpx (async)
LLM client:      openai >= 1.x, anthropic SDK, use `instructor` for structured output
Validation:      Pydantic v2 for both API and LLM output
Logging:         structlog
Metrics:         prometheus-fastapi-instrumentator
Testing:         pytest, pytest-asyncio, httpx (test client), factory-boy
DevOps:          Docker, docker-compose, GitHub Actions
Frontend:        Next.js 14 (App Router), TypeScript, Tailwind, shadcn/ui,
                 TanStack Query, Recharts
Auth:            JWT (python-jose), OAuth2 password flow
Deployment:      Railway (MVP, W9) → AWS ECS Fargate + RDS + ElastiCache (W13–W14)
                 Frontend stays on Vercel throughout
IaC:             Terraform (for AWS migration, state in S3 + DynamoDB lock)
```

**Forbidden / explicitly not used**:
- ❌ Django / Flask (FastAPI only)
- ❌ MongoDB (PostgreSQL only)
- ❌ Synchronous SQLAlchemy 1.x patterns
- ❌ `requests` library (use httpx)
- ❌ celery `chain()` style — use DB-driven state machine instead
- ❌ Hardcoded API keys anywhere

---

## 6. Data Model

All tables use `created_at` and `updated_at` timestamps. Use SQLAlchemy 2.0 `DeclarativeBase` style with `Mapped[]` annotations.

### 6.1 `events`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| source | enum | `FRED`, `SEC_EDGAR`, `FOMC`, `EARNINGS` |
| event_type | varchar | e.g. `CPI_RELEASE`, `8K_FILING`, `FOMC_STATEMENT`, `EARNINGS_REPORT` |
| external_id | varchar | Source's native ID (FRED series ID + date, SEC accession, etc.) Used for dedup. |
| title | varchar(500) | Human-readable headline |
| payload | JSONB | Full structured event data (varies by source) |
| affected_tickers | varchar[] | Tickers we identify as potentially affected |
| published_at | timestamptz | When the event was actually published by the source |
| fetched_at | timestamptz | When we first saw it |
| status | enum | `FETCHED`, `ANALYZED`, `FAILED`, `IGNORED` |
| failure_reason | text nullable | If status=FAILED |

**Unique constraint**: `(source, external_id)`

### 6.2 `predictions`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| event_id | UUID FK → events.id | |
| ticker | varchar(10) | |
| direction | enum | `BULLISH`, `BEARISH`, `NEUTRAL` |
| magnitude | enum | `LOW`, `MEDIUM`, `HIGH` |
| confidence | float | 0.0–1.0 (LLM self-reported) |
| reasoning | text | LLM's free-text justification |
| llm_provider | varchar | `openai`, `anthropic` |
| llm_model | varchar | e.g. `gpt-4o-mini`, `claude-sonnet-4-5` |
| prompt_version | varchar | e.g. `v1`, `v2`. Increment whenever prompt changes. |
| predicted_at | timestamptz | |

### 6.3 `price_snapshots`

| Column | Type | Notes |
|---|---|---|
| id | bigint PK | |
| ticker | varchar(10) | |
| snapshot_at | timestamptz | |
| price | numeric(12,4) | |
| source | varchar | `yfinance` |

**Index**: `(ticker, snapshot_at DESC)`
Consider partitioning by month if rows exceed ~10M. Not needed for MVP.

### 6.4 `prediction_outcomes`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| prediction_id | UUID FK → predictions.id | |
| window | enum | `1h`, `24h`, `7d` |
| baseline_price | numeric(12,4) | Price at prediction time |
| end_price | numeric(12,4) | Price at end of window |
| ticker_return | float | (end - baseline) / baseline |
| spy_return | float | Same calc on SPY |
| excess_return | float | ticker_return - spy_return |
| aligned | boolean | True if sign(excess_return) matches prediction direction (NEUTRAL only aligns if |excess| < 0.5%) |
| validated_at | timestamptz | |

**Unique constraint**: `(prediction_id, window)`

### 6.5 `users`

Standard: id, email (unique), hashed_password, created_at, is_active.

### 6.6 `watchlists`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK | |
| ticker | varchar(10) | |

**Unique constraint**: `(user_id, ticker)`

### 6.7 `notifications`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK | |
| event_id | UUID FK | |
| channel | enum | `IN_APP`, `EMAIL` |
| sent_at | timestamptz nullable | |
| read_at | timestamptz nullable | |

---

## 7. External Source Adapters

Each source has its own adapter module under `app/adapters/`. Adapters must:
- Have a single `fetch_new() -> list[RawEvent]` method
- Be **idempotent** (calling twice does not duplicate)
- Use the `external_id` + DB unique constraint for dedup
- Implement exponential backoff retry (use `tenacity`)
- Log structured events: `source.fetch.started`, `source.fetch.completed`, `source.fetch.failed`

### 7.1 FRED Adapter
- Requires `FRED_API_KEY` env var
- Fetch a curated list of series IDs: `CPIAUCSL` (CPI), `UNRATE` (unemployment), `FEDFUNDS` (Fed funds rate), `GDP`, `PCE`, etc. Define list in `app/config/fred_series.py`.
- Each new release of a series creates one event with `event_type=ECONOMIC_RELEASE`.
- Payload: `{series_id, series_name, value, previous_value, release_date}`
- Schedule: hourly poll. Real releases are infrequent (monthly), so most polls find nothing.

### 7.2 SEC EDGAR Adapter
- No API key, but **mandatory** custom `User-Agent` (`"EventSense your-email@example.com"`)
- Use `https://data.sec.gov/submissions/CIK{cik}.json` for each watchlist company
- Filter to 8-K filings (form type `8-K`)
- Payload: `{cik, ticker, accession_number, filing_date, item_codes, primary_doc_url}`
- Tickers ↔ CIK mapping: maintain a static `app/config/cik_map.py`
- Schedule: every 15 minutes
- Respect SEC's [fair access guidelines](https://www.sec.gov/os/accessing-edgar-data): max 10 req/sec, identify yourself

### 7.3 FOMC Adapter
- Source: Fed's calendar page + RSS for statements
- Poll daily at minimum; on known FOMC decision days, poll every 5 minutes during decision window (typically 2:00–2:30 PM ET)
- Payload: `{statement_text, decision_date, rate_change_bps}`

### 7.4 Earnings Adapter
- Use `yfinance.Ticker(symbol).calendar` to get next earnings date for watchlist tickers
- After earnings is announced, fetch the actual EPS / revenue from `yfinance.Ticker(symbol).earnings_history`
- Create event with `event_type=EARNINGS_REPORT`
- Schedule: daily check for upcoming, hourly check on earnings day

### 7.5 Price Adapter (not really "events" but feeds validator)
- `yfinance` library
- Two cadences:
  - **Recent prices**: every 5 min during market hours (9:30 AM – 4:00 PM ET, Mon–Fri), fetch 1-min bars for all watchlist tickers + SPY
  - **Backfill**: on first deploy, fetch 1 year of daily history per ticker
- **Aggressive Redis caching**: cache latest price per ticker for 60s to avoid hammering yfinance
- yfinance is unofficial; handle `Exception` broadly and retry with backoff

---

## 8. Pipeline (DB-driven state machine)

### Lifecycle of one Event

```
[Fetcher creates row]
  status = FETCHED
       │
       ▼
[Analyzer worker picks up FETCHED rows]
  → Call LLM, create N predictions (one per affected ticker)
  → Update status = ANALYZED (or FAILED with reason)
       │
       ▼
[Validator schedules outcome checks]
  → For each prediction, schedule eta-based tasks at +1h, +24h, +7d
  → Each task computes excess return, writes outcome row
```

### Worker design

Each worker type has its own Celery queue:
- `fetch_queue` — fetcher tasks, IO-bound, can have high concurrency
- `analyze_queue` — LLM calls, rate-limited externally, lower concurrency (5–10 workers)
- `validate_queue` — price-fetch + DB write, IO-bound

### Idempotency rules

- Fetcher: deduplicates via `(source, external_id)` unique constraint. Catches `IntegrityError`, returns "no-op".
- Analyzer: only processes rows where `status = FETCHED`. Wraps work in DB transaction. If LLM call fails, rolls back and leaves status unchanged (will be retried).
- Validator: outcome row unique on `(prediction_id, window)`. If row already exists, no-op.

### Retry policy

Use Celery's `autoretry_for=(httpx.HTTPError, openai.RateLimitError)`, `retry_backoff=True`, `retry_kwargs={'max_retries': 5}`.

---

## 9. LLM Integration

### Prompt structure

Use `instructor` library for structured output. Define a Pydantic schema:

```python
class TickerImpact(BaseModel):
    ticker: str
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    magnitude: Literal["LOW", "MEDIUM", "HIGH"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(max_length=500)

class EventAnalysis(BaseModel):
    summary: str = Field(max_length=200)
    impacts: list[TickerImpact]
```

### Prompt template

Stored in `app/prompts/event_analysis_v1.txt`. Versioned. When changing, bump version and store both, so old predictions retain their original prompt version.

The prompt must:
- Provide the event payload as structured JSON, not paraphrased
- List the watchlist tickers
- Instruct: "If the event has no plausible impact on a ticker, do NOT include it in impacts. Only return tickers with a defensible thesis."
- Instruct: "Confidence should reflect how certain you are about direction, not magnitude."
- Limit reasoning to one sentence per ticker

### Model selection

- `gpt-4o-mini` for routine events (most CPI, most 8-K)
- `gpt-4o` or `claude-sonnet-4-5` for high-stakes events (FOMC decisions, surprise data prints)
- Decision logic in `app/llm/router.py`. Start simple: hardcoded "if event_type == FOMC_STATEMENT use big model"

### Cost guardrails

- Track per-event LLM cost in `predictions` table (add `llm_cost_usd` column)
- Daily cost cap as env var; if exceeded, downgrade all to `gpt-4o-mini` and log warning

---

## 10. REST API

Base path: `/api/v1`

### Public endpoints (no auth)

| Method | Path | Description |
|---|---|---|
| GET | `/events` | List events, paginated. Filters: `source`, `ticker`, `since`, `until` |
| GET | `/events/{id}` | Single event with predictions and outcomes |
| GET | `/predictions/{id}` | Single prediction with all its outcomes |
| GET | `/accuracy` | Aggregate alignment rates. Filters: `source`, `ticker`, `window`, `model` |
| GET | `/tickers` | List of supported tickers |
| GET | `/health` | Liveness check, returns `{status: "ok", version, uptime_s}` |
| GET | `/metrics` | Prometheus format (separate port in prod) |

### Authenticated endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/auth/signup` | email + password |
| POST | `/auth/login` | returns JWT |
| GET | `/users/me` | current user |
| GET | `/watchlist` | current user's watchlist |
| POST | `/watchlist` | add ticker `{ticker}` |
| DELETE | `/watchlist/{ticker}` | remove |
| GET | `/notifications` | user's notifications, paginated |
| PATCH | `/notifications/{id}/read` | mark read |
| WS | `/ws/notifications` | live push (use FastAPI WebSocket) |

### Response shapes

All responses follow:
```json
{
  "data": <payload>,
  "meta": { "page": 1, "per_page": 20, "total": 137 }
}
```

Errors follow:
```json
{
  "error": { "code": "TICKER_NOT_FOUND", "message": "Human-readable" }
}
```

### Pagination

Cursor-based for `/events` (high volume), offset-based elsewhere is fine.

### Rate limiting

Per IP for unauth endpoints: 60 req/min. Per user for auth: 300 req/min. Use `slowapi`.

---

## 11. Implementation Milestones

Each milestone ends in a working, demoable state. **Do not start the next milestone until the previous is committed, tested, and the user has confirmed.**

### Milestone 1 — Foundation (W1)
- Project scaffolding: poetry/uv, ruff, black, mypy, pre-commit hooks
- `docker-compose.yml` with FastAPI + PostgreSQL + Redis (no Celery yet)
- SQLAlchemy 2.0 async setup, Alembic configured, `events` table migration
- FRED adapter: single function `fetch_cpi()` that hits FRED, parses, inserts
- One endpoint: `GET /events` (list, no filters yet)
- README with setup instructions
- **Acceptance**: `docker compose up` runs cleanly; `curl localhost:8000/api/v1/events` returns FRED CPI data after manual trigger

### Milestone 2 — Scheduled fetching (W2)
- Add Celery worker + Beat to docker-compose
- Convert FRED fetcher to Celery task
- Schedule: hourly fetch
- Structlog configured
- Retries with tenacity
- Tests: fetcher idempotency, schema validation
- **Acceptance**: leave system running 2 hours unattended; new FRED data appears without manual triggers

### Milestone 3 — Multi-source ingestion (W3)
- Add SEC EDGAR adapter
- Add FOMC adapter
- Unified `RawEvent` Pydantic schema all adapters return
- CIK map in config
- Tests for each adapter (mock HTTP responses)
- **Acceptance**: All three sources running on schedule; events table contains data from all three

### Milestone 4 — Prices + earnings (W4)
- yfinance integration
- Earnings adapter
- `price_snapshots` table + writer worker
- Backfill script for 1 year of daily prices
- Redis cache for latest price (60s TTL)
- **Acceptance**: SPY + watchlist tickers have populated `price_snapshots`; latest-price endpoint returns cached value

### Milestone 5 — LLM analysis (W5)
- OpenAI + Anthropic clients
- `instructor` for structured output
- Prompt template v1
- Analyzer worker: picks up `FETCHED` events, produces predictions
- Model router (simple version)
- Cost tracking
- **Acceptance**: every new event automatically gets predictions within 2 minutes; `/predictions/{id}` returns structured data

### Milestone 6 — Validation loop (W6)
- Validator worker
- `prediction_outcomes` table
- Schedule outcomes at +1h, +24h, +7d using Celery ETA
- Excess return calculation (vs SPY)
- Alignment logic with neutral threshold
- `GET /accuracy` endpoint
- **Acceptance**: predictions made yesterday now have 24h outcomes with valid excess_return calculations

### Milestone 7 — Frontend Sprint 1 (W7)
- Next.js 14 App Router scaffolding
- shadcn/ui setup
- TanStack Query for API calls
- `/` page: timeline of events
- `/events/[id]` page: event detail with predictions
- Type-safe API client (OpenAPI generated or hand-written types)
- **Acceptance**: can browse events from a browser; predictions render cleanly

### Milestone 8 — Frontend Sprint 2 + tests + CI (W8)
- Recharts price chart with prediction markers on `/events/[id]`
- `/dashboard` page: aggregate accuracy stats
- pytest coverage > 75% on backend (skip the obvious paths, focus on pipeline correctness)
- GitHub Actions: ruff + mypy + pytest on PR
- **Acceptance**: green CI; coverage report committed; dashboard loads with real data

### Milestone 9 — Deploy (W9)
- Multi-stage Dockerfiles
- Deploy backend + workers to Railway
- Deploy frontend to Vercel
- Managed PostgreSQL + Redis (Railway addons)
- Environment variable management
- Health checks + UptimeRobot
- **Acceptance**: production URL accessible from anywhere; system runs unattended for 48 hours without manual intervention

### Milestone 10 — Auth + watchlist (W10)
- User signup + JWT login
- `/watchlist` CRUD
- Notification generation when watchlist ticker is affected
- WebSocket push for in-app notifications
- Email via SendGrid (or skip, in-app only)
- **Acceptance**: two browser sessions with different users see different personalized timelines

### Milestone 11 — Observability (W11)
- Prometheus metrics endpoint
- Grafana dashboard JSON committed to repo
- Custom metrics: events ingested per source, LLM latency p50/p95, prediction count, daily LLM cost
- Structured logging review
- Graceful degradation for market-closed hours
- **Acceptance**: Grafana shows last 24h activity at a glance

### Milestone 12 — Polish + ship (Railway version) (W12)
- README with architecture diagram (use Mermaid or commit a PNG)
- 3-minute Loom demo recorded (Railway-hosted version)
- Resume bullet drafted in repo
- One blog post draft on "what I learned"
- Final pass: dead code removal, dependency audit, `.env.example` complete
- **Acceptance**: a stranger could clone, follow README, and have it running in 15 minutes. Railway production URL stable for ≥7 days.

### Milestone 13 — AWS Infrastructure as Code (W13)

Goal: stand up the empty AWS environment via Terraform. No app code deployed yet — this milestone is purely infra. Treat it as a separate showcase artifact: a clean `infra/` directory that could be reviewed independently of the application code.

- `infra/` directory at repo root with Terraform 1.6+
- Remote state: S3 bucket + DynamoDB table for state locking (bootstrap by hand or via a separate `infra/bootstrap/` module)
- Module structure: `network/`, `data/`, `compute/`, `iam/`, `observability/` — each a reusable module, root `main.tf` wires them together per environment (`envs/staging/`, `envs/prod/`)
- **Networking**: VPC across 2 AZs, public + private subnets, IGW, single NAT gateway (cost-conscious; document tradeoff vs HA NAT in an ADR)
- **Data**:
  - RDS PostgreSQL 16 in private subnets, `db.t4g.micro`, single-AZ for MVP (multi-AZ noted as future)
  - ElastiCache Redis 7, `cache.t4g.micro`, single node
  - Both reachable only from ECS security group
- **Compute**:
  - ECR repositories: `eventsense-api`, `eventsense-worker`
  - ECS Fargate cluster
  - Task definitions for `api`, `worker`, `beat` (Beat runs as a single-replica service — explicit comment about why we can't horizontally scale Beat)
  - ALB in public subnets, HTTPS via ACM cert, target group → API service
- **Secrets**: AWS Secrets Manager entries for `DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `FRED_API_KEY`, `SECRET_KEY`. Task definitions reference via `secrets:` block (not env)
- **IAM**: least-privilege task execution role + task role; separate role per service if permissions diverge
- **Observability**: CloudWatch log groups per service, 30-day retention
- **CI/CD prep**: GitHub Actions OIDC provider + deploy role (no long-lived AWS keys in GitHub secrets)
- **DNS**: Route 53 hosted zone + ACM cert in us-east-1 (or ALB region); decide on subdomain (e.g. `api.eventsense.dev`)
- One ADR: "Why Terraform over CDK" + "Why ECS Fargate over EKS/App Runner/EC2"
- **Acceptance**: `terraform apply` from scratch brings up all infra cleanly; ECR repos exist and accept pushes; RDS reachable from an ECS exec session; ALB returns 503 (no targets yet) on the public DNS name. `terraform destroy` cleans everything up. Frontend (Vercel) and Railway production are untouched.

### Milestone 14 — AWS Application Migration + Cutover (W14)

Goal: move the live application from Railway to AWS with zero data loss, then decommission Railway. This is the milestone where you can claim "migrated a production system between cloud providers" on your resume.

- **Container hardening**: multi-stage Dockerfile review, non-root user, distroless or slim base, image size <300MB target
- **GitHub Actions deploy pipeline**:
  - On push to `main`: build images, push to ECR with both `latest` and commit SHA tags
  - Update ECS service via `aws ecs update-service` with `--force-new-deployment`
  - Wait for rolling deploy, fail the job if tasks don't become healthy
  - Run Alembic migrations as a one-shot ECS task before service update
- **Data migration**:
  - `pg_dump` from Railway PostgreSQL, restore to RDS
  - Verify row counts per table match
  - Run Alembic `current` against RDS to confirm schema parity
  - Redis is ephemeral — no migration needed, just let cache rebuild
- **Cutover sequence** (document in `docs/cutover-runbook.md`):
  1. Put Railway in "drain" mode (stop Celery Beat to prevent new fetches)
  2. Final `pg_dump` → restore to RDS
  3. Start AWS ECS services, verify health
  4. Update Vercel env var `NEXT_PUBLIC_API_URL` to AWS ALB DNS
  5. Update Route 53 if using custom domain
  6. Smoke test: create user, view events, trigger manual fetch
  7. Monitor CloudWatch for 24h
- **Decommission**: only after 48h of stable AWS operation, tear down Railway services (keep DB snapshot for 30 days as rollback insurance)
- **Docs update**: README gains an "Architecture (AWS)" section with infra diagram; deployment instructions cover both Railway (dev/learning) and AWS (production) paths
- **Resume/blog update**: extend the "what I learned" post with a "Migrating to AWS" section covering Terraform tradeoffs, ECS Fargate vs alternatives, cost comparison (Railway $X/mo vs AWS $Y/mo)
- One ADR: "Railway → AWS migration: motivation, approach, lessons"
- **Acceptance**: production traffic served from AWS ALB; Vercel frontend pointing to AWS; Railway services stopped (DB snapshot retained); system runs unattended for ≥7 days post-cutover with no manual intervention; cutover runbook is detailed enough that someone else could execute it.

---

## 12. Repository Layout

```
eventsense/
├── backend/
│   ├── app/
│   │   ├── adapters/          # FRED, SEC, FOMC, yfinance, prices
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   └── deps.py
│   │   ├── config/            # settings, cik_map, fred_series
│   │   ├── db/
│   │   │   ├── models.py
│   │   │   └── session.py
│   │   ├── llm/
│   │   │   ├── clients.py
│   │   │   ├── router.py
│   │   │   └── schemas.py
│   │   ├── prompts/
│   │   │   └── event_analysis_v1.txt
│   │   ├── schemas/           # Pydantic request/response
│   │   ├── tasks/             # Celery tasks (fetcher, analyzer, validator)
│   │   ├── workers/           # Celery app, beat schedule
│   │   ├── main.py            # FastAPI entrypoint
│   │   └── celery_app.py
│   ├── alembic/
│   ├── tests/
│   │   ├── unit/
│   │   └── integration/
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── app/
│   │   ├── page.tsx           # Timeline
│   │   ├── events/[id]/page.tsx
│   │   ├── dashboard/page.tsx
│   │   └── layout.tsx
│   ├── components/
│   │   └── ui/                # shadcn components
│   ├── lib/
│   │   └── api.ts             # Typed API client
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── infra/                     # Terraform (Milestone 13–14)
│   ├── bootstrap/             # one-time: S3 state bucket + DynamoDB lock
│   ├── modules/
│   │   ├── network/           # VPC, subnets, NAT, security groups
│   │   ├── data/              # RDS, ElastiCache
│   │   ├── compute/           # ECS cluster, services, ALB, ECR
│   │   ├── iam/               # task roles, GitHub OIDC role
│   │   └── observability/     # CloudWatch log groups
│   └── envs/
│       ├── staging/
│       └── prod/
├── .github/
│   └── workflows/
│       ├── backend-ci.yml
│       ├── frontend-ci.yml
│       ├── terraform-plan.yml # plan on PR (Milestone 13)
│       └── deploy-aws.yml     # build → ECR → ECS (Milestone 14)
├── docs/
│   ├── architecture.md
│   ├── cutover-runbook.md     # Milestone 14
│   └── decisions/             # ADR-style decision records
└── README.md
```

---

## 13. Configuration

All configuration via `pydantic-settings`. Required env vars:

```
# Backend
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/eventsense
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=<random 32 bytes>
ENVIRONMENT=development|staging|production

# External APIs
FRED_API_KEY=...
SEC_USER_AGENT="EventSense your-email@example.com"
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
SENDGRID_API_KEY=...   # optional

# LLM
LLM_DAILY_COST_CAP_USD=5.00
LLM_DEFAULT_MODEL=gpt-4o-mini
LLM_PREMIUM_MODEL=gpt-4o

# Watchlist
DEFAULT_TICKERS=NVDA,TSLA,AAPL,MSFT,GOOGL,META,AMZN,SPY,QQQ
```

---

## 14. Testing Strategy

### Unit tests (fast, no I/O)
- Adapter parsing logic (feed it raw API response fixtures)
- LLM output validation (Pydantic schemas)
- Alignment / excess return math
- Prompt construction

### Integration tests (DB + Redis, no external HTTP)
- Mock external APIs with `httpx-mock` or `pytest-httpx`
- Mock LLM calls with recorded fixtures (`vcr.py` or similar)
- Test full pipeline: fake event → fake LLM response → outcome calc

### End-to-end smoke (optional, manual)
- A `scripts/smoke.sh` that runs against a fresh docker-compose, hits real FRED with a known series, verifies the row appears

### Coverage targets
- Backend overall: 75%
- `app/adapters/`: 90% (this is the most error-prone code)
- `app/api/`: 80%

---

## 15. Performance & Scale Expectations (MVP)

- **Events per day**: 5–50 (very low volume by design)
- **Predictions per day**: 20–200 (each event spawns 1–10 ticker predictions)
- **Price snapshots per day**: ~100k (14 tickers × every minute × 6.5 hours)
- **Concurrent users**: <50 (friends + interviewers)
- **API p95 latency target**: <300ms for cached endpoints, <1s for non-cached
- **LLM analysis end-to-end SLA**: <2 minutes from event detection to prediction stored

No need to optimize for more than this. Don't add caching, partitioning, or read replicas speculatively.

---

## 16. Security

- Never log API keys, JWTs, or password fields
- Bcrypt for password hashing (`passlib[bcrypt]`)
- JWT expiry: 1 hour access, 30 day refresh
- CORS: explicit allowlist, no `*` in production
- SQL: only parameterized via SQLAlchemy, no raw string interpolation
- LLM output is text only — never `eval()` it, never pass to shell
- No PII collected beyond email
- `.env` in `.gitignore`, secrets via Railway secret store in prod

---

## 17. Out-of-Scope Reminders

To prevent scope creep, these are explicitly excluded from MVP. **Do not implement them even if they seem easy.**

- Multi-language support (English only)
- Mobile-responsive design (desktop only for demo)
- Social features (sharing, comments, likes)
- Advanced charting (only basic line + markers)
- Trading signal generation
- Backtesting framework
- Multiple market support (US only)
- Crypto / commodities
- Real-time WebSocket price streaming (5-min polling is fine)
- LLM fine-tuning (use API)
- Vector search / RAG (NOT in MVP; user explicitly deferred Table-QA integration)
- A/B testing framework
- Admin UI

---

## 18. Definition of Done (overall project)

- [ ] All P0 user stories work end-to-end against the deployed URL
- [ ] System has been running unattended for ≥7 days with new events appearing
- [ ] ≥75% backend test coverage, all tests green in CI
- [ ] README has: setup instructions, architecture diagram, demo video link, tech decisions section
- [ ] At least 100 commits with meaningful messages
- [ ] `.env.example` is complete; cloning + filling env vars + `docker compose up` works in <15 min
- [ ] One ADR (Architecture Decision Record) written for each major tech choice

---

## 19. When Asking the User for Decisions

These are decisions the agent should ask the user about, not silently choose:

1. **API quota exhausted**: if a free tier blocks progress, ask before paying.
2. **LLM provider preference** beyond what's specified
3. **Renaming** the project from "EventSense"
4. **Schema changes** after Milestone 4 (data exists, migrations are riskier)
5. **Adding dependencies** beyond what's listed in §5 — justify in a comment, then ask
6. **Skipping a milestone** to catch up on schedule
7. **Deployment provider change** beyond the planned Railway (W9) → AWS (W13–W14) path — e.g. switching to GCP, dropping Railway before W14, or changing the AWS compute target away from ECS Fargate

---

## 20. References

- FRED API docs: https://fred.stlouisfed.org/docs/api/fred/
- SEC EDGAR API: https://www.sec.gov/edgar/sec-api-documentation
- yfinance: https://github.com/ranaroussi/yfinance
- FastAPI: https://fastapi.tiangolo.com
- SQLAlchemy 2.0: https://docs.sqlalchemy.org/en/20/orm/quickstart.html
- Celery: https://docs.celeryq.dev
- instructor: https://python.useinstructor.com
- shadcn/ui: https://ui.shadcn.com
- Railway: https://docs.railway.app

---

**End of specification.**
