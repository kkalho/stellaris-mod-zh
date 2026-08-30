"""数据体检脚本：一条命令验证知识库健康度

用法:
    python scripts/verify_db.py                # 默认检查 stellaris
    python scripts/verify_db.py --game ck3
    python scripts/verify_db.py --json         # 机器可读输出（自动化用）

检查项:
- 六字段翻译覆盖（title/summary/description/gameplay/reviews/features）
- version / optional_dlcs / pinyin_idx 覆盖（归零 = 交接文档坑 #1 复发）
- translated 标记与翻译记录一致性
- trend / compat / community 表行数
- 抽查已知 MOD（仅 stellaris）

退出码: 0 = 健康；1 = 命中「标注归零」特征（先跑 scripts/rebuild_all.py）
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

SIX_FIELDS = ["title", "summary", "description", "gameplay", "reviews", "features"]

# stellaris 抽查样本：巨构系列（Gigastructural），库中必须有中文标题
SPOT_CHECK = {"stellaris": {"steam_id": "1121692237", "expect_title_field": True}}


def verify(game_id: str) -> dict:
    cfg = get_game(game_id, BASE_DIR)
    if not os.path.exists(cfg.db_path):
        return {"game": game_id, "ok": False, "critical": [f"数据库不存在: {cfg.db_path}"],
                "warnings": [], "stats": {}}
    import sqlite3
    conn = sqlite3.connect(cfg.db_path)
    conn.row_factory = sqlite3.Row

    s: dict = {}
    s["total"] = conn.execute(
        "SELECT COUNT(*) FROM mods WHERE game_id=?", (game_id,)).fetchone()[0]
    s["translated_flag"] = conn.execute(
        "SELECT COUNT(*) FROM mods WHERE game_id=? AND translated=1", (game_id,)).fetchone()[0]

    for f in SIX_FIELDS:
        s[f"cov_{f}"] = conn.execute(
            "SELECT COUNT(DISTINCT t.mod_id) FROM translations t "
            "JOIN mods m ON m.id=t.mod_id WHERE m.game_id=? AND t.field=?",
            (game_id, f)).fetchone()[0]

    s["version"] = conn.execute(
        "SELECT COUNT(*) FROM mods WHERE game_id=? AND version IS NOT NULL AND version != ''",
        (game_id,)).fetchone()[0]
    s["optional_dlcs"] = conn.execute(
        "SELECT COUNT(*) FROM mods WHERE game_id=? AND optional_dlcs IS NOT NULL "
        "AND optional_dlcs != '' AND optional_dlcs != '[]'", (game_id,)).fetchone()[0]
    s["pinyin_idx"] = conn.execute(
        "SELECT COUNT(*) FROM mods WHERE game_id=? AND pinyin_idx IS NOT NULL AND pinyin_idx != ''",
        (game_id,)).fetchone()[0]
    s["deprecated"] = conn.execute(
        "SELECT COUNT(*) FROM mods WHERE game_id=? AND status IS NOT NULL AND status != ''",
        (game_id,)).fetchone()[0]
    try:
        s["trend_rows"] = conn.execute("SELECT COUNT(*) FROM trend").fetchone()[0]
        s["trend_dates"] = conn.execute("SELECT COUNT(DISTINCT date) FROM trend").fetchone()[0]
    except sqlite3.OperationalError:
        s["trend_rows"] = s["trend_dates"] = 0
    try:
        s["compat"] = conn.execute("SELECT COUNT(*) FROM compat").fetchone()[0]
        s["community"] = conn.execute("SELECT COUNT(*) FROM community").fetchone()[0]
    except sqlite3.OperationalError:
        s["compat"] = s["community"] = 0

    # 抽查：已知 MOD 必须有中文标题翻译
    spot = {}
    sc = SPOT_CHECK.get(game_id)
    if sc and s["total"]:
        row = conn.execute(
            "SELECT m.id, t.zh_text FROM mods m "
            "LEFT JOIN translations t ON t.mod_id=m.id AND t.field='title' "
            "WHERE m.game_id=? AND m.steam_id=?",
            (game_id, sc["steam_id"])).fetchone()
        spot = {"steam_id": sc["steam_id"], "found": bool(row),
                "has_zh_title": bool(row and row["zh_text"])}
    s["spot_check"] = spot
    conn.close()

    critical, warnings = [], []
    total = s["total"]
    if total == 0:
        critical.append("库中 0 个 MOD")
    else:
        # 坑 #1 特征：version 与 DLC 标注同时归零（较大库才判定，避免误伤小库）
        if total >= 50 and s["version"] == 0 and s["optional_dlcs"] == 0:
            critical.append("version 与 optional_dlcs 同时归零——「重建清标注」特征，"
                            "请运行 python scripts/rebuild_all.py")
        if total >= 50 and s["translated_flag"] == 0 and s["cov_title"] == 0:
            critical.append("翻译全部丢失（translated=0 且无 title 翻译记录）")
        if s["cov_title"] == 0 and s["translated_flag"] > 0:
            critical.append("translated 标记 >0 但 title 翻译为 0，状态不一致")
        if s["pinyin_idx"] == 0:
            warnings.append("pinyin_idx 为空，拼音搜索不可用（重跑 rebuild_pinyin_idx.py）")
        if s["translated_flag"] != s["cov_title"]:
            warnings.append(f"translated 标记({s['translated_flag']}) 与 title 翻译数"
                            f"({s['cov_title']}) 不一致")
        for f in SIX_FIELDS:
            if s[f"cov_{f}"] == 0:
                warnings.append(f"字段 {f} 覆盖为 0")
    if s.get("spot_check") and total:
        if not s["spot_check"]["found"]:
            warnings.append(f"抽查 MOD {s['spot_check']['steam_id']} 不在库中")
        elif not s["spot_check"]["has_zh_title"]:
            critical.append(f"抽查 MOD {s['spot_check']['steam_id']} 缺少中文标题翻译")

    return {"game": game_id, "ok": not critical, "critical": critical,
            "warnings": warnings, "stats": s}


def print_report(r: dict):
    s = r["stats"]
    print(f"\n===== 数据体检：{r['game']} =====")
    if not s:
        for c in r["critical"]:
            print(f"  🔴 {c}")
        return
    t = s["total"] or 1
    print(f"  MOD 总数          {s['total']}")
    print(f"  六字段覆盖:")
    for f in SIX_FIELDS:
        pct = s[f"cov_{f}"] / t * 100
        mark = "✅" if s[f"cov_{f}"] == s["total"] and s["total"] else ("⚠️ " if s[f"cov_{f}"] else "🔴")
        print(f"    {f:<13} {s[f'cov_{f}']:>5}  ({pct:5.1f}%)  {mark}")
    print(f"  version 标注      {s['version']}")
    print(f"  optional_dlcs     {s['optional_dlcs']}")
    print(f"  pinyin_idx        {s['pinyin_idx']}")
    print(f"  deprecated 标注   {s['deprecated']}")
    print(f"  trend             {s['trend_rows']} 行 / {s['trend_dates']} 天")
    print(f"  compat / community {s['compat']} / {s['community']}")
    if s.get("spot_check"):
        sc = s["spot_check"]
        state = "✓" if sc.get("has_zh_title") else ("✗ 无中文标题" if sc.get("found") else "✗ 不在库中")
        print(f"  抽查 {sc['steam_id']}: {state}")
    for w in r["warnings"]:
        print(f"  🟡 {w}")
    for c in r["critical"]:
        print(f"  🔴 {c}")
    print(f"  结论: {'✅ 健康' if r['ok'] else '🔴 异常——见上方红色项，先跑 scripts/rebuild_all.py'}")


def main():
    ap = argparse.ArgumentParser(description="知识库数据体检")
    ap.add_argument("--game", default="stellaris")
    ap.add_argument("--json", action="store_true", help="输出 JSON（自动化用）")
    args = ap.parse_args()
    r = verify(args.game)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print_report(r)
    sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
