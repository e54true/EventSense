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
- [Part 9.5:Milestone 9.5 — Production hardening + analyzer overhaul(上線後才發現要修的)](#part-95milestone-95--production-hardening--analyzer-overhaul)
- [Part 9.6:Milestone 9.6 — Accuracy overhaul(把量尺修直)+ terminal UI](#part-96milestone-96--accuracy-overhaul把量尺修直--terminal-ui)
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

**關鍵性質:HTTP 是 stateless(無狀態)**。每個 request 都是獨立的,server 預設**不記得**你上一個 request 是誰發的。所以「登入狀態」不是靠 HTTP 本身記住,而是:
- 登入成功後 server 發一個憑證(**cookie / session id / JWT token**)
- 之後每個 request 瀏覽器都把這憑證塞在 header(`Cookie:` 或 `Authorization: Bearer ...`)一起送
- server 每次收到都**重新驗證**這個憑證,才知道你是誰

這就是為什麼上面 `401 Unauthorized` 會存在 —— 沒帶憑證(或憑證過期),server 對它而言就是個陌生人。

> 通則:HTTP 無狀態 → 任何「跨 request 的記憶」(登入、購物車)都得靠 client 每次主動帶憑證,或 server 把狀態存進 DB/Redis 再用一個 id 去撈。

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

**兩個面試必考性質**:
- **Safe(安全)**:不改變 server 狀態。只有 `GET`(`HEAD`)是 safe —— 所以瀏覽器/CDN 可以放心 cache、預抓。
- **Idempotent(冪等)**:做 1 次跟做 N 次結果一樣。`GET`/`PUT`/`DELETE` 是冪等,`POST` **不是**。

| method | safe | idempotent | 重送會怎樣 |
|---|---|---|---|
| GET | ✅ | ✅ | 沒副作用 |
| PUT | ❌ | ✅ | 覆蓋成同一份,沒事 |
| DELETE | ❌ | ✅ | 第二次刪 404,但狀態一致 |
| POST | ❌ | ❌ | **可能新增兩筆 / 扣兩次款** |

> 通則:網路逾時重試前要先問「這 method 冪等嗎」。POST 不冪等,所以付款/下單常用 **idempotency key**(client 帶一個唯一 id,server 認 id 去重)來補上冪等性。

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

**取捨**:JSON 的代價是**體積大、解析慢、沒有強制 schema**(欄位型別靠雙方口頭約定)。所以高吞吐的 service-to-service(gRPC)會改用 **Protobuf**:二進位、有 `.proto` schema 強制型別、體積與解析都更省。

> 通則:對「人看 / 跨語言 / 外部公開 API」用 JSON;對「機器對機器、量大、要嚴格 schema」用 Protobuf/gRPC。本專案對外是瀏覽器,所以 JSON 是對的選擇。

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

> **為什麼第 3 步 render 完,第 7 步還要再打一次 API?** 這牽涉 SSR vs CSR:
> - **第 3 步是 SSR(server-side render)**:在 server 先把頁面骨架/靜態部分轉成 HTML 直接回給瀏覽器 → 使用者**立刻看到畫面**(首屏快、利於 SEO),不用等 JS 下載完才有東西看。
> - **第 6 步 hydration**:JS bundle 載入後,React 在這份靜態 HTML 上「接管」掛上事件處理與狀態,讓它變成可互動的 app。
> - **第 7 步是 CSR 式的 client fetch**:event 的即時資料(可能常變、或需帶使用者憑證)交給瀏覽器端 TanStack Query 撈,好處是之後切換/重抓不必重整頁面、可走 cache。
>
> 通則:SSR 負責「首屏快+SEO」,client fetch 負責「動態/即時/可快取的資料」。不是重複,是分工。(若資料在 server 端就抓好,則屬 Next.js 的 server component / RSC 路線,本專案此頁走的是 client fetch。)

**為什麼第 8 步要 CORS check?** 瀏覽器有 **Same-Origin Policy(同源政策)**:protocol+host+port 三者全同才算「同源」。本專案 frontend 在 `localhost:3000`、backend 在 `localhost:8000`,**port 不同 → 跨來源(cross-origin)**,瀏覽器預設會擋 JS 讀取回應。

- **CORS** = backend 用 response header(`Access-Control-Allow-Origin: http://localhost:3000` 等)主動「開白名單」,告訴瀏覽器「這個來源可以讀我」。
- **Preflight**:當 request 不是「簡單請求」(帶 `Authorization`、`Content-Type: application/json`、或非 GET/POST 的 method),瀏覽器會**先自動發一個 `OPTIONS` 預檢**問 server 准不准,通過了才發真正的 request。FastAPI 用 `CORSMiddleware` 處理這個 OPTIONS。

> 通則:CORS/同源政策是**瀏覽器在前端執行的保護**,擋的是「惡意網站的 JS **讀取**你已登入 API 的回應」——注意它擋的是「讀回應」,**不是**擋 request 送出(送出且造成 side-effect 那是 CSRF,要靠 SameSite cookie / token 防,詳見 7.9)。所以 `curl`/Postman/server-to-server **不受 CORS 限制**(它們沒有同源政策)—— 這就是「curl 正常、網頁 fetch 報 CORS error」的原因。修 CORS 永遠改 **server 端**設定,不是改前端。

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

**為什麼先 COPY pyproject.toml、最後才 COPY . .?**——**Docker layer cache**。每個指令是一層,只要該層的輸入沒變就重用快取。套件清單變動頻率低、source code 變動頻率高,所以把「裝套件」這層放在「複製 code」之前:改一行 code 只會重跑最後的 `COPY . .`,**不用重裝整包依賴**(省幾分鐘)。若順序反過來,改一行 code 就讓 `uv sync` 那層快取失效、每次都重裝。

通則:**Dockerfile 指令按「變動頻率由低到高」排序**。另外 prod build 用 `uv sync --frozen` 強制照 `uv.lock`,build 時不偷偷解析新版本。

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

> **ENUM / ARRAY 的代價(面試會反問)**:
> - **ENUM 演進有摩擦**:新增來源(我們後來真的加了 Fed speeches)要 `ALTER TYPE event_source ADD VALUE 'FED_SPEECH'`,且在 PG 12 以前這語句**不能在 transaction block 內執行**(Alembic 預設包 transaction,需特別處理);ENUM 值也不能直接 rename/刪除。若來源變動頻繁,用 lookup table + FK 會更彈性。我們押 ENUM 是賭「來源種類少且穩定」。
> - **ARRAY 的代價**:`affected_tickers TEXT[]` 寫起來爽,但**無法對陣列元素建 FK**、正規化差;要查「哪些事件影響 AAPL」得用 `'AAPL' = ANY(affected_tickers)` 或 GIN index,跨表 join 不如獨立關聯表。權衡:讀多寫少、ticker 只是標籤不需 referential integrity，ARRAY 划算。
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

> 註:「快」不只因為 in-memory(Postgres 熱資料也在 `shared_buffers` 記憶體裡)。真正差異是**資料模型極簡**:Redis 沒有 SQL parse/plan、沒有 MVCC/transaction 與多版本可見性檢查、單執行緒事件迴圈避開鎖競爭,所以一次 GET 就是 O(1) hash 查找。代價就是它只能做簡單 key 操作,複雜 query 交給 Postgres。
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

### async ≠ 多執行緒(面試必追問)

關鍵差異:event loop 是**單執行緒 + 協作式(cooperative)**排程——只有當你寫 `await` 時,協程才**主動讓出**控制權給 loop;loop 不會「搶」你的執行權(沒有 preemption)。

| | 多執行緒 | asyncio |
|---|---|---|
| 切換時機 | OS 隨時搶(preemptive) | 只在 `await` 讓出 |
| 平行 CPU | 可(受 GIL 限制) | 不行,單執行緒 |
| 切換成本 | 高(context switch) | 極低(函式呼叫等級) |

**通則:async 的並行只對「在等 I/O」的工作有效,對 CPU work 無效。**

兩個致命坑:
- 在 `async def` 裡跑 CPU 密集迴圈(例如大量 JSON 解析)→ 沒有 `await` 讓出 → **整個 loop 卡死**,所有 request 一起延遲。解法:`await asyncio.to_thread(cpu_func)` 丟到執行緒池。
- 在 async code 裡呼叫**同步阻塞**的庫(`requests.get()`、`time.sleep()`、同步 DB driver)→ 阻塞期間 loop 完全停擺。必須換成 async 版(`httpx.AsyncClient`、`asyncio.sleep`、asyncpg)。這也是我們全程 `await` 到底、driver 一定要選 asyncpg 的原因。

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

### async SQLAlchemy 底層怎麼運作?

SQLAlchemy 的 ORM 內核是**同步**寫的。`AsyncSession` 不是把內核改寫成 async,而是用 **greenlet** 當橋:同步內核跑在一個 greenlet 裡,碰到真正 I/O 時把控制權交還給 asyncio event loop(asyncpg 做實際的 async 網路 I/O),I/O 回來再切回 greenlet 繼續。所以裝 `sqlalchemy[asyncio]` 會拉進 `greenlet` 依賴。

**通則:`AsyncSession` / async `engine` 都綁在「建立它的那個 event loop」上,且不是 thread-safe。**
- 一個 session 不能同時被多個 task 並發使用(會 `InterfaceError` 或拿到髒狀態)。
- engine 的連線池綁 loop——若在 worker 裡每個 task 自建臨時 loop(我們 Celery fetcher 就是),共用全域 pool engine 會「connection attached to a different loop」報錯。這就是 1.8 提的 M5 坑,我們的解法是 worker 端用 NullPool 的 transient engine(見 `backend/app/db/session.py` 的 `transient_session()`),每次重建、不跨 loop 共用連線。

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

**為什麼 enum 要手補 DROP TYPE?**
Postgres 的 `ENUM` 是一個**獨立的 type 物件**,跟 table 是分開存的。兩個盲點:
1. `op.create_table()` 帶 `Enum` 欄位時,SQLAlchemy 會**順便 `CREATE TYPE`**,但 `op.drop_table()` **不會**順便 `DROP TYPE`——type 會殘留。
2. `--autogenerate` 預設**不比對 enum type 的增刪**(只比對 table/column),所以這段它幫不了你,一定要手寫。

後果:downgrade 後再 upgrade,`CREATE TYPE eventsource` 撞到殘留的舊 type → `DuplicateObject: type "eventsource" already exists`,migration 卡死。所以我們在 `downgrade()` 手動補:
```python
def downgrade():
    op.drop_table('events')
    op.execute('DROP TYPE IF EXISTS eventsource')  # autogenerate 不會幫你寫
```
**通則:Postgres 裡 ENUM type 的生命週期要自己管,別假設它跟著 table 走。**

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

**pool 耗盡時會怎樣?**(面試必問)
`pool_size=5 + max_overflow=10` = 最多 15 條同時在用的連線。第 16 個請求**不會立刻報錯**,而是**阻塞排隊**等別人歸還,等到 `pool_timeout`(預設 30s)還拿不到 → 丟 `QueuePool limit ... TimeoutError`。

**通則:async 下這個阻塞特別危險——若連線「借出去後一直不還」(忘了關 session、或長 transaction 卡住),pool 會被慢慢吃光,新 request 全部卡 30s 後 500,症狀像「整個服務間歇性掛掉」。** 所以我們用 `Depends(get_db)` 的 `async with` 確保每個 request 結束一定歸還;歸還時 SQLAlchemy 會自動 rollback 未 commit 的 transaction,避免把髒狀態帶給下一個借用者。

sizing 直覺:pool 上限應 ≤ Postgres 的 `max_connections`(預設 100)除以「同時連 DB 的 process 數」,否則 DB 端先爆 `too many connections`。

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

**通則:Beat 必須是單一副本(singleton)**。Worker 可以水平多開搶 task,但 Beat 不行——跑兩個 Beat = 每個 schedule 到點被 **enqueue 兩次**,等於每小時抓兩遍。Worker 的 idempotent 雖然能讓 DB 結果不重複,但白白浪費一次 fetch + 一次 LLM 成本。

我們的部署因此把 Beat 獨立成一個 **單副本 container**(見 docker-compose:`celery ... beat`,replicas=1),跟可水平擴容的 worker 分開。

面試延伸:要高可用又只准一個 Beat → 用帶鎖的 scheduler(如 `redbeat`,把 schedule 與 leader lock 放 Redis),目前單副本對我們的規模足夠,沒上 redbeat。

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

**Redis broker 的真相 — redeliver 靠 visibility timeout,不是 ack 協定**:

RabbitMQ 有 per-message ack channel,worker 連線一斷 broker 立刻知道沒 ack。但我們 broker 是 **Redis**,Redis 沒有這種協定。Celery 的做法:task 被取走時搬進一個「unacked / visibility」暫存區,啟動一個 **visibility timeout**(`broker_transport_options` 預設 **3600 秒**);時間到還沒 ack,task 才重新變可見、被別的 worker 撿走。

推論:
- worker crash 後 **不是馬上** redeliver,而是要等到 visibility timeout 到期(我們沒覆寫 → 1 小時)。
- 通則:**單一 task 的執行時間必須 < visibility timeout**。否則一個還在跑的慢 task 會被誤判逾時、被第二個 worker 重複撿走(M5 LLM task 要留意,但我們 LLM call 遠短於 1h)。
- 這也是為什麼 idempotent 是硬需求,不只因為 retry——visibility timeout 本身就能造成重跑。

代價:**同一個 task 可能跑兩次**(at-least-once delivery)。

要求:**task 必須 idempotent**(下一節)。

### `worker_prefetch_multiplier=1`

預設一個 worker 從 broker 一次 prefetch 4 個 task 進記憶體。對於慢任務不好 — 一個 worker 卡在跑 task A 時其他 prefetched task 也只能等。

設 1 = 一次只拿一個,跑完才拿下個。對 slow LLM task 重要(M5)。

**prefetch_multiplier vs --concurrency(別搞混)**:
- `--concurrency=N`:這個 worker process 開幾個執行單元(prefork 子進程)= 同時能**跑**幾個 task。
- `prefetch_multiplier=M`:每個執行單元預先從 broker **拉進記憶體待命**幾個 task。
- 真正卡在 broker 外的 in-flight 上限 = **N × M**。設 `M=1` 是讓慢 task 不要把後面的 task 鎖在某個 busy 子進程前面餓死。

我們實際部署(docker-compose):

| worker | queues | concurrency | 理由 |
|---|---|---|---|
| fetch | fetch_queue,validate_queue | 4 | I/O bound,可多開 |
| analyze | analyze_queue | 2 | LLM 有 per-org rate limit,開太多只會撞 429 |

搭配 prefetch=1,analyze worker 的 in-flight 上限就是 2×1=2,精準對齊 LLM 速率。

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

**為什麼 NullPool 可接受、邊界在哪**:
根因是 asyncpg connection 在建立時綁定了當下的 event loop;`asyncio.run()` 每個 task 開新 loop,沿用 pool 裡舊 loop 建的連線就炸 `Future attached to a different loop`。NullPool 等於放棄連線重用——每個 task 自己建一條新連線、用完即關,連線永遠屬於當前 loop。

代價:每次付一次 **TCP + TLS + Postgres 認證** 的建連成本(數十 ms)。為什麼划算:
- 我們的 worker task 是**低頻**(每小時/每幾分鐘一次),建連成本相對 fetch+LLM 完全可忽略。
- FastAPI 是長駐單一 event loop,連線能安全重用 → 那邊保留正常的連線池。

通則:**長駐單 loop 用 pool;每呼叫開關 loop 的 worker 用 NullPool**。對應 code:`transient_session()` 每次 build 一個 NullPool engine。

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

**重跑的三條路徑(都要靠 idempotent 兜底)**:

| 來源 | 觸發 | 是否同一 task id |
|---|---|---|
| tenacity 內層 | 一次 HTTP call 抖,在 adapter 內 retry | 是(根本沒離開 task) |
| Celery autoretry | tenacity 用盡後仍 HTTPError,task **主動 `retry()`**、重新排程一份 | 否,新的 retry 計數 |
| acks_late redeliver | worker 中途 crash / visibility timeout 到期 | 否,broker 重發 |

通則:**autoretry 是程式主動丟回 broker;acks_late redeliver 是 broker 因沒收到 ack 自己重發**——前者算進 `max_retries`,後者不算(它在 Celery 眼中是一次全新投遞)。所以同一次外部故障,最壞情況是 `autoretry max_retries=5` 再疊上 crash redeliver,跑幾次不可預測——這正是為什麼 fetcher 的 idempotent(unique + catch IntegrityError)是硬需求而非優化。

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

**為什麼不用 transaction-rollback 隔離,而用 TRUNCATE**:
更乾淨的做法是每個 test 包在一個 transaction 裡、結束 rollback,完全不留痕跡也天然隔離。我們沒採用,因為待測的 code 自己會 commit(`persist_events` 內有 flush/commit + IntegrityError rollback),外層 transaction 會被它破壞。所以改用「test 前 TRUNCATE 重置」。

代價/限制:
- TRUNCATE+commit 是**全域寫**,因此測試 **不能平行跑**(`pytest -n` 會互相洗表),目前單序跑。
- 會洗掉同一個 DB 的 dev 資料 → M9 前共用、M9 後改獨立 test DB。
通則:能 transaction-rollback 就優先(快又隔離);只有當待測 code 自己 commit 才退回 TRUNCATE,並接受不可平行的限制。

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

**external_id 是去重主鍵,各 source 取「天生穩定且唯一」的識別碼**:

| Source | external_id 取自 | 理由 |
|---|---|---|
| SEC 8-K | `accessionNumber`(如 `0000320193-26-000042`) | SEC 對每份 filing 的全域唯一編號,永不重用 |
| FOMC | RSS `<item>` 的 `<link>` URL | 每篇 press release 一個固定 URL |
| FRED | series_id + 觀測日期 | 同序列同日期唯一 |

> **通則**:external_id 必須是**來源端就穩定且唯一**的欄位,不要自己用 title/時間去湊 hash——來源改字串你就重複寫入了。

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

### writer 的冪等寫入(idempotent persist)

攝取是滑動視窗輪詢(每小時抓最近 N 天),**同一筆 event 一定會被重複抓**。靠三層防線去重:

| 層 | 機制 | 角色 |
|---|---|---|
| 防線 1 | DB 上 `(source, external_id)` **unique constraint** | 唯一的真理來源(safety net) |
| 防線 2 | 寫入前 pre-check `SELECT Event.id WHERE source=? AND external_id=?` | **效能優化**:省掉明知會撞的 INSERT round-trip,不是正確性靠它 |
| 防線 3 | 每筆 insert 包 `async with db.begin_nested()`(savepoint),撞 unique 時 catch `IntegrityError` 跳過 | 處理 **SELECT 到 flush 之間的 race**(另一個 worker 剛插了同一筆) |

```python
for raw in raw_events:
    if await db.scalar(select(Event.id).where(
            Event.source == raw.source,
            Event.external_id == raw.external_id)):
        continue                      # 防線 2:已存在,跳過
    try:
        async with db.begin_nested(): # 防線 3:savepoint
            db.add(event); await db.flush()
    except IntegrityError:
        continue                      # race,unique 擋下了
    inserted += 1
await db.commit()
```

**為什麼一定要 `begin_nested()` 而不是直接 `try/except` 包 flush?**
撞 constraint 後 session 進入 aborted 狀態,若用 session 層 `rollback()` 救,會**連帶丟掉同批前面已 flush 但還沒 commit 的事件**,而 `inserted` 計數器還在加 → 靜默資料遺失。savepoint 把回滾範圍縮到「只撤這一筆」。

> **通則**:冪等寫入 = DB unique constraint(正確性)+ 應用層 pre-check(效能)+ 每筆 savepoint(把 race 的回滾半徑縮到單筆)。三者分工,不可互相取代。

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

### 我們實際怎麼限速 + 隔離(別把 #10 兩件事搞混)

SEC 公告上限約 **10 req/s**。adapter 逐一輪詢 watchlist 每個 ticker,**在 ticker 與 ticker 之間** `await asyncio.sleep(0.15)`(≈6.7 req/s,留安全邊際):

```python
for ticker, cik in TICKER_TO_CIK.items():
    submissions = await _fetch_submissions(client, cik)
    ...
    await asyncio.sleep(0.15)   # 節流,放迴圈尾
```

- **為什麼 sleep 在 ticker 之間而非每個 request**:一個 ticker = 一次 `/submissions/CIK*.json`,本來就 1 request,所以「ticker 間隔」就是「request 間隔」。串行 + 固定 sleep 是最簡單能保證不超速的寫法(不需 token bucket / semaphore)。
- **per-ticker isolation 是另一回事**(容錯,不是限速):每個 ticker 包 try/except,某 ticker 失敗(delisted、CIK 打錯 → HTTP 4xx)只 `log.warning` 後 `continue`,**不會讓整批 run 陪葬**。

```python
try:
    submissions = await _fetch_submissions(client, cik)
except httpx.HTTPStatusError:
    log.warning("...ticker_failed"); continue   # 隔離
```

> **通則**:'限速'(別打爆對方)和 'isolation'(一筆壞料別污染整批)是兩個正交問題;前者用 sleep/節流,後者用 per-item try/except。

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

**對齊的脆弱性**:columnar 解析隱含假設「每個 array 等長」。若某 array(如 `primaryDocument`、`items`)較短,裸 `arr[i]` 會 `IndexError` 噴掉整批。實際 code 對「次要欄位」做長度保護、對「主鍵欄位」(form/date/accession)則信任等長(它們是 SEC 的核心欄位,缺了該筆本來就無意義):

```python
primary_doc = primary_docs[i] if i < len(primary_docs) else ""
items       = items_list[i]   if i < len(items_list)   else ""
```

> **通則**:解 columnar 格式時,對「可選欄位」用 `i < len()` 降級成預設值,別讓一個短 array 連坐整批。

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

**為什麼不乾脆在 worker 維護一個池就好?**
根因是「每個 task `asyncio.run()` 就是一個全新 loop」,而 asyncpg connection 綁 loop。要 pool,池的生命週期就得跟 loop 一樣短(每 task 一池一拋),那跟 NullPool 沒差,反而更複雜。真要長期池,得改成「整個 worker 共用一個常駐 loop」(如 single persistent event loop + run_coroutine_threadsafe),那是更大的架構改動。對「每小時一次、低頻」的 task,NullPool 的每 task ~8ms handshake 完全划算——**先用最簡單能對的方案,頻率上來再優化**。

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

**為什麼是 `selectinload` 不是 `joinedload`?**

| | `selectinload` | `joinedload` |
|---|---|---|
| SQL | 主查詢 + 第二條 `WHERE id IN (...)` | 單條 LEFT OUTER JOIN |
| 一對多(predictions) | **每個 parent 一列,不會把 parent 乘開** | parent 欄位隨子數重複,要去重、回傳列數膨脹 |
| round-trip | 2 條 | 1 條 |

Event → predictions 是一對多,`joinedload` 會讓 parent 列數 = 子列數而膨脹;`selectinload` 只多一條 `IN` query 就乾淨拿到,故一對多預設選它。一對一 / 多對一才偏好 `joinedload`(省一個 round-trip 又不膨脹)。

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

**溢位與捨入行為(別搞混):**
- **整數位超過(precision−scale=8 位)** → Postgres **raise `numeric field overflow`**,不是 silent 截斷。所以塞 1 億以上的 price 會直接報錯,反而是好事(早爆早發現)。
- **小數位超過 scale=4** → **四捨五入**到 4 位(`0.00005` → `0.0001`),不是丟掉。
- scale 選 4 是因為美股某些低價股/期權報價到 4 位小數(sub-penny),2 位不夠;12 位則保證連最貴的標的(如 BRK.A 六位數股價)也塞得下還有餘裕。

> 通則:`NUMERIC` 的 precision 是**硬上限會報錯**,scale 是**會四捨五入**;設計時 precision 要抓到「絕不可能超過」,scale 抓「業務需要的最小有效位」。

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

> **補充:為什麼 1000 並發讀打不垮 DB?** 真正的限流不是「讀很便宜」,而是 **connection pool**(本專案 pool size 約 10–20)。1000 個 reader miss 時,實際上只有 pool size 條連線同時打 DB,其餘在 app 層排隊。而且這 1000 個是**同一個 query**(`SELECT latest WHERE ticker=AAPL`),走主鍵/索引、命中 PG 自己的 buffer cache,單筆 sub-ms,排完很快。
>
> 對比 thundering herd 的真正災難情境(write-through):每個 miss 不只讀、還要**寫** cache + 可能觸發重算,寫競爭才是放大器。write-aside 把「寫」這步從 reader 拿掉,所以即使全 miss 也只是純讀排隊。

### Worker 的 dual-write 一致性

worker 一筆要寫兩個 store:**DB(真相)+ Redis(快取)**。兩者不在同一個 transaction,所以順序很關鍵:

```python
await db.commit()                 # 1. 先寫真相
await redis.set(key, val, ex=60)  # 2. 再寫快取
```

| 失敗點 | 結果 | 嚴重度 |
|---|---|---|
| DB 失敗 | 直接 raise,cache 不動 → 還是舊值(stale ≤ 60s) | 可接受 |
| DB 成功、Redis 失敗 | DB 是新值,cache 是舊值 → stale ≤ 60s 後自動過期修正 | 可接受 |

**通則:先寫真相、後寫快取,且 cache 一定要有 TTL**。這樣任何寫失敗最壞只是「stale 一個 TTL」,絕不會出現「cache 有、DB 沒有」的幽靈資料。

反過來「先寫 cache 再寫 DB」就危險:DB 失敗時 cache 已是不存在的值,且 TTL 內所有 reader 都信它。

本專案因為 cache 只是 latest 價的最佳化、TTL 60s 自癒,所以不需要 distributed transaction / outbox,刻意接受短暫 stale。

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

### DST 之外:市場休市日(holidays / 半日)

`is_market_open()` 只看「週一到五 + 9:30–16:00」還不夠。NYSE 一年有約 9 個全休日(感恩節、聖誕、獨立日…)+ 數個**提早收盤**半日(下午 1:00 收,如感恩節隔日)。這些日期**每年不同**(感恩節是 11 月第 4 個禮拜四),不能 hardcode。

通則:**不要自己維護 holiday 表**,用 `pandas_market_calendars`(或 `exchange_calendars`)查 NYSE schedule:

```python
import pandas_market_calendars as mcal
nyse = mcal.get_calendar("NYSE")
sched = nyse.schedule(start_date=today, end_date=today)
# sched 空 → 休市;sched 有 → 用裡面的 market_open/market_close(已含半日提早收盤)
```

影響:沒處理的話,休市日 worker 還是會去打 yfinance,要嘛抓到前一交易日的舊價、要嘛空 DataFrame —— 第 4.12 的四層防禦會讓它 no-op,所以不會 crash,但會浪費 call 且日誌一堆假 warning。

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

### 補充:UUIDv4 vs UUIDv7(2026 必答)

上面對 UUID 的批評(隨機分布 → write amplification)**只對 UUIDv4 成立**。v4 是純亂數,所以散在整棵 B-tree。

**UUIDv7**(RFC 9562,2024 定案)前綴是毫秒 Unix timestamp + 亂數尾巴 → **time-ordered**,寫入幾乎都落在 B-tree 最右側,write amplification 近似 sequential BigInt,同時保有「不洩漏業務資訊、分散式不撞」。

| | BigInt | UUIDv4 | UUIDv7 |
|---|---|---|---|
| 大小 | 8B | 16B | 16B |
| 寫入局部性 | 最佳 | 最差(散亂) | 接近最佳 |
| 全球唯一/分散式 | 需 sequence 協調 | ✅ | ✅ |

那為什麼 events 還用 v4、prices 仍選 BigInt?(1) events 寫入量低,v4 的散亂無所謂,且當初寫時生態工具對 v7 支援未普及;(2) prices 是 8 bytes × 3000 萬筆的量級,光「16B vs 8B」的 index 體積就值得用 BigInt,time-ordering 只是附帶好處。**通則:高頻表先省空間用 BigInt;若一定要 UUID,2026 用 v7 不用 v4。**

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

### 第 0 層(主動):不要被擋

上面四層都是「掛掉之後」的被動降級;還缺一層「一開始就別觸發封鎖」:

- **序列化 + 間隔**:N 個 ticker 不要 `asyncio.gather` 全部一起轟,逐一抓並夾 `sleep`(或限制並發數),把瞬間 request rate 壓在 Yahoo 容忍範圍內。
- **退避重試**:第 3 層的 Celery retry 要用 **exponential backoff**(而非固定間隔),被擋時等久一點再試,避免一直撞牆加重封鎖。
- **單一 batch call 優先**:能用一次 `yf.download([多個 ticker])` 拿回來就別開 N 個連線,request 數本身最小化。

> 通則:面對沒 SLA 的非官方爬蟲源,被動防禦(降級到 no-op)保證不 crash,但主動限流(rate limit + backoff + 合批)才是讓它**長期還能用**的關鍵 —— 兩者都要。

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

> 📝 **後續更新**:M5 寫的 prompt v1 跟「LLM 直接預測 ticker direction」的設計後來大改 — 加了 macro context、prior analysis、MARKET vs COMPANY split。這節保留 M5 當時的版本,完整演化看 [Part 9.5](#part-95milestone-95--production-hardening--analyzer-overhaul)。

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

底層機制(粗略):

這裡要分清楚兩種不同的「強制」,面試常被追問:

| 機制 | 誰做 | 保證強度 |
|---|---|---|
| **Constrained decoding**(OpenAI strict / structured outputs) | 模型 server 端,生成每個 token 時依 schema **mask 掉不合法 token** | 硬保證,語法上不可能違規 |
| **instructor 預設模式** | client 端:用 tool-calling 拿回 JSON → **Pydantic 驗證 → 不過就把錯誤訊息重新 prompt 給模型**(`max_retries`) | 軟保證,靠重試收斂 |

我們 codebase(`app/llm/clients.py`)走的是 **instructor 預設的驗證-重問**(`max_retries=2`),**不是** token-level masking。所以「不可能生成 `UP`」的精確說法是:就算模型吐了 `UP`,Pydantic `Literal` 驗證會擋下 → instructor 把 ValidationError 當 context 重問一次。通則:instructor 給的是「**最終你一定拿到合法 instance,否則 raise**」,而不是「模型物理上吐不出壞 token」。
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

**第 2 層:每日總額**

today_spend 不是另記一個 counter,而是**直接 query**:
```sql
SELECT COALESCE(SUM(llm_cost_usd), 0)
FROM predictions
WHERE predicted_at >= (今天 UTC 午夜);
```
prediction 是 single source of truth,所以 worker 重啟、多 worker 並行都不會把花費算錯(不像 in-memory counter crash 就歸零)。

**粒度**:analyzer 是「每個 event 開新 transaction 時**重查一次** today_spend 再 `choose_model`」,不是批次起點查一次。所以 20 個 event 跑到第 11 個剛好超標,第 12 個起就**即時降級**到便宜 model,不必等下一批。代價:每 event 多一次 SUM query(量小可接受)。
```python
def choose_model(source, event_type, today_spend):
    if today_spend >= LLM_DAILY_COST_CAP_USD:  # 可設定(env LLM_DAILY_COST_CAP_USD)
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

對 EventSense(<100 events/小時)→ DB queue 完勝。

**crash / 重試語意**:我們沒有獨立的 `IN_PROGRESS` 欄位。worker 在 `commit` 前 crash → 那條 connection 斷掉 → PG **自動釋放它持有的 row lock**,且 status 還是 `FETCHED`(因為沒 commit)→ 下一批 `SELECT ... FOR UPDATE SKIP LOCKED` **自然重撈**,等同 at-least-once。對比 message broker 要靠顯式 ack + visibility timeout 才有同樣保證 —— DB queue 把「lock 隨 connection 生死」當成免費的 crash 復原。代價:沒有 per-task 重試次數上限,壞掉的 event 會一直被重撈(所以才需要 5.9 的 `FAILED` 狀態當終點)。

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

每個 event 開**自己的獨立 transaction**(透過 `transient_session()` 拿一條全新 connection):

> 通則:為何不用同一條 connection 開 SAVEPOINT?因為 **row lock 只在 top-level transaction COMMIT 時釋放,SAVEPOINT release 不會釋放 lock**,而且同 connection 上的 savepoint 仍屬同一個 top-level transaction —— lock scope 還是整批。要 lock scope = 單 event,就得每 event 一條**真正獨立的 connection**。附帶好處:不會 idle-in-transaction 把 connection 鎖一整批(避免長交易拖垮 PG)。

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

**2 個 query,不管多少筆**。**1+1 而非 N+1**。

### `lazy="raise"` — async 的安全網

預設 lazy load 在 **async SQLAlchemy 下是地雷**:lazy load 需要同步發 query,但 async session 不能在存取 attribute 時偷偷 await,結果是執行期 `MissingGreenlet`/隱性 N+1。我們在 relationship 設 `lazy="raise"`:
```python
predictions: Mapped[list[Prediction]] = relationship(lazy="raise")
```
效果:**任何沒先 `selectinload` 就存取關聯的 code,當場 raise**(而不是默默跑出 N+1 或在 async 下爆掉)。通則:把『忘記 eager load』從 production 的隱性效能 bug,變成開發期一定會踩到的明確錯誤 —— fail fast。

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

> 📝 **後續更新**:M6 寫的 **excess-return / SPY 當基準 / 1h+24h+7d 三窗** 後來都改了 — alignment 改成只看 raw return,outcome window 砍成 24h + 7d 兩個。原因看 [Part 9.5](#part-95milestone-95--production-hardening--analyzer-overhaul) 的「Alignment 翻案」跟「窗口砍 H1」兩段。本節保留 M6 當時的版本,讀的時候要記得這些概念被後來的版本取代了。

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

> 📝 **後續更新(Alignment 翻案)**:M6 用 `excess_return`(vs SPY)來判 aligned,但對「標的就是大盤」的 MARKET 預測,excess = SPY−SPY ≡ 0,框架直接退化成永遠 NEUTRAL。後來改成 **aligned 一律看 raw_return**(標的絕對漲跌方向對不對),`excess_return` 仍照算照存、但只供 analytics,不再參與 aligned 判定。詳見 Part 9.5「Alignment 翻案」。

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

> ⚠️ **due 條件其實有個 buffer**:價格 worker 是 5 分鐘 cadence 另外在跑,window 剛到期的那一刻,end price 通常還沒寫進 DB。所以真正的 due 條件是:
>
> ```
> now() >= predicted_at + window_duration + _PRICE_AVAILABILITY_BUFFER   # buffer = 15 min
> ```
>
> 多等 15 分鐘讓價格 worker 先補上,避免「window 一到期就掃到、但價格還沒到 → 整批 defer 空轉」的 race。這跟 6.7 的 tolerance 是兩件事:**buffer 控制「多晚才開始算」,tolerance 控制「能接受多舊的價格」**。

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

### 多 worker 並行:靠 queue-table 鎖,不靠運氣

Polling 的隱憂:跑 2 個 validator,兩邊的 discovery query 會掃到**同一批** candidate,可能同一筆 outcome 算兩次、甚至撞 unique constraint。

做法跟 analyzer 同一套 **queue-table pattern**:

```python
# 1. discovery query 只負責「找出候選」,撈完馬上 commit 放掉交易
candidates = await _candidate_pairs(db, now, batch_size)
await db.commit()                       # 不要 idle-in-transaction 跨整批

for prediction, window in candidates:
    async with transient_session() as task_db:
        # 2. 對「這一筆 prediction」上行鎖;別人鎖住的直接跳過
        locked = await task_db.scalar(
            select(Prediction).where(Prediction.id == prediction.id)
            .with_for_update(skip_locked=True)
        )
        if locked is None:              # 另一個 worker 正在處理 → skip
            continue
        # 3. 拿到鎖後「再查一次」outcome 是否已存在(discovery 到上鎖之間
        #    可能已被別人寫掉)
        if await _outcome_exists(task_db, prediction.id, window):
            continue
        ...                             # 算 + 寫,在自己的短交易內
```

三道保險:`SKIP LOCKED`(不互相 block,只是錯開)+ 上鎖後 re-check + DB unique constraint 兜底。

> **通則**:polling 系統「掃到候選」跟「處理候選」之間一定有時間差,多 worker 必須用 `FOR UPDATE SKIP LOCKED` 把候選「認領」下來,並在上鎖後重新驗證前提,否則 discovery 的結果到動手時早就 stale 了。

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

> **Beat 是誰?** Celery Beat 是**獨立的 scheduler process**(`celery beat`),跟 worker 分開跑,只負責「按 cron 把 task 名稱丟進 queue」(validator 是 `crontab(minute="*/5")`)。
>
> Beat 自己掛掉也不致命:它停的那段時間頂多「沒人 enqueue」,**不會丟任何狀態** —— 一旦重啟,下一個 tick 的 due 條件純粹看 DB(`predicted_at + window + buffer <= now()` 且無 outcome),該補的全部自動補回來。這跟 ETA 把「未來要做什麼」存在 broker 裡的脆弱性正好相反:這裡 Beat 只是個「鬧鐘」,真正的待辦狀態永遠在 DB。

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

### Candidate 選取:公平配額 + 新→舊,避免餓死

defer 是合法狀態,但「一直 defer 的 candidate」會反咬 batch:

- **per-window 公平配額**:batch_size 不是先到先拿,而是**每個 window 分 ~limit/N**。否則某一窗(歷史上是 H1:predicted_at 落在 00:00 UTC、跟日線 snapshot 永遠不重疊 → 永久 defer)會把整批名額吃光,H24/D7 一筆都輪不到。(後來 H1 直接從 `_WINDOW_DURATIONS` 拿掉,連 candidate 都不產。)
- **`ORDER BY predicted_at DESC`(新→舊)**:早期用 ASC,validator 會卡在 2023-2024 的歷史 backfill —— 那些 baseline 時間早於 price_snapshots 的保留範圍,**永遠補不到價格、永遠 defer**,新事件(價格齊全的)反而永遠排不到。DESC 讓 backlog 從「我們真的有資料」的近端開始消化。

> **通則**:queue-table 的 discovery query 一定要假設「有些 candidate 天生填不滿」。沒有 per-key 配額 + 合理排序,這些殭屍 candidate 會把 batch 名額和 worker 時間全吃光,可填的工作反而餓死。
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

> 注意:同一條規則對 **SPY 的 baseline / end 兩筆查詢也一樣套用**(baseline 不限、end `must_be_after=predicted_at`)。四筆價格(ticker baseline/end + SPY baseline/end)任一筆拿不到就整筆 defer,不會出現「ticker 有保護、SPY 用到 baseline 當 end」的不對稱污染。

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

> 📝 **後續更新(per-window threshold)**:M6 這裡用單一 0.5% 套全部窗,後來改成**每個窗各自的 band**:H24=0.5%、D7=1.5%。理由:股價波動大致隨 √t 成長,7d 的合理 band ≈ 0.5%×√7 ≈ 1.5%;若 7d 還用 0.5%,SPY 多數週本來就動超過 0.5%,NEUTRAL 幾乎自動判錯。所以 threshold 從 module constant 變成 `NEUTRAL_THRESHOLDS: dict[OutcomeWindow, float]`。詳見 Part 9.5。

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

> 代價:state 一變,該元件 function **整段重跑**,且預設它的子元件也跟著重跑(即使 props 沒變)。重跑的是『產生 element tree』這層(便宜),真實 DOM 更新由 diff 決定(貴的部分被省下)。若某子樹真的重算很貴,才用 `React.memo` / 把 state 下放到更小的元件來縮小重 render 範圍 — **先別過早優化,大多數 re-render 因為沒碰 DOM 而其實很便宜。**
- React 自動 diff,只更新真正變動的 DOM

`events` 一變,React 重 render 整個 function,內部 diff 後**只更新真實變動的部分**。

**diff 怎麼做到「只更新變動部分」?** React 不逐 DOM 比對,而是比對前後兩棵 element tree:同位置同 type 就 reuse 真實 DOM 只改 props,type 不同就整棵砍掉重建。對 list,React 靠 `key` 配對前後同一個邏輯項目。

```
key 穩定(用 e.id):刪中間一筆 → React 知道是哪筆 → 只移除那個 DOM
key = array index:刪第 0 筆 → 每筆 key 都位移 → React 以為是「內容全變」→ 全部重 render,還可能讓 input 內 state 錯位
```

**通則:list key 要用『資料的穩定身分』(id),不能用 array index——index 會在插入/刪除/重排時讓 reconciliation 配對錯誤。**

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

**Server→Client 的邊界是『序列化邊界』:** Server Component 跑完不是吐 HTML 字串,而是吐一段 **RSC payload**(描述 tree 的特殊序列化格式),瀏覽器端的 React 用它接合 client component。

關鍵限制:**跨這條邊界傳給 client 的 props 必須可序列化** — string/number/array/plain object/Promise 可以,**function、class instance、Symbol 不行**(會 build/runtime 報錯)。所以我們只傳 `id={id}`(string)而不是把整個抓資料的 function 傳下去。

**通則:server 元件做 I/O 與資料取得,把『可序列化的純資料』丟過邊界給 client 元件做互動。要傳 callback?那段邏輯本身就得在 client 側。**

### `"use client"` directive

```tsx
"use client";  // ← 檔案第一行

import { useQuery } from "@tanstack/react-query";
```

這一行**整個檔案變 client component**。import 進來的東西也自動進 client bundle。

> 但有個重要例外:client 元件**不會強迫它的 children 也變 client**。透過 `children`/props 傳進來的 server 元件,是在 server 先 render 好、再以 RSC payload 穿過 client 元件 — 它不會被打包進 client bundle。
>
> ```tsx
> // ClientWrapper 是 "use client",但 <ServerHeavyThing/> 仍在 server render
> <ClientWrapper><ServerHeavyThing/></ClientWrapper>
> ```
> **通則:`"use client"` 影響的是『import 的模組』,不是『透過 props 傳入的 element』。要把重的 server 邏輯塞進互動容器裡,用 children 組合而非 import。**

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

**staleTime vs gcTime(別搞混):**

| 參數 | 管什麼 | 預設 |
|---|---|---|
| `staleTime` | 資料多久內算『新鮮』,新鮮就不 refetch | 0 |
| `gcTime`(舊名 cacheTime) | 沒有任何元件在用這筆 cache 後,多久把它從記憶體 GC 掉 | 5 分鐘 |

關鍵行為:資料變 stale **不等於被刪**。重 mount 時若 cache 還在(未過 gcTime),TanStack 是 **stale-while-revalidate** — **先立刻回舊 cache(畫面不閃 loading)、同時背景 refetch、拿到新的再換掉**。所以 staleTime 控『要不要去打 API』,gcTime 控『閒置多久才釋放記憶體』。

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

> ⚠️ 修正一個常見誤解:CORS 其實**擋不住**上面這個轉帳。
>
> | | 同源政策 (SOP) / CORS 做的事 | 防 CSRF 嗎 |
> |---|---|---|
> | 跨 origin 的 GET/簡單 POST | request **照樣送出**(帶 cookie),只是 evil.com 的 JS **讀不到回應** | ❌ 不防 |
> | 真正防 CSRF | `SameSite=Lax/Strict` cookie、CSRF token、檢查 Origin header | ✅ |
>
> **通則:CORS 是『放寬』同源限制讓正當跨域 fetch 能讀到回應的機制,不是 anti-CSRF 機制。** SOP 保護的是『讀回應』,不是『送出 side-effect』。所以本專案防跨站攻擊靠的是後端 cookie/token 策略,CORS 只是讓 Vercel 前端能合法讀到 Railway API 的 JSON。

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

> 補:**不是每個跨域 request 都 preflight。** 只有「非簡單請求」會。
> - **簡單請求(不 preflight)**:GET/HEAD,或 POST 且 Content-Type 是 `application/x-www-form-urlencoded`/`multipart/form-data`/`text/plain`,且沒有自訂 header。
> - **觸發 preflight**:用了 `Content-Type: application/json`、帶自訂 header(如 `Authorization` 以外的)、或 PUT/DELETE 等。
>
> 我們的 API 多半送 JSON,所以幾乎每個寫入都會多一個 OPTIONS round-trip;可用 `Access-Control-Max-Age` 讓瀏覽器快取 preflight 結果減少往返。
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

**兩個前提要講清楚**:(1) Map 覆蓋『保留最後一筆』**假設 input 已按 `snapshot_at` 升序**;若未排序,留下的不保證是當日最後一筆,正式做法應先 sort 或在 reduce 時比較 timestamp 取較晚者。(2) 選「當日最後一筆」是因為它最接近**收盤價**,金融上以收盤代表當日;若要更完整可改存 OHLC,但比較相對 performance 用收盤即可。

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

### 為什麼是 selectinload 而不是 joinedload

| 策略 | SQL 形狀 | 風險 |
|---|---|---|
| `selectinload` | 每層一個 `SELECT ... WHERE fk IN (...)` | parent 太多時 IN list 很長(SQLAlchemy 會自動分批,預設 500/批);總 query 數固定 |
| `joinedload` | 一個大 `LEFT JOIN` | 一對多會**笛卡兒積膨脹**:1 event × 3 prediction × 5 outcome = 15 列重複 event 欄位,網路與記憶體浪費 |

選 `selectinload` 的理由:這是 **one-to-many → many** 的兩層巢狀,用 JOIN 會列數爆炸;分成獨立 `IN` query 反而資料量最小。

**通則**:一對一/多對一用 `joinedload`(一條 JOIN 最省 round-trip);一對多、尤其巢狀多層,用 `selectinload` 避免列膨脹。

### async 的隱藏地雷

在 async SQLAlchemy 下,**沒有 eager load 的關聯一旦在 await 之外被存取會丟 `MissingGreenlet`**(lazy load 需要回到 greenlet/event loop)。所以這條 chain 不只是效能優化,在 async 是**正確性必需**——序列化回應前必須把 `predictions`/`outcomes` 全 eager 載入。

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

**機制**:asyncpg 的 `Connection`/`Pool` 在**建立當下就綁定該 event loop**(內部把 loop 的 socket transport、reader/writer callback 記住)。換一個 loop 來 await 同一個 connection,asyncpg 會直接丟 `got Future attached to a different loop` / `Task got bad yield`。module-level `create_async_engine` 在 import 時就建好 pool(綁主 loop),而 `TestClient` 另開 thread + 新 loop → 同一個 engine 的 connection 被兩個 loop 碰到 → 撞。

ASGITransport 之所以根治:它**不另開 loop、不開 thread**,直接在 pytest 的同一個 event loop 裡呼叫 ASGI `app(scope, receive, send)`,engine pool 與測試共用同一 loop。附帶好處:不經真實 TCP socket → 沒有 port 綁定/釋放、更快、CI 上不會偶發 connection refused。

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

**為什麼 test 要 NullPool**:預設的 `QueuePool` 會把連線留在池裡跨 test 重用;但測試常在不同 loop / 不同 test function 間切換,重用到一條綁了舊 loop 的連線就撞(同上 asyncpg 問題)。`NullPool` = **不池化,每次取連線都新建、用完立即關閉**,確保每個 test 拿到乾淨且綁在當前 loop 的連線。

**override 怎麼接**:`dependency_overrides[get_db]` 只換掉 DI 解析結果,route handler 的 `Depends(get_db)` 完全不動;測試端 `_test_db` 通常 yield 一個 transaction-scoped session,test 結束 rollback,達成 test 間互不汙染。

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

 講清楚:**實測 coverage 約 80%,但 `--cov-fail-under` 故意設 75%**——gate 設在實測值下方留 ~5% buffer,避免「刪掉一段剛好高覆蓋的死碼」或測試輕微抖動就誤紅 PR;gate 是**地板(防退步)**不是目標,目標仍是維持 ~80%。

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

**容器怎麼被連到**:job 若直接跑在 runner host(非 container job),service 容器的 5432 會被 **port-map 到 `localhost`**,所以測試的 `DATABASE_URL` 指向 `postgresql://eventsense@127.0.0.1:5432/...`(不是容器名)。`--health-cmd pg_isready` 讓 GitHub 等 PG 真的 accept 連線才跑後續 step,避免 race 到「connection refused」。

**為什麼先 `alembic upgrade head`**:(1) 把真實 schema 建到 CI 的 Postgres,讓 pytest 跑在跟 prod 同一套 migration 結果上;(2) 等於**順便測 migration 本身可乾淨套用**——若有人寫壞 migration,這步先紅,不必等到部署才爆。

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

> 📝 **後續更新**:本節記錄 M9 部署當下的 production 狀態跟數字(FRED 56% / SEC 0% 那一批),M9 上線後系統還持續演化了好幾個禮拜 —— 整個 analyzer 被重寫、alignment 邏輯翻案、加了 8-K body 下載。這些「**M9 上線後才補出來的事**」獨立成一節 [Part 9.5](#part-95milestone-95--production-hardening--analyzer-overhaul)。M9 本節是「**怎麼上線**」,M9.5 是「**上線後發現要再改什麼**」。

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

- Postgres 改密碼 / 換 host → reference **下一次 deploy 注入時**自動拿到新值,你不用手改字串。注意:env var 是 **container 啟動時的快照**,不是 runtime 熱更新——若 Postgres 在 backend 已經跑著的時候改密碼,Railway 會觸發相依 service 的 redeploy 讓新值生效(或你手動 redeploy),**而非** 正在跑的 process 即時換密碼。
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

我們用 **exec form 去呼叫 shell**:`CMD ["sh", "-c", "uvicorn ... --port $PORT"]`,同時拿到 shell 展開 env var 的能力,又不靠 image 隱式的 `/bin/sh -c`(行為較可控)。**兩者優點都有**:

- `sh -c` 那層 shell 負責展開 `$PORT`、串 `alembic upgrade head && uvicorn ...`
- 但 **PID 1 不是 sh、也不是 uvicorn,是 tini**——因為我們在 ENTRYPOINT 放了 `["/usr/bin/tini", "--"]`,CMD 整串是當作參數交給 tini 去 exec。
- shell 模式展開 env var
- exec 後 sh 是 PID 1,但搭 tini 處理 signal,所以 worker / beat 收得到 SIGTERM clean shutdown

- exec 後若 sh / uvicorn 直接當 PID 1 會踩到 PID 1 的兩個特殊行為,所以墊一層 tini:
  - **PID 1 不會自動 reap zombie**:子 process 結束後 init 要 `wait()` 收屍,kernel 把這責任綁在 PID 1。一般 shell/app 不做 → zombie 累積。tini 是極小的 init,專門 reap。
  - **PID 1 對沒裝 handler 的 signal 預設『忽略』而非『預設動作』**:`docker stop` 送 SIGTERM,若 PID 1 沒 handler 就被吃掉 → 等 10 秒 timeout 被 SIGKILL 硬殺 → Celery 任務沒 graceful drain。tini 會把 SIGTERM **轉送**給子 process,worker/beat 才收得到、跑完 graceful shutdown。

**通則:容器裡只要 entrypoint 後面還會 fork(shell 串命令、celery worker 起 child),就該放 tini/dumb-init 當 PID 1。**

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

**資料怎麼從 Vercel 流回 Railway?** EventSense 前端拿資料是打 backend 的 **public URL**(`*.up.railway.app`),不是走 Railway internal network(internal 只在同 project 內 service 之間,Vercel 在另一個雲、看不到 `*.railway.internal`)。所以這條是公開、走 internet + SSL、會算 Railway egress。對應要設的接縫:backend 的 **CORS allow-list 要放 Vercel 的 frontend domain**,否則瀏覽器端 fetch 被 same-origin policy 擋。

**通則:前後端分屬兩個雲(Vercel + Railway)= 一定走 public network + 要設 CORS;internal network 的零 egress 紅利只在同一個 Railway project 內享受得到。**

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

### 冷啟動空窗:start-period / grace period

backend 開機要先 `alembic upgrade head` 才起 uvicorn,這段還沒有 HTTP server,healthcheck 一打就 fail。若沒寬限期 → 啟動→判死→重啟→再跑 migration→再判死,無限迴圈。

兩道防線:
- Dockerfile `HEALTHCHECK --start-period=30s`:開機後 30 秒內的 fail **不計入** retries(等 migration + cold boot)。
- Railway/k8s 對應概念是 `healthCheckGracePeriod` / `initialDelaySeconds`。

**通則:有 migration 或慢啟動的 service,healthcheck 一定要配 start-period,否則『跑得久的初始化』會被『跑得快的 probe』判死。**

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

### Migration 在哪一步跑?(zero-downtime 的隱藏前提)

backend 真正的 start command 不是只有 uvicorn,是:
```
sh -c 'alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT'
```
所以順序是:**新 container 先跑 migration → 成功才起 uvicorn → 過 healthcheck → swap → 殺舊**。對應到 zero-downtime 的時間軸:

```
舊 container(A,舊 code)還在收 traffic
  └─ 新 container(B):alembic upgrade head  ← 此刻 DB schema 已經是新的
       └─ uvicorn 起來 → /health 200 → swap → 殺 A
```

**關鍵風險**:swap 前的那段,A(舊 code)跑在「已經被 B migrate 過的新 schema」上。所以 migration **必須 backward-compatible**(加欄位/加表 OK;改名/刪欄位/加 NOT NULL 會讓舊 code 當場炸)。破壞性變更要走 **expand-contract**:先一個 deploy 只加(expand)、等舊 code 全退場、下一個 deploy 才 contract。

**通則:zero-downtime 的真正瓶頸不是 container swap,是 schema 與「新舊 code 並存窗口」相容。** 容器秒切很容易,migration 不能 rollback 才是難的。
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

# Part 9.5:Milestone 9.5 — Production hardening + analyzer overhaul

> 這節寫給「**已經把系統上線了,然後發現上線才是學習開始**」的你。

## 9.5.1 這階段在幹嘛?

M9 把系統推到 Railway + Vercel,任何人能用了。但跑了一週看真實數字:

```
20 events / 36 predictions / 30 outcomes
FRED 56% / SEC 0% / FOMC 25%
```

**SEC 0% 不是隨機,是系統錯了**。隨機應該 ~33%(三個方向)。0% 表示 analyzer 看一個 8-K 永遠出錯。打開細看就懂為什麼:

```
Event title: "AMZN 8-K filed 2026-05-22 (items: 5.07)"
LLM 看到的 payload: { title, items: ["5.07"], filing_date, ... }
LLM 預測:AMZN BULLISH HIGH (conf=0.80)
LLM reasoning: "significant corporate developments may increase investor confidence"
```

這 reasoning 是廢話 — LLM 根本不知道 5.07 是什麼(其實是 shareholder vote),沒看 body,只看標題。**等於蒙眼預測**。

M9.5 整個階段就在補這件事:**把 LLM 從「蒙眼預測」變成「有 context 的分析師」**。

## 9.5.2 為什麼 LLM 預測不準 — 三個根本問題

#### 問題 1:LLM 沒看 body,只看 title
- SEC 8-K body 動輒幾十頁,但 M5 的 adapter 只存了 metadata(item codes, filing date)
- FOMC 也是 — 只存「Fed issued statement」這個 title,statement 內容沒下載
- 結果 LLM 對「**事件實際發生了什麼**」根本不知道

#### 問題 2:LLM 沒 macro context
- CPI 釋出:M5 只給 LLM 一個 `value=332.407` 數字
- LLM 不知道這比上個月高還低、不知道現在升息週期還是降息週期、不知道 10Y/2Y 殖利率倒掛沒
- 等於「**告訴你一個體溫,沒告訴你是發燒前還是發燒後**」

#### 問題 3:Excess return 對 ticker prediction 是雜訊
- M6 寫 alignment 用 `excess_return = ticker_return - spy_return`
- 但 watchlist 7 個都是大型科技股,本來就跟 SPY 高度相關
- 「**AMZN 因為 8-K 漲了 3%,SPY 同期漲 1%,excess = 2%**」— 這時候到底是 8-K 帶動 AMZN 還是大盤帶動?excess return 在這個 sample 結構下說不清楚
- 反而:「**AMZN 漲了 3%,BULLISH 對**」這種 raw return 判定更乾淨

修法分別對應 9.5.3 / 9.5.4 / 9.5.6。

## 9.5.3 修法 1:給 LLM 看 macro context(Phase 1-5)

#### 加 indicators 表
新表 `indicators(name, ticker, value, observed_at)` — 存「不是 event 但是 LLM 該看到的環境數字」:
- **DGS10**(10年期美債殖利率)
- **DGS2**(2年期美債殖利率)
- **PE**(S&P 500 PE ratio,從 multpl.com 爬)
- **CAPE**(Shiller CAPE,同樣 multpl.com)

這些不是事件 — 不會「發生」、沒有 publish timestamp、純粹是個 time series 數值。但 LLM 看到「CPI 6.5% + DGS10 4.5% + DGS2 4.8%(殖利率倒掛中)」會做出**比看到單一 CPI 數字遠遠合理**的預測。

#### Predictions 加 `kind` 欄位

原本一個 event 就出 N 個 predictions(N=watchlist 大小)。改成兩種 kind:
- **`MARKET`** prediction:對 SPY / QQQ 出方向
- **`COMPANY`** prediction:對個股(AAPL, MSFT, ...)出方向

為什麼分?**事件本質不同**:
- FOMC / CPI → 主要影響大盤 → MARKET prediction 才有信號
- AAPL 8-K → 主要影響 AAPL → COMPANY prediction 才有信號
- 同一個 LLM call 兩種都生,但 routing / weighting / dashboard 顯示分開處理

#### context_builder

新模組 `app/services/context_builder.py`:對每個要 analyze 的 event,組合「LLM 該看到的世界快照」:

```
給 LLM 看的 context block:
─────────────────────────────────────
Recent macro indicators (latest):
  CPI: 6.5% (3 months ago: 6.4%, trend ↑)
  DGS10: 4.50% (1 month ago: 4.30%, trend ↑)
  PE: 28.3 (Shiller CAPE: 35.1, both ABOVE 20-year mean)

Prior LLM analyses on this ticker (last 30 days):
  - 2026-05-15 earnings → BULLISH, outcome: ❌ (actual -2%)
  - 2026-04-29 earnings → NEUTRAL, outcome: ✅ (actual +0.3%)

Now analyze this event: [event body inline]
─────────────────────────────────────
```

LLM 看到「**我上次說 BULLISH 結果跌了**」會自動調低 confidence — **這就是 self-reflection 的 zero-shot 實現,無需 RLHF**。

> 注意這個 feedback loop 有**冷啟動 / 時間落差**:prior analyses 的 outcome 是 validator 在 H24/D7 之後才回填的。所以一個 event 剛進 analyzer 時,撈到的 prior 很可能 outcome 還是 pending(尤其新 ticker、或 9.5.9 那種 lookback 沒抓夠歷史的情況——窗口直接是空的)。
> 通則:**LLM self-reflection 的有效性正比於『已 settle 的 prior outcome 密度』**。系統跑越久、同 ticker 事件越多,這條 context 才越有訊號;上線初期它幾乎是 no-op,別把它當魔法。

#### Phase 1-5 的執行順序

1. Phase 1(`a127719`):加 schema 鋪路(indicators 表 + predictions.kind 欄位)
2. Phase 2(`dd4b949`):FRED 抓多個 series + 寫殖利率 indicator
3. Phase 3(`f367325`):multpl.com PE/CAPE scrapers + FOMC dot plot
4. Phase 4(`e70924e`):context_builder + v2 analyzer 跑 MARKET/COMPANY 分軌
5. Phase 5(`0bbd849`):frontend 把 MARKET vs COMPANY 拆開顯示 + 畫 macro context box 給用戶看

每個 Phase 都是一個獨立 commit,可以 revert,典型的「**大改用小步走**」策略。

## 9.5.4 修法 2:抓 document body(Phase A/B/C)

LLM 不能光看 title 預測,就要真的讀內容。

#### Phase A(`c894664`):Earnings body
yfinance 拿 EPS surprise 之後,額外拉 Revenue / Net Income / EBITDA + 算 YoY growth。LLM 終於看到完整 fundamentals,不只 EPS。

#### Phase B(`14e4a7f`):SEC 8-K body
新表 `event_documents(event_id, kind, url, body, downloaded_at)`。
- SEC adapter 抓到 8-K → 排程獨立 task 去下載 `*.htm` body + EX-99.1 press release
- Body 通常 50-200KB,存進 DB 不是問題
- Analyzer 加 **doc-wait** 邏輯:event 是 8-K 時,如果 documents 還沒下載完,**defer**(等 5 分鐘下次 beat 再試)
- 不會「半成品 LLM call」— body 沒到就等

- doc-wait 不是無限等,是 **time-bounded defer**:判定條件是「SEC 8-K 且 `fetched_at` 在 5 分鐘(`_DOC_WAIT_SECONDS=300`)內 且 還沒有 `event_documents` row」才 defer。超過 5 分鐘就 **fall through**,帶現有 payload 照樣 analyze。
- 為什麼要設逾時?因為 SEC body 可能永遠抓不到(503 / EX-99.1 不存在 / URL 解析失敗)。沒有逾時就是「無限 defer = 永遠不出 prediction」,那才是真的 fail。
- 所以精確說法是:**短期內優先等 body,但 5 分鐘後寧可用 metadata 出一個 prediction,也不讓 event 卡死**。這跟 9.5.10「Defer ≠ Fail」其實一致——defer 是「給資料一個合理到場時間」,不是「無限等」。

frontend 同步加「attached documents」section 給用戶點開看(commit `58fc074`)。

#### Phase C(`5772a75`):FOMC body
FOMC adapter 抓到 statement URL → 下載文本 inline 到 payload。LLM 看到的不再是「Federal Reserve issues FOMC statement」,而是完整聲明:「The Committee decided to maintain the target range...」

**Phase A/B/C 共同主題**:「**Title 是 metadata,body 是 signal**」。M5 設計犯的錯就是把 title 當 signal — 因為當初開發階段沒看真實 production data。

## 9.5.5 修法 3:Prompt v3.2 — 強制 LLM 思考(`9ca65f0`)

M5 寫的 prompt v1 大概這樣:

```
You are a financial analyst.
Given this event payload: {payload}
Predict the impact on each ticker in the watchlist.
Respond with JSON: {direction, magnitude, confidence, reasoning}.
```

問題:**LLM 寫的 reasoning 是事後合理化** — 它先決定方向再倒推理由。Prompt v3.2 強制改變這個順序:

```
You are a financial analyst.

Step 1: Establish temporal anchor.
  Cite ONE prior comparable event (with date) and its outcome.
  Example: "On 2026-03-15, AMZN announced similar 8-K (items 5.07),
  stock moved -1.2% over 7d."

Step 2: Reason from anchor.
  Compare current event to anchor. What's different?
  How does macro environment (rates, PE) modify your view?

Step 3: Give direction + magnitude + confidence + 5-sentence reasoning.
  Confidence should reflect strength of your anchor + macro confluence.
```

加上:**最近 5 個 prior analyses on same ticker 進 prompt** — LLM 看到自己過去判錯的紀錄,自動調 confidence。

reasoning 從 1 句話放寬到 5-6 句(M5 的 `max_length=500`)— 因為要 capture thought chain。

#### 為什麼這叫 v3.2 不是 v2

prompt iterate 過 v2(commit `e70924e`)→ v3(內部 iteration)→ v3.2(`9ca65f0`)。每次小調都 bump 版本,DB 裡 `prediction.prompt_version` 留紀錄 — **未來想對比「v2 vs v3.2 哪個準」就靠這個欄位**。

## 9.5.6 概念翻案:Excess return 反而是雜訊(`faeb2d6`)

這是 M9.5 最違反直覺的修改。

M6 教的:`excess = ticker - SPY`,正的就是 alpha。直覺很順 — 全市場漲 1%、ticker 漲 3% = ticker 真的有自己的故事 = +2% alpha。

**為什麼這個對 EventSense 沒用**:
- 我們的 watchlist 全是大型科技股 — 跟 SPY corr ~ 0.85
- 大型科技股加總起來大概 = SPY 一半 — 用 SPY 當基準是「**自己當自己的對照組**」
- SEC 公司事件:8-K 是 company-specific shock,大盤動態跟它無關 — 扣 SPY 把訊號扣掉了
- macro 事件(FOMC):全市場一起動,扣 SPY 之後 ticker excess 接近 0,sign 不穩

**新做法**:`is_aligned(direction, ticker_return)` — 不再扣 SPY。
- BULLISH + ticker_return > 0 → aligned
- BEARISH + ticker_return < 0 → aligned
- NEUTRAL + `|ticker_return| < 0.5%` → aligned

- NEUTRAL + `|ticker_return| < 0.5%` → aligned

> Knife-edge:三條規則都用**嚴格不等號**(`>` / `<`),所以在 `|ticker_return| == 0.5%` 這個邊界點,BULLISH/BEARISH 跟 NEUTRAL 都不成立 → 該方向一律判 **not aligned**。這是刻意的:邊界點本來就模稜兩可,寧可算錯一格(保守判錯),也不要讓同一筆 outcome 同時滿足兩個方向、污染 accuracy 統計。閾值 0.5% 也統一套在所有 window(H24/D7),不隨時間放大。

`spy_return` / `excess_return` 欄位**保留**(dashboard 視覺對比有用),但 `aligned` 計算不再用。

**這推翻了 M6 寫的「alpha 是金融正統」的話**。M6 寫得沒錯 — alpha 在投資界確實是標準。**但這個系統的問題不是「ticker 跑贏 SPY 沒」,是「LLM 預測對沒」**。對應到不同 question 就要選不同 metric。

#### 這次修改怎麼跑到 production

光改 code 不夠 — 既有的 `prediction_outcomes` row 裡 `aligned` 是用舊邏輯算的。要重算:
1. 改 code(`faeb2d6`)
2. Push redeploy
3. 跑 `app/scripts/purge_legacy.py` 砍掉所有 v2 outcomes(predictions 留著)
4. Validator beat 5 分鐘內自動重 fill,用新邏輯算

**這就是 9.5.8 那三個 one-shot script 出現的原因**。

## 9.5.7 砍掉 1h outcome window(`462d82e`)

M6 設計三個窗:H1(1 小時)/ H24(24 小時)/ D7(7 天)。M9.5 砍成 **H24 + D7 兩個**。

原因:
- H1 噪訊大 — 1 小時內價格主要反映「事件剛好開盤前 / 開盤後 / 盤中」,跟 LLM 預測對不對沒關係
- 統計上 H1 outcome 跟 H24 outcome 高度相關(同向 80%+)— 收集兩個沒比一個多多少 information
- H1 是 backfill 抓盤前 / 週末資料的災區(週六發布的 event 找不到 +1h 的盤中價)

修法:
- enum 其實**沒拿掉** `OutcomeWindow.H1` 還留在 enum,只是 validator 不再 iterate 它(`_WINDOW_DURATIONS` 只列 H24/D7)。為什麼不直接刪 enum 值?因為 enum 是 Postgres `prediction_kind`/window type,刪 enum 值要 migration、且舊 row 還引用著它。**做法是『stop writing + DELETE 既有 + 顯示層隱藏』,enum 值留作 dead value**——比硬改 enum type 安全。
- `DELETE FROM prediction_outcomes WHERE window = 'H1'` 砍掉既有 H1 outcomes
- `DELETE FROM prediction_outcomes WHERE window = 'H1'`
- frontend 顯示也拿掉

**這也呼應前面的觀念:less is more。多收 1h outcome 沒讓系統更聰明,只是多一欄 noise**。

## 9.5.8 三個 one-shot 維護腳本

M9 上線的時候只有 `backfill_prices.py` 一個 script。M9.5 補了三個處理 **production DB state 變更** 的工具。為什麼需要它們?

**問題**:改 prompt / 改 alignment 邏輯之後,**code 是新的但 DB 裡的舊資料還在用舊邏輯算的**。如果不主動清,用戶看到的 dashboard 永遠是「舊 code 的歷史結果」+「新 code 的近期結果」混在一起。

#### Script 1:`cleanup_backfill.py`(`3c94083`)
**用途**:全部 events 翻回 FETCHED,讓 analyzer 用最新 prompt 重跑。

```python
# 偽碼
async with transient_session() as db:
    await db.execute(update(Event).values(status='FETCHED'))
    await db.execute(
        delete(PredictionOutcome).where(
            PredictionOutcome.prediction_id.in_(
                select(Prediction.id).where(Prediction.prompt_version == 'v2')
            )
        )
    )
    await db.commit()
```

跑完之後 beat 每分鐘 trigger analyzer,~5 分鐘所有 events 都用新 prompt 重 analyze 過了。

#### Script 2:`dedupe_predictions.py`(`acfcdbd`)
**用途**:`cleanup_backfill` 跑兩次以上會產生重複 v2 predictions(原本就有 1 個 + 新跑出來 1 個)。這個 script 砍重複。

根因:`predictions` 表**刻意沒有** `(event_id, ticker, prompt_version)` 的 unique 約束。所以同一個 event 用同一版 prompt 重 analyze,DB 不會擋,就多插一筆。

為什麼不直接加 unique 約束擋掉?因為「同 event 同 ticker 出兩筆」在某些情境是合法的(例如未來想保留 prompt 微調前後的對照,或 MARKET/COMPANY 兩 kind 共用 ticker 維度)。約束加下去會把這條路堵死。**選擇用事後 dedup script 而非前置 unique 約束,是把『去重』從 schema invariant 降級成 maintenance 動作,換取 prediction 寫入的彈性**。

關鍵 SQL:
```sql
WITH ranked AS (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY event_id, ticker, kind
               ORDER BY created_at DESC
           ) AS rn
    FROM predictions WHERE prompt_version = 'v2'
)
DELETE FROM predictions WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
```

`ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ... DESC)` — partition 內按時間降序排,`rn=1` 是最新的,`rn>=2` 全砍。**這是 SQL 經典 dedup pattern,任何 dedup 都用得到**。

Outcomes via `ON DELETE CASCADE` 跟著 prediction 一起砍。

#### Script 3:`purge_legacy.py`(`faeb2d6`)
**用途**:alignment 邏輯改了之後,所有 v2 outcomes 用舊邏輯算的,需要全砍讓 validator 重 fill。

```sql
DELETE FROM prediction_outcomes
WHERE prediction_id IN (SELECT id FROM predictions WHERE prompt_version = 'v2');
```

跑完 outcomes count = 0,validator beat 5 分鐘內開始 refill。

#### 為什麼這些是 one-shot 不是 alembic migration?

- Alembic migration 改 schema(加欄位、改型別)
- One-shot script 改 data(算法變了,row 內容要重生)
- 兩者本質不同,工具也不同

**設計收穫**:**production migration 不只 schema,也包括 data semantics**。M9 上線時沒這個概念,M9.5 才被現實教會。

## 9.5.9 SEC adapter LOOKBACK 14 → 60(`6d9a9f4`,本 session)

#### 怎麼發現的
session 中用戶問「adapters 還有在跑嗎?」我查 production:
- SEC adapter cadence 每 15 分鐘
- 但最近 24 小時 inserted=0(parsed=5 都是 dedup)
- 不是壞了 — 是「沒新 8-K」

順手查 events 表,發現問題:
- production 第一次 ingest 是 2026-06-07
- 但 SEC adapter `LOOKBACK_DAYS = 14`(M3 寫的常數)→ 上線那天往回 14 天 = 5/24 起的 8-Ks 才會抓
- 結果 4-5 月的 18 個 8-Ks(七家科技巨頭各有 1-7 個)**全部沒抓**

LLM 看「最近 30 天 same-ticker prior analyses」窗口時是**空的** — 因為當初該抓的 events 沒抓。

#### 修法 + 後續處理

1. 改 `LOOKBACK_DAYS = 60`,push redeploy
2. 用 Railway env credentials 跑一次 `sec_edgar.fetch_new()` — insert 18 新 8-Ks
3. 跑 cleanup_backfill 翻全部 events 為 FETCHED(51 老 + 18 新 = 69)
4. Analyzer 自動跑完(68 ANALYZED + 1 FAILED — MSFT 5.02 沒解)
5. dedupe_predictions 砍 109 dups(51 老 events 各有 1 舊 v2 + 1 新 v2)
6. purge_legacy 砍 168 v2 outcomes
7. Validator 自動 refill → 216 outcomes(87 H24 + 129 D7)

#### 從這次經驗學到的設計通則

**任何 LOOKBACK / horizon 參數都要留 headroom**。M3 寫 14 天當時夠用(本機開發只看最近),但沒考慮 production deploy gap(系統先實作好但等 1-2 個月才上線)。改 60 天之後再有任何 deploy 延遲都撐得住。`(source, external_id)` unique index 會 dedup,所以拉長 lookback 不會重複 insert。

## 9.5.10 學到的觀念

#### 1. LLM context engineering > prompt wording

M5 寫了很漂亮的 prompt,但 LLM 預測還是 random。為什麼?因為 LLM 沒看 body、沒看 macro、沒看 prior。**改 prompt wording 沒用,得改它看到什麼**。

換句話說:prompt 是「**指令**」,context 是「**資料**」。LLM 是「**老闆**」、勞工是「**資料**」。指令再漂亮,沒資料還是無米之炊。

#### 2. Metric design > metric correctness

M6 用 excess return 不是錯 — 投資界這樣量測。但對 EventSense 這個系統,raw return 反而乾淨。**選 metric 要看 question type,不是看書上怎麼寫**。

正確的問法:「**我這個 metric 的 sign 是不是真的對應我想 measure 的東西?**」

對 EventSense 來說:
- 想 measure 的東西:LLM 預測 ticker 漲跌方向對沒
- raw_return 的 sign:對應「ticker 真實漲跌方向」✓
- excess_return 的 sign:對應「ticker 比 SPY 多 / 少漲多少」— 跟 LLM 預測「方向」有偏差

#### 3. Title is metadata, body is signal

Phase A/B/C 全在做這件事。下次設計 ingestion pipeline 時要記得:**第一版至少要有一個 body 進 LLM**,不要全靠 metadata 做 prediction。

#### 4. One-shot scripts 是 production migration 的 first-class citizen

不只 alembic 改 schema 才叫 migration。算法邏輯改了,DB row 裡的「**用舊算法算出來的結果**」也要有 migration 路徑。

之後設計新功能時的 checklist:
- [ ] Code 改完
- [ ] Tests 過了
- [ ] 改了什麼語義?
- [ ] **既有 DB row 還對嗎?如果不對,寫個 one-shot script**

#### 5. Defer ≠ Fail(再次驗證)

- doc-wait:body 沒下載完不要硬 analyze,等等
- price-missing:end-price 沒到不要寫假 outcome,等等

兩個情境都用 defer。系統永遠在「**等資料 vs 寫半成品**」之間選等。**Defer 是 production data systems 的設計信仰**。

#### 6. LOOKBACK / horizon 要留 headroom

M3 寫 14 天當時夠 — 沒考慮 deploy gap、沒考慮 backfill 場景。M9.5 改 60 之後彈性大很多。

通則:**任何「最近 N 天」的參數,要思考「**N 應該包含我們可能離線多久**」**,而不是「我現在需要看多近的資料」。

#### 7. 上線後要主動 query production 看真實 state

M9 上線寫了一份「20 events / FRED 56%」當記錄,但這數字 24 小時後就變了。Deploy log 不是 production 狀態的 source of truth,**production DB 才是**。

養成定期 `SELECT status, COUNT(*) FROM events GROUP BY status` 的習慣 — 系統行為跟你以為的不同的時候,真實數字會告訴你。

## 9.5.11 對 M5 / M6 寫的東西要記得什麼變了

| M5 / M6 寫的 | 現在實際上是 |
|---|---|
| Prompt v1(直接餵 payload) | Prompt v3.2(餵 context block + temporal anchor + prior analyses) |
| Reasoning max 1 句 | Reasoning 5-6 句,strict temporal ordering |
| Prediction 結構:direction + magnitude + confidence | 加 `kind` (MARKET / COMPANY) + `thesis` (persisted reasoning) |
| Cost cap downgrade:premium → default | Earnings 也升 premium,只有真的 over-budget 才 downgrade |

> 補背景(cost cap 機制細節在 LLM 配置那節,這裡只記 M9.5 的改動):analyzer 每次 call 前查當日累計花費,逼近 $5 日上限時才把 model 從 premium 檔 **downgrade** 成 default 檔以省錢。M9.5 的改法是**讓 earnings 這類高訊號事件預設就升 premium**(之前只有部分事件升),只有在真的快撞上限時才 downgrade——亦即「**預設給好 model,省錢是 fallback,不是常態**」。確切的 premium/default model id 與單價請對照 LLM 配置章節,不在此重述以免過時。
| Outcome window:H1 + H24 + D7 三個 | 只剩 H24 + D7 |
| Alignment metric:`excess_return` (ticker - SPY) | `raw_return` (純 ticker) |
| `is_aligned(direction, excess)` | `is_aligned(direction, raw_return)` |
| Validator candidates ORDER BY ASC | ORDER BY DESC(新 prediction 先 fill,backfill 不 starve 新的) |

補機制(為什麼這兩格要一起改):
- **舊 ASC + 共享 batch_size=50 的 starvation**:validator 每 tick 撈最舊的 50 筆 candidate。H1 永遠 unfillable(週末/盤前沒 snapshot),這些最舊的 H1 row 每次都被撈出來、defer、燒掉一個 slot,**新進 event 永遠排不進那 50 格**。
- **改 DESC**:newest-first,確保有齊 price 的近期 event 先被 fill,不被卡死的舊 H1 拖累。
- **per-window sub-budget**(`per_window = limit // len(_WINDOW_DURATIONS)`):H24 / D7 各分到 batch 的一半,**就算某個 window 全 defer,也不會把另一個 window 的額度吃光**。通則:**有多類別、其中一類可能系統性失敗時,共享 budget 一定要切成 per-class sub-budget,否則壞掉那類會餓死好的那類**。
| Validator batch_size 50 共享 | 每個 window 自己一個 sub-budget |
| event payload 只有 title + metadata | + body + EX-99.1 + fundamentals(Phase A/B/C) |

回去讀 M5/M6 兩節時記得對照這張表,**舊內容當「歷史紀錄」讀,不是當「現況」讀**。

## 9.5.12 面試講 M9.5 故事建議(5 分鐘版)

#### 第 1 分鐘:framing
> 「M9 把系統推上 production 之後跑了一週,觀察到 LLM 預測 accuracy SEC 0% / FRED 56% / FOMC 25%。問題不是 model — 問題是我給 LLM 看的 context 不夠。M9.5 整個階段就在補 context 跟乾淨閉環。」

#### 第 2 分鐘:Phase 1-5(context engineering)
> 「最大改動是加 `context_builder`:每個 event 進 analyzer 之前,組合一個 macro snapshot —— 最近 CPI 趨勢、10Y/2Y 殖利率、PE/CAPE、加上同一 ticker 最近 5 次 prior LLM analyses 跟 outcomes。LLM 看到『我上次說 BULLISH 結果跌了』會自己調 confidence。沒改 model,純改 input → analyzer 從 zero-shot oracle 變 contextual reasoner。」

#### 第 3 分鐘:Phase A/B/C(body 下載)
> 「同步發現 LLM 從來沒看 8-K body,只看 item code metadata。所以加 `event_documents` 表 + 獨立 download task 抓 8-K body / EX-99.1 / FOMC statement。Analyzer 改成 doc-wait — body 沒下載完就 defer,不硬上 LLM。這呼應 M6 學到的『defer ≠ fail』原則。」

#### 第 4 分鐘:概念翻案(metric design)
> 「最違反直覺的改動是把 alignment metric 從 excess-return 改成 raw-return。M6 學到 alpha 是金融正統 — 但我們 watchlist 全是大型科技股,跟 SPY corr ~ 0.85,SPY 當基準等於『**自己當對照組**』。SEC 公司事件特別誇張 — 8-K 是 company-specific shock,扣 SPY 把訊號扣掉了。換 raw return 之後 alignment 數字立刻變乾淨。**Metric correctness 跟 metric design 是兩件事**。」

#### 第 5 分鐘:Production migration scripts
> 「改 alignment 邏輯之後 production DB 裡的舊 outcomes 全部用舊邏輯算的,要重生。所以寫了三個 one-shot scripts:cleanup_backfill 翻 events 回 FETCHED、dedupe_predictions 用 `ROW_NUMBER() OVER PARTITION` 砍重複、purge_legacy 砍舊 outcomes 讓 validator 重算。這讓我意識到 **production migration 不只 schema(alembic),也包括 data semantics**。之後任何算法改動都會問:既有 row 對嗎?不對就寫 script。」

---

# Part 9.6:Milestone 9.6 — Accuracy overhaul(把量尺修直)+ terminal UI

> 這節寫給「**系統會跑、數字會動,但你開始懷疑數字本身對不對**」的你。M9.5 把 LLM 從蒙眼變成有 context;M9.6 發現**評分的尺從第一天就是歪的** — LLM 再強,標籤錯了 accuracy 就是噪音。

## 9.6.1 這階段在幹嘛?

起因是一次全專案 bug 審查。順著「accuracy 怎麼算出來的」往上游追:

```
/accuracy 的 aligned 欄位
  ← validator 用 predicted_at 開 24h/7d 視窗算報酬
    ← predicted_at = event.published_at
      ← FRED adapter:published_at = obs["date"]
        ← FRED 文件:date 是「觀測參考期間」… 等等,這不是發布日?!
```

**五月 CPI 的 `date` 是 `2026-05-01`,但 BLS 實際發布是六月中。** 舊 code 把參考期間當發布日,等於在量「五月一號那天的市場走勢」,跟「CPI 發布的市場反應」毫無關係 — 所有 FRED 事件的 outcome 標籤都是噪音。

這一個發現拉出一整串「測量層」問題,M9.6 一次修完:

| # | 問題 | 修法 |
|---|---|---|
| 1 | FRED 錨點 = 參考期,非發布日 | ALFRED vintage 模式拿真實發布日 |
| 2 | LLM 只看到指數水準(無資訊量)| payload 加 MoM/YoY/月增等 surprise 指標 |
| 3 | 模型只被問 24h,卻被 24h+7d 兩個視窗評分 | `direction_7d` 欄位,per-window 評分 |
| 4 | NEUTRAL ±0.5% 門檻對 7d 太緊 | 門檻按 √t 縮放:7d 用 ±1.5% |
| 5 | BULLISH+LOW 在評分規則下自相矛盾 | prompt 規則:預期在帶內 ⇒ 必須 NEUTRAL |
| 6 | confidence 尺度兩套(0.0 vs 0.5 = coin flip)| 統一 0.5 起跳 + 定錨段位 |
| 7 | accuracy 沒 baseline 對照 | `/accuracy` 回傳三種常數策略對齊率 + 校準分桶 |

口訣:「**先把尺修直(1-5),再把眼睛擦亮(6 + market state),最後才換更強的腦(gpt-5 + 多數決)**」。順序反過來 = 在錯的尺上優化,白燒 token。

## 9.6.2 Point-in-time 資料與 Look-ahead bias — 量化金融第一課

這是 M9.6 最重要的觀念,也是面試最能展現深度的地方。

#### 兩個長得很像但完全不同的日期

經濟數據有**兩個時間軸**:

- **Reference period(參考期間)**:這個數字描述的是哪段時間 — 「五月的 CPI」
- **Release date(發布日)**:市場第一次看到這個數字的時刻 — 六月中某天 08:30 ET

做 event study(事件研究:量測「事件發生後價格怎麼動」)時,**視窗必須錨在 release date** — 因為市場只能對「它知道的事」反應。錨在 reference period 就是在量真空。

#### 還有第三個陷阱:數據會被修訂(vintage)

CPI、NFP、GDP 都會在後續月份**修訂**。今天從 FRED 抓「三月 NFP」,拿到的是**修訂後的值**,不是市場當時看到的初值。如果用修訂值去復盤「市場對 NFP 的反應」,就引入了 **look-ahead bias(前視偏差)— 用了當時不存在的資訊**。

FRED 的解法叫 **ALFRED(ArchivaL FRED)**:每個觀測值保留所有歷史版本(vintage),每個 vintage 帶 `realtime_start/realtime_end` =「這個值是當時的現行值」的期間:

```python
# 一般模式:每個參考期一列,值 = 最新修訂
{"date": "2026-03-01", "value": "332.4"}

# vintage 模式(帶 realtime 範圍查詢):每個 (參考期, 版本) 一列
{"date": "2026-03-01", "value": "332.1", "realtime_start": "2026-04-10"}  # 初值!
{"date": "2026-03-01", "value": "332.4", "realtime_start": "2026-05-12"}  # 修訂
```

**第一個 vintage 的 `realtime_start` = 原始發布日**,它的 `value` = 市場當天看到的數字。一次查詢同時解決「錨點」和「初值」兩個問題:

（邊界條件:這個等式對『ALFRED 開始追蹤之後才發布的數據』成立 — 對 EventSense 只看近月宏觀事件正好涵蓋。對 ALFRED 上線日(各系列不同,常落在 1990s-2010s)之前的舊數據,最早 vintage 的 realtime_start 是『該系列進 ALFRED 的日期』而非當年真實發布日,此時不能拿來當錨點。實務上加一道防呆:若 realtime_start 早於系列已知的 ALFRED coverage start,標記為不可信、不開 event study。)

```python
def _first_releases(vintage_rows):
    best = {}  # ref_period -> (release_date, value)
    for obs in vintage_rows:
        ref, rt = obs["date"], obs["realtime_start"]
        if ref not in best or rt < best[ref][0]:   # 取最早的 vintage
            best[ref] = (rt, float(obs["value"]))
```

最後把 `published_at` 釘在發布日的 **08:30 ET**(CPI/NFP/GDP 都是 8:30 print,FRED 只給日期,時刻自己補)— 這讓 validator 的 baseline 自然落在「發布前一天收盤」、24h end 落在「發布當天收盤」,正好是 event study 要的 close-to-close 視窗。

#### 面試金句

> 「我在自己的專案踩過 look-ahead bias:把 FRED observation date 當發布日,所有宏觀事件的 outcome 都量錯天。修法是改用 ALFRED vintage 模式拿 point-in-time 初值和真實發布日。這個經驗讓我對任何金融資料管線都會先問:**這個欄位是『事情發生的時間』還是『市場知道的時間』?**」

## 9.6.3 Surprise vs Level — 市場定價的是預期差

修完錨點還有第二刀:prompt 裡 CPI 事件長這樣 — `CPI index level=320.321`。

**市場價格已經把「預期中的 CPI」算進去了。** 發布時動的不是水準,是**預期差(surprise)**:比共識高/低、比上月加速/減速。給 LLM 一個指數水準,等於什麼都沒給 — 它沒有 prior 序列,連「升還是降」都判斷不出來(這正是 M9 時代 FRED 預測 ≈ 擲硬幣的原因之一)。

修法:adapter 反正抓了整段 vintage 歷史,**用初值序列免費算出 headline 數字**:

| 系列 | 原始欄位 | 市場真正看的 headline |
|---|---|---|
| CPI(CPIAUCSL,指數水準)| 320.321 | **MoM %、YoY %**(`mom_pct: 0.47, yoy_pct: 4.26, prev_mom_pct: 0.64` → 「漲幅減速」一眼可見)|
| NFP(PAYEMS,就業人數水準)| 159,000 千人 | **月增千人**(差分!`change_thousands: +265` 才是新聞標題那個數字)|
| GDP(GDPC1,SAAR 水準)| 23,400 | **QoQ 年化 %**(`(v/prev)^4 - 1`)|

注意 NFP 那行:**「+265K jobs」是水準的一階差分** — 不知道這件事的人會把 159,000 千人直接餵給模型。財經資料的「headline 轉換」每個系列不一樣,要逐一查。

(共識預估 consensus estimate 沒有免費資料源,所以 surprise 先用「對自身趨勢的偏離」近似 — prompt v3 明確告訴模型:「`derived` 區塊裡的加速/減速就是訊號,水準不是」。)

## 9.6.4 Per-window 評分 + 波動的 √t 縮放

#### 問題:一個方向,兩把尺

Prompt 問模型「未來 **24 小時**的影響」,validator 卻拿同一個 `direction` 同時對 24h **和** 7d 評分。財報「先噴後跌」、FOMC「先跳後回」都是常態 — 24h 的衝擊方向和 7d 的漂移方向**本來就可以不同**,拿模型沒被問的問題扣它分,量出來的 accuracy 低估了模型。

完整判定規則(三方向對稱,門檻 t 按視窗取自 NEUTRAL_THRESHOLDS):
```python
def is_aligned(direction, ret, window):
    t = NEUTRAL_THRESHOLDS[window]   # 24h=0.005, 7d=0.015
    if direction == BULLISH: return ret >  t
    if direction == BEARISH: return ret < -t
    return abs(ret) <= t             # NEUTRAL: 落在帶內才算對
```
關鍵:NEUTRAL 是『區間命中』、BULLISH/BEARISH 是『單邊跨門檻』，所以 9.6.4 的 BULLISH+LOW 矛盾才會發生(LOW 預期 |move|<t,但 BULLISH 要 ret>+t,兩者不可能同時真)。這個函式是整章量尺的唯一真相來源。

修法三件套:
1. LLM schema + DB 加 `direction_7d`(nullable — 舊預測 fallback 到 `direction`,migration 不用 backfill)
2. validator 按視窗選方向
3. prompt 明確要求兩個 call 並警告「不要機械式複製」

#### 為什麼 7d 門檻是 1.5%?

NEUTRAL 的判定帶(±0.5%)在 24h 合理,但 SPY 一週動超過 0.5% 是常態 → 7d 的 NEUTRAL **幾乎自動必錯**、BULLISH 幾乎穩贏(指數長期上漂)。這不是模型問題,是門檻問題。

金融時間序列的基本性質:**報酬的標準差大約隨時間平方根成長**(σ_T ≈ σ_daily × √T,因為獨立增量的變異數相加)。24h ≈ 1 個交易時段、7d ≈ 5-9 個時段:

```
0.5% × √(7~9) ≈ 1.3% ~ 1.5%  → 取整 1.5%
```

```python
NEUTRAL_THRESHOLDS = {
    OutcomeWindow.H24: 0.005,
    OutcomeWindow.D7:  0.015,   # ≈ 0.5% × √t
}
```

不是精確校準(那要用 realized vol 動態算),是「讓每個視窗的三個方向都有合理勝率」的量級修正。

（√t 何時失準:推導前提是報酬增量 i.i.d.(變異數可加)。真實市場兩處違反 — (1) **波動聚集**:高波動日成群出現,7d 實際 σ 會比 √7×σ_daily 胖;(2) **序列自相關/均值回歸**:短期動能或反轉讓增量非獨立。所以 0.5%×√t≈1.5% 是『平靜期的量級』,FOMC/CPI 週要用 realized vol 動態算才準。這裡刻意只做量級修正,是因為門檻的目的是『讓三方向勝率不退化』,不是精確定價。)

#### 連帶抓到的邏輯矛盾:BULLISH + LOW

Prompt 定義 magnitude `LOW = 預期 |move| < 0.5%`;但 BULLISH 要 return **> +0.5%** 才 aligned。所以「BULLISH + LOW」翻譯成白話是「我預期它漲,但漲不到能讓我得分的程度」— **模型誠實 = 系統必judge它錯**。修法寫進 prompt:「預期落在帶內 ⇒ 該視窗必須出 NEUTRAL」。

> 教訓:**評分規則(loss function)和輸出選項(action space)要一起設計**,不然會存在「理性輸出必然失分」的角落。

## 9.6.5 Confidence calibration — 「說 70% 的時候,你有 70% 對嗎?」

#### 尺度先要一致

舊 prompt 寫 `confidence: 0.0 (coin flip) to 1.0`,schema 註解寫 `0.5 = coin flip`。兩套尺度混用 = confidence 欄位整體不可信 — 你不知道某筆 0.3 是「模型覺得會反向」還是「模型覺得略低於五五開」。v3 統一:

```
0.50      = 五五開,看不出 edge
0.55–0.65 = 弱訊號
0.65–0.80 = 完整證據鏈
> 0.80    = 只留給毫無懸念的大 surprise
不准低於 0.50(方向信心低於五五開 ⇒ 你該翻轉方向,而不是報低信心)
```

#### 校準(calibration)是什麼?

一個**校準好的**預測者:它說 70% 的那群預測,實際對 70%。量法是分桶:

```
/accuracy 回傳的 calibration 表:
bucket      total  aligned  rate
0.00-0.55     12      5     42%   ← 模型自己也說沒把握,確實接近五五
0.55-0.65     30     18     60%   ✓ 校準良好
0.65-0.75     25     14     56%   ← 過度自信(說 70% 只對 56%)
0.75-0.85      8      7     88%   (small n,先不下結論)
```

讀法:**rate ≈ bucket 中點 = 校準好;rate 一律低於中點 = 過度自信(LLM 通病)**。這張表還有第二個用途:如果各桶 rate 都一樣 → confidence 完全沒有資訊量,可以忽略它;如果有單調性 → 之後可以做「只交易高信心預測」的策略分析。

（嚴謹度補充:每桶 rate 是 Bernoulli 比例,標準誤 ≈ √(p(1-p)/n)。n=25、p≈0.6 時 SE≈0.10,95% CI 約 ±0.20 — 所以 0.65-0.75 桶『56% vs 中點 70%』其實落在誤差帶內,單月看不能斷言過度自信,要嘛跨月累積 n、要嘛只把『多桶一致、單調偏低』當證據。通則:**校準結論看趨勢(跨桶單調性)不看單桶單點**,n<30 的桶一律標註不下結論。)

## 9.6.6 Baseline — 沒有對照組的 accuracy 是行銷數字

「62% 準確率」聽起來不錯?要先問:**擲銅板的人拿幾分?**

市場有兩個結構性偏置讓 baseline 遠高於直覺的 33%(三分類):
1. **上漂(drift)**:股市長期往上,always-BULLISH 在 7d 視窗常有 55-60%
2. **帶寬設計**:±0.5% 帶內機率 ~40-50%(24h),always-NEUTRAL 也不差

所以 `/accuracy` 現在把**同一組 outcomes** 用三種常數策略重放:

```python
for name, direction in [("always_bullish", BULLISH), ("always_bearish", BEARISH), ("always_neutral", NEUTRAL)]:
    baselines[name] = sum(
        1 for r in rows if alignment.is_aligned(direction, r.ticker_return, r.window)
    ) / total
```

關鍵設計:baseline 用 `ticker_return` **就地重放**,不需要另存資料 — 因為 outcome 已經存了原始報酬,任何策略的對齊率都能事後重算。Dashboard hero 直接顯示 `BASELINES — ALWAYS-BULLISH 57% · ...`,**之後每個 prompt 改動有沒有真效果,看「超出 baseline 的幅度」而不是絕對值**。

> 這個觀念在 ML 叫 **skill score**:模型的價值 = 相對最廉價策略的增益。沒 baseline 的 accuracy 改善可能只是「那個月市場剛好漲」。

（regime 依賴的坑:baseline 用『同一組 outcomes』就地重放,已經消掉了『跨期不可比』的一半問題 — 模型和 baseline 吃完全相同的市場期間,所以 skill = 模型對齊率 − max(三個 baseline) 在該期內是公平對照。但仍要小心:always-bullish 的 baseline 高低本身隨 regime 漂,單月牛市時它可能 60%、模型 62%,skill 只有 2pt 且可能不顯著。通則:**skill 要『跨多個 regime 都為正』才算真 edge**,單期 skell 為正只證明『那期沒輸給最廉價策略』,不證明可遷移。)

