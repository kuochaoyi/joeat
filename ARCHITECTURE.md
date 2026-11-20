# ARCHITECTURE

單一後端服務 + 單一前端 + 一個 PostgreSQL。沒有微服務、佇列、Redis、ML 或向量資料庫——MVP 不需要。

```
  LINE 群組 ──訊息──► LINE Platform ──webhook──► POST /line/webhook ─┐
       │                                                              │
   LIFF (Next.js) ──REST──────────────────────────────► FastAPI ◄─────┘
                                                          │
                       api/ (路由)  →  services/ (流程)  →  recommendation/ (純函式引擎)
                                                          │
                                                   SQLAlchemy ORM
                                                          │
                                       PostgreSQL: ref | staging | identity | enrichment | product
```

## 分層

| 層 | 位置 | 責任 | 不做什麼 |
|---|---|---|---|
| API | `app/api` | HTTP 驗證、狀態碼、回應模型 | 不含商業規則 |
| Services | `app/services` | 交易邊界、載入資料、呼叫引擎、**存證**、組回應 | 不含評分規則 |
| Engine | `app/recommendation` | Hard Filter、計分、排序、解釋文字 | **沒有任何 I/O**,所以可以不碰資料庫做單元測試 |
| Models | `app/models` | 對映 schema_v2 的資料表 | 不建立或更改 schema(Alembic 0001 套用已驗證的 SQL) |
| ER | `app/er` | 地址 / 名稱正規化與評分(來自 PoC) | 尚未接進流程(餐廳身分合併目前仍由種子資料 / 離線腳本處理) |

## 資料流:產生推薦

1. `POST /sessions/{id}/recommendations`
2. `services/recommendations.load_engine_input`:取得候選池(`pool_status='in_pool'` 且非 closed、未被合併、同區)、每位成員的硬限制 / 偏好、每家餐廳每個屬性的**有效證據狀態**(view `restaurant_attribute_state`,含 `deciding_evidence_id`)、料理標籤(含父分類)、獨立來源數、營業時間狀態、決策規則表、計分設定。
3. `recommendation.engine.run_engine`(純函式):
   `hard_filter` → 被排除者不計分 → 其餘 `scoring` → `ranking` → Top N。
4. `services/recommendations.persist`:在同一個交易裡寫入 `recommendation_run`(含 `config_snapshot`)、**每一家**候選(被排除的也寫)、每個 (餐廳 × 成員 × 限制) 一列 `recommendation_constraint_check`(含證據快照)、每個分數元件。
5. 回應由**剛存下的資料**組出(POST 與 GET 同一條程式路徑)。

## 規則在哪裡

- 硬限制決策矩陣(2 類型 × 3 風險 × 5 證據狀態 = 30 條)存在資料庫 `ref.constraint_decision_rule`,**執行時由資料庫載入**。`recommendation/rules.py` 有一份同內容的程式碼副本供單元測試使用,整合測試斷言兩者完全相同。
- 計分權重存在 `ref.scoring_config`(版本化);每次 run 存 `config_snapshot`,舊結果永遠能重算與解釋。
- 規則文字說明:[docs/recommendation_data_contract.md](docs/recommendation_data_contract.md)。

### Hard Filter 摘要

| 屬性類型 | 證據狀態 | 動作 |
|---|---|---|
| avoid | CONFIRMED_PRESENT | 排除 |
| avoid | LIKELY_PRESENT | critical / high:排除;normal:保留 + 高警示 |
| avoid | UNKNOWN / LIKELY_ABSENT | 保留 + 警示(critical 屬性為「重要」警示);**不顯示安全** |
| avoid | CONFIRMED_ABSENT(需第一手) | 通過(唯一可顯示「已確認」) |
| require | CONFIRMED_PRESENT | 通過 |
| require | LIKELY_PRESENT | 有條件通過(附警示) |
| require | UNKNOWN | 保留 + 警示 |
| require | LIKELY_ABSENT | critical / high:排除;normal:警示 |
| require | CONFIRMED_ABSENT | 排除 |

任何一位成員的「排除」都會排除該餐廳(全體生效)。成員填寫的原因(過敏、宗教…)只會**提高**風險等級。

矩陣查完之後,`hard_filter.evaluate_restaurant` 再做兩個以成員為單位的調整(細節與理由:[決策紀錄 0001](docs/decisions/0001-merchant-declaration.md)「整合後的行為」):

- **偏好型柔化**:偏好型限制(`dislike` / `belief_diet`,或無原因時屬性預設)、非 critical 屬性、店家聲明只有「有些餐點」含有 → 排除改為「注意」警示。安全型、critical 屬性、`most` / 範圍未知都照矩陣。
- **嚴格過敏模式**(成員自選):該成員自己的安全型「不吃」限制,`UNKNOWN` / `LIKELY_ABSENT` 改為排除;只有 `CONFIRMED_ABSENT` 通過。

