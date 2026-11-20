"""Entity-resolution scoring components (address + name). All numbers come from er_v1_config.json and are PROVISIONAL
(see poc_yancheng/er_v1_spec.md section 7: tuned on nothing, validated on nothing). Category / geo / ambiguity terms are not ported yet."""
import json
import math
from collections import Counter
from pathlib import Path
from typing import Iterable

from app.er.normalize import address_key, bigrams, clean_name

CONFIG = json.loads((Path(__file__).parent / "er_v1_config.json").read_text(encoding="utf-8"))


def address_score(a: str | None, b: str | None, cfg: dict = CONFIG) -> tuple[float, str]:
    c = cfg["address"]
    ka, kb = address_key(a), address_key(b)
    if not ka or not kb:
        return c["missing_either"], "missing"
    if ka[:3] == kb[:3]:
        return (c["exact_key"], "exact") if ka[3] == kb[3] else (c["same_main_number_sub_differs"], "same_main_number_sub_differs")
    if ka[1] == kb[1] and ka[2] == kb[2] and ka[0][:-1] == kb[0][:-1]:
        return c["road_suffix_variant_same_number"], "road_suffix_variant"
    if ka[0] == kb[0] and ka[1] == kb[1] and abs(ka[2] - kb[2]) <= 2 and ka[2] % 2 == kb[2] % 2:
        return c["near_same_road_same_parity_within_2"], "near"
    return c["both_present_but_different"], "different"


def idf_weights(names: Iterable[str]) -> dict[str, float]:
    df: Counter = Counter()
    for n in names:
        for g in bigrams(clean_name(n)):
            df[g] += 1
    return {g: 1.0 / (1.0 + math.log(max(1, k))) for g, k in df.items()}


def name_score(name_a: str, name_b: str, weights: dict[str, float] | None = None, cfg: dict = CONFIG) -> tuple[float, str]:
    c = cfg["name"]
    a, b = clean_name(name_a), clean_name(name_b)
    if not a or not b:
        return 0.0, "unavailable"
    generic = a in set(cfg["generic_names"]) or len(a) <= 2
    if a == b:
        s, why = c["exact_clean"], "exact"
    elif min(len(a), len(b)) >= c["containment_min_chars"] and (a in b or b in a):
        s, why = c["containment_points"], "containment"
    else:
        w = (lambda g: weights.get(g, 1.0)) if weights else (lambda g: 1.0)
        A, B = bigrams(a), bigrams(b)
        union = sum(w(g) for g in A | B)
        s, why = (c["max_points"] * sum(w(g) for g in A & B) / union if union else 0.0), "bigram_jaccard"
    return (s * c["generic_name_multiplier"], why + " (generic)") if generic else (s, why)