## 9.6.7 Self-consistency 多數決 — 把抽樣方差變成訊號

LLM 同一個 prompt 跑三次,可能出三個不同方向 — 這叫**抽樣方差**(sampling variance)。單次呼叫等於從模型的信念分布抽一個樣本;預測任務裡這是雜訊。

（前提:這套統計只在 **temperature > 0** 時成立 — temperature=0 近似貪婪解碼,三次幾乎同一答案,多數決退化成單次。EventSense 用預設 temperature 讓三次是真正的獨立抽樣。N=3 是成本/方差的折衷:N 從 1→3 把多數決方差降最多的一段,再往上邊際遞減卻線性加成本,3x 已足夠把『單次吵架』轉成可讀的分歧訊號。注意『獨立』是近似 — 同 prompt 同模型的三次抽樣有共同偏誤,所以多數決能修掉抽樣雜訊、修不掉模型的系統性偏差,後者要靠 9.6.5 的 calibration 才看得出來。）

**Self-consistency**:跑 N 次獨立呼叫,對答案投票。為什麼有效:如果模型對方向有真實傾向(p > 0.5),多數決把「單次對的機率 p」放大成「多數對的機率 > p」(同二項分布的中位數集中效應);如果模型根本沒傾向(p ≈ 0.5),三次會分歧 — **而分歧本身就是資訊**。

