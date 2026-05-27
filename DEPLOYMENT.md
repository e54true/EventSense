# EventSense — Production Deployment Runbook

> 把 EventSense 從你的筆電部署到網路上,任何人都能打開。
>
> **架構**:Backend(4 個 services)→ **Railway**;Frontend → **Vercel**;Database & Redis 用 Railway addon。
>
> **時間預估**:第一次跑大概 60-90 分鐘(註冊 + 配置 + 等部署 + 排除小坑)。

---

## 0. 部署前 checklist

| 項目 | 狀態 |
|---|---|
| OpenAI API key — **revoke 舊的、產一把新的** | ⚠️ 一定要做! |
| FRED API key(免費) | 從 https://fred.stlouisfed.org/docs/api/api_key.html |
| GitHub repo 已 push 到 main | ✅ EventSense 已經是 |
| Railway 帳號(免費 trial) | ⏳ 你來辦 |
| Vercel 帳號(免費) | ⏳ 你來辦 |
| Email(SEC User-Agent 用) | 你的 Gmail 就行 |

> **🔥 在做任何事之前**:打開 https://platform.openai.com/api-keys → 找到那把貼過在 chat 的 key → Revoke → 建新一把(複製出來但**這次別貼到任何 chat / IM**,直接 paste 進 Railway UI)。

---

## 1. Railway 帳號 + 專案

### 1.1 註冊

1. 開 https://railway.com
2. 用 GitHub 登入(這樣 Railway 能直接 access 你的 repo)
3. 你會拿到免費 trial credit($5 / 月免費,EventSense 整套大概一個月用 $1-3)

### 1.2 建立 project

1. 右上角 **New Project**
2. 選 **Deploy from GitHub repo**
3. 授權 Railway 看你的 GitHub
4. 選 `e54true/EventSense`

Railway 會建立一個 project。

---

## 2. Railway 加 Database + Redis Addon

兩個 plugin:

### 2.1 PostgreSQL
1. 在 project 內 → 右上 **+ New** → **Database** → **Add PostgreSQL**
2. 等 ~30 秒它 provision 完
3. 點開 Postgres service → **Variables** tab → 記下這些(Railway 自動產的):
   - `DATABASE_URL`
   - `PGUSER` / `PGPASSWORD` / `PGHOST` / `PGPORT` / `PGDATABASE`

### 2.2 Redis
1. 同樣 **+ New** → **Database** → **Add Redis**
2. 等 provision
3. 記下 `REDIS_URL`

---

## 3. 部署 backend 4 個 services

EventSense backend 有 4 個 process:**backend / worker / analyzer / beat**。

我們的 strategy:**4 個 services 共用同一個 Dockerfile**,只是 start command 不同。

### 3.1 第一個 service:`backend`(FastAPI API)

1. **+ New** → **Empty Service** → 命名為 `backend`
2. **Settings** tab:
   - **Source** → connect 到 GitHub repo,Branch = `main`
   - **Root Directory** → `backend`(只觀察 backend 目錄改動)
   - **Build** → Dockerfile path = `backend/Dockerfile`
   - **Deploy** → Start Command:
     ```
     alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
     ```
   - **Healthcheck Path** = `/api/v1/health`
3. **Variables** tab(下面 §4 完整清單)
4. **Networking** → 點 **Generate Domain**(會給你類似 `eventsense-backend-production.up.railway.app` 的 URL)→ 記下這個 URL
5. **Deploy** 按鈕(右上)→ 等 build + deploy,~3 分鐘

### 3.2 第二個 service:`worker`

1. **+ New** → **Empty Service** → 命名 `worker`
2. **Settings**:
   - **Source** → 同一個 repo,branch `main`,root `backend`
   - **Build** → 同 Dockerfile
   - **Deploy** → Start Command:
     ```
     celery -A app.workers.celery_app worker --loglevel=info -Q fetch_queue,validate_queue --concurrency=4
     ```
   - **不**用設 Healthcheck Path(worker 沒 HTTP)
3. **Variables**(同 backend,看 §4)
4. Deploy

### 3.3 第三個 service:`analyzer`

跟 worker 一樣,但 Start Command:
```
celery -A app.workers.celery_app worker --loglevel=info -Q analyze_queue --concurrency=2
```

### 3.4 第四個 service:`beat`

Start Command:
```
celery -A app.workers.celery_app beat --loglevel=info
```

⚠️ **Beat 一定只能 1 replica**(多 replica 會 double-enqueue)。Railway 預設就是 1,但 **Settings → Resources → Replicas 確認是 1**。

