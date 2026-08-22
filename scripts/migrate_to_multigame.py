"""迁移脚本：把旧版单游戏数据迁移到新版多游戏架构

从 data/stellaris_mods.db 迁移到 data/stellaris/mods.db（新架构 schema）
迁移内容：
- mods 主表（含 preview_url / status / compat_json 等）
- translations（title/summary/description/features/gameplay/reviews）
- compat 兼容性数据
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import games.stellaris.config.game  # noqa: F401  触发注册
from core.game_config import get_game
from core.mod_db import ModDB


def migrate():
    old_db = os.path.join(BASE_DIR, "data", "stellaris_mods.db")
    if not os.path.exists(old_db):
        print(f"旧库不存在: {old_db}")
        return 0

    cfg = get_game("stellaris", BASE_DIR)
    new_db = ModDB(cfg)

    # 确保 pinyin_idx 列存在（兼容旧 schema）
    cols = [r[1] for r in new_db.conn.execute("PRAGMA table_info(mods)").fetchall()]
    if "pinyin_idx" not in cols:
        new_db.conn.execute("ALTER TABLE mods ADD COLUMN pinyin_idx TEXT")
        new_db.conn.commit()

    conn_old = sqlite3.connect(old_db)
    conn_old.row_factory = sqlite3.Row

    # 1. 迁移 mods
    rows = conn_old.execute("SELECT * FROM mods").fetchall()
    count = 0
    for r in rows:
        # 解析 compat_json（旧格式）
        compat = {}
        if r["compat_json"]:
            try:
                compat = json.loads(r["compat_json"])
            except Exception:
                compat = {}
        mod_id = new_db.upsert_mod({
            "steam_id": r["steam_id"],
            "title": r["title"],
            "title_en": r["title_en"] or r["title"],
            "author": r["author"],
            "author_name": r["author_name"],
            "subscriptions": r["subscriptions"],
            "favorites": r["favorites"],
            "time_created": r["time_created"],
            "time_updated": r["time_updated"],
            "tags": r["tags"],
            "url": r["url"],
            "preview_url": r["preview_url"],
            "description": r["description"],
            "description_clean": r["description_clean"],
            "status": r["status"],
            "translated": r["translated"],
            "score": _score(r["subscriptions"], r["favorites"]),
            "like_ratio": round(r["favorites"] / r["subscriptions"] * 100, 1)
                          if r["subscriptions"] else 0,
        })
        # 兼容性
        if compat:
            new_db.set_compat(mod_id, {
                "conflicts": compat.get("conflicts", []),
                "requires": compat.get("requires", []),
                "best_with": compat.get("best_with", []),
                "notes": compat.get("notes", ""),
                "has_patches": compat.get("has_patches", []),
            })
        count += 1

    # 2. 迁移 translations
    trans = conn_old.execute("SELECT * FROM translations").fetchall()
    trans_count = 0
    for t in trans:
        mod = new_db.get_mod(t["mod_id"])
        if not mod:
            # mod_id 可能不连续，用 steam_id 反查
            continue
        new_db.set_translation(mod["id"], t["field"], t["zh_text"], t["quality"])
        trans_count += 1

    # 3. 拼音索引（标题中英文生成）
    from pypinyin import lazy_pinyin, Style

    for m in new_db.list_mods(limit=2000):
        title_zh = m.get("title") or ""
        title_en = m.get("title_en") or ""
        full = "".join(lazy_pinyin(title_zh)) + " " + "".join(lazy_pinyin(title_en))
        first = "".join(lazy_pinyin(title_zh, style=Style.FIRST_LETTER))
        idx = f"{full} {first}".lower()
        new_db.conn.execute("UPDATE mods SET pinyin_idx=? WHERE id=?", (idx, m["id"]))
    new_db.conn.commit()

    conn_old.close()
    new_db.close()
    print(f"迁移完成: {count} 个 MOD, {trans_count} 条翻译")
    return count


def _score(subs, fav):
    try:
        subs = int(subs or 0)
        fav = int(fav or 0)
        if subs <= 0:
            return 0.0
        ratio = fav / subs
        s = 4.0 + (min(ratio, 0.15) / 0.15) * 5.5
        if subs >= 100000:
            s += 0.5
        elif subs >= 50000:
            s += 0.3
        return round(min(s, 10.0), 1)
    except Exception:
        return 0.0


if __name__ == "__main__":
    migrate()
