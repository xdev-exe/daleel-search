from app.normalizer import normalize_text, looks_like_name_query, build_mode


def test_arabic_normalization():
    assert normalize_text("أحمد جابر") == "احمد جابر"


def test_name():
    assert looks_like_name_query("doctor mohamed aymen")
    assert build_mode("doctor mohamed aymen", None, None) == "NAME"


def test_semantic_geo():
    assert build_mode("عايز دكتور اسنان قريب مني", 31.0, 30.0) == "HYBRID_GEO"
