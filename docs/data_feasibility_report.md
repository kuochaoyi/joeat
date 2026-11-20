# 鹽埕區 Data Feasibility PoC 報告

- 快照日期:2026-10-31(營業時間 `currently_active` 以週六 22:45 計算)
- 範圍:高雄市鹽埕區、30 家樣本、不爬全高雄、不做正式 crawler
- 檔案:`restaurants_sample_30.csv`(30 列 × 69 欄,缺值一律 `unknown`)、`field_provenance.csv`(194 筆來源追溯)、`field_coverage.csv`、`hours_check.csv`、`build_poc.py`(可重跑)、`raw/osm.json`、`raw/st.json`

## 0. 先講清楚這份 PoC 的邊界(影響所有數字的可信度)

| 我做了 | 我沒做到 / 不能宣稱 |
|---|---|
| 用 OpenStreetMap(Overpass)抓鹽埕區 144 筆餐飲 POI(132 筆有店名),作為結構化底稿 | **沒有存取 Google Maps / Places API**,所以評價、評論數、Google 營業時間、`servesVegetarianFood` 等欄位的實際涵蓋率**沒測** |
| 從 132 筆中挑 30 家(依料理類型分層,不挑熱門),逐家用網頁搜尋交叉驗證 | **(第一輪)政府資料沒取到**。第二輪已補:觀光署餐飲檔鹽埕區 0 筆、財政部稅籍餐飲類 490 筆,詳見 `POC2_GOV_DISCOVERY.md`。TDX 仍需金鑰,未測 |
| 所有非底稿欄位都記錄 source / confidence / last_verified_at | 網頁驗證是透過搜尋引擎摘要,**不是逐頁完整閱讀**;`source_url` 為文章層級,欄位層級歸屬可能有少量誤差 |
| 缺值全部標 `unknown` | **沒開 Facebook / Instagram**(需登入、TOS 風險),社群頁的營業時間與菜單都沒讀 |

**關鍵解讀規則**:`existence_check = osm_only` 代表「搜尋工具找不到第二個來源」,**不代表店已歇業**;反過來也代表我們**無法**用這些資料證明店還在。樣本取自 OSM,本身有選樣偏誤(只含有人去標註的店)。

## 1. Executive Summary

1. **能直接當底稿的只有「店名、座標、(部分)地址電話、料理大類」**。座標 97%、店名 100%;但地址只有 73%、電話 50%。
2. **營業時間「有值」不等於「可信」**:24/30 有值,但其中只有 5 筆(21%)被兩個以上來源互相印證;有兩個來源可比對的 10 筆裡,**5 筆互相矛盾**。
3. **價格幾乎不能用**:`price_min_per_person` 0/30、`price_max_per_person` 2/30(且都是聚合平台的區間)、`price_level` 4/30。能抽到的多半是「單品價」(鴨肉飯 60 元),不能換算成人均。**「預算上限」不適合當 Hard Constraint。**
4. **評價這次完全沒驗證**(只拿到 1 家第三方聚合平台分數)。是否能合法穩定取得,必須用 Google Places API 另測,**不要假設可爬**。
5. **Hard Constraint 結論最重要**:過敏原 8 個欄位裡,所有非 unknown 的值(7 筆)都是「**含有**」的正向偵測(例如店名有「蟳」→ 含甲殼類),**0 筆能證明「不含」**。`halal`、`gluten_free`、`contains_raw_food`、`allergen_milk` 全部 0%。素食只有「專營素食店」有線索,且全是 OSM 單一社群標籤或媒體報導,**沒有任何一筆來自店家第一手**,所以全部只能到 `likely`。
6. **實體對應(entity resolution)本身就是風險**:30 家裡 2 家「名稱/地址對不上」(平津涮牛肉、田記豆漿)、15 家只在 OSM 出現;OSM 對照一篇部落客清單(17 家)只找回約 6 家,**OSM 召回率粗估 35–40%(n=17,僅供量級參考)**。所以餐廳清單不能只靠 OSM。
7. **第二輪補測(Discovery)**:觀光署餐飲檔在鹽埕區是 0 筆,不能當母體;財政部稅籍餐飲類有 490 筆,是目前唯一量級足夠的母體候選,但實體對應要處理名稱與地址問題。詳見 `POC2_GOV_DISCOVERY.md`。
8. **開發建議**:MVP 把「安全」承諾降級成「排除已知衝突 + 明示未確認」,不要做任何「此店安全」的綠色標示,除非有店家第一手資料。

## 2. 30 家鹽埕區樣本

