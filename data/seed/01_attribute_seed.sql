-- attribute_seed.sql : MVP reference data for the hard-constraint layer. Load after schema_v2.sql.
-- Contents: evidence states, evidence bases, legal (state, basis) pairs, attribute dictionary, implications,
--           constraint reasons, decision rules (the executable form of recommendation_data_contract.md), scoring config v1.
-- Run order is irrelevant to other seeds; this file has no restaurant data.

BEGIN;

-- ---------------------------------------------------------------- evidence states (UNKNOWN != SAFE, LIKELY_ABSENT != SAFE)
INSERT INTO ref.evidence_state_def (state, meaning_zh, allowed_basis_note, usable_for_hard_constraint, may_show_safe) VALUES
('CONFIRMED_PRESENT', '已確認含有（或已確認提供）。證據直接指向此店此分店。', '官方菜單、店家聲明、或店名本身直接包含該食材/品項（僅限 avoid 類）', TRUE,  FALSE),
('LIKELY_PRESENT',    '很可能含有（或很可能提供）。有間接證據但未經店家確認。', '媒體/部落格菜名、OSM 標籤、類別推論、品牌層級資料、菜單提及「可能含有」', TRUE,  FALSE),
('LIKELY_ABSENT',     '推測不含（或推測不提供）。只代表沒有看到、或有弱證據，不等於安全。', '媒體/OSM/類別推論、菜單未列但無店家聲明', FALSE, FALSE),
('CONFIRMED_ABSENT',  '已確認不含（或已確認不提供）。只能來自第一手證據，且有效期限。', '官方菜單、店家聲明；來源必須是 first-party；信心必須 HIGH；必須有 valid_until（≤180 天）', TRUE,  TRUE),
('UNKNOWN',           '未知。沒有可靠證據。這是合法狀態，不排除、但必須產生警示。', '沒有證據列即為 UNKNOWN；或明確記錄「已查過但無資訊」', FALSE, FALSE);

INSERT INTO ref.evidence_basis (basis, is_first_party_basis, description) VALUES
('official_menu',          TRUE,  '店家官方菜單（含官方社群貼出的菜單）'),
('restaurant_declaration', TRUE,  '店家直接聲明（表單、電話、對話確認）'),
('restaurant_name',        FALSE, '店名本身含有該食材或品項（例如「蟳」「牛肉麵」「排骨飯」）'),
('media_text',             FALSE, '媒體、部落格、聚合平台的文字描述'),
('osm_tag',                FALSE, 'OpenStreetMap 社群標籤'),
('category_inference',     FALSE, '由料理類別推論（例如麵店推論含麩質），不是事實'),
('no_information_found',   FALSE, '已檢視來源但沒有相關資訊（僅用於 UNKNOWN）');

INSERT INTO ref.evidence_state_basis_rule (state, basis) VALUES
('CONFIRMED_PRESENT','official_menu'), ('CONFIRMED_PRESENT','restaurant_declaration'), ('CONFIRMED_PRESENT','restaurant_name'),
('LIKELY_PRESENT','official_menu'), ('LIKELY_PRESENT','restaurant_declaration'), ('LIKELY_PRESENT','restaurant_name'),
('LIKELY_PRESENT','media_text'), ('LIKELY_PRESENT','osm_tag'), ('LIKELY_PRESENT','category_inference'),
('LIKELY_ABSENT','official_menu'), ('LIKELY_ABSENT','restaurant_name'), ('LIKELY_ABSENT','media_text'), ('LIKELY_ABSENT','osm_tag'), ('LIKELY_ABSENT','category_inference'),
('CONFIRMED_ABSENT','official_menu'), ('CONFIRMED_ABSENT','restaurant_declaration'),
('UNKNOWN','no_information_found');

