"""Soft ranking: deterministic, explainable, no ML.

Components (all stored per candidate):
  cuisine_preference  per participant: love +3, ok +1, any 0, dislike -1 (best match among the restaurant's tags; none matched = 0)
  distance            bands from the meeting point; unknown distance = 0 and a `distance_unknown` warning (never excluded)
  data_confidence     +1 only when >=2 independent sources have settled the restaurant's identity; missing data adds nothing
  rating / price      placeholders: UNKNOWN, 0 points. No validated source exists yet, and budget never excludes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ScoringConfig:
    version: str
    top_n: int
    stance_points: Mapping[str, float]
    distance_bands: Sequence[tuple[int | None, float]]       # (max_m or None for "anything farther", points)
    multi_source_points: float
    raw: Mapping[str, Any] = field(default_factory=dict, compare=False)

    @classmethod
    def from_json(cls, version: str, cfg: Mapping[str, Any]) -> "ScoringConfig":
        bands = [(b["max"], float(b["points"])) for b in cfg["distance_bands_m"]]
        return cls(version=version, top_n=int(cfg.get("top_n", 3)),
                   stance_points={k: float(v) for k, v in cfg["cuisine_stance_points"].items()},
                   distance_bands=bands, multi_source_points=float(cfg["data_confidence"]["multi_source_points"]), raw=cfg)


DEFAULT_CONFIG = ScoringConfig.from_json("v1", {
    "top_n": 3,
    "cuisine_stance_points": {"love": 3, "ok": 1, "any": 0, "dislike": -1},
    "distance_bands_m": [{"max": 300, "points": 2}, {"max": 600, "points": 1}, {"max": 1000, "points": 0}, {"max": None, "points": -1}],
    "data_confidence": {"multi_source_points": 1, "single_source_points": 0},
})


@dataclass
class ComponentRow:
    component: str
    points: float
    participant_id: str | None = None
    raw_value: str | None = None
    detail: dict = field(default_factory=dict)


@dataclass
class ScoreBreakdown:
    cuisine_score: float
    distance_score: float
    data_confidence_score: float
    rating_score: float | None
    total_score: float
    distance_m: int | None
    components: list[ComponentRow]

    def to_dict(self) -> dict:
        return {"cuisine_score": self.cuisine_score, "distance_score": self.distance_score,
                "data_confidence_score": self.data_confidence_score, "rating_score": self.rating_score, "total_score": self.total_score}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371000.0 * math.asin(math.sqrt(a))


def distance_m(meet_lat: float | None, meet_lon: float | None, lat: float | None, lon: float | None) -> int | None:
    if None in (meet_lat, meet_lon, lat, lon):
        return None
    return int(round(haversine_m(meet_lat, meet_lon, lat, lon)))


def distance_points(d: int | None, cfg: ScoringConfig) -> float:
    if d is None:
        return 0.0
    for max_m, pts in cfg.distance_bands:
        if max_m is None or d <= max_m:
            return pts
    return 0.0


def cuisine_components(
    preferences: Mapping[str, Mapping[str, str]],       # participant_id -> {cuisine_tag: stance}
    restaurant_tags: Sequence[tuple[str, str | None]],  # (tag, parent_tag)
    cfg: ScoringConfig,
) -> list[ComponentRow]:
    """One row per participant. A preference for a parent tag (中式) also matches its children (熱炒, 港式)."""
    rows: list[ComponentRow] = []
    for pid in sorted(preferences):
        best: tuple[float, str, str] | None = None
        for tag, parent in restaurant_tags:
            for key in {tag, parent} - {None}:
                stance = preferences[pid].get(key)
                if stance is None:
                    continue
                pts = cfg.stance_points[stance]
                if best is None or pts > best[0]:
                    best = (pts, stance, key)
        if best:
            rows.append(ComponentRow("cuisine_preference", best[0], pid, best[1], {"matched_tag": best[2]}))
        else:
            rows.append(ComponentRow("cuisine_preference", 0.0, pid, None, {"matched_tag": None}))
    return rows


def score_restaurant(
    preferences: Mapping[str, Mapping[str, str]],
    restaurant_tags: Sequence[tuple[str, str | None]],
    dist_m: int | None,
    settled_source_count: int,
    cfg: ScoringConfig = DEFAULT_CONFIG,
) -> ScoreBreakdown:
    cuisine_rows = cuisine_components(preferences, restaurant_tags, cfg)
    cuisine = sum(r.points for r in cuisine_rows)
    dist_pts = distance_points(dist_m, cfg)
    conf_pts = cfg.multi_source_points if settled_source_count >= 2 else 0.0
    comps = list(cuisine_rows)
    comps.append(ComponentRow("distance", dist_pts, None, None if dist_m is None else str(dist_m), {"state": "UNKNOWN" if dist_m is None else "known"}))
    comps.append(ComponentRow("data_confidence", conf_pts, None, str(settled_source_count),
                              {"rule": "points only when >=2 independent sources are settled; missing data adds nothing"}))
    comps.append(ComponentRow("rating", 0.0, None, "UNKNOWN", {"state": "UNKNOWN", "note": "no validated rating source"}))
    comps.append(ComponentRow("price", 0.0, None, "UNKNOWN", {"state": "UNKNOWN", "note": "no per-person price data; budget is soft only"}))
    total = cuisine + dist_pts + conf_pts
    return ScoreBreakdown(cuisine_score=cuisine, distance_score=dist_pts, data_confidence_score=conf_pts, rating_score=None,
                          total_score=total, distance_m=dist_m, components=comps)
