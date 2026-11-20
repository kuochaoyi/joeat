# 推薦資料合約(Recommendation Data Contract)v1

適用:LINE Bot + LIFF 聚餐決策,2–20 人。本文件是「資料 → 推薦」的規則,不是 UI 文案。
對應實作:`schema_v2.sql`(`ref.constraint_decision_rule`、`product.evaluate_session`)、`attribute_seed.sql`(規則內容)、`schema_tests.py`(驗收測試,110 項)。
規則改動必須同時改 `attribute_seed.sql` 並讓 `schema_tests.py` 通過;不得只改程式。

## 0. 不可違反的原則

1. **UNKNOWN ≠ SAFE。** 沒有證據列就是 UNKNOWN;UNKNOWN 不排除,但一定產生警示。
2. **LIKELY_ABSENT ≠ SAFE。** 只代表「沒看到」或弱證據,處理方式與 UNKNOWN 相同(視同未知)。
3. **只有第一手的 CONFIRMED_ABSENT 才是「安全」的正向證據**,而且有效期限最多 180 天。對 critical 過敏原更沒有例外。
4. **預算不是硬條件。** 目前沒有可靠的人均價格資料。
5. **不假設 Places、評價、價格、Google 營業時間存在。** 它們在資料與分數中都以 UNKNOWN / NULL 保留位置,不加分、不扣分、不排除。
6. **每個決定都要能追溯**:哪個參與者、哪個條件、哪筆證據、哪個來源、何時驗證。
7. 自然人姓名不進正式資料庫;LINE user/group id 只存 hash。

## 1. Hard Constraint 與 Soft Preference

| 類別 | 項目 | 資料位置 | 處理 |
|---|---|---|---|
| **Hard** | 過敏、絕對不吃、飲食需求(`ref.attribute` 17 項) | `product.participant_hard_constraint` | 查規則表:排除 / 保留加警示 / 通過 |
| Soft | 想吃的料理(很想吃 / 可以 / 都好 / 不太想) | `product.participant_preference` | 計分 |
| Soft | 預算上限 | `product.participant_budget` | **只作提示**,無價格資料 → UNKNOWN,不排除、不計分 |
| Soft | 距離 | `dining_session.meeting_*` 與餐廳座標 | 計分;缺座標 → UNKNOWN,不排除 |
| Soft | 資料可信度 | 身分對應的獨立來源數 | 計分(加分制) |
| Soft(未啟用) | 評價 | — | 預留 `rating_score`,目前 NULL |
| 提示 | 營業時間 | `enrichment.restaurant_opening_hours` | 不計分;無資料 / 有衝突 → 警示 |

**群組規則**:任何一位參與者的 EXCLUDE 都會排除該餐廳(全體生效)。警示則逐人保留,不合併、不覆蓋。

## 2. 屬性(`ref.attribute`)

`attribute_type`:`avoid`(希望沒有)/ `require`(希望有)。`risk_level`:`critical` / `high` / `normal`。

| 代碼 | 名稱 | 類型 | 風險 | 代碼 | 名稱 | 類型 | 風險 |
|---|---|---|---|---|---|---|---|
| peanut | 花生 | avoid | critical | seafood | 海鮮 | avoid | high |
| tree_nut | 堅果 | avoid | critical | beef | 牛肉 | avoid | high |
| shellfish | 甲殼類/貝類 | avoid | critical | pork | 豬肉 | avoid | high |
| milk | 乳製品 | avoid | critical | raw_food | 生食 | avoid | high |
| egg | 蛋 | avoid | critical | offal | 內臟 | avoid | normal |
| sesame | 芝麻 | avoid | critical | vegetarian | 素食 | require | high |
| soy | 大豆 | avoid | critical | vegan | 純素 | require | high |
| gluten | 麩質 | avoid | critical | halal | 清真 | require | high |
| | | | | gluten_free | 無麩質 | require | critical |

