# API

Base URL `http://localhost:8000`。互動文件(可直接試打):`/docs`(Swagger)。JSON、UTF-8。

**身分(MVP)**:沒有登入。加入聚餐時回傳的 `participant_id` 就是代表該成員的憑證,之後填寫限制 / 偏好都用它。`AUTH_MODE=dev` 時 `line_user_id` 由用戶端自報;`AUTH_MODE=line` 時必須附 LIFF `id_token`,後端向 LINE 驗證(**未對真實 LINE 測過**)。原始 LINE id 不會被儲存,只存 HMAC-SHA256。

**隱私**:沒有任何端點會回傳某位成員的限制或偏好內容;`/progress` 也不回傳其他成員的 `participant_id`。

**錯誤格式**:`{"error": "<code>", "message": "..."}`(驗證錯誤為 FastAPI 預設的 `{"detail": [...]}`,HTTP 422)。

| HTTP | `error` | 情況 |
|---|---|---|
| 404 | `not_found` | 聚餐 / 成員 / 餐廳 / 推薦不存在 |
| 409 | `session_full` | 人數已達上限(`min(party_size, 20)`) |
| 409 | `incomplete` | 還有人沒填完(附 `missing_count`);可用 `allow_partial` 強制 |
| 409 | `no_participants` / `session_closed` | 沒人加入 / 聚餐已關閉 |
| 410 | `session_expired` | 聚餐已過期(7 天) |
| 401 | `id_token_required` / `invalid_id_token` | `AUTH_MODE=line` 時 |
| 422 | `unknown_attribute` / `unknown_reason` / `unknown_cuisine` / `unknown_location_preset` / `bad_coordinates` / `outside_taiwan` / `poll_needs_options` / `slot_in_the_past` / `slots_need_poll` | 欄位值不合法 |
| 403 | `host_only` / `not_a_member` | 只有主揪能做 / 這位成員不屬於這場聚餐 |
| 409 | `poll_closed` / `vote_open` / `vote_closed` / `no_recommendation` / `nothing_to_vote_on` | 時間投票或餐廳投票的狀態不允許 |
| 422 | `incomplete_ballot` | 投票要對每間餐廳表態 |

---

## 聚餐

### `POST /sessions` → 201
```json
{ "title": "高中同學聚餐", "date": "2026-11-14", "time": "18:30",
  "location_preset": "yancheng_pu", "party_size": 3 }
```
`title` 必填(1–80 字)。`party_size` 2–20(可省略,bot 建立時常不填)。地點二選一:`location_preset`(見 `/meta/locations`)或 `meeting_lat` + `meeting_lon`(+ `location_label`)。`date` / `time` 是台灣時間。`line_group_id`(可選)會立即雜湊。

**主揪**:`host_line_user_id`(可選,`AUTH_MODE=line` 時要帶 `host_id_token`)會立即雜湊,存成 `host_ref`;之後以同一個 LINE 身分加入的成員 `is_host = true`。沒有主揪的聚餐(例如從 LINE bot 建立)沒有人有主揪權限,任何成員都可以結束投票。

**時間**:預設 `time_mode = "fixed"`(用 `date` / `time`)。`time_mode = "poll"`:改由**大家勾選自己可以的時段**,主揪只設定截止——帶 `time_slots`(2–30 個候選開始時間,沒帶時區視為台灣時間,不能是過去)與 `time_deadline_hours`(1–168,預設 24)。

**攜伴**:`needs_pets` / `needs_kids`(預設 false)是**主揪在聚餐層級**選的「有人帶寵物 / 小孩」,對全組公開(不是任何成員的私人限制)。之後可用 `PUT /sessions/{id}/needs` `{ participant_id, needs_pets, needs_kids }` 修改(主揪才行,403 `host_only`;改了要重新產生推薦才會套用)。規則:
- **寵物**(`pets_allowed`):店家**明確**不讓寵物入內(確認沒有)→ 排除,理由「店家表示不可攜帶寵物入內」;未知或未確認只警示。
- **小孩**(`kid_friendly` = 有兒童座椅或兒童餐):**永遠只警示**,連店家說沒有也不排除(沒有兒童椅不代表不能帶小孩)。
- 目前**沒有任何餐廳有這類資料**,所以全部顯示「資訊不足,請先向店家確認」,直到店家在填寫頁回答、經審核發布。

