"""数据库迁移：为翻译腐化检测建立基线

为 mods 表新增字段：
  - desc_hash_baseline      TEXT    翻译确认时 description_clean 的 SHA256（原文锚点）
  - translation_confirmed_at TEXT   翻译最后一次与原文对齐的日期（YYYY-MM-DD）
  - translation_stale        INTEGER 0=正常，1=疑似过时（原文已变化，翻译待更新）

初始化逻辑：
  - 仅对 translated=1 的 MOD 建立基线
  - desc_hash_baseline = SHA256(当前 description_clean)
  - translation_confirmed_at = 该 MOD 最新翻译字段的 updated_at
  - translation_stale = 0

用法:
    python scripts/migrate_translation_baseline.py            # 默认 stellaris
    python scripts/migrate_translation_baseline.py --game ck3
    python scripts/migrate_translation_baseline.py --dry-run  # 只看统计不写库

退出码: 0=成功；1=失败
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sqlite3
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import games.stellaris.config.game  # noqa: F401
import games.ck3.config.game  # noqa: F401
import games.hoi4.config.game  # noqa: F401
from core.game_config import get_game

NEW_COLUMNS = [
    ("desc_hash_baseline", "TEXT"),
    ("translation_confirmed_at", "TEXT"),
    ("translation_stale", "INTEGER DEFAULT 0"),
]


def desc_hash(text: str) -> str:
    """计算 description_clean 的 SHA256，空值返回空串。"""
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def column_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(r[1] == col for r in cur.fetchall())


def migrate(game_id: str, dry_run: bool = False) -> dict:
    cfg = get_game(game_id, BASE_DIR)
    db_path = cfg.db_path
    if not os.path.exists(db_path):
        return {"game": game_id, "ok": False, "error": f"数据库不存在: {db_path}"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 1. 统计当前状态
    total = conn.execute(
        "SELECT COUNT(*) FROM mods WHERE game_id=?", (game_id,)).fetchone()[0]
    translated = conn.execute(
        "SELECT COUNT(*) FROM mods WHERE game_id=? AND translated=1", (game_id,)).fetchone()[0]

    # 2. 检查已有字段
    existing = {col for col, _ in NEW_COLUMNS if column_exists(conn, "mods", col)}
    missing = [(col, typ) for col, typ in NEW_COLUMNS if col not in existing]

    print(f"=== 翻译基线迁移：{game_id} ===")
    print(f"  数据库: {db_path}")
    print(f"  MOD 总数: {total}，已翻译: {translated}")
    print(f"  已有字段: {existing or '无'}")
    print(f"  待添加字段: {[c for c, _ in missing] or '无'}")

    if dry_run:
        print("\n  [dry-run] 不执行任何写入")
        conn.close()
        return {"game": game_id, "ok": True, "dry_run": True,
                "total": total, "translated": translated,
                "added_columns": [c for c, _ in missing]}

    # 3. 备份
    backup_path = db_path + f".bak.baseline.{int(time.time())}"
    shutil.copy2(db_path, backup_path)
    print(f"\n  已备份: {backup_path}")

    # 4. 添加缺失字段
    for col, typ in missing:
        conn.execute(f"ALTER TABLE mods ADD COLUMN {col} {typ}")
        print(f"  已添加字段: {col} ({typ})")
    conn.commit()

    # 5. 初始化基线（仅已翻译且 baseline 为空的 MOD）
    cur = conn.execute("""
        SELECT m.id, m.steam_id, m.title_en, m.description_clean,
               (SELECT MAX(updated_at) FROM translations t WHERE t.mod_id = m.id) as last_trans
        FROM mods m
        WHERE m.game_id=? AND m.translated=1
          AND (m.desc_hash_baseline IS NULL OR m.desc_hash_baseline = '')
    """, (game_id,))
    rows = cur.fetchall()

    initialized = 0
    skipped = 0
    for r in rows:
        h = desc_hash(r["description_clean"])
        confirmed = r["last_trans"] or time.strftime("%Y-%m-%d")
        conn.execute("""
            UPDATE mods SET desc_hash_baseline=?, translation_confirmed_at=?,
                            translation_stale=0
            WHERE id=?
        """, (h, confirmed, r["id"]))
        initialized += 1
    conn.commit()

    # 6. 统计已有基线的 MOD
    has_baseline = conn.execute(
        "SELECT COUNT(*) FROM mods WHERE game_id=? AND translated=1 "
        "AND desc_hash_baseline IS NOT NULL AND desc_hash_baseline != ''",
        (game_id,)).fetchone()[0]
    stale_count = conn.execute(
        "SELECT COUNT(*) FROM mods WHERE game_id=? AND translation_stale=1",
        (game_id,)).fetchone()[0]

    print(f"\n  初始化基线: {initialized} 个（本次新增）")
    print(f"  已有基线跳过: {translated - has_baseline if translated > has_baseline else 0} 个")
    print(f"  当前有基线的已翻译 MOD: {has_baseline}/{translated}")
    print(f"  当前标记 stale: {stale_count}")

    # 7. 验证
    if has_baseline != translated:
        print(f"\n  ⚠️  警告: {translated - has_baseline} 个已翻译 MOD 仍无基线")
    else:
        print(f"\n  ✅ 所有已翻译 MOD 均已建立基线")

    conn.close()
    return {"game": game_id, "ok": True, "total": total, "translated": translated,
            "initialized": initialized, "has_baseline": has_baseline,
            "stale": stale_count, "backup": backup_path}


def main():
    ap = argparse.ArgumentParser(description="翻译腐化检测：数据库基线迁移")
    ap.add_argument("--game", default="stellaris", help="游戏标识（stellaris/ck3/hoi4）")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写库")
    args = ap.parse_args()
    r = migrate(args.game, args.dry_run)
    if not r.get("ok"):
        print(f"\n❌ 失败: {r.get('error')}")
        sys.exit(1)
    print(f"\n{'[dry-run] ' if r.get('dry_run') else ''}完成")


if __name__ == "__main__":
    main()
