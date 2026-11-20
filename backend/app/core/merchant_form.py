"""What the merchant sees: plain-language questions, answer options, the attestation text, and the consumer-facing wording of a declaration.

Wording rules (decision D2): state facts ("店家於 …日 聲明 …"), never promise safety. The words in FORBIDDEN_WORDS must not appear anywhere in this module's output
(a test enforces it). The attestation text below is a PLACEHOLDER: it has NOT been reviewed by a lawyer and must not go live as is.
"""
from __future__ import annotations

from datetime import date

FORBIDDEN_WORDS = ("安全", "保證", "100%", "無過敏原", "零過敏")

ATTESTATION_VERSION = "attest-v0-draft"
ATTESTATION_TEXT = (
    "我是這家店的{role}。上述資訊適用於「本分店、目前的菜單」（菜單日期：{menu_as_of}）。"
    "我了解顧客可能依這些資訊決定是否用餐，並同意在菜單或廚房作業改變時更新。"
)
LEGAL_REVIEW = {"status": "pending", "note": "切結文字尚未經法務審閱，僅供開發與示範，不可正式上線。"}

# attribute -> (name shown to merchants, examples in parentheses)
LABELS = {
    "peanut": ("花生", "花生粉、花生醬、花生油"), "tree_nut": ("堅果", "核桃、杏仁、腰果、榛果"), "shellfish": ("甲殼類與貝類", "蝦、蟹、貝類"),
    "milk": ("牛奶與乳製品", "奶油、起司、鮮奶"), "egg": ("蛋", "蛋製品、美乃滋"), "sesame": ("芝麻", "芝麻粉、芝麻醬"),
    "soy": ("大豆", "豆漿、豆腐、豆花、醬油"), "gluten": ("含麩質穀物", "小麥、大麥、裸麥"),
    "beef": ("牛肉", "含牛肉湯底"), "pork": ("豬肉", "含豬油、豬骨湯底"), "seafood": ("海鮮", "魚類、蝦蟹貝類"),
    "offal": ("內臟", "下水、豬舌、豬腦"), "raw_food": ("生食", "生魚片、生蛋、半熟食"),
    "pets_allowed": ("可攜寵物入內", "室內座位；只有戶外座位可以，請在備註說明"), "kid_friendly": ("親子友善", "有兒童座椅或兒童餐"),
    "vegetarian": ("素食", "請在備註說明蛋奶、五辛是否可"), "vegan": ("純素", "不含蛋奶蜂蜜與動物性成分"),
    "halal": ("清真", "有認證請填認證編號"), "gluten_free": ("無麩質", "請在備註說明如何避免交叉接觸"),
}
SECTIONS = [
    ("allergens", "過敏原", ["peanut", "tree_nut", "shellfish", "milk", "egg", "sesame", "soy", "gluten"]),
    ("ingredients", "其他食材", ["beef", "pork", "seafood", "offal", "raw_food"]),
    ("diets", "飲食需求", ["vegetarian", "vegan", "halal", "gluten_free"]),
    ("needs", "入座需求", ["pets_allowed", "kid_friendly"]),
]
# group-need questions are not about the menu: own wording and answer labels (same answer values as the other require-type questions)
NEED_QUESTIONS = {
    "pets_allowed": ("客人可以帶寵物入內用餐嗎？（室內座位；只有戶外座位可以，請在備註說明）", [("offered", "可以"), ("not_offered", "不可以"), ("not_sure", "我不確定")]),
    "kid_friendly": ("你們親子友善嗎？（有兒童座椅或兒童餐）", [("offered", "有"), ("not_offered", "沒有"), ("not_sure", "我不確定")]),
}
NEED_STATEMENT = {"pets_allowed": ("可攜帶寵物入內", "不可攜帶寵物入內"), "kid_friendly": ("提供兒童座椅或兒童餐", "未提供兒童座椅與兒童餐")}
AVOID_ANSWERS = [("absent_entire_menu", "完全沒有"), ("present_in_some_dishes", "有些餐點有"), ("present_in_most_dishes", "大部分餐點有"), ("not_sure", "我不確定")]
REQUIRE_ANSWERS = [("offered", "有提供"), ("not_offered", "沒有提供"), ("not_sure", "我不確定")]
CROSS_CONTACT = [("confirmed_none", "確認沒有共用"), ("possible", "可能有共用"), ("confirmed_shared", "確定有共用"), ("unknown", "我不確定")]
CC_TEXT = {"confirmed_none": "確認無共用", "possible": "可能共用", "confirmed_shared": "確認共用", "unknown": "未知"}


