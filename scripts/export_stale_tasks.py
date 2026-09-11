"""增量重译任务导出：把翻译腐化（原文已变）的 MOD 打包成可重译任务文件

配合 detect_stale_translations.py 使用。输出格式与 export_deep_tasks.py 同构，
便于复用子智能体 prompt / validate_translations 门禁 / import_stellaris_translations。

用法:
    python scripts/export_stale_tasks.py
    python scripts/export_stale_tasks.py --start 1 --end 25 > translations/stale_wave/stale_task_001.json
    python scripts/export_stale_tasks.py --limit 50 --include-marked
    python scripts/export_stale_tasks.py --game ck3

默认只导出「内容维度」腐化：description_clean 的 SHA256 ≠ desc_hash_baseline。
子智能体按 deep 规则重写 description_zh / gameplay_zh，其余字段照抄 *_zh_current。
导入后请跑 scripts/confirm_stale_translations.py 归零基线。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import games.stellaris.config.game  # noqa: F401
import games.ck3.config.game  # noqa: F401
import games.hoi4.config.game  # noqa: F401
from core.game_config import get_game
from core.mod_db import ModDB

FIELDS = ("title", "summary", "description", "gameplay", "reviews", "features")


def sha256(text: str) -> str:
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def collect_stale(game_id: str, include_marked: bool, include_time_suspect: bool) -> list[dict]:
    cfg = get_game(game_id, BASE_DIR)
    db_path = cfg.db_path
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"数据库不存在: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(mods)").fetchall()]
        if "desc_hash_baseline" not in cols:
            raise RuntimeError("缺少基线字段，请先运行 scripts/migrate_translation_baseline.py")

        rows = conn.execute(
            """
            SELECT id, steam_id, title_en, title, time_updated, fetched_at,
                   description_clean, desc_hash_baseline, translation_confirmed_at,
                   translation_stale, subscriptions
            FROM mods
            WHERE game_id=? AND translated=1
              AND desc_hash_baseline IS NOT NULL AND desc_hash_baseline != ''
            ORDER BY subscriptions DESC
            """,
            (game_id,),
        ).fetchall()

        out = []
        for r in rows:
            baseline = r["desc_hash_baseline"] or ""
            current = r["description_clean"] or ""
            cur_hash = sha256(current)
            content_stale = cur_hash != baseline
            marked = int(r["translation_stale"] or 0) == 1
            time_suspect = False
            if not content_stale and r["time_updated"] and r["translation_confirmed_at"]:
                try:
                    conf = datetime.datetime.strptime(
                        str(r["translation_confirmed_at"]), "%Y-%m-%d"
                    ).timestamp()
                    time_suspect = int(r["time_updated"]) > conf
                except (ValueError, TypeError):
                    time_suspect = False

            reason = None
            if content_stale:
                reason = "content_changed"
            elif include_marked and marked:
                reason = "marked_stale"
            elif include_time_suspect and time_suspect:
                reason = "time_updated_newer"
            if not reason:
                continue

            out.append(
                {
                    "db_id": r["id"],
                    "steam_id": str(r["steam_id"] or ""),
                    "title_en": r["title_en"] or r["title"] or "",
                    "description_clean": current,
                    "time_updated": int(r["time_updated"] or 0),
                    "stale_type": reason,
                    "subscriptions": int(r["subscriptions"] or 0),
                }
            )
        return out
    finally:
        conn.close()


def attach_translations(game_id: str, stale: list[dict]) -> list[dict]:
    cfg = get_game(game_id, BASE_DIR)
    db = ModDB(cfg)
    out = []
    try:
        for e in stale:
            m = db.get_mod_by_steam_id(e["steam_id"])
            if not m:
                print(f"# 跳过（库中无此 MOD）: {e['steam_id']}", file=sys.stderr)
                continue
            trans = db.get_translations(m["id"])
            entry = {
                "steam_id": e["steam_id"],
                "title_en": e["title_en"],
                "description_clean": (e["description_clean"] or "")[:6000],
                "tags": m.get("tags") or "",
                "subscriptions": e["subscriptions"],
                "stale_type": e["stale_type"],
                "time_updated": e["time_updated"],
            }
            for f in FIELDS:
                entry[f + "_zh_current"] = trans.get(f, "")
            out.append(entry)
    finally:
        db.close()
    return out


def main():
    ap = argparse.ArgumentParser(description="导出翻译腐化增量重译任务包（JSON → stdout）")
    ap.add_argument("--game", default="stellaris")
    ap.add_argument("--start", type=int, help="名单起始序号（含，1-based）")
    ap.add_argument("--end", type=int, help="名单结束序号（含）")
    ap.add_argument("--limit", type=int, help="只导出前 N 条")
    ap.add_argument("--include-marked", action="store_true",
                    help="并入 translation_stale=1（即使 hash 未变）")
    ap.add_argument("--include-time-suspect", action="store_true",
                    help="并入 time_updated > confirmed_at 的疑似腐化")
    args = ap.parse_args()

    stale = collect_stale(args.game, args.include_marked, args.include_time_suspect)
    if not stale:
        print("# 当前无内容腐化（或未命中过滤条件）", file=sys.stderr)

    if args.limit is not None and args.limit > 0:
        batch = stale[: args.limit]
        label = f"1-{len(batch)}"
    elif args.start is not None or args.end is not None:
        start = max(1, args.start or 1)
        end = args.end or len(stale)
        batch = stale[start - 1: end]
        label = f"{start}-{end}"
    else:
        batch = stale
        label = f"1-{len(batch)}"

    translations = attach_translations(args.game, batch)
    payload = {
        "game": args.game,
        "source": f"增量重译任务包（腐化名单 #{label}，共 {len(translations)} 条）",
        "stale_count_total": len(stale),
        "translations": translations,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
