# Schema Validation Report(schema_v1 → schema_v2)

驗證日期:2026-11-02。方法:**在真實 PostgreSQL 上執行**,不是靜態審查。

## 1. 結論

| 項目 | 結果 |
|---|---|
| `schema_v1.sql` 能否建立 | **能**:33 個 CREATE 全部成功,0 語法錯誤 |
| `schema_v1.sql` 行為是否正確 | **不正確**:20 項行為探測只通過 3 項、失敗 17 項(見 §3) |
| `schema_v2.sql` | 建立成功(30 張表、5 個 view、6 個函式、2 個 trigger、60 個索引、56 個 CHECK、36 個外鍵、8 個 UNIQUE 約束) |
| v2 行為測試 | **110 項全過、0 失敗**(`validation/v2_test_results.txt`) |
| 端到端(種子資料 + 4 人聚餐 + 引擎) | 可執行,排除 / 警示 / 計分 / Top 3 / 解釋皆有存證(見 §7) |

**我必須更正先前說的話**:上一輪我說「資料庫強制:稅籍姓名在 staging 為空」、「確認不含只能來自菜單或店家聲明」。**v1 實際上沒有強制個資規則**(個人姓名可以寫入),而「確認不含」只擋了證據基礎類型、沒檢查來源是否為第一手、沒有效期、不限信心。這些在 v2 才真正由資料庫強制,並且有測試。

## 2. 環境

- PostgreSQL **16.2**(Windows,mingw 建置),以 Python 套件 `pgserver` 裝在暫存的 venv 中,資料目錄在暫存區;`psql` 與 `psycopg 3.3.6` 驅動測試。不動系統設定。
- **這個內嵌版本沒有時區資料庫**(`time zone "Asia/Taipei" not recognized`),所以任何依賴時區名稱的寫法都會失敗。這個限制讓我發現並改掉了一個可攜性風險(§4 第 1 項)。正式環境的 PostgreSQL 通常有 tzdata,但 v2 已不依賴它。

## 3. v1 的行為探測(`validation/v1_behavior_probe.txt`)

測試的是「預期被拒絕的壞資料是否真的被拒絕」。**17 項失敗 = 這些規則在 v1 只是慣例,資料庫不會擋**:

| 類別 | v1 實際接受了什麼(應被拒絕) |
|---|---|
| 個資 | 在 `staging.tax_registry` 與 `restaurant_source_entity` 寫入自然人姓名(`name_is_personal = true` 且 `name` 有值) |
| 身分連結 | 已連結(`auto`)卻沒有 `restaurant_id` |
| 座標 | 只有緯度沒有經度;緯度 122.6 |
| 安全證據 | `CONFIRMED_ABSENT` 沒有 `valid_until`;基礎寫「官方菜單」但來源是部落格;信心 LOW;`CONFIRMED_PRESENT` 來自 OSM 標籤 |
| 重複 | 同一餐廳、屬性、來源、基礎的證據重複兩筆 |
| 聚餐 | `expires_at` 在過去;`participant_budget` ≤ 0 |
| 推薦結果 | 引用**另一個聚餐**的參與者;同一個 run 兩個 rank 1;被排除的候選帶有 rank;top3 的 rank = 4 |
| 預設值(反向) | `dining_session` 沒給 `expires_at` 被拒絕(應有 7 天預設,否則留存政策無法落實) |

通過的 3 項:`CONFIRMED_ABSENT` 的基礎不能是媒體文字、`party_size` 的 1 與 11 被擋。

**結構性不足(不是單筆資料能測出的)**:
- `recommendation_candidate` 只有一組排除欄位 → 同一家餐廳被兩位參與者排除時,只能記一個。
- 沒有逐項檢查表、沒有逐項分數表 → 無法回答「哪筆證據」「cuisine / distance 各幾分」。
- `restaurant_attribute_state` view 沒有 `evidence_id` → 無法說明是哪筆證據決定狀態。
- view 用 `CURRENT_DATE`,結果隨連線時區改變。
- 沒有隱含關係(shellfish ⇒ seafood、vegan ⇒ vegetarian)。
- 沒有候選池閘門之外的測試證據隔離(測試資料可能混進正式推薦)。

## 4. 只有「實際執行」才發現的缺陷(建 v2 過程中)

