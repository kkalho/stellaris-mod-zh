"""导出 translations 全量存档（云端同步用）

与 export_cloud_sync.py（mods 表）配对：云端补齐除了 mods 元数据，
六字段中文翻译也要同步，否则新 MOD 详情页无中文（交接文档 §8 教训 #5）。

用法:
    python scripts/export_translations.py   # → data/stellaris/translations_full_sync.json (+ .gz)

输出格式与 import_stellaris_translations.py 的输入一致：
  {"game": "stellaris", "translations": [{"steam_id", "title_zh", "summary_zh",
   "description_zh", "gameplay_zh", "reviews_zh", "features_zh"}, ...]}
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
import sys
import time
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import games.stellaris.config.game  # noqa: F401
from core.game_config import get_game

FIELD_MAP = {
    "title": "title_zh",
    "summary": "summary_zh",
    "description": "description_zh",
    "gameplay": "gameplay_zh",
    "reviews": "reviews_zh",
    "features": "features_zh",
}


def main():
    cfg = get_game("stellaris", BASE_DIR)
    import sqlite3
    conn = sqlite3.connect(cfg.db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT m.steam_id, t.field, t.zh_text FROM translations t "
        "JOIN mods m ON m.id=t.mod_id WHERE m.game_id='stellaris'").fetchall()
    conn.close()

    by_sid = {}
    for r in rows:
        key = FIELD_MAP.get(r["field"])
        if not key:
            continue
        by_sid.setdefault(str(r["steam_id"]), {})[key] = r["zh_text"]

    translations = []
    for sid, fields in by_sid.items():
        if "features_zh" in fields and isinstance(fields["features_zh"], str):
            try:
                fields["features_zh"] = json.loads(fields["features_zh"])
            except Exception:
                pass  # 非法 JSON 则保留原字符串
        translations.append({"steam_id": sid, **fields})

    payload = {
        "game": "stellaris",
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(translations),
        "translations": translations,
    }
    src = os.path.join(cfg.data_dir, "translations_full_sync.json")
    Path(src).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # 同步生成 .gz 副本（从刚导出的明文现压，保证一致）
    with open(src, "rb") as fin, gzip.open(src + ".gz", "wb", compresslevel=9) as fout:
        shutil.copyfileobj(fin, fout)
    print(f"导出 {len(translations)} 条翻译 → {src}（.gz 副本已同步生成）")


if __name__ == "__main__":
    main()