**地圖選點**:`meeting_lat` / `meeting_lon` 必須在台灣範圍內(否則 422 `outside_taiwan`)。距離鹽埕區中心超過 3 公里時仍可建立,但回應的 `outside_coverage = true`(目前只有鹽埕區有餐廳資料,所有餐廳都會「很遠」),前端據此警告。

回應(實際輸出):
```json
{ "session_id": "138cadea-251e-44b4-a8ff-2e6f8883b41a", "title": "高中同學聚餐", "area": "鹽埕區",
  "location_label": "捷運鹽埕埔站", "meeting_lat": 22.62416, "meeting_lon": 120.28408,
  "meal_time": "2026-11-05T10:30:00Z", "party_size": 3, "status": "collecting",
  "participant_count": 0, "expires_at": "2026-11-09T15:22:37.152748Z",
  "time_mode": "fixed", "time_deadline": null, "time_closed": false, "outside_coverage": false }
```

### `GET /sessions/{session_id}` → 200
同上,`status` 為 `collecting` / `recommended` / `closed`。時間投票過了截止時間會在讀取時自動結束。

### 時間投票(`time_mode = "poll"`)
- `GET /sessions/{id}/time-poll?participant_id=` → 每個時段的人數與「我勾了哪些」(`mine`)。**只有人數,沒有個別成員的選擇。**
- `PUT /participants/{pid}/time-votes` `{ "option_ids": [1, 3] }` → 整組取代我可以的時段(結束後 409 `poll_closed`)。
- `POST /sessions/{id}/time-poll/close` `{ "participant_id" }` → 主揪提前結束。
- 結束條件:截止、主揪結束、或預計人數(`party_size`)都回答了。**可以的人最多的時段**勝出(同數取最早),寫入 `meal_time`;沒人勾選則結束但沒有結果。

## 成員

### `POST /sessions/{session_id}/participants` → 201
```json
{ "line_user_id": "U1234…", "label": "小明" }
```
冪等:同一個 LINE 使用者再次加入會拿到同一個成員。`label` 是顯示給群組的暱稱(請勿用真名;省略則為「成員N」)。
```json
{ "participant_id": "5e4bdcbf-c5ad-4f6e-a1ef-d23d920b0d02", "session_id": "138cadea-…",
  "label": "成員1", "constraints_submitted": false, "preferences_submitted": false }
```

### `GET /participants/{participant_id}` → 200
同上(目前的完成狀態)。

### `GET /participants/{participant_id}/answers` → 200
讀回**自己**已存的硬限制(含原因)、嚴格模式、預算、料理偏好,讓表單能重新打開修改。`participant_id` 就是憑證,別人的答案拿不到。回應也含 `constraints_submitted` / `preferences_submitted`。

### 飲食類型(「飲食 MBTI」,選填、好玩的)
9 題小測驗、3 條軸線、8 種類型。**只是趣味與一個偏好捷徑:不影響任何限制、推薦規則或排名。**
- `GET /meta/diet-types` → 9 題(每題兩個選項,`value` 是軸線字母)、8 種類型(`code`、`emoji`、`name`、`summary`、`suggested_cuisines`)、3 條軸線。軸線:嘗鮮 A ↔ 熟悉 C、濃郁 R ↔ 清爽 L、願意走 W ↔ 想近 N。
- `PUT /participants/{pid}/diet-type` `{ "answers": { "q1": "A", ..., "q9": "N" } }` → 計分並**只存結果類型**(例 `ARW`,不存答案);9 題都要答且字母合法(422 `bad_quiz_answers`)。重測會取代。回傳類型與建議料理(最多 5 種,依「嘗鮮」與「口味」兩軸挑,走路軸不影響料理)。
- `GET /sessions/{id}/diet-types` → **團隊組成**:每種類型的人數與每條軸線的分布,**只有人數、沒有名字**;少於 2 人測過時 `hidden: true`(只有 1 人時看得出是誰)。
- `GET /participants/{pid}/answers` 多了 `diet_type`(自己的)。
- 前端:測驗完按「用這些料理當我的偏好」到偏好頁**預先勾選**(有說明,可自己改,按完成才會存;已存的偏好不會被默默覆蓋)。

