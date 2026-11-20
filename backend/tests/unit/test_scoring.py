import pytest

from app.recommendation.scoring import (
    DEFAULT_CONFIG, cuisine_components, distance_m, distance_points, haversine_m, score_restaurant,
)

TAGS = [("日式", None)]


# ---- soft preference scoring ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("stance,points", [("love", 3), ("ok", 1), ("any", 0), ("dislike", -1)])
def test_stance_points(stance, points):
    rows = cuisine_components({"A": {"日式": stance}}, TAGS, DEFAULT_CONFIG)
    assert rows[0].points == points and rows[0].participant_id == "A"


def test_participant_without_matching_preference_scores_zero():
    rows = cuisine_components({"A": {"火鍋": "love"}, "B": {}}, TAGS, DEFAULT_CONFIG)
    assert [r.points for r in rows] == [0, 0]


def test_best_matching_tag_wins_per_participant():
    tags = [("台式", None), ("小吃", None)]
    rows = cuisine_components({"A": {"台式": "ok", "小吃": "love"}}, tags, DEFAULT_CONFIG)
    assert rows[0].points == 3 and rows[0].detail["matched_tag"] == "小吃"


def test_parent_preference_matches_child_tag():
    rows = cuisine_components({"A": {"中式": "love"}}, [("熱炒", "中式")], DEFAULT_CONFIG)
    assert rows[0].points == 3


def test_group_cuisine_score_is_the_sum_over_participants():
    s = score_restaurant({"A": {"日式": "love"}, "B": {"日式": "ok"}, "C": {"日式": "dislike"}, "D": {}}, TAGS, None, 0)
    assert s.cuisine_score == 3 + 1 - 1 + 0


# ---- distance scoring ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("d,points", [(0, 2), (300, 2), (301, 1), (600, 1), (601, 0), (1000, 0), (1001, -1), (5000, -1), (None, 0)])
def test_distance_bands(d, points):
    assert distance_points(d, DEFAULT_CONFIG) == points


def test_distance_unknown_when_coordinates_are_missing():
    assert distance_m(22.62, 120.28, None, None) is None
    assert distance_m(None, None, 22.62, 120.28) is None


def test_distance_is_plausible():
    # about 0.0001 degree of latitude is roughly 11 metres
    assert 9 <= haversine_m(22.62000, 120.28, 22.62010, 120.28) <= 13
    assert distance_m(22.62416, 120.28408, 22.62416, 120.28408) == 0


# ---- totals, data confidence, placeholders ---------------------------------------------------------------------------
def test_total_is_the_sum_of_components_and_matches_the_expected_shape():
    s = score_restaurant({"A": {"日式": "love"}, "B": {"日式": "love"}, "C": {"日式": "ok"}}, TAGS, 250, 2)
    assert s.to_dict() == {"cuisine_score": 7.0, "distance_score": 2.0, "data_confidence_score": 1.0, "rating_score": None, "total_score": 10.0}
    assert s.total_score == sum(r.points for r in s.components)


def test_data_confidence_only_rewards_corroboration_never_penalises_missing_data():
    assert score_restaurant({}, TAGS, None, 0).data_confidence_score == 0
    assert score_restaurant({}, TAGS, None, 1).data_confidence_score == 0
    assert score_restaurant({}, TAGS, None, 2).data_confidence_score == 1


def test_rating_and_price_are_unknown_placeholders_worth_zero():
    s = score_restaurant({"A": {"日式": "love"}}, TAGS, 100, 0)
    by = {r.component: r for r in s.components if r.participant_id is None}
    assert by["rating"].raw_value == "UNKNOWN" and by["rating"].points == 0
    assert by["price"].raw_value == "UNKNOWN" and by["price"].points == 0
    assert s.rating_score is None