EventSense 的實作細節(都有理由):

```python
direction  = mode(votes, tie_fallback="NEUTRAL")   # 平手 → NEUTRAL:三次抽樣吵架 = 沒有穩定信念 = 無方向
confidence = median(votes)                          # median 不被單次過度自信拉走
magnitude  = mode(votes, tie_fallback="MEDIUM")
reasoning  = 第一份「與多數方向一致」的 reasoning    # 不要拿少數派的理由配多數派的方向
只在 premium 路由(FOMC/CPI/NFP/GDP/財報)啟用      # 高權重事件才值得 3x 成本
少數呼叫才出現的 ticker 直接丟棄                     # 出現本身就沒過半 = 幻覺嫌疑
```

成本帳(跟使用者拍板過):多數決一個月多 ~$0.3。**整個系統成本大頭是 Railway 主機(~$12-18/月),LLM 占比 < 5%** — 在「最影響 accuracy 統計的事件」上,這是性價比最高的準確率手段。

## 9.6.8 把評分規則寫進 prompt — scoring-rule-aware prompting

Prompt v3 開頭就有一節 `HOW YOU ARE SCORED`:per-window 門檻、band 內 = NEUTRAL、24h/7d 分開評、base rates(「單日指數落在 ±0.5% 帶內約一半時間,routine 事件的 24h 預設是 NEUTRAL」)。

