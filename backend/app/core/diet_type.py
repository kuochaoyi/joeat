"""Dining type ("飲食 MBTI"): a 9-question quiz, 3 axes, 8 types.  Fun + a shortcut, NOT a ranking signal.

What it does (user decisions, 2026-11): it tells you a type, SUGGESTS cuisines for your preference list (you can change them), and shows the group
only the composition (counts, never who is what, and only once at least 2 people took it). It never touches hard constraints, the engine or the
ranking: the suggested cuisines become ordinary preferences that you confirm.

Axes (each maps to data we actually have: cuisine tags and distance):
  A / C  adventurous (try the unfamiliar)  vs classic (familiar)
  R / L  rich (strong, hearty flavours)    vs light (fresh, easy)
  W / N  willing to walk                   vs wants it near
"""
from __future__ import annotations

from app.core.ui_meta import CUISINE_CHIPS

AXES = [
    {"key": "adventure", "a": ("A", "嘗鮮"), "b": ("C", "熟悉")},
    {"key": "flavour", "a": ("R", "濃郁"), "b": ("L", "清爽")},
    {"key": "distance", "a": ("W", "願意走"), "b": ("N", "想近")},
]

# (id, axis index, text, option for the first letter of the axis, option for the second)
_Q = [
    ("q1", 0, "菜單上有一道沒看過的料理，你會？", "點點看，好奇心優先", "還是點熟悉的比較安心"),
    ("q2", 0, "朋友說有一間很特別的新店，你通常？", "馬上想去試", "先等大家的評價"),
    ("q3", 0, "旅行時吃飯，你偏好？", "當地沒吃過的特色", "吃得習慣的家常味"),
    ("q4", 1, "想到「今天吃什麼」，你比較被哪個吸引？", "熱騰騰、香氣足、很有味道", "清清爽爽、吃完沒負擔"),
    ("q5", 1, "聚餐後你比較滿意哪種感覺？", "吃得過癮、很飽足", "剛剛好、很輕盈"),
    ("q6", 1, "點菜時你的選擇傾向？", "炸物、烤肉、麻辣、鍋物", "生魚片、沙拉、清湯、輕食"),
    ("q7", 2, "餐廳離集合點多遠你還能接受？", "走 15 分鐘也 OK，好吃最重要", "最好 5 分鐘內到"),
    ("q8", 2, "為了一間評價很好的店，你會？", "願意多走一段路、排隊", "附近有差不多的就好"),
    ("q9", 2, "聚餐當天天氣不太好，你會想？", "照原計畫去那間", "改去最近的那間"),
]
QUESTIONS = [
    {"id": qid, "axis": AXES[ax]["key"], "text": text,
     "options": [{"value": AXES[ax]["a"][0], "label": a}, {"value": AXES[ax]["b"][0], "label": b}]}
    for qid, ax, text, a, b in _Q
]

# code = adventure + flavour + distance letters
TYPES = {
    "ARW": ("🧭", "美食探險家", "為了一碗沒人知道的神店願意跨區，越特別越濃烈越好。"),
    "ARN": ("🌶", "重口味冒險者", "不想走太遠，但附近一定要吃到最嗆、最辣、最新奇的。"),
    "ALW": ("🌿", "清爽尋味者", "愛新鮮、愛嘗試，而且清爽就好，走遠一點也無所謂。"),
    "ALN": ("🍵", "巷口嘗鮮派", "想近、口味清爽，但還是想在家附近找到新花樣。"),
    "CRW": ("🍖", "老饕朝聖者", "吃的是熟悉的好味道，濃郁飽足，值得就走遠一點。"),
    "CRN": ("🍲", "在地飽足派", "熟悉的、濃郁的、就在附近的，最能讓你安心吃飽。"),
    "CLW": ("🍃", "穩健散步派", "熟悉又清爽的味道，順便走一段路消化剛剛好。"),
    "CLN": ("🧋", "安心近處派", "最熟悉、最清爽、最近：不踩雷是你的聚餐哲學。"),
}

# cuisine tag -> (adventure, flavour): +1 leans adventurous / rich, -1 leans classic / light, 0 = neutral. Only chips the UI offers are listed.
_TAG = {
    "台式": (-1, 0), "中式": (-1, 0), "日式": (0, -1), "韓式": (1, 1), "火鍋": (0, 1), "燒肉": (0, 1), "熱炒": (-1, 1), "小吃": (-1, 0),
    "義式": (0, 0), "歐式": (1, -1), "美式": (0, 1), "東南亞": (1, 0), "印度料理": (1, 1), "甜點": (0, -1), "咖啡廳": (-1, -1),
}
MAX_SUGGESTED = 5


def question_axes() -> dict[str, tuple[str, str]]:
    return {q["id"]: (q["options"][0]["value"], q["options"][1]["value"]) for q in QUESTIONS}


def score(answers: dict[str, str]) -> str:
    """answers: question id -> the chosen letter. Every question must be answered with one of its two letters. Returns the 3-letter type code."""
    pairs = question_axes()
    if set(answers) != set(pairs):
        raise ValueError("answer every question")
    letters = ""
    for ax in AXES:
        a, b = ax["a"][0], ax["b"][0]
        mine = [v for q, v in answers.items() if pairs[q] == (a, b)]
        if any(v not in (a, b) for v in mine):
            raise ValueError("invalid answer")
        letters += a if mine.count(a) > mine.count(b) else b                     # 3 questions per axis: never a tie
    return letters


def suggested_cuisines(code: str) -> list[str]:
    """Cuisines whose character matches the type (adventure and flavour axes; the walking axis says nothing about cuisine). Strongest first, at most 5."""
    sa = 1 if code[0] == "A" else -1
    sf = 1 if code[1] == "R" else -1
    offered = [t for t, _ in CUISINE_CHIPS]
    scored = [(t, sa * _TAG[t][0] + sf * _TAG[t][1]) for t in offered if t in _TAG]
    return [t for t, sc in sorted(scored, key=lambda x: (-x[1], offered.index(x[0]))) if sc >= 1][:MAX_SUGGESTED]


def describe(code: str) -> dict:
    emoji, name, summary = TYPES[code]
    return {"code": code, "emoji": emoji, "name": name, "summary": summary, "suggested_cuisines": suggested_cuisines(code)}


def meta() -> dict:
    return {"questions": QUESTIONS, "types": [describe(c) for c in TYPES],
            "axes": [{"key": a["key"], "a": {"letter": a["a"][0], "label": a["a"][1]}, "b": {"letter": a["b"][0], "label": a["b"][1]}} for a in AXES]}


def composition(codes: list[str], joined: int) -> dict:
    """Group view: counts only, never who is what. Hidden until at least 2 people took the quiz (one person's type would identify them)."""
    if len(codes) < 2:
        return {"hidden": True, "taken": len(codes), "joined": joined, "types": [], "axes": []}
    types = [{**{k: v for k, v in describe(c).items() if k in ("code", "emoji", "name")}, "count": codes.count(c)} for c in TYPES if codes.count(c)]
    axes = [{"key": ax["key"], "a": {"label": ax["a"][1], "count": sum(1 for c in codes if c[i] == ax["a"][0])},
             "b": {"label": ax["b"][1], "count": sum(1 for c in codes if c[i] == ax["b"][0])}} for i, ax in enumerate(AXES)]
    return {"hidden": False, "taken": len(codes), "joined": joined, "types": sorted(types, key=lambda t: -t["count"]), "axes": axes}
