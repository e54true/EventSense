# EventSense 實作筆記 (Implementation Log)

> **用途**:這份文件記錄 EventSense 開發過程中**每個 milestone 做了什麼、為什麼這樣選**,目的是讓我未來複習、為面試做準備。
> **語言**:繁體中文,專有名詞 / 程式碼保持英文。
> **閱讀順序**:可以從頭讀,也可以針對特定 milestone 跳讀。每個 milestone 都是獨立完整的章節。
> **配套文件**:[EventSense_Spec.md](EventSense_Spec.md) 是工程規格(寫給 AI agent 看的),本文件是「我學到了什麼」的人類筆記。

---

## 目錄

- [全局技術決策](#全局技術決策)
- [Milestone 1 — Foundation](#milestone-1--foundation)
- [Milestone 2 — Scheduled fetching](#milestone-2--scheduled-fetching)
- [Milestone 3 — Multi-source ingestion](#milestone-3--multi-source-ingestion)
- [Milestone 4 — Prices + earnings](#milestone-4--prices--earnings)
- [Milestone 5 — LLM analysis](#milestone-5--llm-analysis)
- [Milestone 6 — Validation loop](#milestone-6--validation-loop)
- [Milestone 7 — Frontend Sprint 1](#milestone-7--frontend-sprint-1)
- [Milestone 8 — Frontend Sprint 2 + tests + CI](#milestone-8--frontend-sprint-2--tests--ci)
- [Milestone 9 — Deploy (Railway)](#milestone-9--deploy-railway)
- [Milestone 9.5 — Production hardening + analyzer overhaul](#milestone-95--production-hardening--analyzer-overhaul)
- [Milestone 9.6 — Accuracy overhaul + terminal UI](#milestone-96--accuracy-overhaul--terminal-ui)
- [Milestone 10 — Auth + watchlist](#milestone-10--auth--watchlist)
- [Milestone 11 — Observability](#milestone-11--observability)
- [Milestone 12 — Polish + ship](#milestone-12--polish--ship)
- [Milestone 13 — AWS Infrastructure as Code](#milestone-13--aws-infrastructure-as-code)
- [Milestone 14 — AWS Application Migration + Cutover](#milestone-14--aws-application-migration--cutover)
- [常見面試問題整理](#常見面試問題整理)

---

## 全局技術決策

這一節記錄「整個專案層級」的技術選型,不屬於任何單一 milestone。每個 milestone 的局部決策寫在該 milestone 區段裡。

### 為什麼選 FastAPI(而不是 Django / Flask)?

- **原生 async**:FastAPI 基於 ASGI,所有 endpoint 預設 async,適合大量 I/O bound 工作(打外部 API、查 DB)。Django(WSGI)和 Flask 雖然有 async 支援但是 retrofit,效能和生態都比較差。
- **自帶 OpenAPI / Swagger UI**:可以自動產生 API 文件,前端可以用 OpenAPI codegen 生 TypeScript client。
- **Pydantic 整合**:request / response 都用 Pydantic schema 驗證,型別安全度高。
- **學習價值**:FastAPI 是 2020 年後 Python 後端的標配,履歷上比 Flask 加分。

### 為什麼選 SQLAlchemy 2.0 async(而不是 ORM-less 或 1.x)?

- **`Mapped[]` annotation 風格**:2.0 引入的新語法和 Python type system 整合更好,IDE 支援更強。
- **Async support**:跟 FastAPI 的 async 一致,可以一路 `await` 到底,不會在 sync ORM 上被卡住。
- **避免 N+1**:用 `selectinload` / `joinedload` 可以宣告式處理 eager loading。
- **不選 ORM-less(如 asyncpg + raw SQL)**:對 portfolio 專案來說 ORM 帶來的開發速度比手刻 SQL 重要。

### 為什麼選 PostgreSQL(而不是 MongoDB / MySQL)?

- **JSONB 支援**:`events.payload` 欄位用 JSONB 存各種 source 的原始資料,既有 schema-flexible 的好處又能 index。
- **強型別 + Transaction**:預測準確率追蹤是 financial-adjacent 應用,ACID 不可少。
- **Pgvector 等擴充**:未來如果要做 similar events 比對,可以無痛加 vector search。
- **MongoDB 在這個情境完全沒有優勢**:我們的資料是高度結構化的(events, predictions, outcomes 之間有 FK 關係)。

### 為什麼選 Celery(而不是 RQ / Dramatiq / arq)?

- **生態最成熟**:Beat scheduler、retry policy、queue 路由、結果存取都很完整。
- **可以分多個 queue**:fetch / analyze / validate 三個 queue 用不同的 worker pool,避免慢的 LLM call 阻塞快的 fetch task。
- **缺點承認**:Celery 設定複雜、文件雜亂、對 async 的支援不算原生。但是這些缺點不足以換掉它。
- **不用 `chain()`**:雖然 Celery 提供 chain,但我們改用 **DB-driven state machine**(用 `events.status` 欄位來決定下一步做什麼),這樣 worker 重啟、failure 都不會丟掉狀態。

### 為什麼選 uv(而不是 poetry / pip-tools)?

- **速度**:比 poetry 快 10-100 倍。在 CI 和 Docker build 階段差異很明顯。
- **單一 binary**:不依賴 Python 本身就能 install,避免「我要先有 Python 才能裝 Python 套件管理工具」的雞蛋問題。
- **統一工具**:`uv` 一個工具搞定 venv、套件、Python 版本管理(取代 pyenv + poetry + virtualenv 三個)。
- **`uv.lock` 是 cross-platform 的**:不像 `requirements.txt` 需要分平台。
- **缺點承認**:相對較新(2024),招聘 JD 上點名 poetry 的還是多一些。但 uv 是 ruff 作者 Astral 出的,生態快速壯大。

### 為什麼選 Docker Compose 開發 + Railway/AWS 部署?

- **本地一致性**:`docker compose up` 一條指令拉起 FastAPI + Postgres + Redis,新人 onboard 五分鐘搞定。
- **production parity**:本地跑的 PG 版本和 production 一樣,避免「本地用 sqlite, prod 用 postgres」的 schema 差異 bug。
- **Railway 適合 MVP**:不用設定 VPC / IAM / ALB,直接 `git push` 上線。
- **AWS 適合最終展示**:Milestone 13-14 會用 Terraform 把整套搬到 ECS Fargate + RDS,展示 infra 能力。

### 開發環境 vs 容器環境的分工

| | 本地 venv(`.venv/`) | Docker container |
|---|---|---|
| **誰用** | IDE、`pytest`、`ruff`、`mypy`、pre-commit hook | 實際跑 API、worker、連 DB |
| **何時用** | 寫 code 的時候(秒級回饋) | `docker compose up` 跑整個 stack |
| **共用** | 同一份 `pyproject.toml` / `uv.lock`,版本一致 | |

兩者不衝突 — venv 是給 IDE 和 linter 用的;Docker 是給「跑得起來」用的。

---

## Milestone 1 — Foundation

> **狀態**:✅ 完成(等 FRED API key 後跑端對端測試)
> **目標**:建立專案 scaffolding,讓 `docker compose up` 起得來,有一個 `GET /api/v1/events` 能撈出 FRED CPI 資料的端點。

### 做了什麼(依檔案分類)

#### 工具與環境
- **`brew install uv`**:`uv` 是 Astral(出 `ruff` 的同一家公司)的新一代 Python 套件管理器,取代 `pip + virtualenv + pyenv + poetry`。安裝速度比 poetry 快 10-100 倍。
- **`brew install --cask docker-desktop`**:Mac 上跑容器的 runtime。安裝時遇到舊版殘留的死掉 symlink(`/usr/local/bin/docker` 等),清掉重裝才成功。

#### 專案根層級
- **[.gitignore](.gitignore)**:忽略 `.venv/`、`__pycache__/`、`.env`、`.terraform/` 等。
- **[README.md](README.md)**:Quick start、架構圖、repo 結構。
- **[docker-compose.yml](docker-compose.yml)**:三個 service:`postgres`、`redis`、`backend`。
  - Postgres / Redis 加 `healthcheck` → backend `depends_on: condition: service_healthy` 才會等到 DB 真正 ready 再啟動,避免「DB 還沒 init 完就 connect 失敗」的競態。
  - Backend 用 `volumes: ./backend:/app` 把 source code 掛進去 → 改完 code 不用 rebuild,`uvicorn --reload` 自動偵測。
  - `volumes: /app/.venv`(anonymous volume)蓋過 host 的空 venv,讓容器內 builder stage 裝好的 .venv 不被 bind mount 蓋掉。
  - Postgres 用 named volume `postgres_data` → 容器重啟資料不會丟。

#### `backend/pyproject.toml`
- **`[project] requires-python = ">=3.12,<3.13"`**:pin 到 3.12,因為某些套件對 3.14 wheel 還沒齊全(本機系統是 3.14)。`uv` 會自動下載 3.12 給專案用。
- **`dependencies`**:runtime 套件 — `fastapi`、`uvicorn[standard]`(含 `uvloop`、`httptools` 等加速)、`sqlalchemy[asyncio]`、`asyncpg`、`alembic`、`pydantic`、`pydantic-settings`、`httpx`、`tenacity`、`structlog`。
- **`[dependency-groups] dev`**:PEP 735 標準,只給開發用 — `ruff`、`mypy`、`pytest`、`pytest-asyncio`、`pytest-httpx`、`pre-commit`。Production build 用 `uv sync --no-dev` 不會帶入這些,image 較小。
- **`[tool.ruff]`**:`line-length = 100`、`target-version = "py312"`、啟用 `E/W/F/I/B/UP/ASYNC/S/RUF` rule sets。
- **`[tool.ruff.lint.flake8-bugbear].extend-immutable-calls`**:加入 `fastapi.Depends`、`Query` 等到白名單,避免 B008 誤報(FastAPI 的 idiom 就是把 `Depends()` 放在 default argument)。
- **`[tool.mypy] strict = true`**:啟用所有 strict 檢查,搭配 `plugins = ["pydantic.mypy"]` 讓 mypy 看懂 Pydantic model。
- **`[tool.pytest.ini_options] asyncio_mode = "auto"`**:不用每個 async test 手動加 `@pytest.mark.asyncio`。

#### `backend/Dockerfile`
- **Multi-stage build**:
  1. `builder` stage:用 `uv` 安裝 deps,產生 `.venv/`。
  2. `runtime` stage:用 `python:3.12-slim`,只 copy `/app`(含 venv),**不裝 uv**(production 不需要)。
- **`COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv`**:從 uv 官方 image 拿 binary,比 `pip install uv` 快太多。
- **Layer cache 最佳化**:先 `COPY pyproject.toml uv.lock`、`uv sync --no-install-project`、再 `COPY . .`、`uv sync`。這樣只改 source code 不重裝 deps。
- **`USER app`**:non-root 容器,基本 hardening。
- **`PATH="/app/.venv/bin:$PATH"`**:讓 `alembic`、`uvicorn` 等指令直接能用,docker-compose command 才能寫 `alembic upgrade head` 而不用 `uv run alembic ...`(production runtime 沒裝 uv)。

#### `backend/.dockerignore`
- 排除 `.venv`、`__pycache__`、`.git`、`tests/` → build context 小,layer cache 不會因為無關檔案改動而失效。

#### `backend/app/config/settings.py`
- 用 `pydantic-settings` 從 `.env` 讀環境變數,**全部 typed**。
- `@lru_cache def get_settings()` → 全程式只 instantiate 一次,測試可以用 `app.dependency_overrides` 換掉。
- **絕不在 module-level 直接讀 env var**(像 `os.environ["DATABASE_URL"]`)→ 改 env 時整個 module 要重 import,測試地獄。

#### `backend/app/db/base.py`
- **`class Base(DeclarativeBase)`**:SQLAlchemy 2.0 新風格,取代 1.x 的 `declarative_base()`。
- **`TimestampMixin`** 提供 `created_at` / `updated_at`:用 `server_default=func.now()` + `onupdate=func.now()` → 由 DB 端產生時間戳,跨 timezone 一致。
  - 拆成 mixin 而不是塞進 `Base`,因為未來如果有 reference / lookup 表不需要 timestamp 可以選擇不繼承。

#### `backend/app/db/models.py`
- **`Event`** model 對應 spec §6.1。
- **`EventSource(StrEnum)` / `EventStatus(StrEnum)`**:Python 3.11+ 的 `StrEnum` 取代舊的 `class X(str, Enum)`,序列化更乾淨。SQLAlchemy 會自動建 PostgreSQL `ENUM` type。
- **`__table_args__`**:
  - `UniqueConstraint("source", "external_id")` → adapter 去重的依據。
  - `Index("ix_events_status_published", "status", "published_at")` → 給未來 Analyzer 查「找出所有 `FETCHED` 狀態的 event」用,避免 full table scan。
- **`payload: Mapped[dict] = mapped_column(JSONB)`** → 各 source 原始資料用 JSONB,既 flexible 又能 GIN index(目前還沒加,需要時再加)。
- **`affected_tickers: Mapped[list[str]] = mapped_column(ARRAY(String(10)))`** → Postgres 原生 array 型別。MongoDB 不需要也能存,但 PG 也支援。
- **時間欄位都用 `DateTime(timezone=True)`** → 存成 `TIMESTAMPTZ`,避免 naive datetime 混進來。

#### `backend/app/db/session.py`
- **`create_async_engine`**:用 asyncpg driver(URL scheme: `postgresql+asyncpg://`)。
- **`pool_pre_ping=True`**:每次取 connection 前 ping 一下,DB 重啟 / 網路抖動後第一個 request 不會炸。
- **`pool_size=5, max_overflow=10`** → 最多 15 個 connection。小規模 MVP 夠用。
- **`async_sessionmaker(..., expire_on_commit=False)`** → commit 之後 ORM object 還能繼續讀屬性(否則會觸發 lazy load,在 async session 裡會炸)。
- **`async def get_db()`** FastAPI dependency:`async with AsyncSessionLocal() as session: yield session` → request 結束自動關 session。

#### `backend/alembic.ini` + `backend/alembic/env.py`
- `alembic init -t async alembic` 產生 async 版 template。
- **改 `env.py`** 從 `app.config.settings.get_settings()` 拿 DATABASE_URL,而不是寫死在 `alembic.ini` → dev / staging / prod 用同一份 alembic config。
- **`target_metadata = Base.metadata`** + **顯式 `from app.db import models`** → autogenerate 才能掃到 model。
- **`alembic.ini` 把 `sqlalchemy.url = ` 留空** → 明確表示由程式設定,避免「兩處有設定但版本不同」的混亂。

#### `backend/alembic/versions/88b80a46ba34_initial_events_table.py`
- **`alembic revision --autogenerate -m "initial events table"`** 產生 → 比較 Postgres 現況 vs Base.metadata 的 diff,自動寫 `op.create_table(...)` / `op.create_index(...)`。
- **手動修正 `downgrade()`** 加上 `op.execute('DROP TYPE IF EXISTS event_source / event_status')` → autogenerate 不會幫你 drop ENUM type,downgrade 完會留下孤兒型別。
- 用 `alembic upgrade head` 驗證 schema:`\d events` 看到表、欄位、index、unique constraint 都對。

#### `backend/app/adapters/fred.py`
- **`async def fetch_cpi(db: AsyncSession) -> int`**:同步呼叫 FRED API,把新觀測值寫進 events table,回傳新增筆數。
- **去重邏輯**:先 `SELECT Event.id WHERE source=FRED AND external_id=...` 檢查,沒有再 INSERT。但 unique constraint 仍是 source of truth(catch `IntegrityError` → rollback continue),用來防止 race condition(兩個 worker 同時 fetch 同一筆)。
- **`external_id = f"{CPI_SERIES_ID}:{release_date}"`** → 用「series_id + 發布日期」當去重 key。
- **`httpx.AsyncClient(timeout=30.0)`** → async HTTP,而不是 `requests`(spec 明確禁止)。
- **`structlog.get_logger(__name__).bind(source="FRED", series_id=...)`** → structured logging,可以 grep `source=FRED` 看所有 FRED 動作。
- **`FRED_API_KEY` 沒設 → raise `RuntimeError`**,API route 翻成 `503 Service Unavailable`。不偽造資料。

#### `backend/app/schemas/event.py`
- **`EventRead(BaseModel)`** + `model_config = ConfigDict(from_attributes=True)` → Pydantic v2 取代 v1 的 `orm_mode = True`。可以直接 `EventRead.model_validate(event_orm_obj)`。
- **`EventListResponse { data, meta }`** → 符合 spec §10 response shape。所有 list endpoint 都會用這個格式。

#### `backend/app/api/routes/events.py` + `backend/app/api/routes/__init__.py`
- **`GET /api/v1/events`**:支援 `page` / `per_page` query,offset pagination(M1 簡單版,spec 提到 cursor pagination 之後再上)。
- **`POST /api/v1/events/_admin/trigger-fred-cpi`**(`include_in_schema=False`,不出現在 OpenAPI):M1 用的手動 trigger 端點,M2 排程上線後移除或保留作 debug。
- **`GET /api/v1/health`**:liveness check,production load balancer / k8s probe 用。

#### `backend/app/main.py`
- **`configure_logging()` 在 module-level 跑** → 任何 `import app.main` 都會初始化 structlog。
- **dev 環境用 `ConsoleRenderer`**(彩色、人類可讀),其他用 `JSONRenderer`(給 Loki / CloudWatch 吃)。

---

### 為什麼這樣選(關鍵決策)

#### 為什麼用 `StrEnum` 而不是 `class X(str, Enum)`?
- `StrEnum` 是 Python 3.11 引入,專門解決「我想要 enum 也能直接當 string 用」的需求。
- `class X(str, Enum)` 是舊寫法,但有些細節怪怪的(`str(X.A) == "X.A"` 而非 `"A"`)。
- `ruff UP042` 會 flag 舊寫法。

#### 為什麼用 anonymous volume `/app/.venv` 蓋掉 bind mount?
- Bind mount `./backend:/app` 把整個 host 目錄掛進去 → 把容器內 builder 裝好的 `/app/.venv/` 也蓋掉了(host 沒有那個資料夾)。
- 解法:加一個 `/app/.venv` anonymous volume → docker 看到「這裡也有個 volume」就不會被 bind mount 蓋。
- 替代方案:把 venv 裝在 `/opt/venv` 而不是 `/app/.venv`,但這需要改一堆 PATH 設定。anonymous volume 比較直接。

#### 為什麼 alembic.ini 的 `sqlalchemy.url` 留空,在 `env.py` 用 `get_settings()`?
- 一份 alembic config 服務 dev / staging / prod,差別只在 env var。
- 如果 `alembic.ini` 有寫 URL,還要靠 ENV substitution(`%(POSTGRES_HOST)s` 之類)— 比 Python 一行 `config.set_main_option(...)` 醜很多。
- pydantic-settings 已經是專案的 single source of truth,migration 也用同一份。

#### 為什麼 Dockerfile multi-stage 而不是單 stage?
- 單 stage:`uv` binary + 編譯工具 + cache 都會留在 final image,~500MB+。
- Multi-stage:final image 只有 Python + venv,~200MB。
- 部署到 AWS ECR 時,image pull 速度差 2-3x。CI 也快。

#### 為什麼 `from_attributes=True` 而不是手寫 `from_orm` 風格?
- Pydantic v2 的標準寫法。`from_orm` 在 v2 已 deprecated。
- 配合 SQLAlchemy 2.0 的 `Mapped[]` annotation 完全 type-safe。

#### 為什麼初始 migration 手動補 DROP TYPE?
- PostgreSQL ENUM 是獨立的 schema object,不屬於某個 table。
- `op.drop_table('events')` 只刪 table,ENUM 還在。
- 下次 upgrade 想再 create 同名 ENUM 就會炸:`ERROR: type "event_source" already exists`。
- 這是 alembic autogenerate 已知的小坑,養成手動檢查 downgrade 的習慣。

#### 為什麼用 anonymous volume 而不是 named volume 給 .venv?
- Anonymous volume 是 per-container 的,docker compose down + up 會重建。
- 如果用 named volume,改 deps 後舊 venv 還在,得 `docker volume rm` 才會重裝。
- Trade-off:每次 rebuild image 第一次 up 會慢一點(venv 重 copy),但乾淨。

---

### 學到的觀念

1. **State machine in DB,不是 in queue**:spec 強調用 `events.status` 欄位驅動 pipeline,而非 Celery `chain()`。好處是 worker 重啟 / failure 之後,光看 DB 就知道下一步要做什麼,不需要 reconstruct queue state。M2 會用到這個原則。

2. **Idempotency = unique constraint + catch IntegrityError**:adapter 寫得「重複跑沒副作用」,不是靠記憶體判斷,是靠 DB 約束。這是分散式 worker 的標準做法。

3. **Async session 的 `expire_on_commit=False`**:預設 commit 後 ORM object 屬性會被「過期化」,下次讀觸發 lazy load — 但 async 環境的 lazy load 會崩(因為沒 sync session 可用)。關掉 expire 是 async SQLAlchemy 的常識。

4. **`Depends()` 在 function default 不是 Python anti-pattern**:正常 Python 不該在 default 寫 function call(每個 def 共享同一個 mutable),但 FastAPI 用 `Depends()` 是建立依賴注入 marker,FastAPI runtime 會處理 — 所以要把它加進 ruff 白名單。

5. **`docker compose depends_on: condition: service_healthy`** vs 普通 `depends_on`:前者真的等到 healthcheck 通過,後者只等容器啟動(但 Postgres 還在 init script)。少了這行,backend 第一次連 DB 必炸。

---

### 面試可能會被問到

**Q1: 為什麼選 SQLAlchemy 2.0 而不是更輕量的方案如 Tortoise ORM / SQLModel?**
- 2.0 的 `Mapped[]` 配合現代 type system,IDE 體驗最好。
- SQLModel(FastAPI 作者出的)是 Pydantic + SQLAlchemy 包裝,但 abstraction layer 多一層,複雜 query 反而需要 escape hatch 回到 SQLAlchemy。
- Tortoise 是 Django ORM 風格,async-native 但生態小、社群和文件比 SQLAlchemy 差很多。
- 為履歷考量:SQLAlchemy 是 Python 後端的事實標準,招聘 JD 點名率最高。

**Q2: Alembic autogenerate 有哪些坑?**
- 不會 drop ENUM type(剛踩過)。
- 不會 detect column rename(autogen 看到的是 drop + add)。
- Server-side default 改動不會偵測。
- 為什麼還用 autogen:大部分情況省力,生出來的東西自己再 review 一遍就好。

**Q3: 為什麼 `payload` 用 JSONB 而不是 normalize 出多個欄位?**
- 各 source(FRED / SEC / FOMC / earnings)payload 結構完全不一樣,normalize 會有 30+ 個欄位且多數情況是 NULL。
- JSONB 仍然可以建 GIN index 做查詢(`WHERE payload->>'series_id' = 'CPIAUCSL'`)。
- 結構穩定後可以「正規化部分常用欄位 + JSONB 保留原始 raw」。

**Q4: 你的 dedup 邏輯怎麼處理 race condition?**
- 兩個 worker 同時跑 `fetch_cpi`,都先 SELECT 不存在,然後同時 INSERT → 第二個會撞 unique constraint。
- 我們 catch `IntegrityError`,rollback 那一筆,繼續處理下一筆 → 不會 crash,不會重複資料。
- 為什麼還做 pre-check SELECT:大部分情況 SELECT 較便宜,可以省下 INSERT attempt 的 round trip。

**Q5: 為什麼用 asyncpg 不用 psycopg?**
- psycopg2 是同步,跟 FastAPI async 衝突。
- psycopg3 雖然有 async 模式,但效能不如 asyncpg。
- asyncpg 是 MagicStack 出品(uvloop 同團隊),純 C 實作,async PG driver 中最快。

---

### 驗收狀態

- [x] `docker compose up` 一次乾淨啟動,Postgres + Redis + Backend 全部 healthy
- [x] `GET /api/v1/health` → `{"status":"ok"}`
- [x] `GET /api/v1/events` → 空列表 + 正確 meta
- [x] `POST /api/v1/events/_admin/trigger-fred-cpi`(無 key)→ 503 with `FRED_API_KEY not configured`
- [x] 填入 `FRED_API_KEY` 後 trigger → `{"status":"ok","inserted":11}`,GET 拿到 11 筆 CPI 月度資料
- [x] 再次 trigger → `inserted: 0`(unique constraint 阻止重複)

### 過程中踩到的坑

**Bug:`FRED_API_KEY` 填進 `.env` 但 container 內讀不到**
- 症狀:`backend/.env` 已填值、`docker compose restart backend`,但端點仍回 `FRED_API_KEY not configured`。
- 原因:`docker-compose.yml` 原本寫 `environment: FRED_API_KEY: ${FRED_API_KEY:-}` — 這是 docker-compose 的 **shell substitution**,從啟動 compose 的 shell 取值,**不是**從 `backend/.env` 讀。如果 shell 沒設,會塞個 `""` 進容器,蓋過 pydantic-settings 從 `/app/.env` 讀到的值。
- 為什麼這順序很重要:pydantic-settings 的 precedence 是「init args > env vars > .env file」 — 容器 env 永遠贏 `.env` 檔。
- 修法:把 `FRED_API_KEY` 從 `environment:` 拿掉,改加 `env_file: - ./backend/.env`,讓 docker compose 在啟動容器時把 `.env` 整包載入。`DATABASE_URL` / `REDIS_URL` 仍寫在 `environment:`,因為容器內要用 service hostname(`postgres` / `redis`)而非 `localhost`,需要 override `.env`。
- 教訓:多層設定來源很容易誤判優先級。**`env_file:` 是 dev / staging 從本地檔案餵 secret 的乾淨做法;production 應該用 AWS Secrets Manager / Railway secrets,絕不 commit `.env`。**

---

## Milestone 2 — Scheduled fetching

> **狀態**:✅ 完成
> **目標**:加入 Celery + Beat,FRED 改為排程觸發,結構化 logging,tenacity retry,首批 pytest。

### 做了什麼(依檔案分類)

#### `backend/pyproject.toml`
- 加入 `celery[redis]>=5.4.0`。`[redis]` extras 自動裝 `redis-py` 作為 broker driver。

#### `backend/app/workers/celery_app.py`(新)
- **`Celery("eventsense", broker=..., backend=...)`**:broker 和 result backend 都用 Redis。
- **`include=["app.tasks.fetchers"]`**:讓 Celery autodiscover task module,不用每個 task 手動 import。
- **`task_acks_late=True` + `worker_prefetch_multiplier=1`**:worker 跑完才 ack message,中途 crash 會被 redeliver。配合 tasks 本身的 idempotency(unique constraint),safer default。
- **`task_routes`** 把 task 路由到 3 個 queue(`fetch_queue` / `analyze_queue` / `validate_queue`)。M2 只用 fetch,但其他 route 先定義好,以後不用重命名 task。
- **`beat_schedule.fred-cpi-hourly`**:用 `crontab(minute=0)` 每小時整點觸發 `fetch_fred_cpi_task`。
- **`@setup_logging.connect`** signal handler:Celery 預設會用自己的 logging 設定,我們攔截下來改用 `configure_logging()`,讓 worker 和 beat 也吐 structlog 格式。

#### `backend/app/tasks/fetchers.py`(新)
- **Sync Celery task 包 async adapter**:用 `asyncio.run(_run_fetch_cpi())`。每個 task call 起一個新的 event loop — 對我們每小時一次的 cadence,overhead 可以忽略。
- **`autoretry_for=(httpx.HTTPError,)` + `retry_backoff=True` + `retry_jitter=True` + `max_retries=5`**:Celery 層的 retry,catch tenacity 沒 catch 完的更嚴重情況(整個 FRED 掛掉超過 30 秒)。
- 命名 `name="app.tasks.fetchers.fetch_fred_cpi_task"` 明確,避免 Celery autoname 出 surprise。

#### `backend/app/adapters/fred.py`(修改)
- `_fetch_series_observations` 加上 `@tenacity.retry`:
  - `retry_if_exception_type(httpx.HTTPError)` — 只 retry 網路類錯誤,不 retry programming bug
  - `stop_after_attempt(4)` — 最多 4 次
  - `wait_exponential(multiplier=1, min=1, max=10)` — 1s, 2s, 4s, 8s(cap at 10s)
  - `reraise=True` — 最後一次失敗時 raise 原始 exception,讓 Celery 看到 HTTPError 觸發外層 retry

#### `backend/app/logging_config.py`(新,從 `app/main.py` 抽出來)
- 把原本只服務 FastAPI 的 `configure_logging()` 改成共用模組。
- **重點**:`ProcessorFormatter` 讓 stdlib `logging` 模組(SQLAlchemy、Celery、Alembic 用的)也走同一條 structlog processor pipeline,輸出格式完全一致 — 不會看到「FastAPI log 是彩色的、Celery log 是純文字」的混亂。
- 把 `sqlalchemy.engine` 和 `httpx` 的 level 調到 WARNING,避免一堆 INFO 雜訊。

#### `backend/app/main.py`(修改)
- 從 35 行縮到 13 行 — 邏輯都搬到 `logging_config.py`,main 只負責掛 router + 觸發 logging init。

#### `docker-compose.yml`(修改)
- 加入 `worker` service:
  - `command: celery -A app.workers.celery_app worker -Q fetch_queue --concurrency=4`
  - 用 `-Q fetch_queue` 限制 queue,以後加 LLM analyzer 不會搶 fetch CPU
  - `depends_on: backend: service_started` — backend 跑完 migration 才啟動 worker
- 加入 `beat` service:
  - `command: celery -A app.workers.celery_app beat`
  - **單 replica**,因為兩個 beat 會 double-enqueue 每個排程
  - 不依賴 postgres(beat 只跟 broker 通訊)

#### `backend/tests/conftest.py`(新)
- `db_session` fixture:每個 integration test 自動 TRUNCATE `events` 表,確保 test 之間互不污染。
- 用 `text("TRUNCATE TABLE events CASCADE")` 而非 ORM delete — 更快、會 reset sequence。
- Fixture 用 `pytest_asyncio.fixture` 而非 `pytest.fixture`,搭配 `asyncio_mode = "auto"` 不用手動加 marker。

#### `backend/tests/unit/test_fred_adapter.py`(新,4 個測試)
1. `test_fetch_observations_returns_parsed_list` — 用 `pytest-httpx` mock FRED response,確認 parse 出 list of dict。
2. `test_fetch_observations_raises_on_5xx` — 連續 mock 4 個 503,確認 tenacity 用完 retries 後 reraise `HTTPStatusError`。
3. `test_fetch_cpi_skips_missing_value` — observation 中 `value: "."`(FRED 缺值標記)要被略過,不該 insert。
4. `test_fetch_cpi_raises_runtime_error_without_key` — 沒設 `FRED_API_KEY` 要 raise `RuntimeError`。

#### `backend/tests/integration/test_fred_idempotency.py`(新,2 個測試)
1. `test_fetch_cpi_is_idempotent` — 連跑 `fetch_cpi` 兩次,第一次 inserted=3,第二次 inserted=0,DB 仍只有 3 筆。
2. `test_fetch_cpi_writes_expected_fields` — INSERT 後讀回來,確認 external_id、event_type、payload 結構正確。

---

### 為什麼這樣選(關鍵決策)

#### 為什麼 Celery 用 sync wrapper + `asyncio.run()`,而不是 `celery-pool-asyncio`?
- 我們的 task 量很低(每小時一次 per source),沒有 perf pressure。
- `asyncio.run()` 是標準庫,沒有外部依賴。
- `celery-pool-asyncio` 是 third-party,可能與未來 Celery 版本不相容。
- 真的有大量 async task 時再重構,YAGNI。

#### 為什麼 `task_acks_late=True`?
- 預設(`acks_late=False`)是 worker 收到 message 就 ack,然後執行 — 中間 crash → message 丟了。
- `acks_late=True`:跑完才 ack,crash 會 redeliver。
- **代價**:同一個 task 可能跑兩次。但我們所有 fetcher / analyzer 都是 idempotent,所以這 trade 划算。
- 配合 `worker_prefetch_multiplier=1` 避免一個 worker 預取太多 message 卡死。

#### 為什麼 tenacity + Celery 兩層 retry?
- **Tenacity(內層,在 adapter 裡)**:處理「打一次 API 中,1-2 秒網路抖」— 快速 retry,task 內解決,broker 不知道。
- **Celery(外層,在 task 裡)**:處理「FRED 整個掛 30 分鐘」— tenacity 4 次都失敗了,丟回 broker,過 backoff 時間再重試。
- 沒有兩層的話:要嘛 tenacity 等很久(浪費 worker 時間),要嘛 Celery 每次都從頭重新 retry(浪費 broker round trip)。

#### 為什麼 beat 必須單 replica?
- Beat 的工作是「在排定時間 enqueue task」 — 多個 beat 各自看時鐘,每個都會 enqueue 一次。
- 結果:每小時的 task 跑 N 次(N = beat replica 數),DB 雖然被 unique constraint 保護不會壞,但浪費資源 + 日誌混亂。
- 進階解法:`celery-beat-redis-scheduler` 用 Redis lock 讓多 replica 競爭領導權。MVP 不需要。

#### 為什麼把 logging 從 `main.py` 抽出來?
- Celery worker / beat 不會 import `app.main`(沒必要載入 FastAPI),所以 main.py 裡的 logging init 對 worker 沒效。
- 抽到 `app/logging_config.py`,worker celery_app.py 也能 import → 三個 entry point(uvicorn、worker、beat)共用同一份設定。

#### 為什麼 `ProcessorFormatter` 而不是直接讓 structlog 處理所有 log?
- SQLAlchemy、Celery、httpx 用 stdlib `logging`,不會走 structlog。
- 沒有 ProcessorFormatter,你會看到混雜兩種格式的 log,grep 困難。
- ProcessorFormatter 是 structlog 提供的橋:stdlib log record → 經過同一條 processor chain → 同樣的輸出格式。

#### 為什麼 unit test 用 `MagicMock` for `db.add`,但 `AsyncMock` for `db.flush`?
- SQLAlchemy 的 `session.add()` 是 sync method(把 object 加進 identity map,沒 I/O)。
- `session.flush()` / `commit()` / `scalar()` 是 async(真的有 I/O)。
- `AsyncMock` 預設所有 method 都返回 coroutine — `add()` 不該 await,所以要 override 成 `MagicMock`。
- 沒做這個 override 會看到 `RuntimeWarning: coroutine was never awaited`(雖然 test 還是過)。

---

### 學到的觀念

1. **Beat 是 scheduler,不是 worker**:Beat 不執行 task,只是「按表 enqueue」。所以 Beat container 不需要連 Postgres,只需要連 Redis(broker)。

2. **Celery `task_routes` 用 wildcard**:`"app.tasks.fetchers.*": {"queue": "fetch_queue"}` 一次處理整個 module。新增 task 不用改設定。

3. **`asyncio.run()` 一次 task 開一次 event loop**:對低頻 task 無感,但如果某個 task 內要做很多 async work(例如同時打 50 個 ticker 的 yfinance),要記得在 task 裡用同一個 loop（`asyncio.gather`)而非各 spawn loop。

4. **`crontab(minute=0)` 意思是「每小時的第 0 分」**,不是「每 60 分」。後者要寫 `timedelta(minutes=60)`。差別在「對齊整點」vs「相對啟動時間」。

5. **Test 寫 conftest 比 setUp/tearDown 好**:pytest fixture 可以 scope 到 function / module / session、可以 parametrize、可以互相依賴。不要寫 `setUp` 風格。

---

### 面試可能會被問到

**Q1: 為什麼選 Celery 而不是 RQ / Dramatiq / arq / Sidekiq?**
- **RQ**:更輕量,但沒有 beat scheduler、queue routing 比較陽春。
- **Dramatiq**:設計比 Celery 乾淨,但社群小,缺少現成 plugin。
- **arq**:async-native,但生態最小,只適合純 async 專案。
- **Sidekiq**:Ruby,不是 Python option。
- 結論:**Celery 是 Python 生態 default choice,招聘 JD 點名率最高**;缺點是設定複雜、文件雜亂,但有 stack overflow 護身符。

**Q2: `task_acks_late=True` 適合什麼情境?有什麼風險?**
- 適合「task 是 idempotent」+「task 跑超過幾秒鐘」+「資料丟失比重複跑代價高」。
- 風險:不 idempotent 的 task 會被跑兩次造成 side effect(發兩次 email、insert 兩筆訂單)。
- 我們 fetcher / analyzer / validator 都有 unique constraint 保護,所以放心開。

**Q3: 你的 tenacity 設定 `wait_exponential(multiplier=1, min=1, max=10)` 怎麼算?**
- 第 1 次失敗 → 等 1s
- 第 2 次失敗 → 等 2s
- 第 3 次失敗 → 等 4s
- 第 4 次失敗 → 等 8s(cap at 10s,所以不會繼續成 16)
- 配合 `stop_after_attempt(4)`,最多 4 次嘗試,總共 ~15 秒。

**Q4: 為什麼不用 APScheduler 取代 Celery Beat?**
- APScheduler 是 in-process scheduler — 你的 FastAPI 程式自己排程。
- 缺點:FastAPI 多 instance(load balancer 後面)時,每個 instance 都會跑 schedule。
- Celery Beat 是獨立 process,單例好控制,而且 task 進入 broker 之後 worker 可以橫向擴展處理。
- 我們的架構是「scheduler 集中、worker 散開」 → Celery Beat 比較對。

**Q5: 如果 Redis 掛了會發生什麼事?**
- Beat 試圖 enqueue → 連不上 broker → 重試(Celery 內建 retry)。
- Worker 試圖讀取 message → 連不上 → idle 等待。
- 整段時間 task 不會跑,但**不會丟資料**(Beat 不會記住沒送出的 task,但下個 schedule cycle 會繼續送)。
- 對 FRED hourly 來說,Redis 掛 5 分鐘代表那一小時的 fetch 跳過 — 不嚴重,下小時繼續。
- Production 用 Redis Sentinel 或 ElastiCache multi-AZ 避免。

**Q6: 你怎麼測 idempotency?**
- Integration test:`fetch_cpi(db)` 跑兩次,assert 第一次 inserted == N,第二次 == 0,DB 總筆數 == N。
- 沒測的東西:race condition(兩個 worker 同時跑同一個 task)— 因為 Celery `acks_late` 已經防止 broker 層 double-deliver 同一個 task,且我們有 unique constraint 兜底。要真的測 race 要用 multi-process test framework。

---

### 驗收狀態

- [x] `docker compose up` 全部 5 個 service(postgres、redis、backend、worker、beat)起來無錯誤
- [x] Worker 啟動 log 顯示 `[tasks] . app.tasks.fetchers.fetch_fred_cpi_task` 並 listen on `fetch_queue`
- [x] Beat 啟動 log 顯示 schedule 載入(`celery beat ... is starting`)
- [x] 手動 `celery call app.tasks.fetchers.fetch_fred_cpi_task` → worker 收到、執行、寫進 DB
- [x] Worker log 全部 structlog 格式(彩色 console 模式),key=value 結構化
- [x] 6 個 pytest 全綠(4 unit + 2 integration)
- [x] Ruff lint 0 errors,strict mode

(Spec 要求的「leave running 2 hours」full E2E 驗證 — beat 是 `crontab(minute=0)`,下個整點會自動 enqueue;機制已經以手動 call 驗證過,自動排程是相同 path。)

---

## Milestone 3 — Multi-source ingestion

> **狀態**:✅ 完成
> **目標**:加 SEC EDGAR、FOMC adapter,把所有 adapter 重構成共用 `RawEvent` 契約,寫 dedicated `event_writer` 服務,每個 source 各上 Beat 排程,完整測試覆蓋。

### 做了什麼(依檔案分類)

#### 架構小重構 — `RawEvent` 統一契約

之前 M1/M2 的 FRED adapter 直接寫 DB,M3 開始有 3 個 adapter 各做各的會重複大量程式碼。重構成「**adapter 只負責 fetch+parse,return `list[RawEvent]`;persist 由共用的 writer 處理**」。

**`backend/app/schemas/raw_event.py`(新)**
- Pydantic `RawEvent` model:`source` / `event_type` / `external_id` / `title` / `payload` / `affected_tickers` / `published_at`
- `model_config = ConfigDict(frozen=True)` → immutable value object,adapter 創出來之後不能改
- 跟 `Event` ORM model 結構幾乎一樣,但**不依賴 SQLAlchemy** → adapter 不用 import DB 任何東西

**`backend/app/services/event_writer.py`(新)**
- `persist_events(db, raw_events) -> int`:吃 `list[RawEvent]`,做 dedup + INSERT,回傳新增筆數
- **是唯一寫 events 表的地方** — 未來要加 metrics、audit log,只改這裡
- Dedup 邏輯就一份(pre-check SELECT + catch IntegrityError)

#### `backend/app/adapters/fred.py`(重構)
- 移除 `fetch_cpi(db: AsyncSession) -> int`(會寫 DB)
- 新增 `fetch_new() -> list[RawEvent]`(純 fetch + parse)
- 抽出 `_observation_to_raw_event(obs, series_id) -> RawEvent | None` — 純函式,好測試

#### `backend/app/adapters/sec_edgar.py`(新)
- 對每個 watchlist 公司打 `https://data.sec.gov/submissions/CIK{cik}.json`
- **mandatory User-Agent**:SEC 強制要求(`SEC_USER_AGENT` env 必須含 email)— 沒 email 直接 raise RuntimeError
- 篩選 `form == "8-K"` + 過去 14 天 (`LOOKBACK_DAYS`)
- **SEC 回傳的是 column-oriented arrays**(`form: [...], filingDate: [...], accessionNumber: [...]`),要 zip 起來
- **per-ticker rate limit**:`asyncio.sleep(0.15)` 控制在 ~6 req/sec(SEC 規定上限 10 req/sec)
- **per-ticker 容錯**:某個 ticker 404 → log warning + continue,不讓壞 ticker 拖垮整個 run
- 組裝 SEC archive URL 時要注意 accession number 從 `0000320193-26-000042` 變成 `000032019326000042`(去 dash)

#### `backend/app/adapters/fomc.py`(新)
- 抓 https://www.federalreserve.gov/feeds/press_monetary.xml (RSS 2.0)
- 用 **`defusedxml`** 而非 stdlib `xml.etree.ElementTree`(等下解釋)
- 用 `email.utils.parsedate_to_datetime` 解析 RFC 822 格式的 `<pubDate>`
- `_is_fomc_statement(title)` 篩出真正的 FOMC 政策聲明(不是 Beige Book、不是 Powell 演講)
- `external_id` 用 RSS item 的 `<link>` URL(每個 press release 都有唯一 URL)

#### `backend/app/config/cik_map.py`(新)
- 7 個 watchlist 大型科技股的 CIK 對應(AAPL/MSFT/GOOGL/AMZN/META/NVDA/TSLA)
- 排除 SPY/QQQ — 它們是 ETF,filing 形式不同,不會有 8-K
- CIK 是 SEC 永久 ID,合併 / 改名都不變 → 靜態 map 安全

#### `backend/app/tasks/fetchers.py`(重寫)
- 抽 `_run_fetch(source_name, fetch_fn)` 通用骨架 → 3 個 task 只是設定不同
- `_common_task_kwargs` 集中 Celery retry 設定 → 不重複
- 3 個 task:`fetch_fred_cpi_task`、`fetch_sec_edgar_task`、`fetch_fomc_task`
- 每個 task 都 `asyncio.run(fetch_fn())` 拿 RawEvents,再 `asyncio.run(_fetch_and_persist(events))`

#### `backend/app/workers/celery_app.py`(修改)
- Beat schedule 加兩個:
  - `sec-edgar-15min`:`crontab(minute="*/15")` 每 15 分鐘
  - `fomc-daily`:`crontab(hour=14, minute=30)` 每天 UTC 14:30(美東 9:30 早盤前)

#### `backend/app/db/session.py`(重構)— 修 critical bug
- 原本只有一個 pooled engine 給所有人用
- 加 `transient_session()` async context manager:**每次 call 開全新 engine + `NullPool`,用完 dispose**
- 給 Celery task 用(避開「event loop 不同」bug,等下細說)
- FastAPI 還是用 pooled engine(`AsyncSessionLocal`)

#### `backend/pyproject.toml`(修改)
- 加 `defusedxml>=0.7.1`

#### `backend/.env` / `backend/.env.example`
- 加 `SEC_USER_AGENT="EventSense your-email@example.com"`

#### 測試(18 個全綠,M2 的 6 個 → M3 的 18 個)
- `tests/unit/test_fred_adapter.py` 改寫:用新 `fetch_new()` 介面測 RawEvent 輸出
- `tests/unit/test_sec_edgar_adapter.py`(新,5 tests):8-K filter、cutoff date 過期、accession URL 組裝、無 User-Agent 失敗、單一 ticker 失敗不影響其他
- `tests/unit/test_fomc_adapter.py`(新,6 tests):title regex、RSS item parse、missing pubDate、整個 feed extraction
- `tests/integration/test_event_writer.py`(新,3 tests):跨 source idempotency、`(source, external_id)` 複合 unique 行為、空 list no-op

---

### 為什麼這樣選(關鍵決策)

#### 為什麼把 adapter 拆成 pure function?
- 之前 `fetch_cpi(db: AsyncSession)` 把「打 API」「parse」「寫 DB」綁在一起 → 單元測試要 mock db,寫起來囉嗦
- 拆開後 adapter 是純函式:`fetch_new() -> list[RawEvent]`
  - 單元測試:只 mock httpx,不用碰 DB,測試快 100 倍
  - Cross-source 邏輯(retry、log format)集中在 task 層
  - 未來想用 adapter 做 backfill 腳本、CLI 工具 — 不用拖 DB 進來
- 這個 pattern 叫 **"shy code"**:每個 module 認識的東西越少越好

#### 為什麼用 `defusedxml` 而不是 stdlib `xml.etree`?
- stdlib XML parser 對某些 attack 沒防(**XXE entity injection**、**billion laughs**)
- 真實風險:Fed 不會打我們,但 ruff 的 S314 lint rule 還是會 flag → 養成習慣
- `defusedxml` 是 1 個小套件、零維護成本、API 完全相容、面試講得出來
- **interview talking point**:「我知道 XML parser 有安全考量,所以選 defusedxml」

#### 為什麼 SEC adapter 用 `asyncio.sleep(0.15)` 而非真正的 rate limiter?
- SEC 限制 10 req/sec per IP
- 我們 7 個 ticker → 7 req/run,跑得快也撞不到
- `sleep(0.15)` 簡單、無依賴、看程式碼直接懂
- 真正用 token bucket 是「**未來加更多 ticker 時**」的事

#### 為什麼 `LOOKBACK_DAYS = 14`?
- 8-K 有 4 個工作天內申報的規範,所以 14 天足以涵蓋
- 太短(例如 1 天):週末跑會錯過週五的 filing
- 太長(例如 90 天):第一次跑會插入大量舊 filing,後續每次 poll 都掃一大堆已存在的(雖然 unique constraint 兜底,但浪費 API call)

#### 為什麼 SEC `external_id` 用 accession number 而 FOMC 用 link URL?
- SEC accession number 是 SEC 自己給每個 filing 的唯一 ID(格式 `CIK-YY-NNNNNN`),保證唯一
- FOMC RSS 沒有明顯的 ID 欄位,但 `<link>` URL 是穩定的(release URL 一旦發出就不會改)
- 原則:**用 source 自己的 ID,沒有就用最穩定的 stable URL/key**

#### 為什麼 worker 需要 `transient_session()` 而 FastAPI 不用?
- FastAPI 是長期跑的 process,只有一個 asyncio event loop,pool 安心重用 connection
- Celery worker 每個 task 都 `asyncio.run()` → **每次都是全新 event loop**
- asyncpg 的 connection 跟「**開它的 event loop**」綁定 — 換 loop 用會炸 `got Future attached to a different loop`
- 解法:worker 用 `NullPool`(每次重新連線、用完就丟)— 不重用就沒 loop binding 問題
- Trade-off:每個 task 多一次 TCP handshake (~5ms),對每小時跑一次的 task 完全不痛

---

### 過程中踩到的坑

#### 坑 1:Anonymous volume 蓋掉 image 裡新裝的套件
- 加了 `defusedxml`,跑 `docker compose up --build -d`,結果 worker `ModuleNotFoundError: No module named 'defusedxml'`
- 原因:`/app/.venv` 用 anonymous volume 蓋在 bind mount 上(M1 為了 hot reload 設的)— 但 anonymous volume 也會跨 container 重建保留
- 新 build 的 image 有 defusedxml,但 container 啟動時舊的 anonymous volume 蓋回去
- 修法:`docker compose up --build -d --force-recreate --renew-anon-volumes` → 強制重建 anon volume
- 教訓:**改 deps 之後永遠加 `--renew-anon-volumes`**,或 alias 成一個 shell command

#### 坑 2:重構後忘了改 API endpoint(連動 bug)
- 重構 fred.py 把 `fetch_cpi` 改名為 `fetch_new`,但 `app/api/routes/events.py` 還 import 舊名
- backend container 啟動就 ImportError 死
- 修法:刪掉 M1 用的 `_admin/trigger-fred-cpi` endpoint(已被 M2 的 Beat 自動化取代)
- 教訓:**重構函式名後跑 `grep -r "old_name"`** 或讓 IDE refactor → rename 把 reference 全找出來

#### 坑 3:asyncio.run() + SQLAlchemy pool = loop binding 災難
- 症狀:`RuntimeError: got Future attached to a different loop`
- 根因:asyncpg connection 跟 event loop 綁定,Celery 的 `asyncio.run()` 每次開新 loop → pool 重用舊 connection 就炸
- 修法見上面 `transient_session()`
- **這是 Python async 生態最常踩的坑之一**,值得寫進面試故事:
  - 「我遇到這個 bug → 查到是 SQLAlchemy async + event loop 的問題 → 知道 NullPool 是 worker 場景的標準解法 → 用 context manager 包起來保持其他地方乾淨」

---

### 學到的觀念

1. **Pure function 是測試之友**:adapter 不碰 DB,測試就不用 db fixture,跑得超快(unit test 不用 docker)

2. **`(複合 unique constraint)` 才能解決「不同 source 同 external_id」**:單一 `external_id` unique 會擋掉 FRED 的 "CPIAUCSL:2026-04-01" 跟假設另一個 source 用了同樣 string 的合法情況

3. **Column-oriented JSON vs row-oriented**:SEC API 為了省 bandwidth 用 column orientation(每個欄位一個 array,要靠 index 對應)— 第一次看會以為 API 設計不好,實際上是合理的 trade-off,要習慣 zip 起來

4. **`asyncio.run()` 每次都開新 loop**:這是 stdlib 設計,不是 bug。但搭配「跨 call 共享狀態」(像 connection pool)就要特別小心

5. **`defusedxml` 是免費的 interview 加分點**:幾乎沒成本,但展示出「你知道有 XML 安全議題」

---

### 面試可能會被問到

**Q1: 為什麼把 adapter 拆成 pure function?直接寫 DB 不是更簡單?**
- 三個原因:
  - **可測試性**:pure function 只要 mock HTTP,不用 mock 也不用真 DB,測試極快
  - **可重用性**:同一個 adapter 可以給 Celery task / CLI 工具 / backfill 腳本用
  - **單一職責**:adapter 不該知道 transaction、rollback、unique constraint
- 「writer + adapter」拆分對應軟體工程的 **ports and adapters / hexagonal architecture**

**Q2: SEC EDGAR API 為什麼把資料用 column 不用 row 排?**
- 省 bandwidth:row-oriented 每筆都要寫一次 key name(`{"form": "8-K", "date": ...}, {"form": ...}`),column-oriented 只寫一次
- 對 SEC 來說省 50%+ 流量;對我們來說付出 zip 邏輯的成本
- 類似的設計在 Parquet、ClickHouse 等 columnar database 也是這種思維

**Q3: 你的 `transient_session()` 為什麼用 `NullPool`?有什麼成本?**
- 因為 Celery 每次 task `asyncio.run()` 都開新 event loop
- asyncpg connection 跟 loop 綁定,pool 裡舊 loop 的 connection 在新 loop 用會炸
- NullPool = 不 pool,每次 connect-disconnect → 沒有跨 loop 重用問題
- 成本:每個 task 多一次 TCP handshake (~5ms) + auth round trip (~3ms)
- 對我們每小時跑一次的 task,8ms 完全可以忍。對 1000 task/秒的 worker 就不行 — 那時要改用 celery-pool-asyncio 或 sync DB driver

**Q4: 為什麼 SEC 一定要 User-Agent?其他 API 怎麼沒這個要求?**
- SEC 是政府機構,有 fair-access 規定保護伺服器
- User-Agent 含 email 是給他們能「**找到濫用的 bot 把你 ban 掉**」
- 不照規矩會被 IP block(不會回 403,直接 connection refused),所以一定要遵守
- 其他 API 通常用 API key + rate limit 處理,SEC 走的是「**透明 + 信任 + 監督**」路線

**Q5: FOMC RSS 為什麼用 `<link>` 當 external_id 不用 GUID?**
- 好的 RSS feed 會有 `<guid>` 欄位(global unique identifier)
- Fed 的 feed 沒給 — 唯一穩定的 identifier 是 `<link>` URL
- URL 一旦發出就是固定的(press release 不會搬家)
- 真的有 `<guid>` 的話會優先用,但要處理 case where feed 改格式

**Q6: 三層 task retry 配置怎麼想?**
- Layer 1 — tenacity in adapter:「打一次 API 中網路抖一下」,4 次 1-10s
- Layer 2 — Celery autoretry:「FRED/SEC/FOMC 整個 outage 30 分鐘」,5 次 backoff
- Layer 3 — Beat schedule:「Celery 都失敗 → 下個 schedule cycle 自然重試」
- 三層各自處理不同 scale 的 failure,沒有 overlap,沒有 gap

---

### 驗收狀態

- [x] `docker compose up` 5 個 service 全部 healthy(postgres/redis/backend/worker/beat)
- [x] Worker 註冊 3 個 task:`fetch_fred_cpi_task`、`fetch_sec_edgar_task`、`fetch_fomc_task`
- [x] Beat schedule 載入 3 個排程
- [x] 手動 `celery call` 3 個 task 全部成功
- [x] DB 有 3 個 source 的真實資料:
  - FRED: 11 筆 CPI(月度,回溯一年)
  - SEC_EDGAR: 5 筆 8-K(過去 14 天 watchlist 新發的)
  - FOMC: 4 筆 FOMC statement(近期)
- [x] `GET /api/v1/events` 回傳混合 3 source 資料,published_at desc 排序正確
- [x] 18 個 pytest 全綠(4 FRED unit + 5 SEC unit + 6 FOMC unit + 3 writer integration)
- [x] Ruff lint + strict mypy compatible,0 errors

---

## Milestone 4 — Prices + earnings

> **狀態**:✅ 完成
> **目標**:用 yfinance 抓股價 + 財報、新表 `price_snapshots`、Redis 60s 快取、`GET /prices/{ticker}/latest` 端點、1 年歷史 backfill 腳本。

### 做了什麼(依檔案分類)

#### `backend/pyproject.toml`
- 加 `yfinance>=0.2.50` — **非官方** Yahoo Finance scraper(很重要,後面會講為什麼)

#### `backend/app/db/models.py`(新 model)
- 新 `PriceSnapshot` 對應 spec §6.3:
  - `id: bigint PRIMARY KEY autoincrement` — **不是 UUID**,因為這表會 100K+ rows/day,bigint 占 8 bytes < UUID 的 16 bytes,index 也小
  - `price: Numeric(12, 4)` — **不用 float**,float 在大數會掉精度($99,999,999.9999 都能表示)
  - `UniqueConstraint("ticker", "snapshot_at", "source")` — 同一 ticker 同一 timestamp 同一 source 不能重複
  - `Index(ticker, snapshot_at)` — 支援「找 AAPL 最新價」的 ORDER BY DESC LIMIT 1
  - **沒有 created_at / updated_at** — append-only time series,snapshot_at 已經是 authoritative timestamp

#### `backend/alembic/versions/33dfb9feb98c_add_price_snapshots_table.py`
- `alembic revision --autogenerate` 產生
- 沒有 ENUM type,不需要手動補 DROP

#### `backend/app/config/settings.py`(加欄位)
- `default_tickers: str = "NVDA,TSLA,AAPL,MSFT,GOOGL,META,AMZN,SPY,QQQ"`
- `@property watchlist` 解析成 list,trim 空白、轉大寫

#### `backend/app/lib/market_hours.py`(新)
- `is_market_open(now=None) -> bool`:用 `zoneinfo.ZoneInfo("America/New_York")` **正確處理 DST**
- 9:30 ~ 16:00 ET(interval `[open, close)`,16:00:00 整算 closed)
- 不查 NYSE 假日表(那要拉 pandas_market_calendars ~50MB),感恩節跑空 fetch 沒成本
- 8 個 unit test 覆蓋 DST 邊界、開盤/收盤鐘、週末

#### `backend/app/adapters/prices.py`(新)
- **`PriceTick` 是 `@dataclass(frozen=True, slots=True)`**,**不是 Pydantic**:
  - 高頻路徑(backfill 一次 2000+ 物件),Pydantic validation overhead 加總起來明顯
  - `slots=True` 減少每個物件的記憶體
  - SQLAlchemy INSERT 時還是會型別檢查,所以 validation 不會完全跳掉
- `intraday(ticker)`:過去 5 天的 1-minute 線(yfinance 限制 1m interval 一定要 ≥5d period)
- `daily(ticker, period="1y")`:給 backfill 用
- `_yf_history` 用 **broad `except Exception`**,yfinance 是 scraper,會丟各種未文件化 error
- 每一 row 也包 try/except,壞掉的 row 不該污染整個 batch
- `auto_adjust=False`:**split / dividend 不要 mutate 收盤價**,要保持歷史準確

#### `backend/app/services/price_writer.py`(新)
- 用 **PostgreSQL native `INSERT ... ON CONFLICT DO NOTHING`** 而非 per-row try/except:
  - 大批量(2000+ rows)時,one round trip vs 2000 round trips,差 50 倍
  - 用 `from sqlalchemy.dialects.postgresql import insert as pg_insert`
- batch 上限 1000 rows/statement,避免 query plan log 太醜
- 寫完 DB 後**順便更新 Redis 快取**(每個 ticker 的最新 tick) — 一次操作多用途
- `result.rowcount` 是真正 insert 進去的數量(排除 dedup 掉的)

#### `backend/app/services/price_cache.py`(新)
- Redis 快取「每個 ticker 最新價」60 秒 TTL
- Key shape:`eventsense:latest_price:AAPL`
- `redis.asyncio` client,**module 層 singleton** + lazy init(test 不碰 cache 不用 Redis 起來)
- `decode_responses=True` → 直接拿 str,免去自己 decode bytes
- **失敗 fail-silent**:Redis 掛了不該讓 price 寫入失敗(降級到「沒 cache」)

#### `backend/app/adapters/earnings.py`(新)
- 用 `yfinance.Ticker(ticker).earnings_history` 拿過去財報
- DataFrame index 是 quarter-end date,columns 有 `epsActual` / `epsEstimate` / `surprisePercent`
- `_safe_float()` 處理 yfinance 常給的 NaN / None / 怪型別
- 跳過 SPY / QQQ(ETF 沒財報)
- 30 天 lookback,避免回填全年舊財報
- 跟 SEC 一樣:每個 ticker call 隔離 — 一個壞不影響其他
- `external_id = "TICKER:YYYY-MM-DD"`(quarter-end date 是 natural key)

#### `backend/app/tasks/prices.py`(新)
- `fetch_prices_task`:**Beat 不論時間都 fire,task 內部 check `is_market_open()`,closed 直接 return**
  - 為什麼:cron 表達式處理 DST 痛苦(寫死 14:30 UTC 夏天就錯了)
  - market closed = 純 no-op,成本接近 0

#### `backend/app/tasks/fetchers.py`(加 task)
- `fetch_earnings_task` 用同一個 `_run_fetch()` scaffolding
- **沒設 `autoretry_for=HTTPError`** — yfinance 不丟 httpx error(它內部用 requests),adapter 層的 broad except 已經夠

#### `backend/app/workers/celery_app.py`(加排程)
- 加入 `app.tasks.prices` 到 `include` list
- task routing:`app.tasks.prices.*` → `fetch_queue`(I/O bound,跟 fetchers 同一個 worker pool)
- 三個新 Beat schedule:
  - `prices-5min`:`crontab(minute="*/5")` — 每 5 分鐘
  - `earnings-daily`:`crontab(hour=22, minute=0)` — 大多公司收盤後 4:30 PM ET 報,UTC 22:00 抓得到
  - 加 SEC + FOMC 已經在 M3

#### `backend/app/api/routes/prices.py`(新)
- `GET /api/v1/prices/{ticker}/latest` → 先查 Redis,miss 則查 DB,都沒就 404
- Response 含 `source: "cache" | "db"` 欄位 — debug 時超有用,線上想知道「為什麼這個 ticker 沒 cache」
- 404 case:`ticker not in watchlist` 或 `DB 完全沒資料`
- **read path 不寫 cache**:避免 thundering herd(cache 過期瞬間 1000 個 request 全部 fetch+寫)

#### `backend/app/scripts/backfill_prices.py`(新)
- 一次性腳本,跑 `python -m app.scripts.backfill_prices`
- 對每個 watchlist ticker 抓 1 年 daily history
- 全部 ticks 收集起來,一次 bulk insert(2200+ rows / 150ms)
- Idempotent:重跑 0 insert(unique constraint 兜底)

#### 測試(18 → 38 個全綠)
- `test_market_hours.py`(8 tests):DST 夏/冬、開盤/收盤鐘、週末
- `test_prices_adapter.py`(3 tests):正常 parse、空 DataFrame、yfinance exception 不傳染
- `test_earnings_adapter.py`(6 tests):`_safe_float` NaN、未來財報跳過、ETF 跳過、cutoff filter、整體 fetch_new
- `test_price_writer.py`(3 integration tests):bulk insert + dedup、空 list、混合新舊 batch
- M1-M3 既有 18 個 + M4 新 20 個 = 38 個

---

### 為什麼這樣選(關鍵決策)

#### 為什麼 PriceTick 用 dataclass 而 RawEvent 用 Pydantic?
- **RawEvent**:adapter 跨 source 共用契約,Pydantic 給 type safety + auto-validation,寫進 DB 之前最後一道防線
- **PriceTick**:同一個 adapter 內部用,SQLAlchemy 進 DB 時自動 type check
- **效能**:Pydantic v2 雖然快了 10x,每物件還是 ~50µs。2000 物件 = 100ms。dataclass = 0.1ms
- 原則:**邊界用 Pydantic,內部用 dataclass**

#### 為什麼 `Numeric(12, 4)` 不用 `Float`?
- Python `float` 是 IEEE 754 double precision,**~16 位精度**
- 看起來夠?但是 `0.1 + 0.2 = 0.30000000000000004` 這種 binary 表示誤差累積會出包
- 金融場景 ALWAYS 用 `Decimal` / `Numeric`,跟錢沾邊絕對不 float
- **interview 必問**:「為什麼用 Numeric?」答案:「accuracy in monetary calculations — IEEE 754 has binary representation errors that compound」

#### 為什麼 INSERT ... ON CONFLICT 而不是 per-row catch IntegrityError?
- M3 的 `event_writer` 用 per-row catch,因為 events 是低頻(每 source ~10 筆/run)
- price_snapshots 是高頻(2000+ 筆/batch),per-row 變成 2000 個 round trip
- PG 的 `ON CONFLICT DO NOTHING` 一次 statement 處理整批,DB-level dedup
- Trade-off:語法是 PG 專屬(MySQL 是 `INSERT IGNORE`),不 portable — 但我們 lock-in PostgreSQL 了

#### 為什麼 backfill 是一個獨立腳本,不是 Celery task?
- One-shot 性質(部署時跑一次)
- 不需要排程
- 跑起來 30 秒,不會卡 worker queue
- 可以直接 `docker exec` 跑、看 log、ctrl-C 取消
- 加入 Celery 反而要處理「上次跑到哪、要不要 resume」這種複雜性

#### 為什麼 market hours 邏輯放在 task 裡,不放在 Beat 排程?
- Cron 不認識 DST。寫 `crontab(hour=14, minute=30)` 夏天就早 1 小時開盤(因為美東變 UTC-4)
- 解法 1:用 timezone-aware cron(Celery 支援,但設定醜)
- 解法 2:**Beat 不斷觸發,task 自己 check** — 簡單可靠
- 成本:off-hours 也會 fire 一次(~25/24 倍呼叫),但 task 立刻 return,無實質成本

#### 為什麼 yfinance 一律用 broad `except Exception`?
- yfinance 是 scraper,**沒有文件化的 exception type**
- 看 source code 會發現它丟 `RuntimeError`、`KeyError`、`AttributeError`、`requests.HTTPError`、`json.JSONDecodeError`...
- 一個個 catch 早晚漏一個,broad except 是務實選擇
- ruff 的 `BLE001` 會 flag,要 `# noqa: BLE001` 並加註解

#### 為什麼 cache miss 時 endpoint 不寫回 cache?
- 直覺寫法:cache miss → 查 DB → 寫 cache → 回應
- 問題:**thundering herd**。cache 過期瞬間,如果 100 個 request 同時打,100 個都會 miss,100 個都查 DB + 寫 cache
- 解法 A:write through(cache miss 時寫 — 我們**沒**選)
- 解法 B:read through with single-flight lock(複雜)
- 解法 C(我們選的):**只有 worker 寫 cache**,reader 純 read。worker 每 5 分鐘刷新一次,過期最多 60 秒 → reader 接受短時間打 DB
- 這個取捨在 spec 沒寫,是我自己決定的

---

### 過程中踩到的坑

#### 坑 1:測試把 events 表 truncate 了
- 跑 `uv run pytest` 之後,Postgres 裡 M3 抓到的 FRED / SEC / FOMC 資料全沒了
- 原因:`conftest.py` 的 `db_session` fixture 每個 test 都 `TRUNCATE events CASCADE`
- 測試和開發共用同一個 DB → 跑測試會洗掉開發資料
- **不算 bug**(spec 沒要求分開),但 production-grade 做法是用獨立 test DB
- 解法 deferred to M8(CI 加上 GitHub Actions service postgres)

#### 坑 2:Anonymous volume 又咬我一次
- 加 yfinance 之後 `docker compose up --build` 預期會帶新套件
- 結果 container 啟動 `ModuleNotFoundError`
- 解法跟 M3 一樣:`--force-recreate --renew-anon-volumes`
- 第二次踩到了 — 該寫成 shell alias 或更新 README
- M9 部署要重新思考 dev volume 策略(可能不該掛 `.venv` 進去,改用 image-only)

#### 坑 3:`auto_adjust=True` 預設行為
- yfinance `Ticker.history()` **預設 auto_adjust=True**,會回溯調整 split / dividend
- 我們要原始 close 給 LLM 看「事件當天的真實價」 — 寫 `auto_adjust=False` explicit
- 沒注意到的話,backfill 出來的歷史價跟 Yahoo 網頁上看到的不一樣
- 寫進 code 同時加 comment 解釋,避免未來 reviewer 不小心改掉

---

### 學到的觀念

1. **Pydantic 不是萬靈丹**:在高頻熱路徑 dataclass 更適合。Pydantic 強在「邊界 validation」,內部資料流不需要

2. **`Decimal` vs `float`** 是金融開發的第一課:**碰錢一律 Decimal**。Numeric(precision, scale) 對應 Postgres `NUMERIC`,精度有上限保證

3. **`INSERT ... ON CONFLICT`** 是 PG 的殺手 feature。MySQL 有 `INSERT IGNORE` / `ON DUPLICATE KEY UPDATE`,SQL standard 有 `MERGE`。語法不一樣,概念相同 — bulk upsert

4. **Time zones 不要硬編 offset**:總是用 IANA zone name(`America/New_York`),Python `zoneinfo` 會自動讀 OS 的 tz database 處理 DST。寫 `UTC-5` 春夏就錯了

5. **Cache 寫入策略是 trade-off**:write-through、read-through、write-behind 各有應用場景。我們的 case「**worker 主動 push,reader 純讀**」是 read-heavy + 可容忍少量 stale 的最簡解

6. **`zoneinfo` 是 Python 3.9+ stdlib**:取代 pytz。pytz 的 API 有歷史包袱(`tz.localize(naive_dt)` 而非直接 `datetime(..., tzinfo=tz)`),zoneinfo 才是現代寫法

---

### 面試可能會被問到

**Q1: 為什麼用 `Numeric(12, 4)` 不用 `Float` 存價格?**
- IEEE 754 double 有 binary 表示誤差(`0.1 + 0.2 ≠ 0.3`)
- 大量小數累加會放大誤差
- 金融計算的 industry standard 是用 Decimal / NUMERIC
- 真實案例:有交易系統因為 float 把 $1,000,000.00 算成 $999,999.99 被 audit

**Q2: 你的 cache 為什麼是 worker write,reader read?**
- Read-heavy 場景的 thundering herd 防護
- Cache 過期那一刻,如果 100 個 reader 同時 miss,全部去 DB + 寫 cache → DB 瞬間高負載
- 我們把寫 cache 集中到 worker(每 5 min 一次,單實例),reader 純 read miss 直接 fallback DB
- 不是業界唯一做法,有些團隊用 read-through + Redis SET NX 鎖,但更複雜
- 我們的 trade-off:**接受 reader 在 cache 過期 ~60s 內走 DB,換 cache 寫入路徑單純**

**Q3: 為什麼 ON CONFLICT DO NOTHING 比 try/except IntegrityError 好(在 high volume 場景)?**
- per-row try:每筆 INSERT 都是一個 round trip,N rows = N round trips
- 一個 round trip ~1-5ms(本地)、~10-50ms(跨 region)
- 2000 rows × 10ms = 20 秒。**ON CONFLICT 是 1 個 round trip,150ms**
- 100x 差距

**Q4: yfinance 不穩怎麼處理?**
- 三層防護:
  1. **broad except Exception**:adapter 函式失敗就 return `[]`,worker 不 crash
  2. **per-row try**:某幾 row 壞掉不影響整批
  3. **at-least-once delivery**:下個 schedule cycle 自然重試
- 加上 backfill 是 idempotent,人工 rerun 也行
- yfinance 改 API 時:tests 雖然 mock,但 production 會 silent fail(空 list)。應該加 monitoring 看「連續 N 次抓到 0 筆」alert(M11 的事)

**Q5: market hours 為什麼放在 task 裡?可以放在 Beat schedule 嗎?**
- 可以,但 cron 表達式對 DST 很笨
- 寫死 `hour=14` UTC,夏天會在美東 10:00 開始抓(晚 30 分)、冬天 9:00(早 30 分)
- Celery 支援 timezone-aware schedule(`celery_app.conf.timezone = "America/New_York"`),但會影響所有 schedule
- 把 gate 放 task 裡是「**讓 schedule 簡單,讓邏輯複雜**」的選擇,降低 cron 表達式心智負擔

**Q6: 為什麼 PriceSnapshot 用 BigInteger PK 不用 UUID?**
- High volume 表(100K rows/day):
  - UUID 16 bytes vs BigInt 8 bytes → 一年差 ~30GB index 大小
  - UUID 隨機分布 → B-tree index 寫入位置分散 → 寫入 amplification
  - BigInt sequential → 寫到 B-tree 最右側 → cache-friendly
- 低 volume 表(events,~50/day):UUID 的好處(全域唯一、不洩漏業務 ID、適合分散式)勝
- **依據 volume 跟 access pattern 選 PK type**,沒有「永遠用 X」的答案

---

### 驗收狀態

- [x] `docker compose up` 5 個 service healthy
- [x] Worker 註冊 5 個 task:`fetch_fred_cpi_task`、`fetch_sec_edgar_task`、`fetch_fomc_task`、`fetch_earnings_task`、`fetch_prices_task`
- [x] Beat 載入 5 個 schedule
- [x] `docker exec backend python -m app.scripts.backfill_prices` 一次跑完,9 tickers × 251 days = **2259 price snapshots**
- [x] `GET /api/v1/prices/AAPL/latest` → `{"price":"308.8200","source":"cache"}`(cache hit)
- [x] 手動清 cache → 同 endpoint 回 `"source":"db"`(DB fallback)
- [x] `GET /api/v1/prices/UNKNOWN/latest` → 404
- [x] `fetch_earnings_task` 跑出 NVDA 2026-04-30 財報事件(EPS 1.87, est 1.77, surprise 0.1%)
- [x] DB 最終狀態:events 4 sources / price_snapshots 2263 rows
- [x] 38 個 pytest 全綠(M3 的 18 → M4 的 38)
- [x] Ruff lint + strict mypy clean

---

## Milestone 5 — LLM analysis

> **狀態**:✅ 完成
> **目標**:接 OpenAI + Anthropic + `instructor`,新 `predictions` 表,Analyzer worker(FETCHED events → LLM 預測 → ANALYZED),model router、cost tracking、daily cap。
>
> 📝 **後續更新**:M5 寫的 prompt v1 / 單一 prediction model / 單純 direction-only 結構,在 M9 上線後一系列 commit 裡被改寫過。詳見 [Milestone 9.5 — Production hardening + analyzer overhaul](#milestone-95--production-hardening--analyzer-overhaul)。本節內容保留作歷史紀錄。

### 做了什麼(依檔案分類)

#### `backend/pyproject.toml`
- 加 `openai>=1.55.0`、`anthropic>=0.40.0`、`instructor>=1.7.0`
- `instructor` 是把 OpenAI / Anthropic SDK patch 過,**讓 LLM 直接回 Pydantic model**(LLM 回 malformed JSON 時自動 retry)

#### `backend/app/db/models.py`(新 model)
- 新 `Prediction` model 對應 spec §6.2 + 加 `llm_cost_usd` 欄位:
  - `id: UUID PK`(低頻表,跟 events 一樣選擇)
  - `event_id` FK 到 events,`ondelete=CASCADE` — 刪 event 自動刪預測
  - `direction` / `magnitude` 用 `StrEnum`(PG ENUM type)
  - `confidence: Float`(不是 Decimal — 不做金錢計算)
  - `llm_provider` / `llm_model` / `prompt_version` 都存進 row → 之後可以 group by 比較準確率
  - `llm_cost_usd: Float` 給 daily cap 用
- Event model 加 `predictions: Mapped[list["Prediction"]] = relationship(..., lazy="raise")`
  - `lazy="raise"` 強制呼叫方明確 `selectinload(Event.predictions)` → 避免 async 環境下的 N+1 lazy load 災難

#### `backend/alembic/versions/bb5f83a02cf9_add_predictions_table.py`
- `alembic revision --autogenerate` 產生
- 兩個 ENUM types(prediction_direction、prediction_magnitude)
- 兩個 index(event_id 給 join,(ticker, predicted_at) 給「找最近 N 個 AAPL 預測」)

#### `backend/app/config/settings.py`(加欄位)
- `openai_api_key`、`anthropic_api_key`(optional)
- `llm_default_model = "gpt-4o-mini"`、`llm_premium_model = "gpt-4o"`
- `llm_daily_cost_cap_usd = 1.0` — hard cap
- `llm_analyzer_batch_size = 20` — 每次 task 跑多少 event(限制 task 時長)

#### `backend/app/llm/schemas.py`(新)
- `TickerImpact`:單一 ticker 的預測結構
  - `direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]` — `Literal` 比 `Enum` 對 LLM 更友善(generated JSON schema 直接是 string enum)
  - `magnitude: Literal["LOW", "MEDIUM", "HIGH"]`
  - `confidence: float = Field(ge=0.0, le=1.0)` — Pydantic 在 LLM 輸出時就驗證
  - `reasoning: str = Field(max_length=500)` — 強制 LLM 只給一句話,別寫散文
- `EventAnalysis`:整個 event 的分析,含 `summary` + `list[TickerImpact]`
- 兩個都 `frozen=True`(value object)

#### `backend/app/prompts/event_analysis_v1.txt`(新)
- v1 prompt,**versioned**:之後改 prompt 要 v2 v3...,舊預測保留原本 prompt_version
- 內容:
  - 直接餵 event payload JSON(不要 paraphrase)
  - 列出 watchlist tickers
  - 強調「**沒有 plausible impact 就 NOT include**,empty list 是合法的」
  - 強調 confidence 是對 **direction** 的把握,不是 magnitude
  - 限制 reasoning 一句話

#### `backend/app/llm/clients.py`(新)
- `instructor.from_openai(AsyncOpenAI(...))` / `instructor.from_anthropic(AsyncAnthropic(...))`
- Module 層 lazy singleton:`_openai_client` / `_anthropic_client`
- 兩家共用介面 `analyze_event(choice, prompt) -> LLMCallResult`
- `LLMCallResult` 含 parsed `EventAnalysis` + token counts(算 cost 用)
- **`create_with_completion`** 而非 `create`:同時回傳 parsed Pydantic + raw response,可以從 raw 拿 `usage` token counts
- OpenAI 跟 Anthropic 的 `usage` 屬性名字不一樣(`prompt_tokens` vs `input_tokens`),這層幫你 normalize

#### `backend/app/llm/router.py`(新)
- `choose_model(source, event_type, today_spend_usd) -> ModelChoice`
- 規則:
  - `(FOMC, FOMC_STATEMENT)` 或 `(FRED, ECONOMIC_RELEASE)` → premium (gpt-4o)
  - 其他 → default (gpt-4o-mini)
  - **`today_spend_usd >= cap` → 一律 downgrade 到 default,log warning**
- 不從 model name 推 provider(`claude-...` → anthropic,其他 → openai)
- 純函式,3 個 input → 1 個 output,**極好測試**

#### `backend/app/llm/cost.py`(新)
- Hardcoded pricing table(USD per 1M tokens)— 含 gpt-4o-mini / gpt-4o / claude-haiku / claude-sonnet-4-5 / claude-opus
- `estimate_cost_usd(model, prompt_tokens, completion_tokens) -> float`
- `today_spend_usd(db)`:`SUM(llm_cost_usd) WHERE predicted_at >= UTC midnight today`
  - 用 UTC 不用 local time → 部署到不同 region 不會對 day boundary 產生分歧
- Unknown model → cost 0 + log warning(test 不用 mock pricing)

#### `backend/app/services/analyzer.py`(新)— **M5 心臟**
- 實作 DB-driven state machine(spec §8):**FETCHED → ANALYZED 或 FAILED**
- **Queue-table pattern with FOR UPDATE SKIP LOCKED**(下面詳述):
  - 先 cheap SELECT 拿 N 個 candidate event IDs
  - 對每個 ID **開新 transient session**,SELECT FOR UPDATE SKIP LOCKED 鎖住
  - 鎖到 → 跑 LLM、寫預測、commit 釋放鎖
  - 鎖不到(其他 worker 在處理)→ skip
- LLM 失敗時 event 設 FAILED + 寫 failure_reason(operator 可以查)
- **Hallucination filter**:LLM 回非 watchlist 的 ticker(`HALUC`)→ 警告 + 丟掉那一 impact
- Cost 只算給第一個 prediction,其他設 0(sum 還對,避免 0.0001 USD 分數毛錢)

#### `backend/app/tasks/analyzers.py`(新)
- Celery task `analyze_pending_task`
- 跟前面其他 task 一樣的 sync-wrap-async pattern
- 用獨立的 `analyze_queue`

#### `backend/app/workers/celery_app.py`(修改)
- include `app.tasks.analyzers`
- `task_routes` 加 `app.tasks.analyzers.*` → `analyze_queue`
- Beat schedule 加 `"analyzer-1min"`:`crontab(minute="*")` 每分鐘 fire
- (Spec acceptance:event 出現後 ≤2 分鐘要有預測 → 1-min 排程綽綽有餘)

#### `docker-compose.yml`(加 service)
- 新 `analyzer` service:獨立 worker,**只 listen `analyze_queue`**,`--concurrency=2`
- 為什麼分開:LLM call 慢(~1-2s/次)+ 有 rate limit,跟 fetcher(IO-bound,可以高 concurrency)分開避免互相干擾

#### `backend/app/schemas/prediction.py` + `backend/app/api/routes/predictions.py`(新)
- `GET /api/v1/predictions/{id}` → 單一 prediction 詳情

#### `backend/app/api/routes/events.py`(擴充)
- 新 `GET /api/v1/events/{id}` → event + predictions
- 用 `selectinload(Event.predictions)` 做 eager loading → **1 + 1 query**(不是 N+1)
- response 包成 `EventDetailResponse { data: EventRead, predictions: [PredictionRead] }`

#### `backend/.env` / `.env.example`
- 加 OPENAI_API_KEY、ANTHROPIC_API_KEY、LLM_DAILY_COST_CAP_USD、LLM_DEFAULT_MODEL、LLM_PREMIUM_MODEL

#### 測試(38 → 57 個全綠)
- `test_llm_schemas.py`(5 tests):TickerImpact 合法/拒絕 out-of-range confidence/拒絕未知 direction、EventAnalysis empty impacts OK、summary 長度 cap
- `test_llm_router.py`(6 tests):high-stakes 拿 premium、routine 拿 default、over-budget downgrade、provider 從 model name 推、CPI 算 high-stakes、earnings 算 routine
- `test_llm_cost.py`(4 tests):gpt-4o-mini 算對、gpt-4o 算對、unknown model = 0、case-insensitive lookup
- `test_analyzer.py`(4 integration tests):FETCHED → ANALYZED、LLM 失敗 → FAILED + reason、hallucinated ticker 被丟、only picks FETCHED status

---

### 過程中踩到的坑(M5 最重要的故事)

#### 坑 1:Concurrency race condition — duplicate predictions
**症狀**:第一次跑完,20 events 卻有 58 predictions,有些 event 出現 4 次預測。

**根因**:
- Analyzer worker 設 `--concurrency=2`(兩個並行 task 槽)
- Beat 每分鐘 fire 一次 → schedule 跟我手動 `celery call` 重疊
- 兩個 task instance 同時跑,都做 `SELECT WHERE status=FETCHED` → 拿到**完全一樣的 20 個 events**
- 各自送 LLM、各自寫 predictions → 重複

**第一次嘗試的修法**(不夠):加 `SELECT ... FOR UPDATE SKIP LOCKED`
```python
events = await db.scalars(
    select(Event)
    .where(Event.status == EventStatus.FETCHED)
    .limit(batch_size)
    .with_for_update(skip_locked=True)
)
```

**為什麼這樣不夠**:我們的 `_process_one` 每處理完一個 event 就 commit。`commit()` 會釋放**該 transaction 的所有 lock**,不只是已完成那一筆。所以:
- Task A: SELECT FOR UPDATE → lock rows 1-20
- Task A: process row 1, commit → **rows 1-20 lock 全部釋放**
- Task B: SELECT FOR UPDATE → lock rows 2-20(它們又開放了)
- Task A: process row 2 → UPDATE row 2 → 跟 Task B 衝突...

**真正的修法**:重寫 `analyze_pending` 成 **per-event transaction** 模式:
```python
candidate_ids = await _candidate_event_ids(db, batch_size)  # cheap read-only

for event_id in candidate_ids:
    async with transient_session() as task_db:   # 全新 transaction per event
        event = await task_db.scalar(
            select(Event)
            .where(Event.id == event_id, Event.status == EventStatus.FETCHED)
            .with_for_update(skip_locked=True)
        )
        if event is None:
            skipped_locked += 1
            continue
        await _process_one(task_db, event, spend_today)
        await task_db.commit()
```

每個 event 自己一個 transaction = 自己一個 lock scope。其他 worker 跑同一個 event 時 SELECT 會回 None(SKIP LOCKED 略過),乾淨 skip。

**驗證**:reset DB,fire 3 個 analyzer task 平行 → **20 unique events, 35 predictions, 0 duplicates**

這是 **distributed systems 經典 queue-table 模式**,任何要實作 worker pool + 共享 task table 的系統都遇得到。

#### 坑 2:Anonymous volume 第三次咬人
- 加 LLM deps 之後 `docker compose up --build -d` → analyzer container `ModuleNotFoundError: instructor`
- 第三次了。一定要 `--force-recreate --renew-anon-volumes`
- 該寫成 makefile target 了:`make rebuild` 包好正確 flags

---

### 為什麼這樣選(關鍵決策)

#### 為什麼用 `instructor` 而不是手動 parse LLM JSON?
- 沒 instructor:你寫 prompt 「請回 JSON」、LLM 偶爾回 markdown ```json ... ```、偶爾少一個 brace、偶爾欄位名拼錯
- 你要手寫 retry loop + json.loads + KeyError 防禦
- instructor 全包了:JSON schema 從 Pydantic model 自動產生 → 餵給 OpenAI 的 function calling / structured output → 解析失敗自動 retry(把 validation error 丟回給 LLM 改)
- 程式碼從 ~50 行手刻變成 3 行

#### 為什麼 `Literal` 而不是 `Enum` 給 LLM schema?
- `Literal["BULLISH", "BEARISH", "NEUTRAL"]` → 產生的 JSON schema 是 `{type: string, enum: [...]}`
- LLM 看到 enum 就乖乖挑一個
- 用 `class Direction(StrEnum)` 也可以,但 `Literal` 更輕量、更直接表達意圖
- DB 那邊用 `StrEnum`(PG ENUM type 要),LLM 這邊用 `Literal`(prompt schema 要),分工

#### 為什麼 cost 只算給第一個 prediction?
- 一個 LLM call 產生 N 個 prediction(N = impacts 數量)
- 平均分:0.0001 / 3 = 0.0000333 — 小數第 7 位,沒意義
- 全算給第一個:**daily SUM 還是對的**,sum-by-day 的 use case 不受影響
- per-prediction cost analytics 變得不準?反正 LLM call cost 是 per-event 的，把 per-prediction 拆分本來就是 fake granularity

#### 為什麼 analyzer 不用 fetcher 那種 `autoretry_for=HTTPError`?
- LLM SDK 自帶 retry(network、rate limit)
- 失敗大多是「**這 event payload LLM 看不懂**」或「**JSON 格式爛**」— 重試不會變對
- 直接 mark FAILED + log + 等 operator 看(可能改 prompt v2)
- 真的是「OpenAI 整個掛 1 小時」這種情境,Beat 1-min 排程下次跑會自然重試 still-FETCHED 的 events

#### 為什麼有 `failure_reason` 欄位?
- FAILED 沒有原因 = 黑箱,operator 不知道為何掛
- 寫進 DB(不只 log)→ web UI 之後可以列「最近失敗的 events,點開看為何」
- M5 沒 UI,但欄位先準備好,M7 直接用

#### 為什麼 daily cap 是 downgrade 不是 hard stop?
- Hard stop = 整個 LLM pipeline 停 → 系統沒新預測 = 看起來像壞了
- Downgrade = 仍有預測,只是用便宜 model → 還能 demo,只是 marginal 準確率降
- log warning 讓 ops 注意到
- spec §9「if exceeded, downgrade all to gpt-4o-mini and log warning」明確要求

---

### 學到的觀念

1. **Queue table 是 backend 經典 pattern**:用 DB 表當 task queue,worker 用 `SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1` 拿任務。比 Celery + Redis 簡單,但併發控制要小心。我們的 events 表就是 implicit queue,status 欄位就是任務狀態。

2. **`FOR UPDATE` 跟 transaction scope 綁定**:lock 是 transaction 級的,commit 一次釋放全部。要 fine-grained lock 就要 fine-grained transaction。

3. **`instructor` = LLM 界的 Pydantic-FastAPI**:把「型別契約」這個概念套到 LLM 上。Schema 是 source of truth,LLM 必須遵守。

4. **Versioned prompt 是必要的**:`prompt_version="v1"` 寫進 DB → 改 prompt 後可以「**比較 v1 vs v2 的預測準確率**」(M6 / M8 用)。沒這個欄位之後分析像在霧裡看花。

5. **Provider-agnostic 設計值得**:`ModelChoice.provider` + `analyze_event(choice, ...)` → 切換 OpenAI / Anthropic 只改 model name。今天 OpenAI 漲價、明天 Anthropic 出更好的 model — 都不用改 code。

6. **`lazy="raise"` 是 async ORM 的救星**:預設 lazy load 在 async session 會炸(因為要 sync access)。`raise` 強制 explicit `selectinload`,把 bug push 到 dev time 而不是 production。

---

### 面試可能會被問到

**Q1: 你怎麼確保 LLM 不會幻覺?**
- 三層防護:
  1. **Schema-enforced output** via instructor:Direction/Magnitude 是 enum,LLM 不能回 "MAYBE_UP"
  2. **Confidence 範圍**:Pydantic 擋 0-1 之外
  3. **Hallucination filter**:LLM 給的 ticker 不在 watchlist 就 drop + log
- 沒辦法 100% 防,但這三層擋掉 99% 常見問題

**Q2: 為什麼你的 queue 用 DB 表不用 Redis Streams / RabbitMQ?**
- 我們 events 表本來就在那 — 加個 status 欄位就變 queue,不引入新組件
- 規模小(<100 events/小時)— DB 性能足夠
- 好處:**事件本體 + queue 狀態原子性**(同一 transaction)
- 大規模(>10k/秒)會換 Kafka,但我們不是

**Q3: 你說 FOR UPDATE SKIP LOCKED 是 queue-table 標準做法 — 講一下這個 SQL?**
- `FOR UPDATE`:鎖住 SELECT 出來的 rows,其他 transaction 想 UPDATE 會等
- `SKIP LOCKED`:看到已鎖的 rows 直接跳過,不等
- 加起來:多個 worker 平行 SELECT,各自拿一批不同的 rows,**沒人等沒人撞**
- Postgres 9.5+ 才有 SKIP LOCKED;MySQL 8+ 也支援
- 經典用法:「**N 個 worker 從同一張 task 表搶任務**」

**Q4: prompt v1 → v2 怎麼遷移?**
- 不要 in-place 改 prompt — 改的話舊預測沒辦法跟新預測比
- 流程:
  1. 寫 `event_analysis_v2.txt`,bump `PROMPT_VERSION = "v2"`
  2. 重新 analyze 已存在的 events(可選),新預測 prompt_version="v2"
  3. 之後 new event 都用 v2
- Analytics:`SELECT alignment_rate FROM ... GROUP BY prompt_version` 看 v1 vs v2

**Q5: 你的 cost cap 怎麼處理跨 timezone?**
- UTC midnight 是 day boundary
- 為什麼不用 server local time:多 region 部署會對 day 不一致(US 早上是亞洲晚上)
- UTC 是 single source of truth,**所有 metric 都該用 UTC,顯示給人看時再轉**

**Q6: 如果 OpenAI 連續 30 秒回 429 (rate limit) 怎麼辦?**
- OpenAI SDK 預設有 exponential backoff retry,撐得住短暫 burst
- 真的撐不住 → exception 上拋 → analyzer mark event FAILED
- Beat 下次 fire → 看到 FAILED 不會重試(設計選擇,避免 infinite retry)
- 真的要 retry,operator 手動 `UPDATE events SET status='FETCHED' WHERE id=...`
- 未來可以加「retryable failure」狀態 — 但 MVP 不需要

---

### 驗收狀態

- [x] `docker compose up` 6 個 service healthy(postgres / redis / backend / worker / **analyzer** / beat)
- [x] Analyzer worker 註冊 5 個 task(雖然只跑 analyze_pending_task,因為 -Q analyze_queue 限定)
- [x] Beat 載入 6 個 schedule
- [x] 真實 OpenAI call 端對端通過 — gpt-4o-mini 跟 gpt-4o 都跑過
- [x] **20 FETCHED events → 3 parallel analyzer tasks → 0 duplicates** (race fix 確認)
- [x] FOMC + CPI 自動拿 premium model(gpt-4o,$0.0028/event)
- [x] SEC 8-K 拿 default model(gpt-4o-mini,$0.00015/event)
- [x] 預測內容合理:AMZN 8-K → AMZN BULLISH、FOMC statement → SPY+QQQ BEARISH
- [x] 整批驗證總成本 **$0.046**(20 events,遠低於 $1 cap)
- [x] `GET /api/v1/events/{id}` 回 event + nested predictions(eager loaded)
- [x] `GET /api/v1/predictions/{id}` 回單一 prediction
- [x] 57 個 pytest 全綠(38 → 57)
- [x] Ruff lint 0 errors

---

### 真實預測範例

```
SEC_EDGAR (8K_FILING):
  AMZN 8-K filed 2026-05-22 (items: 5.07)
  → AMZN BULLISH HIGH conf=0.80
    reasoning: significant corporate developments may increase investor confidence
    model: gpt-4o-mini cost=$0.000151

FOMC (FOMC_STATEMENT):
  Federal Reserve issues FOMC statement  ← 觸發 premium router
  → SPY BEARISH MEDIUM conf=0.70
  → QQQ BEARISH MEDIUM conf=0.70
    reasoning: FOMC's tightening signals will pressure equity / tech indices
    model: gpt-4o cost=$0.0028

FRED (ECONOMIC_RELEASE):
  CPI release for 2026-04-01: 332.407  ← 觸發 premium router
  → SPY BEARISH MEDIUM conf=0.80
  → QQQ BEARISH MEDIUM conf=0.80
    reasoning: higher CPI = inflation concern = pressure on broad market
    model: gpt-4o cost=$0.0029
```

---

## Milestone 6 — Validation loop

> **狀態**:✅ 完成
> **目標**:新 `prediction_outcomes` 表 + Validator worker → 把「事件 → 預測 → 真實結果」的閉環收起來。每個 prediction 在 +1h / +24h / +7d 三個時間窗自動計算 excess return + alignment。`GET /accuracy` 查整體準確率。
>
> 📝 **後續更新**:M6 寫的 **excess-return / SPY-as-baseline / H1+H24+D7 三窗**,在 M9.5 都被改了 — 現在 alignment 直接看 raw return,outcome window 只剩 H24 + D7。詳見 [Milestone 9.5](#milestone-95--production-hardening--analyzer-overhaul) 的「Alignment refactor」跟「Outcome windows 改造」兩節。本節內容保留作歷史紀錄,有助於了解設計演化過程。

### 做了什麼(依檔案分類)

#### `backend/app/db/models.py`(加 model + enum)
- 新 `OutcomeWindow(StrEnum)`:`H1="1h"`、`H24="24h"`、`D7="7d"`
- 新 `PredictionOutcome` model 對應 spec §6.4:
  - `id: UUID PK`(低頻表)
  - `prediction_id` FK,`ondelete=CASCADE` — 刪 prediction 自動清 outcome
  - `window: OutcomeWindow` enum
  - `baseline_price` / `end_price: Numeric(12,4)` — 跟價格表一致
  - `ticker_return` / `spy_return` / `excess_return: Float` — 純數字,不再做金錢計算
  - `aligned: Boolean` — 預測對不對的判定
  - **`UniqueConstraint("prediction_id", "window")`** — idempotency 兜底
- `Prediction` 加 `outcomes` relationship + `lazy="raise"`

#### `backend/alembic/versions/21601dff6066_add_prediction_outcomes_table.py`
- autogenerate 產生
- 一個 ENUM type(outcome_window)、兩個 index(by prediction_id, by validated_at)

#### `backend/app/services/alignment.py`(新)— **純函式邏輯,最高測試覆蓋**
- `ticker_return(baseline, end)` — `(end - baseline) / baseline`
  - baseline ≤ 0 → raise(防止 div by zero 神祕 inf)
- `excess_return(ticker_ret, spy_ret)` — `ticker_ret - spy_ret`
- `is_aligned(direction, excess)`:
  - BULLISH + excess > 0 → True
  - BEARISH + excess < 0 → True
  - NEUTRAL + `|excess| < 0.005` → True(spec §6.4 神祕的 NEUTRAL 0.5% 閾值)
  - 其他 → False
- 全部沒 DB、沒 mock,16 個 unit test 全部 trivial pass

#### `backend/app/services/validator.py`(新)— M6 心臟
- `validate_pending(db, batch_size=50)`:
  1. 算 candidate `(prediction, window)` pairs:`predicted_at + window + 15min buffer <= now()` 且還沒有對應 outcome row
  2. 對每個 pair 開**獨立 transient session**,跟 M5 analyzer 一樣的 queue-table pattern + `FOR UPDATE SKIP LOCKED`
  3. 查 baseline + end 兩個價格(自己 + SPY)
  4. 缺價 → defer(下次 retry,不寫假資料)
  5. 算 returns,呼叫 `is_aligned`,寫 outcome
- 三個 tunable 常數:
  - `_PRICE_AVAILABILITY_BUFFER = 15min`(等價格 worker 寫完)
  - `_WINDOW_DURATIONS` 對應 1h/24h/7d
  - `_PRICE_LOOKBACK_TOLERANCE`:1h 給 1h、24h 給 24h、7d 給 4天(跨週末)
- **`_price_at_or_before(ticker, target, tolerance, must_be_after)`**:
  - 找 `snapshot_at <= target` 且 `snapshot_at >= target - tolerance` 的最新一筆
  - `must_be_after` 是 end-price 才設的安全鎖(下面講 bug)

#### `backend/app/tasks/validators.py`(新)
- `validate_pending_task` Celery task,5-min schedule
- 路由到 `validate_queue`(新 queue)

#### `backend/app/workers/celery_app.py`(改)
- include `app.tasks.validators`
- task_routes 加 `validate_queue`
- Beat schedule 加 `validator-5min`

#### `docker-compose.yml`(改)
- fetch worker 改 listen `-Q fetch_queue,validate_queue`(共享 worker pool,validate 也是 I/O bound)
- 比另外起一個 validator container 簡單,需要時可拆

#### `backend/app/api/routes/accuracy.py`(新)
- `GET /api/v1/accuracy` 支援 4 個 query filter:`source` / `ticker` / `window` / `model`
- SQL:`SELECT COUNT(*), SUM(aligned::int) FROM outcomes JOIN predictions JOIN events`
- Response 結構:`{total_outcomes, aligned_count, alignment_rate, filters}`
- **`alignment_rate=None` when total=0** — 不要回 0% 騙人(沒資料 ≠ 全錯)
- 把 ticker 自動 .upper() 接受大小寫

#### 測試(57 → 81 個)
- `test_alignment.py`(16 unit):
  - `ticker_return` 正/負/零/baseline ≤ 0
  - `excess_return` 三種市場情境
  - `is_aligned` 各 direction × 各 excess 符號 + NEUTRAL 邊界(`= threshold` 不算 aligned)
- `test_validator.py`(5 integration):
  - 25h 前預測 + 雙時間點價格 → 寫 24h outcome,return 計算正確,aligned=True
  - 30min 前預測(1h 還沒到)→ candidates=0,沒寫
  - 缺 end price → deferred,沒寫假資料
  - 重跑 idempotent(unique constraint 兜底)
  - BEARISH + ticker 跑輸大盤 → aligned=True

---

### 過程中踩到的坑

#### 坑 1:tolerance 太鬆讓 baseline 自己當 end_price
- **症狀**:integration test `test_missing_price_defers_not_writes` 預期 `deferred ≥ 1`,實際 `deferred=0, written=2`
- **根因**:test 只 seed 了 baseline 時間的價格(沒有 end 時間)。validator 查 end_price 時,因為 tolerance 24h,接受了 24h 前的價格(就是 baseline)。結果 `ticker_return = (baseline - baseline) / baseline = 0`,寫了個假的 0% outcome
- **修法**:`_price_at_or_before` 加 `must_be_after` 參數,end-price 查詢時要求 `snapshot_at > predicted_at`。Baseline 不傳這個 → 跟以前一樣寬鬆
- **教訓**:**寫測試的時候腦袋裡要有「壞情境」 — 沒這個 test 寫,production 就出現假 outcome**

#### 坑 2:Postgres 不能 `bool → float` 直接 cast
- **症狀**:`GET /accuracy` 回 500 — `cannot cast type boolean to double precision`
- **根因**:`func.sum(cast(aligned, Float))` — PG 不允許 bool 直接到 float
- **修法**:`cast(aligned, Integer)` 中間轉一道,再讓 Python 做最後除法
- **教訓**:**SQLAlchemy 抽象層下的 SQL 還是有 DB-specific 限制,跨 DB 寫法要試**

#### 坑 3:Demo 資料時區/週末陷阱
- 跑 e2e 時把 predictions backdate 到 `NOW - 3 days`
- 結果發現 3 天前 = 2026-05-23 = **週六**(無交易資料)
- 1h 跟 24h 窗都 defer(找不到當時的價格),只有 D7 窗成功(tolerance 4 天反向找到今天的資料)
- **教訓**:**真實金融資料不是連續的**,Demo 要選平日或包好跨週末邏輯

---

### 為什麼這樣選(關鍵決策)

#### 為什麼用 DB polling 而不是 Celery ETA?
- Spec §11 M6 寫「Schedule outcomes at +1h, +24h, +7d using Celery ETA」
- 但 spec §0.4 / §8 又強調 DB-driven state machine,不要 Celery chain
- 衝突時我選 DB polling,**理由**:
  - Celery ETA 任務存在 broker — broker 重啟、worker pool 改、queue 名字變,**都會默默丟失任務**
  - DB polling 的 source of truth 是 `predicted_at` + outcome row 存在與否 — restart 任何東西,recompute 都對
  - 「**任何時候系統重啟,DB 就是當前狀態**」這個 invariant 很值錢
- 代價:輪詢有 worst-case 5 min 延遲(不該重要,outcome 本來就有 ≥1h 延遲)

#### 為什麼 outcome 表用 `(prediction_id, window)` unique 不是 PK?
- PK 用 UUID 是 ORM relation 跟 API URL 的 stable identifier
- Unique constraint 是業務邏輯:同一 prediction 同一 window 只能有一個 outcome
- 兩個分開 → 業務 unique 改了不影響 reference

#### 為什麼 NEUTRAL 用「絕對值 < 0.5%」當對齊條件?
- BULLISH/BEARISH 是「**方向有偏好**」,只看 excess return 正負就好
- NEUTRAL 是「**沒大方向**」,如果實際大漲或大跌就是預測錯了
- 0.5% 是 spec §6.4 給的閾值 — 直覺上「一天波動 < 0.5%」算「沒大事」
- 用 `<` 不是 `<=`,邊界值不算對齊(保守)— test 有 cover 邊界 case

#### 為什麼 fetch worker 也聽 validate_queue,不開新 worker?
- 兩者都 I/O bound(DB query + INSERT)
- Validate 沒外部 API call,比 fetch 還輕
- 共享 worker pool 一起搶 — 沒有 starvation 風險
- 將來真需要分,改 docker-compose 一行就拆出來
- **「需要時再拆」勝於「先過度設計」**

#### 為什麼 `must_be_after` 只給 end-price 不給 baseline?
- Baseline 在 prediction 之前的近期數據就是合法的(預測作出時的當下價格)
- End-price 必須 strict 在 prediction 之後 — 不然就 cherry-pick 同一筆 row 當 baseline + end
- 不對稱設計 ≠ 不一致 — 反映了業務語義不對稱

#### `alignment_rate` 為什麼用 `float | None` 不是 `0.0`?
- 0 outcomes 時回 0.0 → user 看到「0% accuracy」會誤以為全錯
- None 明確表示「沒有資料」,前端可以顯示「N/A」
- API 設計通則:**沒資料 ≠ 全錯**,要區分

---

### 學到的觀念

1. **`predict → outcome` 是 ML 系統閉環的價值所在**:沒有 outcome 表,你的 LLM 永遠不知道對不對。**這個閉環是 ML 系統跟 toy demo 的分界線**

2. **Excess return 是金融 alpha 的標準量測**:單看 ticker 漲跌沒意義,要扣掉大盤帶動。alpha 才是真技術價值

3. **「Defer」是合法狀態**:資料還沒到,別寫假東西。Defer + retry > 寫錯。idempotent + unique constraint 讓 retry 安全

4. **時區 + 週末是時間序列軟體永遠的坑**:預設假設「資料連續」會出包。Tolerance / lookback 設計就是吸收這種離散性

5. **`bool::int` 是跨 DB 慣用 cast 路徑**:SUM(bool) 在某些 DB 行某些 DB 不行,先轉 int 最 portable

---

### 面試可能會被問到

**Q1: 為什麼用 polling 而不是 Celery ETA?spec 不是說 ETA 嗎?**
- 我覺得 spec 兩處互相衝突 — §11 提 ETA、§8 強調 DB-driven state
- 我選 DB polling 因為 recoverability — broker / worker / queue config 改了都不丟資料
- 代價是 ~5 min 延遲,但 outcome 本來就 ≥1h 才能算,毫無影響
- 真正 production 級 ETA 要搭 Celery's persistent scheduler 或 Temporal — 增加 dep 跟複雜度

**Q2: NEUTRAL 的閾值為什麼 0.5%?**
- spec 給的數字,我接受
- 直覺解釋:S&P 500 日均波動 ~0.7%,< 0.5% 算「相對平靜」
- 真實生產系統可能要 vol-adjusted(高波動股票閾值放大)
- 把閾值放在 alignment.py 的 module constant — 之後要調很方便

**Q3: 為什麼 outcome 不 store summary fields like "absolute return"?**
- 不要 store derived data — 永遠有不一致風險(算法改了 stored data 不對)
- store 原料(prices + returns),需要時用 query 算 summary
- exception:**aligned bool** 我們 store — 因為它是 alignment function 的結果,跟 prompt_version 一樣是「**那一刻決定的判定**」,需要保留歷史

**Q4: 如果 prediction_outcomes 表變 100M 行怎麼辦?**
- 短期:用 `validated_at` 上的 index 對「最近 24h 的 outcomes」加速 dashboard
- 中期:partition by month — 按 `validated_at` 自動拆 partition,舊資料 drop 整個 partition 即可
- 長期:把 cold 資料移到 OLAP(BigQuery / Snowflake),postgres 只留近 30 天 hot data

**Q5: `excess_return` 計算為什麼用 SPY 不用 QQQ?**
- SPY 追蹤 S&P 500,代表廣義美股
- QQQ 追蹤 Nasdaq-100(科技股為主),代表 sub-market
- 我們 watchlist 7 個都是科技股 + SPY + QQQ — 如果用 QQQ 當基準,NVDA 跟 QQQ 高度相關,excess return 永遠很小
- 用 SPY 才能看出「**科技股相對全市場的超額表現**」 — 這是 alpha 的傳統定義

**Q6: 假如同一個 prediction 的 1h / 24h / 7d outcomes 結果不一致(1h 對、24h 錯)怎麼解讀?**
- 完全可能 — short-term 跟 medium-term reaction 不同
- 例如 8-K 出來瞬間 -1%(BEARISH 對 1h),但 24h 後反彈 +2%(BEARISH 錯 24h)
- 我們**分開存**這 3 個 outcome,讓 dashboard 可以看「**這個 model 在哪個 window 最準**」
- 真實 trading 應用會發現:有些 model 適合短線、有些長線

---

### 驗收狀態

- [x] 5 個 service healthy(沒新增 container,fetch worker 多 listen validate_queue)
- [x] Worker 註冊 7 個 task(fetch 4 + prices 1 + analyzers 1 + validators 1)
- [x] Beat 載入 7 個 schedule
- [x] 81 個 pytest 全綠(M5 的 57 → M6 的 81)
- [x] 對 backdated prediction 跑 validator → 5 個 D7 outcomes 寫入,alignment 數學正確
- [x] `GET /api/v1/accuracy` 回 `{total: 5, aligned: 2, alignment_rate: 0.4}`
- [x] Filter by ticker=SPY → `{total: 3, aligned: 2, rate: 0.667}`
- [x] Filter by window=7d → 跟 overall 一致(因為目前只有 D7 outcomes)

---

### 真實 outcome 範例

```
ticker  direction   window  ticker_ret  spy_ret  excess  aligned
─────────────────────────────────────────────────────────────────
QQQ     NEUTRAL     D7      0.0155      0.0094   0.0061   FALSE  ← NEUTRAL 但實際漲了 1.55%
QQQ     BEARISH     D7      0.0155      0.0094   0.0061   FALSE  ← BEARISH 但 excess 是正的
SPY     NEUTRAL     D7      0.0094      0.0094   0.0000   TRUE   ← SPY vs SPY = 0,NEUTRAL 對
SPY     BEARISH     D7      0.0094      0.0094   0.0000   FALSE  ← BEARISH 但 excess = 0
SPY     NEUTRAL     D7      0.0094      0.0094   0.0000   TRUE
```

注意:SPY 對 SPY 的 excess return 永遠是 0(同一個 ticker)— 我們把 SPY 預測也存進去當 sanity check,**alignment 邏輯對 SPY 永遠只有 NEUTRAL 會 aligned**。這是 model router 的次要學習點:讓 LLM 對 SPY 出 BULLISH/BEARISH 預測沒意義,M5 prompt 之後可以加 「不要對 benchmark ETF 出方向預測」guidance(v2 prompt 候選)。

---

## Milestone 7 — Frontend Sprint 1

> **狀態**:✅ 完成
> **目標**:Next.js 14 App Router(實際拿到 16.2.6)+ Tailwind v4 + TanStack Query → timeline 首頁 + `/events/[id]` detail page,從瀏覽器能看到 M1-M6 全部累積出來的事件與預測。

### 做了什麼(依檔案分類)

#### `frontend/` scaffolding
- `npx create-next-app@latest` 一次性建立 — App Router + TypeScript + Tailwind + ESLint
- **拿到 Next.js 16.2.6**(spec 寫 14,實際是更新的 stable)+ React 19.2 + Tailwind v4 + TS 5
- Scaffold 自動生 `AGENTS.md` / `CLAUDE.md` 警告未來改 code 的人「**Next.js 16 跟你熟悉的不一樣**」— 對 AI agent 友善的設計
- 額外 install:`@tanstack/react-query` + `@tanstack/react-query-devtools` + `date-fns`
- **沒有用 shadcn/ui**:它的 CLI 太互動,piped input 過不去;改自己手刻 4 個小 component 用 Tailwind utility class。對 portfolio 反而加分(展示 Tailwind 直接能力)

#### `frontend/lib/types.ts`(新)
- 手寫 TypeScript types,**對應 backend Pydantic schema**
- 涵蓋:`EventSource` / `EventStatus` / `PredictionDirection` / `PredictionMagnitude` / `OutcomeWindow`
- 完整 response shape:`EventRead` / `PredictionRead` / `EventListResponse` / `EventDetailResponse` / `AccuracyResponse`
- **DECISION:手寫而非 OpenAPI codegen** — 簡單、能 PR review、不引入 build step。M8 會加 codegen 進 CI

#### `frontend/lib/api.ts`(新)
- Thin `fetch` wrapper(沒 axios、沒 SWR client lib)
- `request<T>(path)` 統一處理:`API_BASE` + headers + `cache: "no-store"` + JSON error parsing
- `APIError` class 帶 status + detail,讓 UI 可以區分「沒資料 vs 真的壞」
- `api.listEvents()` / `api.getEvent(id)` / `api.getAccuracy(filters)`
- 用 `NEXT_PUBLIC_API_URL` 環境變數 — Next.js 慣例,`NEXT_PUBLIC_` prefix 才會 ship 進 browser bundle

#### `frontend/lib/utils.ts`
- `cn(...classes)` — 把 Tailwind class 字串組起來,過濾 falsy
- 比 `clsx + tailwind-merge` 簡單;沒有 class 衝突場景所以不需要 merge

#### Components(`frontend/components/`)
- **`SourceBadge.tsx`**:每個 source 一個顏色 — FRED 藍、SEC 紫、FOMC 琥珀、EARNINGS 翠綠。scannability 高
- **`DirectionBadge.tsx`**:BULLISH ▲ 綠、BEARISH ▼ 紅、NEUTRAL ● 灰 — 用 unicode 三角形避免額外圖庫
- **`EventCard.tsx`**:timeline 上的卡片 — source badge + 標題 + 相對時間 + ticker tags。**用 `next/link`** 預先 prefetch 點擊目標頁
- **`PredictionRow.tsx`**:單一 prediction — ticker + direction + magnitude + confidence + reasoning + model 來源
- **`QueryProvider.tsx`**:`"use client"` + `useState(() => new QueryClient(...))` 確保 client 跨 render 不重建,30s `staleTime` 平衡新鮮度與請求量

#### Pages
- **`app/layout.tsx`**:全域 layout + nav bar + QueryProvider 包整個 app
- **`app/page.tsx`** (timeline):`"use client"` + `useQuery(["events"])` → 載入中骨架、錯誤狀態、空狀態三條 path 都有
- **`app/events/[id]/page.tsx`** (server) + **`client.tsx`**:
  - Server 元件 only job 是 `await params`(Next.js 16 breaking change!)
  - Client 元件做 TanStack Query + 渲染
  - 拆兩個檔案是 Next.js 16 upgrade guide 推薦做法

#### CORS — `backend/app/main.py`(改)
- 加 FastAPI `CORSMiddleware`,allowlist `localhost:3000` + `127.0.0.1:3000`
- **不用 `["*"]`**:spec §16 明令禁止 wildcard
- M9 上 Vercel 後會把 Vercel domain 加進去

#### `frontend/.env.local.example` + `.env.local`
- 只有 `NEXT_PUBLIC_API_URL=http://localhost:8000`
- `.env.local` 已被 Next.js 預設 gitignore

---

### Next.js 16 的 breaking change 注意點

scaffold 出來才發現 spec 寫的「Next.js 14」實際是「Next.js 16」,有幾個顯著差異:

1. **`params` / `searchParams` 變 Promise** — 我們的 `/events/[id]` 必須 `await params`
2. **Turbopack 預設 ON** — 不用加 `--turbopack` flag
3. **`next lint` 移除** — 用 eslint 直接跑
4. **Async request APIs 全面強制** — `cookies()` / `headers()` 也要 await
5. **`devIndicators` 部分 option 移除** — 不影響我們

scaffold 附的 `AGENTS.md` 提醒 AI agent「**這不是你熟悉的 Next.js**」— 我先看完 `node_modules/next/dist/docs/01-app/02-guides/upgrading/version-16.md` 再開始寫,避免照 Next 14/15 寫法踩坑

---

### 為什麼這樣選(關鍵決策)

#### 為什麼不用 shadcn/ui?
- 它的 CLI 設計成完全互動,piped input 走不過去;debug 太花時間
- M7 只需要 4-5 個小 component,自己用 Tailwind 寫 ~50 行就好
- shadcn 的價值在於「**copy-paste 你可控的 component code**」— 我們直接寫等同效果
- **不引入「Radix Primitives + React 19 相容性問題」這類額外風險**
- 將來真需要(M8 dashboard 的 chart / dialog)再加

#### 為什麼手寫 types,不從 OpenAPI codegen?
- 對小規模 schema 來說,**hand-written 更容易在 PR 中 review**
- FastAPI 的 `openapi.json` 確實能用 `openapi-typescript` 跑 codegen,但要引入 build step、設定 CI 同步,還會生出 verbose 型別
- M8 會把 codegen 加成 pre-commit hook(確保 frontend/types 跟 backend schema 不漂移)— 那才值得引入

#### 為什麼 `cache: "no-store"` 在所有 fetch?
- Next.js 16 預設 fetch 會被 server-side cache(static page)— 不適合 live data
- Timeline 必須每次刷新都看新資料
- `cache: "no-store"` 是 escape hatch,跟 React Server Component 的預設行為 opt-out
- 真的要 server cache(future:LLM 摘要不變的 event 列表)再用 `revalidateTag`

#### 為什麼 timeline 用 `"use client"` + TanStack Query,不用純 server component?
- 純 server component(`async function Page() { const data = await fetch(...) }`)更省 JS bundle
- 但 TanStack Query 給我們:
  - 自動 stale-while-revalidate(tab 重新 focus 自動 refetch)
  - Cache 命中後 detail page click 瞬間出現(預載)
  - 為 M8 的 polling / live update 鋪路
- Trade-off:多 ~30KB JS bundle。值得換 UX

#### 為什麼 `/events/[id]` 拆成 server `page.tsx` + client `client.tsx`?
- Next.js 16 要 `await params` 是 server-side 行為
- TanStack Query hooks 要在 client component
- 拆兩個檔案:server 只負責 `await params` 轉資料,client 做 hooks
- 這是 Next.js 16 upgrade guide 直接推薦的 pattern
- 替代方案:全 client + `use(params)` unwrap promise — 也能跑,但 server 拆出來 0 JS bundle 給 layout 部分

#### 為什麼 CORS allowlist 而不是 `["*"]`?
- Spec §16 禁止 production 用 `*`
- 開發階段不嚴格但養成習慣最重要
- Cookie / credential 跨 origin 時 `["*"]` 也不能搭 `allow_credentials=True`(瀏覽器擋)
- M9 上 Vercel 後 allowlist 加上 production / preview URL,這個 pattern 直接用

---

### 學到的觀念

1. **「Server Component / Client Component」的拆法是 Next.js App Router 的核心心智模型**:
   - Server:可以 await DB / API,沒 JS bundle
   - Client:可以用 hook 跟瀏覽器 API,要付 bundle 成本
   - 邊界用 `"use client"` directive 標記
   - 拆得好 = 速度快 + bundle 小

2. **Next.js 16 的 Async Request APIs 是長期趨勢**:`params` / `cookies()` / `headers()` 都變 Promise — 為了配合 React Server Component 的 streaming 渲染。短期煩,長期對

3. **TanStack Query 的 `staleTime` 是 cache 策略**:不是「資料活多久」而是「我願意 show 多舊的資料給 user 看」。30s 對 events timeline 剛好

4. **`cache: "no-store"` vs `revalidateTag` vs default**:Next.js 16 的 fetch 預設會被 cache,要顯式 opt-out 給 live data — 容易踩坑

5. **Tailwind v4 跟 v3 設定不同**:v4 用 `@import` + CSS,v3 用 `tailwind.config.js`。我們是 v4,所以沒 `tailwind.config.ts`(放在 globals.css 內)

6. **`"use client"` 是檔案級的,不是函式級**:整個檔案 client,或整個檔案 server(可以 import client component)

7. **`useState(() => new QueryClient())` 的 lazy init 很重要**:不寫 `() =>` 每次 render 都 new 一次 → 整個 cache 重設 → 抓資料反覆閃爍

---

### 面試可能會被問到

**Q1: 為什麼選 TanStack Query 而不是 SWR / Redux Query?**
- **TanStack Query**:functional API、強型別、cache 控制最精細、UI library agnostic
- **SWR**:Vercel 出品,跟 Next.js 配合好,但 API 較陽春
- **Redux Toolkit Query**:跟 Redux 綁定,過度為 backed by store 設計
- 我選 TanStack:**型別最舒服 + 文件最完整 + 跟 React Query 同源**(同一 lib,只是改名)— 招聘 JD 點名最高

**Q2: 為什麼 timeline 不用 Server Component?省 JS bundle 不是更好?**
- Trade-off:純 server 確實少 ~30KB JS,但缺:
  - 沒有 client-side cache(每次 navigate 都重抓)
  - 沒有 tab focus refetch(資料過期看不到提示)
  - 沒辦法做 future 的 live update(WebSocket)
- 對「**事件列表這種 dynamic data + 預期 polling**」場景,client + TanStack 更對

**Q3: `params` 在 Next.js 16 變 Promise,你怎麼處理?**
- Server component:`async function Page({ params }) { const { id } = await params; }`
- Client component:`use(params)` unwrap(React 的 `use` hook)
- 我們拆成 server wrapper(`await params`) + client child — 最乾淨

**Q4: 你的 type 為什麼手寫不用 codegen?**
- 小規模時 hand-written 更易 PR review,structure 一目瞭然
- M8 會引入 `openapi-typescript` codegen 在 CI 跑,防止 frontend / backend type drift
- 真實大型專案會 day-1 就 codegen,我們是 staged 增加複雜度

**Q5: CORS allow_origins 為什麼是 list 不是 `"*"`?**
- `"*"` 配 `allow_credentials=True` 瀏覽器會擋(規範限制)
- 即使不用 cookie,具名 allowlist 更安全 — 別的網站不能伺機從 user 瀏覽器調 API
- production 強制具名,dev 養習慣

**Q6: 為什麼 `useState(() => new QueryClient(...))` 用 lazy init?**
- `useState(value)` 跟 `useState(() => value)` 的差別:
  - 前者每次 render 都計算 value(浪費)
  - 後者只 first render 算
- `new QueryClient()` 不便宜(初始化 cache 結構)
- 沒 lazy init:HMR / Strict Mode 雙渲染時 client 會被 dup 出兩個,cache 互不知道 → 看起來像 cache 全失效

---

### 驗收狀態

- [x] `npm run dev` 起 Next.js 16 + Turbopack on :3000
- [x] `npm run build` production build 通過(TS + Tailwind 沒 error,4 routes 生成)
- [x] Backend 81 個 pytest 仍綠(CORS 加進去沒影響)
- [x] Frontend curl 回 200,HTML 含 `EventSense` brand + `LLM predictions` section header
- [x] `OPTIONS` preflight 含 `access-control-allow-origin: http://localhost:3000`(CORS 正確)
- [x] 4 個 UI 元件 + 2 pages + Provider + types + API client 全部就位

### 真實 UI 行為(瀏覽 http://localhost:3000)

```
首頁 /:
  ┌─────────────────────────────────────────┐
  │ EventSense              events→...      │  ← nav
  ├─────────────────────────────────────────┤
  │ Recent events                  19 total │
  │ ┌─────────────────────────────────────┐ │
  │ │ [FRED] ECONOMIC_RELEASE   2 days ago│ │
  │ │ CPI release for 2026-04-01: 332.407│ │
  │ └─────────────────────────────────────┘ │
  │ ┌─────────────────────────────────────┐ │
  │ │ [SEC_EDGAR] 8K_FILING     5 days ago│ │
  │ │ AMZN 8-K filed 2026-05-22 ...      │ │
  │ │ AMZN                                │ │
  │ └─────────────────────────────────────┘ │
  │ ...                                     │
  └─────────────────────────────────────────┘

/events/<id>:
  ← Back to timeline
  ┌─────────────────────────────────────────┐
  │ [SEC_EDGAR] 8K_FILING     May 22 14:30  │
  │ AMZN 8-K filed 2026-05-22 (items: 5.07)│
  │ Status: ANALYZED · External ID: ...    │
  │ [AMZN]                                  │
  └─────────────────────────────────────────┘
  
  LLM predictions (1)       Total cost $0.00015
  ┌─────────────────────────────────────────┐
  │ AMZN  ▲ BULLISH  HIGH      conf 80%    │
  │ Significant corporate developments...   │
  │ gpt-4o-mini · prompt v1 · $0.00015     │
  └─────────────────────────────────────────┘
  
  ▶ Raw payload (click to expand)
```

---

## Milestone 8 — Frontend Sprint 2 + tests + CI

> **狀態**:✅ 完成
> **目標**:Recharts 價格走勢圖、`/dashboard` 聚合準確率頁、pytest 覆蓋率 > 75%、GitHub Actions CI(ruff + mypy + pytest)。

### 做了什麼(依檔案分類)

#### Backend(配合前端 chart + outcomes 顯示)

- **`backend/app/schemas/outcome.py`**(新):API 用的 `OutcomeRead` schema(對應 `PredictionOutcome` model)
- **`backend/app/schemas/prediction.py`** 加 `PredictionWithOutcomes(PredictionRead)`:nested `outcomes: list[OutcomeRead]`
- **`backend/app/api/routes/events.py`** `/events/{id}` 改用 `selectinload(Event.predictions).selectinload(Prediction.outcomes)` — 三層 eager loading,**1+1+1 query 不是 N+M**
- **`backend/app/api/routes/prices.py`** 加 `GET /prices/{ticker}/range?from_at=&to_at=` — 給 chart 用的時間範圍 query,加 30 天上限避免暴衝
- **`backend/app/main.py`** 改 CORS allowlist 用 list-only(M7 已有,M8 不動)

#### Frontend Recharts 整合
- **`npm install recharts`**(響應式圖表 lib,React 19 相容)
- **`frontend/components/PriceChart.tsx`**(新):
  - 拉兩條 parallel `useQuery`:`api.getPriceRange(ticker, ...)` + `api.getPriceRange("SPY", ...)`
  - **Rebase 邏輯**:每條線除以自己的第一個價格 × 100 → 兩條共用 Y 軸,反映「相對於 prediction 那刻的漲跌幅」
  - **Daily resample**:`resampleDaily` 按 UTC 日期 group by,每天保留最後一筆 → 解決「intraday 1m + 歷史 daily 混在一起鋸齒亂飛」的問題
  - `ReferenceLine` 在 `predicted_at` 畫 indigo 虛線
  - 兩條線:NVDA 黑實線 + SPY 灰虛線
  - SPY query `staleTime: 5min` — 多個 event detail 共用 SPY,不重 fetch
- **`frontend/components/OutcomesTable.tsx`**(新):
  - 三 row 表(1h / 24h / 7d),每 row 顯示 ticker_return / spy_return / excess_return / aligned ✓ 或 ✗
  - 沒對應 outcome 的 window 顯示 `pending validation`(避免「沒資料 = 0」誤導)
  - 顏色:正 return 綠、負 return 紅、aligned 用粗體 ✓/✗
- **`frontend/components/PredictionRow.tsx`** 改:接受 `PredictionRead | PredictionWithOutcomes`,有 outcomes 就嵌 `<OutcomesTable>`

#### Dashboard 頁
- **`frontend/app/dashboard/page.tsx`**(新):
  - Hero 大數字 — `/accuracy` 整體 alignment rate(`alignment_rate=null` 顯示 `N/A`,不騙)
  - `AccuracyBarChart` 元件 — 對每個 source / window 平行 `useQuery`,recharts BarChart 顯示
  - 沒有 outcome 的 source / window 自動從圖表略過(不畫空 bar)
- **`frontend/app/layout.tsx`** nav 加 `Dashboard` link

#### Pytest 覆蓋率
- **`backend/pyproject.toml`** 加 `pytest-cov` dev dep + `[tool.coverage]` 設定
- 跑 baseline:**80% 已超過 spec §14 的 75% 目標**(沒額外寫測試只靠 M1-M7 累積)
- 主要 uncovered 區塊:`tasks/*` (Celery decorator wrapping 難 unit test)、`llm/clients.py`(實際 LLM call,需要 mock OpenAI)、`workers/celery_app.py`(純設定)
- CI gate:`--cov-fail-under=75`(掉破 75% 整個 CI 紅)

#### 新增測試:`tests/integration/test_api_endpoints.py`(8 個)
- 涵蓋 `/events` list / detail / 404、`/accuracy` 含 filter、`/prices/range` 各種邊界
- 用 **`httpx.AsyncClient` + `ASGITransport`** 而非 FastAPI 的 sync `TestClient`(下面講為什麼)
- 用 `app.dependency_overrides[get_db] = transient_session` 注入 NullPool session — 避免 M3/M5 的 event loop binding bug

#### `backend/pyproject.toml` mypy 設定
- 三個 module override:
  - `tests.*`:`disallow_untyped_decorators = false`(pytest fixtures 沒 type)
  - `app.tasks.*` + `app.workers.*` + `app.llm.clients`:`disallow_untyped_decorators = false` + `disable_error_code = ["misc", "name-defined"]`(Celery / instructor 第三方 typing 不完整)
  - `celery.*` / `yfinance` / `defusedxml.*` / `instructor` / `pandas.*`:`ignore_missing_imports = true`(沒 py.typed marker)

#### `.github/workflows/backend-ci.yml`(新)
- triggers:push to main / PR,只 watch `backend/**` 跟自己
- 用 **Postgres service container** 16-alpine,健康檢查通過才進 step
- 安裝 uv → install deps → ruff check → ruff format check → mypy → alembic upgrade head → pytest with `--cov-fail-under=75`
- env vars 用 GH Actions defaults(不需要 secrets,測試 stub 掉真實 keys)

#### `.github/workflows/frontend-ci.yml`(新)
- triggers:push to main / PR,只 watch `frontend/**`
- Node 22 + `npm ci`(strict from lockfile)+ `npm run lint` + `npm run build`(build = TS typecheck + 整個 Turbopack bundle 驗證)

---

### 過程中踩到的坑

#### 坑 1:`fastapi.testclient.TestClient` 也撞 event loop binding(M3/M5 再現)
- **症狀**:8 個新 API 測試裡有 3 個炸 `got Future attached to a different loop`
- **原因**:`TestClient` 是 sync,內部用 anyio `BlockingPortal` 開新 loop。FastAPI 的全域 engine 是模組載入時 bind 到 import 時的 loop,跟測試 loop 不同 → asyncpg 在錯誤 loop 用 cached connection → 炸
- **修法**:換成 **`httpx.AsyncClient(transport=ASGITransport(app=app))`** — 跟測試 fixture 在同個 loop 跑
- 額外加 **`app.dependency_overrides[get_db] = _test_db`** 把預設 pooled engine 換成 `transient_session()`(NullPool),防止跨測試共享 connection
- **教訓**:**asyncpg 的 loop binding 不只在 worker,任何「跨 loop 用同一個 engine」的場景都會中**

#### 坑 2:Postgres 不允許 `bool → float` 直接 cast(M6 也踩過)
- M8 寫 `/accuracy` SQL 時又用 `cast(aligned, Float)`,500 error
- 第二次踩,記憶肉啦 — `Integer` 中間轉一次

#### 坑 3:Mypy strict 跟 Celery / instructor 第三方 typing 大戰
- 跑 `mypy --strict` → 26 errors,大多是「`@celery_app.task` 沒 type → 標的 function 也沒 type」`untyped-decorator`
- **不可能去 fork celery 補 typing**
- 修法:模組層 override `disallow_untyped_decorators = false` for `app.tasks.*` / `app.workers.*` / `app.llm.clients` — 把「真的有 bug」跟「第三方 typing 缺陷」分開
- 仍然修了 6 個我們自己的真 bug(`list` missing type arg、`Decimal | None` 沒 narrow、bad `type: ignore` comment)
- **教訓**:mypy strict 是「**寫 code 時警惕**」工具不是「**證明零 bug**」工具,務實處理

#### 坑 4:Chart 鋸齒問題(daily 跟 intraday 混)
- M8 跑完第一次 chart 出現「平滑下降 → 突然鋸齒」
- **原因**:backfill 是 daily(1pt/day),近 5 天的 intraday 是 1m bar(1pt/min)。1237 個點塞進一張圖,密度落差大導致視覺混亂
- 第一次修法:`downsample` 到 120 個 bucket — 沒解掉,因為 daily 那邊 1pt/day 還是 1pt/day,bucket 對它無感
- **真正修法**:`resampleDaily` — 不管原始有多少 point,**按 UTC 日期 group by 取每天最後一筆**。8-day window 就 8 個點,乾淨
- **教訓**:**混合解析度時間序列要先 resample 到統一頻率**才能畫圖

#### 坑 5:pytest TRUNCATE fixture 每次都洗掉 demo 資料
- 跑完 `pytest` → DB 只剩測試 seed 的 1 個 AAPL test event
- 影響每次:demo / 截圖前必須重新 fetcher trigger
- M9 / M10 該分開 test DB(用 `TEST_DATABASE_URL` env override),M8 範圍內先忍

---

### 為什麼這樣選(關鍵決策)

#### 為什麼 chart 用「rebased to 100」而非絕對價格?
- NVDA $150 vs SPY $500 — scale 差 3 倍,絕對價畫一起 NVDA 變平線看不出變化
- Rebase 是金融業界標準 — Bloomberg、Yahoo Finance 比較多 ticker 都這樣畫
- **excess return 直接是兩條線的垂直差距,一眼讀出**

#### 為什麼 chart resample 到 daily 而非小時 / 分鐘?
- 8 天 window 的 use case 是「**這週 NVDA 跑得比大盤好不好**」,不是「intraday volatility」
- Daily 8 個點 < intraday 上千點,**訊號雜訊比好**
- 之後加 1h window 的 chart 再用 1-min resolution

#### 為什麼 `/accuracy` 每個 slice 一個 useQuery 而非一次拿全部?
- 一次拿全部要 backend 多寫一個 `/accuracy/breakdown` endpoint
- 多 useQuery:`useQuery` 自帶 caching、loading state、parallel fetch
- **8 個 queries 直接平行,加總 latency = max(8 個)而非 sum**
- 代價:8 個 round trip(但都 cached after first load)
- 規模大會痛(20+ sources × 5 windows × 3 models = 300 queries),目前 OK

#### 為什麼用 `ASGITransport` 而非 `httpx_mock`?
- `httpx_mock` 是 mock 「打出去的 HTTP request」 — 我們不想 mock,要真的呼叫自己的 FastAPI app
- `ASGITransport(app=app)` 在 process 內直接走 ASGI 介面,**不走真正的 socket**
- 比 `TestClient` 好:async-native、跟測試共享 loop、no thread

#### 為什麼 coverage gate 設 75% 不是 90%?
- spec §14 寫 75%(對 portfolio 專案夠了)
- Push 過頭(95%+)會出現「為了覆蓋率而寫無意義測試」的 anti-pattern
- 80% 是 sweet spot — 真正的 hot path 都覆蓋了,剩下是設定 / Celery decorator wrapping 等難測的
- CI gate 是「**別讓人意外掉破 baseline**」,不是「逼到滿」

#### 為什麼分 backend-ci 跟 frontend-ci 兩個 workflow?
- 三個獨立 trigger:不同 path filter,backend 改不會跑 frontend job(省 CI 分鐘)
- 不同 setup(uv + Postgres vs Node + npm)— 分開更清楚
- 失敗時看 badge 馬上知道是哪邊壞

---

### 學到的觀念

1. **「Rebased index」是看相對 performance 的金融標準**:百分比 / 絕對值 / 對數刻度 都有適合場景,**比較多 series 一定用 rebased**

2. **不一致 sampling rate 的時間序列要 resample**:不只圖表會醜,計算指標(MA、std)也會被高頻段壓垮

3. **`ASGITransport` 是測 FastAPI 的現代答案**:`TestClient` 老 + sync + loop 麻煩,`AsyncClient + ASGITransport` 跟 production 行為更接近

4. **mypy strict + 第三方 typing 缺陷是日常**:不要去修 celery / yfinance 的 typing,**模組 override 把問題隔離**

5. **三層 selectinload 鏈也是 1+1+1**:`Event → predictions → outcomes` 一個 query 加兩個 IN query,不是 N+M。SQLAlchemy eager loading 的威力

6. **CI gate 早期建立 = 後期省力**:M8 加 CI 後,每次 push 都跑完整檢查;之後 milestone 出 bug 在 PR 就攔住

---

### 面試可能會被問到

**Q1: 為什麼 backend 跟 frontend 分開兩個 CI?單一 workflow 也行吧?**
- 分開 = path filter 精準 = CI 分鐘節省(改 README 不會 trigger pytest)
- 分開 = 不同 setup steps(uv + Postgres service vs Node)
- 分開 = badge 顯示獨立(看到 `backend-ci 紅 / frontend-ci 綠` 知道是哪邊壞)
- Monorepo 大規模會用 Nx / Turborepo 做 affected detection,我們規模還沒到

**Q2: `--cov-fail-under=75` 是好做法嗎?**
- 是 — **回歸防止器**。沒這個 gate,有人重構時意外移除測試,coverage 默默掉到 50% 都沒人發現
- 但不要設太高(95%+)— 會逼出「測 getter / setter 補數字」的垃圾測試
- 我們 80% 設 75% gate,留 5% 緩衝給未來小重構

**Q3: 你的 chart 把 daily / intraday 都 resample 成 daily,intraday 資訊不就丟了?**
- 對「8 天 prediction window」這個 use case 來說,intraday 是雜訊
- 真實 use case 要看 intraday(例:盤中突發新聞反應),會另外做「1h zoom view」chart 用 1-min 解析度
- 「**做圖前先想清楚 user 要回答什麼問題**」— 圖表設計第一原則

**Q4: dashboard 用 8 個並行 useQuery 不會打爆 backend?**
- 對 portfolio 規模(<100 outcomes)8 個並行查詢 < 100ms 完成
- 規模大時:用 `useQueries` array hook 或加 `/accuracy/breakdown` 一次拿全
- 過早優化會是「用 8 個 queries 跑得很順,改 1 個 query 反而碎掉所有 cache」

**Q5: `ASGITransport` 跟 `TestClient` 真的差很多?**
- 表面 API 像;**底層**:
  - `TestClient`:啟動一個 BlockingPortal,把 async call wrap 成 sync,跑在獨立 thread
  - `ASGITransport`:純 async,跟 caller 同 loop
- 對「engine 是 module-level singleton」的 app,`TestClient` 的 thread 跟 module init 的 loop 不同 → 我們碰到的 bug
- 現代 FastAPI 文件已經推薦 `AsyncClient + ASGITransport`,`TestClient` 是 legacy

---

### 驗收狀態

- [x] Backend `/prices/{ticker}/range` endpoint 上線
- [x] Event detail response 包 nested outcomes(三層 selectinload)
- [x] 8 個新 API integration test 全綠(用 ASGITransport)
- [x] Pytest coverage **80%**(超過 spec 75%)
- [x] mypy --strict 0 errors(53 files)
- [x] ruff check + format check 0 errors
- [x] Frontend 加 recharts、PriceChart、OutcomesTable、`/dashboard`
- [x] `npm run build` 過(3 routes 含 `/dashboard`)
- [x] GitHub Actions:`backend-ci.yml` + `frontend-ci.yml`(push 後 GH 真的會跑)
- [x] Browser demo:event detail 有 daily-close chart、prediction 下方有 outcomes 表、`/dashboard` 顯示 7.7% overall + by-source / by-window bar

### 視覺成果(real data)

```
/events/{nvda-event} 完整畫面:
┌──────────────────────────────────────────┐
│ SEC · 8K · ANALYZED              May 15  │
│ NVDA 8-K filed 2026-05-15 (items: 2.02)  │
│ [ext_id] [tickers: NVDA] [fetched 21m]   │
└──────────────────────────────────────────┘

PRICE ACTION  — predicted_at marked, daily closes
┌──────────────────────────────────────────┐
│ NVDA vs SPY · daily closes · 8 days      │
│                                          │
│ 100 ●━━━━━●━━●                           │
│              ╲   ╲╲                       │  SPY (灰虛線)
│  98              ●━━●━●━━●               │
│                          ╲╲              │  NVDA (黑實線) 
│  96                          ●           │
│   May 15  May 18  May 20  May 22         │
└──────────────────────────────────────────┘

LLM PREDICTIONS (1)
┌──────────────────────────────────────────┐
│ NVDA  ▲ BULLISH HIGH    conf 75%         │
│ "Strong fundamentals, beat estimates..." │
│ gpt-4o-mini · prompt v1 · $0.00015       │
│ ┌───────┬────────┬────────┬────────┬───┐ │
│ │ 1h    │ pending validation         │   │ │
│ │ 24h   │ pending validation         │   │ │
│ │ 7d    │ -4.50%│ +0.70% │ -5.20%│ ✗ │ │  ← BULLISH 預測但跌了
│ └───────┴────────┴────────┴────────┴───┘ │
└──────────────────────────────────────────┘
```

```
/dashboard:
┌──────────────────────────────────────────┐
│ AGGREGATE ACCURACY                       │
│   7.7%  across 13 validated predictions  │
│   Predictions are aligned when sign of   │
│   excess_return matches direction...     │
├──────────────────────────────────────────┤
│ ACCURACY BY SOURCE                       │
│  SEC:  [▮▮▮▮▮▮▮     ] 20%  (n=5)        │
│  FRED: [               ] 0%   (n=3)      │
│  FOMC: [▮▮▮▮▮▮▮▮▮▮  ] 33% (n=3)        │
├──────────────────────────────────────────┤
│ ACCURACY BY WINDOW                       │
│  7d:   [▮▮▮▮         ] 8% (n=13)        │
│  (1h / 24h 沒資料 — backdate 落在週六)   │
└──────────────────────────────────────────┘
```

---

## Milestone 9 — Deploy (Railway)

> **狀態**:✅ 完成 — **production 真的上線**
> **目標**:後端 4 個 service(backend / worker / analyzer / beat)+ Postgres + Redis 部署到 Railway;frontend 部署到 Vercel;系統自動跑 + 任何人能打開 URL。
>
> 📝 **後續更新**:本節記錄的是 M9 部署當下的 production 狀態(20 events / 36 predictions / FRED 56% 等)。M9 上線後系統持續演化,~25 個 commit 把 analyzer 從「zero-shot LLM」改造成「contextual analyzer」、把 alignment 從 excess-return 改成 raw-return、加 8-K body 下載、加 indicators 表、寫了三個 production 維護腳本。完整改造記錄在 [Milestone 9.5 — Production hardening + analyzer overhaul](#milestone-95--production-hardening--analyzer-overhaul)。本節保留 M9 deploy 當下的 snapshot。

### 上線後的 production URL

```
Frontend:  https://event-sense-five.vercel.app
Backend:   https://eventsense-production.up.railway.app
Code:      https://github.com/e54true/EventSense
```

### 部署架構

```
                       Internet
                          │
                          ├─→ Vercel CDN ─→ Next.js (frontend)
                          │
                          └─→ Railway Proxy ─→ FastAPI (backend)
                                                  │
                                                  ▼
                  Railway Internal Network (railway.internal)
                                                  │
                       ┌──────────────┬───────────┴─────────────┐
                       │              │           │              │
                  PostgreSQL       Redis       worker        analyzer
                  (addon)         (addon)    (celery)      (celery, -Q analyze)
                                              │              │
                                              └──────┬───────┘
                                                     │
                                                    beat
                                                  (celery scheduler)
```

### 做了什麼

#### 程式碼準備(commit `de97f3e`)

**`backend/Dockerfile` 強化**:
- Pin `python:3.12.7-slim` 跟 `uv:0.5.18`(repeatability)
- 裝 `curl`(HEALTHCHECK 用)+ `tini`(PID 1,signal forwarding 給 worker/beat clean shutdown)
- `HEALTHCHECK --interval=30s` 走 `/api/v1/health`
- `ENV PORT=8000` 當 fallback,實際被 Railway 注入的 `$PORT` 蓋過
- Non-root `app` user(M9 過程中發現這層讓 beat 撞權限,見「踩到的坑」)

**`backend/app/api/routes/health.py`(新)**— Split liveness vs readiness:
- `GET /api/v1/health` — 純 process uptime,no DB,給 LB / Dockerfile 用
- `GET /api/v1/health/ready` — 加 DB `SELECT 1` ping,DB 掛時 503

**`backend/app/main.py`** — CORS allowlist + Vercel `*.vercel.app` regex(`allow_origin_regex=r"https://[a-z0-9-]+\.vercel\.app"`)

**`backend/railway.json`** — Railway 讀的 config:`builder: "DOCKERFILE"`, restart policy. **(M9 中發現 healthcheckPath 不該放這裡 — 見坑 §4)**

**`backend/Procfile`** — 4 個 service 的 start command(Heroku-style,Railway 不直接讀但有文件價值)

**`backend/.env.production.example`** — Prod 用 env 範本(用 Railway variable reference `${{Postgres.PGUSER}}` 語法)

**`DEPLOYMENT.md`** — 12 章 step-by-step runbook(Railway 註冊到 production unattended)

#### 修 railway.json healthcheck 規模問題(commit `733449b`)

第一版 `railway.json` 寫 `"healthcheckPath": "/api/v1/health"`。但 worker / analyzer / beat **共用同一個 image + railway.json**,卻沒 HTTP server。Railway 套用 healthcheck 給每個 service → Celery service 永遠 healthcheck timeout → 部署失敗。

修法:**從 `railway.json` 拿掉 healthcheck**,只在 backend service 的 UI 個別設。

---

### Railway 真實部署過程(超多血淚)

#### 坑 1:Railpack 沒讀 root directory
**症狀**:第一次 deploy build 秒失敗,Railpack(Railway 預設 builder)說「找不到語言」,列出整個 repo root(包含 `frontend/`、`.github/` 等)。

**根因**:Railway 從 GitHub import 時預設 root = `/`,沒讀我們的 `backend/Dockerfile`。

**修法**:Service Settings → Source → Root Directory 填 `backend`。**Railway UI 是「輸入完要按 Update 按鈕」**,Enter 不會自動 save(我第一次以為輸入後就好,結果沒存)。

存好之後 Railway 自動找到 `backend/railway.json`,builder 從 Railpack 切到 Dockerfile,build 通過。

#### 坑 2:`$PORT` 不展開
**症狀**:Backend deploy 成功(image 跑起來)但 healthcheck 一直 timeout。Deploy Log 看到:
```
Error: Invalid value for '--port': '$PORT' is not a valid integer.
```

**根因**:Custom Start Command 設 `uvicorn app.main:app --host 0.0.0.0 --port $PORT` → Railway 把它**直接 exec**(不走 shell),`$PORT` 是字面字串。

**修法**:**包 `sh -c`** 強制 shell 模式:
```
sh -c 'alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT'
```

(原本含 `&&` 的版本之所以能跑,是因為 `&&` 觸發 Railway auto-detect shell mode。改成單一 command 時就需要明確 `sh -c`。)

**面試講點**:Docker `CMD` exec form vs shell form 的差異,大部分 platform 都這樣處理 — 一個 command 不展開,多個 chained 自動 shell。

#### 坑 3:Backend Domain target port mismatch
**症狀**:Backend healthcheck 過了、curl `/health` 卻回「Application failed to respond」。

**根因**:Railway inject `$PORT=8080`,uvicorn binds 8080。但 **Generate Domain 時自動用 Dockerfile 的 `EXPOSE 8000`** 當 target port。proxy → 8000 → 沒人在那 → 連不上。

**修法**:Networking → Domain → Edit Port → 改 `8000` 成 `8080`。

**設計教訓**:Dockerfile 應該**不要** `EXPOSE 8000`(讓 Railway 完全用 `$PORT`),M9 後 cleanup 該做。

#### 坑 4:Healthcheck 套用到 Celery service
**症狀**:Worker 部署 build 過、Deploy 過,卻在 `Network > Healthcheck` 5 分鐘 timeout 失敗。

**根因**:`backend/railway.json` 有 `healthcheckPath: "/api/v1/health"`,worker 共用同一 config → Railway 對 worker 也跑 healthcheck → Celery 沒 HTTP server → 永遠 timeout → kill。

**修法**:
1. 從 `railway.json` 拿掉 healthcheck section
2. backend service 自己在 UI 補上 healthcheck path

**通用啟示**:**共用 config 跟 per-service config 要分清楚**。config-as-code 不是萬能,某些設定該留 service-specific UI。

#### 坑 5:Beat 寫不出 schedule file
**症狀**:Beat 部署啟動立刻 crash,traceback:
```
_gdbm.error: [Errno 13] Permission denied: 'celerybeat-schedule'
```

**根因**:Celery Beat 預設寫 `celerybeat-schedule` 到 working directory(`/app`)。我們 Dockerfile:
```dockerfile
WORKDIR /app           # 創 /app 為 root owner
COPY --chown=app:app . # 只 chown copy 進去的「檔案」,不 chown「目錄」本身
USER app               # 切非 root user
```

→ `/app` directory 是 root:root,`app` user 沒 write permission → beat 創不出 schedule file。

**修法**(免 rebuild image):start command 加 `--schedule=/tmp/celerybeat-schedule`(`/tmp` world-writable):
```
celery -A app.workers.celery_app beat --loglevel=info --schedule=/tmp/celerybeat-schedule
```

**長期修法**(M9 後該 cleanup):Dockerfile 加 `RUN chown app:app /app` 在 USER 切換前。

#### 坑 6:OPENAI_API_KEY 401 全失敗
**症狀**:Events 抓到 production DB,analyzer 跑了,但**所有 event 都是 FAILED**,failure_reason:
```
Error code: 401 - Incorrect API key provided: <sk-proj**...c4A>
```

**根因**:Railway env var 裡的 OPENAI_API_KEY 是**舊的 / 失效的**那把。

**修法**:重新貼新 key 進 4 個 service 的 Variables。然後 reset failed events:
```python
async with transient_session() as db:
    await db.execute(
        update(Event).where(Event.status == EventStatus.FAILED).values(
            status=EventStatus.FETCHED, failure_reason=None
        )
    )
    await db.commit()
```
再呼叫 analyzer task → 20 events 全部 ANALYZED ✅

**設計收穫**:**`failure_reason` 欄位救了一命** — 沒它根本不知道是 401。M5 spec 加這欄是對的。

#### 坑 7:Vercel 全部 404
**症狀**:Build log 顯示 5 個 routes(`/`, `/dashboard`, `/events/[id]` 等)生成成功,但打所有 URL 都 404 + body `NOT_FOUND`。

**根因**:Vercel 預設打開 **Deployment Protection — Vercel Authentication**,所有 deployment 需要登入 Vercel 帳號才能看。Canonical URL 回 401(SSO cookie),alias 回 404(被擋的 deploy 透過 alias 看起來像不存在)。

**修法**:Settings → Deployment Protection → **Vercel Authentication 關掉(toggle off)**。

**面試講點**:Vercel 從某個版本後 protection 預設開,出於 Hobby 用戶不希望公開 preview deployment 的考量。但 production deploy 通常該公開,要記得手動關。

---

### 為什麼這樣選(關鍵決策)

#### 為什麼選 Railway 而非 AWS?
- **學習曲線**:Railway 一個下午能上線,AWS first-time 1-2 天
- **抽象層**:Railway 是 PaaS,隱藏 VPC / IAM / ALB / Route 53 / ACM 等 50 個 AWS 概念
- **成本**:Railway $3-5/月,AWS 同等 setup $20-30/月
- **跨平台知識**:Railway 學到的 Docker / env var / healthcheck / DB / Redis 概念**全部可以搬到 AWS**,只是換 UI
- **M13-M14 規劃**:之後會用 Terraform 把同一個系統部到 AWS,**履歷上 Railway + AWS 都有**

#### 為什麼 4 個 service 不合併?
- **Separation of concerns**:fetcher / analyzer / scheduler 各自可以獨立 scale 跟 monitor
- **Failure isolation**:analyzer 因為 OpenAI rate limit 慢,不影響 fetcher 快速處理
- **Queue routing**:每個 service 只 listen 自己的 queue,不會搶 task
- **(Tradeoff)**:Free tier 5 service 限制只能塞 Postgres + Redis + 3 service,所以 Beat 升 Hobby 才放進去

#### 為什麼用 Railway variable reference (`${{Postgres.PGUSER}}`)?
- **不用手 copy connection string** — Railway resolve 時直接拿 Postgres addon 的當下值
- **Postgres password 重置 / hostname 換** → reference 自動更新 → service 不用改設定
- **Internal network**:reference 解析出來是 `postgres.railway.internal`(private network),沒走 public internet → 比較安全 + 沒 egress 費

#### 為什麼 backend service 用 `pre-deploy` 跑 alembic?
**我們沒用**(start command 是 `sh -c 'alembic upgrade head && uvicorn ...'`)。
- 簡單:start command 一條把 migration + server 連 chain 起來
- 缺點:每次 deploy 都跑 alembic(idempotent 但 wasted 0.5 秒)
- 缺點:migration 失敗 = container 永遠起不來 = stuck deploy(但這也是想要的行為)

理想做法是用 Railway 的 **pre-deploy step**(在 service 啟動之前跑一次性命令),但 Railway free / hobby plan 對這個支援不完整。Spec §13 之後可以拉到 Terraform 用 ECS one-shot task 更乾淨。

#### 為什麼 Vercel + Railway 混搭,不全在 Railway?
- **Vercel 為 Next.js 量身打造** — Edge CDN、ISR、Image Optimization、preview deploys 全自動
- **Railway 可以跑 Next.js** 但要自己處理 build / serving / cache
- **業界 default**:Next.js 跟 Vercel 同公司(Vercel 出的 Next.js),整合最深
- **成本**:Vercel Hobby 免費,Railway 跑 Next.js 要計入 service quota

---

### 過程中踩到的坑(總集)

| # | 問題 | 修法 | 教訓 |
|---|---|---|---|
| 1 | Railpack 沒讀 backend root | UI 設 Root Directory + 按 Update | UI update 不是 Enter,要找 button |
| 2 | `$PORT` 字面不展開 | start command 包 `sh -c '...'` | exec form vs shell form |
| 3 | Domain target port 8000 vs app 8080 | Domain edit port → 8080 | EXPOSE 不該 hardcode |
| 4 | Healthcheck 套用到 Celery | 從 railway.json 拿掉,backend UI 個別設 | 共用 config 跟 per-service 要分 |
| 5 | Beat 寫 schedule 權限不夠 | `--schedule=/tmp/celerybeat-schedule` | Dockerfile 要 chown 目錄不只檔案 |
| 6 | OpenAI key 401 全失敗 | 重貼新 key + reset FAILED events | `failure_reason` 欄位救命 |
| 7 | Vercel 全 404 | Deployment Protection 關 | Vercel 預設保護要主動關 |

---

### M9 驗收狀態

- [x] Railway 4 個 service 全綠(backend / worker / analyzer / beat)
- [x] Postgres + Redis addons online
- [x] backend `/api/v1/health` + `/api/v1/health/ready` 都回 200
- [x] 真實 OpenAI call 在 production 工作 — 20 events 全 ANALYZED
- [x] Vercel frontend 任何人可訪問
- [x] Frontend → Backend CORS 正確(`*.vercel.app` regex 工作)
- [x] Backfill 跑進 production DB(2200+ price snapshots)
- [x] Validator 跑出 outcomes(FRED 56% / SEC 0% / FOMC 25% / EARNINGS no data)
- [x] Dashboard 顯示真實 accuracy 數字
- [x] Push to main → 4 個 service 自動 redeploy(zero-downtime 為主)

### 真實 production 表現

```
20 events  (3 days ago ~ 3 months ago, depending on source cadence)
36 predictions
~30 outcomes(7d window 全部 valid,1h/24h 視週末跳過)

Accuracy 數字:
  FRED (CPI macro)    56%   18 validated  ← 比 random 略好
  SEC (8-K filings)    0%    4 validated  ← 樣本太小
  FOMC                25%    8 validated  ← NEUTRAL threshold 陷阱
  EARNINGS           N/A    no outcomes

Cost:
  - Railway:約 $2-3/月(Hobby plan 4 services)
  - Vercel:$0(Hobby plan)
  - OpenAI:約 $0.01/天(LLM_DAILY_COST_CAP_USD=1.0)
  - 總計:< $4/月
```

**Production 系統 24/7 自動跑** — Beat 每分鐘 trigger analyzer、每 15 分鐘抓 SEC、每天抓 FOMC + earnings。**完全 unattended**。

---

## Milestone 9.5 — Production hardening + analyzer overhaul

> **狀態**:✅ 完成(M9 上線後 ~25 個 commits 的持續演化)
> **目標**:把 M9 那個「**會跑但預測都是 random**」的 production 升級成「**有結構化上下文 + 真實基準 + 乾淨閉環**」的版本。
> **為什麼有這個 milestone**:M9 上線後跑了一週,觀察到三個根本問題:(1) LLM 沒有 macro context 在「FOMC 升息」事件出 BULLISH;(2) excess-vs-SPY 對齊邏輯在 SEC 公司事件上產生雜訊(SPY 拿來扣科技股波動沒道理);(3) 大部分 8-K 看 title 看不出實際內容 — analyzer 預測等於亂猜。這節記錄怎麼把這三個一起修。
>
> **TL;DR(對照 M5/M6 寫的舊內容)**:
> - **Prompt v1 → v3.2** — 加 temporal-ordering rule、prior analysis as context、強制 historical anchor
> - **Predictions 加 `kind` 欄位** — MARKET(對 SPY/QQQ 出方向)vs COMPANY(對個股出方向),routing 也分開
> - **Alignment 從 excess-return 改 raw-return** — 不再扣 SPY,單看 ticker 真實漲跌
> - **Outcome windows 從 H1 + H24 + D7 砍成 H24 + D7** — H1 噪訊太大,1 小時內價格還在開盤波動
> - **8-K / FOMC / Earnings payload 真正下載 body**(Phase A/B/C)— 不只看標題
> - **加 indicators table + DGS10/DGS2 + multpl PE/CAPE scraper** — 給 analyzer 看「現在 macro 環境怎樣」
> - **三個 one-shot 維護腳本**:`cleanup_backfill` / `dedupe_predictions` / `purge_legacy`
> - **SEC adapter LOOKBACK_DAYS 14 → 60** — 防 production gap 漏抓

### 為什麼需要這個階段

M9 上線後第一週的數字:

```
20 events / 36 predictions / ~30 outcomes
FRED 56% / SEC 0% / FOMC 25%   ← 對照「擲銅板 50%」
```

看似有結果,但拆開看每個案例就尷尬:
- **SEC 0%**:每筆 8-K analyzer 只看到「AMZN 8-K filed 2026-05-22 (items: 5.07)」這種 title — items 5.07 是 shareholder vote,可能漲可能跌,LLM 沒 body 等於亂猜
- **FRED 56%**:CPI 釋出後 LLM 看到 `value=332.407` 出 BULLISH/BEARISH — 但沒 prior reading,LLM 不知道這是升還降
- **FOMC 25%**:LLM 不知道現在利率 trajectory(是升息週期還是降息週期),光看「Fed issues statement」幾乎只能 NEUTRAL

問題本質:**M5 的 prompt 設計把 LLM 當 zero-shot oracle,沒餵足夠 context**。M9.5 整段就在補這個。

### Phase 1-5 — Analyzer 大改造(commits `a127719` → `0bbd849`)

#### Phase 1(commit `a127719`):schema 鋪路
- 新 `indicators` 表 —(ticker, name, value, observed_at)— 讓 macro 指標(PE, CAPE, DGS10/DGS2 殖利率)有地方存
- `predictions` 加 `kind` 欄位(`MARKET` | `COMPANY`)— 一個 event 可以同時生 MARKET preds(SPY/QQQ)跟 COMPANY preds(AAPL/MSFT/...)
- `EventType` enum 把 `MACRO_INDICATOR` 改名成 `ECONOMIC_RELEASE`(語意更準)

#### Phase 2(commit `dd4b949`):FRED 多 series + 殖利率
- FRED adapter 從只抓 CPIAUCSL 擴成抓多個 series(`fred_series` env var 控制)
- 加 DGS10(10Y treasury)、DGS2(2Y treasury)indicators
- 給 analyzer 看的 macro context 從「CPI 一個數字」變成「現在 10Y / 2Y 殖利率 + spread」

#### Phase 3(commit `f367325`):FOMC dot plot + multpl scrapers
- 新 adapter 抓 [https://www.multpl.com](https://www.multpl.com) 的 S&P 500 PE ratio、Shiller CAPE
- 新 FOMC dot plot HTML adapter — 抓 Summary of Economic Projections,寫進 events
- 這些都是 macro context 的補充

#### Phase 4(commit `e70924e`):v2 contextual analyzer — **核心轉折**
- 新 `app/services/context_builder.py` — 對每個 event 組合「最近 30 天的 macro 環境快照」:
  - 最近 CPI value + change
  - 最近 DGS10 / DGS2 殖利率
  - PE / CAPE current value
  - 最近 N 個相關 events 的 prior analysis(prompt v2 才用得到)
- Prompt v2 模板 — 餵這個 context block 給 LLM,並且 LLM 要分開出 MARKET prediction(SPY/QQQ)跟 COMPANY prediction(個股)
- Analyzer 改成寫 N 個 `kind=MARKET` + N 個 `kind=COMPANY` predictions

#### Phase 5(commit `0bbd849`):frontend surface
- Event detail page 顯示 MARKET vs COMPANY 拆開的預測
- Macro context box 顯示給用戶看 LLM 看到什麼

**整個 Phase 1-5 的意義**:把 LLM 從「fortune teller」變成「有 prior knowledge 的分析師」。

### Phase A/B/C — Document body 真實下載(commits `c894664` → `58fc074`)

#### Phase A(commit `c894664`):Earnings 加 fundamentals
- yfinance 拿到 Earnings 後,額外抓 Revenue / Net Income / EBITDA + 計算 YoY growth
- Payload 從只有 EPS surprise 擴成完整 income statement summary
- LLM 終於知道「不只 EPS beat,revenue 跟 NI 也 beat → bullish much stronger」

#### Phase B(commit `14e4a7f` + `58fc074`):SEC 8-K body
- 新 `event_documents` 表 — 存下載完的 filing body(以及 EX-99.1 press release 附件)
- SEC adapter 抓到 8-K → 排程獨立 task 去下載 `*.htm` body + EX-99.1
- Analyzer 加 **doc-wait** 邏輯:event 是 8-K 時,如果 documents 還沒下載完,defer analyze(等 5 分鐘)
- 這是「**defer ≠ fail**」原則的另一個應用 — body 還沒下載完不要硬上 LLM,等等沒關係
- Event detail page 也顯示 attached documents(commit `58fc074`)

#### Phase C(commit `5772a75`):FOMC statement body
- FOMC adapter 抓到 statement URL → 下載文本 inline 到 payload
- Analyzer 看到的不再是「Federal Reserve issues FOMC statement」,而是完整聲明內容

**Phase A/B/C 的共同主題**:**不要相信 title,要看 body**。Title is metadata, body is signal.

### Prompt v3.2(commit `9ca65f0`)— LLM 的最終形態

- **Temporal-ordering rules**:強制 LLM 在 reasoning 裡明確說「過去 X 是因,未來 Y 是果」,不能說「現在的價格反映 future earnings」這種倒果為因的話
- **Prior analysis as context**:相同 ticker 最近 5 個 events 的 LLM 預測 + outcome 餵進 prompt — LLM 看到「上次我說 BULLISH 結果 ticker 跌了」會調整 confidence
- **Detailed reasoning**:reasoning 從 1 句話放寬到 5-6 句(M5 的「summary」風格效益太低,prompt v3.2 要看到 thought chain)
- **Mandatory historical anchor**:CPI/FOMC/earnings 都強制要 reference 一個過去同類事件當錨點(避免 LLM 抽象 reasoning)

### LLM model 升級(commit `8b5f231`)

- Earnings event 也升 premium model(gpt-4o)— spec router 原本只給 FOMC/CPI 升,但 earnings 的 fundamentals body 太重,gpt-4o-mini 抓不到細節
- 新欄位 `prediction.thesis: Text` — 持久化 LLM 的完整 reasoning(原本只在 log,現在進 DB)
- 前端加 legend 解釋 BULLISH/BEARISH/NEUTRAL 跟 MARKET/COMPANY 的關係

### Alignment refactor(commit `faeb2d6`)— **最重要的概念翻案**

M5/M6 寫的:**alignment = direction 對上 excess return 的符號**(excess = ticker - SPY)。

問題:
- 7 個 watchlist 都是科技股 → 跟 QQQ 高度相關,跟 SPY 普通相關
- SEC 8-K 是公司特有事件 — 用 SPY 當 baseline 在扣什麼?扣不掉 noise,只是把 ticker return 偏移
- 用戶看「QQQ 漲 2%、ticker 漲 3%、excess 1%」→ 對齊但其實很普通;反過來「SPY 跌 1%、ticker 跌 0.5%、excess 0.5%」→ 對齊但 ticker 真實跌

決策:**alignment 改成只看 raw return 跟方向是否一致**。
- BULLISH + ticker_return > 0 → aligned
- BEARISH + ticker_return < 0 → aligned
- NEUTRAL + `|ticker_return| < 0.5%` → aligned

`prediction_outcomes.spy_return` / `excess_return` 欄位**保留**(可能 dashboard 還想顯示),但 `aligned` 的計算不再用到它們。`alignment.py::is_aligned` 從 `(direction, excess)` 改成 `(direction, ticker_return)`。

**這推翻了 M6 「excess return 是金融 alpha 的標準量測」的論述** — 在我們這個 sample size 跟 watchlist 結構下,raw return 更乾淨。alpha framing 是真的(投資界這樣量測),但對「**LLM 預測對不對**」這個簡單 yes/no question 加了無謂雜訊。

### Outcome windows 改造(commit `462d82e`)

從 H1 + H24 + D7 砍成 **只有 H24 + D7**:
- H1 噪訊大 — 1 小時內價格主要反映「事件發生時剛好在開盤前 / 開盤後 / 盤中」,跟 LLM 預測對不對沒關係
- 統計上 H1 outcome 跟 H24 outcome 高度相關 — 重複收集沒新資訊
- H1 還是 backfill 抓盤前 / 週末資料的災區 — 拿掉省麻煩

Migration 直接 `DELETE FROM prediction_outcomes WHERE window = 'H1'` + 拿掉 enum 那層程式碼。**沒做 backfill** — H1 outcome 本來就沒人看。

### Validator 兩個關鍵 fix

#### 1. Order DESC(commit `94f65c9`)
- 原 candidates SELECT 是 `ORDER BY predicted_at ASC` — 最早的先做
- 但 backfill 的 events 可能 predicted_at 比 production price history 還早 → 每次 SELECT 都拿到這些,price lookup deferred,**佔住 batch 額度**
- 改 DESC → 新 prediction 先做,老的 backfill defer 不影響別人
- **教訓**:queue ordering 的 default ASC 不是金科玉律 — 看任務特性

#### 2. Split batch evenly across windows(commit `9e9d91a`)
- 原本 batch_size=50 是「所有 (pred, window) pairs 共享」
- 結果 H24 pairs 比 D7 多很多(時間早成熟),老是把 50 個額度佔光
- D7 永遠 starve,沒人 fill
- 修法:`batch_size / N_windows`,每個 window 自己一個 sub-budget
- **這就是這個 session 觀察到的 H24=87 vs D7=129 imbalance 的反向**(D7 fill 比 H24 多 — 因為這個 fix 後 D7 有自己保留額度,但 H24 還在受 backfill events 拖累)

### Frontend table fix(commit `20d16bd`)

Outcomes table 原本只顯示「有 outcome 的 row」,看起來就是「7 個 event 都 N/A」。改成三狀態:
- **Filled** — 有 outcome,顯示數字
- **Maturing** — predicted_at + window 還沒到,顯示 ⏳
- **Unavailable** — 過了 deadline 但 price worker 還沒寫,顯示 ✗
- 三種視覺區隔讓用戶看出「**這是還沒成熟 vs 真的算不出來**」

### Chart fix(commit `7f12553`)

Event detail page 的價格 chart:
- 公司事件(SEC 8-K, earnings)→ 畫 **company + SPY + QQQ** 三條線
- Macro 事件(FOMC, CPI)→ 畫 **SPY + QQQ** 兩條
- 跟 alignment refactor 配套 — chart 還是顯示 benchmark(視覺對比有用),但對齊計算不再用

### Chart anchor fix(commit `be0af76`)

Chart 的 price window 原本 anchor 在 `prediction.predicted_at`(LLM 跑完的時間)— 但 backfill 重跑 LLM,predicted_at 會變最近時間,chart 就跳到 backfill 當天而不是 event 真實發生那天。

修法:anchor 改成 `event.published_at`(事件真實發生時間)— 不管 prediction 何時跑,chart 視覺穩定。

### 三個 one-shot 維護腳本

M9 上線時的腳本只有 `backfill_prices`。M9.5 補了三個處理「**production 狀態管理**」的工具:

#### `app/scripts/cleanup_backfill.py`(commit `3c94083` 加入,session 用過多次)
- 把所有 ANALYZED 的 events 翻回 FETCHED + 砍掉 v2 outcomes
- 等 analyzer beat 自動重 analyze + validator 重 fill
- **用法**:改 prompt 或 schema 之後,想讓 production 用新 prompt 重跑所有 events

#### `app/scripts/dedupe_predictions.py`(commit `acfcdbd`)
- `ROW_NUMBER() OVER (PARTITION BY event_id, ticker, kind ORDER BY created_at DESC)` 留 newest,砍其他
- **用法**:cleanup_backfill 跑多次累積出來的重複 v2 preds 清掉
- 這個 session 跑了一次砍掉 109 個

#### `app/scripts/purge_legacy.py`(commit `faeb2d6` 加入)
- 砍所有 v1 predictions(cascade outcomes)— alignment 從 excess 改 raw 之後 v1 outcomes 數字邏輯不再對
- 砍所有 v2 outcomes(predictions 留著,validator refill)
- **用法**:alignment semantics 改變之後讓 validator 用新邏輯重算
- 這個 session 跑了一次砍掉 168 個 outcomes

**設計收穫**:**production 修法不該只在程式碼,DB state 也要有對應 migration / one-shot script**。沒有 cleanup_backfill,改 prompt 之後 production 永遠是舊預測 — 系統理論上對但用戶看不到改善。

### SEC adapter LOOKBACK 14 → 60(commit `6d9a9f4`,本 session)

#### 發現問題
session 中查 production 資料,發現:
- 系統第一次 ingest 是 2026-06-07
- SEC adapter `LOOKBACK_DAYS = 14`(spec 當初寫的)→ 只抓 5/24 起的 8-Ks
- 但實際上 4-5 月有 **18 個 8-Ks**(AAPL/MSFT/GOOGL/AMZN/META/NVDA/TSLA 每家 1-7 個)沒抓到
- 第一筆 production analyzer 跑的 context 不完整 — LLM 看 recent events 30 天 window 是空的

#### 修法
`LOOKBACK_DAYS = 60`(留 ~2 個月 headroom,以後再有 deploy gap 也撐得住)。`(source, external_id)` 唯一鍵會 dedup,所以 LOOKBACK 拉長不會重複 insert。

#### 後續處理
1. Push commit → Railway redeploy
2. 用 production credentials 跑 `sec_edgar.fetch_new()` once → insert 18 新 8-Ks
3. 跑 cleanup_backfill 把 51 老 events + 18 新 events 都翻 FETCHED
4. Analyzer 自動跑完(68 ANALYZED + 1 FAILED)
5. dedupe_predictions 砍 109 dups(51 老 events 各有 1 舊 + 1 新 v2 preds)
6. purge_legacy 砍 168 v2 outcomes(讓 validator 用乾淨 preds 重算)
7. Validator 自動 refill → 216 outcomes(87 H24 + 129 D7)

#### 1 個 FAILED event 沒解
**MSFT 8-K filed 2026-06-05 (items: 5.02)** — items 5.02 是 Departure/Election of Directors。Analyzer 跑這個 event 失敗,沒留 trace。可能性:
- LLM 看到 5.02 body 找不到實質方向訊號 → 拋 validation error → mark FAILED
- 或者 doc-wait 邏輯有 race(body 還沒下載完就被 analyze)
- 沒影響其他 events;之後可以單獨重 trigger 或忽略

#### H24 vs D7 outcome imbalance 沒解
session 結束時觀察到:H24=87, D7=129(D7 更多),理論上 H24 應該至少跟 D7 一樣多(24h 比 7d 先成熟)。可能原因:
- H24 price lookup 卡在 weekend gap(週六/日 publish 的 event 找不到 +24h 的盤中價)
- 或 validator H24 lookup 對 `must_be_after` 限制太嚴
- 不影響 dashboard 正確性,但值得後續調查

### 學到的觀念(總集)

1. **LLM context engineering > prompt wording**:M5 寫了個漂亮 prompt 但 LLM 還是 random — 因為它沒看到 macro / prior analysis。後來加 context_builder 比改任何 prompt 字眼都有用
2. **Alignment metric 不只是數學,是 metric 設計**:excess return 是金融標準但對「LLM 預測對不對」這個簡單問題反而 noise。**選 metric 要看 question type,不是看書上怎麼寫**
3. **Title is metadata, body is signal**:Phase A/B/C 全在做這件事 — 抓 body
4. **One-shot scripts 是 production migration 的 first-class citizen**:不只 alembic 才算 migration,DB 狀態變更也要有腳本
5. **Defer ≠ Fail** 再次驗證:doc-wait 跟 price-missing 都用 defer 處理,沒寫過半成品 outcome
6. **LOOKBACK / horizon 參數要留 headroom**:M5 寫 14 天當時夠用 — 但沒考慮 deploy gap 跟 backfill 場景。M9.5 改 60 之後彈性大很多
7. **DESC ordering 對 backfill 重要**:queue ordering ASC 是預設,但「最近事件先處理」對用戶感知更好(老 backfill events 可以慢慢補)
8. **Migration 之後要驗證 production 真實 state**:M9 上線那天的「20 events / 36 preds」數字 一週後就變了 — 不能只看 deploy log,要定期 query production

### 這個 milestone 跟前面的關係(舊內容哪些過期了)

回去翻 M5/M6 寫的東西,有幾處要記得「**現在不一樣了**」:

- **M5 §測試** — 寫「prompt_version='v1'」,現在 production 是 v3.2
- **M5 §真實預測範例** — reasoning 寫「significant corporate developments may increase investor confidence」這種空話,v3.2 後 reasoning 是 5-6 句具體分析
- **M6 §做了什麼** — 寫「excess_return: Float — 預測對不對的判定」,現在 alignment 不再用 excess
- **M6 §坑 1** — `must_be_after` 對 end-price 還是對,但 SPY end-price 已經不影響 alignment 結果
- **M6 §學到的觀念 #2** — 「Excess return 是金融 alpha 的標準量測」這句技術上對,但在 EventSense 這個系統脈絡下被 raw return 取代了
- **M6 §面試 Q5** — 「為什麼 SPY 不 QQQ」這題現在 moot — 都不用了
- **M6 §真實 outcome 範例** — 那張表有 spy_return / excess 欄位,現在 dashboard 不再用這些欄位算 aligned
- **M9 §真實 production 表現** — 「20 events / 36 preds」是當時 snapshot,現在(2026-06-09 session 結束)production 是 **69 events / 165 v2 preds / 216 outcomes**

這些舊內容**沒改寫**(歷史紀錄保留),但讀的時候要記得 M9.5 後狀態已經跟 M5/M6 寫的不一樣。

---

## Milestone 9.6 — Accuracy overhaul + terminal UI

> **狀態**:✅ 完成(2026-06-11 單一 session,commits `64f3d3a` → `4ea0b6b`)
> **目標**:一次解決「accuracy 數字本身量錯了」的測量層問題,順帶 UI 大改版、timeline 篩選、watchlist 擴編。
> **為什麼有這個 milestone**:做全專案 bug 審查時發現一個顛覆性的問題 — **FRED 事件的時間錨點從第一天就是錯的**,所有宏觀事件的 outcome 標籤都是噪音。修這個的過程牽出一整串測量層問題,於是把「先把尺修直,再把眼睛擦亮,最後才換更強的腦」一次做完。
>
> **TL;DR**:
> - **FRED 改用 ALFRED vintage 模式** — `published_at` 錨真實發布日(08:30 ET),不再是統計參考期;payload 加 CPI MoM/YoY、NFP 月增、GDP 年化 QoQ 等 **surprise 指標**
> - **Per-window 評分** — predictions 加 `direction_7d` 欄位,24h/7d 各自評分;NEUTRAL 門檻按視窗縮放(24h ±0.5%、7d ±1.5%)
> - **Prompt v2 → v3** — 評分規則寫進 prompt、confidence 尺度統一(0.5=擲硬幣)、LOW⇒NEUTRAL 一致性規則、強制歷史類比降為 optional、新增 MARKET STATE(動能/波動)與 TRACK RECORD(自己的近期命中率)區塊
> - **Self-consistency 多數決** — 高權重事件(premium 路由)跑 3 次獨立呼叫,per-ticker 方向投票,平手 → NEUTRAL
> - **模型升級** — gpt-4o-mini/gpt-4o → gpt-5-mini/gpt-5,日上限 $1 → $5
> - **`/accuracy` 加 baseline 對照 + 校準分桶** — always-bullish/bearish/neutral 在同一組 outcomes 上的對齊率,以及按 confidence 分桶的校準表
> - **UI 全站改版** — Bloomberg 終端機風(深色、等寬數字、琥珀 accent、綠漲紅跌),design tokens 集中在 globals.css
> - **Timeline 無限載入 + 篩選列**(source/ticker/type);**watchlist 擴到美股前十大**(+AVGO/BRK-B/LLY,含 `TICKER_INGEST_SINCE` 不回抓機制);recent events 可點擊跳轉
> - **六個 bug 修復** + 一個 production 級鎖死偵錯故事

### 起點:全專案 bug 審查

用兩個 read-only agent 分頭掃前後端,人工驗證後確認的真 bug:

| Bug | 位置 | 嚴重度 |
|---|---|---|
| 30 天前指標查詢只有上界沒下界 — 資料有缺口時 `delta_30d` 拿幾個月前的舊值 | `context_builder.py` | HIGH |
| 撞唯一鍵時 `db.rollback()` 連同批已 flush 未 commit 的事件一起回滾,計數卻照加 — 事件默默遺失 | `event_writer.py` | MEDIUM |
| `useQuery` 在 `.map()` 裡呼叫(Rules of Hooks)| dashboard | HIGH |
| `rebase()` 基準價為 0 → 整張圖 Infinity/NaN | `PriceChart.tsx` | MEDIUM |
| Anthropic 路徑 `max_tokens=1024`,schema 根本塞不下(800 字 summary + N×2000 字 reasoning)| `clients.py` | MEDIUM |
| list key 用 array index + `as` 硬轉型 | `RecentEventsTimeline.tsx` | LOW |

agent 也報了假陽性(recharts 的 `domain={["dataMin - 0.5", ...]}` 其實是合法語法)— **agent 產出要人工驗證再動手**。

修法亮點:event_writer 改用 `async with db.begin_nested()`(savepoint)包每筆 flush — 撞鍵只退該筆,不汙染整批。

### 最大發現:FRED 時間錨點從第一天就是錯的

`obs["date"]` 是 FRED observation 的**統計參考期間**(五月 CPI = `2026-05-01`),不是發布日(六月中)。舊 code 把它當 `release_date` 用:

- `published_at` 錨在數據還沒公布的日子
- validator 用 `predicted_at = published_at` 算 24h/7d 報酬 → 量的是「參考月第一天的走勢」,跟 CPI 發布的市場反應**完全無關**
- 所有 FRED 類的 aligned 標籤都是噪音 — **LLM 再聰明也救不回標籤錯的評分**

修法:改用 **ALFRED vintage 模式** — 查詢帶 `realtime_start/realtime_end` 範圍,API 回傳每個 (observation, vintage) 一列,**每個參考期第一個 vintage 的 `realtime_start` = 原始發布日**。`published_at` 錨在發布日 08:30 ET(CPI/NFP/GDP 都是 8:30 print)→ validator 的 baseline 自然落在發布前收盤、24h end 落在發布後收盤,正好是 event study 要的視窗。

順帶解決第二個問題:**指數水準對 LLM 毫無資訊量**(`CPI index level=320.321` 等於什麼都沒說)。市場交易的是 surprise — 從 first-release vintage 值算出 CPI MoM/YoY、NFP 月增千人(PAYEMS 是水準,headline 是差分!)、GDP 年化 QoQ,連同 `headline` 字串放進 payload。

**錨點驗證**(production 實測):五月 CPI → `ref 2026-05-01 | released 2026-06-10 | published_at 12:30 UTC | {mom_pct: 0.47, yoy_pct: 4.26, prev_mom_pct: 0.64}` ✓

### 其他測量層修正

1. **模型只被問 24h,卻同時被 7d 評分** — prompt 寫「forecast over the next 24 hours」,validator 卻拿同一個 direction 算兩個視窗。修法:LLM schema + DB 各加 `direction_7d`(nullable,legacy 預測 fallback 到 `direction`),validator 按視窗選方向。
2. **NEUTRAL ±0.5% 對 7d 太緊** — SPY 一週動超過 0.5% 是常態,7d NEUTRAL 幾乎必錯。波動 ∝ √t,7d 門檻改 1.5%(`NEUTRAL_THRESHOLDS` per-window dict)。
3. **BULLISH+LOW 自相矛盾** — LOW = 預期 |move|<0.5%,但 BULLISH 要 >+0.5% 才 aligned。模型誠實說「會漲但漲不多」系統必判錯。修法寫進 prompt:「預期在帶內 → 必須出 NEUTRAL」。
4. **沒有 baseline 就沒有意義** — 「62% 準確率」要對照 always-BULLISH(指數上漂,7d 可達 ~57%)才知道好壞。`/accuracy` 用同一組 outcomes 的 `ticker_return` 重放三種常數策略 + confidence 5 桶校準表。dashboard hero 直接顯示 BASELINES 一行。

### Prompt v3 + context 升級

- **評分規則入文**:讓模型知道自己的 loss function(per-window 門檻、band 內 = NEUTRAL),是最便宜的對齊手段
- **confidence 尺度統一**:prompt v2 寫 `0.0 (coin flip)`,schema 註解寫 `0.5 = coin flip` — 兩套尺度混用讓 confidence 欄位整體不可信。v3 統一 0.5 起跳並給定錨段位
- **強制歷史類比 → optional**:v3.2 的 MANDATORY anchor 強迫模型把當下硬套進敘事框架、mini 模型常給幻覺類比、cutoff 後的 regime 根本不知道。降級成「真的高度相似才引用,一個子句,不得主導方向判斷」
- **MARKET STATE 區塊**:context_builder 從 `price_snapshots` 算 SPY/QQQ/個股的 1d/5d/20d 報酬 + 20d 年化波動(leak-safe:只取 `published_at` 前的快照)— 模型第一次知道「市場最近在幹嘛」
- **TRACK RECORD 區塊**:過去 60 天 (window, kind, direction) 分桶的命中率聚合(只取 trigger 前已驗證的 outcomes)。**聚合餵比 raw dump 餵有效** — v2 把 50 筆舊預測全文截斷塞進去,token 重訊號稀

### Self-consistency 多數決

高權重事件(premium 路由:FOMC/CPI/NFP/GDP/財報)跑 **N=3 次獨立呼叫**,per-(ticker, kind) 投票:方向取眾數(**平手 → NEUTRAL,分歧本身就是低信心**)、confidence 取中位數、magnitude 取眾數、reasoning 取與多數方向一致的第一份。少數呼叫才出現的 ticker 直接丟棄。`analyzer_consensus_calls` 設定控制,=1 即關閉。

成本分析(這個決策跟使用者來回確認過):多數決一個月只多 ~$0.3 — **整個系統成本大頭是 Railway 主機(~$12-18/月),LLM 連 5% 都不到**。在最影響 accuracy 統計的高權重事件上,這是最便宜的準確率手段。

### 資料重置(清舊資料重抓)

錨點修正後,舊 FRED 資料**無法就地修復**(`(source, external_id)` 去重會擋住修正後的重寫),必須 purge 重抓;但 SEC/FOMC/財報的錨點是對的,**不用全清** — 既有 outcomes 用腳本就地重算:

- **`scripts/reset_fred.py`** — 刪 FRED events(FK CASCADE 帶走 predictions/outcomes),fetcher 重抓
- **`scripts/recompute_alignment.py`** — 從已存的 `ticker_return` 重推 `aligned`(新 per-window 規則),不用重抓價格,idempotent

Production 執行(沒有 ssh key,走 **Railway TCP proxy**:取 Postgres 服務的 `DATABASE_PUBLIC_URL`,本機 `DATABASE_URL=... python -m app.scripts.reset_fred`):刪 40 個錨錯事件(連帶 80 preds + 58 outcomes)→ 174 筆 outcomes 重驗、**9 筆在 7d ±1.5% 新門檻下翻牌** → 重抓 33 筆(14 CPI + 14 NFP + 5 GDP)→ analyzer 以 gpt-5 ×3 重分析,**66 筆 v3 predictions 全帶 direction_7d,花費 $4.66**(貼著 $5 日上限,router 降級護欄正常運作)。

### UI 改版 + timeline 功能(commits `64f3d3a`、`4ea0b6b`)

- **Bloomberg 終端機風**:近黑底 `#0a0e14`、全部顏色收斂成 `term-*` / `src-*` design tokens(Tailwind v4 `@theme`)、等寬數字、無圓角細邊框、琥珀 accent、綠漲紅跌。三頁 + 所有元件一次換完
- **Timeline**:`useInfiniteQuery` 無限載入(20 筆/頁 + LOAD MORE)取代「只能看 20 筆」;篩選列 source/ticker/type chips,選項由新端點 `GET /events/filters` 從 DB 動態算(`SELECT DISTINCT unnest(affected_tickers)`)— 加新公司不用改前端
- **後端 `/events` 加 `source`/`ticker`/`event_type` 參數** — ticker 過濾踩了兩個小坑:泛用 `sa.ARRAY` 沒有 `.contains()`(那是 postgresql 方言的),改 `any_()`;然後 `ticker == any_(col)` 會走 `str.__eq__` 讓 mypy 抓到回傳 `bool` — SQL 表達式要放等號左邊
- **Watchlist 擴到美股前十大**:+AVGO/BRK-B/LLY(CIK 入 map)。使用者要求「新公司不用回抓歷史」→ 新 `TICKER_INGEST_SINCE: dict[str, date]`,SEC/earnings fetcher 對晚加入的 ticker 用 `max(全域 cutoff, 加入日)` — 不浪費 LLM 分析沒有價格快照可驗證的舊事件
- **Recent events 可點擊**:`event_id` 從 `RecentEventSummary` → API → 前端一路補齊(prompt renderer 不需要、忽略)
- **Recharts tooltip 黑字 bug**:bar 顏色來自 `<Cell>` 時 recharts 拿不到 item color,fallback 黑色在深色底上看不見 — 補 `itemStyle`

### 偵錯故事:idle-in-transaction 49 分鐘 + 孤兒 pytest

部署前最後一步 pytest 突然永久卡死(之前同套件 13 秒跑完)。追查過程值得記:

1. `pg_stat_activity` 看到 **兩條連線 idle in transaction 49 分鐘**,握著 events 表的鎖;測試 fixture 的 `TRUNCATE TABLE events CASCADE` 排在後面,再後面所有 SELECT 全部排隊
2. 鎖主是誰?**analyzer 的 candidate scan** — `analyze_pending()` 外層 session 跑完 discovery SELECT 後沒結束 transaction,而 self-consistency 讓一個批次(33 事件 × 3 次 gpt-5 呼叫)跑幾十分鐘,transaction 就 idle 著橫跨整批
3. 修法:discovery 完 **立即 `await db.commit()`**(validator 同樣處理)— 外層 session 本來就只做唯讀掃描,沒理由抱著 transaction
4. 但重跑還是卡!第二層原因:**被中斷的 pytest 變孤兒程序** — 停掉外層 shell 不會殺到 pytest 子程序,孤兒繼續握著 DB session,一層卡一層。`pkill -9 -f pytest` + `pg_terminate_backend()` 清光後,164 tests 13 秒全綠
5. faulthandler 立大功:`pytest -o faulthandler_timeout=35` 在卡死時 dump 全執行緒 stack,直接看到卡在 **fixture 的 TRUNCATE**(連測試本體都沒進去)— 不用再猜是哪個測試的問題

**結構性教訓**:integration 測試和 dev 容器共用同一顆 DB,analyzer 長批次跑著的時候測試必卡。跑套件前 `docker compose stop analyzer worker beat backend`。

### 部署鏈上的坑

- **`docker compose restart` 不會重讀 `env_file`** — env 是 container create 時固定的,改 `.env` 要 `docker compose up -d` recreate。本機 analyzer 因此用舊模型跑了一輪才發現
- **Railway 環境變數與 repo 的 `.env` 是兩個世界** — `railway variables --set ... --skip-deploys` 改完要 `railway redeploy` 才生效
- **Railway 沒設 `DEFAULT_TICKERS`** → 用程式碼預設值,改 settings default 即全環境生效,雲端不用動

### 學到的觀念

1. **標籤錯了,一切白搭**:FRED 錨點錯 → 那一類的 accuracy 是純噪音。做預測系統第一件事是驗證 outcome 標籤的因果鏈(事件「何時」對市場可見),再談模型
2. **市場反應的是 surprise,不是 level**:給 LLM 指數水準等於沒給。差分/變化率/對前值比較才是訊號
3. **評分規則要讓模型知道**:模型不知道 loss function 就會輸出與評分機制不相容的答案(BULLISH+LOW)。把 scoring rule 寫進 prompt 是零成本對齊
4. **聚合回饋 > 原始記錄堆疊**:track record 給分桶命中率比塞 50 筆舊預測全文有效且省 token
5. **方向類任務的多數決便宜又穩**:3 次投票 + 平手歸 NEUTRAL,把單次抽樣的方差變成訊號(分歧=低信心)
6. **長批次不要抱著 transaction**:discovery query 跑完就 commit。「idle in transaction」是 Postgres 鎖問題的頭號嫌犯,`pg_stat_activity` 永遠先看這個
7. **殺程序要殺到底**:中斷的測試/腳本可能留下孤兒子程序握著 DB 連線 — 清理要 `pkill` + `pg_terminate_backend` 雙管齊下
8. **baseline 是 accuracy 數字的及格線**:沒有 always-bullish 對照,任何 prompt 改動的「提升」都可能是市場漂移的假象

### 面試可能會被問到

**Q1: 你怎麼發現 FRED 錨點錯的?**
- 做 code review 時順著「accuracy 怎麼算」往上游追:validator 用 `predicted_at` 開視窗 → `predicted_at = published_at` → FRED adapter 的 `published_at` 來自 `obs["date"]` → 查 FRED API 文件確認 `date` 是 observation period 不是 release date。教訓:**金融資料管線要逐欄位驗證語意,欄位名(`release_date`)會騙人**。

**Q2: 為什麼 7d 門檻是 1.5% 不是別的數字?**
- 波動隨時間 √t 縮放:0.5% × √(~7-9 個交易時段) ≈ 1.3-1.5%,取整。不是精確校準,是「讓 NEUTRAL 在 7d 不再自動必錯」的量級修正;之後可以用 realized vol 動態化。

**Q3: self-consistency 為什麼平手歸 NEUTRAL 而不是取第一個?**
- 三次獨立抽樣方向分歧,代表模型對方向沒有穩定信念 — 這個資訊本身就該映射到「無方向」。取第一個等於把噪音當訊號。

**Q4: 為什麼 reset 只清 FRED 不全清?**
- 錯的是 FRED 的時間錨,其他 source 的錨正確;outcomes 的 `aligned` 規則改了但 `ticker_return` 都存著 — 就地重算即可,不用重抓價格也不用重花 LLM 錢。**清資料的範圍 = 不可修復的範圍**。

**Q5: idle-in-transaction 為什麼會擋 TRUNCATE?普通 SELECT 不是不上鎖嗎?**
- SELECT 會拿 `ACCESS SHARE` 鎖,transaction 不結束鎖就不放;TRUNCATE 要 `ACCESS EXCLUSIVE`,跟任何鎖都衝突 → 排隊;而 Postgres 的鎖排隊是 FIFO,TRUNCATE 排在前面後,**後續所有新 SELECT 也跟著排在 TRUNCATE 後面** — 一條 idle 連線癱瘓整張表。

### 驗收狀態

- [x] 後端 ruff + mypy(strict)0 errors,164 pytest 全綠(13s)
- [x] 前端 eslint + `next build` 通過
- [x] Production:FRED 33/33 重分析(正確錨點 + surprise 指標)、66 筆 v3 predictions 全帶 `direction_7d`、84 筆 v3 outcomes 已回填
- [x] `direction_7d` migration 部署時自動套用(Procfile `alembic upgrade head`)
- [x] Vercel 新 UI + 篩選列上線實測;Railway 全服務 SUCCESS
- [x] 一次性重分析成本 $4.66,落在 $5 日上限內;穩定月成本估 ~$0.7(LLM)+ ~$12-18(Railway)

---

## Milestone 9.7 — 模擬跟單損益(simulated P&L)

> **狀態**:✅ 完成(2026-06-13 單一 session)
> **目標**:回答「如果我從第一個事件開始,每次都照系統的方向判斷下單 $100,現在賺賠多少、報酬率幾 %?」— 把 accuracy(對/錯)翻譯成錢(賺/賠)。
>
> **TL;DR**:
> - **新 endpoint `GET /api/v1/pnl`** — 每筆已驗證的 (prediction, window) outcome 視為一筆交易:BULLISH 做多 $100、BEARISH 做空 $100、NEUTRAL 不進場(不佔資金);損益 = ±$100 × 該視窗的 `ticker_return`,7d 交易跟 validator 一樣優先吃 `direction_7d`
> - **SPY 基準對照** — 同樣的注碼、同樣的視窗,但一律做多 SPY(用 outcome 既存的 `spy_return`),回答「跟單有沒有贏過無腦買大盤」
> - **信心加權變體** — 注碼 = $100 × confidence,回應「按信心指數操作」的字面解讀
> - **權益曲線** — 按名目出場時間(`predicted_at` + 視窗長度)排序累計,前端 recharts 雙線(策略 vs SPY)
> - **Dashboard 新區塊** — 損益 hero、權益曲線、24h/7d/勝率/最佳最差交易卡、按模型/ticker/信心分桶三張損益表
> - **即時更新** — 每次請求從 DB 現算(數百筆 outcome,單一 SELECT),validator 驗完新事件下一次載入就反映;前端 60s refetchInterval

### 設計決策

**做空怎麼模擬?** 預測跌的標準作法就是做空:損益 = 注碼 × (−報酬率)。其他工具(put 選擇權、反向 ETF)有時間價值衰減/槓桿重設,從現有資料推不出來。所以用**純名目反向**(不計借券費、保證金利息、滑價、手續費)— 這是衡量「訊號品質」的標準簡化,文件裡明寫假設。

**報酬率怎麼定義?** 交易跨 ticker/視窗重疊,沒有單一複利帳戶可言。誠實的算法:**總損益 ÷ 總投入名目**(= 平均每注報酬)。$100/注是線性縮放,% 不變。

**為什麼不用排程算?** Outcome 量級是百筆,單一窄 SELECT + Python 聚合 < 10ms,跟 `/accuracy` 同款設計 — 現算永遠最新,零維運。

**正確性錨點**:多數決(consensus)在 analyzer 端就先合併成單筆 prediction 再落 DB(`_consensus_analysis`),每事件也只路由一個模型 → 不會重複下注;1h 是 deprecated 視窗,query 與 service 雙層排除。

### 驗證

- 純函式 `services/pnl.py`(同 `alignment.py` 的「最難邏輯不碰 DB」原則),19 個單元測試:多空方向符號、NEUTRAL 跳過、7d 方向覆蓋、權益曲線按出場排序、信心分桶邊界、空集合
- 本機 docker 卡死(engine 無回應)→ 整合測試交給 CI 的 Postgres service container;push 前用 `app.main` import + SQL compile 煙霧測試補位
- **Replay 驗證**:用公開 API 抓全部 78 事件/291 outcomes,餵進同一個 `simulate()` — 數字跟 `/accuracy` 對得上(291 = 219 交易 + 72 NEUTRAL)
- 上線當下的真實成績:**+$354.47(+1.62%),勝率 74.4%,SPY 同注碼 +$207.34(+0.95%)** — 訊號有正 edge;信心分桶單調遞增(0.55-0.65 → +0.71%/注,0.85-1.00 → +2.33%/注),信心指數在「錢」的維度上也是有校準的

---

## Milestone 10 — Auth + watchlist

> **狀態**:⏳ 未開始
> **目標**:JWT auth、watchlist CRUD、in-app notification。

_(待實作)_

---

## Milestone 11 — Observability

> **狀態**:⏳ 未開始
> **目標**:Prometheus metrics、Grafana dashboard。

_(待實作)_

---

## Milestone 12 — Polish + ship

> **狀態**:⏳ 未開始
> **目標**:README + 架構圖、Loom demo、ADR 整理。

_(待實作)_

---

## Milestone 13 — AWS Infrastructure as Code

> **狀態**:⏳ 未開始
> **目標**:用 Terraform 在 AWS 建好 VPC + ECS + RDS + ElastiCache + ALB(尚未部署 app)。

_(待實作)_

---

## Milestone 14 — AWS Application Migration + Cutover

> **狀態**:⏳ 未開始
> **目標**:把 production 從 Railway 遷移到 AWS,完成 cutover。

_(待實作)_

---

## 常見面試問題整理

_(隨開發進度累積。每完成一個 milestone,把該階段可能被問到的問題寫進來,並附上自己的答案大綱。)_

### 系統設計類

_(待補)_

### Python / FastAPI 類

_(待補)_

### Database / SQL 類

_(待補)_

### Celery / 非同步處理類

_(待補)_

### LLM / Prompt engineering 類

_(待補)_

### DevOps / AWS 類

_(待補)_