- **蘊含關係**:`shellfish ⇒ seafood`、`vegan ⇒ vegetarian`。子項「存在」推得父項「存在」;父項「不存在」推得子項「不存在」。推得的證據在 view 標記 `implied = true`。
- **有效風險**:`max(屬性風險, 原因風險)`。原因 `allergy`、`medical` → critical;`religion`、`belief_diet` → high;`dislike`、`unspecified` → normal。原因只會**提高**風險,不會降低。例:使用者因口味不吃海鮮,有效風險仍是 high(屬性本身 high)。

## 3. 五種證據狀態

| 狀態 | 意義 | 允許的證據基礎 | 可用於 Hard Constraint? | 可顯示「安全/符合」? |
|---|---|---|---|---|
| `CONFIRMED_PRESENT` | 已確認含有 / 已確認提供,指向此店此分店 | 官方菜單、店家聲明;店名本身直接含該品項(僅限 avoid 類) | 是(單獨可觸發排除或通過) | 僅 require 類可顯示「已確認提供」 |
| `LIKELY_PRESENT` | 很可能含有 / 很可能提供 | 菜單提及、媒體菜名、OSM 標籤、類別推論、品牌層級資料 | 是,依風險等級(見 §4) | 否(最多「可能符合,未經店家確認」) |
| `LIKELY_ABSENT` | 推測沒有 / 推測不提供 | 媒體、OSM、類別推論、菜單未列但無聲明 | **否**(視同 UNKNOWN) | **否** |
| `CONFIRMED_ABSENT` | 已確認不含 / 已確認不提供 | **只有**官方菜單、店家聲明;來源必須是第一手;信心必須 HIGH;必須有 `valid_until` 且 ≤ 驗證日 + 180 天;必須指向此分店 | 是 | **是**(avoid 類:唯一正向安全證據) |
| `UNKNOWN` | 沒有可靠證據(合法狀態) | 沒有證據列;或明確記錄「已查過但無資訊」 | 否 | **否** |

資料庫強制(不是慣例):
- `CONFIRMED_ABSENT` 的來源必須 `is_first_party`;基礎只能是 `official_menu` / `restaurant_declaration`;`valid_until` 必填且 ≤ 180 天;信心必須 HIGH;`applies_to` 必須是 `this_branch`(品牌層級資料,例如九記總店的菜單,最多是 `LIKELY_*`)。
- `CONFIRMED_*` 一律需要 HIGH 信心;店名只能確認 avoid 類的「存在」,不能確認 require 類(店名有「素食」不等於能確認素食)。
- 證據過期(`valid_until` 已過,以台灣時間日期計)自動失效,回到 UNKNOWN。
- 測試資料(`is_test` 來源)預設不可見,必須明確設定 `joeat.allow_test_evidence = 'on'`。

**同一屬性多筆證據的合併(保守)**:avoid 類,任何「存在」證據勝過任何「不存在」證據;require 類,任何「不存在」證據勝過「存在」證據。`deciding_evidence_id` 記錄是哪一筆決定了狀態。

## 4. 決策矩陣(`ref.constraint_decision_rule`,共 30 列)

動作:`EXCLUDE` 排除;`WARN` 保留並警示;`PASS_CONDITIONAL` 有條件通過(附警示);`PASS` 通過。警示等級:`critical` > `high` > `normal`。

**avoid 類**

| 證據狀態 | critical | high | normal |
|---|---|---|---|
| CONFIRMED_PRESENT | EXCLUDE | EXCLUDE | EXCLUDE |
| LIKELY_PRESENT | **EXCLUDE** | **EXCLUDE** | WARN(high) |
| UNKNOWN | WARN(**critical**) | WARN(high) | WARN(normal) |
| LIKELY_ABSENT | WARN(**critical**)* | WARN(high)* | WARN(normal)* |
| CONFIRMED_ABSENT | PASS ✓ | PASS ✓ | PASS ✓ |

\* 視同 UNKNOWN。✓ = 允許顯示「已有第一手資料確認」。

**require 類**

