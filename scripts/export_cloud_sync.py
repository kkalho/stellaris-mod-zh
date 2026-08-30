"""导出 mods 全量行存档（云端同步用）

用法:
    python scripts/export_cloud_sync.py     # → data/stellaris/mods_full_sync.json

用途：云端数据库不同步 git（交接文档 §8），本脚本把本地（权威）库的全部
MOD 行导出成 JSON 存档，git 推送后云端用 scripts/apply_cloud_sync.py 应用，
实现「云端 = 本地」的确定性收敛——取代历史上临时拼装的同步方式。

应用端配套：scripts/apply_cloud_sync.py（更新已有行/插入新行，保留云端主键，
不破坏 translations/compat/community/trend 的 mod_id 外键）。
"""
from __future__ import annotations

import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import games.stellaris.config.game  # noqa: F401
from core.game_config import get_game
from core.mod_db import ModDB


def main():
    cfg = get_game("stellaris", BASE_DIR)
    db = ModDB(cfg)
    rows = [dict(r) for r in db.conn.execute(
        "SELECT * FROM mods WHERE game_id='stellaris'").fetchall()]
    db.close()
    for r in rows:
        r.pop("id", None)  # 主键由云端自管，存档不携带
    payload = {
        "game": "stellaris",
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(rows),
        "rows": rows,
    }
    cfg.save_json("mods_full_sync.json", payload)

    # 同步产出 .gz 副本（r13 教训：gz 靠手工压缩会漏更新——旧 gz 混进 git，
    # 云端解压出 777 行旧存档。这里从刚导出的明文现压，保证两者永远一致）
    import gzip
    import shutil
    src = os.path.join(cfg.data_dir, "mods_full_sync.json")
    dst = src + ".gz"
    with open(src, "rb") as fin, gzip.open(dst, "wb", compresslevel=9) as fout:
        shutil.copyfileobj(fin, fout)
    print(f"导出 {len(rows)} 行 → data/stellaris/mods_full_sync.json（.gz 副本已同步生成）"
          f"（不含 id，云端 apply 时更新/插入分流）")


if __name__ == "__main__":
    main()