def form_spec(attrs: dict[str, dict]) -> dict:
    """attrs: attribute_code -> {attribute_type, risk_level}. Built from the database so the form can never ask about an attribute the engine does not know."""
    sections = []
    for key, title, codes in SECTIONS:
        items = []
        for code in codes:
            if code not in attrs:
                continue
            name, eg = LABELS[code]
            avoid = attrs[code]["attribute_type"] == "avoid"
            q_text, q_answers = NEED_QUESTIONS.get(code, (None, None))
            items.append({
                "attribute_code": code, "name": name, "type": attrs[code]["attribute_type"], "risk_level": attrs[code]["risk_level"],
                "question": q_text or (f"你們的菜單裡，有任何餐點使用到「{name}」嗎？（{eg}）" if avoid else f"你們有提供「{name}」餐點嗎？（{eg}）"),
                "answers": [{"value": v, "label": l} for v, l in (q_answers or (AVOID_ANSWERS if avoid else REQUIRE_ANSWERS))],
                "cross_contact": ({"question": f"「{name}」：廚房是否與其他餐點共用鍋具、炸油或工作檯？", "options": [{"value": v, "label": l} for v, l in CROSS_CONTACT],
                                   "asked_when": "absent_entire_menu"} if avoid else None),
                "certificate": code == "halal",
            })
        sections.append({"key": key, "title": title, "items": items})
    return {
        "sections": sections, "default_answer": "not_sure", "validity_days": 90,
        "intro": "請依「目前的菜單」回答。不確定就選「我不確定」，這是完全正常的答案，不會有任何影響。",
        "attestation": {"version": ATTESTATION_VERSION, "template": ATTESTATION_TEXT}, "legal_review": LEGAL_REVIEW,
    }


def describe(plan_row: dict, today: date) -> dict:
    """Consumer-facing sentence for one planned evidence row + what it will count as. plan_row = a row of merchant.declaration_plan()."""
    name = LABELS[plan_row["attribute_code"]][0]
    st, cc = plan_row["new_state"], CC_TEXT[plan_row["cross_contact_status"]]
    if plan_row["attribute_code"] in NEED_STATEMENT:                      # "店家於 … 聲明可攜帶寵物入內。"
        yes, no = NEED_STATEMENT[plan_row["attribute_code"]]
        present = st in ("CONFIRMED_PRESENT", "LIKELY_PRESENT")
        note = "" if st.startswith("CONFIRMED") else "（尚未達到「已確認」）"
        return {"attribute_code": plan_row["attribute_code"], "text": f"店家於 {today} 聲明{yes if present else no}{note}。", "state": st,
                "effect": "confirmed" if st.startswith("CONFIRMED") else "possible"}
    avoid = plan_row["attribute_type"] == "avoid"
    if avoid and st == "CONFIRMED_ABSENT":
        text, effect = f"店家於 {today} 聲明其目前菜單未使用{name}；共用設備：{cc}。", "confirmed"
    elif avoid and st == "LIKELY_ABSENT":
        why = "共用設備尚未確認無共用" if plan_row["capped_by_cross_contact"] else "尚未完成進一步驗證"
        text, effect = f"依店家提供資訊，目前未確認含有{name}（不列為「已確認」：{why}）；共用設備：{cc}。", "possible"
    elif avoid and st in ("CONFIRMED_PRESENT", "LIKELY_PRESENT"):
        if plan_row["capped_by_cross_contact"]:
            text = f"店家表示{name}雖不在菜單上，但與其他餐點共用設備；系統會把這家店視為可能含有{name}。"
        else:
            extent = "大部分" if plan_row["presence_extent"] == "most" else "部分"
            text = f"店家聲明{extent}餐點含有{name}。"
        effect = "contains"
    elif st in ("CONFIRMED_PRESENT", "LIKELY_PRESENT"):
        note = "" if st == "CONFIRMED_PRESENT" else "（尚未達到「已確認」，例如清真需要認證編號）"
        text, effect = f"店家於 {today} 聲明有提供{name}餐點{note}。", "confirmed" if st == "CONFIRMED_PRESENT" else "possible"
    else:
        text, effect = f"店家於 {today} 聲明沒有提供{name}餐點。", "confirmed"
    return {"attribute_code": plan_row["attribute_code"], "text": text, "effect": effect, "state": st}
