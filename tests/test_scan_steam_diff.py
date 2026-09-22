"""离线冒烟：mock Steam 返回，验证 scan_steam_diff 双维度分类与导出链路。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "scripts"))

import scan_steam_diff as sds
from core.steam_fetch import clean_bbcode


def test_classify_dual():
    row = {
        "desc_hash": sds.sha256("old desc"),
        "baseline_hash": sds.sha256("old desc"),
        "time_updated": 100,
        "subs": 10,
    }
    # Steam 内容变了 → content_changed + baseline_stale
    steam = {"description_clean": "new desc", "time_updated": 200, "subscriptions": 20}
    db_k, base_k = sds.classify(row, steam)
    assert db_k == "content_changed", db_k
    assert base_k == "baseline_stale", base_k

    # 库已写新、中文基线仍旧 → unchanged/meta + baseline_stale
    row2 = {
        "desc_hash": sds.sha256("new desc"),
        "baseline_hash": sds.sha256("old desc"),
        "time_updated": 200,
        "subs": 20,
    }
    db_k, base_k = sds.classify(row2, steam)
    assert db_k == "unchanged", db_k
    assert base_k == "baseline_stale", base_k

    # 库描述旧但基线=Steam → content_changed + baseline_ok（只需 --write）
    row3 = {
        "desc_hash": sds.sha256("old desc"),
        "baseline_hash": sds.sha256("new desc"),
        "time_updated": 100,
        "subs": 10,
    }
    db_k, base_k = sds.classify(row3, steam)
    assert db_k == "content_changed", db_k
    assert base_k == "baseline_ok", base_k

    # 无基线
    row4 = {
        "desc_hash": sds.sha256("new desc"),
        "baseline_hash": "",
        "time_updated": 200,
        "subs": 20,
    }
    db_k, base_k = sds.classify(row4, steam)
    assert db_k == "unchanged", db_k
    assert base_k == "no_baseline", base_k

    # clean_bbcode 回退
    steam_bb = {"description": "[b]hi[/b] there", "time_updated": 1, "subscriptions": 1}
    row5 = {
        "desc_hash": sds.sha256("old"),
        "baseline_hash": sds.sha256("old"),
        "time_updated": 0,
        "subs": 0,
    }
    db_k, base_k = sds.classify(row5, steam_bb)
    assert db_k == "content_changed"
    assert base_k == "baseline_stale"
    print("test_classify_dual OK")


def test_export_pack_shape():
    fields = ("title", "summary", "description", "gameplay", "reviews", "features")
    # 与 export_stale_tasks.attach_translations 同构
    item = {
        "steam_id": "1",
        "title_en": "T",
        "description_clean": "x" * 10,
        "tags": "",
        "subscriptions": 1,
        "stale_type": "baseline_stale",
        "time_updated": 1,
        "db_kind": "unchanged",
        "baseline_kind": "baseline_stale",
    }
    for f in fields:
        item[f + "_zh_current"] = ""
    payload = {
        "game": "stellaris",
        "source": "t",
        "stale_count_total": 1,
        "translations": [item],
    }
    assert set(payload.keys()) >= {"game", "source", "stale_count_total", "translations"}
    t0 = payload["translations"][0]
    assert "description_zh_current" in t0 and "features_zh_current" in t0
    print("test_export_pack_shape OK")


def test_main_with_mock():
    import argparse
    from unittest import mock

    # 准备临时库路径依赖已注册 stellaris；直接 mock fetch 与 snapshot
    snap = {
        "111": {
            "steam_id": "111",
            "title": "Changed Mod",
            "subs": 999,
            "time_updated": 1,
            "desc_hash": sds.sha256("old"),
            "baseline_hash": sds.sha256("old"),
            "desc_len": 3,
            "fetched_at": "2026-01-01",
            "stale": 0,
            "confirmed_at": "2026-01-01",
        },
        "222": {
            "steam_id": "222",
            "title": "Meta Only",
            "subs": 10,
            "time_updated": 1,
            "desc_hash": sds.sha256("same"),
            "baseline_hash": sds.sha256("same"),
            "desc_len": 4,
            "fetched_at": "2026-01-01",
            "stale": 0,
            "confirmed_at": "2026-01-01",
        },
    }
    steam_map = {
        "111": {
            "publishedfileid": "111",
            "description": "NEW TEXT",
            "description_clean": "NEW TEXT",
            "subscriptions": 1200,
            "favorited": 50,
            "views": 9,
            "time_updated": 2,
            "preview_url": "",
        },
        "222": {
            "publishedfileid": "222",
            "description": "same",
            "description_clean": "same",
            "subscriptions": 11,
            "favorited": 1,
            "views": 1,
            "time_updated": 1,
            "preview_url": "",
        },
    }

    class FakeDB:
        def __init__(self):
            self.conn = mock.MagicMock()
            self._mods = {
                "111": {"id": 1, "steam_id": "111", "title_en": "Changed Mod", "tags": "t",
                        "subscriptions": 999, "title": "改过的"},
                "222": {"id": 2, "steam_id": "222", "title_en": "Meta Only", "tags": "",
                        "subscriptions": 10, "title": "仅元数据"},
            }

        def get_mod_by_steam_id(self, sid):
            return self._mods.get(sid)

        def get_translations(self, mod_id):
            return {
                "title": "旧标题",
                "summary": "旧简介",
                "description": "旧详介",
                "gameplay": "旧玩法",
                "reviews": "旧评价",
                "features": '["旧"]',
            }

        def upsert_mod(self, data):
            return 1

        def close(self):
            pass

    fake = FakeDB()
    argv = [
        "scan_steam_diff.py",
        "--game", "stellaris",
        "--mark-stale",
        "--export-pack",
    ]
    pack_dir = BASE / "translations" / "stale_wave"
    pack_dir.mkdir(parents=True, exist_ok=True)
    before = set(pack_dir.glob("stale_task_scan_*.json"))

    with mock.patch.object(sds, "load_db_snapshot", return_value=snap), \
         mock.patch.object(sds, "fetch_details", return_value=steam_map), \
         mock.patch.object(sds, "get_game", return_value=object()), \
         mock.patch.object(sds, "ModDB", return_value=fake), \
         mock.patch.object(sys, "argv", argv):
        rc = sds.main()

    assert rc == 1, rc
    # mark-stale 被调用
    assert fake.conn.execute.called
    # export-pack 写出
    after = set(pack_dir.glob("stale_task_scan_*.json"))
    new_files = after - before
    assert len(new_files) == 1, new_files
    pack = json.loads(next(iter(new_files)).read_text(encoding="utf-8"))
    assert pack["game"] == "stellaris"
    assert pack["stale_count_total"] >= 1
    sids = {t["steam_id"] for t in pack["translations"]}
    assert "111" in sids
    # 222 仅元数据 → 不进重译包
    assert "222" not in sids
    hit = next(t for t in pack["translations"] if t["steam_id"] == "111")
    assert hit["description_clean"] == "NEW TEXT"
    assert hit["description_zh_current"] == "旧详介"
    assert hit["stale_type"] == "baseline_stale"
    # 清理本次产物
    for p in new_files:
        p.unlink()
    print("test_main_with_mock OK")


if __name__ == "__main__":
    test_classify_dual()
    test_export_pack_shape()
    test_main_with_mock()
    print("ALL_SMOKE_OK")