| # | 缺陷 | 如何發現 | 修正 |
|---|---|---|---|
| 1 | `now() AT TIME ZONE 'Asia/Taipei'`:環境沒有 tzdata,所有 view 查詢失敗;同時代表對時區資料庫有隱性依賴 | 查詢 view 即報錯 | 改為 `((now() AT TIME ZONE 'UTC') + interval '8 hours')::date`(台灣自 1979 年固定 UTC+8,無夏令時間) |
| 2 | `CHECK (stage <> 'eligible' OR total_score IS NOT NULL ...)` 與引擎「先插入候選、後計分」的順序衝突,引擎第一次執行就失敗 | 執行 `evaluate_session` | 改為 eligible 只要求 `rank IS NULL`;新增 `recommendation_run.completed_at`;完成的 run 不得有未計分列,改由測試驗證 |
| 3 | 刪除一個聚餐失敗:`session → participant` 與 `session → run → check` 兩條 cascade 路徑,參與者 FK(NO ACTION)比檢查紀錄先被檢查 | 執行刪除測試 | `chk_part_fk`、`comp_part_fk` 加 `ON DELETE CASCADE`(參與者的檢查紀錄隨參與者一起刪,也符合留存政策) |
| 4 | 解釋 view 的警示用 `ORDER BY warning_level DESC`,依字母排序 → `normal` 排在 `critical` 前面,**花生過敏的警告被排到最後** | 檢視引擎輸出的 JSON | 改用 CASE 依 critical > high > normal 排序,並加測試(「critical 警示排第一」) |
| 5 | 外鍵缺索引:`er_review_queue`、`restaurant.merged_into`、`recommendation_constraint_check` 的 `participant_id` / `deciding_evidence_id`、`score_component.participant_id` | 目錄查詢 | 補 6 個索引;測試改成「指向非字典表的 FK 必須有領頭索引」 |

另外,**測試腳本本身**也出過錯(型別轉換、計數沒排除暫存資料、一個 RESTRICT 測試其實是被別的 FK 擋下而非預期的那條),都已修正並確認測試真的在測它要測的東西。

**不是 schema 的錯誤,但同一輪發現**:PoC 的地址比對腳本漏掉 OSM `addr:full` 開頭的郵遞區號(`803高雄市…`),低估了 OSM ↔ 稅籍的交集(47 → 61 筆)。已修正並更新 `POC2_GOV_DISCOVERY.md`。

## 5. 你要求的檢查清單

| 檢查項 | v2 結果 | 證據 |
|---|---|---|
| DDL 可建立 | ✅ 0 錯誤 | `validation/v2_build_log.txt` |
| Foreign keys 正確 | ✅ 36 個;複合外鍵 `(participant_id, session_id)`、`(run_id, session_id)`、`(run_id, restaurant_id)` 保證跨表同屬一個聚餐/run | 測試:引用他人聚餐的參與者被拒(檢查表與分數元件各一) |
| Unique 約束合理 | ✅ `(source_id, source_record_id)` 放來源端;證據 `(restaurant, attribute, source, basis, applies_to)`;`(run_id, rank)` 部分唯一;元件 `(run, restaurant, component, COALESCE(participant))` | 重複證據、重複元件、重複 rank、重複檢查列皆被拒 |
| Check 約束合理 | ✅ 56 個;其中個資、安全證據、連結狀態、座標、排名等有專屬測試 | `v2_test_results.txt` |
| Enum / domain | ✅ `ref.evidence_state` 為 enum;其餘用 `CHECK ... IN` 與字典表(`ref.evidence_state_basis_rule`)以便不改 schema 就能調整規則 | view 與規則表測試 |
| View 可建立且語意正確 | ✅ 5 個;保守合併(avoid 以存在為準、require 以不存在為準)、隱含關係、過期失效、測試資料隔離、`deciding_evidence_id` | 9 項 view 測試 |
| 索引合理 | ✅ 60 個;非字典表 FK 皆有領頭索引。**仍無索引的 FK 全是指向小型字典表**(屬性、基礎、來源、料理標籤、原因、計分版本),刻意不建 | 目錄測試(非資訊性) |
| Cascade / restrict | ✅ 見下表 | 測試:刪除聚餐全面清除;被 run 引用的餐廳不可刪;有來源實體的餐廳不可刪;證據不隨聚餐刪除 |
| Nullable 設計 | ✅ 見下 | — |
| Timestamp / timezone | ✅ 全部 `TIMESTAMPTZ`,資料庫內 0 個 `timestamp without time zone`;「驗證日期」用 `DATE`,以 `ref.today_tpe()`(UTC+8)計算,view 不使用 `CURRENT_DATE` | 目錄測試 |

**Cascade / Restrict 政策**

