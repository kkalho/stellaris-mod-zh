"""翻译自动扩充：发现工坊榜单上的未译 / 薄字段 / 新进榜缺口并导出任务包

与增量重译（export_stale_tasks）互补：
  - stale  = 作者更新后旧译过期
  - expand = 新收录、未译完、或日后再次变薄的字段

发现来源:
  1. data/workshop_top1000.json 榜单 rank vs 库内 steam_id → 新进榜未入库
  2. 库内 translated != 1 → 未译
  3. 已译但 description < --min-desc 或 gameplay < --min-gameplay → 薄字段

用法:
    python scripts/export_expand_tasks.py --report
    python scripts/export_expand_tasks.py --export --start 1 --end 50 \
        > translations/expand_wave/expand_task_001.json
    python scripts/export_expand_tasks.py --export --only thin --limit 25
    python scripts/export_expand_tasks.py --game ck3 --report

退出码: 0=成功；1=库/参数错误
--report 时：有缺口 exit 0 但 stderr 提示数量（便于 cron 日志）；--strict 则有缺口 exit 2
"""
from __future__ import annotations

import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import games.stellaris.config.game  # noqa: F401
import games.ck3.config.game  # noqa: F401
import games.hoi4.config.game  # noqa: F401
from core.game_config import get_game
from core.mod_db import ModDB

FIELDS = ("title", "summary", "description", "gameplay", "reviews", "features")
TOP_PATH = os.path.join(BASE_DIR, "data", "workshop_top1000.json")


def load_workshop_top() -> list[dict]:
    if not os.path.exists(TOP_PATH):
        return []
    with open(TOP_PATH, encoding="utf-8") as f:
        data = json.load(f)
    mods = data.get("mods") or []
    out = []
    for i, m in enumerate(mods, start=1):
        sid = str(m.get("publishedfileid") or m.get("steam_id") or "").strip()
        if not sid:
            continue
        out.append({"rank": i, "steam_id": sid, "title": m.get("title") or ""})
    return out


def scan_gaps(game_id: str, min_desc: int, min_gameplay: int) -> dict:
    cfg = get_game(game_id, BASE_DIR)
    if not os.path.exists(cfg.db_path):
        raise FileNotFoundError(f"数据库不存在: {cfg.db_path}")

    top = load_workshop_top() if game_id == "stellaris" else []
    db = ModDB(cfg)
    try:
        rows = db.conn.execute(
            """
            SELECT m.id, m.steam_id, m.title_en, m.title, m.tags, m.subscriptions,
                   m.translated,
                   (SELECT t.zh_text FROM translations t
                    WHERE t.mod_id=m.id AND t.field='description') AS desc_zh,
                   (SELECT t.zh_text FROM translations t
                    WHERE t.mod_id=m.id AND t.field='gameplay') AS play_zh
            FROM mods m
            WHERE m.game_id=?
            """,
            (game_id,),
        ).fetchall()
        by_sid = {str(r["steam_id"]): r for r in rows if r["steam_id"]}
    finally:
        db.close()

    new_in_workshop = []
    for t in top:
        if t["steam_id"] not in by_sid:
            new_in_workshop.append(t)

    untranslated = []
    thin = []
    for sid, r in by_sid.items():
        translated = int(r["translated"] or 0)
        desc = r["desc_zh"] or ""
        play = r["play_zh"] or ""
        base = {
            "db_id": r["id"],
            "steam_id": sid,
            "title_en": r["title_en"] or r["title"] or "",
            "subscriptions": int(r["subscriptions"] or 0),
            "rank": next((t["rank"] for t in top if t["steam_id"] == sid), None),
        }
        if translated != 1 or not desc or not play:
            untranslated.append({**base, "reason": "untranslated",
                                 "desc_len": len(desc), "gameplay_len": len(play)})
            continue
        if len(desc) < min_desc or len(play) < min_gameplay:
            thin.append({**base, "reason": "thin",
                         "desc_len": len(desc), "gameplay_len": len(play)})

    # 排序：榜单 rank 优先，其次订阅量
    def sk(e):
        return (e.get("rank") or 99999, -e.get("subscriptions", 0))

    new_in_workshop.sort(key=sk)
    untranslated.sort(key=sk)
    thin.sort(key=sk)
    return {
        "game": game_id,
        "new_in_workshop": new_in_workshop,
        "untranslated": untranslated,
        "thin": thin,
        "counts": {
            "new_in_workshop": len(new_in_workshop),
            "untranslated": len(untranslated),
            "thin": len(thin),
        },
    }