為什麼這很重要:**模型不知道 loss function,就會輸出與評分機制不相容的答案**(9.6.4 的 BULLISH+LOW 就是例子)。把 scoring rule 寫進 prompt 是**零成本的對齊** — 不用 fine-tune、不用 RLHF,直接告訴它遊戲規則。

另一個 v3 的反向操作:**把 v3.2 的「強制歷史類比」降級成 optional**。原因三個:(1) 強制類比讓模型把當下硬套進敘事框架,方向被類比牽著走;(2) 小模型的類比常是幻覺;(3) 模型 cutoff 之後的 regime 它根本不知道。v3 改成「真的高度相似才引用、一個子句、不得主導方向判斷 — **資料才是判斷基礎**」。

> 對照 9.5.5:M9.5 學到「強制模型引用歷史」,M9.6 學到「強制過頭會反噬」。Prompt engineering 不是一直加規則,是**校準規則的強度**。

還有一個配套:TRACK RECORD 區塊改餵**聚合統計**(「過去 60 天 MARKET BULLISH 24h:12/20」)而不是 50 筆舊預測全文 — **聚合回饋 > 原始記錄堆疊**,省 token 又讓模型真的能用來自我校準。

## 9.6.9 Postgres 鎖深度課(M9.6 之星)— idle in transaction 癱瘓全表