存在性欄位:`web_corroborated`=至少一個非 OSM 來源對得上名稱與地址/電話;`osm_only`=僅 OSM;`entity_conflict`=名稱或地址在來源間對不上。類型為我自行 normalize。

| ID | 店名 | 正規化類型 | 存在性 | 地址 | 營業時間 | 一致性 | 價格證據 | 飲食/過敏(非 unknown) |
|---|---|---|---|---|---|---|---|---|
| YC001 | 鴨肉珍 | 台式;小吃 | web_corroborated | 五福四路258號 | We-Mo 10:00-20:20 | agree | 鴨肉飯 小碗60/大碗70 (2026-01 media); older blog 50 | contains_pork=likely、contains_offal=likely |
| YC002 | 老蔡虱目魚粥 | 台式;小吃;海鮮 | web_corroborated | 瀨南街201號 | Mo-Su 06:00-14:00 | conflict | unknown | contains_seafood=confirmed |
| YC003 | 港園牛肉麵 | 台式;中式;小吃 | web_corroborated | 大成街55號 | Mo-Su 10:30-20:00 | single_source | unknown | contains_beef=confirmed、contains_pork=likely、allergen_gluten=likely |
| YC004 | 平津涮牛肉 | 火鍋;中式 | entity_conflict | 大勇路8號 | Mo-Su 11:00-14:00, 17:00-21:00 | single_source | unknown | contains_beef=likely |
| YC005 | 陶湘火鍋店 | 火鍋;中式 | osm_only | unknown | Mo-Su 11:00-14:00, 17:00-22:00 | single_source | unknown | 全 unknown |
| YC006 | 好貳 | 火鍋;素食 | osm_only | unknown | unknown | unknown | unknown | vegetarian=likely |
| YC007 | 大智羊肉 | 中式;其他 | osm_only | unknown | Mo-Su 17:00-23:00 | single_source | unknown | 全 unknown |
| YC008 | 蟳市長 | 海鮮;小吃 | web_corroborated | 七賢三路257號 | Tu-Fr 09:00-17:00; Sa-Su 10:00-15:00 | conflict | unknown | contains_seafood=confirmed、allergen_shellfish=confirmed |
| YC009 | 小韓國 | 韓式 | osm_only | unknown | Mo,We-Su 11:00-14:00, 17:00-21:30 | single_source | unknown | 全 unknown |
| YC010 | 東京小城 | 熱炒;中式;日式 | web_corroborated | partial:五福四路(門牌unknown) | unknown | unknown | unknown | 全 unknown |
| YC011 | 鐘庵日本料理 | 日式 | osm_only | 五福四路65號 | unknown | unknown | unknown | 全 unknown |
| YC012 | Big Mama | 義式 | osm_only | 大勇路78號 | Mo-Fr 11:30-14:30, 17:30-22:00; Sa-Su 11:30-22:00 | single_source | unknown | 全 unknown |
| YC013 | 泰老食 | 東南亞 | osm_only | unknown | Mo-Su 11:00-14:30, 17:00-20:30 | single_source | unknown | 全 unknown |
| YC014 | Thai Funk Cafe | 東南亞 | osm_only | unknown | unknown | unknown | unknown | vegetarian=likely |
| YC015 | HATA烏克蘭廚房 | 其他 | osm_only | 五福四路150號 | unknown | unknown | unknown | 全 unknown |
| YC016 | 黛麗莎 | 其他 | osm_only | 五福四路146號 | Mo-Su 11:00-22:00 | single_source | unknown | 全 unknown |
| YC017 | 傑克兄弟牛排 | 美式;牛排 | osm_only | unknown | Mo-Su 12:00-15:00, 17:00-22:00 | single_source | unknown | contains_beef=likely |
| YC018 | 千葉養生素食 | 素食 | osm_only | 大義街131號 | Mo-Su 07:00-20:30 | single_source | unknown | vegetarian=likely |
| YC019 | 禪風蔬藝 | 素食 | osm_only | 七賢二路455之1號 | Tu-Su 10:00-13:30, 16:00-19:00 | single_source | unknown | vegetarian=likely、vegan=likely |
| YC020 | 里歐歐式早餐(五福四路131號) | 早午餐 | web_corroborated | 五福四路131號 | Mo-Su 06:30-13:30 | agree | FooTinder band $1-400 (NT$) | 全 unknown |
| YC021 | 柒壹喫堂 | 早午餐;日式 | web_corroborated | 大公路71號 | Fr-We 11:00-19:00 | conflict | 低消 NT$100/人 (2021 blog) | 全 unknown |
| YC022 | The Borage 琉璃苣 | 素食;其他 | web_corroborated | 瀨南街141之7號 | Th-Su 16:30-20:30 | conflict | unknown | vegetarian=likely、vegan=likely |
| YC023 | Do good coffee & dessert | 咖啡廳;甜點 | web_corroborated | 必信街116號 | We-Mo 10:00-18:00 | single_source | qualitative only: 'very affordable' | 全 unknown |
| YC024 | 鹽埕町冰果室 | 甜點 | osm_only | 富野路56巷10號 | Mo-Su 09:00-21:00 | single_source | unknown | 全 unknown |
| YC025 | 九記 鹽埕食糖水 | 甜點 | web_corroborated | 鹽埕路36巷23號 | Mo-Su 14:00-23:00 | conflict | one unlabeled item NT$75 (Marie Claire) | allergen_tree_nut=likely、allergen_sesame=likely |
| YC026 | 郭家肉粽 | 台式;小吃 | web_corroborated | 北斗街19號 | Mo-Su 07:00-23:00 | agree | 碗粿 30/碗 (2021 media) | contains_pork=likely、allergen_peanut=likely |
| YC027 | 田記豆漿 | 台式;早午餐 | entity_conflict | 大義街126號 | Mo-Su 05:30-11:30, 16:00-23:30 | agree | FooTinder band $1-200 (NT$) | allergen_egg=likely、allergen_soy=confirmed |
| YC028 | 阿英排骨飯 | 台式;小吃 | web_corroborated | 富野路79-2號 | Fr-Tu 10:30-20:45 | single_source | 排骨便當 90 (media) | contains_pork=confirmed |
| YC029 | 香港馬興記燒臘臘味專賣店 | 中式;港式 | osm_only | unknown | unknown | unknown | unknown | contains_pork=likely |
| YC030 | 大溝頂虱目魚米粉湯 | 台式;小吃;海鮮 | web_corroborated | 新樂街198-38號 | Mo-Su 05:30-13:30 | agree | unknown | contains_seafood=confirmed |