---

## 4. Backend 4 個 services 共用的 env vars

每個 service 的 **Variables** tab 都要設這些(用 Railway 的 reference 語法 `${{Postgres.PGUSER}}` 等),或複製貼上:

```
ENVIRONMENT=production

# Postgres — 用 Railway reference 語法引用 Postgres addon
DATABASE_URL=postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}

# Redis
REDIS_URL=${{Redis.REDIS_URL}}

# External APIs
FRED_API_KEY=<把你的 FRED key 貼這>
SEC_USER_AGENT=EventSense <your-email>@gmail.com

# OpenAI — 用「新」revoke 後的 key
OPENAI_API_KEY=sk-proj-<NEW_KEY_HERE>
LLM_DAILY_COST_CAP_USD=1.0
LLM_DEFAULT_MODEL=gpt-4o-mini
LLM_PREMIUM_MODEL=gpt-4o

# Watchlist
DEFAULT_TICKERS=NVDA,TSLA,AAPL,MSFT,GOOGL,META,AMZN,SPY,QQQ
```

**省事招**:在 Railway 設定一個共用 env group → 4 個 services 都引用它,改 key 一次改全部生效。

> **`DATABASE_URL` 為什麼要 `postgresql+asyncpg://` 不是 `postgresql://`?**
> 因為我們用 SQLAlchemy async + asyncpg driver,SQLAlchemy 用 URL scheme 決定 driver。Railway 預設給 `postgresql://`(同步 driver),要手動加 `+asyncpg`。

---

## 5. 確認 backend 跑起來

1. 等 4 個 services 都顯示 **Deployed** / 綠燈
2. 開 backend 的 public URL:
   ```
   https://eventsense-backend-production.up.railway.app/api/v1/health
   ```
   應該回:`{"status":"ok","uptime_seconds":42.3}`
3. 試 readiness(會打 DB):
   ```
   https://.../api/v1/health/ready
   ```
   應該回:`{"status":"ok","uptime_seconds":...,"database":"ok"}`
4. 試 events list:
   ```
   https://.../api/v1/events
   ```
   應該回空 list(production DB 是空的,beat 還沒跑、worker 才剛啟動)
5. **看 worker / analyzer / beat 的 Logs tab** → 應該看到 Celery 啟動訊息

### 第一次手動 trigger fetch 看看

打開 Railway 的 worker service → **Logs** → 等到 `celery@... ready.` 出現後 → 在 **Service** tab 找 SSH/shell 入口(Railway 有 "Run command" 按鈕)→ 跑:

```bash
celery -A app.workers.celery_app call app.tasks.fetchers.fetch_fred_cpi_task
```

過 30 秒回 `/api/v1/events` 應該有 FRED 資料。

---

## 6. Vercel 部署 frontend

### 6.1 註冊 + import

1. 開 https://vercel.com
2. 用 GitHub 登入
3. **Add New** → **Project** → 選 `e54true/EventSense`
4. **Root Directory** → `frontend`(Vercel 預設整個 repo,要明確指定 frontend 子目錄)
5. **Framework Preset** → Vercel 自動偵測 `Next.js`(讓它自動)
6. **Environment Variables** → 加一條:
   ```
   NEXT_PUBLIC_API_URL = https://eventsense-backend-production.up.railway.app
   ```
   (用上面 §5 拿到的 Railway backend URL)
7. **Deploy**

等 ~2 分鐘。Vercel 會給你 URL 例如 `https://event-sense.vercel.app`。

### 6.2 驗證

開那個 Vercel URL,應該看到首頁有 hero + AccuracyPills + (空) timeline。

點 `/dashboard` 也應該載入。

---

## 7. 等資料累積(48 小時 acceptance)

Beat schedule 跑起來會:
- 每 15 分鐘:SEC EDGAR fetch
- 每小時整點:FRED CPI fetch(月度資料,大多 no-op)
- 每天 14:30 UTC:FOMC fetch
- 每天 22:00 UTC:earnings fetch
- 每 5 分鐘(市場時間內):price snapshots
- 每 1 分鐘:analyzer(處理 FETCHED events)
- 每 5 分鐘:validator(算 outcomes)

第一次部署需要跑 **backfill** 把 1 年歷史 price 拉進來。Railway worker service → Run command:

```bash
python -m app.scripts.backfill_prices
```

跑 ~30 秒,2200+ price snapshots 進 DB。

之後系統就**完全自動**了。

---

## 8. Production 後續監控

### Railway 內建
- **Metrics** tab — CPU / memory / network 圖
- **Logs** tab — 即時串流 log
- **Deployments** tab — 每次 deploy 的 build log

