"""云端应用 mods 全量行存档（与 export_cloud_sync.py 配对使用，多游戏通用）

用法（在云服务器 /opt/stellaris-mod-zh 下）:
    python3 scripts/apply_cloud_sync.py --game stellaris
    python3 scripts/apply_cloud_sync.py --game ck3
    （不带 --game 时默认 stellaris，保持旧用法兼容）

行为：
- 读 data/<game>/mods_full_sync.json（本地权威库导出的全量行，不含 id）
- 已存在（game_id+steam_id 命中）→ UPDATE 保留云端主键 id，
  不破坏 translations/compat/community/trend 表的 mod_id 外键
- 不存在 → INSERT 新行
- SQL 为字面量语句 + 参数绑定；列清单为字面量（与 ModDB.SCHEMA 一致）
"""
from __future__ import annotations

import argparse
import json
import sqlite3

# 与 core/mod_db.py SCHEMA 的 mods 表列一致（不含自增主键 id）
COLS = ("game_id", "steam_id", "title", "title_en", "author", "author_name",
        "version", "subscriptions", "favorites", "views", "time_created",
        "time_updated", "tags", "url", "preview_url", "description",
        "description_clean", "required_dlcs", "optional_dlcs",
        "localization_id", "score", "like_ratio", "community_score",
        "status", "pinyin_idx", "translated", "fetched_at")

_GAMES = ("stellaris", "ck3", "hoi4")


def main():
    ap = argparse.ArgumentParser(description="云端应用 mods 全量行存档")
    ap.add_argument("--game", default="stellaris", choices=_GAMES,
                    help="目标游戏（默认 stellaris）")
    args = ap.parse_args()
    game_id = args.game
    db_path = f"data/{game_id}/mods.db"
    archive_path = f"data/{game_id}/mods_full_sync.json"

    with open(archive_path, encoding="utf-8") as f:
        data = json.load(f)
    rows = data.get("rows", [])
    print(f"存档[{game_id}]: exported_at={data.get('exported_at')}, {len(rows)} 行")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA busy_timeout=8000")
    cur = conn.cursor()
    n_upd = n_ins = 0
    for r in rows:
        vals = [r.get(c) for c in COLS]
        ex = cur.execute(
            "SELECT id FROM mods WHERE game_id=? AND steam_id=?",
            (game_id, r.get("steam_id"))).fetchone()
        if ex:
            cur.execute(
                "UPDATE mods SET game_id=?, steam_id=?, title=?, title_en=?, "
                "author=?, author_name=?, version=?, subscriptions=?, "
                "favorites=?, views=?, time_created=?, time_updated=?, tags=?, "
                "url=?, preview_url=?, description=?, description_clean=?, "
                "required_dlcs=?, optional_dlcs=?, localization_id=?, score=?, "
                "like_ratio=?, community_score=?, status=?, pinyin_idx=?, "
                "translated=?, fetched_at=? WHERE id=?",
                (*vals, ex[0]))
            n_upd += 1
        else:
            cur.execute(
                "INSERT INTO mods (game_id, steam_id, title, title_en, author, "
                "author_name, version, subscriptions, favorites, views, "
                "time_created, time_updated, tags, url, preview_url, "
                "description, description_clean, required_dlcs, optional_dlcs, "
                "localization_id, score, like_ratio, community_score, status, "
                "pinyin_idx, translated, fetched_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                vals)
            n_ins += 1
    conn.commit()
    total = cur.execute(
        "SELECT COUNT(*) FROM mods WHERE game_id=?", (game_id,)).fetchone()[0]
    conn.close()
    print(f"应用完成[{game_id}]: 更新 {n_upd}, 插入 {n_ins}; 库中共 {total} 个 MOD")


if __name__ == "__main__":
    main()