類型覆蓋:台式/小吃、中式、火鍋、海鮮、韓式、日式、義式、東南亞、美式牛排、素食、早午餐、咖啡廳、甜點都有。**樣本裡沒有燒肉、印度料理**(OSM 132 筆命名 POI 中未見,不代表區內沒有);熱炒只有 1 家(東京小城,而且 OSM 把它標成 japanese,與部落客描述不符);海鮮只有 2 家。

## 3. 欄位逐項涵蓋率(30 家,non-null / unknown / coverage)

`partial_count` = 有值但不完整(例如只有街名沒有門牌,已計入 non-null)。`derived` 欄位(currently_active、near_public_transport)由其他欄位計算而來,可靠度取決於上游。

| 欄位 | non-null | unknown | partial | coverage % |
|---|---|---|---|---|
| restaurant_name | 30 | 0 | 0 | 100.0 |
| alternate_name | 8 | 22 | 0 | 26.7 |
| address | 22 | 8 | 1 | 73.3 |
| district | 30 | 0 | 0 | 100.0 |
| city | 30 | 0 | 0 | 100.0 |
| latitude | 29 | 1 | 0 | 96.7 |
| longitude | 29 | 1 | 0 | 96.7 |
| phone | 15 | 15 | 0 | 50.0 |
| osm_id | 29 | 1 | 0 | 96.7 |
| existence_check | 30 | 0 | 0 | 100.0 |
| osm_cuisine_tag | 21 | 9 | 0 | 70.0 |
| official_cuisine_class | 0 | 30 | 0 | 0.0 |
| normalized_cuisine_tags | 30 | 0 | 0 | 100.0 |
| cuisine_confidence | 30 | 0 | 0 | 100.0 |
| cuisine_basis | 30 | 0 | 0 | 100.0 |
| opening_days | 24 | 6 | 0 | 80.0 |
| opening_time | 24 | 6 | 0 | 80.0 |
| closing_time | 24 | 6 | 0 | 80.0 |
| break_time | 24 | 6 | 0 | 80.0 |
| closed_day | 24 | 6 | 0 | 80.0 |
| currently_active | 24 | 6 | 0 | 80.0 |
| hours_raw | 24 | 6 | 0 | 80.0 |
| hours_source | 24 | 6 | 0 | 80.0 |
| hours_consistency | 24 | 6 | 0 | 80.0 |
| hours_confidence | 24 | 6 | 0 | 80.0 |
| price_min_per_person | 0 | 30 | 0 | 0.0 |
| price_max_per_person | 2 | 28 | 0 | 6.7 |
| price_level | 4 | 26 | 0 | 13.3 |
| price_item_evidence | 8 | 22 | 0 | 26.7 |
| price_source | 8 | 22 | 0 | 26.7 |
| price_confidence | 8 | 22 | 0 | 26.7 |
| rating | 1 | 29 | 0 | 3.3 |
| review_count | 1 | 29 | 0 | 3.3 |
| rating_source | 1 | 29 | 0 | 3.3 |
| external_recognition | 1 | 29 | 0 | 3.3 |
| vegetarian | 5 | 25 | 0 | 16.7 |
| vegan | 2 | 28 | 0 | 6.7 |
| halal | 0 | 30 | 0 | 0.0 |
| gluten_free | 0 | 30 | 0 | 0.0 |
| contains_beef | 3 | 27 | 0 | 10.0 |
| contains_pork | 5 | 25 | 0 | 16.7 |
| contains_seafood | 3 | 27 | 0 | 10.0 |
| contains_offal | 1 | 29 | 0 | 3.3 |
| contains_raw_food | 0 | 30 | 0 | 0.0 |
| allergen_peanut | 1 | 29 | 0 | 3.3 |
| allergen_tree_nut | 1 | 29 | 0 | 3.3 |
| allergen_shellfish | 1 | 29 | 0 | 3.3 |
| allergen_milk | 0 | 30 | 0 | 0.0 |
| allergen_egg | 1 | 29 | 0 | 3.3 |
| allergen_sesame | 1 | 29 | 0 | 3.3 |
| allergen_soy | 1 | 29 | 0 | 3.3 |
| allergen_gluten | 1 | 29 | 0 | 3.3 |
| group_friendly | 0 | 30 | 0 | 0.0 |
| estimated_group_capacity | 1 | 29 | 0 | 3.3 |
| reservation_available | 2 | 28 | 1 | 6.7 |
| reservation_url | 0 | 30 | 0 | 0.0 |
| private_room | 0 | 30 | 0 | 0.0 |
| table_for_6_plus | 0 | 30 | 0 | 0.0 |
| parking_available | 0 | 30 | 0 | 0.0 |
| near_public_transport | 29 | 1 | 0 | 96.7 |
| nearest_station | 29 | 1 | 0 | 96.7 |
| images | 0 | 30 | 0 | 0.0 |
| website_url | 0 | 30 | 0 | 0.0 |
| google_maps_url | 0 | 30 | 0 | 0.0 |
| social_url | 4 | 26 | 0 | 13.3 |
| menu_url | 2 | 28 | 0 | 6.7 |

