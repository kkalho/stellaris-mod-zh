# 翻译门禁回归测试（validate_translations）
# 背景：HARD_REVIEWS 的「好评」需放行结构化标签前缀「👍 好评：」（batch16+ 标准格式），
# 同时仍要拦截编造形态（获得 N 好评 / 好评率 / 官方数据显示）。
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.validate_translations import scan_entry  # noqa: E402


def _hits_for(reviews_text):
    return scan_entry({"steam_id": "123", "reviews_zh": reviews_text})


def test_label_prefix_allowed():
    """「👍 好评：」标签前缀是格式，不是编造，必须放行。"""
    hits = _hits_for("👍 好评：作者自述面向休闲玩家。\n⚠️ 注意：作者声明禁止商用。")
    assert hits == [], f"标签前缀被误拦: {hits}"


def test_fabricated_praise_blocked():
    """编造社区评价的典型形态必须全部拦截。"""
    for text in (
        "获得 5000 条好评的 MOD",
        "好评率高达 97%",
        "广受好评，好评如潮",
        "Mod 界的神作、天花板",
        "官方数据显示本 MOD 是标杆",
    ):
        hits = _hits_for(text)
        assert hits, f"编造措辞漏拦: {text}"


def test_global_words_any_field():
    """「官方数据显示」任何字段都拦；reviews 词表只查 reviews 字段。"""
    hits = scan_entry({"steam_id": "123", "summary_zh": "官方数据显示的经典之作"})
    assert any(h["field"] == "summary" for h in hits)
    # 「必装」出现在 description 不拦（该词只在 reviews 词表）
    hits2 = scan_entry({"steam_id": "123", "description_zh": "新手必装的入门指南"})
    assert hits2 == []