部署前最後一步,pytest 從 13 秒變成永久卡死。追查過程是這個 milestone 最值錢的故事。

#### 第一現場:pg_stat_activity

```sql
SELECT pid, state, now()-xact_start AS xact_age, wait_event_type, left(query,60)
FROM pg_stat_activity
WHERE datname='eventsense' AND state <> 'idle';
```

```
pid    state                xact_age   wait_event  query
13044  idle in transaction  00:49:06   Client      SELECT events.id FROM events WHERE status=...
13234  active               00:47:01   Lock        TRUNCATE TABLE events CASCADE
13242  active               00:46:26   Lock        SELECT events.id, events.source, ...
```

讀懂這三行需要三個觀念:

**觀念 1:SELECT 也上鎖。** 每個查詢都拿表級鎖,普通 SELECT 拿最弱的 `ACCESS SHARE` — 它不擋別的 SELECT/UPDATE,但**擋 `ACCESS EXCLUSIVE`**(TRUNCATE/DROP/某些 ALTER 需要的最強鎖)。

**觀念 2:鎖跟著 transaction 走,不是跟著 query。** Query 跑完鎖不會放,要等 transaction commit/rollback。`idle in transaction` = 「query 跑完了,transaction 開著,程式在做別的事」 — 鎖就這樣被抱著 49 分鐘。

