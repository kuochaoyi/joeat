# JOEAT 揪呷

LINE Bot + LIFF 的多人聚餐決策工具(MVP)。2–20 人各自填「不能違反的條件」(過敏、不吃、素食…)與「想吃什麼」,系統先排除不符合的餐廳,再依偏好排序,推薦 Top 3,並說明理由與「資訊不足」的地方。

目前只涵蓋**高雄市鹽埕區**,餐廳是 31 家來自資料可行性 PoC 的真實餐廳(其中 15 家有第二來源佐證、進入推薦池)。

## 這個 MVP 做了什麼、沒做什麼

| 已完成並驗證 | 刻意不做 / 未驗證 |
|---|---|
| 建立聚餐 → 3 人加入 → 填硬限制與偏好 → Hard Filter → 計分 → Top 3 → 理由與警示(後端、前端、資料庫全部串通) | 評價、Google Places、價格排序、團體容量、訂位、付款、AI 聊天、推播、正式登入。**店家自填:審核 API、資料庫(遷移 0003 / 0004)、店家填寫頁(`/m/{token}`)與審核後台(`/ops`)都已做,但只用假資料驗證(SETUP.md 3.1),沒有任何真實店家參與;推薦引擎與結果頁**已整合**(聲明以事實陳述呈現、偏好型柔化、嚴格過敏模式、回報錯誤需審核才生效),同樣只用假資料驗證;切結文字未經法務** |
| 資料不足一律標「資訊不足」,**絕不顯示「安全」**(除非有第一手的「確認不含」資料,目前沒有) | **真實 LINE / LIFF 登入與 LINE 回覆沒有對真實 LINE 測過**(沒有 channel 憑證);bot 邏輯與簽章驗證有測試,回覆在 dry-run 模式 |
| 預算只是軟條件(目前沒有可靠的人均價格,不排除、不計分) | `docker-compose.yml` 已寫但**沒有執行過**(開發機沒有 Docker) |
| 215 項自動化測試(單元 101 + 整合 114)、瀏覽器端到端手動走過三次(推薦流程;店家頁 + 審核後台;推薦整合) | 前端沒有自動化測試;沒有效能 / 併發測試 |

## 快速開始(Windows PowerShell;macOS / Linux 見 SETUP.md)

需要 Python 3.12+ 與 Node 20+。

```powershell
# 1) 後端環境
cd joeat\backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt

# 2) PostgreSQL(二選一)
.\.venv\Scripts\python scripts\dev_postgres.py          # A. 不需要 Docker:內嵌 PostgreSQL,自動寫入 backend\.env
# docker compose -f ..\docker\docker-compose.yml up -d db   # B. Docker(要把 backend\.env 的 DATABASE_URL 設成 compose 裡的值,見 SETUP.md)

# 3) 建表 + 種子資料
.\.venv\Scripts\python scripts\seed.py --reset

# 4) 跑後端(http://localhost:8000/docs)
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000

# 5) 另開一個終端機:前端(http://localhost:3000)
cd joeat\frontend
npm install
npm run dev
```

## Demo

固定劇本「高中同學聚餐」:A 不吃牛、想吃日式;B 花生過敏、想吃火鍋;C 都好。

```powershell
cd joeat\backend
.\.venv\Scripts\python scripts\demo.py --in-process      # 不需要啟動伺服器,直接在終端機看到 Top 3
.\.venv\Scripts\python scripts\demo.py                   # 對執行中的 http://localhost:8000 跑,並印出可在網頁開啟的 session id
```

預期結果(以預設種子):候選 15 家 → 排除 2 家(**港園牛肉麵**:牛肉已確認含有;**郭家肉粽**:花生疑似含有且是 critical)→ Top 3 = 東京小城、柒壹喫堂(日式加分)、汕頭天天沙茶火鍋(火鍋加分),**每一家都帶「花生資訊不足」的重要警示**——因為目前沒有任何一家有花生的第一手資料。

### 在瀏覽器手動走一遍

