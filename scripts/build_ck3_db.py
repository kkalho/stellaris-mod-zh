"""构建 CK3 知识库 SQLite（新多游戏架构，直接写 data/ck3/mods.db）

用法: python build_ck3_db.py
数据源:
  1. data/ck3/details.jsonl      - 官方 API 完整详情（描述等）
  2. data/ck3/workshop_top.json  - 官方页面榜单（订阅数/评分/预览图）

入库字段（对齐 ModDB.upsert_mod）:
  title/title_en/author/subscriptions/favorites/views/tags/url/preview_url
  description/description_clean/status/score/like_ratio/required_dlcs/optional_dlcs
"""
import sys, io, json, os, time, re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import games.ck3.config.game  # noqa: F401  触发注册
from core.game_config import get_game
from core.mod_db import ModDB

DATA_DIR = os.path.join(BASE_DIR, "data", "ck3")


def _score(subs, fav):
    """综合评分（与群星迁移脚本一致）：好感比例 + 订阅量加成"""
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


def _detect_status(title_en, desc_clean):
    """废弃/停更警告（与群星逻辑一致）"""
    t_low = (title_en or "").lower()
    if any(k in t_low for k in ("deprecated", "outdated", "do not use", "legacy",
                                 "on hold", "discontinued", "abandoned", "hiatus")):
        return "deprecated"
    d_low = (desc_clean or "").lower()
    if any(k in d_low for k in ("this mod is deprecated", "no longer updated",
                                "will no longer be updated", "abandoned")):
        return "deprecated"
    return ""


def main():
    details_path = os.path.join(DATA_DIR, "details.jsonl")
    top_path = os.path.join(DATA_DIR, "workshop_top.json")

    rows = []
    if os.path.exists(details_path):
        with open(details_path, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
    print(f"详情数据: {len(rows)} 条")

    top_mods = {}
    if os.path.exists(top_path):
        with open(top_path, encoding="utf-8") as f:
            for m in json.load(f).get("mods", []):
                top_mods[str(m.get("publishedfileid", ""))] = m
    print(f"榜单数据: {len(top_mods)} 条")

    cfg = get_game("ck3", BASE_DIR)
    db = ModDB(cfg)

    # 兼容旧 schema：确保 pinyin_idx 列存在（与 migrate_to_multigame.py 一致）
    cols = [r[1] for r in db.conn.execute("PRAGMA table_info(mods)").fetchall()]
    if "pinyin_idx" not in cols:
        db.conn.execute("ALTER TABLE mods ADD COLUMN pinyin_idx TEXT")
        db.conn.commit()
        print("已补加 pinyin_idx 列")

    inserted = 0
    updated = 0
    for r in rows:
        if r.get("result") != 1:
            continue
        steam_id = str(r.get("publishedfileid", ""))
        tags = ",".join(t.get("tag", "") for t in r.get("tags", []))
        url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={steam_id}"
        title_en = r.get("title", "")
        # 从榜单补充订阅数/预览图（榜单数据更新）
        top = top_mods.get(steam_id, {})
        subs = top.get("subscriptions") or r.get("subscriptions", 0)
        fav = top.get("favorited") or r.get("favorited", 0)
        views = top.get("views") or r.get("views", 0)
        preview = top.get("preview_url") or r.get("preview_url", "")

        desc_clean = r.get("description_clean", "")
        # DLC 依赖：CK3 描述中提及的 DLC 一律标可选（数据真实原则，无 require 依据）
        optional_dlcs = cfg.detect_required_dlcs({
            "description_clean": desc_clean, "description": r.get("description", "")})
        status = _detect_status(title_en, desc_clean)

        mod_id = db.upsert_mod({
            "steam_id": steam_id,
            "title": title_en,
            "title_en": title_en,
            "author": r.get("creator", ""),
            "subscriptions": subs,
            "favorites": fav,
            "views": views,
            "time_created": r.get("time_created", 0),
            "time_updated": r.get("time_updated", 0),
            "tags": tags,
            "url": url,
            "preview_url": preview,
            "description": r.get("description", ""),
            "description_clean": desc_clean,
            "required_dlcs": [],
            "optional_dlcs": optional_dlcs,
            "status": status,
            "score": _score(subs, fav),
            "like_ratio": round(fav / subs * 100, 1) if subs else 0,
            "translated": 0,
        })
        # 记录旧库中已翻译的（若重复跑建库保留翻译状态）
        inserted += 1

    # 拼音索引（标题中英文）
    try:
        from pypinyin import lazy_pinyin, Style
        for m in db.list_mods(limit=5000):
            title_zh = m.get("title") or ""
            title_en = m.get("title_en") or ""
            full = "".join(lazy_pinyin(title_zh)) + " " + "".join(lazy_pinyin(title_en))
            first = "".join(lazy_pinyin(title_zh, style=Style.FIRST_LETTER))
            idx = f"{full} {first}".lower()
            db.conn.execute("UPDATE mods SET pinyin_idx=? WHERE id=?", (idx, m["id"]))
        db.conn.commit()
    except ImportError:
        print("警告: pypinyin 未安装，跳过拼音索引")

    total = db.count()
    trans = db.conn.execute(
        "SELECT COUNT(*) FROM mods WHERE game_id='ck3' AND translated=1").fetchone()[0]
    print(f"导入完成：{inserted} 条，库中共 {total} 个 CK3 Mod，已翻译标记 {trans}")
    db.close()


if __name__ == "__main__":
    main()
