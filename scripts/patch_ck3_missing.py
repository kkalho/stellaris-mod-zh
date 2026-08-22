"""补录 CK3 榜单中有、但详情 API 未返回的 MOD（元数据完整，描述留空）

用法: python patch_ck3_missing.py
数据源: data/ck3/workshop_top.json（官方页面榜单，含标题/订阅数/预览图）
"""
import sys, io, json, os, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import games.ck3.config.game  # noqa: F401
from core.game_config import get_game
from core.mod_db import ModDB

DATA_DIR = os.path.join(BASE_DIR, "data", "ck3")


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


def main():
    cfg = get_game("ck3", BASE_DIR)
    db = ModDB(cfg)

    # 库中已有的 steam_id
    existing = {r[0] for r in db.conn.execute(
        "SELECT steam_id FROM mods WHERE game_id='ck3' AND steam_id IS NOT NULL").fetchall()}

    with open(os.path.join(DATA_DIR, "workshop_top.json"), encoding="utf-8") as f:
        top = json.load(f)

    added = 0
    for m in top["mods"]:
        fid = str(m.get("publishedfileid", ""))
        if not fid or fid in existing:
            continue
        url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={fid}"
        subs = m.get("subscriptions", 0)
        fav = m.get("favorited", 0)
        db.upsert_mod({
            "steam_id": fid,
            "title": m.get("title", ""),
            "title_en": m.get("title", ""),
            "author": m.get("creator", ""),
            "subscriptions": subs,
            "favorites": fav,
            "views": m.get("views", 0),
            "time_created": m.get("time_created", 0),
            "time_updated": m.get("time_updated", 0),
            "tags": ",".join(t.get("tag", "") for t in m.get("tags", [])),
            "url": url,
            "preview_url": m.get("preview_url", ""),
            "description_clean": "",
            "required_dlcs": [],
            "optional_dlcs": [],
            "status": "deprecated" if "DEPRECATED" in (m.get("title") or "").upper() else "",
            "score": _score(subs, fav),
            "like_ratio": round(fav / subs * 100, 1) if subs else 0,
            "translated": 0,
        })
        added += 1
        print(f"补录: {fid} {m.get('title', '')[:40]}")

    # 拼音索引
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

    print(f"补录完成：{added} 条，库中共 {db.count()} 个 CK3 Mod")
    db.close()


if __name__ == "__main__":
    main()
