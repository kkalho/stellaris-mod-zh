"""全库 Steam 差分扫描：快速找出「Steam 上已变、库里还是旧的」MOD。

与 core.cli update 的区别：
- update 只重抓 fetched_at 超过 N 天的，且只写订阅/描述，不告诉你谁变了
- 本工具一次遍历全库 steam_id，批量打 Steam API，逐条比对 time_updated / 描述 hash，
  输出「内容变了 / 仅元数据变了 / Steam 上已消失」清单

比对维度：
1. content_changed  Steam 描述 hash ≠ 库内 description_clean（库里旧了）
2. baseline_stale   Steam 描述 hash ≠ desc_hash_baseline（即使库里已写新，中文仍过期）
3. meta_changed     仅订阅/time_updated 变化
4. missing          Steam 上查不到（下架/不可见）

用法:
    python scripts/scan_steam_diff.py                  # 扫描全库，打印报告
    python scripts/scan_steam_diff.py --json           # JSON 报告（自动化）
    python scripts/scan_steam_diff.py --write          # 把 Steam 新数据写回 mods 表
    python scripts/scan_steam_diff.py --mark-stale     # 对 baseline_stale 写 translation_stale=1
    python scripts/scan_steam_diff.py --export-pack    # 导出重译任务包到 translations/stale_wave/
    python scripts/scan_steam_diff.py --limit 200      # 只扫前 200 个（试跑）
    python scripts/scan_steam_diff.py --sleep 1.5      # 批次间隔（默认 2s）
    python scripts/scan_steam_diff.py --export-details # 同时把原始详情追加到 details.jsonl

退出码: 0=无需处理；1=发现内容/基线腐化；2=扫描失败
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "core"))

import games.stellaris.config.game  # noqa: F401
import games.ck3.config.game  # noqa: F401
import games.hoi4.config.game  # noqa: F401
from core.game_config import get_game
from core.mod_db import ModDB
from core.steam_fetch import fetch_details, clean_bbcode


def sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def load_db_snapshot(db, game_id: str, limit: int = 0) -> dict:
    rows = db.conn.execute(
        "SELECT steam_id, title, title_en, subscriptions, time_updated, "
        "description_clean, desc_hash_baseline, fetched_at, translation_stale, "
        "translation_confirmed_at "
        "FROM mods WHERE game_id=? ORDER BY subscriptions DESC",
        (game_id,),
    ).fetchall()
    snap = {}
    for r in rows:
        sid = str(r["steam_id"])
        snap[sid] = {
            "steam_id": sid,
            "title": r["title"] or r["title_en"] or "",
            "subs": r["subscriptions"] or 0,
            "time_updated": int(r["time_updated"] or 0),
            "desc_hash": sha256(r["description_clean"] or ""),
            "baseline_hash": r["desc_hash_baseline"] or "",
            "desc_len": len(r["description_clean"] or ""),
            "fetched_at": r["fetched_at"] or "",
            "stale": r["translation_stale"] or 0,
            "confirmed_at": r["translation_confirmed_at"] or "",
        }
        if limit and len(snap) >= limit:
            break
    return snap


def classify(snap_row: dict, steam: dict) -> tuple[str, str]:
    """返回 (db_kind, baseline_kind)。

    db_kind:      content_changed / meta_changed / unchanged
                  — Steam 描述 vs 库内 description_clean
    baseline_kind: baseline_stale / baseline_ok / no_baseline
                  — Steam 描述 vs desc_hash_baseline（翻译是否过期）
    """
    steam_desc = steam.get("description_clean") or clean_bbcode(steam.get("description") or "")
    new_hash = sha256(steam_desc)
    if new_hash != snap_row["desc_hash"]:
        db_kind = "content_changed"
    else:
        new_tu = int(steam.get("time_updated") or 0)
        new_subs = int(steam.get("subscriptions") or 0)
        db_kind = "meta_changed" if (new_tu != snap_row["time_updated"]
                                     or new_subs != snap_row["subs"]) else "unchanged"
    base = snap_row["baseline_hash"]
    if not base:
        baseline_kind = "no_baseline"
    elif new_hash != base:
        baseline_kind = "baseline_stale"
    else:
        baseline_kind = "baseline_ok"
    return db_kind, baseline_kind


def main() -> int:
    ap = argparse.ArgumentParser(description="全库 Steam 差分扫描")
    ap.add_argument("--game", default="stellaris")
    ap.add_argument("--limit", type=int, default=0, help="只扫订阅最高的前 N 个（0=全库）")
    ap.add_argument("--batch", type=int, default=50, help="Steam API 每批数量")
    ap.add_argument("--sleep", type=float, default=2.0, help="批次间隔秒（越小越快，越容易限流）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--write", action="store_true", help="把 Steam 新数据写回 mods 表")
    ap.add_argument("--mark-stale", action="store_true",
                    help="对 baseline_stale 写 translation_stale=1")
    ap.add_argument("--export-pack", action="store_true",
                    help="导出重译任务包到 translations/stale_wave/")
    ap.add_argument("--export-details", action="store_true",
                    help="把原始详情追加到 data/details.jsonl")
    ap.add_argument("--top", type=int, default=30, help="文本报告最多显示多少条")
    args = ap.parse_args()

    cfg = get_game(args.game, BASE_DIR)
    db = ModDB(cfg)
    t0 = time.time()
    snap = load_db_snapshot(db, args.game, limit=args.limit)
    ids = list(snap.keys())
    print(f"[scan] 库内 {len(ids)} 个 MOD，batch={args.batch} sleep={args.sleep}s", flush=True)
    if not ids:
        print("库为空")
        db.close()
        return 2

    details = fetch_details(ids, batch=args.batch, sleep=args.sleep, verbose=True)
    elapsed = time.time() - t0
    print(f"[scan] Steam 返回 {len(details)}/{len(ids)}，耗时 {elapsed:.1f}s", flush=True)

    content, meta, unchanged, missing = [], [], 0, []
    baseline_stale_list = []
    need_retranslate = []  # content_changed ∪ baseline_stale
    for sid, row in snap.items():
        steam = details.get(sid)
        if not steam:
            missing.append(row)
            continue
        db_kind, baseline_kind = classify(row, steam)
        steam_desc = steam.get("description_clean") or clean_bbcode(steam.get("description") or "")
        entry = {
            "steam_id": sid,
            "title": row["title"][:48],
            "db_kind": db_kind,
            "baseline_kind": baseline_kind,
            "subs_old": row["subs"],
            "subs_new": int(steam.get("subscriptions") or 0),
            "tu_old": row["time_updated"],
            "tu_new": int(steam.get("time_updated") or 0),
            "desc_old_len": row["desc_len"],
            "desc_new_len": len(steam_desc),
            "stale_flag": row["stale"],
            "confirmed_at": row["confirmed_at"],
        }
        if db_kind == "content_changed":
            content.append(entry)
        elif db_kind == "meta_changed":
            meta.append(entry)
        else:
            unchanged += 1
        if baseline_kind == "baseline_stale":
            baseline_stale_list.append(entry)
        if db_kind == "content_changed" or baseline_kind == "baseline_stale":
            entry["_steam_desc"] = steam_desc
            entry["_steam"] = steam
            need_retranslate.append(entry)

    content.sort(key=lambda x: -x["subs_new"])
    meta.sort(key=lambda x: -abs(x["subs_new"] - x["subs_old"]))
    baseline_stale_list.sort(key=lambda x: -x["subs_new"])
    need_retranslate.sort(key=lambda x: -x["subs_new"])

    report = {
        "game": args.game,
        "scanned": len(ids),
        "steam_ok": len(details),
        "elapsed_sec": round(elapsed, 1),
        "content_changed": len(content),
        "baseline_stale": len(baseline_stale_list),
        "need_retranslate": len(need_retranslate),
        "meta_changed": len(meta),
        "unchanged": unchanged,
        "missing_on_steam": len(missing),
        "content_top": [{k: v for k, v in e.items() if not k.startswith("_")} for e in content[:50]],
        "baseline_stale_top": [
            {k: v for k, v in e.items() if not k.startswith("_")}
            for e in baseline_stale_list[:50]
        ],
        "meta_top": meta[:20],
        "missing_top": [
            {"steam_id": m["steam_id"], "title": m["title"][:48], "subs": m["subs"]}
            for m in missing[:20]
        ],
    }

    if args.write:
        n = 0
        for sid, steam in details.items():
            row = snap.get(sid)
            if not row:
                continue
            mod = db.get_mod_by_steam_id(sid)
            if not mod:
                continue
            db.upsert_mod({
                **mod,
                "subscriptions": steam.get("subscriptions", mod.get("subscriptions") or 0),
                "favorites": steam.get("favorited", mod.get("favorites") or 0),
                "views": steam.get("views", mod.get("views") or 0),
                "time_updated": steam.get("time_updated", mod.get("time_updated") or 0),
                "description": steam.get("description", mod.get("description") or ""),
                "description_clean": steam.get("description_clean") or clean_bbcode(steam.get("description") or ""),
                "preview_url": steam.get("preview_url", mod.get("preview_url") or ""),
                "fetched_at": time.strftime("%Y-%m-%d"),
            })
            n += 1
        print(f"[write] 已写回 {n} 个 MOD 的 Steam 最新数据", flush=True)
        report["written"] = n

    if args.mark_stale and baseline_stale_list:
        ids_mark = [e["steam_id"] for e in baseline_stale_list]
        db.conn.execute(
            "UPDATE mods SET translation_stale=1 "
            "WHERE game_id=? AND steam_id IN (SELECT value FROM json_each(?))",
            [args.game, json.dumps(ids_mark)],
        )
        db.conn.commit()
        print(f"[mark-stale] 已写 translation_stale=1：{len(ids_mark)} 个（baseline_stale）")
        report["marked_stale"] = len(ids_mark)

    if args.export_pack and need_retranslate:
        pack_dir = os.path.join(BASE_DIR, "translations", "stale_wave")
        os.makedirs(pack_dir, exist_ok=True)
        fields = ("title", "summary", "description", "gameplay", "reviews", "features")
        translations = []
        for e in need_retranslate:
            mod = db.get_mod_by_steam_id(e["steam_id"])
            if not mod:
                continue
            trans = db.get_translations(mod["id"])
            if e["baseline_kind"] == "baseline_stale":
                stale_type = "baseline_stale"
            else:
                stale_type = "content_changed"
            item = {
                "steam_id": e["steam_id"],
                "title_en": mod.get("title_en") or e["title"],
                "description_clean": (e.get("_steam_desc") or "")[:6000],
                "tags": mod.get("tags") or "",
                "subscriptions": e["subs_new"],
                "stale_type": stale_type,
                "time_updated": e["tu_new"],
                "db_kind": e["db_kind"],
                "baseline_kind": e["baseline_kind"],
            }
            for f in fields:
                item[f + "_zh_current"] = trans.get(f, "")
            translations.append(item)
        pack_path = os.path.join(
            pack_dir, f"stale_task_scan_{time.strftime('%Y%m%d_%H%M%S')}.json"
        )
        payload = {
            "game": args.game,
            "source": (
                f"Steam 差分扫描重译任务包（content∪baseline 共 {len(translations)} 条）"
            ),
            "stale_count_total": len(translations),
            "translations": translations,
        }
        with open(pack_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        print(f"[export-pack] 写出 {len(translations)} 条 → {pack_path}")
        report["export_pack"] = pack_path
        report["export_pack_count"] = len(translations)

    if args.export_details:
        details_path = os.path.join(BASE_DIR, "data", "details.jsonl")
        with open(details_path, "a", encoding="utf-8") as f:
            for d in details.values():
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        print(f"[export] 追加 {len(details)} 条到 details.jsonl")

    # 清理临时键，避免 JSON 报告膨胀
    for e in need_retranslate:
        e.pop("_steam_desc", None)
        e.pop("_steam", None)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("\n===== Steam 差分报告 =====")
        print(f"扫描 {len(ids)} · 成功 {len(details)} · 耗时 {elapsed:.0f}s")
        print(
            f"DB内容变化 {len(content)} · 基线过期 {len(baseline_stale_list)} · "
            f"需重译(并集) {len(need_retranslate)} · "
            f"仅元数据 {len(meta)} · 无变化 {unchanged} · Steam 已消失 {len(missing)}"
        )
        if content:
            print(f"\n【DB 描述落后 Steam】前 {min(args.top, len(content))} 条：")
            for e in content[:args.top]:
                mark = "⚠已标stale" if e["stale_flag"] else "  "
                print(f"  {e['subs_new']:>9,}  {e['steam_id']}  {mark}  "
                      f"desc {e['desc_old_len']}→{e['desc_new_len']}  {e['title']}")
        if baseline_stale_list:
            print(f"\n【中文基线过期 / 需重译】前 {min(args.top, len(baseline_stale_list))} 条：")
            for e in baseline_stale_list[:args.top]:
                mark = "⚠已标stale" if e["stale_flag"] else "  "
                print(f"  {e['subs_new']:>9,}  {e['steam_id']}  {mark}  "
                      f"db={e['db_kind']}  {e['title']}")
        if meta:
            print(f"\n【仅订阅/时间变化】前 {min(10, len(meta))} 条：")
            for e in meta[:10]:
                delta = e["subs_new"] - e["subs_old"]
                sign = "+" if delta >= 0 else ""
                print(f"  {e['subs_new']:>9,}  {e['steam_id']}  {sign}{delta}  {e['title']}")
        if missing:
            print(f"\n【Steam 已消失/不可见】{len(missing)} 条（可能下架或仅好友可见）")
        if not content and not baseline_stale_list:
            print("\n✅ 无内容/基线腐化，中文库与 Steam 描述一致")
        elif need_retranslate:
            print(f"\n→ 下一步：--write 刷新库描述 + --export-pack 导出重译包"
                  f"（已有 {len(need_retranslate)} 条）；导入后 confirm_stale_translations")

    db.close()
    return 1 if (content or baseline_stale_list) else 0


if __name__ == "__main__":
    sys.exit(main())
