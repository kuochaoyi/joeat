# Entity Resolution v1 規格(OSM / 稅籍 / 未來 Places)

狀態:**所有門檻與權重都是暫定(provisional)**,存放在 `er_v1_config.json` 與資料表 `identity.er_config`,不得寫死在程式裡。
目的:判斷「兩個來源的紀錄是不是同一家餐廳」,並把不確定的送人工,而不是硬猜。
實作原型:`er_v1.py`;回歸測試資料:`er_gold_set.csv`(45 組);基準結果:`validation/er_v1_baseline.txt`。

## 1. 為什麼需要 v1(v0 看到的問題)

| v0 的問題 | 例子(真實資料) | v1 的對策 |
|---|---|---|
| 純字串相似度不夠 | 港園牛肉麵 ↔ 港園麵館 只有 0.75;千葉養生素食 ↔ 仟悅素食養生自助餐館 只有 0.27 | 地址、類別、IDF 加權的 token 相似度合併計分 |
| 同址多戶 | The Borage 所在門牌有 8 筆登記;黛麗莎與老宋同址 | 同址多戶懲罰 + 名稱必須能區分 |
| 共用 token 造成誤併 | 郭家肉粽 ↔ 孫家肉粽;黑乾溫州餛飩大王 ↔ 金溫州餛飩大王 | 通用詞降權(IDF)、通用名稱懲罰 |
| 地址有誤 | 田記豆漿(OSM 門牌錯);九記(路名「鹽埕路」錯字) | 路名後綴容錯、門牌主號比對、名稱可補救 |
| 同址、行業不符 | 柒壹喫堂的門牌登記的是美髮沙龍 | 稅籍非餐飲行業 → 類別否決 |
| OSM 無地址 | OSM 約 64% 的餐飲點沒有地址 | 需要座標距離(見 §6 的結構性限制) |

## 2. 正規化

**地址**(輸出鍵 `(路/街, 巷弄, 門牌主號, 副號)`)
1. Unicode NFKC(全形數字轉半形)。
2. **去掉開頭的郵遞區號**(OSM `addr:full` 常是 `803高雄市…`;PoC 就曾因漏掉這步低估比對數)。
3. 各種破折號(`- － ― — – ‑`)統一視為副號「之」。
4. 去掉「高雄市」「鹽埕區」「○○里」「N 樓」「之後的括號說明」。
5. 解析 `路|街` + 可選 `N巷` `N弄` + `N號`(`之M` 為副號)。無法解析 → 地址視為缺失(不扣分)。

**名稱**
1. NFKC、轉小寫、去空白與標點、去括號內文字(例:`(總店)`)。
2. 去除不具辨識力的詞:公司型態(股份有限公司、有限公司、企業社、商行、商號)、`店`、`館`、`餐飲`、`食品`、`工作室`、`鹽埕`、`高雄`、`總店`、`分店`。
3. 稅籍名稱若為 `[個人名]`(已遮罩)或清完為空 → 名稱分 0,不可靠名稱判斷,只剩地址與類別。
4. 別名:OSM `name:en` / `alias` / `old_name`,以及 `identity.restaurant_alias`,逐一比對取最高。

## 3. 候選產生(blocking)

對每個 OSM 實體,稅籍候選 = 「同址鍵(路 + 巷 + 主號)」**或**「名稱分 ≥ 20」。未來加入:座標距離 ≤ 150 m(需稅籍地址 geocode)。候選之外不計分。

## 4. 計分

```
score = address_score + name_score + geo_score + category_score − ambiguity_penalty
```