**觀念 3:Postgres 的鎖等待是 FIFO 佇列。** TRUNCATE 排進佇列後,**所有更晚到的請求(包括無辜的 SELECT)都排在它後面** — 不是因為它們跟 SELECT 衝突,是因為佇列不准插隊(否則 TRUNCATE 會餓死)。結果:一條 idle 連線 → 擋 TRUNCATE → TRUNCATE 擋全世界,**一張表癱瘓**。

#### 鎖主是誰?自己的 analyzer

`analyze_pending()` 的流程:外層 session 跑 discovery SELECT 找候選 → 逐事件用獨立 transient session 處理。外層 session 跑完 SELECT 之後**沒有人去結束它的 transaction**,而 M9.6 的 self-consistency 讓一個批次(33 事件 × 3 次 gpt-5 呼叫)跑幾十分鐘 — 外層 transaction 就 idle 著橫跨整批。

（為什麼只修外層就夠:per-event transient session 是**短命**的 — 每個事件 open→寫入→commit→close 才幾秒,鎖隨即釋放,且任一時刻只有一個在用,不會堆成長 idle。真正的兇手只有那條橫跨整批、抱著 ACCESS SHARE 幾十分鐘的外層 discovery transaction。連線池上限(asyncpg/SQLAlchemy pool_size)要 ≥ 並發 transient session 數,但因為它們是序列處理、生命週期短,池壓力極小 — 所以一行 commit 就根治。)

修法一行:

```python
candidate_ids = await _candidate_event_ids(db, batch_size)
await db.commit()   # 唯讀 discovery 跑完立刻結束 transaction,別抱著鎖跑 LLM
```

> 通則:**「先查清單、再逐項長時間處理」的 pattern,查完清單就 commit。** 唯讀 transaction 的 commit 沒有副作用,只是放鎖。

#### 第二層:殺掉的程序沒死透

修完重跑還是卡 — `ps aux` 發現之前被「停掉」的 pytest 變成**孤兒程序**:停掉外層 shell 不會殺到子程序,孤兒抱著自己的 DB session 繼續演同一齣戲。清理要雙管齊下:

```bash
pkill -9 -f '.venv/bin/pytest'                      # 殺程序
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE datname='eventsense' AND pid <> pg_backend_pid();  # 斷殘存 session
```

#### 抓現行的工具:faulthandler

不知道卡在哪行?pytest 內建 faulthandler:

```bash
pytest -o faulthandler_timeout=35   # 卡超過 35 秒自動 dump 所有 thread 的 stack
```

這次 dump 直接顯示卡在 **fixture 的 TRUNCATE**(連測試本體都沒進去)— 一秒終結「是哪個測試壞了」的瞎猜。

#### 結構性教訓

Integration 測試和 dev 容器**共用同一顆 Postgres**,analyzer 長批次跑著時測試必卡。跑套件前 `docker compose stop analyzer worker beat backend`。(更乾淨的解法是測試用獨立 DB/schema — 記在未來改進。)

## 9.6.10 Savepoint — transaction 裡的「局部復原點」

Bug 審查抓到 event_writer 的資料遺失缺陷:

```python
# 舊 code(壞的)
for raw in raw_events:
    db.add(event)
    try:
        await db.flush()
    except IntegrityError:     # 撞 (source, external_id) 唯一鍵
        await db.rollback()    # ← 災難:回滾「整個 transaction」
        continue
    inserted += 1              # A、B 已計數,但 C 撞鍵時 A、B 也被回滾掉了
await db.commit()              # 沒東西可 commit → 事件默默遺失、計數虛報
```

`rollback()` 是 transaction 級的 — 它把這個 transaction 裡**所有**已 flush 未 commit 的變更全部退掉。要「只退這一筆」需要 **savepoint**(SQL 標準的 transaction 內標記點):

```python
# 新 code
try:
    async with db.begin_nested():   # SAVEPOINT
        db.add(event)
        await db.flush()
except IntegrityError:               # 自動 ROLLBACK TO SAVEPOINT — 只退這筆
    continue
inserted += 1
```

SQLAlchemy 的 `begin_nested()` 就是 savepoint 的包裝:成功 → `RELEASE SAVEPOINT`;例外 → `ROLLBACK TO SAVEPOINT`,前面的 flush 完好無損。

> 面試版本:「**批次寫入 + 預期內的唯一鍵衝突,標準解法是 per-item savepoint**,不是 session rollback。後者會默默吃掉同批已成功的資料,而且計數還是對的 — 最難發現的那種 bug。」

## 9.6.11 SQLAlchemy 泛用型別 vs 方言型別 + 一個 mypy 陷阱

Timeline 的 ticker 篩選要查「array 欄位包含某值」,連踩兩個小坑,都值得記:

**坑 1:`sa.ARRAY` 沒有 `.contains()`。** SQLAlchemy 的型別分兩層 — 泛用(`sqlalchemy.ARRAY`)和方言(`sqlalchemy.dialects.postgresql.ARRAY`)。`@>`(containment)是 Postgres 特有運算子,只有方言版有。Model 用泛用版時,改用標準 SQL 的 `= ANY()`:

```python
from sqlalchemy import any_
conditions.append(any_(Event.affected_tickers) == ticker.upper())
```

**坑 2:等號方向決定誰的 `__eq__` 被呼叫。** 寫成 `ticker.upper() == any_(...)` 時,Python 先呼叫**左運算元**(str)的 `__eq__` → mypy 推導回傳 `bool`,而不是 SQL 表達式 → type error。把 SQL 表達式放左邊,SQLAlchemy 的 `__eq__` 才會接手生成 `ColumnElement`。

> 運算子重載的語言通則:**混合型別運算式,讓「重載方」當左運算元**。(實際上 Python 有 `__req__` 反射機制所以 runtime 沒事,但型別檢查器看的是左邊。)

## 9.6.12 useInfiniteQuery — 「載更多」的 server state 模型

「看全部事件」的正解不是一次全載(表會無限長大),是**分頁累積**。TanStack Query 有專門的 hook:

```tsx
const events = useInfiniteQuery({
  queryKey: ["events", filters],            // filters 變 → 整個分頁堆疊重置,天然正確
  queryFn: ({ pageParam }) => api.listEvents(pageParam, 20, filters),
  initialPageParam: 1,
  getNextPageParam: (last) => {
    const { page, per_page, total } = last.meta;
    return page * per_page < total ? page + 1 : undefined;  // undefined = 沒有下一頁
  },
});
const all = events.data?.pages.flatMap(p => p.data) ?? [];
```

跟 `useQuery` 的差別:cache 形狀是 **page 陣列**(`data.pages`),`fetchNextPage()` 往後堆,`hasNextPage` 由 `getNextPageParam` 回傳值決定。配套的後端契約:**`total` 必須是「套用篩選後」的總數**,否則前端永遠以為還有下一頁。

篩選列的選項(有哪些 ticker/type 可選)用獨立端點 `/events/filters` 從 DB `SELECT DISTINCT` 算 — 加新公司、新事件類型**零前端改動**。

## 9.6.13 Tailwind v4 design tokens — 整站換皮只改一個檔