def export_batch(game_id: str, gaps: dict, only: str, start: int, end: int) -> list[dict]:
    if only == "new":
        pool = gaps["new_in_workshop"]
    elif only == "untranslated":
        pool = gaps["untranslated"]
    elif only == "thin":
        pool = gaps["thin"]
    else:
        # 默认：未译 + 薄字段（新进榜需先 fetch/import 才有原文，不进翻译包）
        pool = gaps["untranslated"] + gaps["thin"]

    pool = sorted(pool, key=lambda e: (e.get("rank") or 99999, -e.get("subscriptions", 0)))
    batch = pool[start - 1: end] if end else pool[start - 1:]
    sids = [e["steam_id"] for e in batch]

    db = ModDB(get_game(game_id, BASE_DIR))
    translations = []
    try:
        for e in batch:
            m = db.get_mod_by_steam_id(e["steam_id"])
            if not m:
                print(f"# 跳过（库中无此 MOD，需先 fetch/import）: {e['steam_id']}", file=sys.stderr)
                continue
            trans = db.get_translations(m["id"])
            entry = {
                "steam_id": e["steam_id"],
                "title_en": e.get("title_en") or m.get("title_en") or "",
                "description_clean": (m.get("description_clean") or "")[:6000],
                "tags": m.get("tags") or "",
                "subscriptions": e.get("subscriptions") or 0,
                "expand_reason": e.get("reason") or "new_in_workshop",
            }
            if e.get("rank"):
                entry["workshop_rank"] = e["rank"]
            for f in FIELDS:
                entry[f + "_zh_current"] = trans.get(f, "")
            translations.append(entry)
    finally:
        db.close()
    return translations


def write_targets_file(game_id: str, gaps: dict) -> str:
    path = os.path.join(BASE_DIR, "data", game_id, "expand_targets.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    merged = []
    n = 0
    for e in gaps["untranslated"] + gaps["thin"] + gaps["new_in_workshop"]:
        n += 1
        merged.append({
            "rank_by_expand": n,
            "steam_id": e["steam_id"],
            "title_en": e.get("title_en") or e.get("title") or "",
            "reason": e.get("reason") or "new_in_workshop",
            "rank": e.get("rank"),
            "subs": e.get("subscriptions") or 0,
        })
    payload = {
        "game": game_id,
        "updated_at": __import__("time").strftime("%Y-%m-%d %H:%M"),
        "counts": gaps["counts"],
        "targets": merged,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    return path


def main():
    ap = argparse.ArgumentParser(description="翻译自动扩充：发现缺口并导出任务包")
    ap.add_argument("--game", default="stellaris")
    ap.add_argument("--report", action="store_true", help="只打印缺口统计")
    ap.add_argument("--export", action="store_true", help="导出任务包 JSON → stdout")
    ap.add_argument("--write-targets", action="store_true", help="写 data/<game>/expand_targets.json")
    ap.add_argument("--only", choices=["all", "untranslated", "thin", "new"], default="all")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=0, help="0=到末尾")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--min-desc", type=int, default=150)
    ap.add_argument("--min-gameplay", type=int, default=100)
    ap.add_argument("--strict", action="store_true", help="有缺口时 exit 2")
    args = ap.parse_args()

    if not args.report and not args.export and not args.write_targets:
        args.report = True

    try:
        gaps = scan_gaps(args.game, args.min_desc, args.min_gameplay)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    c = gaps["counts"]
    if args.report or args.write_targets:
        print(
            f"[{args.game}] 新进榜未入库={c['new_in_workshop']} "
            f"未译={c['untranslated']} 薄字段={c['thin']} "
            f"（阈值 desc<{args.min_desc} / gameplay<{args.min_gameplay}）",
            file=sys.stderr,
        )
        for label, key in (("新进榜", "new_in_workshop"), ("未译", "untranslated"), ("薄字段", "thin")):
            for e in gaps[key][:8]:
                print(
                    f"  {label} rank={e.get('rank')} {e['steam_id']} "
                    f"{(e.get('title_en') or '')[:40]}",
                    file=sys.stderr,
                )
        if c["new_in_workshop"] or c["untranslated"] or c["thin"]:
            if args.strict:
                sys.exit(2)

    if args.write_targets:
        path = write_targets_file(args.game, gaps)
        print(f"targets → {path}", file=sys.stderr)

    if args.export:
        start = max(1, args.start)
        if args.limit and args.limit > 0:
            end = start + args.limit - 1
        else:
            end = args.end if args.end and args.end > 0 else 10**9
        translations = export_batch(args.game, gaps, args.only, start, end)
        label = f"{start}-{end if end < 10**9 else len(translations)}"
        payload = {
            "game": args.game,
            "source": f"翻译扩充任务包（only={args.only} #{label}，共 {len(translations)} 条）",
            "expand_counts": c,
            "translations": translations,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
