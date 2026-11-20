# PoC 2:政府資料 Discovery 補測(鹽埕區)

快照:2026-10-31。目標是回答 Gate 1:**餐廳母體從哪裡來?** 本輪只測不需金鑰的政府來源,Google Places 與 TDX 需要你本人建立金鑰,尚未測。

## 結論(一句話)

觀光署的餐飲開放資料在鹽埕區是 **0 筆**,不能當母體;財政部營業(稅籍)登記在鹽埕區有 **490 筆餐飲類**,是目前唯一量級足夠的母體候選,但「同一家店」的對應(entity resolution)必須另外設計。**Discovery 必須多來源 union,不是選一個來源。**

## 1. 先前判斷的更正

第一輪我說 data.gov.tw 與 khh.travel「讀不到」。實際上 data.gov.tw 的 API 用 curl 是通的(先前是我的網頁抓取工具不行),觀光署餐飲檔也可免金鑰整檔下載。所以第一輪「政府資料沒取到」應理解為「我當時的工具不行」,不是資料不可得。

## 2. 實測結果

### 2.1 觀光署「餐飲 - 觀光資訊資料庫」(data.gov.tw/dataset/7779,每日更新,免費)

| 項目 | 數字 |
|---|---|
| 全台筆數 | 4,666 |
| 高雄市 | 60(甲仙 16、杉林 15、美濃 15、六龜 13、桃源 1) |
| **鹽埕區** | **0**(以行政區與座標框 22.612–22.640N、120.270–120.295E 都是 0) |
| 欄位 | 有座標、地址、電話、`CuisineClasses`、`ServiceTimeInfo`、`WebsiteURL`、`ReservationURLs`、`RestaurantFeatures` 等,但鹽埕沒有資料可看 |

這份資料是各縣市政府自行投稿,高雄都會區沒有投稿,所以**對本專案的 Discovery 召回為 0**。TDX 的觀光 API 很可能是同一資料來源,但我沒有金鑰,**未驗證**。

### 2.2 財政部「營業(稅籍)登記資料集」(`eip.fia.gov.tw/data/BGMOPEN1.csv`,免金鑰,檔頭日期 2026-10-31)

| 項目 | 數字 |
|---|---|
| 全國列數 | 約 171.5 萬 |
| 鹽埕區全部營業登記 | 3,012 |
| **含餐飲類行業碼(56\*)** | **490**(主行業為 56\*:461) |
| 其中使用統一發票 | 133 |
| 行業別分布(含次要行業碼,一列可計多次) | 麵店/小吃店 186、餐廳 99、手搖飲店 54、其他飲料店 49、餐食攤販 39、咖啡館 29、早餐店 22、飲酒店 19、便當/自助餐店 18、茶館 3、連鎖速食店 3 等 |
| 對推薦的意義 | 490 筆包含手搖飲、飲酒店、攤販,**不全是聚餐候選**;進入 Master List 前要依行業碼過濾 |

欄位:營業地址、統一編號、營業人名稱、資本額、設立日期、組織別、行業代號(最多 4 個)。**沒有歇業狀態、沒有座標、沒有營業時間、沒有評價。** 地址為全形數字,有「116―1號」這類長破折號,需先 normalize(我一開始就因此漏配,修正後數字才正確)。

### 2.3 稅籍 vs OSM(集合運算)

| 集合 | 筆數 |
|---|---|
| OSM(有名稱) | 132 |
| 稅籍餐飲類 | 490 |
| 交集(地址或名稱比對上) | 約 56–61(已更正,見下方更正說明) |
| 只有 OSM | 約 71 |
| 只有稅籍 | 約 434 |
| 聯集 | **約 566(上限)** |

聯集是上限,因為名稱比對會漏掉大量「同一家但名稱寫法不同」的配對,實際交集較大、聯集較小。**稅籍母體約為 OSM 的 3.7 倍。** 逐筆結果在 `gov_vs_osm_match.csv`。

### 2.4 稅籍對「真實店家」的覆蓋(獨立檢驗)

用一篇旅遊文章列出的 17 家鹽埕小吃(有門牌)當獨立名單,不依賴 OSM:

| 判準 | 命中 |
|---|---|
| 同門牌有餐飲類稅籍 | 16 / 17(94%) |
| 稅籍名稱也對得上店名 | 6 / 17(35%) |
| 完全沒有:蟳市長(七賢三路 257 號整個門牌 0 筆稅籍) | 1 / 17 |

我的 30 家樣本中有完整地址的 21 家:**名稱與地址都對上 5 家;只有地址對上、但稅籍名稱是別的名字 10 家;地址完全沒稅籍 6 家**(`sample30_tax_match.csv`)。