### 3.1 OSM 全區(144 筆)欄位完整度——不是只看樣本

| 欄位 | 筆數 | 比例 |
|---|---|---|
| cuisine | 70 | 49% |
| 地址(addr:full 或門牌) | 48 | 33% |
| opening_hours | 40 | 28% |
| phone | 25 | 17% |
| website / 社群 | 12 | 8% |
| diet:* | 10 | 7% |
| capacity | 1 | 1% |
| reservation | 1 | 1% |

我的樣本在地址/營業時間上比全區好看,是因為我**刻意挑**了有欄位的店來驗證。真實全區的底稿完整度是這張表。

### 3.2 營業時間一致性(24 筆有值)

| 一致性 | 筆數 | 說明 |
|---|---|---|
| agree(≥2 來源一致) | 5 | 鴨肉珍、里歐、郭家肉粽、田記豆漿、大溝頂 |
| conflict | 5 | 老蔡虱目魚粥、蟳市長、柒壹喫堂、The Borage、九記 |
| single_source | 14 | 只有 OSM 或只有一篇文章 |

衝突多為「公休日不同」或「關門時間差 1 小時以上」,而這兩種誤差正好是會讓人撲空的類型。`hours_check.csv` 有逐筆明細。

## 4. Data Feasibility Matrix

Availability:A 穩定、B 可取得需清理、C 部分有、D 品質不穩、X 幾乎無法可靠取得。Coverage 為本 PoC 的 30 家實測,「未測」表示本次沒存取該來源。

