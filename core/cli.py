"""Paradox 中文 MOD 管理工具 - 命令行入口

用法：
    python -m core.cli list-games                    # 列出支持的游戏
    python -m core.cli scan --game stellaris          # 扫描本地 MOD
    python -m core.cli dlc-check --game stellaris --owned 281992,392450
    python -m core.cli localize --game stellaris      # 汉化包匹配
    python -m core.cli community --game stellaris --import data/stellaris/community.json
    python -m core.cli update --game stellaris --force  # 更新数据
    python -m core.cli search 巨构 --game stellaris   # 搜索
"""
from __future__ import annotations

import argparse
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.game_config import GAME_REGISTRY, get_game, list_games
from core.mod_db import ModDB

# 导入所有游戏配置以触发注册（可扩展：新增游戏只需加入 import）
import games.stellaris.config.game  # noqa: F401
import games.ck3.config.game  # noqa: F401
import games.hoi4.config.game  # noqa: F401


def cmd_list_games(args):
    print("支持的 Paradox 游戏:")
    for gid in list_games():
        cfg = get_game(gid, BASE_DIR)
        print(f"  {gid:12s} {cfg.game_name}  (Steam AppID: {cfg.steam_app_id})")


def cmd_scan(args):
    cfg = get_game(args.game, BASE_DIR)
    from core.local_scanner import LocalScanner
    print(f"扫描本地 MOD（{cfg.game_name}）...")
    scanner = LocalScanner(cfg)
    mods = scanner.scan(verbose=True)
    stats = scanner.stats()
    print(f"\n发现本地 MOD: {stats['total']} 个")
    print(f"  知识库已收录: {stats['in_knowledge']} 个")
    print(f"  知识库未收录: {stats['unknown']} 个")
    if args.list:
        for m in scanner.list_local():
            flag = "✓" if m["in_knowledge"] else "?"
            print(f"  {flag} [{m['source']}] {m['display_name']} v{m['version']} {m['size_mb']}MB")
    scanner.close()


def cmd_dlc_check(args):
    cfg = get_game(args.game, BASE_DIR)
    from core.dlc_checker import DLCChecker
    checker = DLCChecker(cfg)
    owned = args.owned.split(",") if args.owned else []
    print(f"DLC 依赖检测（{cfg.game_name}），你拥有的 DLC: {len(owned)} 个")
    warnings = checker.scan_all(owned, limit=getattr(args, "limit", 200))
    if not warnings:
        print("  没有检测到缺失的 DLC 依赖")
    else:
        print(f"  发现 {len(warnings)} 个 MOD 有缺失 DLC")
    for w in warnings[:20]:
        missing_names = ", ".join(m["name_zh"] for m in w["missing"])
        print(f"  ⚠ {w['mod']['title_en'][:35]}: 缺 {missing_names}")
    if args.verbose:
        print("\n全部 DLC 清单:")
        for d in checker.all_dlcs():
            print(f"  {d.app_id} | {d.name_zh} ({d.name})")
    checker.close()


def cmd_search(args):
    cfg = get_game(args.game, BASE_DIR)
    db = ModDB(cfg)
    mods = db.list_mods(keyword=args.keyword, limit=args.limit)
    print(f"搜索「{args.keyword}」: {len(mods)} 条")
    for m in mods[:args.limit]:
        score = m.get("score") or 0
        print(f"  {score:4.1f}分 | {m['title_en'][:40]} | {m['subscriptions']:,} 订阅")
    db.close()


def cmd_localize(args):
    cfg = get_game(args.game, BASE_DIR)
    from core.localization_matcher import LocalizationMatcher
    matcher = LocalizationMatcher(cfg)
    locs = matcher.all()
    print(f"汉化包数据库: {len(locs)} 条")
    for loc in locs:
        print(f"  {loc.get('mod_steam_id')} | {loc.get('name')} | 目标 {loc.get('target_version')} | {loc.get('status')}")