1. 開 `http://localhost:3000` → 建立聚餐(名稱、日期、時間、地點、人數)。
2. 進到聚餐頁(你自動成為成員1)→ 「填寫硬限制」勾「牛肉」→ 「填寫料理偏好」把日式選 🔥 → 完成。
3. 其他人用同一個連結加入(不同瀏覽器 / 無痕視窗 = 不同使用者)。也可以用 `scripts/demo.py` 當另外兩人,見 TESTING.md。
4. 進度全部 ✅ 後按「產生推薦 Top 3」→ 看 Top 3、分數、硬限制狀態、警示與理由;展開「被排除的餐廳」看被哪一項條件排除(**只顯示條件,不顯示是誰的**)。

## 測試

```powershell
cd joeat\backend
.\.venv\Scripts\python -m pytest -q          # 單元 + 整合(整合會自動建立/刪除 joeat_test 資料庫;沒有 PostgreSQL 時整合測試自動跳過)
.\.venv\Scripts\python -m pytest tests\unit  # 只跑單元測試(不需要資料庫)
cd ..\frontend; npm run typecheck; npm run build
```

## 審核後台與管理員設計（`/ops` + Python Dash）

審核後台用於管理店家自填聲明、認領驗證、使用者回報、緊急煞車事故與營運數據洞察。前台首頁（`/`）刻意不放置入口，管理員直接由 `/ops` 進入。

### 路由與選單架構
- **`/ops/login`（獨立管理員登入頁）**：沿用既有 `OPS_API_KEY` 共用金鑰與稽核姓名驗證（不更動資料庫），支援金鑰顯示切換、啟用中管理員快選、停用名單阻擋與 `next` 安全導回；登入成功時同步核發 Python Dash 專用簽章 Cookie。
- **`/ops`（總覽儀表板）**：呈現待審店家聲明、待處理使用者回報、未結案事故與認領統計等核心 KPI 卡片，以及最新待審聲明摘要與快速操作入口。
- **`/ops/analytics`（數據分析 · Python Dash）**：以全高響應式 `<iframe>` 無縫嵌入後端 FastAPI 掛載的 Plotly Dash 應用（`/ops/dash/`），提供「包含示範資料」切換、即時重新整理、5 張 KPI 卡片與 4 張互動圖表（聲明狀態分布、餐廳候選池分布、回報與事故類型分析、近 14 日聚餐開團與參與趨勢）。
- **`/ops/declarations` 與 `/ops/declarations/[id]`（聲明審核）**：檢視待審／補件／已核准／已駁回／草稿佇列、矛盾證據與稽核軌跡，執行核准發布、退回補件、駁回或撤下。
- **`/ops/claims`（認領與驗證）**：邀請餐廳並產生一次性連結，記錄電話回撥、實地確認或官方菜單覆核留痕。
- **`/ops/reports`（使用者回報）** 與 **`/ops/incidents`（事故處理）**：查證使用者回報並決定駁回或升級為事故（觸發正向聲明緊急煞車）。
- **`/ops/admins`（管理員帳號管理）**：試辦階段採瀏覽器本機名冊（`localStorage`，不更動資料庫），支援新增管理員與啟用／停用切換（內建防自我鎖定保護，避免停用正在操作中的本人）。

### 版面與安全機制
- **響應式導覽（`OpsShell`）**：桌面版採左側固定側邊欄（260px）並即時顯示待辦紅點徽章；行動版自動切換為頂部標題列與滑出抽屜選單（支援 `Esc` 關閉）。透過 `main:has(.ops-shell-root)` 自動解除前台 500px 手機窄版限制，完全不影響前台畫面。
- **雙層驗證保護**：
  - 後端 REST API（`/ops/*`）透過 `X-Ops-Key` 與百分比編碼的 `X-Ops-User` 標頭驗證。
  - 後端 Python Dash（`/ops/dash/*`）透過 `POST /ops/dash-session` 核發 `HttpOnly`、`SameSite=Lax` 的 HMAC-SHA256 簽章 Cookie（`joeat_ops_dash`，由 `ID_HASH_SECRET` 與 `OPS_API_KEY` 共同衍生，8 小時有效；更換金鑰或呼叫 `POST /ops/dash-logout` 登出即刻失效）。未攜帶有效 Cookie 直接開啟 `/ops/dash/` 會被中介層阻擋並回傳 401。