| Field | Business Importance | Availability | Coverage | Source | Reliability | Extraction Difficulty | Maintenance Cost | Hard Constraint? | Recommendation |
|---|---|---|---|---|---|---|---|---|---|
| restaurant_name | 必要 | A | 100% | OSM / 媒體 | Medium | 低 | 低 | 否 | 存;需處理同名/連鎖/改名(平津涮牛肉、田記豆漿) |
| address | 必要 | B | 73%(1 筆不完整;3 筆來源間有出入) | OSM / 媒體 | Medium | 中(需 normalize、門牌差異) | 中 | 否 | 存,附 source;缺的需 geocode 補 |
| latitude / longitude | 必要 | A | 97%(蟳市長不在 OSM) | OSM | Medium | 低 | 低 | 否 | 存;缺的用地址 geocode,並標 source |
| phone | 高(撥打確認) | C | 50% | OSM / 媒體 | Medium-Low | 低 | 中 | 否 | 存;缺值時退而導向地圖連結 |
| official_cuisine_class | 中 | X | 0%(政府資料本次未取得) | 政府:未測成功 | — | 高 | — | 否 | 先不做;待 TDX / 食藥署資料驗證 |
| normalized_cuisine_tags | 必要 | B | 100%(自行 normalize,22 筆 Medium、8 筆 Low) | OSM tag + 店名 + 媒體 | Medium-Low | 中 | 中 | 否 | 存,標 `derived` 與依據;OSM tag 會錯(東京小城) |
| opening_days / time / closed_day | 高 | D | 80% 有值;21% 有多源印證;多源可比 10 筆中 5 筆衝突 | OSM / 媒體 | Low | 中 | **高**(會變動) | 否 | 存原始字串 + consistency + last_verified;低信心時 UI 提示先確認 |
| currently_active | 高 | D | 80%(衍生) | 由營業時間計算 | Low | 低 | 高 | 否 | 即時計算、不入庫;unknown 不得顯示「營業中」 |
| price_min/max_per_person | 高 | X | min 0%、max 7% | 聚合平台區間 | Low | 高 | 高 | **不可** | 不依賴;改存 price_level(粗分級)並允許 unknown |
| price_level | 高 | D | 13% | 單品價推估 | Low | 高 | 高 | 不可 | 同上 |
| rating / review_count | 高 | 未測 | 3%(僅一個聚合平台) | Google 未測 | 未測 | 中(法規/成本) | 中 | 否 | 以 Google Places API 另測,不要爬 |
| vegetarian / vegan | 高 | C | 17% / 7%(專營素食店) | OSM 標籤、媒體 | Low | 中 | 中 | **不可當保證** | 作為「可能提供」+ 未確認提示 |
| halal / gluten_free | 中 | X | 0% | 無 | — | 高 | — | 不可 | 先不支援為硬條件 |
| contains_beef / pork / seafood | 高 | C(僅正向偵測) | 10% / 17% / 10% | 店名、菜名 | 店名 High、媒體菜名 Low | 中 | 中 | **只能排除、不能保證** | 「含有」可用於排除;「不含」永遠 unknown |
| contains_offal | 高 | X | 3% | 媒體菜名 | Low | 高 | 高 | 不可 | 同上 |
| contains_raw_food | 中 | X | 0% | 無 | — | 高 | — | 不可 | 先不做 |
| allergen_*(8 項) | **最高** | X | 0%–3%(僅正向) | 店名/品牌菜單 | Low | 很高 | 很高 | **不可** | 見第 7 節 |
| group_friendly | 高 | X | 0% | 無(Google 可能有欄位,未測) | — | 中 | 中 | 否 | 第二階段,先測 Google |
| estimated_group_capacity | 高 | X | 3% | OSM 單一標籤 | Low | 高 | 高 | 否 | 先不做 |
| reservation_available / url | 中 | C | 7% / 0% | OSM、2021 部落格 | Low | 中 | 中 | 否 | 當 soft 資訊 |
| private_room / table_for_6_plus | 中 | X | 0% | 無 | — | 高 | 高 | 否 | 店家自填或電話;先不做 |
| parking_available | 低 | X | 0% | 無 | — | 中 | 中 | 否 | 先不做 |
| near_public_transport | 低 | A | 97%(衍生) | OSM 座標 + OSM 捷運/輕軌站 | Medium | 低 | 低 | 否 | 可算,但**鹽埕全區 29/29 都在 500 公尺內,沒有鑑別力** |
| images | 低 | X | 0%(本次未收集) | — | — | 中(版權) | 中 | 否 | 不存圖,只存 Google/官方連結 |
| website_url | 中 | X | **0%(30 家沒找到一個官方網站)** | — | — | — | — | 否 | 不要把官網當主要來源 |
| social_url | 中 | C | 13% | OSM 連結 | Medium | 低 | 低 | 否 | 存連結,不爬內容 |
| menu_url | 中 | X | 7% | OSM 連結(Uber Eats、Google Drive) | Low | 低 | 高 | 否 | 存連結即可 |
| google_maps_url / place_id | 中 | 未測 | 0% | Google Places | — | 低 | 低 | 否 | 以 place_id 為主鍵之一(TOS 允許長期保存 place_id,需對照現行條款確認) |

