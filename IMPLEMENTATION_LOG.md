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

> **狀態**:⏳ 未開始
> **目標**:加 SEC EDGAR、FOMC adapter,統一 `RawEvent` schema。

_(待實作)_

---

## Milestone 4 — Prices + earnings

> **狀態**:⏳ 未開始
> **目標**:yfinance 整合、price_snapshots 表、Redis 快取。

_(待實作)_

---

## Milestone 5 — LLM analysis

> **狀態**:⏳ 未開始
> **目標**:OpenAI/Anthropic + instructor,Analyzer worker。

_(待實作)_

---

## Milestone 6 — Validation loop

> **狀態**:⏳ 未開始
> **目標**:Validator worker,outcome 計算,`/accuracy` endpoint。

_(待實作)_

---

## Milestone 7 — Frontend Sprint 1

> **狀態**:⏳ 未開始
> **目標**:Next.js 14 App Router scaffolding,timeline + event detail 頁。

_(待實作)_

---

## Milestone 8 — Frontend Sprint 2 + tests + CI

> **狀態**:⏳ 未開始
> **目標**:Recharts 圖、dashboard 頁、pytest 覆蓋率 > 75%、GitHub Actions CI。

_(待實作)_

---

## Milestone 9 — Deploy (Railway)

> **狀態**:⏳ 未開始
> **目標**:後端 + worker 部署到 Railway,前端到 Vercel。

_(待實作)_

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