### `POST /participants/{participant_id}/constraints` → 200
**整組取代**該成員的硬限制。空陣列是合法的(「我沒有限制」),並把這一步標為完成。
```json
{ "items": [ { "attribute_code": "peanut", "reason": "allergy" }, { "attribute_code": "beef" } ] }
```
`attribute_code` 取自 `/meta/attributes`(beef、pork、seafood、shellfish、offal、raw_food、peanut、tree_nut、milk、egg、sesame、soy、gluten、vegetarian、vegan、halal、gluten_free)。`reason`(可選):`allergy` / `medical` / `religion` / `belief_diet` / `dislike` / `unspecified`;只會**提高**風險等級;省略時,過敏原類預設 `allergy`。`budget_max_per_person`(可選,整數)只是軟條件,**永遠不會排除餐廳**。`reason` 同時決定這條限制是**安全型**(`allergy` / `medical` / `religion`)還是**偏好型**(`belief_diet` / `dislike`);沒填時用屬性預設(過敏原、無麩質為安全型)。`strict_allergy`(可選,預設 false):**嚴格過敏模式**,只有這位成員自己的安全型「不吃」限制會要求店家確認才通過;每次整組取代都會重設。
```json
{ "saved": 2, "participant": { "participant_id": "…", "session_id": "…", "label": "B", "constraints_submitted": true, "preferences_submitted": false } }
```

### `POST /participants/{participant_id}/preferences` → 200
整組取代。沒列出的料理 = 沒意見。
```json
{ "items": [ { "cuisine_tag": "日式", "stance": "love" }, { "cuisine_tag": "小吃", "stance": "dislike" } ] }
```
`stance`:`love`(🔥 很想吃 +3)、`ok`(👍 可以 +1)、`any`(😐 都好 0)、`dislike`(👎 不太想 −1)。

### `GET /sessions/{session_id}/progress?participant_id=…` → 200
只有計數與完成與否。`participant_id` 可選,用來把那位成員標成 `is_me`。
```json
{ "session_id": "138cadea-…", "party_size": 3, "joined": 3, "constraints_done": 3, "preferences_done": 3,
  "participants": [ { "label": "B", "is_me": false, "constraints_done": true, "preferences_done": true },
                    { "label": "成員1", "is_me": true, "constraints_done": true, "preferences_done": true } ],
  "all_complete": true, "ready_for_recommendation": true, "missing_count": 0 }
```
`ready_for_recommendation` = 已加入的人全部填完且至少 2 人。

## 推薦

### `POST /sessions/{session_id}/recommendations?include_excluded=false` → 201
Body(可省略):`{ "allow_partial": false }`。未填完時回 409 `incomplete`;`allow_partial: true` 則用目前已加入的人執行。每次呼叫都會產生新的 run 並完整存證。

