"""Sorting and Top-N selection. Deterministic: the same inputs always give the same order."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RankInput:
    restaurant_id: str
    total_score: float
    critical_warning_count: int
    warning_count: int
    distance_m: int | None


def sort_key(c: RankInput) -> tuple:
    """score desc -> fewer critical warnings -> fewer warnings -> nearer (unknown distance last) -> restaurant_id."""
    return (-c.total_score, c.critical_warning_count, c.warning_count, c.distance_m is None, c.distance_m if c.distance_m is not None else 0, c.restaurant_id)


def rank(candidates: list[RankInput], top_n: int = 3) -> list[RankInput]:
    return sorted(candidates, key=sort_key)[:top_n]
