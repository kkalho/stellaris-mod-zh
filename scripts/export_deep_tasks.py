"""深度精做任务导出：把薄字段的 MOD 打包成子智能体任务文件

用法（配合 data/stellaris/deep_thin_targets.json）:
    python scripts/export_deep_tasks.py --start 1 --end 50 > translations/deep_wave/deep_task_001.json

每个任务条目自包含：steam_id / title_en / description_clean（Steam 原文）/ 现有六字段翻译。
子智能体只做重写写作（description_zh ≥300 字、gameplay_zh 300-600 字），其余字段原样保留。
产出为标准 batch 格式（可过 validate_translations 门禁 + import_stellaris_translations 导入）。
JSON 打印到 stdout，由调用方重定向落盘（文件写入不经本脚本）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import games.stellaris.config.game  # noqa: F401
from core.game_config import get_game
from core.mod_db import ModDB

FIELDS = ("title", "summary", "description", "gameplay", "reviews", "features")


def main():
    ap = argparse.ArgumentParser(description="导出深度精做任务文件（JSON → stdout）")
    ap.add_argument("--start", type=int, required=True, help="目标清单起始序号（含，1-based）")
    ap.add_argument("--end", type=int, required=True, help="目标清单结束序号（含）")
    args = ap.parse_args()

    targets_path = os.path.join(BASE_DIR, "data", "stellaris", "deep_thin_targets.json")
    targets = json.load(open(targets_path, encoding="utf-8"))
    batch = targets[args.start - 1: args.end]
    cfg = get_game("stellaris", BASE_DIR)
    db = ModDB(cfg)
    out = []
    for t in batch:
        m = db.get_mod_by_steam_id(str(t["steam_id"]))
        if not m:
            print(f"# 跳过（库中无此 MOD）: {t['steam_id']}", file=sys.stderr)
            continue
        trans = db.get_translations(m["id"])
        entry = {
            "steam_id": str(t["steam_id"]),
            "title_en": m.get("title_en") or m.get("title") or "",
            "description_clean": (m.get("description_clean") or "")[:6000],
            "tags": m.get("tags") or "",
            "subscriptions": m.get("subscriptions") or 0,
        }
        for f in FIELDS:
            entry[f + "_zh_current"] = trans.get(f, "")
        out.append(entry)
    db.close()

    payload = {
        "game": "stellaris",
        "source": f"深度精做任务包（目标清单 #{args.start}-{args.end}，共 {len(out)} 条）",
        "translations": out,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
