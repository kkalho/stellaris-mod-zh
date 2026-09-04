"""导出 mods 全量行存档（云端同步用，多游戏通用）

用法:
    python scripts/export_cloud_sync.py --game stellaris   # → data/stellaris/mods_full_sync.json(.gz)
    python scripts/export_cloud_sync.py --game ck3
    python scripts/export_cloud_sync.py --game all         # 逐个已配置游戏导出
    （不带 --game 时默认 stellaris，保持旧用法兼容）

用途：云端数据库不同步 git（交接文档 §8），本脚本把本地（权威）库的全部
MOD 行导出成 JSON 存档，git 推送后云端用 scripts/apply_cloud_sync.py 应用，
实现「云端 = 本地」的确定性收敛——取代历史上临时拼装的同步方式。

应用端配套：scripts/apply_cloud_sync.py（更新已有行/插入新行，保留云端主键，
不破坏 translations/compat/community/trend 的 mod_id 外键）。
"""
from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import games.stellaris.config.game  # noqa: F401
import games.ck3.config.game  # noqa: F401
import games.hoi4.config.game  # noqa: F401
from core.game_config import get_game, list_games
from core.mod_db import ModDB


def export_one(game_id: str) -> int:
    cfg = get_game(game_id, BASE_DIR)
    db = ModDB(cfg)
    rows = [dict(r) for r in db.conn.execute(
        "SELECT * FROM mods WHERE game_id=?", (game_id,)).fetchall()]
    db.close()
    if not rows:
        print(f"[{game_id}] 空库，跳过导出（不产出空存档）")
        return 0
    for r in rows:
        r.pop("id", None)  # 主键由云端自管，存档不携带
    payload = {
        "game": game_id,
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(rows),
        "rows": rows,
    }
    cfg.save_json("mods_full_sync.json", payload)

    # 同步产出 .gz 副本（r13 教训：gz 靠手工压缩会漏更新——旧 gz 混进 git，
    # 云端解压出 777 行旧存档。这里从刚导出的明文现压，保证两者永远一致）
    src = os.path.join(cfg.data_dir, "mods_full_sync.json")
    dst = src + ".gz"
    with open(src, "rb") as fin, gzip.open(dst, "wb", compresslevel=9) as fout:
        shutil.copyfileobj(fin, fout)
    print(f"[{game_id}] 导出 {len(rows)} 行 → data/{game_id}/mods_full_sync.json（.gz 副本已同步生成）"
          f"（不含 id，云端 apply 时更新/插入分流）")
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description="导出 mods 全量行存档（云端同步用）")
    ap.add_argument("--game", default="stellaris",
                    choices=list_games() + ["all"],
                    help="目标游戏（默认 stellaris；all=逐个已配置游戏）")
    args = ap.parse_args()
    targets = list_games() if args.game == "all" else [args.game]
    for g in targets:
        export_one(g)


if __name__ == "__main__":
    main()
