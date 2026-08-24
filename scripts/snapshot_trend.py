"""订阅热度趋势快照：把当前库中各 MOD 的订阅量写入趋势表

- 表: data/<game>/mods.db 的 trend(steam_id, date, subs)  —— 每日一行
- 用法: python scripts/snapshot_trend.py [--game stellaris]
- 由 updater 注册为每日任务（trend_snapshot），也可手动跑
- 注意：快照记录的是「当前库中」的订阅数；配合 `cli update`（Steam 同步）
  使用，即可形成真实的订阅涨跌趋势
"""
from __future__ import annotations

import argparse
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import games.stellaris.config.game  # noqa: F401
import games.ck3.config.game  # noqa: F401
import games.hoi4.config.game  # noqa: F401
from core.game_config import get_game
from core.mod_db import ModDB


def snapshot(game_id: str = "stellaris", verbose: bool = False) -> dict:
    cfg = get_game(game_id, BASE_DIR)
    db = ModDB(cfg)
    # 确保 trend 表存在
    db.conn.execute("""
        CREATE TABLE IF NOT EXISTS trend (
            steam_id TEXT NOT NULL,
            date     TEXT NOT NULL,
            subs     INTEGER DEFAULT 0,
            PRIMARY KEY (steam_id, date)
        )""")
    today = time.strftime("%Y-%m-%d")
    mods = db.list_mods(limit=5000)
    count = 0
    for m in mods:
        sid = m.get("steam_id")
        if not sid:
            continue
        subs = m.get("subscriptions") or 0
        db.conn.execute(
            "INSERT OR REPLACE INTO trend (steam_id, date, subs) VALUES (?,?,?)",
            (sid, today, subs))
        count += 1
    db.conn.commit()
    # 清理 60 天前的旧数据
    import datetime
    old = (datetime.date.today() - datetime.timedelta(days=60)).strftime("%Y-%m-%d")
    db.conn.execute("DELETE FROM trend WHERE date < ?", (old,))
    db.conn.commit()
    db.close()
    if verbose:
        print(f"快照完成：{today} 记录 {count} 个 MOD 的订阅量")
    return {"date": today, "snapshotted": count}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="stellaris")
    args = ap.parse_args()
    snapshot(args.game, verbose=True)


if __name__ == "__main__":
    main()
