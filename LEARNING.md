# EventSense 從零學習指南

> **這份文件給誰看?** — 給你自己。寫給「**對 backend / frontend / DevOps 都只懂皮毛**」的人,把每個 milestone 用最白話、最詳細的方式說一遍。
>
> **跟 [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md) 的差別?** — `IMPLEMENTATION_LOG.md` 是「**做了什麼 + 為什麼這樣選**」的工程筆記。這份是「**這些概念到底是什麼意思 + 為什麼世界要這樣設計**」的入門教材。
>
> **怎麼讀?** — 第一次按順序讀(每個 milestone 都是建立在前一個之上)。之後當字典查。
>
> **語言**:繁體中文,技術名詞保持英文。

---

## 目錄

- [Part 0:Foundation — 開工前必懂的基礎](#part-0foundation--開工前必懂的基礎)
- [Part 1:Milestone 1 — Foundation(蓋專案、起容器、第一個 endpoint)](#part-1milestone-1--foundation)
- [Part 2:Milestone 2 — Scheduled Fetching(Celery + Beat 排程)](#part-2milestone-2--scheduled-fetching)
- [Part 3:Milestone 3 — Multi-source Ingestion(重構 + SEC + FOMC)](#part-3milestone-3--multi-source-ingestion)
- [Part 4:Milestone 4 — Prices + Earnings(時間序列 + Redis cache)](#part-4milestone-4--prices--earnings)
- [Part 5:Milestone 5 — LLM Analysis(OpenAI + 預測)](#part-5milestone-5--llm-analysis)
- [Part 6:Milestone 6 — Validation Loop(預測驗證閉環)](#part-6milestone-6--validation-loop)
- [Part 7:Milestone 7 — Frontend Sprint 1(Next.js + UI)](#part-7milestone-7--frontend-sprint-1)
- [Part 8:Milestone 8 — Frontend Sprint 2 + CI(圖表 + dashboard + GitHub Actions)](#part-8milestone-8--frontend-sprint-2--ci)
- [Part 9:Milestone 9 — Deploy (Railway + Vercel)](#part-9milestone-9--deploy-railway--vercel)
- [Part 10:術語對照表(查得到的字典)](#part-10術語對照表)
- [Part 11:面試講故事 — 5 分鐘版每個 milestone](#part-11面試講故事)

---

# Part 0:Foundation — 開工前必懂的基礎

## 0.1 什麼是「web app」?

打開瀏覽器看 Gmail / Facebook / Twitter,你看到的東西叫 **web app**。它不是一個程式,是**兩個半**:

```
[你的瀏覽器]  ←─ HTTP ─→  [伺服器]
   ↑                            ↓
   │                         Database
渲染畫面                     (資料庫)
給你看
```

**三個角色**:
- **Browser(瀏覽器)**:跑在你電腦,負責渲染 HTML + 跑 JavaScript + 接你的滑鼠 / 鍵盤操作。**這是 frontend(前端)。**
- **Server(伺服器)**:遠端那台機器,接收 HTTP request、處理、回 response。**這是 backend(後端)。**
- **Database(資料庫)**:伺服器旁邊那個專門存資料的程式,通常是 PostgreSQL / MySQL / MongoDB。資料永久存著,server 程式重啟資料不會丟。

## 0.2 HTTP 是什麼?

**HTTP** = HyperText Transfer Protocol。瀏覽器跟伺服器溝通的「**共同語言**」。

最常見兩種 HTTP message:

**Request(瀏覽器發給 server)**:
```
GET /api/v1/events HTTP/1.1
Host: localhost:8000
Accept: application/json
```
意思:「我想要 `/api/v1/events` 這個資源,回我 JSON 格式」

**Response(server 回瀏覽器)**:
```
HTTP/1.1 200 OK
Content-Type: application/json

{"data": [...], "meta": {"total": 19}}
```
意思:「OK,給你 JSON,內容如下」

**Status codes 你最常見幾個**:
- `200 OK` — 成功
- `400 Bad Request` — 你 request 寫錯了
- `401 Unauthorized` — 沒登入
- `403 Forbidden` — 登入了但沒權限
- `404 Not Found` — 資源不存在
- `500 Internal Server Error` — server 自己 bug

**HTTP methods**(動詞):
- `GET` — 拿資料,不該改任何東西
- `POST` — 新增資料 / 觸發動作
- `PUT` / `PATCH` — 更新資料
- `DELETE` — 刪資料

## 0.3 API 是什麼?

**API(Application Programming Interface)** = 「**程式之間溝通的合約**」。

對 web app 而言通常指 **REST API** — 用 HTTP 暴露一組 endpoint:
```
GET    /api/v1/events           ← 列出 events
GET    /api/v1/events/{id}      ← 看單一 event
POST   /api/v1/events           ← 新增 event
DELETE /api/v1/events/{id}      ← 刪 event
```

每個 endpoint = 「**這個 URL + 這個 method = 做這件事**」的約定。

## 0.4 JSON 是什麼?

**JSON(JavaScript Object Notation)** = 結構化資料的文字格式。

```json
{
  "id": "abc-123",
  "title": "AAPL 8-K filed 2026-05-22",
  "tickers": ["AAPL"],
  "confidence": 0.75,
  "published": true
}
```

特性:
- **人類看得懂**(vs binary format 像 Protobuf)
- **任何程式語言都能解析**
- 純文字,可以放進 HTTP body 直接傳

是現代 web API 的事實標準。

## 0.5 為什麼用 Python(backend)+ TypeScript(frontend)?

### Python 給 backend 的理由
- **資料處理 / ML 生態超強**(NumPy / Pandas / scikit-learn / PyTorch)
- **語法簡潔**(同樣邏輯比 Java / Go 短 30%+)
- **FastAPI / Django / Flask 都是頂級框架**
- **跟 LLM API 整合最好**(OpenAI / Anthropic 官方 SDK 都是 Python first)
- 缺點:比 Go / Rust / Java 慢 10-100 倍 — 但對「等 DB / 等 API」的 backend,瓶頸不在 CPU

### TypeScript 給 frontend 的理由
- 瀏覽器只認 JavaScript(歷史包袱),所以 frontend 只能寫 JS 或編譯到 JS 的語言
- **TypeScript 是 JS 加型別**(微軟出品)→ 抓出 80% 的低級 bug 在 compile time
- 跟 React / Next.js / Vue 生態完全整合
- 現代 frontend 工作 JD 90%+ 寫 TypeScript

## 0.6 一個 request 從點擊到回應的旅程

你在 EventSense 點一張 event 卡片,背後發生什麼:

```
1. 瀏覽器看到 <a href="/events/abc-123">,你點下去
2. 瀏覽器發 HTTP GET request 到 localhost:3000/events/abc-123
3. Next.js dev server 收到 → 找對應的 page.tsx → server-render 初始 HTML
4. HTML 回到瀏覽器 → 顯示出來 (但裡面的資料還沒)
5. 同時 JS bundle 也下載到瀏覽器
6. JS 在 browser 跑起來 → React component 啟動 → TanStack Query useQuery 觸發
7. 瀏覽器發第二個 HTTP GET 到 localhost:8000/api/v1/events/abc-123
8. FastAPI 收到 → CORS check pass → 路由到 get_event 函式
9. get_event 用 SQLAlchemy 查 Postgres:SELECT ... FROM events WHERE id = ...
10. Postgres 回 row → SQLAlchemy 轉成 Event ORM 物件
11. FastAPI 用 Pydantic schema 轉成 JSON → 回 response
12. 瀏覽器收到 JSON → TanStack Query 把結果塞進 cache + 通知 component
13. React component 重新 render → UI 更新顯示 event 資料
```

**14 步**就為了一個點擊。每一步都可能出問題 — 這就是 backend 工程師的工作。

---

# Part 1:Milestone 1 — Foundation

## 1.1 這階段在幹嘛?

```
從零的資料夾 → 一個能跑的「最小可行 backend」
```

具體成果:
- 一個 Python 專案(用 uv 管理)
- 一個 Docker compose 起 PostgreSQL + Redis + FastAPI
- 一張 events 資料表
- 一個 `GET /api/v1/events` endpoint
- 一個手動可以從 FRED API 抓 CPI 資料的功能

## 1.2 新概念清單

1. **uv** — Python 套件管理
2. **Virtual environment(venv)**
3. **Docker / Container / Image**
4. **docker-compose**
5. **PostgreSQL** — 關聯式資料庫
6. **Redis** — in-memory key-value store
7. **FastAPI** — Python web framework
8. **ASGI / WSGI** — Python web app 規格
9. **SQLAlchemy 2.0 async** — ORM
10. **Alembic** — DB migration
11. **Pydantic / pydantic-settings** — 資料驗證
12. **structlog** — 結構化 logging
13. **Async / await** — 非同步程式
14. **Connection pool**
15. **Dependency injection**(FastAPI Depends)
16. **CORS preview**(M7 才正式講)
17. **`.env` + 環境變數**
18. **`.gitignore` + secret hygiene**

---

## 1.3 Docker / Container — 「打包整台電腦給對方」

### 問題:「我這邊可以跑啊!」

10 年前部署一個 Python app:
```
你的筆電:   Python 3.10, OpenSSL 1.1, libpq 12, macOS Big Sur
production:  Python 3.9, OpenSSL 1.0, libpq 11, Ubuntu 20.04
```

跑起來行為不一樣 → 神祕 bug → debug 三天才發現是 OpenSSL 版本不同。

### Container 是什麼?

**Container** = 「**把你的程式 + 它需要的所有東西(Python 版本、套件、系統 library、設定檔)打包成一個密封盒**」

比喻:
- 傳統部署 → 寄一份 Word 檔給對方,期望他電腦有對的 Word 版本
- Container → 把整台電腦截圖丟給對方,他打開就是你看到的畫面

### Image vs Container

- **Image** = 「**藍圖**」(蓋盒子用的圖)— 不變的,可以版本化、推到 registry
- **Container** = 從 Image 蓋出的「**實際運行中的盒子**」— 跑起來、跑完、刪掉,Image 還在

```
docker build → 從 Dockerfile 蓋出 Image (一次)
docker run   → 從 Image 起 Container (每次)
```

### Dockerfile 是食譜

```dockerfile
FROM python:3.12-slim          # 起點:「一台裝好 Python 3.12 的乾淨 Linux」
WORKDIR /app                    # 在容器內進到 /app 目錄
COPY pyproject.toml ./          # 把套件清單複製進去
RUN uv sync                     # 裝套件
COPY . .                        # 把我們的 source code 複製進去
CMD ["uvicorn", "app.main:app"] # 啟動時跑這個指令
```

**重點**:這份食譜跑在誰的電腦上,蓋出的 image 都一模一樣。

### docker-compose — 「多個盒子串起來」

我們需要 PostgreSQL + Redis + FastAPI 三個 service 同時跑 + 彼此能溝通。手動跑三個 `docker run` 很麻煩。

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    ports: ["5432:5432"]
  redis:
    image: redis:7-alpine
  backend:
    build: ./backend
    depends_on: [postgres, redis]
```

一條 `docker compose up` 把三個盒子一起拉起來。

**Compose 內部魔法**:每個 service 名字自動變成 DNS hostname。所以 backend 連 Postgres 寫 `host=postgres`(不是 `localhost`)。

### Anonymous Volume 的坑

我們 docker-compose 有這個:
```yaml
volumes:
  - ./backend:/app           # bind mount,host 跟 container 共享
  - /app/.venv               # anonymous volume
```

第一行:把 host 的 `./backend` 整個目錄掛進 container 的 `/app`。改 code 立刻反映在 container 內(hot reload)。

第二行:**告訴 docker「`/app/.venv` 這個路徑不要被上面的 bind mount 蓋掉」**。為什麼需要?
- 我們 host 的 `backend/` 沒有 `.venv/` 資料夾(用 uv 建在容器內)
- Bind mount 會把 host 的「沒有 .venv」也蓋過去,container 就找不到套件了
- Anonymous volume 用一個 docker 管理的隱形 volume 「擋」在那個路徑

**這個 anonymous volume 會持續存在不會自動更新**。改完 dependencies(新增套件)`docker compose up --build` 重 build image,但 container 啟動時 anonymous volume 蓋回去 → 新套件沒了!

修法:
```bash
docker compose up --build -d --force-recreate --renew-anon-volumes
```

`--renew-anon-volumes` 強制重建匿名 volume。我們在 M3 / M4 / M5 都踩過這坑。

---

## 1.4 PostgreSQL — 我們選的資料庫

### 為什麼選 PostgreSQL?

四大主流關聯式資料庫:
- **PostgreSQL**:開源,功能最全,業界共識「**現代 default**」
- **MySQL**:也很流行,但 PG 在 JSON / partial index / window function 等高級功能完勝
- **SQLite**:嵌入式,單檔案,適合手機 app / 小工具,不適合多人寫入
- **Oracle**:企業級,要付錢

PostgreSQL 給 EventSense 特別有用:
- **JSONB** — 把 JSON 當 first-class 欄位存,還可以 index
- **ENUM type** — `event_source` 限定只能是 FRED / SEC_EDGAR / FOMC / EARNINGS
- **ARRAY** — `affected_tickers` 直接存 `['AAPL', 'MSFT']`
- **`FOR UPDATE SKIP LOCKED`**(M5/M6 用)— queue table 的關鍵
- **`ON CONFLICT DO NOTHING`**(M4 用)— bulk upsert 必備

### 為什麼**不**選 MongoDB?

文件型 DB,適合「**schema 完全不固定**」的場景。但:
- 我們的資料 schema 很穩定(events / predictions / outcomes 有明確結構)
- 我們需要 FK / transaction(MongoDB 弱)
- 預測準確率追蹤是 financial-adjacent,ACID 不能省

**MongoDB 在我們這個場景沒有任何優勢**。

## 1.5 Redis — in-memory key-value store

**Redis** = 把 key-value pair 存在記憶體裡的資料庫。比 PostgreSQL **快 100 倍**(0.1ms vs 5ms),代價是:
- **重啟資料消失**(可選 persistence,但通常當 cache 用就接受丟失)
- **不適合複雜 query**(就是 GET / SET key)

M1 我們起了 Redis 但**還沒用** — 它是給 M2 的 Celery broker 跟 M4 的 cache 預備的。

## 1.6 FastAPI — Python web framework

### 三大 Python web framework 比較

| | Django | Flask | FastAPI |
|---|---|---|---|
| 出生 | 2005 | 2010 | 2018 |
| 路線 | 全端「batteries included」 | 極簡 | 現代 + async + 型別 |
| Async support | 後來補 | 後來補 | 第一天就有 |
| 學習曲線 | 陡 | 平緩 | 中等 |
| 適合 | 全端 monolith | 小工具 | 純 API |

我們選 FastAPI 因為:
- 純 API 用途(frontend 分開)
- async-native(打 FRED / SEC / LLM 一堆外部 API 需要)
- 自動產生 Swagger UI(`http://localhost:8000/docs`)
- 配 Pydantic 型別最舒服
- 招聘 JD 出現率高(新案幾乎 100% 用它,不用 Django/Flask)

### Hello FastAPI

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/api/v1/events")
async def list_events():
    return {"data": [], "meta": {"total": 0}}
```

`@app.get(...)` decorator:這個 function 處理「**GET 這個 URL**」的 request。

Function 回什麼,FastAPI 自動 serialize 成 JSON。

### Swagger UI

打開 `http://localhost:8000/docs` → 自動看到所有 endpoint 的互動文件 + 「Try it out」按鈕直接測試。

完全免設定,FastAPI 從你的 function signature 跟 docstring 推出來。

## 1.7 ASGI / WSGI — Python web 規格

歷史:
- **WSGI**(Web Server Gateway Interface, 2003)— Python web app 跟 server 通訊的標準。**同步**,只能一個 request 跑完換下一個。
- **ASGI**(Asynchronous Server Gateway Interface, 2018)— WSGI 的 async 版,支援 async + WebSocket + HTTP/2。

我們用 ASGI(FastAPI 是 ASGI app),server 用 **uvicorn**(輕量 ASGI server)。

```
uvicorn app.main:app
       └── 找 app/main.py 裡名為 app 的 FastAPI instance
```

## 1.8 Async / await — 「等的時候去做別的事」

### 同步 vs 非同步 — 餐廳服務生比喻

**同步**:
```
1. 接客 A → 帶位 → 等他點餐(3 分鐘,站著等)
2. 送單到廚房 → 等出菜(15 分鐘,站著等)
3. 上菜給 A
4. 才能接客 B
```
一個服務生服務一桌,中間都在「站著等」。

**非同步**:
```
1. 接客 A → A 看菜單(不等)→ 接客 B → B 看菜單(不等)→ 看 C 點好了沒
2. C 點完 → 送單到廚房(不等)→ 看 A 點好了沒
3. 廚房叫「A 的菜好了」→ 去拿,送給 A
```
**一個服務生服務 10 桌**,因為他不會卡在「等」上面。

### 對應到 backend

```python
# 同步(假設用 Flask)
def get_events():
    rows = db.query(...)  # 等 DB 5ms,期間 worker 完全卡死
    return rows

# 非同步(FastAPI)
async def get_events():
    rows = await db.scalars(...)  # 等 DB 5ms,期間 event loop 去處理別的 request
    return rows
```

那個 `await` 關鍵字 = 「**我要等了,你去做別的,我好了再回來**」

### 為什麼後端特別需要 async?

Backend 90% 時間在等:
- 等 DB query 返回
- 等外部 API 回應
- 等網路 round trip

「**等的時候不能浪費,要去服務別人**」 — 這就是 async 的價值。

對 EventSense 特別重要 — 我們要打 FRED / SEC / FOMC / OpenAI / Anthropic 一堆外部 API,每次都要等百毫秒到幾秒。

### 「Event loop」是什麼

`asyncio.run(some_async_func())` 背後:
- 啟動一個 **event loop**(事件迴圈)
- Loop 維護一個「**等的工作」清單**
- 哪個工作好了(I/O 回來了)→ loop 跑那個工作的 callback
- 一個 event loop 跑一個 thread,但能同時管 1000+ async task

**「event loop 跟誰 binding」很重要** — M3 / M5 都踩過這個坑(M3 是 asyncpg connection,M5 是 SQLAlchemy engine)。

## 1.9 uv — Python 套件管理

歷史包袱:
```
2010s 早期:pip(裝套件)+ virtualenv(隔離)+ pyenv(切 Python 版本)
2018:    pipenv 想統一,半成功
2020:    poetry 興起,變主流
2024:    uv 出現(Astral 出品,就是 ruff 那家)
```

**uv 的優勢**:
- **比 poetry 快 10-100 倍**(Rust 寫的)
- **單一 binary**,不靠 Python 本身就能裝
- **管 Python 版本 + venv + 套件 一條龍**(取代 pyenv + virtualenv + poetry 三個)
- `uv.lock` 跨平台

### 我們的 workflow

```bash
uv init        # 開新專案,產生 pyproject.toml
uv add fastapi # 加套件,寫進 pyproject.toml + 鎖到 uv.lock
uv sync        # 從 lock 檔同步 .venv/
uv run pytest  # 在 venv 內跑指令
```

## 1.10 Virtual Environment — 「每個專案自己一份 Python」

```
不用 venv:           用 venv:
  系統 Python          系統 Python
    └ all packages       
                       專案 A/.venv/        專案 B/.venv/
                       └ Django 4.0           └ Django 3.2
```

**為什麼需要?** 兩個專案需要不同版本的同一套件 — 系統 Python 只能裝一個版本,衝突。

每個專案自己的 `.venv/` 資料夾,獨立的 Python interpreter + packages。`uv` 自動幫你建。

## 1.11 SQLAlchemy 2.0 async — ORM

### 沒 ORM 的世界

```python
sql = f"INSERT INTO events (source, title) VALUES ('{source}', '{title}')"
cursor.execute(sql)
```

問題:
- **SQL injection**:`title = "'; DROP TABLE events; --"` → 整張表被刪
- **沒型別**:`cursor.fetchone()` 回 tuple,要靠 index 取
- **改 schema 痛苦**:全 grep 找 SQL 字串

### 有 ORM(SQLAlchemy 2.0)

```python
event = Event(source=EventSource.FRED, title="...")
db.add(event)
await db.commit()

rows = await db.scalars(select(Event).where(Event.source == EventSource.FRED))
```

**ORM(Object-Relational Mapping)** = 「**用 class 操作 DB,不寫 SQL 字串**」

我們的 model:
```python
class Event(Base, TimestampMixin):
    __tablename__ = "events"
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True)
    source: Mapped[EventSource] = mapped_column(Enum(EventSource), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    # ...
```

`Mapped[]` 是 SQLAlchemy 2.0 的 type annotation,**IDE 看得懂**(autocomplete 起飛)。

### 為什麼 async SQLAlchemy?

跟 FastAPI 一致 — 一路 `await` 到底,中間不會被 sync 操作卡住。

跟 asyncpg(async PG driver)配對使用。

## 1.12 Alembic — DB Migration

### 沒有 migration 的痛

```
你週一加了 events.published_at 欄位
同事週二 pull → 他的 DB 沒這欄 → 程式炸
你週三部署 production → 忘了「ALTER TABLE」 → 炸
```

### Migration 是 DB schema 的 git

```
alembic/versions/
├── 0001_initial_events.py
├── 0002_add_predictions.py
├── 0003_add_prediction_outcomes.py
└── ...
```

每個檔案 = 「**從上個版本到這個版本要怎麼改 schema**」。

```python
def upgrade():
    op.create_table('events', ...)

def downgrade():
    op.drop_table('events')
```

DB 裡有一張 `alembic_version` 表記錄「**目前在哪個版本**」。

```bash
alembic upgrade head      # 跑到最新版
alembic downgrade -1      # 倒退一個版本
```

### `--autogenerate` 偵測

```bash
alembic revision --autogenerate -m "add predictions table"
```

它會:
1. 連到你的 DB,看現況
2. 跟你 Python model 的 metadata 比對
3. 自動產生 `op.create_table(...)` migration

**90% 對,10% 要手動修**(我們在 M1 補了 `DROP TYPE` for enum types)。

## 1.13 Pydantic — 資料驗證

### Pydantic model = 帶型別的 dict

```python
class EventRead(BaseModel):
    id: uuid.UUID
    source: EventSource
    title: str
    affected_tickers: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
```

把 dict / JSON 轉成 Pydantic 物件:
```python
event = EventRead.model_validate(raw_data)
# 自動驗證:每個欄位有沒有、型別對不對、confidence 在不在 0-1 範圍
```

驗證失敗:
```python
EventRead.model_validate({"confidence": 1.5})
# ValidationError: confidence: Input should be less than or equal to 1
```

### Pydantic vs dataclass

- **dataclass**(stdlib):只給型別 hint,**不驗證 runtime**
- **Pydantic**:給型別 hint + **真的驗證**

FastAPI 用 Pydantic 在 API 邊界做雙向驗證:
- Request body 進來 → 用 Pydantic 解析 + 驗證 → 給你 typed object
- Function return → 用 Pydantic schema 序列化成 JSON

我們在 M3 學到「**邊界用 Pydantic,內部 hot path 用 dataclass**」原則。

## 1.14 Connection Pool — 不要每次都建新連線

### 沒 pool

```
每次 request:
  1. TCP handshake to PG (5ms)
  2. PG 認證 (3ms)
  3. SELECT (2ms)
  4. 關連線
```

80% 時間在 1+2,真正幹活的時間只有 20%。

### 有 pool

```python
engine = create_async_engine(url, pool_size=5, max_overflow=10)
```

意思:**預先開好 5 個連線放池子裡**,需要時撈、用完還回去。最多再臨時加 10 個。

第 N 次 request:
```
1. 從 pool 撈現成 (0.01ms)  ← 800 倍快
2. SELECT (2ms)
3. 還回 pool
```

### `pool_pre_ping=True`

連線可能會壞掉(網路抖、DB 重啟、防火牆 reset),pool 不會自動知道。

`pool_pre_ping=True` = 「**每次從 pool 拿出來之前先 ping 一下確認還活著**」,死了就丟掉重建。

成本:每次多 0.1ms。回報:不會在 PG 重啟後第一個 request 神祕 500。

## 1.15 Dependency Injection(FastAPI Depends)

### 沒 DI

```python
@app.get("/events")
async def list_events():
    session = AsyncSessionLocal()  # 自己拿 DB
    try:
        rows = await session.scalars(...)
        return rows
    finally:
        await session.close()  # 不能忘
```

問題:
- 測試難(怎麼換成 mock DB?)
- 重複(每個 endpoint 寫一遍 try/finally)
- 隱式依賴(看 function signature 不知道它要 DB)

### 有 DI

```python
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
    # 出 with → 自動 close

@app.get("/events")
async def list_events(db: AsyncSession = Depends(get_db)):
    rows = await db.scalars(...)
    return rows
```

FastAPI 看到 `Depends(get_db)`:
1. 自動 call `get_db()`
2. 拿 yield 出來的 session 傳給 `db` 參數
3. Endpoint 結束自動跑 yield 之後的 cleanup

### 測試的好處

```python
app.dependency_overrides[get_db] = lambda: fake_db
# Endpoint code 不用改,跑起來用的是 fake_db
```

M8 我們的 API test 就是用這招 swap 進 NullPool session。

## 1.16 Structured Logging

### 傳統 print

```python
print(f"Fetched CPI for {date}, got {count} observations")
```
```
Fetched CPI for 2026-04-01, got 12 observations
```

想知道「總共抓多少」要寫 regex 從字串挖數字。

### Structured(structlog)

```python
logger.info("fred.fetch.completed", series_id="CPIAUCSL", date="2026-04-01", count=12)
```

JSON 模式輸出:
```json
{"event": "fred.fetch.completed", "series_id": "CPIAUCSL", "date": "2026-04-01", "count": 12, "timestamp": "..."}
```

餵給 Grafana Loki / CloudWatch:
```
查詢:event="fred.fetch.completed" AND count > 0 AND time > today
→ 一秒拿結果
```

**`print` 給人看,structured log 給機器看**。

## 1.17 `.env` + Secret Hygiene

### `.env` 是什麼

純文字檔放敏感設定:
```
DATABASE_URL=postgresql://...
OPENAI_API_KEY=sk-...
FRED_API_KEY=...
```

啟動時 `pydantic-settings` 讀進來變成 `Settings` 物件。

### 永遠 `.gitignore` `.env`

```
# .gitignore
.env
.env.local
.env.*.local
```

**`.env` 進 git** = secret 永久外流(git history 抹不掉,GitHub 的 search 全索引)。

我們有個對應的 `.env.example`(可以 commit)讓人知道有哪些變數要填:
```
DATABASE_URL=postgresql+asyncpg://eventsense:eventsense@localhost:5432/eventsense
FRED_API_KEY=
OPENAI_API_KEY=
```

### Production 不用 `.env`,用 secret manager

- AWS:Secrets Manager / SSM Parameter Store
- Railway / Vercel:平台內建的 secret UI
- Heroku:`heroku config:set`

`.env` 只給 dev 用。

---

## 1.18 M1 速記表

| 概念 | 一句話 |
|---|---|
| **Docker container** | 把程式 + 環境打包的密封盒,「我這邊能跑」的根除方案 |
| **Docker image** | 蓋盒子用的藍圖,可版本化 |
| **docker-compose** | 用 YAML 描述多個 service 的編排 |
| **anonymous volume** | 沒名字的 docker volume,擋住 bind mount 蓋路徑 |
| **PostgreSQL** | 業界 default 的關聯式 DB,JSONB / ENUM / ARRAY 樣樣行 |
| **Redis** | 記憶體 DB,快 100 倍,適合 cache / broker |
| **FastAPI** | 現代 Python web framework,async-native + 型別友善 |
| **ASGI / WSGI** | Python web app 跟 server 的通訊規格(async vs sync) |
| **async / await** | 「等的時候去做別的事」 — 高 throughput backend 必備 |
| **Event loop** | async code 的指揮中心,管「現在誰該跑」 |
| **uv** | 新一代 Python 套件管理,比 poetry 快 10-100x |
| **venv** | 每個專案隔離的 Python 環境 |
| **ORM** | 用 class 操作 DB 不寫 SQL,SQLAlchemy 2.0 是業界標準 |
| **Migration** | DB schema 的版本控制(Alembic) |
| **`--autogenerate`** | Alembic 自動 diff model vs DB 生成 migration |
| **Pydantic** | 帶型別驗證的 dict,API 邊界必備 |
| **Connection pool** | 預先開好的 DB 連線池,降低 round trip 成本 |
| **`pool_pre_ping`** | 拿連線前 ping 一下,防 stale connection |
| **Dependency Injection** | 「我需要 X」由 framework 注入,測試時可 swap |
| **Structured logging** | log 用 key=value 結構,給機器 grep |
| **`.env` 必 gitignore** | secret 進 git 等於永久外流 |

---

# Part 2:Milestone 2 — Scheduled Fetching

## 2.1 這階段在幹嘛?

M1:**手動**呼叫一個 endpoint 才會去抓 FRED 資料。
M2:**自動排程** — 每小時自己去抓,不用人介入。

## 2.2 新概念清單

1. **Celery** — 分散式任務佇列
2. **Celery Beat** — 排程器
3. **Message broker** — Redis 當訊息中介
4. **Task queue / Producer / Consumer**
5. **Worker process**
6. **`asyncio.run()` 包 async code 在 sync task 裡**
7. **`task_acks_late` + at-least-once delivery**
8. **`worker_prefetch_multiplier`**
9. **Idempotency** — 「跑幾次結果都一樣」
10. **tenacity** — retry library
11. **兩層 retry**(tenacity + Celery)
12. **`crontab`** schedule expression
13. **Pytest + asyncio**
14. **Mock(unittest.mock, pytest-httpx)**
15. **Integration test vs unit test**
16. **`TRUNCATE TABLE ... CASCADE`**
17. **`ProcessorFormatter`**(structlog 跟 stdlib logging 的橋)

---

## 2.3 Celery — 分散式任務佇列

### 問題:長時間任務不能塞在 HTTP request 裡

```python
@app.get("/api/v1/events")
async def list_events():
    events = await db.scalars(...)
    await fetch_fred_cpi()  # ← 等 5 秒
    return events
```

問題:
- User 等 5 秒才看到網頁,體驗爛
- 沒人打這 endpoint 就永遠不更新
- 如果這 5 秒中失敗,user 看到 500

### 解法:**把慢動作丟給 background worker**

```
Web request → 立刻回應
       │
       ├─→ enqueue「跑 fetch_fred_cpi」到 task queue
       
       ↓ 同時
       
Worker process(獨立) → 從 queue 拿任務 → 跑 → 寫進 DB
```

**Celery** 是 Python 生態最成熟的分散式任務佇列。

### 三個角色

1. **Producer** — 「**我有事情要做**」的人
   - 例:Beat 排程器、API endpoint
2. **Broker** — 「**訊息中介**」(Redis / RabbitMQ)
   - 暫存「待辦事項」
3. **Consumer / Worker** — 「**我有空,給我事**」的人
   - 從 broker 拿任務,實際執行

```
Beat:「跑 fetch_fred_cpi」→ Redis (broker) ─→ Worker A
                                          └→ Worker B
                                          └→ Worker C
                                          (多個 worker 平行搶)
```

### Celery Beat — 排程器

**Beat** 是獨立的 process,工作只有一個:**看時鐘,到時間就 enqueue 任務**。

```python
celery_app.conf.beat_schedule = {
    "fred-hourly": {
        "task": "app.tasks.fetchers.fetch_fred_cpi_task",
        "schedule": crontab(minute=0),  # 每小時整點
    },
}
```

### `crontab` 是什麼

Linux cron 的時間表達式:
```
crontab(minute=0)              # 每小時整點(0 分)
crontab(minute="*/5")          # 每 5 分鐘
crontab(hour=14, minute=30)    # 每天 14:30 UTC
crontab(day_of_week="mon-fri") # 週一到週五
```

**5 個欄位**:`minute hour day_of_month month day_of_week`

## 2.4 Worker 設定 — 三個關鍵 flag

```python
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.tasks.fetchers.*": {"queue": "fetch_queue"},
    },
)
```

### `task_acks_late=True`

**Default**(False):worker 拿到 task 就 ack(告訴 broker「收到了」)→ 執行 → 中間 crash → **task 永遠丟失**。

**`acks_late=True`**:worker 拿到 task → 執行 → 成功才 ack → crash 時 broker 看到沒 ack,**redeliver 給下個 worker**。

代價:**同一個 task 可能跑兩次**(at-least-once delivery)。

要求:**task 必須 idempotent**(下一節)。

### `worker_prefetch_multiplier=1`

預設一個 worker 從 broker 一次 prefetch 4 個 task 進記憶體。對於慢任務不好 — 一個 worker 卡在跑 task A 時其他 prefetched task 也只能等。

設 1 = 一次只拿一個,跑完才拿下個。對 slow LLM task 重要(M5)。

### 多個 queue

```python
task_routes={
    "app.tasks.fetchers.*":   {"queue": "fetch_queue"},      # I/O bound
    "app.tasks.analyzers.*":  {"queue": "analyze_queue"},    # LLM (慢)
    "app.tasks.validators.*": {"queue": "validate_queue"},   # I/O bound
}
```

啟動 worker 時 `-Q fetch_queue` 限定它只聽 fetch_queue → **慢的 LLM call 不會佔住 quick fetch 的 worker slot**。

## 2.5 Idempotency — 「跑幾次結果都一樣」

### 定義

```
不 idempotent:轉帳 100 元跑 5 次 → 轉了 500 元 ❌
Idempotent:  把 balance 設為 1000 跑 5 次 → 還是 1000 ✅
```

### 為什麼 fetcher 必須 idempotent

`acks_late + retry + 人為操作` 三個原因 task 可能被跑多次。如果 fetcher 不 idempotent:
```
跑 1 次 → 1 筆 CPI in DB
跑 2 次 → 2 筆一模一樣的 CPI ❌
```

統計分析全錯。

### 怎麼做到

```python
# DB 層:UNIQUE 約束
UNIQUE (source, external_id)

# Application 層:
try:
    db.add(new_event)
    await db.flush()
except IntegrityError:
    await db.rollback()
    continue              # 已經有了就跳過
```

**跑 N 次,DB 最終狀態完全一樣**。

## 2.6 Async code 在 sync Celery task 裡

Celery 是 sync 框架,但我們的 adapter 是 async(用 httpx async client、asyncpg)。怎麼搭?

```python
@celery_app.task
def fetch_fred_cpi_task():  # sync function
    return asyncio.run(_run())  # 開個 event loop 跑 async code

async def _run():
    async with transient_session() as db:
        events = await fred.fetch_new()
        return await persist_events(db, events)
```

`asyncio.run()` = **「開個新 event loop,跑這段 async code,跑完關 loop」**。

成本:每個 task 開關 loop ~毫秒級。對「**每小時跑一次的 task**」完全無感。

### 為什麼這個 pattern 有時會出 bug?

M5 / M6 / M8 我們都踩過 — `asyncio.run()` 每次新 loop,但 SQLAlchemy 的 pooled engine 把 connection 跟「**開它的 loop**」綁定。

跨 loop 用 connection → `got Future attached to a different loop` 炸出來。

修法:**worker 場景用 `NullPool`**(每次連線、不重用)。

## 2.7 兩層 retry — tenacity + Celery

```python
# Inner: tenacity 在 adapter 裡
@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def _fetch_series_observations(...):
    ...

# Outer: Celery 在 task 上
@celery_app.task(
    autoretry_for=(httpx.HTTPError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def fetch_fred_cpi_task():
    ...
```

職責分明:

| 層 | 處理什麼 | 時間尺度 |
|---|---|---|
| **tenacity**(adapter 內) | 一次 HTTP call 內網路抖一下 | 1-10 秒內解決 |
| **Celery autoretry**(task 層) | 整個外部服務 outage | 1-10 分鐘 backoff |

**只用 tenacity**:整個 LLM down 30 分鐘 → worker 一直 retry 卡住,其他 worker slot 浪費。

**只用 Celery**:每個小網路抖都得完整 retry 整個 task,費 round trip。

**兩層**:小問題快速解,大問題吐回 broker。

## 2.8 Pytest + Mock

### Unit test vs Integration test

| | Unit test | Integration test |
|---|---|---|
| 範圍 | 一個 function / class | 多個 component + DB / Redis |
| 速度 | 毫秒級 | 百毫秒到秒 |
| 依賴 | 全部 mock | 真實 DB |
| 抓什麼 | 邏輯 bug | 跨組件 bug |

### Mock — 「假的物件代替真的依賴」

```python
from unittest.mock import AsyncMock, patch

with patch(
    "app.adapters.fred._fetch_series_observations",
    new=AsyncMock(return_value=[{"date": "2026-04-01", "value": "332.4"}]),
):
    events = await fred.fetch_new()

assert len(events) == 1
```

`patch` 在這段 with block 內把 `_fetch_series_observations` 換成 mock。**不真的打 FRED**,測試秒級跑完。

### `pytest-httpx` — 專門 mock HTTP

```python
def test_fetch_observations(httpx_mock):
    httpx_mock.add_response(
        url="...",
        json={"observations": [...]},
    )
    result = await _fetch_series_observations(...)
    assert ...
```

不用手寫 mock object,fixture 自動攔截 httpx call。

### `TRUNCATE TABLE ... CASCADE`

我們的 integration test 用 fixture:
```python
@pytest_asyncio.fixture
async def db_session():
    async with session_local() as session:
        await session.execute(text("TRUNCATE TABLE events CASCADE"))
        await session.commit()
        yield session
```

每個 test 前清空 events 表(CASCADE 連帶清掉 child predictions / outcomes)。

**為什麼用 TRUNCATE 不用 DELETE**:
- TRUNCATE 快(直接 reset 表,不 row-by-row 刪)
- 自動 reset sequence(autoincrement ID 重新從 1)
- CASCADE 處理 FK 關聯

副作用:**測試會洗掉 dev 環境的資料**。我們在 M9 之前忍,M9 上 production 用獨立 test DB。

## 2.9 structlog + stdlib logging 的橋

我們用 structlog 寫結構化 log,但 SQLAlchemy / Celery / httpx 用 stdlib `logging`。

不處理 → 你會看到兩種格式混雜的 log:
```
2026-05-25 [info] fred.fetch.completed inserted=11   ← structlog (彩色 + key=value)
INFO:sqlalchemy.engine:SELECT events.id, events.source...  ← stdlib (純文字)
```

### `ProcessorFormatter` 解法

```python
# logging_config.py
handler = logging.StreamHandler()
handler.setFormatter(structlog.stdlib.ProcessorFormatter(
    foreign_pre_chain=shared_processors,
    processors=[..., renderer],
))
logging.getLogger().addHandler(handler)
```

**stdlib log record 被 redirect 進 structlog 的 processor pipeline**,輸出格式統一。

## 2.10 M2 速記表

| 概念 | 一句話 |
|---|---|
| **Celery** | Python 分散式任務佇列,業界 default |
| **Celery Beat** | 獨立的排程 process,看時鐘 enqueue task |
| **Broker** | 訊息中介(Redis),producer 跟 consumer 解耦 |
| **Producer / Consumer** | 丟事 / 拿事的人 |
| **Worker** | Consumer process,從 queue 拿 task 執行 |
| **`task_acks_late`** | 跑完才 ack,crash 會 redeliver(at-least-once) |
| **At-least-once** | 訊息至少送達一次(可能多次)— 要 idempotent |
| **`prefetch_multiplier`** | worker 一次預取幾個 task,慢任務設 1 |
| **Queue routing** | 把 task 路由到不同 queue,讓不同 worker 處理 |
| **Idempotency** | 跑幾次結果都一樣 — DB unique + catch IntegrityError |
| **`asyncio.run()`** | 開新 event loop 跑 async code,Celery + async 標準橋 |
| **tenacity** | Python retry library,decorator 式 |
| **兩層 retry** | tenacity 處理瞬時抖、Celery 處理 systemic outage |
| **`crontab` expression** | minute / hour / day-of-week 5 欄位排程語法 |
| **Mock(unittest.mock)** | 假的物件代替真的依賴,單元測試必備 |
| **pytest-httpx** | mock httpx 的 fixture,不真打 HTTP |
| **TRUNCATE CASCADE** | 比 DELETE 快,連帶清 child rows |
| **structlog ProcessorFormatter** | stdlib logging 跟 structlog 共用同一條 pipeline |

---

# Part 3:Milestone 3 — Multi-source Ingestion

## 3.1 這階段在幹嘛?

M2:只有 FRED 一個 source,程式碼直接寫死。
M3:**加 SEC EDGAR + FOMC** + **小重構**讓三個 source 共用 pattern。

## 3.2 新概念清單

1. **Refactoring** — 改寫但行為不變
2. **Pure function vs side effect**
3. **Pydantic 當 data contract**
4. **Anti-Corruption Layer**
5. **Single Responsibility Principle**
6. **Shy code 哲學**
7. **`@dataclass(frozen=True)`** vs Pydantic
8. **SEC EDGAR + CIK + 8-K(金融背景)**
9. **FOMC + RSS(金融背景)**
10. **Rate limiting**(asyncio.sleep + per-ticker isolation)
11. **XML 攻擊**(XXE / billion laughs)
12. **`defusedxml`**
13. **Column-oriented JSON**(SEC API 特色)
14. **`underscore` private convention**
15. **`Event loop binding bug` — NullPool 修法**
16. **`@asynccontextmanager`**
17. **`lazy="raise"` SQLAlchemy 關聯設定**

---

## 3.3 Refactoring — 「改寫但行為不變」

### 為什麼要重寫能跑的程式?

M1 / M2 只有 FRED,一切寫死沒問題。M3 要加 SEC + FOMC,**直接複製 FRED code** 改 → 三份高度重複 code → 改一個 bug 要改三遍。

**重構** = 把共同 pattern 抽出來,行為**完全不變**,結構變更乾淨。

### 重構的鐵則:**先有測試,後重構**

最大風險是「改著改著行為跑掉了」。M2 寫的 6 個 test 是安全網 — 重構過程中 test 一直跑,任何時刻變紅就知道哪裡壞了。

> 面試講:「我在 M3 重構之前先確保 M2 test 覆蓋率夠。每改一段跑一次 test。」

## 3.4 Pure Function vs Side Effect

### Pure function = 沒副作用,只看 input → output

```python
# M3 的 FRED adapter
async def fetch_new() -> list[RawEvent]:
    observations = await get_fred()
    return [RawEvent(...) for obs in observations]
```

只回傳資料,不寫 DB、不改全域、什麼都不副作用。

### 有 side effect 的對比

```python
# M1 / M2 的舊寫法
async def fetch_cpi(db):
    observations = await get_fred()
    for obs in observations:
        db.add(Event(...))  # ← 寫 DB (副作用)
        await db.commit()   # ← 副作用
    return inserted_count
```

### Pure 的好處

**測試瞬間簡單**:
```python
# Pure version test:
events = await fetch_new()
assert len(events) == 2

# Side-effect version test:
fake_db = AsyncMock()
fake_db.add = MagicMock()
fake_db.scalar = AsyncMock(return_value=None)
fake_db.flush = AsyncMock()
fake_db.commit = AsyncMock()  # 5 行設定
result = await fetch_cpi(fake_db)
assert fake_db.add.call_count == 2
```

**可以組合**:同樣 adapter 給 Celery task、給 CLI 工具、給 backfill 腳本 — 不用拖 DB 進來。

**思考容易**:讀 pure function 你只看 input → output,**不用追「它改了哪些外部狀態」**。

這個原則叫 **referential transparency**(指涉透明性)— 同樣 input 永遠同樣 output。

## 3.5 Pydantic 當「契約」

### RawEvent — Adapter 跟 Writer 的合約

```python
class RawEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    source: EventSource
    event_type: str = Field(max_length=50)
    external_id: str = Field(max_length=255)
    title: str = Field(max_length=500)
    payload: dict[str, Any]
    affected_tickers: list[str] = Field(default_factory=list)
    published_at: datetime
```

這段宣告等於說:

> **「我」(任何 adapter)保證會給你一個物件,有這些欄位、型別正確、長度不超標。**
> **「你」(event_writer)可以放心用,不用做防禦性檢查。**

Pydantic 是「**合約執行警察**」 — adapter 違規(給少欄位、給錯型別)立刻 raise ValidationError。

### `frozen=True` — Immutable value object

```python
event = RawEvent(...)
event.title = "x"  # ← raise ValidationError!
```

**Immutable** 的好處:
- 避免遠端 mutation bug(adapter 創出來給 writer,writer 不小心改)
- 可以當 dict key / set 元素(可 hash)
- 多 thread 安全

「**Value object 該 immutable**」是 Domain-Driven Design 的核心觀念。

## 3.6 Anti-Corruption Layer

### 問題:外部世界的格式很亂

SEC API 給 column-oriented JSON;FOMC 給 RSS XML;FRED 給標準 JSON。

如果每個 adapter 直接寫進 events 表 → events 表的 ORM model 要適應**所有 source 的怪 schema**。改一個 source 牽動全部。

### 解法:Anti-Corruption Layer(ACL)

```
外部 API → adapter parses → RawEvent → writer 統一處理 → Event ORM → DB
                              ↑
                        這層 RawEvent 是 anti-corruption layer
```

外部格式只「污染」到 adapter 內部,**不會洩漏出來**。內部一律是乾淨的 RawEvent。

**好處**:
- FRED 改 API → 影響只限於 fred.py
- 加新 source → 只要寫新 adapter,writer 不動
- DB schema 跟外部 schema 解耦

## 3.7 Single Responsibility Principle(SRP)

「**一個 module 只負責一件事,變動的理由只有一個**」

| Module | 做什麼 | 改變的理由 |
|---|---|---|
| `adapters/fred.py` | 跟 FRED API 溝通 | FRED 改 API |
| `adapters/sec_edgar.py` | 跟 SEC API 溝通 | SEC 改 API |
| `services/event_writer.py` | 寫進 events 表 | DB schema 變、dedup 邏輯變 |

FRED 改不影響 SEC,DB schema 改不影響 adapter。**改一個地方影響半徑很小**。

## 3.8 Shy Code

「**每個 module 認識的東西越少越好**」

- FRED adapter 認識:FRED API、httpx、RawEvent
- FRED adapter **不**認識:DB session、其他 adapter、Celery、FastAPI

未來換 DB 從 PostgreSQL → MongoDB,**FRED adapter 不用動**(它不認識 DB)。

對比 M1 / M2 的 FRED adapter:認識 AsyncSession、Event ORM、IntegrityError、commit() — 整個世界都認識,任何改動都可能波及。

## 3.9 SEC EDGAR — 金融背景

### SEC 是什麼

**SEC(Securities and Exchange Commission)** = 美國證券交易委員會,管美股的政府機構。

**EDGAR(Electronic Data Gathering, Analysis, and Retrieval)** = SEC 線上資料庫,**所有上市公司必須在這裡 file 文件**。任何人都可以免費查。

### CIK

**Central Index Key** = SEC 給每個 filer 的**永久 ID**。

```
AAPL  → CIK 0000320193
MSFT  → CIK 0000789019
GOOGL → CIK 0001652044
```

為什麼用 CIK 不用 ticker?
- Ticker 會變(改名、合併)
- CIK 永遠不變

URL 強制 10 位數補零:`/submissions/CIK0000320193.json`

### 8-K 是什麼

SEC 規定上市公司**遇到重大事件就要 file 8-K**,4 個工作天內。

常見 item codes:
| Code | 意義 |
|---|---|
| **2.02** | Results of Operations(財報出來了)— 對股價超大 |
| **5.02** | Departure of Directors / Officers(高層走人)— 通常大 |
| **5.07** | Submission of Matters to Vote(股東會投票結果)— 通常小 |
| **1.01** | Material Definitive Agreement(簽大合約) |
| **8.01** | Other Events — 通常無關痛癢 |

### SEC 為什麼一定要 User-Agent

```
GET https://data.sec.gov/...
Headers:
  User-Agent: EventSense ppgk119@gmail.com   ← 必須含 email
```

SEC fair-access 規定:
- 不能讓你匿名濫用
- 你的 bot 跑太兇 → 他們寄 email 警告
- 還不收斂 → ban IP(直接 connection refused)

「**透明 + 監督**」的 rate limiting,跟 OpenAI 的 「API key 直接拒絕」是兩種模型。

## 3.10 FOMC + RSS

### FOMC

**Federal Open Market Committee** = 聯準會的利率決策委員會,**每年開 8 次會議,決定美元利率**。

每次會議結束發 FOMC statement(政策聲明)。**每個字都被市場 parse 到爆** — 改一個用詞可能讓 S&P 500 ±2%。

### RSS

**RSS(Really Simple Syndication)** = XML 格式,網站用來「廣播新內容」。

```xml
<rss version="2.0">
  <channel>
    <item>
      <title>Federal Reserve issues FOMC statement</title>
      <link>https://...</link>
      <pubDate>Wed, 18 Mar 2026 18:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
```

我們的 adapter:抓 XML → 找 `<item>` → 篩 title 含 "FOMC statement" → 變 RawEvent。

## 3.11 XML 安全攻擊

### XXE(XML External Entity)

```xml
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<foo>&xxe;</foo>
```

老實 parse 這段 XML → server 機密檔被讀出來。**Uber 2019 年中過**。

### Billion Laughs

```xml
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  ... 一路展開到 lol9 ...
]>
```

每層展開 10 倍 → 第 9 層 10⁹ 個 "lol" → 10 GB 記憶體 → server OOM 死(DoS)。

### `defusedxml` 防

```python
# 不安全
from xml.etree import ElementTree as ET

# 安全
from defusedxml import ElementTree as ET
```

**Drop-in replacement**,API 一樣,禁用了 entity expansion + external fetch。

我們用的真實風險低(Fed 不會打我們),但:
- ruff lint(S314)會 flag stdlib XML parser
- 養成習慣
- **面試免費加分點** — 你知道 XXE,你用了 mitigation

## 3.12 Column-oriented JSON(SEC 特色)

### SEC API 回傳

```json
{
  "filings": {
    "recent": {
      "form":           ["8-K", "10-K", "4",   "8-K"],
      "filingDate":     ["2026-05-22", "2026-05-01", ...],
      "accessionNumber":["0000320193-26-000042", ...],
      "primaryDocument":["aapl-x.htm", "10k-2026.htm", ...]
    }
  }
}
```

不是「**4 個 filing 物件的 array**」,是「**4 個 array,每個 array 的第 i 元素一起組成第 i 個 filing**」。

### 為什麼這樣設計

**省 bandwidth**:row-oriented 每筆寫一次 key name,100 個 filing 就重複 100 次。column-oriented 只寫一次。對 SEC 一天被打幾百萬次的 server 很重要。

省 50%+ JSON 大小。

### 我們的 parser

```python
forms = recent["form"]
dates = recent["filingDate"]

for i, form in enumerate(forms):  # 用 index 對應
    if form != "8-K":
        continue
    accession = recent["accessionNumber"][i]
    ...
```

類似的概念在 Parquet / Apache Arrow / ClickHouse 都是 columnar format — 大數據世界常見。

## 3.13 The Event Loop Binding Bug(NullPool 修法)

### 症狀

M3 跑起來 worker container 一直炸:
```
RuntimeError: got Future <Future pending ...> attached to a different loop
```

### 根因

asyncpg connection 跟「開它的 event loop」綁定。

- FastAPI:整個 process 一個 loop,pool 重用 connection 沒問題 ✅
- **Celery worker**:每個 task 都 `asyncio.run()` → **每次都是全新 event loop**
- Pool 把上個 loop 的 connection 拿出來給新 loop 用 → 炸

### 解法:`NullPool`

```python
@asynccontextmanager
async def transient_session():
    engine = create_async_engine(URL, poolclass=NullPool)  # ← 不 pool
    session_local = async_sessionmaker(engine)
    try:
        async with session_local() as session:
            yield session
    finally:
        await engine.dispose()  # 用完關
```

`NullPool` = 「不 pool,每次重新連線、用完關掉」。每次 task call → 新 engine → 新 connection(在當前 loop 開)→ 用完關。

**Trade-off**:
- 損失:每 task 多 ~8ms TCP handshake
- 收穫:不再有 loop binding bug

對每小時跑一次的 task,8ms 無感。

### 為什麼 FastAPI 不需要這樣?

FastAPI 長期 process,**一個 loop 服務所有 request**。Pool connection 永遠在這個 loop 用,從不跨 loop。

### `@asynccontextmanager`

Python 標準 decorator,讓你寫 generator 包 setup + teardown:

```python
@asynccontextmanager
async def transient_session():
    engine = create_engine(...)  # setup
    session = make_session()
    try:
        yield session  # ← 給使用者用
    finally:
        await engine.dispose()  # teardown,一定會跑
```

使用:
```python
async with transient_session() as db:
    await persist_events(db, events)
# 出 with block → 自動 teardown
```

## 3.14 `lazy="raise"` SQLAlchemy

```python
class Event:
    predictions: Mapped[list["Prediction"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        lazy="raise",  # ← 任何 lazy load 嘗試 → 直接 raise
    )
```

### 預設 lazy loading 的問題

```python
event = await db.scalar(select(Event).where(...))
print(event.predictions)  # ← 預設 lazy load,觸發新 query
```

但**在 async session 裡 lazy load 會炸**(它是 sync 行為)。

### `lazy="raise"`

強迫 caller 明確 `selectinload`:
```python
event = await db.scalar(
    select(Event)
    .where(...)
    .options(selectinload(Event.predictions))  # 顯式 eager load
)
print(event.predictions)  # ✅ 已經 loaded
```

忘記寫 `selectinload` → 立刻 raise `InvalidRequestError`,**bug 在 dev time 暴露**,不是 production 500。

「**Forced explicit**」是 modern Python 的設計哲學。

## 3.15 Underscore Private Convention

```python
def _fetch_series_observations(...):
def _observation_to_raw_event(...):
def _parse_recent_8ks(...):
```

Python 沒有 `private` keyword,但**約定俗成 `_` 開頭代表「module 內部用」**。

意義:
- 給 reader 的訊號:「實作細節」
- 重構這些函式不用怕破壞外部 API
- 真正的「公開介面」只有 `fetch_new()` 跟 `RawEvent`

## 3.16 M3 速記表

| 概念 | 一句話 |
|---|---|
| **Refactoring** | 行為不變,結構變好。前提是有 test 護身 |
| **Pure function** | 沒副作用,只看 input → output。測試瞬間簡單 |
| **Pydantic contract** | 用 type 強制 module 之間的資料約定 |
| **Anti-Corruption Layer** | 外部格式不污染內部 model(RawEvent vs Event) |
| **Single Responsibility** | 一個 module 只做一件事,變動半徑小 |
| **Shy code** | 每個 module 認識的東西越少越好 |
| **CIK** | SEC 給每個 filer 的永久 10 位數 ID |
| **8-K** | 上市公司重大事件 filing,4 日內必申報 |
| **FOMC statement** | Fed 利率決策聲明,市場最在乎的文件之一 |
| **RSS feed** | XML 格式的「網站新內容廣播」 |
| **XXE / Billion Laughs** | XML parser 的兩種經典攻擊;用 defusedxml 防 |
| **SEC User-Agent** | SEC 強制要 email,違規 IP block |
| **Rate limiting (sleep)** | 控制 request 頻率,別把人家打爆 |
| **Event loop binding** | asyncpg connection 綁開它的 loop,跨 loop 用就炸 |
| **NullPool** | 不 pool,每次 connect-disconnect。worker 場景的標準 |
| **`@asynccontextmanager`** | 包 async 的 setup/teardown |
| **Anonymous Docker volume gotcha** | 改 deps 後要 `--renew-anon-volumes` |
| **Column-oriented JSON** | 多個 array 對應位置組成 row,省 bandwidth |
| **Frozen Pydantic model** | Immutable value object |
| **`lazy="raise"`** | 強迫 explicit selectinload,async 安全網 |

---

# Part 4:Milestone 4 — Prices + Earnings

## 4.1 這階段在幹嘛?

M1-M3:抓「事件」(events 表)
M4:加「**股價**」資料(price_snapshots 表)— 為 M6 預測驗證鋪路

M4 後系統能力:**「事件 + 當時股價」**。M5 才能 LLM 預測,M6 才能驗證「真的漲了嗎」。

## 4.2 新概念清單

1. **Time series 資料特性**
2. **Decimal vs Float**
3. **`Numeric(precision, scale)`**
4. **Redis cache 真正用上(不只 broker)**
5. **TTL(Time To Live)**
6. **Thundering herd 問題**
7. **Cache 寫入策略**(write-through, write-aside, read-through)
8. **Time zone + DST**
9. **`zoneinfo` vs `pytz`**
10. **`INSERT ... ON CONFLICT DO NOTHING`**(PG 專屬)
11. **BigInt vs UUID PK**(高頻表設計)
12. **Pandas DataFrame**
13. **OHLCV**(金融)
14. **Ticker / ETF / SPY**(金融)
15. **EPS / earnings surprise**(金融)
16. **`auto_adjust=False`**(yfinance 細節)
17. **Scraper(yfinance)防禦策略**
18. **`@dataclass(frozen=True, slots=True)`**
19. **Write amplification**(B-tree index)
20. **Backfill script**

---

## 4.3 Time Series 資料

### Events vs Prices 本質不同

| | Events | Price snapshots |
|---|---|---|
| 每筆代表 | 一個有意義的事件 | 一個瞬間的觀察值 |
| 頻率 | 不規律 | 規律(每分鐘) |
| 每天筆數 | 5-50 | ~100,000 |
| 寫入模式 | INSERT + UPDATE(status 改) | **只 INSERT,從不 UPDATE** |
| 查詢模式 | 「最近的 events」「特定 source」 | 「AAPL 從 5/1 到 5/22 的所有價格」 |
| 屬於 | OLTP(一筆一筆) | OLAP-ish(時間範圍大量) |

兩種資料**應該不同表**:索引策略不同、寫入策略不同、容量量級不同。

### Append-only 是時間序列特性

歷史價不會回頭改(2026-05-22 收盤就是 308.82,永遠不變)。

省 `updated_at` 欄位,也讓未來 partition(按月切表)很自然。

## 4.4 Decimal vs Float — 金融軟體第一課

### Float 的問題

```python
>>> 0.1 + 0.2
0.30000000000000004      # 不是 0.3 !
```

### 為什麼?

電腦用 **IEEE 754** 規格存浮點數,**二進位表示**。

```
0.1 (十進位) = 0.000110011001100... (二進位,無限循環) → 必須截斷
```

像 1/3 = 0.3333... 永遠寫不完,**0.1 在二進位也是無限循環**。

### 累積誤差

```python
total = 0.0
for _ in range(1_000_000):
    total += 0.1
# 期望:100000.0,實際:100000.00000133288
```

對科學計算可能無所謂。**對錢死定了**。

真實災難:加拿大某交易所用 float 算指數,半年累積誤差 50 點。

### `Decimal` 解法

```python
from decimal import Decimal
>>> Decimal("0.1") + Decimal("0.2")
Decimal('0.3')          # 完美
```

直接用**十進位**存(不轉二進位),沒有截斷誤差。代價:慢 ~100 倍(對金額計算不痛)。

### Postgres `NUMERIC(12, 4)`

```python
price: Mapped[Decimal] = mapped_column(Numeric(12, 4))
```

意思:**最多 12 位數,小數點後 4 位**。
能存 `99,999,999.9999`。

> **面試必問**:「為什麼用 Numeric 不用 Float?」
> 答:「Float IEEE 754 binary 誤差累積會出包,金融計算 industry standard 是 Decimal/NUMERIC。」

## 4.5 Redis Cache 真正用上

### 什麼是 cache

「**把常被問的答案先存好,免得每次重算**」

```
不用 cache:
  /prices/AAPL/latest → SELECT FROM price_snapshots ... → 5-20ms

有 cache (Redis):
  /prices/AAPL/latest → Redis GET → 0.5ms
```

Redis 是記憶體 DB,比 PostgreSQL 快 10-100 倍。

### TTL — 「key 活多久」

```python
await redis.set("key", "value", ex=60)  # 60 秒後自動刪
```

為什麼要設?
- **沒 TTL**:cache 永遠不更新,資料永遠 stale
- **太短**(1 秒):命中率太低,跟沒 cache 一樣
- **太長**(1 小時):user 看到 1 小時前的價

我們選 60 秒:
- worker 每 5 分鐘寫 cache
- TTL 60 秒 → 最多 stale 60 秒
- worker 沒寫(market 關)→ 60 秒後 cache 過期 → 走 DB

## 4.6 Thundering Herd 問題

「**驚群效應**」/「**雷暴**」— 經典 cache 災難:

```
情境:AAPL cache TTL 過期那一秒,1000 個 user 同時打 /prices/AAPL/latest

「cache miss → 查 DB → 寫 cache」邏輯:
  request 1   → cache miss → 查 DB → 寫 cache
  request 2   → (還沒看到 cache) → 查 DB → 寫 cache
  ...
  request 1000 → 查 DB → 寫 cache

結果:DB 瞬間被 1000 個一樣的 query 轟炸
```

DB load 暴衝,可能直接掛。

### 三種解法

| 策略 | 怎麼做 | 優缺點 |
|---|---|---|
| **Write-through** | reader miss 時自己寫 cache | 簡單,但會 thundering herd |
| **Read-through + lock** | miss 時搶 Redis SETNX 鎖,只有一個查 DB | 複雜,完美防雷暴 |
| **Write-aside(我們選的)** | 只有 worker 寫 cache,reader 純讀 | 簡單;代價是 cache 過期後 reader 走 DB |

### 我們的 Write-aside

```
Worker(每 5 分鐘):抓新價 → 寫 DB + 寫 cache(60s TTL)

Reader(web request):
  → 看 cache
     有 → 回
     沒有 → 查 DB → 回 (不寫 cache!)
```

**Reader 不寫 cache** → 1000 個 reader 同時 miss → 1000 次 DB 讀(不寫 cache)→ DB 讀很便宜,撐得住。

## 4.7 Time Zone + DST 陷阱

### 美股市場時間

```
紐約證交所:9:30 AM – 4:00 PM Eastern Time
週一到週五
```

但 **Eastern Time 自己會變**:
- 冬:EST(Eastern Standard Time)= UTC-5
- 夏:EDT(Eastern Daylight Time)= UTC-4

切換時間(美國):
- 3 月第 2 個禮拜天:跳 1 小時前進
- 11 月第 1 個禮拜天:跳 1 小時後退

這就是 **DST(Daylight Saving Time / 日光節約時間)**。

### 寫死 offset 的陷阱

```python
# 錯誤
ET_OFFSET = -5  # UTC-5
def is_market_open(utc_now):
    et_now = utc_now + timedelta(hours=ET_OFFSET)
    return 9 <= et_now.hour < 16
```

夏天就錯了(美東其實是 UTC-4,差 1 小時)。

### 正確:`zoneinfo`(Python 3.9+ stdlib)

```python
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
et_now = utc_now.astimezone(EASTERN)
```

`ZoneInfo("America/New_York")` 會:
1. 讀 OS 的 IANA tz database
2. 知道每個歷史 DST 切換時點
3. 自動套用正確 offset

### 為什麼**不**用 `pytz`?

`pytz` 是 Python 3.9 前的方案,API 醜:
```python
import pytz
ny = pytz.timezone("America/New_York")
naive_dt = datetime(...)
correct = ny.localize(naive_dt)  # 一定要用 localize
```

`zoneinfo`:
```python
correct = datetime(..., tzinfo=ZoneInfo("America/New_York"))
```

**新專案直接用 `zoneinfo`**。

### Cron 的 DST 問題

Beat 用 cron 表達式:
```python
crontab(hour=14, minute=30)  # 每天 UTC 14:30
```

- 夏天:UTC 14:30 = 美東 10:30(晚開盤 1 小時抓)
- 冬天:UTC 14:30 = 美東 9:30(剛好開盤)

我們的解法:**Beat 一直 fire,task 內部 check `is_market_open()`**:

```python
def fetch_prices_task():
    if not is_market_open():
        return  # 早 return
    ...
```

代價:24/7 都 fire 一次,但 off-hours 立刻 return,實質成本 0。

**比起寫 timezone-aware cron 簡單多了**。

## 4.8 `INSERT ... ON CONFLICT DO NOTHING`

### M3 的 per-row catch IntegrityError

```python
for raw_event in raw_events:
    db.add(event)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        continue
```

每筆都是一次 round trip。2000 筆 = 2000 round trips × 5ms = **10 秒**。

### Postgres native bulk upsert

```sql
INSERT INTO price_snapshots (ticker, snapshot_at, price, source)
VALUES (...), (...), (...) ... (2000 rows)
ON CONFLICT (ticker, snapshot_at, source) DO NOTHING;
```

意思:**整批 INSERT,撞 unique constraint 跳過**。

**1 次 round trip,150ms 搞定。67 倍快**。

### SQLAlchemy 寫法

```python
from sqlalchemy.dialects.postgresql import insert as pg_insert

stmt = pg_insert(PriceSnapshot).values(rows).on_conflict_do_nothing(
    constraint="uq_price_snapshots_dedup",
)
await db.execute(stmt)
```

注意 `from sqlalchemy.dialects.postgresql` — 這是 **PG 專屬 dialect**。MySQL 是 `INSERT IGNORE`,語法不同。

### 什麼時候用哪個?

- **低頻 events(<100/run)**:per-row catch IntegrityError(M3 寫法)— 更易讀
- **高頻 prices(>1000/batch)**:ON CONFLICT(M4 寫法)— 效能差太多

## 4.9 BigInt vs UUID PK

### 我們的選擇

```
events:          UUID PK
price_snapshots: BigInt PK
```

為什麼不同?

### UUID 優點(events 受惠)

- 16 bytes,全球唯一
- 不洩漏業務資訊(看到 `e834ca00-...` 不知道是第幾筆)
- 適合分散式(多 region 寫不撞)
- API URL 用 UUID 比 `?id=42` 安全

### UUID 缺點(prices 受不了)

- **16 bytes vs BigInt 8 bytes**:price 一年 ~3000 萬筆 → index 大 240MB
- **隨機分布** → B-tree index 寫入位置散亂 → **write amplification**
- **Cache 不友善**:每次寫觸碰不同 page

### BigInt sequential 好處

- 8 bytes
- 永遠遞增 → 寫入永遠在 B-tree 最右側 → 同一個 page,cache hot

### 結論

**根據 volume + access pattern 選 PK**,沒有「永遠用 X」的答案。

對 portfolio 專案,**講得出這個 trade-off 比實際省的空間更值錢**。

### Write Amplification 是什麼

B-tree index 結構:每次 insert 找對的位置塞,可能要 split page、rebalance。

- Sequential PK(1, 2, 3, ...):永遠塞最右側,單一 page 一直寫 → 高效
- Random PK(UUID):每次塞不同 page → 多 page 都要寫 → 磁碟 I/O 放大

**Write amplification** = 「實際磁碟寫入量 / 邏輯資料量」。Sequential PK ≈ 1x,UUID 可能 3-5x。

## 4.10 Pandas DataFrame

yfinance 回傳的是 **pandas DataFrame** — Python 的「Excel 表格」:

```
                     Open    High     Low    Close    Volume
Date
2026-05-22 09:30   180.50  180.85  180.30  180.65  1234567
2026-05-22 09:31   180.65  180.92  180.55  180.80  2345678
```

特性:
- Column names(`Open`, `Close`)
- Index(這裡是時間 timestamp)
- 雙軸,類似 spreadsheet
- 向量化操作很快(`df["Close"].mean()`)

### OHLCV — 金融基本

每分鐘股價 5 個維度:
- **O**pen — 這分鐘第一筆交易價
- **H**igh — 這分鐘最高
- **L**ow — 這分鐘最低
- **C**lose — 這分鐘最後一筆 ← **最常用**
- **V**olume — 這分鐘交易張數

我們只存 Close,因為:
- 「那個瞬間的市場共識價」
- 預測驗證算 +1h/+24h/+7d 後的價格,用 Close 一致
- 存 5 個欄位 DB 大 5 倍

### `Decimal(str(float_val))` 小技巧

```python
close = Decimal(str(row["Close"])).quantize(Decimal("0.0001"))
```

直接 `Decimal(float_val)` 會把 float 的 binary 誤差也帶進來。
先轉 str(`"180.65"`)再轉 Decimal,得到**字面值**。

## 4.11 `auto_adjust=False`

### 股票分割(Stock Split)

公司可以「**把一股拆成 N 股**」吸引散戶。

```
NVDA 2024-06-10 做 10-for-1 split:
  前:每股 $1200
  後:每股 $120,但你原本 1 股變 10 股
總價值不變,但 chart 上看會有「股價瞬間跌 90%」假象
```

### yfinance 預設「自動調整」

```python
df = yf.Ticker("NVDA").history(period="1y")
# 預設 auto_adjust=True
# 會回填:把 split 之前所有歷史價除以 10
```

對畫圖方便。但對**我們**有問題:

```
2024-03-15 (split 之前):
  auto_adjust=True 給的:   $120  ← 已經回算
  那一天 LLM 看到的真實價:   $1200
```

我們要餵給 LLM「**事件當天的真實市場價**」,所以 `auto_adjust=False`:

```python
df = yf.Ticker(ticker).history(
    period="1y",
    auto_adjust=False,  # ← 顯式關掉
)
```

### 為什麼難察覺

- 預設值不跳警告
- 大部分股票一年沒 split,不會發現
- 直到某天 query 出「2024-03-15 NVDA = $120」想「奇怪不是 1200 嗎」才查

寫 code 時加 comment 解釋,避免 reviewer 改掉。

## 4.12 Scraper 防禦策略(yfinance)

### yfinance 是什麼

**不是**官方 Yahoo Finance API。Yahoo 沒開放公開 API。

yfinance 是有人寫的 lib,**模擬瀏覽器爬 Yahoo Finance 網頁**。

風險:
- Yahoo 改 API 隨時掛
- 沒 SLA
- 沒 throttling 公告(打太快被擋)
- exception 不文件化(會丟 RuntimeError / KeyError / AttributeError 看心情)

### 四層防禦

**第 1 層:adapter 內 broad except**
```python
try:
    df = yf.Ticker(ticker).history(...)
except Exception as exc:
    log.warning("prices.yfinance.failed", error=str(exc))
    return []
```

`except Exception` 一般是 anti-pattern,對 scraper 是務實選擇。ruff `BLE001` 會 flag,要 `# noqa: BLE001` 加註解。

**第 2 層:row 級 try**
```python
for ts, row in df.iterrows():
    try:
        close = Decimal(str(row["Close"]))
    except Exception:
        continue  # 壞 row 跳過,別影響整批
```

**第 3 層:Celery at-least-once** — task 整個失敗,下個 schedule cycle 自動 retry

**第 4 層:idempotency** — unique constraint + ON CONFLICT,重試不會重複

四層加起來,yfinance 各種「神祕掛掉」都降級到 no-op,不會 cascade failure。

## 4.13 `@dataclass(frozen=True, slots=True)`

```python
@dataclass(frozen=True, slots=True)
class PriceTick:
    ticker: str
    snapshot_at: datetime
    price: Decimal
```

### `dataclass`

Python 3.7+ decorator,自動產生 `__init__` / `__repr__` / `__eq__`:
```python
PriceTick(ticker="AAPL", price=Decimal("180.5"), snapshot_at=...)
```

省 boilerplate。

### `frozen=True`

「不能改」(immutable):
```python
tick.price = Decimal("999")  # ← raise FrozenInstanceError
```

跟 Pydantic `frozen` 概念一樣。Value object 應該 immutable。

### `slots=True`

預設每個 object 有 `__dict__`(占 ~200 bytes)。`slots=True` 取消 `__dict__`,用 C-level slot:
- 每個 instance 從 ~280 bytes → ~80 bytes
- Backfill 一次 2200 個物件,差 ~400KB

### 為什麼 PriceTick 用 dataclass,不用 Pydantic?

- **Pydantic** 強在「邊界 validation」 — 外部資料進來、API response 出去
- **dataclass** 強在「內部資料流」 — 同 module 內傳遞,不需要 validation

PriceTick:
- adapter 內部產生 → writer 寫 DB
- 不穿越 API 邊界
- 不接受外部 user input

→ 不需要 Pydantic validation overhead

Pydantic v2 雖然已經很快(每物件 ~50µs),2000 物件累計 100ms。dataclass = 0.1ms。

**邊界用 Pydantic,內部用 dataclass**。

## 4.14 股市基本術語

### Ticker(股票代號)
- AAPL = Apple
- TSLA = Tesla
- NVDA = NVIDIA

### ETF(Exchange-Traded Fund)
「一籃子股票打包成單一商品」。
- **SPY** = SPDR S&P 500 ETF,追蹤標普 500
- **QQQ** = 追蹤 Nasdaq-100(科技股為主)

### 為什麼一定要 SPY

M6 算 **excess return**(超額報酬)需要它當基準:
```
AAPL 8-K 後 24h:
  AAPL 漲 2%
  SPY 同期漲 1.5%
  excess return = 2% - 1.5% = 0.5%
```

沒 SPY 不知道「漲是因為 event 還是大盤本來就在漲」。

### EPS(Earnings Per Share)

「**每股盈餘**」 — 公司一季賺的錢除以總股數。

```
NVDA Q1 2026:
  EPS = $1.87
```

### EPS Estimate vs Actual

財報前:華爾街分析師「猜的 EPS」(estimate)。
財報後:**真的**多少(actual)。

```
NVDA Q1 2026:
  Estimate: $1.77
  Actual:   $1.87  → "earnings beat" → 通常漲
```

### Surprise %

```
surprise % = (actual - estimate) / estimate × 100%
NVDA: (1.87 - 1.77) / 1.77 ≈ +5.6%
```

## 4.15 M4 速記表

| 概念 | 一句話 |
|---|---|
| **Time series 資料** | 規律取樣的觀察值,append-only |
| **Decimal vs Float** | 金融計算永遠 Decimal,float 有 binary 誤差 |
| **`Numeric(12, 4)`** | Postgres 對應型別,精度有上限保證 |
| **Cache TTL** | key 活多久,過期消失 |
| **Thundering herd** | cache 過期那瞬間 N 個 request 同時 miss 打 DB |
| **Write-aside cache** | 只有 worker 寫,reader 純讀,防雷暴 |
| **`zoneinfo`** | Python 3.9+ 時區庫,自動處理 DST |
| **IANA tz database** | 全球時區規則庫,OS 內建 |
| **DST(日光節約)** | 美東一年切換兩次,寫死 offset 必錯 |
| **BigInt vs UUID PK** | high-volume 表用 BigInt 省 index 空間 |
| **`ON CONFLICT DO NOTHING`** | PG-native 批次 upsert,快 67 倍 |
| **Pandas DataFrame** | Python 的「Excel 表」資料結構 |
| **OHLCV** | Open/High/Low/Close/Volume 五維度 |
| **`auto_adjust=False`** | 不要回填 split/dividend 調整,保留歷史真實價 |
| **Scraper(yfinance)** | 爬網頁的非官方 lib,要 broad except 防禦 |
| **Ticker / ETF** | 股票代號 / 一籃子股票打包 |
| **SPY** | 追蹤標普 500 的 ETF,用來算 excess return |
| **EPS / surprise %** | 每股盈餘 / 實際打敗預期多少 |
| **`@dataclass(frozen=True, slots=True)`** | 輕量 immutable 物件,hot path 用 |
| **Write amplification** | 隨機 UUID PK 寫入 B-tree 散亂,效率差 |

---

# Part 5:Milestone 5 — LLM Analysis

## 5.1 這階段在幹嘛?

M1-M4:抓事件 + 抓股價
M5:**讓 AI 預測「事件對股價的影響」** — 系統從「data pipeline」進化成「AI app」

## 5.2 新概念清單

1. **LLM API 基本**(tokens, prompt, completion)
2. **Token pricing**(input vs output)
3. **Structured output**(function calling / tool use)
4. **`instructor` library**
5. **`Literal` vs `Enum`** 給 LLM schema
6. **Prompt engineering 基本**
7. **Versioned prompts**(prompt as code)
8. **LLM hallucinations + 多層防護**
9. **Daily cost cap + downgrade pattern**
10. **State machine in DB**(進階)
11. **Queue table pattern**
12. **`SELECT ... FOR UPDATE SKIP LOCKED`**
13. **Transaction scope vs lock scope**(race bug)
14. **Per-event transaction(fine-grained lock)**
15. **N+1 query + `selectinload`**
16. **`CASCADE` delete**
17. **`ondelete=CASCADE` vs cascade="all, delete-orphan"**

---

## 5.3 LLM API 基本

### 你跟 ChatGPT 聊天 vs 程式打 API

**瀏覽器版**:
```
你輸入「明天股市會漲嗎」→ ChatGPT 回字串
```

**API 版**:
```python
response = openai.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "..."}],
)
print(response.choices[0].message.content)
```

差別:
- 瀏覽器版有人類介面
- API 版**純 JSON 進、純 JSON 出**

OpenAI API 本質就是 HTTP endpoint:
```
POST https://api.openai.com/v1/chat/completions
Headers: Authorization: Bearer sk-...
```

所有 LLM 服務(OpenAI / Anthropic / Google / 開源)都長這樣。

### Tokens

**Token** = LLM 內部把文字切的最小單位。**不**是字也**不**是字母。

```
"Hello world" → 2 tokens
"明天股市會漲嗎" → 8-10 tokens (中文每字常 2-3 tokens)
"supercalifragilistic..." → 10 tokens (長字會切)
```

粗略換算:**英文 1 token ≈ 0.75 字 / 中文 1 token ≈ 1-2 字**。

### 為什麼這麼重要

**OpenAI 按 token 收錢**:

```
gpt-4o-mini:
  Input (你給的字):  $0.15 / 1M tokens
  Output (LLM 回的):  $0.60 / 1M tokens
```

我們一個 event analysis:
- prompt ≈ 700 tokens(input)
- response ≈ 70 tokens(output)
- cost = (700 × 0.15 + 70 × 0.60) / 1,000,000 = **$0.00015**

20 個 events ≈ $0.003。比一杯咖啡便宜。

### 為什麼 output 比 input 貴

- Input:LLM **平行讀**整個 context,GPU 一次處理
- Output:LLM **一個一個 token 吐**,每生成 1 token 都要把整個 context + 已生成的字再跑一次(自迴歸)

所以 output 計算量是 input 的 N 倍(N = output 長度)。價格反映。

**結論**:控制 output 長度就是控制成本。我們 prompt 強調「一句話 reasoning」就是這個。

## 5.4 Structured Output

### 問題:叫 LLM 「請回 JSON」會發生什麼

```python
prompt = "Analyze this event and return JSON with: summary, ticker, direction"
response = await llm.chat(prompt)
# response 可能是:
#   '{"summary": "x", ...}'                     ← 好
#   '```json\n{...}\n```'                       ← 包了 markdown
#   '{"direction": "UP"}'                       ← 你要 BULLISH 它給 UP
#   '{"summary": "x" "ticker": "AAPL"}'         ← 漏個逗號
#   "Sure! Here is my analysis: ..."            ← 又開始講人話
```

你要寫一堆**防禦性 parsing** — 50 行垃圾 code。

### OpenAI / Anthropic 解法:Function Calling / Tool Use

近年 LLM 都支援「**結構化輸出**」 — 你給 JSON schema,LLM **強制按 schema 生成**。

底層機制(粗略):
- OpenAI 在生成每個 token 時,根據 schema **限制可以生成哪些 token**
- 生成到 `"direction": "` 時,只允許下個 token 是 `BULLISH` / `BEARISH` / `NEUTRAL`
- 不可能生成 `UP` 或 `MOON`

### `instructor` library 包好

手動用 OpenAI structured output 還要寫一堆設定。`instructor` 包好:

```python
import instructor
from openai import AsyncOpenAI

client = instructor.from_openai(AsyncOpenAI(api_key=...))

result: EventAnalysis = await client.chat.completions.create(
    model="gpt-4o-mini",
    response_model=EventAnalysis,    # ← 你的 Pydantic class
    messages=[{"role": "user", "content": prompt}],
    max_retries=2,                    # 失敗自動重問
)

print(result.impacts[0].direction)   # "BULLISH" (有 type)
```

**從 50 行手刻變 3 行**。

### `Literal` vs `Enum` 給 LLM

```python
class TickerImpact(BaseModel):
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]  # ← 不是 Enum
```

差別:
- `Literal["BULLISH", ...]` → JSON schema `{"type": "string", "enum": ["BULLISH", ...]}`
- `Enum` → 也能轉,但多一層 reference,某些 LLM 處理不夠好

**對 LLM 越「直接、扁平」越好懂**。

DB 那邊還是用 Python `StrEnum`(PG ENUM type 對應需要),LLM 這邊用 `Literal`。**LLM schema 跟 DB schema 不一定要同一個 Python class**。

## 5.5 Prompt Engineering

### 我們的 v1 prompt 結構

```
You are EventSense, an analyst that forecasts...

EVENT (verbatim from the source):
{event_json}

WATCHLIST (only these tickers are eligible):
{watchlist_csv}

TASK
1. Write a one-line summary...
2. For each watchlist ticker likely to move BECAUSE OF THIS SPECIFIC EVENT...

GUIDELINES
- Be skeptical. Most events affect 0-2 tickers.
- Never invent tickers outside the watchlist.
```

每段有用意:

### Role priming
```
You are EventSense, an analyst that...
```
告訴 LLM「你是誰、做什麼」。研究顯示比直接給指令效果好。

### 直接餵 raw JSON
```
EVENT (verbatim):
{event_json}
```
**不**自己摘要。理由:
- LLM 看 raw JSON 比看你的摘要準
- 你的摘要可能丟掉 LLM 需要的細節

### 限制可選值
```
WATCHLIST: AAPL, MSFT, ...
```
明確告訴 LLM「就這些」。

### 「不包含也是合法」
```
If no plausible impact, DO NOT include. Empty list is fine.
```

**這超重要**。不講的話 LLM 會塞滿每個 ticker。

### 給域知識
```
A macro event (CPI, FOMC) usually moves SPY/QQQ broadly...
An 8-K for company X primarily affects X...
```

把「**做這個任務需要的常識**」寫進 prompt,LLM 不用自己 hallucinate。

### 明確負面指令
```
Never invent tickers outside the watchlist.
```

LLM 還是會偶爾 hallucinate(我們程式擋一層),但 prompt 講清楚會減少。

## 5.6 Versioned Prompts

### 為什麼要 versioning

情境:
```
Week 1: prompt v1,100 events,80% 準
Week 3: 改 prompt
Week 4: 200 events,75% 準

問題:準確率下降是因為...
  A. 新 prompt 變差?
  B. 那週市場特別難?
  C. 抓的 event 類型不同?
```

**沒 versioning 永遠回答不了**(新舊混在一起)。

### 我們的做法

```python
PROMPT_VERSION = "v1"
# 寫進每個 prediction:
Prediction(prompt_version="v1", ...)
```

之後改 prompt:
1. 寫新檔 `event_analysis_v2.txt`
2. bump `PROMPT_VERSION = "v2"`
3. 新預測自動標 v2
4. 舊預測還是 v1

查:
```sql
SELECT prompt_version, AVG(aligned::int) AS accuracy
FROM predictions JOIN outcomes ...
GROUP BY prompt_version;
```

→ **量化「v2 是不是真的比 v1 好」**。

### 軟體工程 vs ML 工程

這 pattern 叫 **prompt as code** — 把 prompt 當版本控制的 artifact,不是手調的 magic string。

對應:
- Git 對 code
- DB migration 對 schema
- **Prompt version 對 prompt**

成熟 LLM 應用都這樣做。

## 5.7 LLM Hallucinations + 多層防護

### 什麼是 hallucination

LLM 「**自信地說錯東西**」。不是 bug,是 LLM 本質 — 它預測「下一個最像對的字」,有時 plausible-looking 但實際不存在。

我們場景:
- watchlist `[AAPL, MSFT, GOOGL]`,LLM 回 `ticker: "TSLA"` 不在 list
- 編造 reasoning「Apple 跟 Tesla 合作」(其實沒)
- 給 confidence 0.99,但根本不確定

### 三層防護

**第 1 層:Schema enforcement(instructor)**
```python
direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
```
LLM 不可能回 `"MAYBE_UP"` — 編譯器層級擋掉。

**第 2 層:Pydantic validation**
```python
confidence: float = Field(ge=0.0, le=1.0)
```
回 `confidence: 1.5` → ValidationError → instructor 自動 retry。

**第 3 層:Application-level filter**
```python
if impact.ticker not in get_settings().watchlist:
    logger.warning("analyzer.hallucinated_ticker", ticker=impact.ticker)
    continue  # 丟掉
```

LLM 給 `ticker: "HALUC"` → silently drop + log。

### 為什麼三層都要

每層擋不同類型:
- Layer 1:不在 enum 的值
- Layer 2:型別 / 範圍錯
- Layer 3:值本身合法但**業務上錯**(ticker 是合法 string,但不在 watchlist)

**沒有一層能 catch all。defense in depth 是 LLM 工程常識**。

## 5.8 Daily Cost Cap + Downgrade

### 真實災難

2023 年有團隊把 GPT-4 串到 Discord bot,某 user 開 script 一直 spam,**一個下午燒 $30,000**。

LLM 沒有 builtin 防護 — 給 API key,它就無限收錢。

### 我們的兩層

**第 1 層:單次成本控制(prompt design)**
```python
reasoning: str = Field(max_length=500)
```
+ prompt 寫「one sentence」→ 單次 output ~70 tokens(vs 沒限制 ~500)。

**第 2 層:每日總額**
```python
def choose_model(source, event_type, today_spend):
    if today_spend >= LLM_DAILY_COST_CAP_USD:  # $1
        return default_model  # ← 降級到便宜
    elif is_high_stakes(source, event_type):
        return premium_model
    else:
        return default_model
```

### Downgrade 不是 hard stop

```
Hard stop:超過 → analyzer 完全停 → 系統看起來壞
Downgrade:超過 → 全部用 mini → 還能預測,marginal 準確率降
```

**「降級服務 > 完全停服」**是 production 系統黃金原則。

### UTC midnight 是 day boundary

```python
start_of_day = datetime.now(UTC).replace(hour=0, minute=0, ...)
```

不用 local time,因為:
- SF server 在 SF 凌晨 reset
- Tokyo server 在 Tokyo 凌晨 reset
- 兩台對「今天」定義不同,metric 對不起來

**UTC 是 single source of truth**,所有 backend metric 用 UTC,顯示給人看再轉本地。

## 5.9 State Machine in DB(進階)

### Events.status 的演進

```
                      LLM call fails
                  ┌─────────────────┐
                  │                 │
                  ▼                 │
  [FETCHED] ────────[Analyzer]───────► [ANALYZED]
                       │                
                       │ LLM call fails 
                       ▼                
                  [FAILED] (有 failure_reason)
                       │                
                       │ operator 手動 fix
                       ▼                
                  [IGNORED]
```

每個狀態:
- `FETCHED`:抓回來,還沒 LLM 分析
- `ANALYZED`:有預測,可以給 user 看
- `FAILED`:出問題,operator 查
- `IGNORED`:operator 決定不處理

### DB-driven 的優勢

**狀態存 stable storage(DB),不存 broker / memory**:

- Worker crash:重啟看 DB 知道從哪繼續
- Broker 重啟:DB 仍是 truth
- 系統重啟:任何時候從 DB 重新 recompute 都對

業界趨勢的 **reliable workflow**(Temporal、Restate、Step Functions)都是這個思想。

## 5.10 Queue Table Pattern

### 什麼意思

我們 `events` 表有 `status` 欄位。Analyzer 找 `WHERE status='FETCHED'`。

**events 表 + status 欄位 = 一個 queue**:
- Producer:fetcher 寫 status=FETCHED
- Consumer:analyzer 撈 status=FETCHED → 處理 → 改 status
- FIFO:`ORDER BY published_at ASC`
- 多 consumer 平行搶:用 FOR UPDATE SKIP LOCKED

### DB queue vs message broker

| | DB queue | Message broker |
|---|---|---|
| 基礎設施 | 已有的 PG | 多裝一套 |
| 效能上限 | 1k tasks/s | 100k+ tasks/s |
| task + state 原子性 | ✅ 同一 transaction | ❌ 兩個系統 |
| 適用規模 | 小到中(<10k/小時) | 中到大 |

對 EventSense(<100 events/小時)→ DB queue 完勝。

不適用:event 量到每秒幾千個 → 換 Redis Streams / Kafka。

## 5.11 `FOR UPDATE SKIP LOCKED`

### 什麼是 `FOR UPDATE`

SQL 標準的「**row-level 寫鎖**」:

```sql
BEGIN;
SELECT * FROM events WHERE status='FETCHED' FOR UPDATE;
-- 這些 rows 被鎖,其他 transaction 想 UPDATE 或 SELECT FOR UPDATE 會等
...
COMMIT;  -- 釋放所有 lock
```

### `SKIP LOCKED`

進階變形:「**已被別人鎖的 rows 直接跳過,不要等**」

```sql
-- Task A
SELECT * FROM events WHERE status='FETCHED' LIMIT 20 FOR UPDATE SKIP LOCKED;
→ 拿 events [1..20],鎖住

-- Task B (毫秒級晚)
SELECT * FROM events WHERE status='FETCHED' LIMIT 20 FOR UPDATE SKIP LOCKED;
→ 看到 [1..20] 已鎖,SKIP
→ 在剩下的 events 找 → 沒有 → 回空 list
```

這就是 **queue table pattern 核心** — 多 worker 安全搶任務。

## 5.12 Race Condition Bug 深度故事(M5 之星)

### 症狀

20 個 FETCHED events → 跑 analyzer → DB 結果:**58 個 predictions**(有些 event 出現 4 次)

### 根因 — 圖解

```
Timeline:
00:00.000  Worker concurrency=2, Beat 也 fire,兩個 task 同時跑

00:00.001  Task A: SELECT * FROM events WHERE status='FETCHED' LIMIT 20
                  → 拿 events [1..20]

00:00.002  Task B: SELECT * FROM events WHERE status='FETCHED' LIMIT 20
                  → 拿 events [1..20]  ← 一樣!

00:00.003  Task A: for each event: call LLM, write prediction, UPDATE status

00:00.004  Task B: for each event (一樣的 20 個): 重複 call LLM, 重複寫 prediction
```

**兩 task 並行各自 SELECT → 一樣資料 → 各自寫 prediction**。

### 第一次嘗試:加 FOR UPDATE SKIP LOCKED

我加 `with_for_update(skip_locked=True)`,結果**還是有 duplicate**。

### 為什麼第一次嘗試失敗

**Row-level lock 跟 transaction scope 綁定**。我們 code:

```python
async def analyze_pending(db):
    events = SELECT ... FOR UPDATE SKIP LOCKED LIMIT 20   # 鎖 [1..20]

    for event in events:
        call LLM
        write prediction
        event.status = ANALYZED
        await db.commit()  # ← 這裡 COMMIT 釋放整個 transaction 的所有 lock!
        # 此時 events 2-20 的 lock 已經沒了
```

時序:
```
Task A: SELECT FOR UPDATE → lock [1..20]
Task A: process event 1, COMMIT → 釋放 lock [1..20] (整批!)
Task B: 此時 SELECT FOR UPDATE → 看到 [2..20] 沒鎖 → lock [2..20]
Task A: 繼續處理 event 2 → 跟 Task B 撞
```

**「COMMIT 釋放整個 transaction 的所有 lock」是 SQL 標準行為**,我忘了。

### 真正修法 — Per-event transaction

每個 event 開**自己的獨立 transaction**:

```python
async def analyze_pending(outer_db):
    candidate_ids = SELECT id FROM events WHERE status='FETCHED' LIMIT 20

    for event_id in candidate_ids:
        async with transient_session() as task_db:   # ← 全新 transaction
            event = task_db.SELECT * FROM events 
                     WHERE id = event_id AND status='FETCHED'
                     FOR UPDATE SKIP LOCKED
            if event is None:
                continue   # 別人搶走了
            
            call LLM
            write prediction
            event.status = ANALYZED
            await task_db.commit()  # 只釋放這個 transaction 的 lock(一個 row)
```

新時序:
```
Task A: candidate_ids = [1..20]
Task B: candidate_ids = [1..20]

Task A: 開 transaction A1, SELECT id=1 FOR UPDATE → lock event 1
Task B: 開 transaction B1, SELECT id=1 FOR UPDATE → SKIP → 回 None → continue
Task B: 開 transaction B2, SELECT id=2 FOR UPDATE → lock event 2 ✅
Task A: process event 1, COMMIT A1 → 釋放 lock 1 (event 1 已 ANALYZED)
Task A: 開 transaction A2, SELECT id=2 → SKIP (B2 在鎖) → None → continue
Task A: 開 transaction A3, SELECT id=3 FOR UPDATE → lock event 3 ✅
...
```

**完美併發**。

### 教訓

1. **row lock 跟 transaction scope 綁定**
2. **要 fine-grained lock 就要 fine-grained transaction**
3. **分散式併發要實際 test** — 單機想破頭也想不到

> 面試講:「我先做了 X,結果發現 Y,所以改成 Z」是 senior 工程師語氣。

## 5.13 N+1 Query + `selectinload`

### N+1 是什麼

```python
events = await db.scalars(select(Event).limit(20))
for event in events:
    print(event.predictions)  # ← 每次存取觸發新 query
```

預設 lazy load:
- 1 個 query 拿 20 個 events
- 20 個 query 拿每個 event 的 predictions
- **總共 21 queries**

對 200 個 events:201 queries。**這就是 N+1**。

### 解法:`selectinload`

```python
event = await db.scalar(
    select(Event)
    .where(Event.id == id)
    .options(selectinload(Event.predictions))
)
```

執行:
```sql
SELECT * FROM events WHERE id = ?;
SELECT * FROM predictions WHERE event_id IN (?);  ← 一次拿光
```

**2 個 query,不管多少筆**。**1+1 而非 N+1**。

### M8 的三層 selectinload chain

```python
.options(selectinload(Event.predictions).selectinload(Prediction.outcomes))
```

執行:
```sql
SELECT * FROM events WHERE ...;
SELECT * FROM predictions WHERE event_id IN (?);
SELECT * FROM outcomes WHERE prediction_id IN (?, ?, ...);
```

**3 個 query**,不管 events / predictions / outcomes 各多少。

## 5.14 CASCADE Delete

```python
event_id: Mapped[uuid.UUID] = mapped_column(
    UUID,
    ForeignKey("events.id", ondelete="CASCADE"),
)
```

`ondelete="CASCADE"` = 刪 parent event → **自動刪 child predictions**。

不加 CASCADE:
```python
await db.delete(some_event)
# → ForeignKeyViolation: predictions 還引用,不能刪
# 要先手動 delete predictions,再 delete event
```

加 CASCADE → DB 自動把 child rows 收拾乾淨。

### 什麼時候**不**該用 CASCADE?

Child 是「歷史紀錄」性質 — parent 刪了 child 仍要保留作 audit log。

例:刪 user account 之後,他的 order 不該消失(會計問題)。

我們的 prediction:parent 沒了沒意義,CASCADE 對。

## 5.15 M5 速記表

| 概念 | 一句話 |
|---|---|
| **LLM API** | HTTP endpoint,給 prompt 拿 response |
| **Token** | LLM 看的最小單位,按 token 收錢 |
| **Output > Input pricing** | output 一個一個吐,計算量大 N 倍 |
| **Structured output** | LLM 給 JSON schema,強制按格式生成 |
| **`instructor`** | 把 SDK 包成「給 Pydantic class 拿 instance」,自動 retry |
| **`Literal` 給 LLM** | 比 `Enum` 直接,LLM 處理更乾淨 |
| **Prompt engineering** | 不是隨便寫 — role priming / raw data / 白名單 / 域知識 / 負面指令 |
| **Versioned prompt** | `PROMPT_VERSION="v1"` 寫進 DB,讓 v1 vs v2 可量化比較 |
| **Daily cost cap** | LLM 沒 builtin 防呆,沒設 cap bug 一發生會破產 |
| **Downgrade > stop** | 超過 budget 用便宜 model,不要整個停服務 |
| **UTC midnight** | 跨 region 部署的 day boundary 唯一解 |
| **Hallucination** | LLM 自信說錯 — 三層 schema / validation / business filter |
| **State machine in DB** | 任務狀態存 DB,worker crash 重啟仍知道從哪繼續 |
| **Queue table pattern** | DB 表 + status 欄位 + FOR UPDATE SKIP LOCKED = 輕量 queue |
| **`FOR UPDATE`** | row-level lock,其他 transaction 要等 |
| **`SKIP LOCKED`** | 看到鎖住的 row 跳過 |
| **Lock = Transaction scope** | commit 釋放全部 lock,不能 cherry-pick |
| **Per-event transaction** | 每 task 一個 session,讓 lock scope = task scope |
| **N+1 query** | for-loop 裡存取 ORM 關聯,每次觸發 query |
| **`selectinload`** | eager loading,1+1 query 取代 N+1 |
| **`lazy="raise"`** | async 安全網,忘記 selectinload 立刻炸 |
| **CASCADE delete** | 刪 parent 自動刪 child rows |

---

# Part 6:Milestone 6 — Validation Loop

## 6.1 這階段在幹嘛?

M5:LLM 預測寫進 DB,**但沒人知道準不準**
M6:**真實價格驗證** → 算 excess return → 判定 aligned → **閉環完成**

從「會說話的黑箱」變成「**自己知道自己準確率的系統**」。

## 6.2 新概念清單

1. **Closed loop / ground truth** — ML 系統 vs demo 的分界
2. **Alpha / Excess Return** — 金融關鍵概念
3. **Benchmark(SPY)** — 為什麼一定要它
4. **三個時間窗(1h / 24h / 7d)為什麼**
5. **ETA scheduling vs polling** — 設計選擇
6. **Recoverable state** 概念
7. **Tolerance windows** — 處理稀疏資料
8. **`must_be_after` invariant bug** — 測試的價值
9. **NEUTRAL threshold philosophy**
10. **API design:`alignment_rate=None` vs 0.0**
11. **Postgres bool → int → float cast 限制**
12. **`NOT EXISTS` anti-join 寫法**

---

## 6.3 Closed Loop / Ground Truth — ML 系統的價值所在

### M1-M5 的世界

```
事件 → 預測 → 結束
       ↑
   「我說的對嗎?不知道,反正寫進 DB」
```

### M6 加進的「閉環」

```
事件 → 預測 → 真實結果 → 比對 → 量化「準確率」這個事實
                              │
                              ▼
                          accuracy 變成新的 ground truth
```

業界術語:**ground truth** = 「真實答案」。我們抓真實價格變化當 ground truth,跟 LLM 預測比對。

這個 pattern 在 ML 通用:
- 推薦系統 → user 真的點了嗎?
- 翻譯模型 → 人類校稿覺得品質如何?
- 詐欺偵測 → 真的是詐欺嗎(事後查證)?

**沒閉環的 ML 系統就是會說話的黑箱**。

## 6.4 Alpha / Excess Return

### 「漲了 2%」這句話有意義嗎?

```
情境 A:大盤 +1.5%,AAPL +2% → AAPL 多漲 0.5% → LLM 真有點本事
情境 B:大盤 -3%, AAPL +2% → AAPL 多漲 5% → LLM 超神
情境 C:大盤 +5%, AAPL +2% → AAPL 跑輸 3% → LLM 預測「漲」其實**錯**了!
```

「AAPL 漲了」不代表 LLM 對。要看「比大盤多漲還是少漲」。

### Alpha — 金融老祖宗詞

```
alpha = 你的回報 − 市場平均回報

你 +3%, 市場 +1% → alpha = +2%(贏大盤)
你 +5%, 市場 +6% → alpha = -1%(輸大盤,雖然絕對賺)
你 -1%, 市場 -3% → alpha = +2%(損失少於大盤 — 算贏)
```

**任何傻瓜把錢丟進 SPY 都能拿到「市場回報」**。你的「真本事」是能不能贏過 SPY。

### 我們怎麼算

```python
ticker_return = (price_after_24h - price_at_prediction) / price_at_prediction
spy_return    = (spy_after_24h - spy_at_prediction) / spy_at_prediction

excess_return = ticker_return - spy_return    # ← 這就是 alpha
```

`prediction_outcomes.excess_return` 欄位就是 alpha。

### 為什麼 SPY 而不是 QQQ?

- **SPY** = SPDR S&P 500,代表「整個美股」最準
- **QQQ** = Nasdaq-100,科技股偏多
- 我們 watchlist 7/9 是科技股 — 用 QQQ 當基準會「自己跟自己比」(高相關性,alpha 永遠很小)
- 用 SPY 才能看出「科技股**相對全市場**的超額表現」

## 6.5 三個時間窗為什麼?

每個 prediction 排 **三個** outcome:**+1h、+24h、+7d**

```
1h:  量「即時市場反應」
     例如 8-K 出來瞬間,自動交易演算法反應
     → 看 LLM 抓不抓得到短線 signal

24h: 量「隔夜消化後」
     市場消化新聞、analyst 寫 report、機構買賣
     → 看 LLM 抓不抓得到主流共識
     
7d:  量「結構性影響」
     基本面真的變化?還是反應只是噪音?
     → 看 LLM 抓不抓得到 fundamental shift
```

不同 LLM(不同 prompt 版本)可能在不同 horizon 表現不同。**有資料才能優化**。

## 6.6 ETA Scheduling vs Polling

### 兩種「未來執行任務」做法

**A. ETA Scheduling(到時候叫我)**:
```python
analyze_outcome.apply_async(eta=predicted_at + timedelta(hours=24), args=[id])
```
Celery 把 task 存進 broker。

像鬧鐘 — 設好,到時候響。

**B. Polling(每分鐘自己看)**:
```python
def validate_pending_task():
    candidates = SELECT predictions WHERE predicted_at + window <= now() AND no outcome yet
    for c in candidates:
        compute_outcome(c)
```

像清掃機器人 — 定期巡邏,看到該做的就做。

### 我們選 B,為什麼?

| | ETA(A) | Polling(B) |
|---|---|---|
| **broker 重啟** | ETA tasks 可能丟失 | 沒影響(狀態在 DB) |
| **worker 升級** | 升級中累積的可能丟 | 沒影響 |
| **rename task** | 舊 ETA 找不到 task 名 fail | 沒影響 |
| **延遲** | 精準 | worst case 5 min |
| **回頭補做** | 不行(time machine?) | 一行 SQL 就能補 |

對 outcome validation,**5 分鐘延遲完全無所謂**(outcome 本來就 ≥1h 後才能算)。

換來「**永遠 recoverable**」 — 系統任何部分掛了重啟,從 DB 就能 recompute 所有狀態。

### 「Recoverable」的具體意思

```
昨晚 10pm:你誤改 docker-compose,worker 全部停 6 小時
早上 4am:重啟系統

ETA 版:6 小時內到期的 outcome task 全丟失。
        手動寫 script 補做(query 缺失的 outcome,手動 enqueue)。

Polling 版:重啟後 5 分鐘內 Beat 觸發,validator 看 DB 發現
          「有 outcome 應該算但還沒算」→ 自動補。
          你連碰都不用碰。
```

這是 **DB-driven state machine** 的核心優勢。

## 6.7 Tolerance Windows — 處理稀疏資料

### 問題:時間序列資料是稀疏的

你以為:**每分鐘都有一筆價格**
實際:
```
週一 9:30-16:00:每分鐘一筆 ✅
週一 16:00-週二 9:30:沒資料(盤後)
週六 + 週日:完全沒
感恩節 / 聖誕節:沒有
歷史:只有每日收盤(1-min 限 5 天)
yfinance 抽風:某小時的資料突然缺
```

**現實世界的 timestamp 不是連續的**。

### 我們的 tolerance 設計

```python
_PRICE_LOOKBACK_TOLERANCE = {
    OutcomeWindow.H1:  timedelta(hours=1),     # 短線:1 小時內必須有
    OutcomeWindow.H24: timedelta(hours=24),    # 中線:24 小時內任何資料
    OutcomeWindow.D7:  timedelta(days=4),      # 長線:4 天內(跨週末 OK)
}
```

查詢:
```
找 ticker 在 target_time 之前最近的一筆,
但不能比 target_time - tolerance 還舊
```

### 「Defer」是合法狀態 — 不要寫假資料

```python
if 找不到價格:
    return None    # ← defer,不寫 outcome
```

**錯**:沒資料寫 0% return / hardcoded "MISSING" — 假資料污染 dataset
**對**:什麼都不寫,下次 schedule 再 retry

下次 retry:
- price fetcher 補上資料 → 算 → 寫 outcome
- 沒補上 → 繼續 defer

**Idempotent 設計**:重試永遠安全(unique constraint 兜底)。

## 6.8 `must_be_after` Bug — 測試的價值

### Bug 出現

第一版 `_price_at_or_before`:
```python
async def _price_at_or_before(ticker, target_at, tolerance):
    earliest = target_at - tolerance
    return await db.scalar(
        select(PriceSnapshot.price)
        .where(snapshot_at <= target_at, snapshot_at >= earliest)
        .order_by(snapshot_at.desc()).limit(1)
    )
```

看起來合理。

### 我寫 test 故意創造「只有 baseline 沒有 end」

```python
predicted_at = 25h ago
seed_price("AAPL", predicted_at, "100")     # 只有 baseline
# 沒有 24h 後的價格
```

**預期**:validator 應該 defer。**實際**:validator 寫出了 outcome,ticker_return = 0%。

### 追 SQL 邏輯

24h 窗:
```
target_at = predicted_at + 24h = (now - 25h) + 24h = now - 1h
tolerance = 24h
earliest = target_at - tolerance = 25 小時前 = predicted_at

SELECT price WHERE snapshot_at <= target_at AND snapshot_at >= earliest
```

我們 seeded 的 baseline 在 `predicted_at`,正好 = `earliest`,**在範圍內**。SQL 返回 baseline 那筆當「end」。

於是:`ticker_return = (100 - 100) / 100 = 0%` — 看起來合理但**完全錯**。

### 修法

```python
async def _price_at_or_before(
    ticker, target_at, tolerance,
    *, must_be_after: datetime | None = None,
):
    stmt = (
        select(PriceSnapshot.price)
        .where(snapshot_at <= target_at, snapshot_at >= earliest)
        .order_by(snapshot_at.desc()).limit(1)
    )
    if must_be_after is not None:
        stmt = stmt.where(snapshot_at > must_be_after)  # ← end-price 才用
    return await db.scalar(stmt)

# Caller:
baseline = await _price_at_or_before(ticker, predicted_at, tolerance)        # 不限
end      = await _price_at_or_before(ticker, target_at, tolerance,
                                     must_be_after=predicted_at)             # 必須在 predicted_at 之後
```

### 教訓

1. **「正確」邊界條件不直觀**:`<= target` + `>= earliest` 都沒錯,合起來把 baseline 抓進去
2. **Silent fake data 比 hard fail 可怕** — 不會炸,但污染 accuracy 統計
3. **測試的價值在於想到「壞情境」** — happy path 永遠抓不到

## 6.9 NEUTRAL Threshold 哲學

### 問題:NEUTRAL 怎麼判對?

LLM 三種預測:BULLISH / BEARISH / **NEUTRAL**

BULLISH / BEARISH 看 excess 正負就好。NEUTRAL 呢?
- excess = +0.1% → 漲一點點,算「沒大事」嗎?
- excess = +0.4% → 漲一些,算嗎?
- excess = +2% → 明顯漲,NEUTRAL 顯然錯

### Spec 答案:0.5%

```python
NEUTRAL_THRESHOLD = 0.005   # 0.5%

if direction == NEUTRAL:
    aligned = abs(excess) < NEUTRAL_THRESHOLD
```

意思:|excess| < 0.5% 才算 NEUTRAL 對。

### 為什麼選 0.5%?

不是科學決定,**design choice**:

- **S&P 500 日均波動**: ~0.7%
- < 0.5% = 比平均波動還小 → 確實沒大事
- > 0.5% = 大於平均 → 有事情,NEUTRAL 預測錯

換句話說:**0.5% 是「我可以說『沒事』的最大波動」**。

### 邊界:`<` 不是 `<=`

剛好 0.5% 算「邊緣大事」,保守不給 aligned。

Test 有 cover:
```python
def test_not_aligned_at_exactly_threshold():
    assert is_aligned(NEUTRAL, NEUTRAL_THRESHOLD) is False
```

### 為什麼 threshold 寫成 module constant?

```python
NEUTRAL_THRESHOLD = 0.005    # top of file
```

不要 hardcode magic number。寫成 constant:
- 一處改全部改
- 名字本身解釋意義
- 可以被 import 進 test
- 之後想 vol-adjust(高波動股票放寬)只改一個地方

## 6.10 API 設計 — `alignment_rate=None` vs 0.0

### 沒 outcome 資料時 endpoint 回什麼?

```python
GET /accuracy?ticker=NOTHING

# Option A: 回 0
{"total_outcomes": 0, "aligned_count": 0, "alignment_rate": 0.0}

# Option B: 回 None
{"total_outcomes": 0, "aligned_count": 0, "alignment_rate": null}
```

### 為什麼選 B

**A 騙人**:
- Frontend 看 `alignment_rate: 0` → 顯示「0% accurate」
- User 以為「這個 ticker 我們預測全錯」
- 實際是「沒資料」

**B 誠實**:
- `null` 強迫前端處理「沒資料」case
- 顯示「N/A」或「Not enough data yet」
- 不誤導 user

### API 設計通則

> **「沒資料」≠「全錯」**
> **回 null / 404 比回「中性值」誠實**

類似:
- 平均分 `(a+b+c)/n`,n=0 別回 0,回 None
- 投票結果 0:0:0 別說「平局」,說「無人投票」

## 6.11 Postgres bool → int → float

### 想算「aligned 的比率」

```python
func.sum(cast(PredictionOutcome.aligned, Float))  # 我第一次嘗試
```

爆 `cannot cast type boolean to double precision`。

### 為什麼

PG cast 規則:
- `bool → int`:✅(true → 1, false → 0)
- `int → float`:✅
- **`bool → float`:❌**(沒寫這條 cast)

### 修法

```python
func.sum(cast(PredictionOutcome.aligned, Integer))   # 先到 int
# Python 算 alignment_rate = aligned_sum / total
```

或用 `CASE WHEN`(更 portable):
```sql
SUM(CASE WHEN aligned THEN 1 ELSE 0 END)
```

### 教訓

**SQLAlchemy 抽象在 DB-specific limitation 上不是無漏洞**:
- 90% SQL 跨 DB 跑
- 10% 要小心 — cast 規則、function name、window function 語法,各 DB 不同

## 6.12 `NOT EXISTS` Anti-join

### 問題:「找出有 X 但沒對應 Y 的 row」

「prediction 過了 24h 但還沒有 24h outcome」

### 直覺寫法(LEFT JOIN)

```sql
SELECT p.*
FROM predictions p
LEFT JOIN prediction_outcomes po
  ON po.prediction_id = p.id AND po.window = '24h'
WHERE po.id IS NULL  -- 沒有對應的 outcome
  AND p.predicted_at <= NOW() - INTERVAL '24h 15m'
```

OK 但 verbose。

### `NOT EXISTS`(我們的)

```python
no_outcome_yet = ~exists().where(
    and_(
        PredictionOutcome.prediction_id == Prediction.id,
        PredictionOutcome.window == window,
    )
)

stmt = select(Prediction).where(
    Prediction.predicted_at <= cutoff,
    no_outcome_yet,
)
```

對應 SQL:
```sql
SELECT * FROM predictions p
WHERE p.predicted_at <= ?
  AND NOT EXISTS (
    SELECT 1 FROM prediction_outcomes po
    WHERE po.prediction_id = p.id AND po.window = ?
  )
```

### 為什麼 NOT EXISTS 比 LEFT JOIN IS NULL 好?

- **語義更直接** — 「沒有匹配 row」這意圖直接寫出來
- **效能通常更好** — DB 看到 `EXISTS` 會用 semi-join,LEFT JOIN 可能多做工
- **不 SELECT 子查詢欄位** — `EXISTS` 只看存在不存在

### 通用 anti-join pattern

「A 表的 row 在 B 表沒有對應」三種寫法:
1. `LEFT JOIN B ... WHERE B.id IS NULL` — 經典
2. `NOT EXISTS (SELECT 1 FROM B WHERE ...)` — 我們的
3. `NOT IN (SELECT id FROM B)` — **小心 NULL 陷阱**(NOT IN 含 NULL 永遠 false)

實務上 2 最安全。

## 6.13 M6 速記表

| 概念 | 一句話 |
|---|---|
| **Closed loop / 閉環** | 預測 → 真實 → 比對 → 量化準確率。ML 系統跟 demo 的分界 |
| **Ground truth** | 真實答案,跟模型輸出比對的對象 |
| **Alpha / Excess return** | 你的回報 - 大盤回報。真實能力的量測 |
| **Benchmark (SPY)** | 「整個美股」的代理,所有 alpha 都對它算 |
| **3 個時間窗** | 量「即時 / 隔夜 / 結構性」三種反應 |
| **ETA scheduling** | 「到時候叫我」,broker 存 task |
| **Polling** | 「每分鐘自己看」,DB 存狀態 |
| **Recoverable state** | 重啟系統能 recompute → DB 是 source of truth |
| **Tolerance window** | 接受多舊的 price snapshot 當「end price」 |
| **Defer ≠ Fail** | 沒資料就什麼都不寫,下次再試 |
| **`must_be_after`** | end-price 必須嚴格在 predicted_at 之後 |
| **NEUTRAL threshold** | |excess| < 0.5% 才算 NEUTRAL 對齊 |
| **`alignment_rate=None`** | 沒資料 ≠ 全錯,要區分 |
| **PG `bool → int → float`** | bool 不能直接 cast 到 float |
| **`NOT EXISTS` anti-join** | 「A 沒有對應 B」的乾淨寫法 |

---

# Part 7:Milestone 7 — Frontend Sprint 1

## 7.1 這階段在幹嘛?

M1-M6:純後端,只有 API + Swagger UI
M7:**第一個真正的 web UI** — 可以打開瀏覽器看 timeline 跟 event 細節

## 7.2 新概念清單

1. **Frontend vs Backend 分工**
2. **SPA(Single Page App)**
3. **React** — 核心心智模型
4. **JSX / TSX** — HTML 在 JS 裡
5. **Component**
6. **Next.js** — React + production essentials
7. **App Router**
8. **Server Component vs Client Component**
9. **`"use client"` directive**
10. **TypeScript value**
11. **Tailwind CSS utility-first**
12. **TanStack Query** — server state
13. **`staleTime` cache 策略**
14. **`useState(() => ...)` lazy init**
15. **CORS** — 跨來源安全
16. **`NEXT_PUBLIC_` env prefix**
17. **Hot reload / dev server**
18. **Async params(Next.js 16 breaking change)**

---

## 7.3 React 核心心智

### 沒 React 前

```javascript
// jQuery 時代
$("#events-list").empty();
events.forEach(event => {
    $("#events-list").append(`<li>${event.title}</li>`);
});
$("#total").text(events.length);
```

問題:
- 「畫面長什麼樣」散在各地(追每個 jQuery `$(...)`)
- 改一個地方常忘記更新另一個
- 100 個元件互相 setter/getter,bug 滿天飛

### React 的核心想法

**「畫面是 state 的純函數」**

```jsx
function EventList({ events }) {
    return (
        <div>
            <p>Total: {events.length}</p>
            <ul>{events.map(e => <li key={e.id}>{e.title}</li>)}</ul>
        </div>
    );
}
```

意思:
- 你**不操作 DOM**
- 你「**宣告**」 — 給定 events,畫面長這樣
- React 自動 diff,只更新真正變動的 DOM

`events` 一變,React 重 render 整個 function,內部 diff 後**只更新真實變動的部分**。

### TSX / JSX — 「HTML 寫在 JavaScript」

```tsx
<div className="text-lg">
    <h1>EventSense</h1>
    <p>Count: {count}</p>
</div>
```

不是字串,是 **JS expression**。JSX 是 JS 語法擴展。
- `className` 不是 `class`(`class` 是 JS reserved)
- `{count}` 大括號裡可以放任何 JS expression
- 被 Babel/TypeScript compiler 轉成 `React.createElement(...)`

TSX = TypeScript 版 JSX。

### Component

```tsx
function EventCard({ event }: { event: EventRead }) {
    return <div>...</div>;
}

<EventCard event={someEvent} />
```

**接 props、回 JSX 的 function**。寫一次,到處用。

UI 拆小片,組合成複雜畫面 — **React 心智核心**。

## 7.4 Next.js — React + Production Essentials

### React 解決 / 不解決什麼

React 解決「**怎麼描述 UI**」。React **不**解決:
- 路由(`/events`、`/dashboard` 怎麼運作?)
- Server-side rendering(SEO)
- Build 設定(webpack、bundling、code splitting)
- 圖片優化、字型載入、cache 策略

Next.js 全包了。

### App Router — 「資料夾就是路由」

```
frontend/app/
├── page.tsx              → /
├── layout.tsx            → 共用 layout
├── dashboard/
│   └── page.tsx          → /dashboard
└── events/
    └── [id]/
        ├── page.tsx      → /events/<some-id>
        └── client.tsx    → (內部使用)
```

「**檔案路徑直接決定 URL**」 — 不用 `app.get('/events/:id', handler)`。

`[id]` 中括號 = 動態參數,真實值放 `params.id`。

## 7.5 Server Component vs Client Component

**這是 Next.js App Router 最容易心智混亂的設計**。理解了就懂現代 React。

### 兩種 component

| | Server | Client (`"use client"`) |
|---|---|---|
| 在哪跑 | 伺服器 | 瀏覽器 |
| Bundle 大小 | 0 KB | 有 JS bundle |
| 互動性(onClick / state) | 不行 | 可以 |
| 初始載入速度 | 快(直接 HTML) | 要等 JS 下載 + 執行 |
| SEO | 好 | 較差 |
| Hooks(useState 等) | ❌ | ✅ |
| `await fetch` 直接 | ✅ | ❌(用 useEffect 或 TanStack Query) |

### 理想做法

**最外層 Server,需要互動的內層拆 Client**。

我們的 `/events/[id]`:
```
page.tsx (Server)
  ↓
  await params.id (Next.js 16 強制 async)
  ↓
  render <EventDetailClient id={id}/>
  
client.tsx ("use client")
  ↓
  useQuery 抓資料
  render UI、處理 hover / click
```

Server 層**沒 JS bundle**,只負責 URL 解析。Client 層才真正互動 → bundle 最小化。

### `"use client"` directive

```tsx
"use client";  // ← 檔案第一行

import { useQuery } from "@tanstack/react-query";
```

這一行**整個檔案變 client component**。import 進來的東西也自動進 client bundle。

**為什麼明確標記?** 預設 server(省 bundle),需要互動才升級 client。

## 7.6 TypeScript 的價值

### 沒 TypeScript

```javascript
function add(a, b) { return a + b; }

add("5", "10");    // "510" ← 字串串接,炸過很多 bug
add(5);            // NaN
```

### 有 TypeScript

```typescript
function add(a: number, b: number): number {
    return a + b;
}

add("5", "10");    // ❌ Compile error
add(5);            // ❌ Missing argument
```

**Compile time 抓錯**,不是 runtime。

### 對我們特別有用

```typescript
// frontend/lib/types.ts(mirror 後端 Pydantic)
export interface EventRead {
    id: string;
    source: "FRED" | "SEC_EDGAR" | "FOMC" | "EARNINGS";
    title: string;
}

// 用:
const event: EventRead = await api.getEvent(id);
event.titel  // ❌ Did you mean 'title'?
```

改 backend 欄位名,frontend 不更新會立刻紅線。

## 7.7 Tailwind CSS Utility-First

### 傳統 CSS

```css
.event-card { border: 1px solid; padding: 16px; ... }
```
```html
<div class="event-card">...</div>
```

### Tailwind

```tsx
<div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm hover:border-slate-300">
```

每個 class 一個原子樣式:
- `rounded-lg` = `border-radius: 0.5rem`
- `p-4` = `padding: 1rem`
- `hover:border-slate-300` = hover 時的 border

### 為什麼這樣寫?

爭議大,但 Tailwind 贏了(2020 後新專案 60%+ 用)。

1. **不用想 class 名字**(不用「我這個按鈕該叫 btn-primary 還是 button-cta」)
2. **不用切檔案**(HTML 跟 styling 同一個地方)
3. **沒有 cascade 災難**(改 A 頁 CSS 不會壞 B 頁)
4. **Bundle 小**(只 ship 用到的 utility)

## 7.8 TanStack Query — Server State 不是 Client State

### 兩種 state

```
Client State:                        Server State:
  「dark mode 還是 light mode?」        「最新 events 是哪些?」
  「modal 開著還是關著?」              「accuracy 多少?」
  → useState 處理                     → 要 fetch、cache、loading/error
```

### useState 寫 server state 的痛

```tsx
function EventList() {
    const [events, setEvents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        setLoading(true);
        fetch('/api/v1/events')
            .then(r => r.json())
            .then(data => { setEvents(data.data); setLoading(false); })
            .catch(err => { setError(err); setLoading(false); });
    }, []);

    if (loading) return <Skeleton />;
    if (error) return <Error error={error} />;
    return <List items={events} />;
}
```

每個元件這樣寫 + 沒 cache + 沒 retry + 沒 dedup...

### TanStack Query 一行

```tsx
const { data, isLoading, error } = useQuery({
    queryKey: ['events'],
    queryFn: () => api.listEvents(),
});
```

自動:
- Loading state
- Error state
- Cache(同 queryKey 共用)
- Deduplication
- Refetch on focus / interval / mutation
- Optimistic updates

### `staleTime`

```tsx
new QueryClient({
    defaultOptions: {
        queries: { staleTime: 30_000 }  // 30 秒
    }
})
```

意思:**cache 30 秒內,即使 component 重 mount 也不重 fetch**。

- `staleTime: 0`(預設):每次 mount 都 refetch — 浪費
- `staleTime: 30s`:30 秒內看 cache,超過再背景 refetch
- `staleTime: Infinity`:永不過期

### `useState(() => new QueryClient())` lazy init

```tsx
// ❌ 錯誤
const [client] = useState(new QueryClient());
// 每次 render 都新建,雖然 useState 只用第一次,
// 但「執行 new QueryClient()」每次都跑

// ✅ 正確
const [client] = useState(() => new QueryClient());
// () => 延遲到實際需要時(第一次 render)
```

「**Lazy initializer**」是 useState 特色,對昂貴初值很重要。

## 7.9 CORS — 跨來源安全限制

### 為什麼有 CORS?

沒 CORS 的世界:
```
你在 evil.com 看貓影片
evil.com 偷偷:
  fetch("https://yourbank.com/api/transfer", { amount: 1000000 })
  ↓
  瀏覽器:打給 yourbank.com
  yourbank.com:cookie 有,已登入,轉帳完成
```

你還在看貓,錢沒了。**CSRF(Cross-Site Request Forgery)**。

### CORS 解決方法

**Same-Origin Policy**:預設,網頁 JS **不能呼叫不同 origin 的 API**。

但很多正當需求要跨 origin(frontend on Vercel 打 backend on Railway,不同 domain)。

**CORS** = 「**伺服器明確說『歡迎這幾個 origin 來打我』**」

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # 只開放這個
    allow_credentials=True,
)
```

瀏覽器發 request 前先 OPTIONS preflight 問:
> "你接受來自 localhost:3000 的 GET 嗎?"

backend 回:
> "接受 (`Access-Control-Allow-Origin: http://localhost:3000`)"

瀏覽器確認後才真的發 request。

### 為什麼不用 `*`?

```python
allow_origins=["*"]  # 任何 origin 都能來
```

問題:
- 任何網站都能從 user 瀏覽器調我們 API
- 配 `allow_credentials=True` 時瀏覽器規範**直接拒絕**

Spec §16 禁止 `*` in production。dev 開始就守紀律。

## 7.10 `NEXT_PUBLIC_` Env Var

```bash
# .env.local
DATABASE_URL=...                    # 只有 server 看得到
NEXT_PUBLIC_API_URL=http://...      # ship 進 browser bundle
```

**`NEXT_PUBLIC_` 前綴 = 會被打包進 JS bundle 給瀏覽器**。

```typescript
// browser 用得到:
process.env.NEXT_PUBLIC_API_URL  // ✅

// browser 看不到:
process.env.DATABASE_URL          // undefined (編譯時剔除)
```

**規則設計很好** — secret 預設安全,要 ship 必須明確宣告。

## 7.11 Async Params(Next.js 16 Breaking Change)

```tsx
// Next 14/15 (舊):
export default function Page({ params }: { params: { id: string } }) {
    return <h1>{params.id}</h1>;
}

// Next 16 (新):
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
    const { id } = await params;
    return <h1>{id}</h1>;
}
```

`params` 變 Promise — Next.js 為了配合 React Server Component streaming 渲染。

短期煩,長期對。

## 7.12 M7 速記表

| 概念 | 一句話 |
|---|---|
| **Frontend vs Backend** | 瀏覽器 vs 伺服器,用 HTTP API 連 |
| **SPA** | Single Page App,前後端分離,JS 自己 render |
| **React** | 「畫面是 state 的函數」,自動 diff DOM |
| **TSX / JSX** | HTML 寫在 JS 裡,被 compile 成 createElement |
| **Component** | 接 props、回 JSX 的 function,UI 拆小片 |
| **Next.js** | React + 路由 + SSR + build + 1000 個 production essentials |
| **App Router** | 資料夾路徑 = URL |
| **Server Component** | 跑在伺服器,沒 JS bundle,不能用 hook |
| **Client Component** | 跑在瀏覽器,有 JS bundle,可以用 hook |
| **`"use client"`** | 標記檔案為 client component |
| **TypeScript** | JS 加型別,compile time 抓 bug |
| **Tailwind utility class** | atomic style,verbose 但快 |
| **TanStack Query** | server state 專用 lib,自動 cache / loading / retry |
| **`staleTime`** | cache 多久不重 fetch |
| **CORS** | 瀏覽器同源政策的白名單機制 |
| **`NEXT_PUBLIC_` prefix** | env var ship 進 browser bundle 的明確標記 |
| **Async params** | Next.js 16 強制 params 是 Promise |

---

# Part 8:Milestone 8 — Frontend Sprint 2 + CI

## 8.1 這階段在幹嘛?

M7:Timeline + event detail,基本能看
M8:**加圖表 + dashboard + GitHub Actions CI** — production-ready 程度

## 8.2 新概念清單

1. **Recharts** — chart library
2. **Rebased index** — 金融 chart 標準畫法
3. **Daily resample** — 處理混合解析度
4. **三層 selectinload chain**
5. **`ASGITransport`** — 測 async FastAPI 的現代方式
6. **Dependency override**(swap DI in test)
7. **Test coverage**(line coverage 真意)
8. **CI / Continuous Integration**
9. **GitHub Actions**
10. **YAML workflow 結構**
11. **Path filters**
12. **Service container in CI**
13. **CI gate**(coverage `--cov-fail-under`)
14. **`--cov-fail-under` 設多少合適**
15. **CI vs CD**

---

## 8.3 Recharts + Chart 設計

### Recharts 是什麼

React 的 chart library,基於 SVG。寫法:

```tsx
<LineChart data={data}>
    <XAxis dataKey="ts" />
    <YAxis />
    <Line dataKey="value" stroke="#000" />
</LineChart>
```

宣告式,跟 React 心智一致。

### Rebased Index — 金融標準

真實:
```
NVDA: $150 → $143.5  (-4.3%)
SPY:  $500 → $502.5  (+0.5%)
```

直接 plot 絕對值:
```
500 ━━━━━━━━━━━━━━━━━━━━━━ (SPY,一條平線)
150 ━━━━━━━━━━━━━━━━━━━━━━ (NVDA,看不出變化)
```

兩條 scale 差 3 倍,**NVDA 的 4% 跌幅在這 scale 下看不出來**。

Rebase 到 100:
```
NVDA: 100 → 95.7
SPY:  100 → 100.5

兩條共用 Y 軸:
  100.5 ━━━━━━━━━━━━━━━━ SPY
  100   ━━━━━━━━━━━━━━━━ 
   95.7 ━━━━━━━━━━━━━━━━ NVDA  ← 一眼看出 NVDA 跑輸大盤
```

**業界術語**:performance comparison chart / relative strength chart。Bloomberg 標配。

### Daily Resample 的故事

資料兩種粒度:
- 歷史 daily backfill:1 點/天
- 最近 5 天 intraday:1 點/分鐘

直接 plot 全部 → 1237 個點塞進一張圖,鋸齒亂跳。

修法 — `resampleDaily`:
```typescript
function resampleDaily(points) {
    const byDay = new Map();
    for (const p of points) {
        const day = p.snapshot_at.slice(0, 10);  // YYYY-MM-DD
        byDay.set(day, p);  // overwriting → 每天保留最後一筆
    }
    return Array.from(byDay.values());
}
```

**Group by 日期,每天只留一個 point**。8-day window 變 8 個點,乾淨。

**教訓**:**混合解析度時間序列要先 resample 到統一頻率**才能比較。

## 8.4 三層 selectinload chain

```python
.options(selectinload(Event.predictions).selectinload(Prediction.outcomes))
```

執行:
```sql
SELECT * FROM events WHERE id = ?;
SELECT * FROM predictions WHERE event_id IN (?);
SELECT * FROM outcomes WHERE prediction_id IN (?, ?, ?, ...);
```

**3 個 query**,不管 events / predictions / outcomes 各多少。

**1+1+1** 而非 **N+M**。

## 8.5 `ASGITransport` — 測 async FastAPI

### TestClient 的問題

```python
from fastapi.testclient import TestClient

with TestClient(app) as client:
    response = client.get("/api/v1/events")
```

寫起來像同步 HTTP client,**但底層**:
- 啟動一個 **thread + 新 event loop**
- 把 sync call 翻成 async

問題:**新 event loop 跟 FastAPI app 的 module-level engine 不同 loop** → asyncpg loop binding 撞 → 跟 M3/M5 同 bug。

### ASGITransport — 現代答案

```python
async def test():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/events")
```

差別:
- `httpx.AsyncClient` 是 async
- `ASGITransport` 直接走 ASGI interface,**不走真實 socket**
- 跟 test 同 loop → 不撞

**為什麼這樣比較對**:
- production 是 ASGI(uvicorn) + async
- 測試用 ASGITransport = 跟 prod 同 code path
- TestClient 走 thread + sync-wrap,**測的不是真實行為**

### Dependency Override

```python
app.dependency_overrides[get_db] = _test_db
```

FastAPI DI 強在:**測試時無痛 swap**。
- production:`get_db` 給 pooled session
- test:給 NullPool transient session

測試完不用復原 — pytest 結束 process 就好。

## 8.6 Test Coverage — 80% 不是「測試 80% 程式」

### Coverage 量什麼?

```python
def divide(a, b):
    if b == 0:
        return None
    return a / b
```

Test:
```python
def test_divide_normal():
    assert divide(10, 2) == 5
```

Coverage 100% line coverage?
**不對** — `if b == 0: return None` 那行 `return None` 沒執行(b=2)。

兩個維度:
- **Line coverage**:多少 % 行被執行
- **Branch coverage**:多少 % 分支(if true/false)被走

我們 pytest-cov 預設 line coverage。80% = **跑到 80% 程式行**。

### Coverage 高 ≠ 沒 bug

```python
def withdraw(account, amount):
    account.balance -= amount  # 100% covered

def test_withdraw():
    acct = Account(balance=100)
    withdraw(acct, 50)
    assert acct.balance == 50
```

Line coverage 100%。但沒測「超過 balance」:
```python
withdraw(acct_balance_50, 1000)
# balance = -950 (透支!沒測到)
```

**Coverage 只證明「程式碼被執行過」,不證明「行為對」**。

### Coverage 還是有用

- **回歸防止器**:有人刪 module,coverage 掉 → CI 紅 → PR 不 merge
- **找盲點**:report 顯示「app/llm/clients.py 51% covered」→ 知道這 module 還沒測夠
- **基線管理**:不允許新 PR 把 coverage 拉低

### 「為什麼 75% 不 90%?」

過頭追求反效果:
```python
def test_user_init():
    u = User(name="x")
    assert u.name == "x"  # 測 setter,沒意義
```

寫垃圾測試把 % 拉到 95% — 沒抓任何 bug,浪費。

**Sweet spot 約 75-85%**。我們 80% 設 75% gate,留 5% buffer。

## 8.7 CI/CD = 「每次 push 自動跑」

### 沒 CI 的世界

```
A 寫完,本地跑 test 過,push,merge
B pull,本地跑 test,紅???
debug 兩小時 → A 忘 push 一個 file
A:「我這邊好的啊」  ← 程式界最古老的笑話
```

### CI(Continuous Integration)

**每次 push,自動在乾淨環境跑所有檢查**:

```
A push to GitHub
       ↓
GitHub Actions 啟動 ubuntu VM
       ↓
從 0:checkout → install deps → lint → mypy → pytest
       ↓
全綠才允許 merge / 自動部署
```

「**CI 是 ground truth**」。

### 我們的 backend-ci.yml 解讀

```yaml
on:
  push: { branches: [main], paths: ['backend/**'] }
  pull_request: { paths: ['backend/**'] }
```
觸發條件:push to main / PR,只有 backend 改動才跑。改 README 不會 trigger。

```yaml
services:
  postgres:
    image: postgres:16-alpine
    options: --health-cmd "pg_isready -U eventsense" ...
```
**Service container**:GitHub 幫我們起 Postgres。`--health-cmd` 確認 PG ready 才往下跑。

```yaml
steps:
  - uses: actions/checkout@v4
  - uses: astral-sh/setup-uv@v3
  - run: uv sync --frozen
  - run: uv run ruff check .
  - run: uv run ruff format --check .
  - run: uv run mypy app/
  - run: uv run alembic upgrade head
  - run: uv run pytest --cov --cov-fail-under=75
```

串連檢查,任何一步紅就整個 fail。

### Path Filters

```yaml
paths:
  - "backend/**"
  - ".github/workflows/backend-ci.yml"
```

只有改 backend 或這 workflow 才跑這個 job。改 frontend → 只跑 frontend-ci。

**GitHub Actions 按 minute 計費**,省 CI 分鐘實在。

### CI vs CD

- **CI(Continuous Integration)**:每 push 跑檢查
- **CD(Continuous Deployment)**:檢查過了**自動部署**

我們現在只有 CI。M9 加 CD — push to main → 自動 deploy 到 Railway / Vercel。

## 8.8 M8 速記表

| 概念 | 一句話 |
|---|---|
| **Recharts** | React 的 SVG chart lib,宣告式 |
| **Rebased index** | 都從 100 開始的相對 performance chart,金融標準 |
| **Daily resample** | 把混合解析度 time series 統一到日級,避免鋸齒 |
| **三層 selectinload** | 1+1+1 query,不是 N+M |
| **`ASGITransport`** | 測 async FastAPI 的現代方式 |
| **Dependency override** | 測試時 swap 掉 DI |
| **Line coverage** | 多少 % 程式行被執行,**不是** % 程式對 |
| **CI gate** | 「coverage 掉破 75% PR 不能 merge」 |
| **GitHub Actions** | YAML workflow,push 觸發 |
| **Service container** | CI 環境裡開 Postgres / Redis |
| **Path filter** | 只有特定 path 改動才跑 job |
| **CI vs CD** | 跑檢查 vs 自動部署 |

---

# Part 9:Milestone 9 — Deploy (Railway + Vercel)

## 9.1 這階段在幹嘛?

```
M1-M8:本機 docker compose 起來能跑,但 URL 只有你看得到
M9:把整套搬到雲端,任何人開瀏覽器都能用
```

從「**localhost 玩具**」變「**有真實 URL 跑著的 production app**」。

## 9.2 新概念清單

1. **PaaS vs IaaS** — Railway / Vercel 是什麼
2. **Railway architecture** — service / addon / project
3. **Variable references** — `${{Postgres.PGUSER}}`
4. **Vercel architecture** — Edge / serverless / build
5. **Internal vs public network**
6. **`$PORT` injection** — 動態 port
7. **`sh -c` vs exec form** — Dockerfile CMD 的 shell 模式
8. **Healthcheck per-service**
9. **Deployment Protection**(Vercel)
10. **CDN edge caching**
11. **Zero-downtime deploy**
12. **Push-to-deploy automation**
13. **Production cost model**

---

## 9.3 PaaS vs IaaS — Railway / Vercel 是什麼

### 雲端服務的「**抽象層厚度**」光譜

```
低抽象 (IaaS)                                              高抽象 (SaaS)
   │                                                          │
   ▼                                                          ▼
AWS EC2 ──→ AWS ECS ──→ Railway / Render ──→ Vercel ──→ Notion
(虛擬機)    (容器編排)     (PaaS,跑你的 code)    (跑特定框架)    (現成 app)
```

**IaaS(Infrastructure as a Service)** — 給你機器跟網路,你裝什麼自己管(Linux、Docker、DB...)
**PaaS(Platform as a Service)** — 給你「跑 code」的平台,基礎設施隱藏(Railway 是這層)
**SaaS(Software as a Service)** — 直接給你 app(Gmail / Slack)

### 我們 M9 選 PaaS(Railway + Vercel)的理由

| | AWS (IaaS+) | Railway (PaaS) |
|---|---|---|
| **學習時間** | 1-2 天(VPC / IAM / ECS / ALB / RDS / Route 53...) | 1-2 小時 |
| **隱藏的概念** | 全部要你自己懂 | Network / certs / load balancer 都自動 |
| **成本** | $20-30/月 | $3-5/月 |
| **彈性** | 高(可以 fine-tune) | 低(opinionated) |
| **業界職缺要求** | 70% JD 點名 | 5% 點名 |

**M9 學 PaaS** = 快速上線拿到 URL + 學「部署」概念。
**M13-M14 將學 IaaS** = 把同個系統用 Terraform 部到 AWS,履歷雙打。

---

## 9.4 Railway Architecture — 怎麼運作

### 物件層級

```
Railway Account
  └── Project (像 GitHub repo,但是部署單位)
        ├── Service (一個 container,跑你的程式)
        │     └── Deployment (每次 push 一個新版本)
        ├── Service (worker)
        ├── Service (analyzer)
        ├── Addon (Postgres) ← 跟 service 一樣是 box,只是 managed
        └── Addon (Redis)
```

### 我們 EventSense 部 6 個 box

```
Postgres ──┐
Redis ─────┤
backend ───┤ ← public URL
worker ────┤
analyzer ──┤
beat ──────┘
```

每個 box **跑在自己的 container** 上。Railway 幫你:
- 從 GitHub repo build Docker image
- 跑 container
- 給 public URL(只有 backend 有)
- Inject env vars
- 收 logs / metrics
- Auto-restart on crash
- Auto-redeploy on git push

你完全**不用**碰 server / VM / load balancer。

---

## 9.5 Variable References — Railway 的「自動連線」魔法

### 沒 reference 的世界(原始)

如果你直接抄 Postgres 的 URL 進 backend 的 env:
```
DATABASE_URL=postgresql://user:abc123@hostname.railway.app:5432/db
```

問題:
- Postgres 重 provision 時 password 變了 → backend env 還是舊的 → connect 失敗
- Hostname 變了 → 一樣斷
- Password 寫在 plain text(雖然 Railway UI 有 mask 但還是存在)

### Reference 語法

```
DATABASE_URL=postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}
```

`${{Postgres.PGUSER}}` 不是字面字串 — **Railway resolve 時拿當下 Postgres addon 的 PGUSER 值**。

優點:
- Postgres 改密碼 / 換 host → 自動更新,backend 不用碰
- Service Console 看 env 時這個欄位仍是 reference shape(不洩漏 password)
- 私有 hostname(`postgres.railway.internal`)自動 resolve

### 為什麼要加 `+asyncpg`?

Railway Postgres 自動給的 `DATABASE_URL` 是 `postgresql://...`(預設 driver)。
我們用 SQLAlchemy async + asyncpg driver,**SQLAlchemy 用 URL scheme 決定 driver**:
- `postgresql://` → 用 psycopg2(同步)
- `postgresql+asyncpg://` → 用 asyncpg(非同步)

**只差幾個字,backend 整個跑不跑得起來**。記得加。

---

## 9.6 `$PORT` Injection — 動態 port 的概念

### 為什麼 platform 要 inject port?

```
Railway 一台 host 機器:
  Port 8001 ← service A
  Port 8002 ← service B
  Port 8003 ← service C
  ...
```

多個 service 不能搶同一個 port。**Platform 動態分配每個 service 一個 port**,inject 進 env var `$PORT`。

你的 app **必須讀 $PORT 決定 bind 在哪**:
```python
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

不照規矩 → app 跑了但 platform 找不到 → healthcheck 永遠 fail。

### 我們踩到的坑

第一版 start command:
```
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Railway **直接 exec** 這個 command(沒走 shell),`$PORT` 變字面字串 → uvicorn:
```
Error: Invalid value for '--port': '$PORT' is not a valid integer.
```

**修法:用 `sh -c` 包**:
```
sh -c 'uvicorn app.main:app --host 0.0.0.0 --port $PORT'
```

`sh -c` 啟動 shell,shell 展開 `$PORT` 成實際數字。

### Docker CMD 兩種 form

```dockerfile
# Exec form(array)— 直接 exec,沒 shell
CMD ["uvicorn", "app.main:app", "--port", "$PORT"]
# ↑ $PORT 不展開,literal 字串

# Shell form(string)— 走 /bin/sh -c
CMD uvicorn app.main:app --port $PORT
# ↑ $PORT 展開,但 signal forwarding 較差
```

我們用第三種:exec form `sh -c '...'`,**兩者優點都有**:
- shell 模式展開 env var
- exec 後 sh 是 PID 1,但搭 tini 處理 signal,所以 worker / beat 收得到 SIGTERM clean shutdown

---

## 9.7 Vercel Architecture — Edge + Serverless

### Vercel 跟 Railway 不一樣的地方

Railway:跑長期 process(container 一直開著)
Vercel:**function-based**

```
你的 Next.js page:
  Static page (○) → 預先 render 成 HTML,放 CDN → 第一次 request 直接吐
  Dynamic page (ƒ) → Vercel function on-demand 起來 → render → 回應
```

### Edge CDN

Vercel 把 static assets(HTML、JS、圖片)複製到**全球 70+ edge location**。
你在台灣開頁面 → 從東京 / 香港 edge 拉,**不用跨太平洋打到美東**。

我們的 Next.js build 出 3 個 static routes(`/`、`/_not-found`、`/dashboard`)+ 1 個 dynamic(`/events/[id]`)。

### Serverless function

`/events/[id]` 是 dynamic — 每次 request 在 Vercel function 跑一遍。
- 第一次:**cold start**(load Node + import code,~500ms)
- 後續:**warm**(~50ms)

Vercel function 跑在 AWS Lambda 上(Vercel 自己跑在 AWS)。

### Vercel 沒有「server」概念

你不會看到「container」「process」這些字眼。Vercel UI 沒有「重啟 server」按鈕。
**改了 code → push to main → Vercel 自動 rebuild + atomic swap → 新版本上線**。

---

## 9.8 Internal vs Public Network

### 公開 vs 私有

```
Public Network:
  internet ──→ eventsense-production.up.railway.app ──→ backend
  
Private Network:
  backend ──→ postgres.railway.internal ──→ Postgres
  worker  ──→ redis.railway.internal    ──→ Redis
```

### 為什麼分?

**Public**:
- 任何人可訪問
- 走 internet / SSL 加密
- 有 egress 費(出 cloud 的流量)
- 適合給 user 用的 API

**Private (`*.railway.internal`)**:
- 只有同 project 內的 service 看得到
- 走 cloud 內部網路(不出 internet)
- 沒 egress 費
- **安全**(沒人能從 internet 連 PG / Redis)

我們 backend → Postgres 走 `postgres.railway.internal` — DB **完全不對 internet 開放**。

### 對比 AWS

AWS 對應:**VPC + Private Subnet + Security Group**。Railway 自動幫你做了 — 完全不用設。
AWS 自己做要:畫 subnet、設 NACL、設 SG 允許 backend SG → RDS SG 的 5432 port。

---

## 9.9 Healthcheck — Liveness vs Readiness 為什麼分

### 兩種 probe

| | Liveness | Readiness |
|---|---|---|
| 問題 | 「process 活著嗎?」 | 「process 準備好處理 request 嗎?」 |
| 預設 | 必須 cheap 跟可靠 | 可以做 DB / 外部依賴 check |
| 不過時的行為 | 整個 kill 重啟 | 從 load balancer 摘掉(但 process 不殺) |

### 我們的設計

```python
GET /api/v1/health        — uptime only, no I/O
GET /api/v1/health/ready  — adds DB SELECT 1
```

**為什麼分**:
- 如果 DB 掛 30 秒,liveness 還活 → process 不會被 kill → DB 回來後直接 healthy
- 如果不分,DB 掛 → liveness fail → process 被 kill → 重啟 → DB 仍掛 → 再 kill → 無限重啟

對 Railway 來說我們只設了 liveness path(`/api/v1/health`)— Railway 沒有獨立 readiness 概念。但**未來搬到 k8s** 兩個都用得到。

### Healthcheck 配 Celery 的陷阱(坑 4)

Worker / analyzer / beat 是 Celery,**沒 HTTP server**。Railway 對它們也跑 healthcheck `/api/v1/health` → 永遠 timeout → 永遠 kill。

修法:**healthcheck per-service**(在 service UI 個別設),不要寫進共享 `railway.json`。

**通用教訓**:**config-as-code 的「共享性」是雙刃劍**。某些設定該留 service-specific UI。

---

## 9.10 Vercel Deployment Protection 是什麼

### Vercel 的「預設保護」

Vercel Hobby plan 從某個版本後,**預設打開 Deployment Protection**:
- 所有 preview deployment(每個 PR 自動 deploy 一份)需要 Vercel 帳號登入
- **production deployment 也預設保護**(在某些 plan)
- 目的:你的 user-only-side-project 不想被 Google 索引到

### 我們踩到

Frontend deploy ready,但 URL 全 404 → 因為 protection 開著 + alias 處理保護的 deploy 變 404。

**修法**:Settings → Deployment Protection → Vercel Authentication 關掉(toggle off)。

### 業界 best practice

- Preview deploys(每個 PR)→ 保護(只有 team member 看)
- Production deploy(main branch)→ 公開

Vercel UI 可以分開設,我們直接全關(Hobby 不分 preview / production)。

---

## 9.11 Zero-Downtime Deploy

### 傳統部署

```
ssh server
git pull
systemctl restart backend
# ↑ 期間 1-10 秒 user 看到 502
```

### Railway 的做法

```
新 deploy push:
  1. 起新 container(B)
  2. 等新 container healthcheck pass
  3. Switch load balancer:traffic → B
  4. 殺舊 container(A)

User 看不到 downtime
```

### 我們的 healthcheck 是 zero-downtime 的關鍵

如果沒 healthcheck → Railway 不知道新 container ready 沒 → 可能舊先殺新還沒起 → downtime
有 healthcheck → 「新 container `/api/v1/health` 回 200 才算 ready」→ 安全 swap

---

## 9.12 Push-to-Deploy

連 GitHub repo 後,**push to main 自動觸發**:

```
local: git push origin main
              │
              ▼
GitHub:webhook 通知 Railway + Vercel
              │
              ├─→ Railway 4 個 service 都 rebuild
              │     (path filter 沒設,所以全 trigger;
              │      M8 時 GH Actions 我們有設 path filter,
              │      但 Railway 沒設)
              │
              └─→ Vercel rebuild frontend
                    (Vercel 自動只看 frontend/ 因為 Root Directory)

~3-5 分鐘後 production 更新
```

**達成「沒人在管」的自動化**。

### CI vs CD 關係

- **CI(M8 做的)**:每 push 跑 ruff / mypy / pytest
- **CD(M9 達成)**:檢查過了**自動部署**

完整 pipeline:
```
push to main
  ↓
GitHub Actions:lint + type + test     (CI)
  ↓ pass
Railway + Vercel:rebuild + deploy     (CD)
  ↓
Production updated
```

**「真實的 modern web dev workflow」就是這個**。

---

## 9.13 Production Cost — 真實便宜

| 服務 | 月費 |
|---|---|
| Railway Hobby plan(4 backend services + Postgres + Redis) | ~$2-3 |
| Vercel Hobby plan(frontend) | $0 |
| OpenAI(LLM daily cap $1)| ~$0.5-1 |
| **總計** | **<$5/月** |

**對 portfolio demo 的 value 而言極划算** — 一杯咖啡的錢就能說「我有 production app 跑著」。

### 對比業界其他 stack

| Stack | 月費 |
|---|---|
| Heroku(2024 後沒 free tier) | ~$15-25 |
| AWS(同等 setup) | $20-30 |
| GCP(Cloud Run + Cloud SQL) | $15-25 |
| Vercel + Supabase | $0-5 |
| Railway + Vercel(我們) | <$5 |

---

## 9.14 我們踩到的所有坑(濃縮版)

| # | 症狀 | 根因 | 修法 | 教訓 |
|---|---|---|---|---|
| 1 | Railpack 找不到語言 | Root Directory 沒設 | UI 填 `backend` + 按 Update | UI 改設定要找 confirm button |
| 2 | `$PORT` is not a valid integer | Railway exec form 不展開 | start command 包 `sh -c '...'` | exec vs shell form |
| 3 | Application failed to respond | Domain target port 8000 vs app 8080 | Domain port 改 8080 | EXPOSE 別 hardcode |
| 4 | Celery service healthcheck timeout | railway.json healthcheck 套到 Celery | railway.json 拿掉,backend UI 個別設 | 共享 config 跟 per-service 要分 |
| 5 | Beat 寫 schedule 權限不夠 | `/app` 被 root own | start command 加 `--schedule=/tmp/...` | Dockerfile 該 chown 目錄 |
| 6 | OpenAI 401 全失敗 | env var 是舊 key | 重貼新 key + reset FAILED events | failure_reason 欄位救命 |
| 7 | Vercel 全 404 | Deployment Protection 預設開 | Settings → toggle off | Vercel hobby 默認保護 |

每一個都是面試講得出來的故事。**沒踩坑等於沒學東西**。

---

## 9.15 M9 速記表

| 概念 | 一句話 |
|---|---|
| **PaaS / IaaS** | Railway = PaaS(隱藏 infra),AWS = IaaS+(全自己管) |
| **Railway Project / Service / Addon** | 一個 project 包多個 service 跟 managed addon |
| **`${{Postgres.PGUSER}}`** | Railway variable reference,自動拿 addon 當下值 |
| **`postgresql+asyncpg://`** | SQLAlchemy 用 scheme 選 driver — 一定要 +asyncpg |
| **Internal vs public network** | `*.railway.internal` 是私網,只 project 內看得到 |
| **`$PORT` injection** | Platform 動態分配 port 給 service |
| **`sh -c` shell form** | Dockerfile / start command 想展開 `$VAR` 必須 |
| **tini PID 1** | Signal forwarding 給 worker / beat clean shutdown |
| **Liveness vs Readiness** | 「活著嗎」vs「準備好嗎」,k8s 標準 |
| **Per-service healthcheck** | Celery 沒 HTTP,別套 backend 的 healthcheck 給它 |
| **Vercel Edge CDN** | Static asset 70+ 全球節點,自動 cache |
| **Vercel Serverless function** | Dynamic page 跑在 AWS Lambda 上 |
| **Deployment Protection** | Vercel 預設保護所有 deploy,要主動關 |
| **Zero-downtime deploy** | 新 container healthy 才 swap traffic |
| **Push-to-deploy** | git push → GitHub webhook → 自動 build + deploy |
| **CI → CD** | 檢查過了就部署,完整 modern web dev workflow |

---

## 9.16 面試講 M9 故事建議

5 分鐘版本:

**第 1 分鐘**:架構
> 「M9 把 EventSense 上 production — Railway 跑 backend 4 個 service(FastAPI + 3 個 Celery worker)+ Postgres + Redis addons,Vercel 跑 Next.js frontend。整個 stack 不到 $5/月。」

**第 2 分鐘**:設計選擇
> 「選 PaaS(Railway / Vercel)而非 AWS 是 staged approach — 先快速上線拿到 URL 證明系統能用,M13-M14 會用 Terraform 把同樣系統部到 AWS ECS + RDS,展示 IaaS 能力。Railway 學到的 Docker / env / healthcheck / network 概念全可搬。」

**第 3 分鐘**:踩坑故事一(技術深度)
> 「Beat service 一直 crash 在 `Permission denied: celerybeat-schedule`。追下去發現是 Dockerfile 的 COPY --chown 只 chown 檔案不 chown 目錄,non-root user 沒辦法在 /app 創新檔。臨時修法是把 schedule 寫到 /tmp,長期該改 Dockerfile RUN chown。」

**第 4 分鐘**:踩坑故事二(系統思考)
> 「另一個是 healthcheck 套到 Celery service 全 timeout。原因是 railway.json 把 healthcheck path 設成共享,但 4 個 service 共用 image,只有 backend 有 HTTP。教訓是 config-as-code 不是萬能,某些 per-service 不同的設定該留 UI 個別設。把 healthcheck 從 railway.json 拿掉、backend service 自己設,worker / analyzer / beat 就過了。」

**第 5 分鐘**:結果
> 「Production URL 任何人能開。20 events、36 predictions、30 outcomes 全是真實 OpenAI 跑出來。Accuracy:FRED 56%、SEC 0%、FOMC 25%。**這成績爛但真實** — 業界 LLM 對短線預測接近 random 是已知,我的系統 capture 了這現實沒造假。比『demo 顯示 100% 對』可信 100 倍。」

---

# Part 10:術語對照表

| 術語 | 一句話 |
|---|---|
| **API** | 程式之間溝通的合約(URL + method = 做這件事) |
| **REST API** | 用 HTTP 暴露的 API,我們用的就是 |
| **JSON** | 文字格式的結構化資料,API 標準 |
| **HTTP method** | GET 拿 / POST 新增 / DELETE 刪 / PATCH 改 |
| **status code** | 200 OK / 404 不存在 / 500 server bug |
| **CORS** | 「我同意這些 origin 來打我」的 server 宣告 |
| **container** | 程式 + 環境打包的密封盒(Docker) |
| **image** | 蓋盒子用的藍圖 |
| **volume** | container 外面的儲存空間 |
| **service container** | CI 環境裡的 sidecar(Postgres / Redis) |
| **ORM** | 用 class 操作 DB,不寫 SQL |
| **migration** | DB schema 的版本控制 |
| **connection pool** | 預先開好的 DB 連線池 |
| **NullPool** | 不 pool,每次連線、用完關 |
| **transaction** | 一組 SQL 命令,要嘛全做要嘛全不做 |
| **FOR UPDATE** | row-level lock,其他人想動要等 |
| **SKIP LOCKED** | 看到鎖住就跳過,不等 |
| **idempotent** | 跑 N 次結果都一樣 |
| **at-least-once delivery** | 訊息至少送到一次(可能多次) |
| **state machine** | 狀態轉移的 model,每個狀態有意義 |
| **queue table** | DB 表 + status 欄位 = 輕量任務佇列 |
| **race condition** | 並行執行順序不確定造成的 bug |
| **broker** | 訊息中介(Redis / RabbitMQ) |
| **producer / consumer** | 生產 / 消費 訊息的人 |
| **worker** | consumer process |
| **scheduler / cron** | 排程,按時間表 fire task |
| **async / await** | 「等的時候去做別的事」 |
| **event loop** | async code 指揮中心 |
| **coroutine** | async function 的 return value |
| **callback** | 「等好了叫我」的 function reference |
| **Token(LLM)** | LLM 看的最小單位,按 token 收錢 |
| **Prompt** | 你給 LLM 的指示文字 |
| **Completion** | LLM 回的文字 |
| **Hallucination** | LLM 自信地說錯東西 |
| **Structured output** | LLM 強制按 schema 生成 JSON |
| **Function calling / Tool use** | LLM 結構化輸出的底層機制 |
| **Versioned prompt** | prompt 也要版本控制 |
| **Daily cost cap** | 防止 LLM 帳單暴衝 |
| **Decimal vs Float** | 金融計算永遠 Decimal |
| **Numeric(precision, scale)** | Postgres 對應 Decimal 的型別 |
| **TTL** | cache key 活多久 |
| **Thundering herd** | cache 過期瞬間 N 個 request 同時 miss |
| **Cache write strategy** | write-through / write-aside / read-through |
| **Time series** | 規律取樣的時間資料 |
| **append-only** | 只 INSERT 不 UPDATE 的特性 |
| **OHLCV** | Open/High/Low/Close/Volume |
| **EPS** | Earnings Per Share 每股盈餘 |
| **Surprise %** | 實際打敗預期多少 |
| **Ticker** | 股票代號 |
| **ETF** | 一籃子股票打包成單一商品 |
| **SPY** | 追蹤 S&P 500 的 ETF |
| **Alpha / Excess return** | 超過大盤的回報 |
| **Benchmark** | 基準(我們的 benchmark 是 SPY) |
| **Ground truth** | 真實答案,用來評估模型 |
| **Closed loop** | 預測 → 真實 → 比對的閉環 |
| **CIK** | SEC 給每個 filer 的永久 ID |
| **8-K** | 美國上市公司重大事件 filing |
| **FOMC** | 聯準會利率決策委員會 |
| **RSS** | XML 格式的網站新內容廣播 |
| **XXE** | XML External Entity 攻擊 |
| **DST** | Daylight Saving Time 日光節約 |
| **zoneinfo** | Python 3.9+ 的時區庫 |
| **React** | 「畫面是 state 函數」的 UI library |
| **Component** | 接 props 回 JSX 的 function |
| **JSX / TSX** | HTML 寫在 JS / TS 裡 |
| **Next.js** | React + 路由 + SSR + production essentials |
| **App Router** | 資料夾路徑 = URL |
| **Server Component** | 跑在伺服器,沒 JS bundle |
| **Client Component** | 跑在瀏覽器,需 `"use client"` |
| **TypeScript** | JS 加型別 |
| **Tailwind** | utility-first CSS |
| **TanStack Query** | server state 專用 lib |
| **`staleTime`** | cache 多久不重 fetch |
| **`NEXT_PUBLIC_`** | env var ship 進 browser bundle |
| **SPA** | Single Page App |
| **Rebased index** | 都從 100 開始的金融 chart 標準 |
| **Recharts** | React chart library |
| **CI** | Continuous Integration,每 push 跑檢查 |
| **CD** | Continuous Deployment,自動部署 |
| **GitHub Actions** | GitHub 的 CI/CD 平台 |
| **Coverage** | 多少 % 程式行被測試執行過 |
| **selectinload** | SQLAlchemy eager loading,防 N+1 |
| **N+1 query** | for-loop 觸發的 N 個額外 query |
| **CASCADE delete** | 刪 parent 自動刪 child |
| **anti-join** | 「A 沒對應 B」的 query pattern |
| **NOT EXISTS** | 最乾淨的 anti-join 寫法 |

---

# Part 11:面試講故事 — 5 分鐘版每個 milestone

## M1 — Foundation

> 「M1 是 scaffolding — uv 管 Python 套件、Docker compose 起 Postgres + Redis + FastAPI、用 SQLAlchemy 2.0 async + Alembic 設好 ORM 跟 migration。重點是把 dev environment 弄到『**clone repo → docker compose up → 5 分鐘就跑起來**』。pydantic-settings 處理 env vars,structlog 寫結構化 log,從一開始就 production-ready 的習慣。」

## M2 — Scheduled Fetching

> 「M2 加 Celery + Beat,把 M1 的手動 trigger 變自動排程。重點設計選擇:**DB-driven state machine 而非 Celery chain** — `events.status` 欄位驅動 pipeline,worker crash 重啟仍知道從哪繼續。`task_acks_late=True` + idempotent task 換來 at-least-once delivery 的可靠性。**兩層 retry** — adapter 內 tenacity 處理瞬時抖,task 上 Celery autoretry 處理 systemic outage,職責分明。」

## M3 — Multi-source Ingestion

> 「M3 加 SEC EDGAR 跟 FOMC adapter。但更大的工作是**重構** — 從 M1/M2 的『FRED 直接寫 DB』改成『**adapter 純函式 return list[RawEvent],writer 統一處理 DB**』,讓三個 source 共用 dedup 邏輯。Pydantic frozen model 當 anti-corruption layer。
> 
> 過程中撞到 Python async 最常踩的坑之一 — `got Future attached to a different loop`。asyncpg connection 跟 event loop 綁定,Celery 每次 `asyncio.run()` 開新 loop → pool 重用舊 loop 的 connection 就炸。用 `NullPool` 在 Celery context 開 transient engine 解決,FastAPI 繼續用 pooled engine 維持效能。
> 
> 還有 XML parser 用 `defusedxml` 防 XXE / billion laughs 攻擊。」

## M4 — Prices + Earnings

> 「M4 加股價這條軸,是 M5/M6 的鋪路。新表 `price_snapshots` 用 `Numeric(12,4)` 不用 `float`(IEEE 754 binary 誤差金融計算不能容忍),用 `BigInt PK` 而非 UUID(高頻表 sequential PK 對 B-tree 寫入友善)。
> 
> 用 PG-native `INSERT ... ON CONFLICT DO NOTHING` 做 bulk upsert,比 per-row catch IntegrityError 快 67 倍。Redis cache 60 秒 TTL 給 latest price,**write-aside 策略** — 只有 worker 寫 cache,reader 純讀,避免 cache 過期那瞬間 thundering herd。
> 
> Market hours 邏輯用 `zoneinfo.ZoneInfo("America/New_York")` 正確處理 DST,放在 task 裡而非 cron 表達式 — cron 對 DST 很笨。yfinance 是非官方 scraper,broad except + per-row try + Celery retry + idempotency 四層防禦。」

## M5 — LLM Analysis

> 「M5 是 EventSense 從 data pipeline 變成 AI app 的分水嶺。用 `instructor` 把 OpenAI SDK 包成『丟 Pydantic class 進去,拿 instance 出來』,自動 retry on malformed JSON。Schema 用 `Literal` 而非 `Enum` — 對 LLM 更友善。
> 
> Versioned prompt(`PROMPT_VERSION='v1'` 寫進 DB)讓未來能比較 v1 vs v2 準確率。Daily cost cap $1,超過時 router downgrade premium → default 而非 hard stop — 『**降級服務 > 完全停服**』是 production 原則。
> 
> 跑 e2e 時抓到 race condition — 3 個 parallel analyzer task 對 20 events 產生了 58 predictions。第一次加 `FOR UPDATE SKIP LOCKED` 還是錯,因為 per-event commit 釋放整個 transaction 的所有 lock。真正修法是 per-event transient session,讓 lock scope = task scope。重 test 0 duplicates 通過。**這個 bug 教我 transaction scope 跟 lock scope 是綁在一起的**。」

## M6 — Validation Loop

> 「M6 收閉環 — 預測 → 真實價格驗證 → alignment 判定。算 excess return 而非絕對漲跌:`(ticker_return - spy_return)`,SPY 是大盤基準。NEUTRAL alignment 用 0.5% 閾值(spec 給,大致對應 S&P 一日標準差)。
> 
> 選 **DB polling 而非 Celery ETA**,雖然 spec 提 ETA。理由是 recoverability — broker / worker / config 任何問題重啟仍能 recompute,5 分鐘延遲對 outcome validation 完全無感(本來就 ≥1h 後才能算)。
> 
> 過程中 test 抓到一個 silent data corruption — 第一版 price lookup 在沒 end-price 時會默默拿 baseline 當 end,寫 0% return 的假 outcome。修法是 end-price 加 `must_be_after=predicted_at` 約束,反映 baseline 跟 end 業務語義不對稱。**Silent fake data 比 hard fail 可怕**。」

## M7 — Frontend Sprint 1

> 「M7 第一次有 UI — Next.js 16 App Router + Tailwind v4 + TanStack Query。心智核心是 **server / client component 二分**:server 元件無 JS bundle 但不能用 hook,client 元件相反。我把 `/events/[id]` 拆 server 殼(`await params` 是 Next 16 breaking change)+ client child(TanStack Query 抓資料)— bundle 最小化的同時保留互動。
> 
> 沒用 shadcn/ui — CLI 過不去 piped input,改自己手刻 4 個 Tailwind components,程式碼反而更乾淨。CORS allowlist 而非 `*` — spec 紀律 + 配 `allow_credentials=True` 時瀏覽器規範禁止 wildcard。」

## M8 — Frontend Sprint 2 + CI

> 「M8 加價格 chart(Recharts)、`/dashboard` 聚合準確率頁、80% pytest coverage、GitHub Actions CI。
> 
> Chart 第一版鋸齒像心電圖 — 因為混了 daily backfill + intraday minute 兩種解析度。修法是 `resampleDaily` 按 UTC 日期 group by 統一到日級。用 **rebased-to-100** 表示法 — 金融業比較多 ticker 的標準做法,讓 excess return 直接是兩條線的垂直差距。
> 
> 測試 API 用 `httpx.AsyncClient + ASGITransport` 而非 FastAPI sync `TestClient`(TestClient 走 thread + sync wrapper,跟 M3/M5 同 loop binding bug 根本原因)。用 `app.dependency_overrides[get_db]` 把 pooled engine swap 成 NullPool transient session。
> 
> CI 分 backend / frontend 兩個 workflow,path filter 精準到目錄。Backend 用 Postgres service container。Coverage gate 設 75%(我們在 80%)— 回歸防止器,但不過度逼出垃圾測試。」

---

# 終章:你現在懂的事 vs 三個月前

```
三個月前的你:
  - 知道「後端」「前端」「資料庫」的字面意思
  - 用過 Python,沒部署過
  - 看過 React,沒寫過

現在的你:
  ✅ async / event loop 為什麼存在、什麼時候會炸
  ✅ ORM / migration / connection pool 怎麼運作
  ✅ Celery 分散式 task queue,at-least-once delivery + idempotency
  ✅ FOR UPDATE SKIP LOCKED 跟 transaction scope 的關係
  ✅ LLM API 的 token 經濟、structured output、prompt versioning
  ✅ 金融的 alpha / excess return / SPY benchmark 概念
  ✅ React server / client component 二分
  ✅ TanStack Query 的 cache 策略
  ✅ CORS 怎麼防 CSRF
  ✅ CI 為什麼存在、Path filter 怎麼省 CI 分鐘
  ✅ 測試 coverage 真正意義 + 設多少合適
  ✅ Production 設計原則 — 降級服務 > 完全停服 / Defer ≠ Fail
```

更重要的是,你**踩過的坑**:
- M3 / M5 / M6:asyncpg loop binding(三次,刻骨銘心)
- M3 / M4 / M5:Docker anonymous volume gotcha
- M5:race condition + 第一次修法錯誤的故事
- M6:silent fake data 0% return 的 must_be_after 修法
- M8:bool → float cast in PG

**這些故事就是面試講出來能贏的東西**。
