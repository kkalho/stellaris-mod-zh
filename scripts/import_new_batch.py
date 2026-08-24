"""群星扩容：增量导入新批次 MOD 到数据库（不动已有数据）

- 从 data/details.jsonl 读取详情，按榜单 rank 范围筛选新 MOD
- 用 ModDB.upsert_mod 增量写入（已有 steam_id 跳过，新增的插入）
- 生成 pinyin_idx（拼音搜索）
- 更新 progress.json 翻译进度

用法: python scripts/import_new_batch.py [起始rank] [结束rank]
示例: python scripts/import_new_batch.py 278 327
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import games.stellaris.config.game  # noqa: F401
import games.ck3.config.game  # noqa: F401
import games.hoi4.config.game  # noqa: F401
from core.game_config import get_game
from core.mod_db import ModDB

DATA_DIR = os.path.join(BASE_DIR, "data")


def clean_bbcode(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\[/?[a-zA-Z0-9=#\"' ]*\]", "", text)
    return text.strip()


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


def import_range(game_id: str, start: int, end: int, verbose: bool = True) -> dict:
    cfg = get_game(game_id, BASE_DIR)
    db = ModDB(cfg)

    # 榜单（按枚举顺序 = rank）
    with open(os.path.join(DATA_DIR, "workshop_top1000.json"), encoding="utf-8") as f:
        top = json.load(f)["mods"]

    # 详情
    details = {}
    with open(os.path.join(DATA_DIR, "details.jsonl"), encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("result") == 1:
                details[str(d["publishedfileid"])] = d

    # 已存在的 steam_id
    existing = {r[0] for r in db.conn.execute(
        "SELECT steam_id FROM mods WHERE game_id=? AND steam_id IS NOT NULL",
        (game_id,)).fetchall()}

    added = skipped = 0
    new_ids = []
    for i, m in enumerate(top, start=1):
        if i < start or i > end:
            continue
        fid = str(m.get("publishedfileid", ""))
        if not fid or fid in existing:
            skipped += 1
            continue
        d = details.get(fid)
        if not d:
            if verbose:
                print(f"  ⚠ 无详情: #{i} {m.get('title','')[:30]}")
            continue
        subs = d.get("subscriptions", m.get("subscriptions", 0))
        fav = d.get("favorited", m.get("favorites", 0))
        db.upsert_mod({
            "steam_id": fid,
            "title": d.get("title", ""),
            "title_en": d.get("title", ""),
            "author": d.get("creator", ""),
            "subscriptions": subs,
            "favorites": fav,
            "views": d.get("views", 0),
            "time_created": d.get("time_created", 0),
            "time_updated": d.get("time_updated", 0),
            "tags": ",".join(t.get("tag", "") for t in d.get("tags", [])),
            "url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={fid}",
            "preview_url": d.get("preview_url", ""),
            "description_clean": clean_bbcode(d.get("description", "")),
            "required_dlcs": [],
            "optional_dlcs": [],
            "status": "deprecated" if "DEPRECATED" in (d.get("title") or "").upper() else "",
            "score": _score(subs, fav),
            "like_ratio": round(fav / subs * 100, 1) if subs else 0,
            "translated": 0,
        })
        new_ids.append(fid)
        added += 1
        if verbose:
            print(f"  + #{i} {d.get('title','')[:40]} ({subs:,} 订阅)")

    # 拼音索引（全库重建，保证一致性）
    try:
        from pypinyin import lazy_pinyin, Style
        for mod in db.list_mods(limit=5000):
            idx = ("".join(lazy_pinyin(mod.get("title") or "")) + " "
                   + "".join(lazy_pinyin(mod.get("title_en") or ""))
                   + " " + "".join(lazy_pinyin(mod.get("title") or "", style=Style.FIRST_LETTER))).lower()
            db.conn.execute("UPDATE mods SET pinyin_idx=? WHERE id=?", (idx, mod["id"]))
        db.conn.commit()
    except ImportError:
        pass

    total = db.count()
    print(f"\n新增 {added} 个（跳过已存在 {skipped} 个），库中共 {total} 个 MOD")
    db.close()
    return {"added": added, "skipped": skipped, "total": total, "new_ids": new_ids}


if __name__ == "__main__":
    s = int(sys.argv[1]) if len(sys.argv) > 1 else 278
    e = int(sys.argv[2]) if len(sys.argv) > 2 else s + 49
    import_range("stellaris", s, e)
