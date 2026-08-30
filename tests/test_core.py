"""核心逻辑最小测试集

覆盖三个曾出过事故/即将演化出事故的路径：
1. upsert_mod 部分更新（坑 #1 根因修复的回归保护）
2. calc_score 评分启发式（双实现合并后的行为锁定）
3. 版本筛选（精确匹配不过吸收 3.1x，通配 3.x 不误中 4.x）

运行: python -m pytest tests -q
"""
from __future__ import annotations

import json
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import games.stellaris.config.game  # noqa: F401,E402
import games.ck3.config.game  # noqa: F401,E402
import games.hoi4.config.game  # noqa: F401,E402
from core.mod_db import ModDB, calc_score  # noqa: E402
import web_server_multigame as ws  # noqa: E402

GAME = "test"


class TempCfg:
    game_id = GAME
    db_path = ""
    data_dir = ""


@pytest.fixture()
def db(tmp_path):
    cfg = TempCfg()
    cfg.db_path = str(tmp_path / "test.db")
    cfg.data_dir = str(tmp_path)
    d = ModDB(cfg)
    yield d
    d.close()


# ---------------------------------------------------------------------------
# calc_score
# ---------------------------------------------------------------------------

def test_calc_score_bounds():
    assert calc_score(100000, 15000) == 10.0   # 收藏率 15% 封顶 + 10 万订阅加成
    assert calc_score(0, 100) == 0.0
    assert calc_score(None, None) == 0.0
    v = calc_score(10000, 1000)                # 收藏率 10%
    assert 0.0 <= v <= 10.0


# ---------------------------------------------------------------------------
# upsert_mod 部分更新（坑 #1 回归保护）
# ---------------------------------------------------------------------------

def test_upsert_partial_update_preserves_annotations(db):
    mid = db.upsert_mod({
        "steam_id": "999", "title": "TestMod", "title_en": "TestMod",
        "version": "适配 4.4", "optional_dlcs": ["281992"],
        "status": "", "translated": 1, "subscriptions": 100,
    })
    # 模拟并行会话/迁移脚本只回灌元数据的场景
    db.upsert_mod({"steam_id": "999", "subscriptions": 200})
    m = db.get_mod(mid)
    assert m["version"] == "适配 4.4"
    assert json.loads(m["optional_dlcs"]) == ["281992"]
    assert m["translated"] == 1
    assert m["subscriptions"] == 200


def test_upsert_explicit_fields_still_override(db):
    db.upsert_mod({"steam_id": "999", "title": "T", "version": "适配 4.4"})
    db.upsert_mod({"steam_id": "999", "version": "更新于 3.4 时期"})
    assert db.get_mod_by_steam_id("999")["version"] == "更新于 3.4 时期"


def test_upsert_insert_sets_fields(db):
    mid = db.upsert_mod({"steam_id": "888", "title": "New", "version": "适配 4.4"})
    assert db.get_mod(mid)["version"] == "适配 4.4"


# ---------------------------------------------------------------------------
# 版本筛选（精确匹配回归：3.1 不得误中 3.10~3.14）
# ---------------------------------------------------------------------------

@pytest.fixture()
def version_db(tmp_path):
    # get_versions / search 的 SQL 按 game_id 过滤，这里用已注册的 "stellaris"
    cfg = TempCfg()
    cfg.game_id = "stellaris"
    cfg.db_path = str(tmp_path / "version.db")
    cfg.data_dir = str(tmp_path)
    d = ModDB(cfg)
    d.upsert_mod({"steam_id": "1", "title": "A", "version": "适配 3.1", "subscriptions": 30})
    d.upsert_mod({"steam_id": "2", "title": "B", "version": "更新于 3.10 时期", "subscriptions": 20})
    d.upsert_mod({"steam_id": "3", "title": "C", "version": "适配 4.4", "subscriptions": 10})
    yield d
    d.close()


def test_search_exact_version_no_overmatch(version_db):
    rows = ws.search("stellaris", "", version="3.1", db=version_db)
    versions = {r["version"] for r in rows}
    assert versions == {"适配 3.1"}


def test_search_wildcard_3x_excludes_4x(version_db):
    rows = ws.search("stellaris", "", version="3.x", db=version_db)
    versions = {r["version"] for r in rows}
    assert versions == {"适配 3.1", "更新于 3.10 时期"}


def test_search_exact_44(version_db):
    rows = ws.search("stellaris", "", version="4.4", db=version_db)
    assert {r["version"] for r in rows} == {"适配 4.4"}


def test_search_keyword(version_db):
    # search 按空格分词后 AND 匹配；单词条精确对应标题
    rows = ws.search("stellaris", "B", db=version_db)
    assert [r["title_en"] for r in rows] == ["B"]


# ---------------------------------------------------------------------------
# get_versions（版本下拉数据源）
# ---------------------------------------------------------------------------

def test_get_versions_sorted_with_names(version_db):
    # get_versions 需要已注册游戏配置（取 VERSION_NAMES 代号表）
    out = ws.get_versions("stellaris", db=version_db)
    vs = [v["v"] for v in out["versions"]]
    assert vs == ["4.4", "3.10", "3.1"]          # 数值降序，不是字典序
    labels = {v["v"]: v["label"] for v in out["versions"]}
    assert labels["4.4"] == "4.4 飞马"            # 代号来自 VERSION_NAMES
    assert labels["3.10"] == "3.10"               # 未配置代号的只显示版本号
