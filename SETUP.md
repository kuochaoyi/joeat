# SETUP

## 前置需求

| 工具 | 版本 | 備註 |
|---|---|---|
| Python | 3.12+ | 後端與測試 |
| Node.js | 20+ | 前端(開發時用 24 驗證過) |
| PostgreSQL | 14+(開發時用 16.2 驗證) | 見下方兩種方式 |

## 1. 後端

macOS / Linux:

```bash
cd joeat/backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
cp .env.example .env        # Windows: copy .env.example .env
```

Windows PowerShell:

```powershell
cd joeat\backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
copy .env.example .env
```

下面的指令都以 `PY` 代表 `.venv/bin/python`(Windows:`.\.venv\Scripts\python`)。

## 2. PostgreSQL(二選一)

### A. 內嵌 PostgreSQL(不需要 Docker、不需要安裝 PostgreSQL)

```
PY scripts/dev_postgres.py          # 啟動(可重複執行)、建立資料庫 joeat、把 DATABASE_URL 寫進 backend/.env
PY scripts/dev_postgres.py --stop   # 停止
```

資料放在 `backend/.pgdata/`(已列入 .gitignore)。這是開發用,正式環境請用一般 PostgreSQL。

### B. Docker

```
docker compose -f docker/docker-compose.yml up -d db
```

然後把 `backend/.env` 的 `DATABASE_URL` 設成
`postgresql+psycopg://joeat:joeat@127.0.0.1:5432/joeat`。

> docker-compose.yml 與 backend.Dockerfile 已撰寫,但**沒有在建置 MVP 的機器上執行過**(該機器沒有 Docker)。若有問題請回報。

### C. 自己的 PostgreSQL

建立一個資料庫與帳號,把 `DATABASE_URL` 設成 `postgresql+psycopg://USER:PASS@HOST:PORT/DBNAME`。需要能 `CREATE EXTENSION`/建 schema 的權限不是必須的:schema 只用到內建功能(`gen_random_uuid()` 需要 PostgreSQL 13+)。

## 3. 建表與種子資料

```
PY scripts/seed.py --reset          # alembic downgrade base → upgrade head → 載入 data/seed/*.sql
PY scripts/seed.py                  # 資料庫是空的才會載入;已有資料就什麼都不做
PY scripts/seed.py --pool all       # 僅供 demo:把單一來源、未驗證的 16 家也強制放進推薦池(會印出警告)
```

只想跑遷移:`PY -m alembic upgrade head`(從 `backend/` 執行)。

種子檔(`data/seed/`,依檔名順序套用):

| 檔案 | 內容 |
|---|---|
| `01_attribute_seed.sql` | 證據狀態、19 個屬性(17 項食材 / 飲食 + 可攜寵物、親子友善)、30 條決策規則、計分設定 v1 |
| `02_seed_restaurants.sql` | 30 家 PoC 餐廳、身分來源、料理標籤、營業時間、26 筆證據(全是「含有 / 可能含有」)、3 筆**測試用**假聲明 |
| `03_seed_extra_hotpot.sql` | 汕頭天天沙茶火鍋(稅籍 + 網路兩個來源佐證),讓 demo 能展示火鍋加分 |

預設 31 家中只有 15 家在推薦池(`pool_status = 'in_pool'`):只有被第二個來源佐證存在的店才進池。

> 屬性字典在種子檔裡:舊的開發資料庫要執行 `seed.py --reset` 才會有新增的屬性(例如可攜寵物、親子友善、歐式料理)。

### 3.0 試辦用的資料庫(給真實店家用,**不是**示範資料庫)

```
PY scripts/seed.py --reset --no-fixtures   # 真實資料、沒有假證據;不要執行 seed_demo_merchants.py
PY scripts/pilot_preflight.py              # 退出碼 1 = 還不能給真店家用(列出每個阻擋項)
```

