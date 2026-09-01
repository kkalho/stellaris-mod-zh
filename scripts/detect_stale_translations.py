"""翻译腐化检测：识别原文已更新但翻译未跟进的 MOD

三维度检测（按精确度排序）：
  1. 内容维度（精确）  当前 description_clean 的 SHA256 ≠ desc_hash_baseline
                        → 确定腐化，翻译必须重审
  2. 时间维度（粗筛）  mods.time_updated（Steam 更新时间戳）> translation_confirmed_at
                        → 疑似腐化（可能只改了标签/预览图，描述未变）
  3. 待检维度（自动）  fetched_at > translation_confirmed_at 但 hash 未变
                        → 已重抓且原文无变化，可自动刷新 confirmed_at

用法:
    python scripts/detect_stale_translations.py                  # 默认 stellaris，文本报告
    python scripts/detect_stale_translations.py --game ck3
    python scripts/detect_stale_translations.py --json           # JSON 输出（自动化用）
    python scripts/detect_stale_translations.py --top 30         # 只显示前 30
    python scripts/detect_stale_translations.py --mark-stale     # 将腐化写入 translation_stale 字段
    python scripts/detect_stale_translations.py --auto-refresh   # 自动刷新"重抓无变化"的 confirmed_at

退出码: 0=无腐化；1=检测到腐化（内容维度或时间维度）
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sqlite3
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import games.stellaris.config.game  # noqa: F401
import games.ck3.config.game  # noqa: F401
import games.hoi4.config.game  # noqa: F401
from core.game_config import get_game


def sha256(text: str) -> str:
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def date_to_ts(date_str: str) -> int:
    """YYYY-MM-DD 转当天 00:00 的 Unix 时间戳，失败返回 0。"""
    if not date_str:
        return 0
    try:
        return int(datetime.datetime.strptime(date_str, "%Y-%m-%d").timestamp())
    except (ValueError, TypeError):
        return 0


def detect(game_id: str, mark_stale: bool = False,
           auto_refresh: bool = False) -> dict:
    cfg = get_game(game_id, BASE_DIR)
    db_path = cfg.db_path
    if not os.path.exists(db_path):
        return {"game": game_id, "ok": False, "error": f"数据库不存在: {db_path}"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 检查字段是否存在（未迁移的库）
    cols = [r[1] for r in conn.execute("PRAGMA table_info(mods)").fetchall()]
    if "desc_hash_baseline" not in cols:
        conn.close()
        return {"game": game_id, "ok": False,
                "error": "缺少 desc_hash_baseline 字段，请先运行 scripts/migrate_translation_baseline.py"}

    total = conn.execute(
        "SELECT COUNT(*) FROM mods WHERE game_id=?", (game_id,)).fetchone()[0]
    translated = conn.execute(
        "SELECT COUNT(*) FROM mods WHERE game_id=? AND translated=1", (game_id,)).fetchone()[0]
    has_baseline = conn.execute(
        "SELECT COUNT(*) FROM mods WHERE game_id=? AND translated=1 "
        "AND desc_hash_baseline IS NOT NULL AND desc_hash_baseline != ''",
        (game_id,)).fetchone()[0]

    # 取所有已翻译 MOD 做检测
    rows = conn.execute("""
        SELECT id, steam_id, title_en, title, time_updated, fetched_at,
               description_clean, desc_hash_baseline, translation_confirmed_at,
               translation_stale, subscriptions, length(description_clean) as desc_len
        FROM mods
        WHERE game_id=? AND translated=1
        ORDER BY subscriptions DESC
    """, (game_id,)).fetchall()

    content_stale = []   # 确定腐化：hash 变了
    time_suspect = []    # 疑似腐化：time_updated 较新但 hash 未变
    refreshable = []     # 可自动刷新：fetched_at 较新但无变化
    no_baseline = []     # 无基线（迁移遗漏）

    for r in rows:
        baseline = r["desc_hash_baseline"] or ""
        if not baseline:
            no_baseline.append(dict(r))
            continue

        current_hash = sha256(r["description_clean"] or "")
        confirmed_at = r["translation_confirmed_at"] or ""
        confirmed_ts = date_to_ts(confirmed_at)
        steam_updated = r["time_updated"] or 0
        fetched_at = r["fetched_at"] or ""

        entry = {
            "steam_id": r["steam_id"],
            "title_en": r["title_en"],
            "title": r["title"],
            "subscriptions": r["subscriptions"] or 0,
            "time_updated": datetime.date.fromtimestamp(steam_updated).isoformat() if steam_updated else "",
            "fetched_at": fetched_at,
            "translation_confirmed_at": confirmed_at,
            "baseline_hash": baseline[:16],
            "current_hash": current_hash[:16],
            "desc_len": r["desc_len"] or 0,
        }

        # 维度 1：内容 hash 变化 → 确定腐化
        if current_hash != baseline:
            # 计算 baseline 时的描述长度（不可得，用当前长度做参考）
            entry["stale_type"] = "content_changed"
            content_stale.append(entry)
            continue

        # 维度 2：time_updated > confirmed_at 但 hash 未变 → 疑似
        if steam_updated > 0 and confirmed_ts > 0 and steam_updated > confirmed_ts:
            entry["stale_type"] = "time_updated_newer"
            entry["days_after_confirm"] = (
                datetime.date.fromtimestamp(steam_updated) -
                datetime.datetime.fromtimestamp(confirmed_ts).date()
            ).days
            time_suspect.append(entry)
            continue

        # 维度 3：fetched_at > confirmed_at 但 hash 未变 → 可自动刷新
        if fetched_at and confirmed_at and fetched_at > confirmed_at:
            entry["stale_type"] = "refreshable"
            refreshable.append(entry)

    # 写库操作
    written = {"mark_stale": 0, "refresh": 0}
    if mark_stale and content_stale:
        ids = [e["steam_id"] for e in content_stale]
        conn.execute(f"""
            UPDATE mods SET translation_stale=1
            WHERE game_id=? AND steam_id IN ({','.join('?' * len(ids))})
        """, [game_id] + ids)
        # 清除非腐化的 stale 标记
        all_stale_ids = set(ids)
        conn.execute("""
            UPDATE mods SET translation_stale=0
            WHERE game_id=? AND translation_stale=1
              AND steam_id NOT IN ({})
        """.format(','.join('?' * len(all_stale_ids))), [game_id] + list(all_stale_ids))
        conn.commit()
        written["mark_stale"] = len(content_stale)

    if auto_refresh and refreshable:
        today = time.strftime("%Y-%m-%d")
        ids = [e["steam_id"] for e in refreshable]
        conn.execute(f"""
            UPDATE mods SET translation_confirmed_at=?
            WHERE game_id=? AND steam_id IN ({','.join('?' * len(ids))})
        """, [today, game_id] + ids)
        conn.commit()
        written["refresh"] = len(refreshable)

    # 当前库中的 stale 标记数
    db_stale = conn.execute(
        "SELECT COUNT(*) FROM mods WHERE game_id=? AND translation_stale=1",
        (game_id,)).fetchone()[0]

    conn.close()

    return {
        "game": game_id,
        "ok": True,
        "total": total,
        "translated": translated,
        "has_baseline": has_baseline,
        "no_baseline_count": len(no_baseline),
        "content_stale": content_stale,
        "time_suspect": time_suspect,
        "refreshable": refreshable,
        "db_stale_marked": db_stale,
        "written": written,
    }


def print_report(r: dict, top: int = 50):
    print(f"\n===== 翻译腐化检测：{r['game']} =====")
    print(f"  MOD 总数: {r['total']}，已翻译: {r['translated']}")
    print(f"  有基线: {r['has_baseline']}/{r['translated']}"
          f"{'  ⚠️ 缺基线 ' + str(r['no_baseline_count']) + ' 个' if r['no_baseline_count'] else ''}")
    print(f"  库中 stale 标记: {r['db_stale_marked']}")
    print()

    # 确定腐化
    cs = r["content_stale"]
    print(f"  🔴 确定腐化（原文描述已变化）: {len(cs)} 个")
    if cs:
        print(f"     {'订阅':>8}  {'Steam更新':>12}  {'翻译确认':>12}  {'描述长度':>8}  MOD")
        for e in cs[:top]:
            print(f"     {e['subscriptions']:>8,}  {e['time_updated']:>12}  "
                  f"{e['translation_confirmed_at']:>12}  {e['desc_len']:>8}  "
                  f"{(e['title_en'] or e['title'] or '')[:45]}")
        if len(cs) > top:
            print(f"     ... 还有 {len(cs) - top} 个")
    print()

    # 疑似腐化
    ts = r["time_suspect"]
    print(f"  🟡 疑似腐化（Steam 有更新但描述未变）: {len(ts)} 个")
    if ts:
        print(f"     {'订阅':>8}  {'Steam更新':>12}  {'翻译确认':>12}  {'超期天数':>8}  MOD")
        for e in ts[:top]:
            print(f"     {e['subscriptions']:>8,}  {e['time_updated']:>12}  "
                  f"{e['translation_confirmed_at']:>12}  {e['days_after_confirm']:>8}  "
                  f"{(e['title_en'] or e['title'] or '')[:45]}")
        if len(ts) > top:
            print(f"     ... 还有 {len(ts) - top} 个")
    print()

    # 可自动刷新
    rf = r["refreshable"]
    print(f"  🔵 可自动刷新（已重抓无变化）: {len(rf)} 个")
    if rf and top < 20:
        for e in rf[:top]:
            print(f"     {e['subscriptions']:>8,}  fetched={e['fetched_at']}  "
                  f"confirmed={e['translation_confirmed_at']}  "
                  f"{(e['title_en'] or '')[:40]}")
    print()

    if r["written"]["mark_stale"]:
        print(f"  ✍️  已写入 translation_stale=1: {r['written']['mark_stale']} 个")
    if r["written"]["refresh"]:
        print(f"  ✍️  已自动刷新 confirmed_at: {r['written']['refresh']} 个")

    has_stale = len(cs) > 0 or len(ts) > 0
    print(f"  结论: {'🔴 检测到腐化/疑似腐化' if has_stale else '✅ 无腐化，翻译与原文对齐'}")


def main():
    ap = argparse.ArgumentParser(description="翻译腐化检测")
    ap.add_argument("--game", default="stellaris")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--top", type=int, default=50, help="每类最多显示条数")
    ap.add_argument("--mark-stale", action="store_true",
                    help="将确定腐化的 MOD 写入 translation_stale=1")
    ap.add_argument("--auto-refresh", action="store_true",
                    help="自动刷新'已重抓无变化'的 translation_confirmed_at")
    args = ap.parse_args()

    r = detect(args.game, mark_stale=args.mark_stale, auto_refresh=args.auto_refresh)
    if not r.get("ok"):
        print(f"❌ {r.get('error')}")
        sys.exit(2)

    if args.json:
        # JSON 模式下不打印长列表的全部内容，控制输出大小
        out = {k: v for k, v in r.items() if k not in ("content_stale", "time_suspect", "refreshable")}
        out["content_stale_count"] = len(r["content_stale"])
        out["time_suspect_count"] = len(r["time_suspect"])
        out["refreshable_count"] = len(r["refreshable"])
        out["content_stale_top"] = r["content_stale"][:args.top]
        out["time_suspect_top"] = r["time_suspect"][:args.top]
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print_report(r, top=args.top)

    has_stale = len(r.get("content_stale", [])) > 0 or len(r.get("time_suspect", [])) > 0
    sys.exit(1 if has_stale else 0)


if __name__ == "__main__":
    main()