-- ---------------------------------------------------------------- attribute dictionary (19: 17 food attributes + 2 group needs)
INSERT INTO ref.attribute (attribute_code, display_name_zh, attribute_type, risk_level, description, default_unknown_behavior, sort_order) VALUES
('peanut',     '花生',   'avoid',   'critical', '花生及花生製品（含土豆粽等以花生入菜者）。過敏原。',                         'warn_critical', 10),
('tree_nut',   '堅果',   'avoid',   'critical', '樹生堅果（核桃、杏仁、腰果、榛果等）。過敏原。',                              'warn_critical', 11),
('shellfish',  '甲殼類／貝類', 'avoid', 'critical', '蝦、蟹、貝類、頭足類以外的甲殼與軟體動物。過敏原；蟹／蝦／蛤蜊皆屬之。',        'warn_critical', 12),
('milk',       '乳製品', 'avoid',   'critical', '牛奶及乳製品（含奶油、起司、鮮奶）。過敏原。',                               'warn_critical', 13),
('egg',        '蛋',     'avoid',   'critical', '蛋及蛋製品（蛋餅、蛋糕、美乃滋等）。過敏原。',                               'warn_critical', 14),
('sesame',     '芝麻',   'avoid',   'critical', '芝麻及芝麻製品（芝麻糊、麻油除外與否須另述）。過敏原。',                       'warn_critical', 15),
('soy',        '大豆',   'avoid',   'critical', '大豆及豆製品（豆漿、豆花、豆腐、醬油）。過敏原。',                            'warn_critical', 16),
('gluten',     '麩質',   'avoid',   'critical', '含麩質穀物（小麥、大麥、裸麥）。乳糜瀉或過敏者使用；與 gluten_free 為不同方向。',  'warn_critical', 17),
('seafood',    '海鮮',   'avoid',   'high',     '魚類與海鮮整體。shellfish 為其子集；魚類過敏者也使用此項。',                    'warn',          20),
('beef',       '牛肉',   'avoid',   'high',     '牛肉及牛肉製品（含牛肉湯底）。信仰或飲食原因。',                              'warn',          21),
('pork',       '豬肉',   'avoid',   'high',     '豬肉及豬肉製品（含豬油、豬骨湯底）。信仰或飲食原因。',                         'warn',          22),
('raw_food',   '生食',   'avoid',   'high',     '生魚片、生蛋、半熟食等未完全加熱食物。孕婦、免疫低下者使用。',                  'warn',          23),
('offal',      '內臟',   'avoid',   'normal',   '動物內臟（下水、豬舌、豬腦等）。多為口味因素。',                              'note',          30),
('vegetarian', '素食',   'require', 'high',     '店家能提供符合素食者的餐點。五辛、蛋奶是否可食須另述。',                       'warn',          40),
('vegan',      '純素',   'require', 'high',     '店家能提供純素餐點（無蛋奶蜂蜜、無動物性成分）。',                            'warn',          41),
('halal',      '清真',   'require', 'high',     '店家有清真認證或可靠聲明。',                                              'warn',          42),
('gluten_free','無麩質', 'require', 'critical', '店家能提供無麩質餐點且處理交叉污染。乳糜瀉者使用，故為 critical。',            'warn_critical', 43),
('pets_allowed','可攜寵物', 'require', 'normal',   '客人可以帶寵物入內用餐（室內座位）。由發起人在聚餐層級選擇「有人帶寵物」；店家明確不可才排除，未知只警示。', 'note', 50),
('kid_friendly','親子友善', 'require', 'normal',   '有提供兒童座椅或兒童餐。由發起人在聚餐層級選擇「有人帶小孩」；永遠只警示，不排除。',                    'note', 51);

INSERT INTO ref.attribute_implication (sub_attr, super_attr) VALUES ('shellfish', 'seafood'), ('vegan', 'vegetarian');

-- ---------------------------------------------------------------- why a participant has a constraint (raises, never lowers, the risk level)
INSERT INTO ref.constraint_reason (reason, min_risk_level, label_zh) VALUES
('allergy', 'critical', '過敏'), ('medical', 'critical', '醫療／健康'), ('religion', 'high', '宗教'),
('belief_diet', 'high', '信念／飲食方式'), ('dislike', 'normal', '絕對不吃（口味）'), ('unspecified', 'normal', '未說明');