`seed.py --reset` 在資料庫已有**真實**(非示範)店家認領時會**拒絕**執行(它會刪光所有聲明與稽核紀錄);確定要刪才加 `--destroy-real-data`。完整的試辦準備:[docs/pilot/README.md](docs/pilot/README.md)。

### 3.1 示範用假店家資料(店家填寫頁 + 審核後台)

目前的開發策略是「先用假資料把系統做完」。假資料與真實資料完全隔離:示範認領發布的證據一律寫進隱藏的測試來源(`test_fixture`),只有 `ALLOW_TEST_EVIDENCE=true` 時引擎才看得見,且結果頁會顯示示範橫幅。

```
# backend/.env 需要:OPS_API_KEY=dev-ops-key   ALLOW_TEST_EVIDENCE=true
PY scripts/seed_demo_merchants.py     # 建立 8 個示範認領(已有就拒絕;沒開 ALLOW_TEST_EVIDENCE 也拒絕)
```

| 網址 | 情境 |
|---|---|
| `/m/demo-duck` | 鴨肉珍:已驗證、尚未填寫 → 可走完整個填寫流程 |
| `/m/demo-borage` | The Borage:未驗證 → 只顯示「等待身分確認」 |
| `/m/demo-ayin` `/m/demo-guo` `/m/demo-tian` `/m/demo-jiu` `/m/demo-dagou` `/m/demo-laocai` | 已送出 / 與既有證據矛盾 / 基本驗證 / 退回補件 / 已發布 / 已發布且有未結事故 |
| `/ops` | 審核後台:金鑰 `dev-ops-key`,姓名自填(可用中文) |

想看推薦整合的效果:建立聚餐 → 限制頁選「乳製品」並勾「嚴格過敏模式」→ 結果頁只會剩示範店家「大溝頂虱目魚米粉湯」(它的牛奶聲明是示範資料),並顯示帶日期的聲明陳述;不勾嚴格模式則其他店會以「資訊不足」警示出現。在結果頁按「回報資料錯誤」,再到 `/ops/reports` 升級為事故,該店的聲明就會被暫停。

**上線前**:`ALLOW_TEST_EVIDENCE=false`、換掉 `OPS_API_KEY`、刪除示範認領與 `test_fixture` 來源的證據。

## 4. 啟動後端

```
PY -m uvicorn app.main:app --port 8000 --reload
```

- API 文件(Swagger):http://localhost:8000/docs
- 健康檢查:http://localhost:8000/healthz

## 5. 前端

```
cd joeat/frontend
cp .env.example .env.local          # Windows: copy .env.example .env.local
npm install
npm run dev                         # http://localhost:3000
```

`NEXT_PUBLIC_API_BASE` 預設 `http://localhost:8000`。`NEXT_PUBLIC_LIFF_ID` 留空 = 一般瀏覽器 demo 模式(會產生一個存在 localStorage 的假使用者 id,用不同瀏覽器或無痕視窗就是不同使用者)。

正式 build:`npm run build && npm run start`。

## 環境變數(後端 `backend/.env`)

| 變數 | 預設 | 說明 |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres@127.0.0.1:5432/joeat` | SQLAlchemy URL(使用 psycopg 3) |
| `ID_HASH_SECRET` | `dev-only-change-me` | LINE user / group id 以 HMAC-SHA256 雜湊後才存入;**上線前務必更換並妥善保管**,更換會讓既有 hash 失效 |
| `AUTH_MODE` | `dev` | `dev`:用戶端自報 `line_user_id`(僅供 demo)。`line`:必須帶 LIFF ID token,後端向 LINE 驗證 |
| `FRONTEND_URL` | `http://localhost:3000` | bot 回覆的連結網址 |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | 允許的前端來源 |
| `OPS_API_KEY` | 空 | 審核 API(`/ops/*`)的共用金鑰。**空 = 整組停用(503)**;設了才啟用,並要求 `X-Ops-User` 標頭。只適合試辦等級的少數營運 |
| `ALLOW_TEST_EVIDENCE` | `false` | 是否讓引擎看見測試用假證據。**正式環境必須是 false** |
| `LINE_CHANNEL_ID` | 空 | LINE Login channel id(驗證 ID token 用,`AUTH_MODE=line` 時必填) |
| `LINE_CHANNEL_SECRET` | 空 | Messaging API channel secret(驗證 webhook 簽章) |
| `LINE_CHANNEL_ACCESS_TOKEN` | 空 | 回覆訊息用 |
| `LINE_DRY_RUN` | `true` | true = 不呼叫 LINE,只回傳「會送出的訊息」 |
| `LINE_SKIP_SIGNATURE` | `false` | 只給本機測試 / 自動化測試,**正式環境必須是 false** |
| `LIFF_ID` | 空 | 設了之後 bot 發出 `https://liff.line.me/<LIFF_ID>/s/<session>` |