| 證據狀態 | critical | high | normal |
|---|---|---|---|
| CONFIRMED_PRESENT | PASS ✓ | PASS ✓ | PASS ✓ |
| LIKELY_PRESENT | PASS_CONDITIONAL(critical) | PASS_CONDITIONAL(normal) | PASS_CONDITIONAL(normal) |
| UNKNOWN | WARN(critical) | WARN(high) | WARN(normal) |
| LIKELY_ABSENT | **EXCLUDE** | **EXCLUDE** | WARN(normal) |
| CONFIRMED_ABSENT | EXCLUDE | EXCLUDE | EXCLUDE |

### 4.1 直接排除
任一參與者的任一條件落在 EXCLUDE 格。被排除的餐廳**不進計分**,但完整保留在 `recommendation_candidate`(`stage='excluded'`)與 `recommendation_constraint_check`,供除錯與解釋。

### 4.2 保留但必須警示
所有 WARN / PASS_CONDITIONAL。警示文字必須說明「**資料不足,無法確認,請向店家確認**」,並顯示對象(哪位參與者的哪項條件)。**critical 警示必須在卡片上直接可見**,不可收進展開區。解釋 view 以 critical → high → normal 排序(已測試)。

### 4.3 允許推薦
餐廳沒有任何 EXCLUDE 即為 eligible。eligible ≠ 安全:卡片上必須同時呈現它的所有警示。只有 `may_show_safe_badge = TRUE` 的檢查結果才能顯示正向標示,且要附 `last_verified_at` 與 `valid_until`。

### 4.3.1 成員層級的兩個調整(矩陣之外)

矩陣查完後,引擎還依「這位成員為什麼避開它」做兩個調整(實作與理由見 [docs/decisions/0001-merchant-declaration.md](decisions/0001-merchant-declaration.md)「整合後的行為」):**偏好型限制 + 店家聲明「只有些餐點含有」→ 排除降為警示**(critical 屬性與安全型限制不降);**嚴格過敏模式**(成員自選)→ 該成員安全型限制的 UNKNOWN / LIKELY_ABSENT 改為排除。兩者都不會把任何東西標成「安全」,也不影響分數。

### 4.4 零個或不足 3 個 eligible
- 不足 3 家:有幾家推薦幾家。
- 零家:回傳空的 Top 3 與排除統計(哪些條件排除了多少家)。**不得自動放寬任何硬條件**;可以建議使用者自己調整。

## 5. 預算

1. `participant_budget` 永遠不是篩選條件。
2. 有人均價格資料(目前不存在):未來可作 Soft Ranking,分數另訂。
3. 無價格資料:`price` 分數元件記為 UNKNOWN,0 分;餐廳 `warnings` 加入 `price_unknown`;UI 顯示「**價格資訊不足**」。
4. 不得因為缺價格而排除或降低排名。
5. 升級為硬條件的前提:人均價格有可靠來源與覆蓋率(建議門檻另行決定),且價格證據同樣帶 source / confidence / last_verified_at。

## 6. 候選池(進入計分前)

`pool_status = 'in_pool'` 且 `active_status IN ('active','unverified')` 且未被合併,且 `district = session.area`。
- `closed`、`not_a_restaurant` 不進池;資料庫約束禁止 closed 的店標成 in_pool。
- `unverified` 允許進池,但 UI 要標示「營業狀態未驗證」。稅籍沒有歇業狀態,OSM 可能過期,所以幾乎所有餐廳目前都是 unverified。
- 單一來源、未經第二來源佐證的店維持 `candidate`,不進推薦池。

## 7. 計分 v1(deterministic,無 ML)

`total = cuisine_score + distance_score + data_confidence_score + rating_score(NULL→0)`;只對 eligible 計分。權重存於 `ref.scoring_config`(版本化),每次 run 保存 `config_snapshot`,舊結果永遠能重算與解釋。