-- ---------------------------------------------------------------- decision rules (30 = 2 types x 3 risk levels x 5 states)
-- avoid : the user wants the thing NOT present.   require : the user wants it present.
INSERT INTO ref.constraint_decision_rule (attribute_type, risk_level, state, action, warning_level, may_show_safe_badge, note) VALUES
-- avoid / critical
('avoid','critical','CONFIRMED_PRESENT','EXCLUDE','none',FALSE,'確認含有，排除'),
('avoid','critical','LIKELY_PRESENT',   'EXCLUDE','none',FALSE,'critical 風險：疑似含有也排除'),
('avoid','critical','UNKNOWN',          'WARN','critical',FALSE,'不排除，但必須置頂警示：無法確認'),
('avoid','critical','LIKELY_ABSENT',    'WARN','critical',FALSE,'視同未知；推測不含不等於安全'),
('avoid','critical','CONFIRMED_ABSENT', 'PASS','none',TRUE,'唯一可顯示「已有第一手資料確認」的狀態'),
-- avoid / high
('avoid','high','CONFIRMED_PRESENT','EXCLUDE','none',FALSE,'確認含有，排除'),
('avoid','high','LIKELY_PRESENT',   'EXCLUDE','none',FALSE,'high 風險：疑似含有也排除'),
('avoid','high','UNKNOWN',          'WARN','high',FALSE,'不排除，高度警示'),
('avoid','high','LIKELY_ABSENT',    'WARN','high',FALSE,'視同未知'),
('avoid','high','CONFIRMED_ABSENT', 'PASS','none',TRUE,'第一手確認不含'),
-- avoid / normal
('avoid','normal','CONFIRMED_PRESENT','EXCLUDE','none',FALSE,'確認含有，排除'),
('avoid','normal','LIKELY_PRESENT',   'WARN','high',FALSE,'保留但以高風險提示（口味類條件，不直接排除）'),
('avoid','normal','UNKNOWN',          'WARN','normal',FALSE,'不排除，一般警示'),
('avoid','normal','LIKELY_ABSENT',    'WARN','normal',FALSE,'視同未知'),
('avoid','normal','CONFIRMED_ABSENT', 'PASS','none',TRUE,'第一手確認不含'),
-- require / critical
('require','critical','CONFIRMED_PRESENT','PASS','none',TRUE,'第一手確認提供'),
('require','critical','LIKELY_PRESENT',   'PASS_CONDITIONAL','critical',FALSE,'有條件通過：未經店家確認，critical 需明確警示'),
('require','critical','UNKNOWN',          'WARN','critical',FALSE,'保留但置頂警示'),
('require','critical','LIKELY_ABSENT',    'EXCLUDE','none',FALSE,'critical 需求：疑似不提供就排除'),
('require','critical','CONFIRMED_ABSENT', 'EXCLUDE','none',FALSE,'確認不提供，排除'),
-- require / high
('require','high','CONFIRMED_PRESENT','PASS','none',TRUE,'第一手確認提供'),
('require','high','LIKELY_PRESENT',   'PASS_CONDITIONAL','normal',FALSE,'有條件通過：未經店家確認'),
('require','high','UNKNOWN',          'WARN','high',FALSE,'保留但高度警示'),
('require','high','LIKELY_ABSENT',    'EXCLUDE','none',FALSE,'high 需求：疑似不提供就排除'),
('require','high','CONFIRMED_ABSENT', 'EXCLUDE','none',FALSE,'確認不提供，排除'),
-- require / normal
('require','normal','CONFIRMED_PRESENT','PASS','none',TRUE,'第一手確認提供'),
('require','normal','LIKELY_PRESENT',   'PASS_CONDITIONAL','normal',FALSE,'有條件通過'),
('require','normal','UNKNOWN',          'WARN','normal',FALSE,'保留，一般警示'),
('require','normal','LIKELY_ABSENT',    'WARN','normal',FALSE,'保留並警示（normal 需求不排除）'),
('require','normal','CONFIRMED_ABSENT', 'EXCLUDE','none',FALSE,'確認不提供，排除');

-- ---------------------------------------------------------------- scoring config v1 (deterministic; no ML)
INSERT INTO ref.scoring_config (version, config, is_active, note) VALUES
('v1', '{
  "top_n": 3,
  "cuisine_stance_points": {"love": 3, "ok": 1, "any": 0, "dislike": -1},
  "distance_bands_m": [{"max": 300, "points": 2}, {"max": 600, "points": 1}, {"max": 1000, "points": 0}, {"max": null, "points": -1}],
  "data_confidence": {"multi_source_points": 1, "single_source_points": 0},
  "rating": {"enabled": false, "note": "no validated rating source"},
  "price": {"mode": "soft_unknown_no_points", "note": "per-person price coverage too low; budget never excludes"},
  "tiebreak": ["total_score desc", "critical_warning_count asc", "warning_count asc", "distance_m asc", "restaurant_id"]
}'::jsonb, TRUE, 'provisional weights; tune after real sessions');

-- ---------------------------------------------------------------- merchant declarations (migration 0003): a basic-level declaration of absence may only be LIKELY_ABSENT
INSERT INTO ref.evidence_state_basis_rule (state, basis) VALUES ('LIKELY_ABSENT', 'restaurant_declaration') ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------- safety vs preference (columns added by migration 0003)
-- Class belongs to the CONSTRAINT: the participant's reason decides; "unspecified" falls back to the attribute default.
UPDATE ref.attribute SET default_constraint_class = 'safety' WHERE attribute_code IN ('peanut','tree_nut','shellfish','milk','egg','sesame','soy','gluten','gluten_free');
UPDATE ref.constraint_reason SET constraint_class = 'safety' WHERE reason IN ('allergy','medical','religion');

COMMIT;