| 元件 | 規則(暫定值,見 `er_v1_config.json`) | 分數 |
|---|---|---|
| **address_score** | 路/巷/主號/副號全同(exact key) | +40 |
| | 主號同、副號不同(例:146 vs 146 之 2) | +30 |
| | 主號與巷同,路名僅差後綴 `路`/`街`(例:鹽埕路 vs 鹽埕街) | +25 |
| | 同路、相距 ≤2 號、奇偶相同 | +10 |
| | 兩邊都有地址但不同 | −10 |
| | 任一邊缺地址 | 0(不扣分) |
| **name_score**(0–40) | 清理後完全相同 | 40 |
| | 一方包含另一方且較短者 ≥ 3 字 | 34 |
| | 別名完全相同 | 36 |
| | 其他:字元 bigram 的 **IDF 加權 Jaccard** × 40(權重 = 1/(1+ln(df)),df 為全區名稱語料中該 bigram 出現次數) | 0–40 |
| | **通用名稱**(在 `generic_names` 或 ≤2 字) | 分數 ×0.5 |
| **geo_score** | ≤30 m / ≤80 m / ≤200 m / ≤500 m / 更遠 | +20 / +12 / +4 / 0 / −15 |
| | 任一邊沒有座標(稅籍尚未 geocode,目前一律如此) | 0 |
| **category_score** | 稅籍行業與 OSM 類型相容 | +10 |
| | 中性 | 0 |
| | 不相容(例:OSM 正餐店 vs 手搖飲/酒吧) | −25 |
| | **稅籍行業完全不是餐飲(否決)** | −40 |
| **ambiguity_penalty** | 同址多戶:每多一個其他餐飲實體 −5,上限 −15;僅在名稱分 < 30 時適用 | 0 至 −15 |
| | 次佳候選的分數與最佳相差 ≤ 5 | −10 |
| | 通用名稱 | −10 |
| | 稅籍地址含「攤販/攤位/市場」 | −5 |

OSM 類型分組:`amenity = cafe|ice_cream` 或名稱含 糖水/豆花/冰/茶/咖啡/甜 → 咖啡甜點組;其餘 → 正餐組。稅籍行業碼對應見 `er_v1.py` 的 `tax_class`。

## 5. 決策與防護欄

| 決策 | 條件(暫定) | 動作 |
|---|---|---|
| `auto_match` | score ≥ `auto_match_threshold`(70) | 寫入 `restaurant_source_entity`,`match_status='auto'` |
| `probable` | ≥ `probable_threshold`(50) | `match_status='probable'`;**待座標距離確認**後才可升為 auto |
| `review` | ≥ `manual_review_threshold`(30) | `restaurant_id` 為 NULL、`match_status='review'`,寫入 `identity.er_review_queue` |
| `non_match` | 其他 | 不連結(`rejected` 或不建立) |

**防護欄(不是門檻,必須成立)**
1. 類別否決成立時,不得 auto。
2. 懲罰合計 ≥ 10 時,不得 auto。
3. 兩邊都有地址、地址不同或地址缺失時,不得僅憑名稱 auto(降為 probable)。
4. 人工決定一律優先,並成為新的 gold 紀錄。
5. 同一來源內的重複節點(例:OSM 兩個「鴨肉珍」)必須收斂到同一家餐廳,不得變成兩家。

## 6. 結構性限制(基準評估發現)

- **OSM 沒有地址的店(約 64%),名稱再像,分數上限也只有 44**(名稱 34 + 類別 10),**永遠到不了 probable(50)**,只會落在 review。要解開這類配對,必須先把稅籍地址 geocode 出座標,啟用 `geo_score`。**這不是調門檻能解決的**。
- 稅籍行業碼與實際業態可能不一致(見 §7 的黛麗莎),`incompatible −25` 目前可能過重。

## 7. Gold set 與基準結果

`er_gold_set.csv`:45 組真實配對(21 match / 12 non_match / 12 review),每組都由腳本回頭到 OSM 與稅籍檔解析。涵蓋:明確 match(6)、同址不同店(5 + 市場多戶 2)、改名或名稱變體、公司型態名稱、OSM 地址錯、路名錯字、副號不同、全形字、通用名稱一對多、OSM 重複節點、連鎖外送分公司、共用 token 但不同店、稅籍行業不符。

**⚠ 標籤限制**:全部是我依地址、名稱、行業碼與 PoC 網頁檢查做的判斷,**沒有任何一組經電話或實地驗證**(最高信心為 medium;`review` 類多為 low)。門檻也**沒有**用這組資料調整。所以下表是「回歸基準」,**不是準確率**。