| 元件 | 規則 | 預設值 |
|---|---|---|
| 料理偏好(逐人) | 該參與者偏好的料理標籤命中餐廳標籤(含父分類):很想吃 +3、可以 +1、都好 0、不太想 −1;多個命中取最高;未命中 0 | `cuisine_stance_points` |
| 距離 | ≤300 m +2;≤600 m +1;≤1000 m 0;更遠 −1;缺座標 0 並警示 `distance_unknown` | `distance_bands_m` |
| 資料可信度 | 身分對應有 ≥2 個**獨立來源類型**且已確認(auto / manual_confirmed)+1;其餘 0。**資料不足不加分、也不扣分** | `data_confidence` |
| 評價 | 目前 UNKNOWN,0 分,`rating_score` 保持 NULL | 未啟用 |
| 價格 | UNKNOWN,0 分(見 §5) | 不計分 |

- **UNKNOWN 警示不扣分**,但獨立記錄(`recommendation_constraint_check`、`warnings`),且參與排序的次要鍵。
- 營業時間:不計分;無資料 → `hours_unknown`,有衝突 → `hours_conflict`。

### Top 3 排序
依序:`total_score` 高者先 → `critical_warning_count` 少者先 → `warning_count` 少者先 → 距離近者先(缺值最後)→ `restaurant_id`(確保結果可重現)。取前 3。

**注意**:同分時「critical 警示少」會勝出,代表資料較完整的店在同分時優先;但分數本身不因警示扣分,所以總分高、但有 critical 警示的店仍可能進 Top 3。這是刻意的:安全資訊靠**警示呈現**,不靠悄悄降分。

## 8. 每個推薦必須能回答的問題(schema 對照)

| 問題 | 儲存位置 |
|---|---|
| 是否被排除 | `recommendation_candidate.stage` |
| 排除原因 | `recommendation_constraint_check.action = 'EXCLUDE'` + `message_zh` |
| 觸發哪位參與者的限制 | `…constraint_check.participant_id`(複合外鍵保證屬於同一個聚餐) |
| 哪個 attribute | `…constraint_check.attribute_code`、`attribute_type`、`effective_risk_level` |
| 哪筆證據 | `deciding_evidence_id`(證據被刪則 SET NULL)+ `evidence_snapshot`(文字、基礎、來源、信心、日期的副本) |
| 哪些條件 UNKNOWN | `…constraint_check.evidence_state IN ('UNKNOWN','LIKELY_ABSENT')`;`explanation.unknown_attributes` |
| 料理分數 / 距離分數 / 資料可信度 / 未來評價分 / 總分 | `recommendation_candidate.cuisine_score / distance_score / data_confidence_score / rating_score / total_score` |
| 每個元件的明細(含逐人) | `recommendation_score_component`(`points`、`raw_value`、`detail`) |
| 非屬性警示 | `recommendation_candidate.warnings`(`hours_unknown`、`price_unknown`、`distance_unknown`…) |
| 當時用了什麼權重 | `recommendation_run.config_snapshot` |

`product.v_recommendation_explanation` 一次回傳上述內容。驗收:`schema_tests.py` 對「總分 = 元件加總」「排除必有 EXCLUDE 紀錄」「非 UNKNOWN 的決定必有證據引用」「safe badge 只出現在 CONFIRMED_*」皆有不變量檢查。

## 9. 已知限制(尚未解決,不得假裝已解決)

1. **目前沒有任何 `CONFIRMED_ABSENT` 的真實資料**。PoC 的證據全是「含有 / 可能含有」。種子資料中僅有 3 筆 `source_type='test_fixture'` 的測試證據(預設不可見)。因此在現有資料下,過敏原的 UNKNOWN 警示會出現在幾乎所有推薦上。第一手資料(店家自填)是唯一能改變這件事的路。
2. `radius_m` 已儲存但引擎尚未使用;距離只計分。
3. 交叉污染(cross-contact)無法用此模型表達:`CONFIRMED_ABSENT` 只代表「菜單/聲明中不含該食材」,**不是**「廚房無交叉污染」。critical 過敏原的 UI 仍需附註「請向店家確認處理方式」。
4. 規則矩陣、權重、距離分段都是**暫定值**,尚未用真實使用資料調整。
5. 尚未處理「有成員沒填限制」:建議 UI 顯示「N 位成員尚未填寫」,引擎不自行補預設值。