## 6. LINE Bot + LIFF(接真實 LINE)

> 下列步驟**沒有對真實 LINE 帳號測過**(開發時沒有 channel 憑證)。程式邏輯與簽章驗證有自動化測試;實際整合請預期需要除錯。

1. 在 [LINE Developers](https://developers.line.biz/) 建立 Provider,新增 **Messaging API** channel(bot)與 **LINE Login** channel(LIFF 用)。
2. 公開你的後端(例如 ngrok / 雲端部署,必須 HTTPS),Webhook URL 設為 `https://<後端網域>/line/webhook`,並開啟「Use webhook」。
3. 建立 LIFF app:Endpoint URL = 前端的 HTTPS 網址(例如 `https://<前端網域>/`),Scope 選 `profile`、`openid`;記下 LIFF ID。
4. 設定環境變數:
   - 後端:`LINE_CHANNEL_SECRET`、`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_DRY_RUN=false`、`LIFF_ID`、`LINE_CHANNEL_ID`(LINE Login channel id)、`AUTH_MODE=line`、`ID_HASH_SECRET`(換掉)、`CORS_ORIGINS`(含前端網域)。
   - 前端:`NEXT_PUBLIC_API_BASE`(後端公開網址)、`NEXT_PUBLIC_LIFF_ID`。
5. 把 bot 加進群組,輸入 `建立聚餐 高中同學聚餐 3人`,按回覆裡的連結填寫;填完輸入 `推薦`。

bot 指令:`建立聚餐 [名稱] [N人]`、`分享`、`進度`、`推薦`、`強制推薦`、`結果`、`說明`。

## 疑難排解

| 現象 | 原因 / 處理 |
|---|---|
| `connection refused` / 測試全部被跳過 | 資料庫沒啟動。`PY scripts/dev_postgres.py` 或啟動 Docker |
| 前端顯示「連不上伺服器」 | 後端沒開,或 `NEXT_PUBLIC_API_BASE` / `CORS_ORIGINS` 不一致(改了 `NEXT_PUBLIC_*` 要重新 `npm run dev`) |
| 推薦頁顯示「候選 0 家」 | 沒載入種子資料:`PY scripts/seed.py` |
| `alembic` 找不到資料庫 | 從 `backend/` 目錄執行,並確認 `.env` 的 `DATABASE_URL` |
| Windows 終端機中文亂碼 | 使用 UTF-8 終端機;Python 加 `-X utf8` |
| 內嵌 PostgreSQL 重開機後連不上 | 再執行一次 `PY scripts/dev_postgres.py`(埠號可能變了,會重寫 `.env`) |
| 內嵌 PostgreSQL 被強制結束後起不來(逾時、`postmaster.pid`) | 結束殘留的 `postgres.exe`、刪除 `backend/.pgdata/postmaster.pid`,以 `-X utf8` 重新執行 `dev_postgres.py`,再跑一次 `seed.py --reset` 與 `seed_demo_merchants.py`(重啟後埠號會變) |
| 審核後台登入顯示「連不上伺服器」 | 舊版把中文姓名直接放進標頭,瀏覽器拒絕送出;已改為百分比編碼。若仍發生,確認前端已重新 `npm run build` / 重啟 |