### 外部 uptime 監控(UptimeRobot)
1. 註冊 https://uptimerobot.com(免費)
2. **+ New Monitor** → HTTP(s) monitor
3. URL = `https://eventsense-backend-production.up.railway.app/api/v1/health`
4. 5 分鐘 interval
5. Down 時寄 email 通知你

### LLM 預算監控
打開 https://platform.openai.com/usage 看每天花多少。預期 < $1/天(我們 cap $1)。

---

## 9. 常見問題排查

### Q: Backend deploy 後 healthcheck 紅
```
Logs 看 alembic upgrade head 是否成功
   → 若 fail:DATABASE_URL 是否含 +asyncpg
   → 若 fail:Postgres 是否還在 provisioning
```

### Q: Worker 跑起來但沒在處理 task
```
Logs 看是否 connect to Redis 成功
   → 若 fail:REDIS_URL 是否正確
   → 若 fail:Redis service 是否啟動
```

### Q: Frontend 開了但 timeline 空白 + console 報 CORS error
```
backend 的 CORS allowlist 是否包含 Vercel domain
   → app/main.py 的 allow_origin_regex 應該 cover *.vercel.app
   → 重 deploy backend 讓設定生效
```

### Q: LLM 預算很快就 hit cap
```
看 /accuracy 是否大量 events 被 analyze
   → 可能 backfill 拉太多歷史 events 進 events 表
   → 暫時調整 LLM_DAILY_COST_CAP_USD 或 prompt batch_size
```

### Q: Beat 沒在 fire schedule
```
Beat service 的 Logs 看是否有 "Scheduler: Sending due task ..."
   → 沒有的話:Beat process 可能 crashed,重啟看 logs
   → 若 healthy 但 task 沒進 worker:Redis 連線問題
```

---

## 10. 之後 push to main 自動 deploy

Railway 預設 **push to main → 自動 build + deploy**(每個 service 都會 trigger)。

Vercel 也是預設行為。

所以 M9 之後的 workflow:
```
本地改 code → commit → push main
   → Railway 自動 rebuild 4 個 backend services
   → Vercel 自動 rebuild frontend
   → 你什麼都不用做,~3-5 分鐘後 production 更新
```

**第一次達成「自動部署」的工程師快感** 😎

---

## 11. 成本估算(月)

```
Railway:
  - $5 / month free trial credit
  - 預期使用:~$3 / month (4 services 都很 idle,小 Postgres / Redis instance)
  
Vercel:
  - Hobby plan free (個人專案 OK,商業用要升級)
  
OpenAI:
  - $0.05 / month(M5 daily cap 已經 $1/day,實際遠低於)
  
總計:< $3 / month
```

跟 portfolio demo 的價值比,**便宜到嚇人**。

---

## 12. M9 驗收清單

跑完上面所有步驟,跑下面這些 sanity check:

```bash
# 1. Backend public URL 回 200
curl https://<your-backend>.up.railway.app/api/v1/health
# {"status":"ok","uptime_seconds":...}

# 2. Backend 可以連 DB
curl https://<your-backend>.up.railway.app/api/v1/health/ready
# {"status":"ok","database":"ok"}

# 3. Events / accuracy / prices endpoint 工作
curl https://<your-backend>.up.railway.app/api/v1/events
curl https://<your-backend>.up.railway.app/api/v1/accuracy

# 4. Frontend 在 Vercel URL 開得了
# 開 https://<your-frontend>.vercel.app 看到 hero + timeline

# 5. Frontend 真的能打 backend(看 Network tab 沒 CORS error)

# 6. Worker / analyzer / beat 各 service Logs 都看到正常 startup
```

通過 = **production 上線**。

---

# 🎉 你做到了什麼?

```
你有一個 https://xxx.vercel.app 任何人開都能看
背後跑 6 個 cloud services(backend + 3 workers + 2 addons)
每天自動抓 4 個 source 的真實市場資料
LLM 自動分析每個事件
驗證 LLM 預測準確率
全部 24/7 跑著,你不用管
總成本 < $3/月
```

履歷上可以寫:
- *"Designed and deployed production-grade LLM analytics system with 6 cloud services on Railway + Vercel"*
- *"Built async Python backend (FastAPI + Celery + PostgreSQL + Redis) handling N events/day"*
- *"Implemented closed-loop ML evaluation: events → LLM predictions → real-time validation against market data"*

**🔥 下次 LinkedIn 改自己 title 為 "Full-stack engineer"**。
