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