## 5. Source Comparison

| 來源 | 本次實測結果 | 優點 | 風險 / 限制 |
|---|---|---|---|
| **政府公開資料** | **第一輪沒取到;第二輪已補測(見 `POC2_GOV_DISCOVERY.md`)**:觀光署餐飲檔(每日更新)全台 4,666 筆、高雄 60 筆全在山區、**鹽埕區 0 筆**;財政部營業(稅籍)登記鹽埕區餐飲類 490 筆(OSM 132 筆的 3.7 倍)。衛生局餐飲分級名冊是 PDF,111 年名冊鹽埕區只列到 2 家飯店餐廳。TDX 需金鑰,未測 | 官方、免金鑰、可整檔下載、含地址與行業別 | 稅籍名稱多為登記名/負責人名、無歇業狀態、地址可能一址多戶;無評價、營業時間、飲食資訊 |
| **OpenStreetMap** | 144 筆 POI;座標好、地址 33%、營業時間 28%、電話 17%;有少量 `diet:*` | 開放授權(ODbL,需標示)、可批次、有座標 | 社群維護、召回率粗估 35–40%、營業時間無人定期驗證、同店重複節點(鴨肉珍兩筆且衝突)、cuisine 標籤會錯 |
| **Google Maps / Places** | **未測** | 一般預期評價、營業時間、價位等級最完整 | 授權與費用限制(詳見下);**不得爬取**;快取限制(以現行條款為準,我這次讀不到完整條款全文) |
| **部落客 / 媒體** | 最多資料(營業時間、菜名、單品價),但經常過期 | 有菜名可抽正向偵測 | 日期不明、地址/時間互相衝突、只適合 Low |
| **聚合平台**(FooTinder、Wanderlog) | 提供評分、價位區間、結束營業時間 | 補洞 | 授權不明、不應直接入庫 |
| **外送平台**(Uber Eats) | 只看到部分店家頁面,且常是其他分店 | 有菜單 | TOS、分店混淆,**不爬** |
| **店家官網** | 30 家 0 個 | — | 鹽埕小店基本沒官網 |
| **FB / IG** | OSM 連到 4 家;**未開啟** | 最即時 | 需登入、反爬、TOS;只存連結 |
| **米其林指南** | 鹽埕媒體報導約 1 家(北港蔡三代筒仔米糕),樣本中的鴨肉珍有列名頁面 | 可當「評價替代訊號」 | 覆蓋極窄、授權另議 |

**Google Maps 的法律提醒**:我嘗試讀取 Google Maps Platform 服務條款,但回傳內容被截斷,**無法引用原文**。依一般認知:Places 內容有快取期限限制、不得大量擷取或建立衍生資料庫、`place_id` 通常可長期保存。**以上都要在正式開發前對照現行條款逐條確認,本報告不構成法律意見。**

## 6. Data Quality Risks

1. **實體混淆**:同名連鎖(港園牛肉麵有 3 分店,媒體清單的「銘邦港園牛肉麵」位於五福四路 53 號,無法確認是否同一家)、同名外地店(Big Mama、陶湘、好貳)、改名/搬家(平津涮牛肉 ↔ 京華餐廳)。
2. **重複節點與衝突**:OSM 有兩筆「鴨肉珍」,一筆說每日 10:00–23:00、一筆說週二休到 20:20。
3. **欄位錯標**:東京小城 OSM 標 japanese,實際描述為台式熱炒/川菜;禪風蔬藝 OSM 標 `taiwanese;argentinian`。
4. **地址不一致**(Do good、九記、田記豆漿):同一家在不同來源門牌或路名不同。
5. **過期風險**:部落客資料 2021–2024,營業時間 50% 衝突。
6. **分店資料借用**:九記的芝麻/核桃資訊來自品牌總店報導,不能直接套到鹽埕分店;傑克兄弟牛排為連鎖,沒有任何頁面證實鹽埕分店。
7. **正向偵測偏誤**:只能找到「有」,找不到「沒有」。若團隊把「沒找到 → 沒有」寫進程式,等於把過敏原當成安全。

## 7. Hard Constraint Feasibility

