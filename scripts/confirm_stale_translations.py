"""增量重译确认：重译导入后刷新腐化基线并清除 stale 标记

历史缺口：import_stellaris_translations 只写 translations 表，不写
desc_hash_baseline / translation_confirmed_at / translation_stale。
本脚本在人工/子智能体确认「中文已跟上当前原文」后调用。

用法:
    python scripts/confirm_stale_translations.py --ids 1121692237,1726290528
    python scripts/confirm_stale_translations.py --from-file translations/stale_wave/stale_task_001_merged.json
    python scripts/confirm_stale_translations.py --all-content-stale
    python scripts/confirm_stale_translations.py --game ck3 --all-content-stale

行为:
    desc_hash_baseline      = SHA256(当前 description_clean)
    translation_confirmed_at = 今天 (YYYY-MM-DD)
    translation_stale        = 0

退出码: 0=成功；1=参数或库错误
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
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


def parse_ids(args) -> list[str]:
    ids: list[str] = []
    if args.ids:
        for part in re.split(r"[,\s]+", args.ids.strip()):
            part = re.sub(r"[^0-9]", "", part)
            if part:
                ids.append(part)
    if args.from_file:
        path = args.from_file
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        rows = data.get("translations") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ValueError("文件格式不对：应为数组或含 translations 数组的对象")
        for row in rows:
            if isinstance(row, dict):
                sid = re.sub(r"[^0-9]", "", str(row.get("steam_id") or ""))
                if sid:
                    ids.append(sid)
    # 去重保序
    seen = set()
    out = []
    for sid in ids:
        if sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


def confirm_ids(game_id: str, steam_ids: list[str]) -> int:
    if not steam_ids:
        return 0
    today = time.strftime("%Y-%m-%d")
    db_path = get_game(game_id, BASE_DIR).db_path
    conn = sqlite3.connect(db_path, timeout=8)
    conn.execute("PRAGMA busy_timeout = 8000")
    try:
        n = 0
        for sid in steam_ids:
            row = conn.execute(
                "SELECT id, description_clean FROM mods WHERE game_id=? AND steam_id=?",
                (game_id, sid),
            ).fetchone()
            if not row:
                print(f"# 跳过（库中无此 MOD）: {sid}", file=sys.stderr)
                continue
            h = sha256(row[1] or "")
            cur = conn.execute(
                "UPDATE mods SET desc_hash_baseline=?, translation_confirmed_at=?, "
                "translation_stale=0 WHERE game_id=? AND steam_id=?",
                (h, today, game_id, sid),
            )
            n += cur.rowcount or 0
        conn.commit()
        return n
    finally:
        conn.close()


def confirm_all_content_stale(game_id: str) -> int:
    today = time.strftime("%Y-%m-%d")
    db_path = get_game(game_id, BASE_DIR).db_path
    conn = sqlite3.connect(db_path, timeout=8)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 8000")
    try:
        rows = conn.execute(
            """
            SELECT steam_id, description_clean, desc_hash_baseline
            FROM mods
            WHERE game_id=? AND translated=1
              AND desc_hash_baseline IS NOT NULL AND desc_hash_baseline != ''
            """,
            (game_id,),
        ).fetchall()
        n = 0
        for r in rows:
            h = sha256(r["description_clean"] or "")
            if h == (r["desc_hash_baseline"] or ""):
                continue
            cur = conn.execute(
                "UPDATE mods SET desc_hash_baseline=?, translation_confirmed_at=?, "
                "translation_stale=0 WHERE game_id=? AND steam_id=?",
                (h, today, game_id, r["steam_id"]),
            )
            n += cur.rowcount or 0
        conn.commit()
        return n
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description="重译确认：刷新基线并清除 translation_stale")
    ap.add_argument("--game", default="stellaris")
    ap.add_argument("--ids", help="逗号分隔 steam_id 列表")
    ap.add_argument("--from-file", help="从任务包/合并 JSON 读取 steam_id")
    ap.add_argument("--all-content-stale", action="store_true",
                    help="对所有当前内容腐化的 MOD 批量确认（危险：确认前请确认译文已更新）")
    args = ap.parse_args()

    try:
        if args.all_content_stale:
            if args.ids or args.from_file:
                print("error: --all-content-stale 与 --ids/--from-file 互斥", file=sys.stderr)
                sys.exit(1)
            n = confirm_all_content_stale(args.game)
            print(f"confirmed={n} game={args.game} mode=all-content-stale")
            return
        ids = parse_ids(args)
        if not ids:
            print("error: 需要 --ids / --from-file / --all-content-stale 之一", file=sys.stderr)
            sys.exit(1)
        n = confirm_ids(args.game, ids)
        print(f"confirmed={n} game={args.game} mode=ids")
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
