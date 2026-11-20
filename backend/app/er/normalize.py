"""Address / name normalisation for entity resolution (ported from the PoC's er_v1.py; rules in poc_yancheng/er_v1_spec.md)."""
import re
import unicodedata

_ADDR = re.compile(r"^(?:高雄市)?(?:鹽埕區)?(?:[^路街\d]{1,4}里)?((?:[^\d（(]+?)(?:路|街))((?:\d+巷)?(?:\d+弄)?)(\d+)(?:之(\d+))?號")
_STOP = ["股份有限公司", "有限公司", "企業社", "商行", "餐飲", "食品", "小吃店", "麵店", "工作室", "商號", "店", "館", "鹽埕", "高雄", "總店", "分店"]


def nfkc(s: str | None) -> str:
    return unicodedata.normalize("NFKC", s or "")


def address_key(addr: str | None) -> tuple[str, str, int, str] | None:
    """(road, lane, house number, sub-number) or None when the address cannot be parsed. Handles full-width digits,
    leading postcodes (OSM `803高雄市…`), dash variants as 之, 里 prefixes and floors."""
    if not addr:
        return None
    a = re.sub(r"^\d{3,6}", "", re.sub(r"[-－―—–‑]", "之", nfkc(addr)).replace(" ", ""))
    m = _ADDR.match(a)
    return (m.group(1), m.group(2) or "", int(m.group(3)), m.group(4) or "") if m else None


def clean_name(name: str | None) -> str:
    n = re.sub(r"[（(].*?[）)]", "", nfkc(name))
    n = re.sub(r"[\s\-·・.,&'’]", "", n).lower()
    for s in _STOP:
        n = n.replace(s, "")
    return n


def bigrams(s: str) -> set[str]:
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else ({s} if s else set())