Bloomberg 終端機 UI 改版能一次換完三頁 + 14 個元件,靠的是把顏色全部收斂成 **semantic tokens**:

```css
/* globals.css — Tailwind v4 的 @theme 把 CSS 變數變成 utility class */
@theme {
  --color-term-bg: #0a0e14;      /* 近黑底 */
  --color-term-amber: #ffb02e;   /* 品牌 accent */
  --color-term-up: #2fd980;      /* 漲 */
  --color-term-down: #ff5c6c;    /* 跌 */
  --color-src-fred: #4cc3ff;     /* 每個資料源有身分色 */
}
```

之後元件寫 `bg-term-bg text-term-up border-term-border` — **語意命名(這是什麼)而不是外觀命名(這是什麼顏色)**。要再換主題,改 7 個變數,不用動幾百處 class。配套紀律:漲=綠/跌=紅/品牌=琥珀的語意在所有元件一致,包括 Recharts 的 `stroke`/`contentStyle`(chart library 不吃 Tailwind class,要手動同步 hex — 這是 token 集中的另一個理由:有一個唯一出處可以抄)。

順帶一個 Recharts 坑:bar 顏色用 `<Cell>` 指定時,tooltip 拿不到 item 顏色會 fallback **黑字** — 深色主題下隱形。要手動給 `itemStyle={{ color: ... }}`。

## 9.6.14 docker compose 的 env 讀取時機 — restart ≠ recreate

本機改了 `.env`(換 gpt-5)→ `docker compose restart` → analyzer 還在用 gpt-4o。為什麼?

| 指令 | 容器 | env_file 重讀? |
|---|---|---|
| `docker compose restart` | 同一個容器重啟 | ❌(env 在 **create** 時固定)|
| `docker compose up -d` | 設定變了就 **recreate** | ✅ |

`env_file` 的內容在容器**建立**時就燒進 container config;restart 只是重啟同一個容器。改 env 之後要 `up -d`(compose 會 diff 設定決定要不要 recreate)。連帶一提:程式碼是 volume mount 所以 restart 就能載新碼(celery 不會 hot reload,要重啟)— **「code 改了用 restart、env 改了用 up -d」**,兩件事的生效機制不同。

Railway 那邊也有對應版本:`railway variables --set` 之後要 redeploy 才生效;而 Railway 沒設的變數會 fallback 到程式碼預設值 — 所以改 `settings.py` 的 default 是「全環境生效」的捷徑(`DEFAULT_TICKERS` 就是這樣上線的)。

## 9.6.15 M9.6 速記表

| 主題 | 一句話 |
|---|---|
| Look-ahead bias | 復盤只能用「當時市場知道的資訊」— 初值不是修訂值、發布日不是參考期 |
| ALFRED vintage | FRED 的 point-in-time 模式;第一個 vintage 的 realtime_start = 真實發布日 |
| Surprise vs Level | 市場定價預期差;CPI 要 MoM/YoY、NFP 要月增(差分)、GDP 要年化 QoQ |
| Per-window 評分 | 24h 衝擊 ≠ 7d 漂移;一個方向兩把尺 = 結構性扣分 |
| √t 縮放 | 報酬波動 ∝ √時間;NEUTRAL 門檻 7d = 0.5% × √t ≈ 1.5% |
| Calibration | 說 70% 的那群要對 70%;分桶表診斷過度自信 |
| Baseline | accuracy 要對照 always-bullish 等常數策略;skill = 超出 baseline 的部分 |
| Self-consistency | N 次投票,平手→NEUTRAL(分歧=低信心);只在高權重事件開 |
| Scoring rule in prompt | 模型不知道 loss function 就會輸出必失分的答案;寫進 prompt 是零成本對齊 |
| idle in transaction | 鎖跟 transaction 走;discovery 查完立刻 commit |
| 鎖佇列 FIFO | 一條 idle 連線 → 擋 TRUNCATE → 擋所有後來者 → 全表癱瘓 |
| Savepoint | 批次寫入 + 預期衝突 = per-item `begin_nested()`,不是 session rollback |
| faulthandler | `pytest -o faulthandler_timeout=N` 卡死自動 dump stack |
| 泛用 vs 方言 ARRAY | `.contains()` 是 postgresql 方言的;泛用版用 `any_()`;SQL 表達式放等號左邊 |
| useInfiniteQuery | cache 是 page 堆疊;queryKey 含 filters 自動重置;total 要算篩選後 |
| Design tokens | 語意命名顏色集中一處;整站換皮 = 改幾個變數 |
| restart vs up -d | env 在 create 時固定;改 env 要 recreate |

## 9.6.16 面試講 M9.6 故事建議(5 分鐘版)

> 「系統上線後我做了一次全面 code review,發現一個顛覆性的問題:**宏觀事件的時間錨點從第一天就是錯的**。FRED API 的 observation date 是統計參考期間,不是發布日 — 五月 CPI 標的是五月一號,但 BLS 六月中才發布。我的 validator 拿這個日期開 24h/7d 視窗算市場反應,等於在量數據根本還沒公布的日子。所有宏觀事件的 accuracy 都是噪音。
>
> 修法是改用 FRED 的 ALFRED vintage 模式 — 它保留每個數據點的所有歷史版本,第一個版本的 realtime_start 就是真實發布日,而且值是市場當天看到的初值,不是後來的修訂值。這同時解掉了 look-ahead bias。我還順手把 payload 從『指數水準』升級成 MoM/YoY 這類 surprise 指標 — 因為市場定價的是預期差,不是水準。
>
> 接著我把整個評分層翻修了一遍:模型只被問 24 小時,卻被 24 小時和 7 天兩個視窗評分,所以我加了獨立的 7 天方向欄位;NEUTRAL 門檻按波動的 √t 縮放;accuracy 加上 always-bullish 這類常數策略 baseline — 因為股市上漂,沒有 baseline 的準確率是行銷數字。高權重事件再加上三次呼叫的多數決,平手就歸 NEUTRAL,因為抽樣分歧本身就是低信心的訊號。
>
> 過程中還踩了一個很好的 production 鎖問題:多數決讓 analyzer 批次變長,它的 discovery query 的 transaction 一直開著,idle in transaction 49 分鐘,擋住測試的 TRUNCATE,而 Postgres 鎖佇列是 FIFO,後面所有查詢跟著全卡 — 一條 idle 連線癱瘓整張表。修法一行:discovery 完立刻 commit。這件事讓我養成看 pg_stat_activity 先找 idle in transaction 的習慣。
>
> 資料層的收尾也有講究:錨點錯的 FRED 資料不可修復、必須清掉重抓,但其他來源錨點是對的,outcome 又都存了原始報酬 — 所以只需要一個 idempotent 腳本就地重算 aligned,不用重抓價格、不用重花 LLM 錢。**清資料的範圍等於不可修復的範圍**,這是我這次最大的心得之一。」

被追問時的彈藥:ALFRED realtime 機制細節(9.6.2)、√t 推導(9.6.4)、校準表怎麼讀(9.6.5)、多數決為什麼有效(9.6.7)、鎖佇列 FIFO 為什麼連 SELECT 都卡(9.6.9)、savepoint vs rollback(9.6.10)。

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
| **context_builder** | 對每個 event 組合「LLM 該看到的世界快照」 |
| **MARKET vs COMPANY prediction** | 一個 event 同時對大盤(SPY/QQQ)跟個股出方向 |
| **doc-wait** | analyzer 看 body 還沒下載完 → defer,不硬上 LLM |
| **raw return vs excess return** | 純 ticker 漲跌 vs 扣 SPY 後的 alpha — EventSense 翻案用 raw |
| **one-shot script** | DB data semantics 變了用的維護腳本,跟 alembic 互補 |
| **`ROW_NUMBER() OVER PARTITION`** | SQL dedup 經典寫法,partition 內保留 newest 砍其他 |
| **temporal anchor** | Prompt 強制 LLM 在 reasoning 裡 cite 一個過去同類事件 |
| **prior analysis as context** | 把同 ticker 最近 N 次 LLM 預測 + outcome 餵回 prompt |
| **indicators table** | 不是 event 但 LLM 該看到的 macro 環境數字(PE/CAPE/殖利率) |
| **LOOKBACK headroom** | 任何「最近 N 天」參數要留 deploy gap / backfill buffer |
| **Event study** | 量測「事件發生後價格怎麼動」的方法論;視窗必須錨在市場知道事件的時刻 |
| **Reference period vs release date** | 數據描述的期間 vs 市場第一次看到它的日子 — 錨錯 = 量真空 |
| **Look-ahead bias** | 復盤時用了當時不存在的資訊(修訂值、未發布數據)— 量化第一大忌 |
| **ALFRED / vintage** | FRED 的 point-in-time 模式;每個數據點保留所有歷史版本,首版 realtime_start = 真實發布日 |
| **Surprise vs Level** | 市場定價預期差不是水準;CPI 看 MoM/YoY、NFP 看月增(差分) |
| **√t 縮放** | 報酬波動 ∝ √時間 → NEUTRAL 門檻按視窗長度放大(24h ±0.5% / 7d ±1.5%) |
| **Calibration(校準)** | 說 70% 的那群預測實際對 70%;按 confidence 分桶驗 |
| **Baseline / skill score** | 模型價值 = 超出常數策略(always-bullish 等)的部分;沒 baseline 的 accuracy 是行銷數字 |
| **Self-consistency** | 同 prompt N 次獨立呼叫對答案投票;平手 = 模型沒有穩定信念 → NEUTRAL |
| **Scoring-rule-aware prompt** | 把評分規則(loss function)寫進 prompt,杜絕「理性輸出必失分」的角落 |
| **idle in transaction** | query 跑完但 transaction 沒關 — 鎖被抱著;Postgres 鎖問題頭號嫌犯 |
| **ACCESS SHARE / ACCESS EXCLUSIVE** | 最弱(SELECT)/ 最強(TRUNCATE)表級鎖;後者跟一切互斥 |
| **鎖佇列 FIFO** | 等鎖不能插隊 → 一個排隊的 TRUNCATE 會擋住所有後來的 SELECT |
| **Savepoint / `begin_nested()`** | transaction 內的局部復原點;批次寫入撞唯一鍵只退該筆 |
| **pg_stat_activity** | Postgres 連線/鎖診斷的第一站(state、xact_age、wait_event) |
| **faulthandler** | `pytest -o faulthandler_timeout=N` 卡死自動 dump 全 thread stack |
| **孤兒程序** | 殺外層 shell 殺不到子程序;清 DB 鎖要 pkill + pg_terminate_backend 雙管 |
| **泛用 vs 方言型別(SQLAlchemy)** | `sa.ARRAY` 沒有 `@>`;方言功能在 `dialects.postgresql`;泛用用 `any_()` |
| **useInfiniteQuery** | TanStack Query 的分頁累積 hook;cache 是 page 堆疊,queryKey 變即重置 |
| **Design token** | 語意命名的樣式變數(term-up = 漲色)集中一處;整站換皮改幾個變數 |
| **TICKER_INGEST_SINCE** | 晚加入 watchlist 的公司只從加入日開始追,不回抓沒價格可驗證的歷史 |
| **restart vs up -d** | docker compose 的 env_file 在 create 時固定;改 env 要 recreate 不是 restart |

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
  ✅ LLM context engineering — 改 input 比改 prompt 有用(M9.5)
  ✅ 金融的 alpha / excess return / SPY benchmark 概念
  ✅ 但你也學會了 metric design ≠ metric correctness(M9.5)
  ✅ React server / client component 二分
  ✅ TanStack Query 的 cache 策略
  ✅ CORS 的真正作用:放寬同源限制、讓正當跨域 fetch 讀得到回應(注意:**不防 CSRF**,那靠 SameSite cookie / CSRF token)
  ✅ CI 為什麼存在、Path filter 怎麼省 CI 分鐘
  ✅ 測試 coverage 真正意義 + 設多少合適
  ✅ Production 設計原則 — 降級服務 > 完全停服 / Defer ≠ Fail
  ✅ Production migration ≠ schema migration — data semantics 也要 script(M9.5)
  ✅ Title vs body — adapter 不該只存 metadata,要有 body 進 LLM(M9.5)
  ✅ 可觀測性三層 RED / 背景 / domain,Counter/Gauge/Histogram 怎麼選、跨 process 用 DB 當真相來源(M11)
  ✅ Prometheus pull 模型、histogram 怎麼估 p95、label cardinality 紀律(M11)
  ✅ IaaS:VPC/subnet 的 public-private 本質、SG vs NACL、Fargate vs EC2/Lambda/EKS(M13)
  ✅ Terraform desired-state、state remote+locking、for_each vs count、PaaS↔IaaS 成本 trade-off(M13)
```

更重要的是,你**踩過的坑**:
- M3 / M5 / M6:asyncpg loop binding(三次,刻骨銘心)
- M3 / M4 / M5 / M11:Docker anonymous volume gotcha(M11 又咬一次 — 改 pyproject 後 image rebuild 了,但 `/app/.venv` anon volume 沿用舊 venv,要 `--renew-anon-volumes` 才載到新依賴)
- M5:race condition + 第一次修法錯誤的故事
- M6:silent fake data 0% return 的 must_be_after 修法
- M8:bool → float cast in PG
- M9.5:M6 學的 excess-return 在這個系統反而是雜訊,改 raw-return 才對
- M9.5:LLM 預測 SEC 0% 不是 model 爛,是沒餵 body
- M9.5:SEC LOOKBACK 14 天上線時夠 — 但沒考慮 deploy gap,改 60 才安全
- M9.5:改 alignment 邏輯之後 production 舊 outcomes 還在用舊邏輯,要寫 purge script
- M11:domain counter 在 Celery worker increment、API process 看不到 — 跨 process 改用 DB 當真相來源
- M11:`rate(...[5m])` 剛啟動/無流量時 NO DATA(rate 需窗內 ≥2 sample)— 不是壞了
- M13:RDS 密碼字元要排除 `: @ / ? # &`,否則組進 `DATABASE_URL` 會被切壞
- M13:`for_each` 不用 `count` — count 用索引定址,中間刪一個會讓後面全位移觸發重建

**這些故事就是面試講出來能贏的東西**。

---

# Part 12:Milestone 11 — Observability(Prometheus + Grafana)

> 這節寫給「系統會跑、但你不知道它『現在』好不好」的你。M9–M9.8 把功能做完;M11 是裝上儀表板,把健康、流量、準確率、花費變成看得見的曲線。

## 12.1 三層 metrics:RED / 背景 / 業務

可觀測性不是「裝個 Prometheus」就好,是想清楚**你要回答哪些問題**,再決定量什麼:

- **HTTP(RED metrics:Rate / Errors / Duration)** — 「API 現在被打多兇、錯多少、慢不慢?」用 `prometheus-fastapi-instrumentator` 掛 ASGI middleware 自動產生,per-(method, handler, status) 的 count + latency histogram。RED 是 service 層的通用三件套,任何 HTTP 服務都該有。
- **背景 pipeline(Celery)** — 「fetch/analyze/validate 的 task 在動嗎、有沒有在 fail?」Celery 原生不吐 Prometheus,用 `celery-exporter` 聽 broker 的 task 事件流。worker 要加 `-E`,celery conf 開 `worker_send_task_events`。
- **業務狀態(domain)** — 「事件漏斗卡在哪、預測準不準、今天 LLM 花多少?」這層是 EventSense 獨有的,別人抄不走,也是面試最能展現「你懂自己系統」的地方。

**面試點**:能講出「我先列要回答的問題,再反推 metric」而不是「我裝了 Prometheus」,層級差很多。

## 12.2 跨 process 的 metric 怎麼聚合?——別 increment,去查真相來源

最違反直覺的一課。直覺做法:在分析完一個事件時 `ANALYZED_COUNTER.inc()`。問題:analyzer 跑在 **Celery worker**,跟服務 `/metrics` 的 **FastAPI process** 是兩個 process。worker 裡 increment 的 counter,API process 的 registry 根本沒有。

多 process 聚合 Prometheus 有正規解(`multiprocess` 模式 + 共享目錄、或 pushgateway),但都有維運成本。EventSense 的取巧:**domain gauge 在 scrape 當下直接查 Postgres**。DB 是每個 process 本來就都同意的那一份狀態——繞過聚合問題本身。代價是每次 scrape 幾條 aggregate query,用 **10s TTL 快取**壓住(Prometheus 預設 15s scrape,等於每次都打 DB 也還好,但 TTL 讓多個 scraper / 手動 curl 不會疊加)。

**可轉移觀念**:跨 process 的計數,與其想辦法把 counter 同步過來,不如問「有沒有一個雙方都已經同意的真相來源可以現查?」——通常有(DB、object store、外部 API)。

## 12.3 `/metrics` 為什麼要自己手寫成 async

instrumentator 的 `.expose()` 註冊的是同步 route。但 domain gauge 要 `await` 一個 async DB 查詢才能更新。解法:只用 `.instrument(app)` 掛 middleware(HTTP metrics 進預設 registry),`/metrics` route 自己定義成 `async def`,先 `await refresh_domain_metrics()` 再 `generate_latest()`。**library 的方便函式擋路時,降一層用它的零件自己組**。

## 12.4 metrics 端點絕不能 500

`refresh_domain_metrics` 吞掉所有 DB 例外。為什麼?DB 短暫不可達時,如果 `/metrics` 跟著 500,Prometheus 不只記一次 scrape failure,還**連帶抓不到 HTTP metrics**(那些根本不需要 DB)。寧可回「舊但合法」的 gauge 值、讓 HTTP 層繼續流。**監控系統自己要比被監控的系統更耐操**。

## 12.5 驗證的紀律:不花錢也要看到真資料

驗 M11 時起了 worker+beat 讓真實 task 流進 exporter,但**刻意不起 analyzer**——因為 analyzer 會打 OpenAI(本機跟 prod 同一把 key,等於雙倍花費)。結果:`analyze_pending_task` 在 exporter 看得到 `sent` 但沒有 `succeeded`(沒人消費),fetcher(免費 API)正常跑出 `succeeded`。**既驗證了 Celery metrics 鏈路、又零 LLM 花費**——可觀測性本身幫你確認了「錢沒亂花」。