| 關係 | 行為 | 理由 |
|---|---|---|
| 聚餐 → 參與者 / 限制 / 偏好 / 預算 / run / 候選 / 檢查 / 分數 | CASCADE | 聚餐資料有留存期限(`expires_at`),到期整批刪除 |
| 餐廳 → 證據 / 料理 / 營業時間 / 別名 | CASCADE | 餐廳的衍生知識 |
| 餐廳 → 來源實體 | **RESTRICT** | 不可丟失血統;合併時改指向 `merged_into_restaurant_id` |
| 餐廳 → 推薦候選 | **RESTRICT** | 歷史推薦要能解釋;餐廳用軟刪除(`active_status`、`merged_into`) |
| 證據 → 檢查紀錄 | **SET NULL** | 檢查紀錄已複製 `evidence_snapshot`,證據被刪後解釋仍在 |
| 字典表(屬性、來源…)→ 使用者 | RESTRICT(預設) | 不得刪除正在被引用的字典值 |

**Nullable 政策**:缺失的事實一律 `NULL`(= UNKNOWN),不存字串 `'unknown'`。座標成對(同為 NULL 或同有值)。`rating_score` 預留為 NULL。`source_name` 在自然人姓名時必為 NULL。證據只在「有證據」時才有列,沒有列就是 UNKNOWN。

## 6. v2 相對 v1 的變更

1. 個資:`CHECK (NOT name_is_personal OR name IS NULL)`(staging 與來源實體)。
2. 證據:狀態與基礎的合法配對表 + trigger(來源須第一手、店名不得確認 require 類);`CONFIRMED_*` 需 HIGH 信心且 `applies_to = this_branch`;`CONFIRMED_ABSENT` 需 `valid_until` 且 ≤ 180 天;日期先後;唯一性;`applies_to` 區分此分店 / 品牌層級。
3. `ref.attribute` 改為你指定的欄位(`attribute_code`、`display_name_zh`、`attribute_type`、`risk_level`、`description`、`default_unknown_behavior`),共 17 項;新增 `ref.evidence_state_def`、`ref.evidence_basis`、`ref.attribute_implication`、`ref.constraint_reason`、`ref.constraint_decision_rule`(30 列)、`ref.scoring_config`。
4. view:`v_evidence_valid` → `v_evidence_expanded`(含隱含關係)→ `restaurant_attribute_state`(含 `deciding_evidence_id`、`evidence_ids`、`implied`);測試資料需明確開關才可見。
5. 推薦層:新增 `recommendation_constraint_check`(逐人逐屬性逐餐廳,含證據快照)與 `recommendation_score_component`(逐元件、逐人);候選表加入各分數欄位、`warnings`、`explanation`;`recommendation_run` 保存 `config_snapshot` 與 `completed_at`;解釋 view `v_recommendation_explanation`。
6. 引擎:`product.evaluate_session()`(plpgsql 原型,規則表驅動)。
7. 其他:`restaurant.merged_into_restaurant_id`、`pool_status` 與 `active_status` 的一致性約束、`identity.er_config`、`er_review_queue.status`、`ref.today_tpe()`、`set_updated_at` trigger、補索引。
8. 預算:`participant_budget` 加註「僅軟條件」,引擎不讀它做篩選;ref 預設 7 天留存。

## 7. 端到端驗證(種子資料 + 一場 4 人聚餐)

種子:30 家 PoC 餐廳(14 家 `in_pool`)、42 筆來源實體、52 筆料理標籤、24 筆營業時間、26 筆 PoC 證據(**全是「含有 / 可能含有」,沒有任何「不含」**)、3 筆明確標示的測試證據(預設不可見)。

情境(測試用,聚餐中心點為鹽埕埔站):A 花生過敏(allergy → critical)、B 不吃牛(religion → high)、C 吃素(belief_diet → high,預算 150 元)、D 不吃海鮮(dislike → 有效 high);各自有料理偏好。

| 結果 | 數值 |
|---|---|
| 候選池 → 排除 / 通過 | 14 → 5 排除、9 eligible(其中 Top 3 = 3、其餘 eligible 6) |
| 被排除者 | 郭家肉粽(花生 `LIKELY_PRESENT`、critical → 排除)、港園牛肉麵(牛 `CONFIRMED_PRESENT`)、蟳市長 / 老蔡虱目魚粥 / 大溝頂虱目魚米粉湯(海鮮 `CONFIRMED_PRESENT`) |
| Top 3(真實資料) | ① 鴨肉珍 8.0(料理 6 + 距離 1 + 資料可信度 1) ② 阿英排骨飯 7.0 ③ The Borage 琉璃苣 6.0 |
| 鴨肉珍的花生檢查 | 真實資料:`UNKNOWN` → WARN(**critical**),不可顯示安全;測試證據開啟:`CONFIRMED_ABSENT` → PASS(可顯示第一手確認)——只有這一種情況才出現安全標示 |
| 預算 | 沒有任何餐廳因預算被排除;price / rating 元件 0 分、狀態 UNKNOWN;候選的 `warnings` 含 `price_unknown` |