### `GET /sessions/{session_id}/recommendations?include_excluded=false` → 200
回傳最近一次完成的 run(404 = 尚未產生)。兩個端點的回應格式相同(實際輸出,`top3` 只留第 1 名):
```json
{
  "run_id": "d65d7f19-c294-4879-9402-5c23cd806975", "session_id": "138cadea-…", "created_at": "2026-11-02T15:23:35.975742Z",
  "scoring_version": "v1", "participants": 3, "party_size": 3,
  "pool_size": 15, "excluded_count": 2, "eligible_count": 13,
  "top3": [ {
    "rank": 1, "restaurant_id": "5c3168d6-81a3-50ff-a52e-c4459bc973cd", "name": "東京小城", "address": null, "phone": null,
    "cuisines": ["熱炒", "中式", "日式"], "distance_m": 102,
    "score": { "cuisine": 3.0, "distance": 2.0, "data_confidence": 0.0, "rating": null, "total": 5.0 },
    "hard_constraint": { "status": "no_known_conflict", "unknown_attributes": ["牛肉", "花生"], "confirmed_safe": [],
                         "note": "已知資料中沒有發現衝突；資料不足的項目不代表安全" },
    "warnings": [
      { "code": "attribute_unknown", "level": "critical", "text": "花生資訊不足，建議向店家確認", "attribute": "peanut", "display": "花生" },
      { "code": "attribute_unknown", "level": "high", "text": "牛肉資訊不足，建議向店家確認", "attribute": "beef", "display": "牛肉" },
      { "code": "hours_unknown", "level": "normal", "text": "營業時間資訊不足", "attribute": null, "display": null },
      { "code": "status_unverified", "level": "normal", "text": "營業狀態未驗證", "attribute": null, "display": null } ],
    "reasons": [ "1/3 人偏好日式", "已知資料中，沒有任何人的硬限制被違反（資料不足的項目見警示）", "距離集合點約 102 公尺" ],
    "summary": "總分 5：料理偏好 3、距離 2、資料可信度 0；評價與價格尚無可靠資料，未計分" } ],
  "excluded": null,
  "disclaimer": "推薦只依據目前蒐集到的資料。標示「資訊不足」的項目代表我們無法確認，不代表安全；過敏或嚴格飲食請務必向店家確認。"
}
```
- 第三輪(推薦整合)新增:每家餐廳多了 `declarations`(店家聲明的帶日期事實陳述:`{attribute, display, text, verified}`,例:「店家於 2026/11/04 聲明其目前菜單未使用乳製品;共用設備資訊:確認沒有共用。已由揪呷人工驗證身分。」),整份回應多了 `strict_mode`(有成員開啟嚴格過敏模式,群組層級、不說是誰)。規則見 [決策紀錄](docs/decisions/0001-merchant-declaration.md)「整合後的行為」。
- 每家餐廳多了 `needs`:`[{ code: "pets" | "kids", name, status: "yes" | "maybe" | "no" | "unknown", text }]`(沒有選攜伴時為空)。店家聲明以帶日期的事實呈現,例如「店家於 2026/11/01 聲明可攜帶寵物入內。已由揪呷人工驗證身分。」。寵物 / 小孩**不會**出現在食材警示、`unknown_attributes` 或 `declarations` 裡。
- 新的警示 `code`:`attribute_present_some`(偏好型限制 + 店家表示只有些餐點含有 → 注意)、`attribute_cross_contact_possible`(店家聲明沒有,但共用設備可能有交叉接觸)、`attribute_declared_shared_unknown`(店家聲明沒有;共用設備資訊未知)。
- `hard_constraint.status`:`no_constraints` / `no_known_conflict` / `partial_conflict`(店家表示只有些餐點含有不想吃的食材)/ `suspected_conflict`。**沒有「safe」這個值**;`confirmed_safe` 只有在有第一手「確認不含」證據時才會有內容(目前資料中不存在)。
- `warnings[].level`:`critical`(重要)> `high`(注意)> `normal`(提醒)。`code` 可能是 `attribute_unknown`(資訊不足)、`attribute_likely_absent`(推測沒有,視同資訊不足)、`attribute_likely_present`(資料顯示可能含有,未確認),或非屬性警示 `hours_unknown`、`hours_conflict`、`price_unknown`、`distance_unknown`、`status_unverified`。
- `score.rating` 目前永遠是 `null`(沒有可靠評價來源)。
- `include_excluded=true` 會多回 `excluded: [{restaurant_id, name, reasons: ["牛肉：此店含有/疑似含有"]}]`——只有被哪項條件排除,**沒有是誰的條件**。

## 最後投票(拉桿)

對一次推薦的 Top 3,**每位成員對每間餐廳拉一個 0–10 的桿**(0 不太想去、10 很想去),或選「都可以」(記為中性 5)。投票中**只顯示已投人數**,看不到任何人的票;結束後才公布統計。

- `POST /sessions/{id}/votes` `{ "participant_id", "closes_in_hours": 24 }` → 201。主揪才能發起(沒有主揪的聚餐任何成員都可以);需要先有推薦(409 `no_recommendation`);同時只能有一場進行中(409 `vote_open`)。選項是最近一次推薦的 Top 3(**都已通過所有硬限制**),並凍結當時的卡片(警示、店家聲明)。
- `GET /sessions/{id}/votes/current?participant_id=` → 狀態、選項、我的票(`my_score` / `my_any_ok`)、`voted` / `joined`;結束後才有 `result` 與 `winner_restaurant_id`。
- `PUT /votes/{vote_id}/ballot` `{ "participant_id", "scores": [{ "restaurant_id", "score": 0–10, "any_ok": false }] }` → 整張票取代,必須涵蓋每間餐廳(422 `incomplete_ballot`)。
- `POST /votes/{vote_id}/close` `{ "participant_id" }` → 主揪提前結束。
- 結束條件:截止、主揪結束、或所有已加入的人(至少 2 人)都投了。
- **勝出規則**:總分最高;同分取「最低分較高者」(沒人討厭的那間),再取很想去(≥ 8)人數,最後取推薦排名較前者(`tie_broken = true`)。統計只含總分、平均、投票人數、很想去 / 不太想(≤ 2)/ 都可以的人數。

## 餐廳

