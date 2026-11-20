"""Dining type quiz: scoring, suggestions and the privacy rule of the group view. Pure functions."""
import pytest

from app.core import diet_type as d
from app.core.ui_meta import CUISINE_CHIPS


def answers(adv, flav, dist):
    """adv / flav / dist: the letters picked for the 3 questions of each axis."""
    letters = list(adv) + list(flav) + list(dist)
    return {q["id"]: letters[i] for i, q in enumerate(d.QUESTIONS)}


def test_the_quiz_has_nine_questions_three_per_axis_and_eight_types():
    assert len(d.QUESTIONS) == 9 and len(d.TYPES) == 8
    for ax in d.AXES:
        assert sum(1 for q in d.QUESTIONS if q["axis"] == ax["key"]) == 3
    assert {c for c in d.TYPES} == {a + b + c for a in "AC" for b in "RL" for c in "WN"}
    for q in d.QUESTIONS:
        assert len(q["options"]) == 2 and q["options"][0]["value"] != q["options"][1]["value"]


@pytest.mark.parametrize("picked, code", [
    (("AAA", "RRR", "WWW"), "ARW"), (("CCC", "LLL", "NNN"), "CLN"), (("AAC", "RLL", "NNW"), "ALN"), (("ACC", "LRR", "WWN"), "CRW"),
])
def test_each_axis_is_decided_by_the_majority_of_its_three_answers(picked, code):
    assert d.score(answers(*picked)) == code


def test_incomplete_or_invalid_answers_are_refused():
    ok = answers("AAA", "RRR", "WWW")
    with pytest.raises(ValueError):
        d.score({k: v for k, v in ok.items() if k != "q9"})
    with pytest.raises(ValueError):
        d.score({**ok, "q1": "X"})
    with pytest.raises(ValueError):
        d.score({**ok, "q1": "R"})                          # a letter from another axis


def test_suggestions_are_offered_cuisines_matching_the_type_and_capped():
    offered = {t for t, _ in CUISINE_CHIPS}
    for code in d.TYPES:
        s = d.suggested_cuisines(code)
        assert 1 <= len(s) <= d.MAX_SUGGESTED and set(s) <= offered
    assert "韓式" in d.suggested_cuisines("ARW") and "台式" in d.suggested_cuisines("CRN")
    assert "火鍋" not in d.suggested_cuisines("CLN") and "東南亞" not in d.suggested_cuisines("CLW")
    assert d.suggested_cuisines("ARW") == d.suggested_cuisines("ARN")      # the walking axis says nothing about cuisine


def test_the_group_view_shows_counts_only_and_hides_until_two_people_took_the_quiz():
    one = d.composition(["ARW"], joined=4)
    assert one["hidden"] is True and one["types"] == [] and one["taken"] == 1                         # one type would identify its owner
    many = d.composition(["ARW", "ARW", "CLN"], joined=4)
    assert many["hidden"] is False and many["taken"] == 3
    assert [(t["code"], t["count"]) for t in many["types"]] == [("ARW", 2), ("CLN", 1)]
    assert {a["key"]: (a["a"]["count"], a["b"]["count"]) for a in many["axes"]} == {"adventure": (2, 1), "flavour": (2, 1), "distance": (2, 1)}
    assert "participant" not in str(many)


def test_type_texts_never_promise_anything_about_safety():
    from app.core.merchant_form import FORBIDDEN_WORDS
    text = str(d.meta())
    assert not any(w in text for w in FORBIDDEN_WORDS)