不變量(皆已自動檢查):Top 3 不含被排除者;被排除者無分數與排名;總分 = 元件加總;每個排除都有「哪位參與者 + 哪項屬性」的 EXCLUDE 紀錄;每個非 UNKNOWN 的決定都有證據 id 與快照;`may_show_safe_badge` 只出現在 `CONFIRMED_*`;critical 過敏原永遠不會在非 `CONFIRMED_ABSENT` 時 PASS;所有 UNKNOWN 的花生檢查都帶 critical 警示;解釋中 critical 警示排第一。

**這個結果給產品的訊號**:用真實 PoC 資料時,Top 3 的每一家都有花生(critical)的「資料不足」警示。系統忠實呈現了「我們不知道」——這不是 bug,是目前資料的真實狀態。

## 8. 尚未驗證 / 限制(請不要當作已完成)

- 只在**單一**PostgreSQL 16.2 實例上測;**未**測 PostgreSQL 14 / 15、其他平台、PostGIS。`gen_random_uuid()` 需 PG13+。
- **沒有**併發測試(同時評估、同時寫入證據)、**沒有**效能測試(只有 30 家餐廳)、**沒有**大量資料下的索引驗證。
- 沒有 v1 → v2 的資料遷移腳本(v1 沒有任何正式資料,直接重建)。
- `evaluate_session` 是**原型**:無鎖、用暫存表、沒有權限控管;`radius_m` 已儲存但未使用;`district = session.area` 是目前唯一的地理過濾;未處理「有成員沒填限制」。
- `CONFIRMED_ABSENT` 只代表菜單或聲明沒有該食材,**不代表沒有交叉污染**,schema 無法表達後者。
- 規則矩陣、距離分段、權重、ER 門檻都是**暫定值**;ER 的 gold set 是我自己的判斷、沒有實地驗證(見 `er_v1_spec.md` §7)。
- 稅籍姓名遮罩是啟發式:確定有過度遮罩(例:店名「扁嘴之家」被當成個人名),也可能有漏網。正式 ETL 需更嚴格的 PII 流程。
- Places、評價、價格、Google 營業時間**仍未驗證**,schema 只預留位置(`rating_score` 為 NULL、價格元件固定 UNKNOWN),沒有任何地方假設它們存在。

## 9. 重現方式

```bash
# 需要一個可用的 PostgreSQL;本次用 pgserver 套件的內嵌版本
createdb joeat_v2
psql -d joeat_v2 -v ON_ERROR_STOP=1 -f schema_v2.sql
psql -d joeat_v2 -v ON_ERROR_STOP=1 -f attribute_seed.sql
psql -d joeat_v2 -v ON_ERROR_STOP=1 -f seed_restaurants.sql
JOEAT_PG_URI=postgresql://user@host/joeat_v2 python schema_tests.py   # 需要 psycopg 3;全程在一個交易內執行並 rollback
```

`seed_restaurants.sql` 由 `build_seed.py` 從 PoC 檔案產生(`python -I -X utf8 build_seed.py`)。檔案清單:`schema_v1.sql`(舊版,保留供比對)、`schema_v2.sql`、`attribute_seed.sql`、`seed_restaurants.sql`、`schema_tests.py`、`recommendation_data_contract.md`、`er_v1_spec.md`、`er_v1.py`、`er_v1_config.json`、`er_gold_set.csv`、`build_gold.py`、`validation/*`。

## 附錄:v2.1 修正(MVP 開發時發現)

MVP 的整合測試把 Python 引擎與本 schema 內的 SQL 引擎(`product.evaluate_session`)逐項比對,發現 **SQL 引擎把「沒有座標」的距離算成 −1 分**(落入「更遠」那一格),與合約及 Python 引擎的「0 分 + 警示」不一致。先前的測試沒有抓到,是因為當時所有候選餐廳都有座標;之後加入的一家沒有座標的火鍋店才暴露它。

- 已修正 `schema_v2.sql`(距離為 NULL 時直接 0 分),並同步到 `joeat/backend/app/db/sql/schema_v2.sql`。
- 守護測試在 `joeat/backend/tests/integration/test_engine_parity.py`。本資料夾的 `schema_tests.py` 沒有補這個案例(它的候選全部有座標)。
- 同一輪也修正了 `GET /sessions/{id}/progress` 洩漏 participant_id 的問題(屬於 MVP API,不是 schema)。