**解讀**:
- 「這個門牌有餐飲登記」召回很高;但「這家店是哪個稅籍列」要靠名稱 + 地址 + 人工/模型判斷。稅籍名稱常是登記名或負責人姓名(例:水源羊肉海產店 ↔ 負責人姓名;勇伯冬粉豬舌 ↔ 個人名;大溝頂虱目魚米粉湯同門牌有 4 個人名,是攤位)。
- 一址多戶很常見(The Borage 所在門牌有 8 筆登記;黛麗莎與老宋牛肉麵同址)。
- **稅籍有沒有收錄 ≠ 店還在營業**,也不是所有店都有登記(蟳市長 0 筆;柒壹喫堂的門牌登記的是一家美髮沙龍)。
- 反過來也證明稅籍能**修正別的來源的錯誤**:
  - 田記豆漿:稅籍有「田記豆漿店,新樂街 75―3 號」,與 FooTinder 一致;OSM 的「大義街 126 號」是錯的。
  - 九記:稅籍「趙九記食糖水舖,鹽埕街 36 巷 23 號」,與 OSM 門牌一致,OSM 的路名「鹽埕路」是錯字。
  - 平津涮牛肉:OSM 的大勇路 8 號,稅籍同門牌是熱狗堡與另一家小吃,沒有火鍋,支持「OSM 節點過期」的判斷。
  - 郭家肉粽、禪風蔬藝:稅籍查不到該門牌,可能登記在別的行業碼或其他地址,未能確認。

> **更正(第四輪)**:OSM 的 `addr:full` 常以郵遞區號開頭(例如 `803高雄市鹽埕區…`),我的地址解析器沒有先去掉,導致約一半有地址的 OSM 項目比對不到。修正後:OSM 對稅籍的比對由 47 筆升到 61 筆(地址 35、名稱 26),只有 OSM 約 71、只有稅籍約 434、聯集上限約 566;ER v0 的 auto_match 由 7 升到 15、稅籍-only 池由 455 變 456。本文先前的數字已更新。**第 2.4 節(17 家旅遊文章的獨立檢驗,16/17)與樣本 30 家的稅籍比對不受影響**(它們用的地址沒有郵遞區號)。`tax_only_audit_30.csv` 因池變動已用同一個亂數種子重新抽樣,內容與先前不同。

## 3. 對架構的含意

```
Discovery(多來源 union)            Enrichment(各欄位各自最佳來源)
 財政部稅籍 (免金鑰、母體大)         OSM  → 座標、部分地址/電話/時間
 Google Places (待測,需金鑰)   →    Places → 評價、評論數、營業時間、價位(待測)
 OSM / 觀光署(補充)                 店家自填 → 飲食與過敏(唯一能產生「不含」的路)
        ↓
 Restaurant Master + RestaurantSource(source_type, source_id, first_seen/last_seen)
        ↓
 Entity Resolution(地址 normalize + 名稱相似 + 同址多戶消歧 + 人工覆核佇列)
```

- 稅籍是**候選母體**,不是「已確認營業的餐廳清單」:需要用 Places 的 `businessStatus`、評論數或其他活動訊號篩掉歇業與非實體店。
- Entity Resolution 比寫爬蟲更該先設計:同址多戶、名稱是負責人姓名、路名錯字(鹽埕路/鹽埕街)、門牌副號(之)、全形數字與破折號,這次全都實際遇到。

## 4. 還沒做、需要你做的

1. **Google Places pilot**(Gate 2):我寫好 `places_pilot.py`,對同一份 30 家抓 place_id、評分、評論數、價位、營業時間、素食/可訂位/團體適合欄位,產出 `places_pilot.csv`。**尚未執行,也未實際測試**,因為需要你在 Google Cloud 建立金鑰並啟用計費。跑前請先看現行費用與條款(快取、儲存、顯示規範),評價與營業時間類欄位可能落在較高價位的 SKU。
2. **TDX 金鑰**:在 tdx.transportdata.tw 免費註冊後,測 `Tourism/Restaurant/Kaohsiung`,確認是否與觀光署檔案同源(預期鹽埕為 0)。我不會代為註冊或輸入你的帳密。
3. **稅籍母體的精確度抽驗**:從約 434–456 筆「只有稅籍」中隨機抽 20–30 筆,用 Places 或電話確認是否仍營業、是否真是餐廳。這決定稅籍能當母體還是只能當線索。
4. 其他尚未測:食藥署食品業者登錄、衛生局餐飲分級完整名單(市面上只看到 PDF 與舊年度資料集)。

## 5. 檔案