## 12.6 Prometheus 的四種 metric type(被問倒高發區)

面試最常見的第一個追問:「你用哪種 metric type、為什麼?」答不出 Counter/Gauge/Histogram/Summary 的差別會很尷尬。

| Type | 語意 | 怎麼查 | EventSense 用在哪 |
|---|---|---|---|
| **Counter** | 只增不減(重啟歸零) | `rate()` / `increase()` | HTTP 請求數、Celery `task_succeeded_total` |
| **Gauge** | 可上可下的瞬時值 | 直接讀 | domain 全部(事件數、準確率、今日花費)、in-progress 請求數 |
| **Histogram** | 觀測值丟進預設 bucket(累積 counter)+ `_sum` + `_count` | `histogram_quantile()` | HTTP latency |
| **Summary** | client 端先算好 quantile | 直接讀 quantile | 沒用(原因見下) |

**為什麼 domain 用 Gauge?** 它們是「現在的狀態量」——事件總數、準確率比例、今日累計花費,都可上可下、隨時讀當下值。

**為什麼 latency 用 Histogram 不用 Summary?** Summary 在 client(每個 app 實例)端就把 p95 算死了,**不能跨實例聚合**(兩個實例各自的 p95 沒辦法合成整體 p95)。Histogram 只在 client 端把觀測丟進 bucket(便宜),真正的 quantile 在 Prometheus query 端算——所以多實例、多 task 可以 `sum by (le)` 聚合後再求 quantile。分散式系統幾乎一律選 Histogram。

## 12.7 Histogram 怎麼從 bucket「估」出 p95

這題會被鑽。`http_request_duration_seconds_bucket{le="0.1"}` 的值是「延遲 ≤ 0.1s 的觀測**累積**數」——是 cumulative:`le="0.25"` 的 bucket 含 `le="0.1"` 的所有觀測。

```promql
histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))
```

步驟:① 對每個 bucket 算 `rate`(每秒落入率)→ ② 按 `le` 聚合(跨 handler/實例)→ ③ 找第 95 百分位落在哪兩個 bucket 邊界之間,做**線性內插**。

**關鍵限制:p95 是估計值,精度由 bucket 邊界決定。** 如果 p95 落在 `le=0.5` 與 `le=1.0` 之間,內插假設這區間內均勻分佈;真實分佈不均就有誤差。極端例子:所有觀測都擠進同一個大 bucket,quantile 會爛掉。instrumentator 的預設 bucket(覆蓋 ms 到數秒)對 web latency 夠用,但**自訂服務要按你的延遲分佈調 bucket**。

**為什麼不直接看 avg?** 平均會被大量快速請求稀釋、被尾巴拉歪——p95/p99 才看得到「最慢那 5%/1% 的使用者體驗」,也就是 SLO 真正在乎的尾延遲。

## 12.8 Pull 模型 + 為什麼 Counter 一定要配 `rate()`

**Prometheus 是 pull(拉),不是 push。** 它定時去 scrape 每個 target 的 `/metrics`。好處:① target 健康度天生可見(scrape 失敗 = `up=0`,不需要額外 heartbeat);② app 不需要知道 Prometheus 在哪;③ service discovery 容易。只有短命 job(cron/batch,還沒被 scrape 就結束了)才需要 push,走 pushgateway。

**Counter 直接畫沒意義。** 它只增、且重啟歸零,畫出來是條一直往上的累計線。要看「每秒發生幾次」必須用 `rate()`/`increase()` 取區間斜率。`rate()` 還會自動偵測 counter reset(看到值下降就當作重啟、補正),所以重啟不會在圖上戳出假尖刺。

**`rate(...[5m])` 為什麼有時 NO DATA?** rate 需要窗內 **≥2 個 sample**。剛啟動、或最近 5 分鐘完全沒流量時,可能算不出來或為 0——我驗 M11 時 http rate 一開始就是 NO DATA,打一波流量等兩次 scrape 後才出 `0.16`。窗的取捨:窗大→平滑但反應鈍(適合 alert,少假警報);窗小→靈敏但抖。dashboard 用 5m 折衷。

## 12.9 Label cardinality 與 TTL 快取的 async 安全

**每一個 label 值的組合 = 一條獨立 time series**,Prometheus 的記憶體/磁碟跟 series 數成正比。所以**高基數 label 會炸掉**:`user_id`、`event_id`、原始 URL、timestamp 這種無界值絕對不能當 label。

我的 label 全部有界:`source`(~6)、`status`(~5)、`window`(2)、HTTP 的 `handler`/`method`/`status`(路由數有限)。**故意不把 `event_id` 放進 metric**——要查單筆明細是 DB/API 的事,不是 metric 的事。這條紀律面試很加分。

**`EVENTS.clear()` 的必要性**:Gauge 的 label set 是「黏」的——某個 `(source, status)` 組合出現過一次,就會一直留在 registry。如果之後該狀態清空(例如 `FAILED` 歸零),不 clear 會殘留一個過期的舊值。每次 refresh 先 `clear()` 再重設 = 永遠反映當下真實的 label set。代價是 clear→set 之間有極短空窗若剛好被 scrape 會少幾條,可接受。

**TTL 快取為什麼不用 lock?** `_last_refresh_at` 是 module global,但 `refresh_domain_metrics` 跑在 asyncio 單執行緒事件迴圈裡,沒有真正的平行寫入。最壞情況:兩個併發 scrape 同時看到 TTL 過期、都去查一次 DB——多刷一次而已,不會壞資料。「多查一次」的代價遠小於上 lock 的複雜度,所以不上。

## 12.10 面試講 M11 故事建議(3 分鐘版)

> 「M11 我加了三層可觀測性:HTTP 的 RED metrics 用 instrumentator 自動產;Celery 背景 pipeline 用 celery-exporter 聽 broker 事件;最有價值的是 domain 層——事件漏斗、各時間窗的方向準確率、今日 LLM 花費 vs 上限。
>
> 最有意思的決策是 domain metrics 怎麼跨 process 聚合:分析跑在 Celery worker、metrics 由 API process 提供,counter 同步很麻煩。我改成 scrape 當下直接查 Postgres——DB 是兩個 process 本來就都同意的真相來源,直接繞過聚合問題,再用 10s TTL 快取壓 DB 負載。
>
> 全套跑在 docker-compose 的 profile 裡,Grafana datasource + dashboard 自動 provision,零雲端成本。」

---

# Part 13:Milestone 13 — AWS Infrastructure as Code(Terraform)

> 這節接 [Part 9 的「我們 M9 選 PaaS 的理由」](#我們-m9-選-paasrailway--vercel的理由)。M9 用 Railway 快速上線證明系統能用;M13 把同一套系統寫成 AWS 上的 Terraform——履歷上 PaaS + IaaS 雙打。

## 13.1 一張 map 打四個 service:把「重複」變成「資料」

Railway 上四個 service(backend + worker + analyzer + beat)共用一份 Dockerfile,只差 start command。搬到 ECS 最笨的寫法是四段 copy-paste 的 task definition + service。

漂亮的寫法:一張 `local.services` map(每個 key 帶 `command` / cpu / memory / `attach_lb`),用 `for_each` 同時驅動 task definition、service、log group;只有 `backend` 要掛 ALB,用 `dynamic "load_balancer"` 條件式產生那個 block。**加一隻 service 或改大小變成改一行資料,不是改四段程式**。這也是面試展現 Terraform 熟練度的點:`for_each` + `dynamic` + `merge()` 條件欄位。

## 13.2 兩個 IAM role 的分工(execution vs task)

ECS 慣例兩個 role,新手常搞混:
- **execution role** — ECS *agent* 用的,負責「把容器**啟動起來**」:拉 ECR image、讀 Secrets、寫 CloudWatch log。
- **task role** — *應用程式碼*跑起來後的身分。EventSense 自己不呼叫任何 AWS API,所以這個 role **故意留空**——least privilege 的預設就是「什麼都不給」。

## 13.3 Secrets 注入:相對 Railway 的具體安全升級

Railway 的機敏值是 dashboard 上的明文 env var。AWS 版全進 **Secrets Manager**,透過 task definition 的 `secrets` block 用 `valueFrom = secret ARN` 注入——容器 runtime 收到的是 env,但值**不出現在 task def JSON、ECS console、CloudWatch**。而且 `DATABASE_URL` / `REDIS_URL` 是在 Terraform 內用 RDS / ElastiCache 的屬性**組出來**的,不是手抄(一個小坑:DB 密碼要排除 `: @ / ? # &` 這些有 URL 意義的字元,免得組出來的連線字串被切壞)。

## 13.4 成本就是 trade-off 本身:~$15 vs ~$150

同一套 workload:

| | Railway(PaaS) | AWS(IaaS) |
|---|---:|---:|
| 月成本 | ~$15 | **~$150** |
| 大頭 | 一口價 | Fargate 24/7 ~$67 + NAT ~$33 + ALB ~$18 |

**約 10 倍。搬上 AWS 不是為了省錢**——是換 VPC 隔離、IAM、multi-AZ 選項、水平擴展、「infra 即可審查的程式碼」,這些 PaaS 幫你抽象掉了。誠實的結論:side-project 成本上 PaaS 完勝;AWS 版的價值是**展示能力**,以及當隔離 / 規模真的需要時已經 ready。面試敢把這個數字講出來、並說清楚「為什麼還是值得學/做」,比假裝 AWS 比較省更有說服力。

## 13.5 M13 為什麼不 apply

照 milestone 切法:M13 = IaC 寫對 + `terraform validate` 過;M14 才是 `apply` + 資料遷移 + DNS cutover。不 apply = 不開資源 = **$0**。沒有 AWS 憑證時,`terraform validate`(語法 / 型別 / 引用正確性)是可達的最高驗證標準;`plan` / `apply` 要憑證 + 取消註解 S3 backend。**「能 validate 的 IaC」本身就是一個可交付、可審查的成果**,不需要真的開帳單才算數。

## 13.6 刻意精簡 ≠ 不會:把 prod-hardening 列成 backlog

Demo 版單 AZ、單一 NAT、只有 HTTP listener、無 autoscaling。但 README 把每一項「為什麼省 + 怎麼補」列清楚(multi_az、每 AZ 一個 NAT、ACM/443、VPC endpoints 省 NAT 流量費、Fargate Spot)。**面試官最愛問「這個 production-ready 嗎?」——答案不是「是」或「不是」,是「這些我刻意簡化、各自的 trade-off 跟補法是這樣」**。展示你知道差距在哪,比假裝沒差距強。

## 13.7 AWS 運算光譜:為什麼是 Fargate(不是 EC2 / Lambda / EKS)

「為什麼選 Fargate?」幾乎必問。要答得出整條光譜的 trade-off:

| 選項 | 你要管什麼 | 適合 | 為何 EventSense 不選 |
|---|---|---|---|
| **EC2** | VM(OS patch、容量、scaling) | 要最大控制 | 維運最重,殺雞用牛刀 |
| **ECS on EC2** | 容器編排,但 node 還是你的 EC2 | 已有 EC2 機隊要塞容器 | 還要管 cluster 容量 |
| **Fargate**(選這) | 只給 task 的 cpu/memory | 「我只想關心容器」 | — |
| **Lambda** | 純函式,≤15min,冷啟動 | event-driven、短任務 | uvicorn + celery 是**長駐**服務,不適合 |
| **EKS(k8s)** | k8s control plane + 生態 | 大規模、需要 k8s 排程 | control plane ~$73/月 + 學習曲線,四個服務不值得 |

**Fargate 的本質**:serverless 容器——你不碰底層主機,按 task 用量計費。心智模型剛好對應 Railway「我只關心容器、別讓我管機器」。代價就是帳單上那 ~$67:Fargate 單位運算成本比自己管 EC2 貴,你付的是「不用管主機」。

## 13.8 VPC 網路基礎(public/private 的本質 + SG vs NACL)

**subnet 的 public / private 不是一個屬性,是路由決定的。** route table 裡:

- `0.0.0.0/0 → IGW(internet gateway)` ⇒ 這個 subnet 是 **public**(雙向對外)。
- `0.0.0.0/0 → NAT gateway` ⇒ **private**(只能出、不能被進)。

**NAT 在幹嘛**:讓 private subnet 裡的 ECS task 能**主動出去**(拉 ECR image、打 OpenAI/FRED/SEC),但外面無法主動連進來(SNAT,只放行回程)。NAT 自己坐在 public subnet、掛 EIP。

**為什麼 ECS/RDS/Redis 全放 private**:不給 public IP,網際網路打不到它們,唯一入口是 public subnet 裡的 ALB。這是縱深防禦——資料層和運算層對外完全隱形。

**awsvpc 模式 + `target_type=ip`**:每個 Fargate task 拿自己的 **ENI(彈性網卡)+ 私有 IP**。所以 ALB target group 註冊的是 **task 的 IP**,不是 EC2 instance id(Fargate 根本沒有你能註冊的 instance)。這就是 `target_type = "ip"` 的原因。

**SG vs NACL(經典考題)**:

| | Security Group | Network ACL |
|---|---|---|
| 綁在 | ENI(實例層) | subnet |
| 狀態 | **stateful**(放行出去的回程自動通) | **stateless**(進、出要各自開) |
| 規則 | 只能 allow | allow + **deny** |

我用 **SG 鏈**(SG 互相引用:ALB-SG → ECS-SG → RDS-SG)做 least privilege——每層只收前一層的 SG,不寫死 IP。NACL 留預設。stateful 是關鍵:ECS task 打 OpenAI 時不用為「回應封包」另開 inbound 規則,SG 自動記得這條連線。

## 13.9 Terraform 核心模型(state / plan-apply / for_each vs count)

**宣告式 desired state,不是命令式腳本。** 你描述「基礎設施該長怎樣」,Terraform 比對「現在長怎樣(記在 state)」與目標,自己算出最小變更集。你不寫「先建 VPC 再建 subnet」,你寫結果,依賴關係 Terraform 從資源引用推出來。

**三個動詞**:`validate`(只查設定本身:語法/型別/引用,不連雲、不需憑證)→ `plan`(連雲算 diff、給你看、不動真資源)→ `apply`(執行 diff)。M13 我做到 validate;plan/apply 是 M14。

**state file 為什麼要 remote(S3)+ locking(DynamoDB)**:state 是 Terraform 記住「我管的資源 ↔ 真實 AWS ID」的對照表。① 多人協作時各自本機 state 會打架 → S3 存共享狀態;② 兩人同時 `apply` 會把 state 寫爛 → DynamoDB 做分散式鎖,一次只准一個 apply;③ state 可能含明文 secret(例如 DB 密碼)→ S3 加密 + IAM 權限控管。這就是 `versions.tf` 裡那段註解掉的 S3 backend 的意義。

**`for_each` vs `count`(為什麼四個服務用 for_each)**:`count` 用**索引**定址(`svc[0]`、`svc[1]`)——中間刪掉一個,後面全部位移,Terraform 會以為要「重建一票資源」。`for_each` 用**穩定的 key** 定址(`svc["worker"]`)——增刪某個 key 不影響其他。所以一組異質資源幾乎一律該用 for_each。我的 `local.services` map 正是這個 pattern。

## 13.10 ECS 滾動部署 + ALB 健康檢查怎麼接

「你怎麼零停機部署?」的答案在這。改 task definition 後,ECS service 預設做 **rolling update**:

1. 起新版 task → 等它通過 ALB target group 的 health check(打 `/api/v1/health`)。
2. 健康後註冊進 target group、開始分流量。
3. 把舊 task 從 target group 排掉(deregister)、等連線排空、再終止。
4. `minimumHealthyPercent` / `maximumPercent` 控制過程中保留多少容量。

**`health_check_grace_period_seconds = 60`(只給 backend)**:新 backend task 啟動時要先跑 `alembic upgrade head` 再開 uvicorn,給它 60 秒寬限期,別一啟動就被 health check 判死、陷入「啟動→被殺→重啟」無限迴圈。

**ALB health check 的遲滯**:`healthy_threshold=2`(連兩次過才進流量)、`unhealthy_threshold=3`(連三次掛才排除),配 `interval=30s`——避免單次抖動就誤判。這直接呼應我在 Part 9 寫的 liveness/readiness 設計:ALB 打便宜、不碰 DB 的 `/health`,跟 Railway/Dockerfile HEALTHCHECK 同一套紀律,沒有為了上 AWS 重寫。

## 13.11 Secrets Manager vs SSM Parameter Store

兩者都能存 secret 並注入 ECS task,差別是面試延伸題:

| | Secrets Manager(我選的) | SSM Parameter Store(SecureString) |
|---|---|---|
| 自動輪替 rotation | 有(內建 Lambda) | 無 |
| 成本 | 每 secret ~$0.40/月 + API 費 | standard tier **免費** |
| 跨區複製 | 有 | 無 |

我選 Secrets Manager 是為了示範「正規 secret 管理 + 具備 rotation 能力」;但**如果成本敏感,SSM SecureString 是免費替代**,對這種規模其實夠用。能講出這個取捨(而不是「我就用了 Secrets Manager」)就贏一截。注入機制兩者一樣:task definition 的 `secrets` block 用 `valueFrom = ARN`,值不落進 task def JSON。

## 13.12 面試講 M13 故事建議(3 分鐘版)

> 「M9 我選 Railway(PaaS)快速上線;M13 我用 Terraform 把同一套系統寫成 AWS IaC,展示 IaaS 能力。核心是一張 service map 配 `for_each` 打出四個 ECS Fargate service——對應 Railway 共用一份 image、靠 command 區分的模型,只有 backend 用 `dynamic` block 掛 ALB。網路手刻 VPC(2 AZ、private subnet、SG 層層只收前一層),secrets 走 Secrets Manager 注入,比 Railway 的明文 env 升級。
>
> 我刻意只 `validate` 不 apply——建資源是 M14。最值得講的是成本:同一套 workload Railway ~$15、AWS ~$150,約 10 倍。搬 AWS 不是為了省錢,是換隔離、IAM、擴展性跟 infra-as-code。side-project 我會留在 Railway;AWS 版是證明我兩邊都能做、而且知道什麼時候該換。」