def cmd_community(args):
    cfg = get_game(args.game, BASE_DIR)
    from core.community_rating import CommunityRating
    cr = CommunityRating(cfg)
    if args.import_file:
        import json
        with open(args.import_file, encoding="utf-8") as f:
            data = json.load(f)
        # 兼容两种格式：直接列表，或 {"community": [...]}
        if isinstance(data, dict):
            data = data.get("community", [])
        n = cr.import_json(data)
        print(f"导入社区口碑: {n} 条")
        n2 = cr.recompute_all()
        print(f"重算推荐指数: {n2} 个 MOD")
    else:
        print("用法: community --import <file.json>")


def cmd_update(args):
    cfg = get_game(args.game, BASE_DIR)
    from core.updater import DataUpdater
    from core.steam_fetch import sync_subscriptions
    sys.path.append(os.path.join(BASE_DIR, "scripts"))
    from snapshot_trend import snapshot  # noqa: E402
    db = ModDB(cfg)
    updater = DataUpdater(cfg, db)
    # 真实 Steam API 增量同步（订阅量/更新时间）
    updater.register_task(
        "steam_sync",
        lambda: sync_subscriptions(cfg, db, stale_days=args.stale_days, verbose=True),
        schedule_hours=24)
    # 订阅热度趋势快照（每日）
    updater.register_task(
        "trend_snapshot",
        lambda: snapshot(args.game, verbose=True),
        schedule_hours=24)
    results = updater.run(force=args.force, verbose=True)
    print("\n更新结果:")
    for r in results:
        status = "✓" if r["ok"] else "✗"
        print(f"  {status} {r['task']}: {r.get('result', r.get('error'))}")
    print("\n状态:", updater.status())
    db.close()


def main():
    ap = argparse.ArgumentParser(description="Paradox 中文 MOD 管理工具")
    ap.add_argument("--game", default="stellaris", choices=list(GAME_REGISTRY),
                    help="目标游戏")
    sub = ap.add_subparsers(dest="cmd")

    def add_game_opt(p):
        p.add_argument("--game", default=None, choices=list(GAME_REGISTRY),
                       help="目标游戏（覆盖全局）")

    p_list = sub.add_parser("list-games")
    p_list.set_defaults(fn=cmd_list_games)

    p_scan = sub.add_parser("scan", help="扫描本地 MOD")
    p_scan.add_argument("--list", action="store_true", help="列出详情")
    add_game_opt(p_scan)
    p_scan.set_defaults(fn=cmd_scan)

    p_dlc = sub.add_parser("dlc-check", help="DLC 依赖检测")
    p_dlc.add_argument("--owned", default="", help="已拥有 DLC app_id，逗号分隔")
    p_dlc.add_argument("--limit", type=int, default=200, help="扫描 MOD 数量上限")
    p_dlc.add_argument("--verbose", action="store_true")
    add_game_opt(p_dlc)
    p_dlc.set_defaults(fn=cmd_dlc_check)

    p_s = sub.add_parser("search", help="搜索 MOD")
    p_s.add_argument("keyword")
    p_s.add_argument("--limit", type=int, default=10)
    add_game_opt(p_s)
    p_s.set_defaults(fn=cmd_search)

    p_l = sub.add_parser("localize", help="汉化包匹配")
    add_game_opt(p_l)
    p_l.set_defaults(fn=cmd_localize)

    p_c = sub.add_parser("community", help="社区口碑")
    p_c.add_argument("--import-file", dest="import_file")
    add_game_opt(p_c)
    p_c.set_defaults(fn=cmd_community)

    p_u = sub.add_parser("update", help="数据更新")
    p_u.add_argument("--force", action="store_true", help="忽略计划时间强制更新")
    p_u.add_argument("--stale-days", type=int, default=3,
                     help="超过 N 天未抓取的 MOD 才更新（默认 3）")
    add_game_opt(p_u)
    p_u.set_defaults(fn=cmd_update)

    args = ap.parse_args()
    if not hasattr(args, "fn"):
        ap.print_help()
        return
    # 子命令 --game 未指定时回退到全局默认
    if not getattr(args, "game", None):
        args.game = "stellaris"
    args.fn(args)


if __name__ == "__main__":
    main()