| 檔案 | 內容 |
|---|---|
| `raw/gov/unz/RestaurantList.json` | 觀光署餐飲檔(全台 4,666 筆) |
| `raw/fia/yancheng_food_biz.csv` | 稅籍:鹽埕區餐飲類 490 筆 |
| `raw/fia/yancheng_all_biz.csv` | 稅籍:鹽埕區全部 3,012 筆 |
| `fia_extract.py`、`gov_match.py`、`gov_misses.py` | 抽取與比對(`python -I gov_match.py` 可重跑;抽取需要自行下載 BGMOPEN1.csv,約 320 MB) |
| `gov_vs_osm_match.csv` | 132 筆 OSM 對稅籍的比對結果 |
| `sample30_tax_match.csv` | 30 家樣本對稅籍的比對結果 |
| `raw/fia/match_report.txt`、`misses_report.txt` | 逐筆比對明細 |
| `places_pilot.py` | Places API pilot(未執行) |

資料授權:觀光署資料依「政府資料開放授權條款第 1 版」;稅籍資料來自財政部財政資訊中心開放資料,使用前請確認授權條款與個資(獨資業者名稱可能是自然人姓名)。

---

# 追加(第三輪):Gate 1 正式結論、個資處理、ER v0、Gate 3 結構性檢查

## 6. Gate 1 結論(可關閉的部分)

1. **觀光署餐飲檔不能建立鹽埕區母體**:鹽埕區 0 筆。
2. **稅籍覆蓋高,但不適合當使用者看到的店名來源**:它適合找「可能存在的餐飲營業實體」。同門牌 94% 有餐飲登記,但店名能對上的只有約 35%;稅籍名稱常是登記名、公司名或負責人名,一址多戶、無歇業狀態。
3. **OSM 覆蓋低,但店名較接近實際招牌**:適合補名稱、座標與公開資訊。但它也會錯(平津涮牛肉過期、田記豆漿與九記地址錯、東京小城料理標錯),不能單獨信任。

**還不能關的部分**:「稅籍 + OSM 聯集」的**精確度(precision)**。目前只有結構性數字(見 8),沒有人工驗證,所以 Gate 3 仍開著。

## 7. 個資處理

- 獨資業者常以自然人姓名登記。推薦系統用不到,所以抽取時就遮罩(`fia_extract.py` 的 `mask_name`):`獨資/合夥` + 2–4 個中文字 + 不含店型字詞者,存成 `[個人名]`。3,012 筆中遮罩 363 筆(約 12%)。
- 這是**啟發式、盡力而為**:我人工掃過剩餘的短名稱,仍有「名字 + 店型字」混合的邊角案例(例如姓名後接「沙龍」),可能殘留。
- 我把含姓名的 320 MB 全國原檔從暫存區刪除了,專案裡只留遮罩後的鹽埕區擷取;比對輸出也已重跑,並用已知的個人姓名掃過全專案,沒有殘留。
- 正式 ETL 建議更嚴格:**稅籍名稱預設不持久化**;只有在它與另一來源(OSM / Places)的公開店名比對成功時,才保留作為 `source_name`。其餘只留 `tax_record_id`、地址、行業碼、設立日期。

## 8. ER v0 與稅籍-only 結構性檢查

規則(**門檻是提案,沒有 gold set 驗證**):同地址 + 名稱相似 ≥ 0.8 → `auto_match`;同地址且相似 < 0.4 → 「同址他店或已改名」;介於中間 → `review`;OSM 沒地址則名稱唯一候選 ≥ 0.8 → `probable`(待座標距離確認,稅籍無座標,需先 geocode)。

| ER v0 決定(OSM 132 筆) | 筆數 |
|---|---|
| auto_match | 15 |
| probable_match_needs_distance_check | 21 |
| review / review_multiple_name_candidates | 5 / 3 |
| same_address_other_business_or_renamed | 15 |
| no_match | 73 |

稅籍餐飲 490 筆中 34 筆被連到 OSM,**稅籍-only 池 456 筆**。

**看出來的規則缺陷**(逐筆在 `raw/er_eyeball.txt`):
- 港園牛肉麵 ↔ 港園麵館(同址)只拿 0.75,會被丟去 review;千葉養生素食 ↔ 仟悅素食養生自助餐館(同址、同為素食)只拿 0.27。**純字串相似度不夠**,要加料理類型相容、關鍵字詞(而不是整串)、地址同址加權。
- 「豆花」「高雄婆婆冰」這種泛稱名稱會對到多個候選,必須進人工佇列。
- 外送分公司、旅館/青旅登記(Big Mama 同址是青旅登記)會造成「同址他店」,需要靠行業碼與次要行業碼判斷。

**稅籍-only 池的結構性分類**(只看行業碼與地址,**不是驗證過的精確度**):

