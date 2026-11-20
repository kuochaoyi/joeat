import pytest

from app.er.normalize import address_key, clean_name
from app.er.scoring import address_score, idf_weights, name_score


def test_address_key_handles_postcode_fullwidth_dashes_and_floors():
    assert address_key("803高雄市鹽埕區瀨南街201號") == ("瀨南街", "", 201, "")
    assert address_key("高雄市鹽埕區中原里瀨南街２０１號１樓") == ("瀨南街", "", 201, "")
    assert address_key("高雄市鹽埕區必信街116―1號1樓") == ("必信街", "", 116, "1")
    assert address_key("高雄市鹽埕區富野路56巷10號") == ("富野路", "56巷", 10, "")
    assert address_key(None) is None and address_key("沒有門牌") is None


@pytest.mark.parametrize("a,b,pts,why", [
    ("高雄市鹽埕區五福四路258號", "高雄市鹽埕區教仁里五福四路２５８號１樓", 40, "exact"),
    ("高雄市鹽埕區五福四路146號", "高雄市鹽埕區五福四路146―2號", 30, "same_main_number_sub_differs"),
    ("高雄市鹽埕區鹽埕路36巷23號", "高雄市鹽埕區鹽埕街36巷23號", 25, "road_suffix_variant"),
    ("高雄市鹽埕區大義街126號", "高雄市鹽埕區新樂街75之3號", -10, "different"),
    (None, "高雄市鹽埕區新樂街75號", 0, "missing"),
])
def test_address_score(a, b, pts, why):
    assert address_score(a, b) == (pts, why)


def test_name_cleaning_removes_legal_forms():
    assert clean_name("鐘庵有限公司") == clean_name("鐘庵") == "鐘庵"
    assert clean_name("Ｔｈｅ　Ｂｏｒａｇｅ") == clean_name("The Borage")


def test_name_scores_exact_containment_generic_and_shared_tokens():
    assert name_score("鴨肉珍", "鴨肉珍小吃店")[1] == "exact"
    assert name_score("香港馬興記燒臘臘味專賣店", "香港馬興記燒臘店") == (34, "containment")
    assert name_score("豆花", "豆花")[0] == 20 and name_score("豆花", "豆花")[1].endswith("(generic)")      # generic names are halved
    w = idf_weights(["郭家肉粽", "孫家肉粽", "肉粽", "小吃", "家和肉粽", "金記肉粽"])
    assert name_score("郭家肉粽", "孫家肉粽", w)[0] < 20, "sharing a common token must not look like the same shop"
    assert name_score("陶湘火鍋店", "", w) == (0.0, "unavailable")
