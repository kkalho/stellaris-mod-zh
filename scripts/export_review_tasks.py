"""导出「补作者自述」的提炼任务数据（P1）

从数据库查 reviews 无自述（仅「订阅 X、收藏 Y」）的 MOD，配对源存档里的
中文 description，按每批 BATCH 条分成多个 JSON 文件，供子智能体提炼自述。

用法:
    python scripts/export_review_tasks.py [--batch 50]

输出: data/stellaris/review_tasks/batch_NN.json
  [{"steam_id", "title", "description"}, ...]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import games.stellaris.config.game  # noqa: F401
from core.game_config import get_game

# reviews 仅「订阅 X、收藏 Y。」（无自述）的判定：以「订阅」开头、单句号结尾、且短
_NO_NARR = re.compile(r"^订阅[^。]*、收藏[^。]*。$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=50)
    args = ap.parse_args()

    cfg = get_game("stellaris", BASE_DIR)
    conn = sqlite3.connect(cfg.db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT m.steam_id, m.title, t.zh_text AS reviews FROM translations t "
        "JOIN mods m ON m.id=t.mod_id WHERE m.game_id='stellaris' AND t.field='reviews'"
    ).fetchall()
    conn.close()

    # 无自述的 MOD
    no_narr = [str(r["steam_id"]) for r in rows
               if r["reviews"] and _NO_NARR.match((r["reviews"] or "").strip())]

    # 源存档里的中文 description
    desc_map = {}
    title_map = {}
    for fp in glob.glob(os.path.join(BASE_DIR, "translations", "**", "*.json"),
                        recursive=True):
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        trs = d.get("translations", []) if isinstance(d, dict) else d
        for t in trs:
            if not isinstance(t, dict):
                continue
            sid = str(t.get("steam_id"))
            desc = t.get("description_zh") or t.get("description") or ""
            if sid not in desc_map and desc:
                desc_map[sid] = desc
            if t.get("title_zh") and sid not in title_map:
                title_map[sid] = t["title_zh"]

    tasks = []
    for sid in no_narr:
        if sid in desc_map:
            tasks.append({"steam_id": sid,
                          "title": title_map.get(sid, ""),
                          "description": desc_map[sid]})

    outdir = os.path.join(cfg.data_dir, "review_tasks")
    os.makedirs(outdir, exist_ok=True)
    # 清空旧批次
    for old in glob.glob(os.path.join(outdir, "batch_*.json")):
        os.remove(old)

    n_batch = (len(tasks) + args.batch - 1) // args.batch
    for i in range(n_batch):
        chunk = tasks[i * args.batch:(i + 1) * args.batch]
        p = os.path.join(outdir, f"batch_{i + 1:02d}.json")
        Path(p).write_text(json.dumps(chunk, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  batch_{i + 1:02d}.json: {len(chunk)} 条")

    print(f"\n共 {len(tasks)} 个 MOD 待提炼，分成 {n_batch} 批（每批 {args.batch} 条）")


if __name__ == "__main__":
    main()