| 指標(定義) | 基準結果 |
|---|---|
| auto_match 數 / 其中與標籤不符 | 5 / 1(80%);不符的是「大胖碳烤三明治 ↔ 大摳胖碳烤三明治」,我標成 review(low),分數 73,可能其實是同一家,標籤本身不確定 |
| match 召回(auto+probable / 標籤為 match) | 15 / 21 = 71%;另 2 組送 review(81% 未遺失) |
| **false split**(標籤 match 卻判成 non_match) | 4:黛麗莎↔黛麗莎美食坊、老宋牛肉麵↔老宋小吃店、阿進切仔麵↔阿進麵攤、金記溫州餛飩大王↔金溫州餛飩大王 |
| **false merge**(標籤 non_match 卻判成 match) | 1:Big Mama ↔ 萊克青旅有限公司(同址、類別相容;地址 exact +40 + 類別 +10 = **剛好 50 = probable 門檻**,名稱 0 分) |
| 標籤 review 卻被機器直接決定 | 3(auto/probable);另有 **5 組被判 non_match 而沒進人工佇列**,這是潛在的 false split |
| 標籤 non_match 被正確分開 | 11 / 12 |

**失敗原因(逐筆拆解,見 `er_v1_eval.csv`)**
1. **`probable` 門檻 50 恰好等於「同址 +40 + 類別相容 +10」**:只要同址且類別相容,即使名稱完全無重疊(0 分)也會變 probable。Big Mama ↔ 青旅(false merge)、里歐 ↔ 五二早餐店、里歐 ↔ 新星早餐店(後兩者標籤為 review,卻被機器直接判 probable)都是這個原因。這是**門檻與權重配置的人為巧合**,不是資料問題。是否要求「probable 必須有最低名稱分」須用更多標籤決定,**這裡不擅自改**。
2. **名稱分太弱導致 false split**(都沒有地址,所以名稱是唯一證據,上限 44 又到不了 50,見 §6):老宋牛肉麵 ↔ 老宋小吃店(清完後稅籍名只剩 `老宋` 2 字,包含規則要求 ≥3 字,只剩 bigram 10.4 分)、阿進切仔麵 ↔ 阿進麵攤(5.1 分,`阿進麵攤` 不是 `阿進切仔麵` 的子字串)、金記溫州餛飩大王 ↔ 金溫州餛飩大王(17.1 分,只差一個字)。
3. **黛麗莎 ↔ 黛麗莎美食坊**:地址 +30、名稱 +34,卻因稅籍行業與 OSM 類型被判不相容(正餐 vs 飲料店)−25,再加「次佳候選接近」−10,最後 29 分被丟掉。**稅籍行業碼不一定反映實際業態**,`incompatible −25` 可能過重。
4. **田記豆漿**(OSM 地址錯):地址 −10、名稱 40 → 40 分,落在 review。稅籍地址 geocode 後座標相距約 25 m,可再 +12 到 +20,會升為 probable。
5. **香港馬興記燒臘**(OSM 無地址,名稱包含):34 + 10 = 44 分,只能 review(§6 的上限)。
6. **標籤 review 卻被判 non_match 的 5 組沒有進人工佇列**:有漏掉真實配對的風險(例如標籤為「可能同一家」的同址改名)。`manual_review_threshold` 是否該更低,同樣要等有更多標籤。

## 8. 建議的下一步(都未實作)

1. 把稅籍地址 geocode(來源與條款需先確認),啟用 `geo_score`,重跑 gold set。
2. 把 `incompatible` 從 −25 降為較輕的值(或只對 bar / 手搖飲啟用)——**需要更多標籤再決定,不要憑 1 筆調**。
3. 為 2 字名稱與無地址情境另設規則(例:別名表、品牌 token 表、人工確認後回灌)。
4. 擴充 gold set:目標至少數百組、經電話或 Places 驗證、依 `case_type` 分層;只在此之後才把門檻標成 `validated`。
5. 驗收門檻(**建議、尚未採納**):auto_match 的 false merge 在 gold 上為 0;在 ≥ 200 組已驗證配對上 auto precision ≥ 98%;review 佇列量在人工可負擔範圍。

## 9. 寫入資料庫時要保存的欄位

`restaurant_source_entity`:`matched_by`(`same_address+name` / `name_only` / `coord+name` / `alias` / `manual`)、`match_score`、`match_features`(JSON:各元件分數與理由,例如 `address_why`、`name_why`)、`er_version`、`match_status`。
`er_review_queue.reason` 建議值:`same_address_name_differs`、`multiple_name_candidates`、`generic_name`、`one_to_many`、`chain_branch`、`low_score_review`。
`identity.er_config`:每次調整門檻都新增一版,舊版標 `retired`;`er_version` 對應該版本。