**1. 過敏原資料能不能取得?** 不能。8 項過敏原共 30×8=240 格,非 unknown 僅 7 格,而且全是「含有」:蟳市長含甲殼類(店名)、田記豆漿含大豆(店名)、郭家肉粽可能含花生(菜名土豆粽)、田記豆漿可能含蛋、九記可能含芝麻與堅果(品牌菜單)、港園牛肉麵可能含麩質(類別推論)。**沒有任何一格能證明「不含」。** 第一手來源(店家公開的過敏原標示)在 30 家中 0 家。
**2. 飲食限制?** 素食只有專營素食店有線索(好貳、Thai Funk Cafe、千葉、禪風、The Borage 共 5 家 `likely`),全來自 OSM 單一標籤或媒體,**0 家 confirmed**;純素 2 家 `likely`;halal、gluten_free 為 0。
**3. 不吃牛 / 豬 / 內臟 / 海鮮?** 「含有」可用店名、菜名偵測並用於排除(牛 3、豬 5、海鮮 3、內臟 1);「不含」無法判斷。例如沒看到「牛」字的店,不能推論不含牛(高湯、醬料、配料都可能含)。
**4. 資料不足時怎麼呈現 Unknown?**
- UI:灰色「未確認」標籤,**絕不用綠色勾**;文字寫「資料來源無法確認,請向店家確認」,並附電話(涵蓋率僅 50%,缺值時給地圖連結)。
- 排序:已確認符合 > 未確認 > 含有疑似衝突者排除;未確認者不得被標成「安全」。
- 群組層級:顯示「N 位成員的限制此店無法確認」,而不是只顯示總分。
- 嚴重過敏模式:僅推薦有第一手證據者;在現有資料下是 0 家,所以要先有「店家自填」或電話確認的流程,否則此模式只能回覆「目前無法保證」。
- 資料模型:存 `claim_value` + `certainty` + `source` + `last_verified_at`,並**分開記錄「含有」與「不含」**,避免 `contains_beef=unknown` 被誤讀成 false。
**5. 只能 Soft Filtering、不能當 Safety Guarantee 的條件**:所有 `likely`/Low 的值;料理類型推論(例如「日式 → 有生食」);素食/純素(除非店家第一手);預算上限(人均價缺失);營業時間(50% 衝突);座位數與包廂;任何由 NLP 或類別推論得來的標記。

## 8. MVP Recommended Fields

**【MVP 可直接依賴】**:restaurant_name、latitude/longitude(缺值走 geocode)、normalized_cuisine_tags(作為 soft 偏好用)、near_public_transport(可算但不具鑑別力,距離排序改用使用者位置)。

**【MVP 可以用,但必須允許 Unknown】**:address、phone、營業時間(附 consistency 與 last_verified,`unknown`/衝突時不得標營業中)、price_level(僅排序輔助、不做硬篩)、social_url、menu_url、`likely` 級 vegetarian/vegan(只作「可能」提示)、「含有」類偵測(用於**排除**)。

**【不應拿來做 Hard Constraint 的資料】**:所有 allergen_*、halal、gluten_free、contains_raw_food、contains_offal、任何 `likely`、預算上限、營業時間、素食/純素、group 相關欄位。

**【第二階段再補】**:評價(先用 Google Places API 實測)、group_friendly/reservable(Places 可能有對應欄位,待測)、parking、官方分級資料(TDX/食藥署)、店家自填的飲食與過敏資訊。

**【需要外部 API / 商業資料源才能穩定取得】**:評價與評論數、可靠營業時間、價位等級、place_id 與照片(Google Places 或同級商業來源);官方料理分類與業者登記(TDX、食藥署業者登錄、商工登記)。

## 9. Missing Fields(本 PoC 完全抓不到或沒測)

official_cuisine_class、price_min_per_person、halal、gluten_free、contains_raw_food、allergen_milk、group_friendly、reservation_url、private_room、table_for_6_plus、parking_available、images、website_url、google_maps_url;以及「評價」與「Google 版營業時間」這兩項**因為沒存取 Google 而未測,不能視為不可得**。

## 10. Minimal Database Schema(只依這次結果)

判斷:`restaurant`、`restaurant_cuisine`、`restaurant_opening_hours`、`restaurant_dietary_claim`、`restaurant_data_source` **要做**;`restaurant_price`、`restaurant_rating`、`restaurant_feature` **先不要做**(資料抓不到或授權未確認,先放在 `restaurant` 的少數欄位或執行期向 Google 查詢)。