### `POST /restaurants/{restaurant_id}/reports` → 201
「回報資料錯誤」。**只會進審核佇列,不會改變任何推薦結果。**
```json
{ "participant_id": "…", "kind": "wrong_info", "attribute_code": "milk", "note": "選填,300 字內" }
```
`kind`:`wrong_info` / `allergic_reaction` / `closed` / `other`。限制:`participant_id` 必須是存在的成員;該店必須出現在**該成員自己那場聚餐**的推薦結果裡(否則 403 `not_a_candidate`);每人 24 小時最多 3 次(429 `rate_limited`),同一店同一項不能重複(429 `already_reported`);每家店最多 30 筆待處理(429 `queue_full`)。審核者在 `/ops/reports` 處理,看不到回報人。

### `GET /restaurants/{restaurant_id}` → 200
身分、料理標籤、營業時間(原文 + 一致性)、**每個已知屬性的證據**(狀態、依據、信心、來源網址、驗證日期、有效期限)、來源清單與備註。沒有證據的屬性不會列出(= 資訊不足,不代表安全)。

## UI 中繼資料

| 端點 | 內容 |
|---|---|
| `GET /meta/attributes` | 三組硬限制(不吃的食材 / 過敏原 / 飲食需求)、每項的類型與風險等級、可選原因、隱私提示「其他人不會看到你的個人需求。」 |
| `GET /meta/cuisines` | 14 個料理 chip(台式、中式、日式、韓式、火鍋、燒肉、熱炒、小吃、義式、美式、東南亞、印度料理、甜點、咖啡)與 4 種態度 |
| `GET /meta/locations` | 鹽埕區集合點預設(座標來自 OSM 捷運 / 輕軌站) |
| `GET /healthz` | 資料庫連線檢查 |

## LINE webhook

`POST /line/webhook`(LINE Platform 呼叫)。驗證 `X-Line-Signature`;未設定 `LINE_CHANNEL_SECRET` 時回 503(`LINE_SKIP_SIGNATURE=true` 僅限本機)。處理文字訊息(指令見 SETUP.md)與 `join` 事件。`LINE_DRY_RUN=true`(預設)時不呼叫 LINE,而是在回應裡列出會送出的訊息。

## 審核 API(`/ops/*`,店家聲明)

給營運 / 審核者用。**不是給消費者或店家的 API。** 設計與決策:[docs/decisions/0001-merchant-declaration.md](docs/decisions/0001-merchant-declaration.md)。

**存取**:標頭 `X-Ops-Key`(= 環境變數 `OPS_API_KEY`)與 `X-Ops-User`(你的名字,寫進稽核紀錄)。`OPS_API_KEY` 未設定時整組回 503 `ops_disabled`;金鑰錯誤 401 `bad_ops_key`;缺名字 400 `ops_user_required`。**這是試辦等級的閘門:一把共用金鑰、名字是自述的,不是使用者管理。** 資料庫規則被違反時回 409 `rule_violation`(訊息為資料庫的原文)。

| 端點 | 說明 |
|---|---|
| `POST /ops/claims` `{restaurant_id}` → 201 | 建立邀請。回傳 `token`(**只出現這一次**,資料庫只存 SHA-256) |
| `GET /ops/claims/{id}` | 認領狀態、驗證方式 / 等級 / 驗證者 / 時間 / 備註 |
| `POST /ops/claims/{id}/verify` `{method, note, claimant_role?}` | 記錄**怎麼驗證的**。`method`:`phone_callback` / `onsite_visit` / `official_menu_review`(→ strong)、`official_channel_message`(→ basic)。`note` 至少 5 字(實際做了什麼)。驗證者 = `X-Ops-User` |
| `POST /ops/claims/{id}/revoke` | 撤銷 |
| `GET /ops/declarations?status=submitted` | 審核清單(含每份聲明的矛盾數) |
| `GET /ops/declarations/{id}` | 審核者要看的全部:認領與驗證、19 項答案、**發布預覽**(`plan`:每項會寫入的狀態 / 基礎 / 信心 / 範圍 / 是否被共用設備降級 / 與哪些既有證據矛盾)、矛盾證據內容、稽核紀錄 |
| `POST /ops/declarations/{id}/publish` `{supersede?: false}` | 核准並寫入第一手證據。與 `LIKELY_*` 證據矛盾 → 409,除非 `supersede: true`(留稽核);與 `CONFIRMED_*` 矛盾 → **永遠 409** |
| `POST /ops/declarations/{id}/needs-info` / `reject` `{note}` | 退回補件 / 駁回,`note` 必填(至少 5 字) |
| `POST /ops/declarations/{id}/withdraw` `{note}` | **撤下已發布(approved)的聲明**(菜單改了 / 店家要求 / 不再信任)。「沒有 X」類(正向)證據**立即失效**;「含有 X」類風險資訊保留到原有效期限。聲明列保留、狀態變 `withdrawn`,稽核寫入原因與失效 / 保留筆數,店家可重新填寫。非 approved → 409,`note` 至少 5 字(422) |
| `POST /ops/incidents` `{restaurant_id, severity, attribute_code?, description?}` → 201 | 登錄事故。`allergic_reaction` 或 `wrong_info` 會**立即暫停**該店的正向(安全)聲明 |
| `GET /ops/incidents?status=open` | 事故清單(含被暫停的證據數) |
| `POST /ops/incidents/{id}/resolve` `{outcome}`(`confirmed` 或 `dismissed`) | `dismissed` 恢復聲明;`confirmed` 作廢被暫停的證據並撤銷該店所有已驗證的認領 |

