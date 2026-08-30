"""导出订阅热度趋势快照（云端备份用，当前仅群星）

用法:
    python scripts/export_trend.py          # → data/stellaris/trend_export.json

背景：trend 表只存在于运行每日 cron 的云端库中，本地没有历史。
服务器磁盘一旦损坏，连续快照历史即丢失。建议云端每日 cron 在
`core.cli update` 之后追加运行本脚本；需要取回本地时，用 TAT 执行
`gzip -k trend_export.json && base64 trend_export.json.gz`（gzip 后约
20-40KB，满足 TAT 64KB 输出上限），把输出粘回本地解码。

当前仅支持群星（唯一有云端每日快照的游戏）；CK3/HOI4 需要时
参照 GameConfig.save_json 的固定目录写入方式扩展。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import games.stellaris.config.game  # noqa: F401
from core.game_config import get_game


def export(cfg) -> dict:
    conn = sqlite3.connect(cfg.db_path)
    try:
        rows = conn.execute(
            "SELECT steam_id, date, subs FROM trend ORDER BY date, steam_id").fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return {
        "game": cfg.game_id,
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "rows": [{"steam_id": r[0], "date": r[1], "subs": r[2]} for r in rows],
    }


def main():
    ap = argparse.ArgumentParser(description="导出 trend 表为 JSON（云端备份用）")
    args = ap.parse_args()

    cfg = get_game("stellaris", BASE_DIR)
    data = export(cfg)
    cfg.save_json("trend_export.json", data)
    print(f"导出 {len(data['rows'])} 行 → data/stellaris/trend_export.json")


if __name__ == "__main__":
    main()