```sql
-- 1) 主表:只放 PoC 證實拿得到的欄位
CREATE TABLE restaurant (
  restaurant_id   TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  alternate_name  TEXT,
  address         TEXT,                -- NULL = unknown
  address_quality TEXT,                -- full | partial | conflict
  district        TEXT NOT NULL,
  city            TEXT NOT NULL,
  lat             DOUBLE PRECISION,    -- NULL = unknown
  lng             DOUBLE PRECISION,
  phone           TEXT,
  osm_id          TEXT,
  google_place_id TEXT,                -- 第二階段
  social_url      TEXT,
  menu_url        TEXT,
  existence_check TEXT NOT NULL,       -- web_corroborated | osm_only | entity_conflict
  price_level     SMALLINT,            -- NULL = unknown;僅排序用,不得做硬篩
  status          TEXT NOT NULL DEFAULT 'unverified',  -- active | unverified | closed
  last_verified_at DATE
);

-- 2) 料理:多標籤 + 信心(含 official 與 normalize 兩種來源)
CREATE TABLE restaurant_cuisine (
  restaurant_id TEXT REFERENCES restaurant,
  tag           TEXT NOT NULL,         -- 台式/日式/火鍋/素食/...
  origin        TEXT NOT NULL,         -- official | osm_tag | derived
  confidence    TEXT NOT NULL,         -- High | Medium | Low
  PRIMARY KEY (restaurant_id, tag, origin)
);

-- 3) 營業時間:保留原始字串與一致性,不要只存解析後的結果
CREATE TABLE restaurant_opening_hours (
  restaurant_id TEXT REFERENCES restaurant,
  raw_text      TEXT NOT NULL,         -- OSM 語法或原文
  consistency   TEXT NOT NULL,         -- agree | conflict | single_source
  confidence    TEXT NOT NULL,
  source_id     BIGINT,
  last_verified_at DATE NOT NULL
);

-- 4) 飲食/過敏:EAV;「含有」與「不含」分開記,unknown 不需寫入
CREATE TABLE restaurant_dietary_claim (
  restaurant_id TEXT REFERENCES restaurant,
  claim_type    TEXT NOT NULL,         -- contains_beef | offers_vegetarian | allergen_peanut ...
  claim_value   BOOLEAN NOT NULL,      -- true=含有/提供, false=不含/不提供
  certainty     TEXT NOT NULL,         -- confirmed | likely
  confidence    TEXT NOT NULL,         -- High | Medium | Low
  source_id     BIGINT NOT NULL,
  last_verified_at DATE NOT NULL,
  PRIMARY KEY (restaurant_id, claim_type, source_id)
);
-- 規則:claim_value=false 且 certainty=confirmed 必須 source 為店家第一手;
--       查詢時「沒有任何 claim」= unknown,不是安全。

-- 5) 來源追溯(欄位層級)
CREATE TABLE restaurant_data_source (
  source_id  BIGSERIAL PRIMARY KEY,
  restaurant_id TEXT REFERENCES restaurant,
  field      TEXT NOT NULL,
  value      TEXT,
  source     TEXT NOT NULL,            -- osm | media | first_party | google | gov
  source_url TEXT,
  confidence TEXT NOT NULL,            -- High | Medium | Low | Unknown
  last_verified_at DATE NOT NULL
);
```

`field_provenance.csv` 的欄位與第 5 張表一一對應,可直接匯入驗證。

## 11. Recommended Next Step

1. **補測 Google Places(最優先)**:用同一份 30 家,以 Places API 取 place_id、rating、userRatingCount、regularOpeningHours、priceLevel,以及是否有素食/可訂位/適合團體等欄位(實際欄位以現行文件為準)。目的:量化「評價、營業時間、價位」的涵蓋率,並和本 PoC 的 OSM 營業時間比對一致率。同時逐條核對費用與快取條款。
2. **補測政府資料**:申請 TDX 金鑰測 `Tourism/Restaurant`;另測食藥署食品業者登錄與商工登記的開放資料,看能否提供「業者名稱 + 地址 + 登記狀態」當存在性驗證。
3. **做 10 家電話/實地抽驗**,算出 OSM 營業時間與地址的實際錯誤率,作為「是否能依賴」的門檻依據。
4. **為 Hard Constraint 設計第一手管道**:店家自填表單(LIFF)或 Bot 對話式確認,每筆要有 `last_verified_at` 與到期重驗機制。這是在可預見範圍內唯一能產生 `confirmed 不含` 的做法。
5. **訂 Go / No-Go 門檻**:例如營業時間多源一致 ≥ 70%、餐廳清單召回 ≥ 80%(對照 Google 或政府名單)。沒過就只做「推薦 + 明示未確認」,不做任何安全保證。

## 附錄:來源網址

OSM 快照:Overpass API,2026-10-31,資料 © OpenStreetMap contributors(ODbL)。其餘見 `field_provenance.csv` 的 `source_url`。