使用者回報:`GET /ops/reports?status=open|escalated|dismissed`(含「此店待處理的不同回報人數」,不含回報人)、`POST /ops/reports/{id}/dismiss` 與 `/escalate`,body `{note}`(至少 5 字)。`escalate` 會建立商家事故;過敏反應 / 資訊錯誤會立即暫停該店的正向聲明。已處理的回報再處理回 409 `already_handled`。

另有 `GET /ops/claims`(認領清單)與 `GET /ops/restaurants?q=`(搜尋餐廳,給邀請與事故表單用)。`POST /ops/claims` 可帶 `is_demo: true` 建立**示範認領**:它的聲明只會發布到隱藏的測試來源,且 `ALLOW_TEST_EVIDENCE` 未開時整組被拒絕(409 `demo_disabled`)。

`X-Ops-User` 是 HTTP 標頭,只能是 ASCII:瀏覽器端用 `encodeURIComponent` 送出,後端 `unquote` 後才記進稽核紀錄,所以中文姓名可用,純英文名字照舊可用。

審核畫面在前端 `/ops`(聲明審核 / 認領與驗證 / 事故三個分頁);金鑰與姓名只存在該分頁的 `sessionStorage`。

## 店家 API(`/merchant/*`)

給店家填寫頁(前端 `/m/{token}`)用。**認證是邀請 token,放在標頭 `X-Claim-Token`,絕不放網址**(網址會進存取紀錄)。token 不認識 → 一律 404(不透露是否存在);已撤銷 / 過期 → 410。尚未做速率限制。

| 端點 | 說明 |
|---|---|
| `GET /merchant/form-spec` | 19 題(17 題食材 / 飲食 + 2 題入座需求:可攜寵物、親子友善)的題目、選項、切結文字與版本(`attest-v0-draft`,**尚未經法務審閱**) |
| `GET /merchant/me` | 這家店的基本資料、認領狀態、`can_declare`(只有已驗證才為 true)、`demo` |
| `POST /merchant/declaration` | 開始填寫(建立草稿) |
| `GET /merchant/declaration` | 目前的草稿 / 已送出的內容與狀態 |
| `PUT /merchant/declaration/items` | 儲存答案(每題 `answer`、`cross_contact_status`、`note` ≤ 300、`certificate_ref` ≤ 100)。送出後凍結 |
| `PUT /merchant/declaration/menu` | 儲存菜單連結(必須是 http(s)) |
| `GET /merchant/declaration/preview` | 「顧客會看到什麼」:用與發布**同一個** `declaration_plan()` 算出,措辭由 `core/merchant_form.py` 產生,禁用「安全 / 保證 / 100% / 無過敏原 / 零過敏」。共用設備為「可能 / 未知」時,「完全沒有」會降級顯示為「目前未確認含有 X」 |
| `POST /merchant/declaration/submit` `{role, menu_as_of, accepted, attestation_version}` | 送出審核(必須勾選同意、版本須相符) |

店家的答案**不會**直接進入推薦:一律經審核者發布(`/ops/declarations/{id}/publish`)才寫入證據。示範認領的 API 回應與預覽帶 `demo: true`,前端據此顯示橫幅。

## 推薦回應中的示範旗標

`POST / GET /sessions/{id}/recommendations` 的回應多了 `test_evidence_enabled`(= `ALLOW_TEST_EVIDENCE`)。為 true 時前端結果頁會顯示「示範資料模式」橫幅,避免把假的店家聲明當成真實資訊。
