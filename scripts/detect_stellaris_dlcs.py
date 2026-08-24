"""群星 DLC 依赖标注修复/重检脚本

背景：build_db 重建会丢 DLC 标注（2026-08-24 发现库中 0 条标注）。
本脚本从 MOD 描述（description_clean）重新检测 DLC 提及，按数据真实原则
全部标为「可选」（无明确 require 依据不标必需）。

用法: python scripts/detect_stellaris_dlcs.py
"""
from __future__ import annotations

import os
import sys
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import games.stellaris.config.game  # noqa: F401
from core.game_config import get_game
from core.mod_db import ModDB


def main():
    cfg = get_game("stellaris", BASE_DIR)
    db = ModDB(cfg)
    mods = db.list_mods(limit=5000)
    dlc_map = {d.app_id: d for d in cfg.load_dlcs()}

    hit_count = 0
    hit_by_dlc = {}
    for m in mods:
        sid = m.get("steam_id")
        if not sid:
            continue
        detected = cfg.detect_required_dlcs(m)
        # 数据真实原则：全部标可选（描述提及相关功能，非必需声明）
        db.conn.execute(
            "UPDATE mods SET optional_dlcs=? WHERE id=?",
            (json.dumps(detected, ensure_ascii=False), m["id"]))
        if detected:
            hit_count += 1
            for app_id in detected:
                hit_by_dlc[app_id] = hit_by_dlc.get(app_id, 0) + 1
    db.conn.commit()

    print(f"扫描 {len(mods)} 个 MOD，命中 DLC 提及 {hit_count} 个：")
    for app_id, n in sorted(hit_by_dlc.items(), key=lambda x: -x[1]):
        d = dlc_map.get(app_id)
        name = d.name_zh if d else app_id
        print(f"  {name:12s} × {n}")

    # 抽查 5 个
    print("\n抽查：")
    for m in db.list_mods(limit=100):
        opt = json.loads(m.get("optional_dlcs") or "[]")
        if opt:
            names = ", ".join(dlc_map.get(a).name_zh if dlc_map.get(a) else a for a in opt)
            print(f"  {m['title_en'][:35]} → {names}")
            hit_count -= 0  # noop
    db.close()
    return hit_count


if __name__ == "__main__":
    main()