兩者都在稽核資料的 `evidence_snapshot.engine_note` 留下原因。**SQL 參考引擎沒有跟進這兩項**(仍是 v1 矩陣)。聲明在結果頁以帶日期的事實陳述呈現(`explain.declaration_statements`),不加分、不降低警示等級。「回報錯誤」只進審核佇列,不影響引擎(`services/reports.py`)。

### 計分 v1(可解釋,無 ML)

`總分 = 料理偏好 + 距離 + 資料可信度`(評價、價格是 UNKNOWN 佔位,0 分;預算永遠不排除)。

- 料理偏好:逐人,很想吃 +3 / 可以 +1 / 都好 0 / 不太想 −1;命中多個標籤取最高;偏好父分類(中式)也命中子分類(熱炒)。
- 距離:≤300 m +2、≤600 m +1、≤1000 m 0、更遠 −1;**缺座標 = 0 分並警示**(不扣分、不排除)。
- 資料可信度:身分有 ≥2 個獨立來源確認才 +1;資料不足**不加也不扣**。
- 排序:總分高 → 重要警示少 → 警示少 → 距離近(未知殿後)→ restaurant_id(可重現)。

## 隱私與安全設計

- **私密需求**:所有成員的硬限制只存在 `participant_hard_constraint`;沒有任何 API 會回傳某人的限制。進度只回 `label` 與完成與否(不含 participant_id,因為 MVP 的 participant_id 就是代表該成員操作的憑證)。推薦回應只顯示屬性層級的警示(「花生資訊不足」),不指名是誰。
  - 限制:3 個人的小團體裡,「花生資訊不足」本身就洩漏「有人要避開花生」。這是產品需求的固有取捨。
- **不存原始 LINE id**:`line_user_id`、`line_group_id` 進入後立即 `HMAC-SHA256(ID_HASH_SECRET, id)`;資料庫只有雜湊。
- **聚餐資料會過期**:`dining_session.expires_at` 預設 7 天,刪除聚餐會 CASCADE 刪除成員、限制、偏好、推薦結果。(目前沒有排程自動刪除過期資料,需要補一個 cron / 定期工作。)
- **稅籍姓名不入庫**:資料庫約束禁止 `name_is_personal = true` 時存名稱。
- **測試證據隔離**:測試用假聲明預設不可見。
- Webhook 以 `X-Line-Signature` 驗證;未設 channel secret 時回 503(除非明確開 `LINE_SKIP_SIGNATURE`,僅限本機)。

## 設計決策與取捨

| 決策 | 理由 | 代價 |
|---|---|---|
| Alembic 0001 直接執行 `schema_v2.sql` | schema 有 CHECK、trigger、view、函式,已在 PostgreSQL 驗證;不想用 ORM metadata 重寫而失真 | 不能 autogenerate;ORM 模型與 SQL 要人工保持一致(整合測試會抓到欄位對不上) |
| 引擎寫成無 I/O 的純函式 | 可以直接單元測試,規則一目了然 | 需要一層 `load_engine_input` 把資料轉成引擎輸入 |
| 資料庫裡另有一份 SQL 版引擎(`product.evaluate_session`) | 當作參考實作;**整合測試逐項比對兩者輸出**(排除、分數、警示、排名、稽核列) | 兩份實作要維護。這個比對曾抓到 SQL 版的真實 bug(未知距離被算成 −1) |
| 規則存資料庫、程式有副本 | 規則可以不改程式調整;副本讓單元測試獨立 | 兩份要一致(測試保證) |
| 被排除的候選也存 | 可除錯、可解釋、可稽核 | 每次 run 多寫 N 列 |
| 不做登入,participant_id 當憑證 | MVP 範圍 | 知道某人的 participant_id 就能代他操作;正式版必須接 LIFF ID token(`AUTH_MODE=line` 已實作驗證,**未對真實 LINE 測過**) |
| 前端只有 4 個畫面 + 首頁 | 垂直流程優先 | 沒有編輯聚餐、踢人、刪除、重填通知等 |

## 已知缺口

1. 沒有任何第一手「確認不含」資料 → 所有過敏原都是「資訊不足」。需要店家自填 / 電話確認流程(尚未設計實作)。
2. 餐廳身分合併(ER v1)尚未接進流程;推薦池是種子資料。
3. 營業時間只作警示,沒有「現在是否營業」的判斷。
4. `radius_m` 已儲存但未使用;距離只計分。
5. 過期聚餐的刪除沒有排程。
6. 真實 LINE / LIFF 整合未測試。