## 專案結構

```
joeat/
  backend/            FastAPI + SQLAlchemy + Alembic + Python Dash
    app/api/            REST 路由、LINE webhook、審核後台 API（ops.py）
    app/dash_app.py     Python Dash（Plotly）互動式營運數據儀表板（掛載於 /ops/dash/）
    app/recommendation/ 純 Python 推薦引擎:hard_filter / scoring / ranking / engine / explain / rules
    app/services/       sessions、recommendations(載入→引擎→存證→回傳)、restaurants、line_bot
    app/models/         SQLAlchemy 模型(對映 schema_v2.sql 建出的資料表)
    app/er/             實體解析的正規化與評分(來自 PoC 的 ER v1,尚未接進流程)
    app/db/sql/         schema_v2.sql(Alembic 0001 原樣套用)
    alembic/versions/   0001 schema、0002 MVP 欄位
    scripts/            dev_postgres.py、seed.py、demo.py、seed_demo_merchants.py
    tests/              unit/、integration/
  frontend/           Next.js(App Router)+ Tailwind CSS + LIFF SDK:前台聚餐流程 + /ops 管理員審核後台
  data/seed/          01 屬性與規則、02 餐廳與證據、03 一家額外的火鍋店
  data/raw/           OSM 捷運/輕軌站(集合點座標來源)
  docs/               推薦合約、ER 規格、schema 驗證報告、資料可行性報告
  docker/             docker-compose.yml、backend.Dockerfile
```

## 文件

- [SETUP.md](SETUP.md):各平台安裝、環境變數、LINE / LIFF 設定
- [ARCHITECTURE.md](ARCHITECTURE.md):架構、資料流、決策與取捨
- [API.md](API.md):API 與範例
- [TESTING.md](TESTING.md):測試策略、涵蓋範圍與缺口
- [docs/recommendation_data_contract.md](docs/recommendation_data_contract.md):推薦規則合約(硬限制、UNKNOWN、計分)
- [docs/ui_design.md](docs/ui_design.md):介面設計原則(Stitch 版面手法、哪些資訊不能因為簡潔而收起來)
- [docs/user_testing_feedback.md](docs/user_testing_feedback.md):對 Stitch 原型的使用者測試回饋、逐項處理狀態、以及原型與我們設計原則衝突的地方
- [docs/pilot/README.md](docs/pilot/README.md):**真實店家試辦套件**(計畫、候選名單、通話腳本、營運手冊、上線檢查;目前預檢有 6 個阻擋項)
- [docs/decisions/0001-merchant-declaration.md](docs/decisions/0001-merchant-declaration.md):店家聲明的產品決策與目前實作狀態(**以它為準**)
- [docs/merchant_self_declaration_design.md](docs/merchant_self_declaration_design.md):店家自填設計(最初的設計草案;實作與決策以 0001 為準)

## 你需要知道的資料限制

- 目前**沒有任何餐廳有「確認不含」過敏原的第一手資料**。所以每個推薦都會對過敏原顯示「資訊不足」。這是正確的,但也代表「嚴重過敏模式」現階段無法推薦任何「已確認安全」的店;要改變這件事需要真實店家透過填寫頁 + 人工驗證提供資料(流程已做好,目前只有假資料跑過)。**「嚴格過敏模式」在真實資料下會是 0 家**:它只放行店家已確認不含的餐廳,而現在沒有任何真實的確認資料;畫面會如實說明,不會硬湊推薦。
- 營業時間約一半互相矛盾、營業狀態全部「未驗證」、價格與評價沒有可靠資料。UI 會明確標示。
- `seed_restaurants.sql` 內有 3 筆明確標示為**測試用**的假聲明(`source_type = test_fixture`),預設不可見;只有設定 `ALLOW_TEST_EVIDENCE=true` 才會被引擎看到。**上線前請刪除。** 示範店家(`seed_demo_merchants.py`)發布的假聲明走同一個隱藏來源,開啟旗標時結果頁會顯示「示範資料模式」橫幅。