| 類別 | 筆數 | 比例 |
|---|---|---|
| 可能的聚餐候選(餐廳、麵店/小吃、便當/自助餐、早餐、咖啡館、茶館、速食) | 292 | 64.0% |
| 排除類(手搖飲 45、其他飲料 29、餐食攤販 23、飲酒店 9 等) | 108 | 23.7% |
| 攤販或市場地址 | 28 | 6.1% |
| 餐飲碼只在次要行業 | 28 | 6.1% |

所以即使不驗證店還在不在,**稅籍-only 池最多約 6 成是結構上可能的聚餐候選**;真正精確度只會更低(歇業、純登記、非對外營業)。這個 64% 是上限,不是估計值。

## 9. Gate 3 稽核表

`tax_only_audit_30.csv`:從 456 筆稅籍-only 池以固定亂數種子(20261031)抽 30 筆。結構性欄位已填;**`still_operating`、`real_trade_name`、`is_restaurant`、`suitable_for_group_dining`、`findable_on_places`、`auditor_note` 一律是 `unknown`,等人工或 Places 結果填**。我沒有用搜尋引擎去填:前面 30 家樣本的經驗是我的搜尋工具對小店召回很差,「搜不到」會被誤讀成「已歇業」,反而讓精確度估計偏低。建議用 Places 比對加電話抽驗,算出:

```
precision = 真正仍營業且適合聚餐 / 30
```

## 10. Schema 調整建議(只動身分層)

採用你提的拆分,補三個我實際遇到的需求:

```sql
CREATE TABLE restaurant (
  restaurant_id      TEXT PRIMARY KEY,
  canonical_name     TEXT NOT NULL,       -- 優先序:Places > OSM > 稅籍(僅在非自然人名時)
  canonical_address  TEXT,
  lat DOUBLE PRECISION, lon DOUBLE PRECISION,
  active_status      TEXT NOT NULL DEFAULT 'unverified'   -- active | unverified | closed | not_a_restaurant
);

CREATE TABLE restaurant_source_entity (
  source_entity_id BIGSERIAL PRIMARY KEY,
  restaurant_id    TEXT REFERENCES restaurant,           -- NULL = 尚未對應(candidate)
  source_type      TEXT NOT NULL,                        -- tax | osm | places | gov_tourism
  source_record_id TEXT NOT NULL,                        -- 稅籍:統一編號 + 地址;OSM:node/way id;Places:place_id
  source_name      TEXT,                                 -- 自然人姓名一律 NULL(ETL 時遮罩)
  source_name_is_personal BOOLEAN NOT NULL DEFAULT FALSE,
  source_address   TEXT,
  address_key      TEXT,                                 -- normalize 後的 (路街, 門牌主號),供比對
  industry_code    TEXT,
  source_url       TEXT,
  matched_by       TEXT,                                 -- same_address+name | name_only | coord+name | manual
  match_score      REAL,
  match_status     TEXT NOT NULL,                        -- auto | probable | review | rejected | manual_confirmed
  first_seen_at DATE, last_seen_at DATE,
  UNIQUE (source_type, source_record_id)
);

-- 同一家店多個名稱(招牌、登記名、英文名)
CREATE TABLE restaurant_alias (
  restaurant_id TEXT REFERENCES restaurant, alias TEXT NOT NULL, origin TEXT NOT NULL,
  PRIMARY KEY (restaurant_id, alias)
);
```

- `address_key` 與 `match_status` 是這次最需要的欄位:地址 normalize 規則(全形、各種破折號、副號「之」)決定能不能對上。
- 稅籍列入庫時應包含 `industry_code`,以便過濾手搖飲、飲酒店、攤販。
- 一個 `restaurant` 可對應多個同源實體(同址多戶、分店更名),所以 `UNIQUE` 設在 source 端而不是 restaurant 端。

## 11. 狀態與下一步

| Gate | 狀態 |
|---|---|
| Gate 1 母體來源 | **可關閉**(結論見 6);但聯集精確度併入 Gate 3 |
| Gate 2 Places pilot | **未執行**:`places_pilot.py` 已寫好、只通過語法檢查,需要你的 Google Maps API 金鑰與計費。跑之前先確認現行費用與條款 |
| Gate 3 稅籍-only 稽核 | **稽核表已備,待人工/Places 填寫** |

建議順序:Places pilot(順便得到 Places↔OSM、Places↔稅籍的比對率)→ 用 30 筆稽核表算精確度 → 以兩者的結果建一個 50 組左右的 gold set,回頭調 ER 門檻,再寫 Data Architecture / ER Model / ETL Specification。

新增檔案:`er_v0.py`、`er_v0_osm_to_tax.csv`、`er_v0_summary.txt`、`tax_only_pool.csv`(456 筆)、`tax_only_audit_30.csv`、`raw/er_eyeball.txt`。
