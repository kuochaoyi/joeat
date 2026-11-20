"""UI-facing metadata: grouping / ordering / labels for the constraint and cuisine pickers, and meeting-point presets.

Attribute definitions (type, risk, descriptions) live in the database (ref.attribute). Only presentation lives here.
Meeting-point coordinates come from OpenStreetMap transit stations (data/raw/osm_transit_stations.json, (c) OpenStreetMap contributors, ODbL).
"""

ATTRIBUTE_GROUPS = [
    ("ingredients", "不吃的食材", ["beef", "pork", "seafood", "shellfish", "offal", "raw_food"]),
    ("allergens", "過敏原", ["peanut", "tree_nut", "milk", "egg", "sesame", "soy", "gluten"]),
    ("diets", "飲食需求", ["vegetarian", "vegan", "halal", "gluten_free"]),
]
# Group needs the HOST chooses for the whole session (not any member's private constraint): session flag -> (attribute, soft).
# soft = a refusal is only a warning; otherwise a restaurant that explicitly refuses is excluded (unknown is always just a warning).
GROUP_NEEDS = {"needs_pets": ("pets_allowed", False), "needs_kids": ("kid_friendly", True)}
NEED_ATTRIBUTES = {code for code, _ in GROUP_NEEDS.values()}
ALLERGEN_CODES = {"peanut", "tree_nut", "milk", "egg", "sesame", "soy", "gluten", "shellfish"}

# 15 chips (歐式 added after user testing; 義式 is its child, so choosing 歐式 also matches Italian places); value = (ref.cuisine_tag, label shown)
CUISINE_CHIPS = [
    ("台式", "台式"), ("中式", "中式"), ("日式", "日式"), ("韓式", "韓式"), ("火鍋", "火鍋"), ("燒肉", "燒肉"), ("熱炒", "熱炒"),
    ("小吃", "小吃"), ("義式", "義式"), ("歐式", "歐式"), ("美式", "美式"), ("東南亞", "東南亞"), ("印度料理", "印度料理"), ("甜點", "甜點"), ("咖啡廳", "咖啡"),
]
STANCES = [("love", "🔥 很想吃"), ("ok", "👍 可以"), ("any", "😐 都好"), ("dislike", "👎 不太想")]

LOCATION_PRESETS = [
    {"key": "yancheng_pu", "label": "捷運鹽埕埔站", "lat": 22.62416, "lon": 120.28408},
    {"key": "pier2_dayi", "label": "駁二大義站（輕軌）", "lat": 22.61850, "lon": 120.28422},
    {"key": "pier2_penglai", "label": "駁二蓬萊站（輕軌）", "lat": 22.62045, "lon": 120.27992},
    {"key": "wenwu", "label": "文武聖殿站（輕軌）", "lat": 22.62955, "lon": 120.28073},
    {"key": "shoushan_park", "label": "壽山公園站（輕軌）", "lat": 22.62653, "lon": 120.27867},
    {"key": "hamasen", "label": "捷運哈瑪星站", "lat": 22.62137, "lon": 120.27480},
]
