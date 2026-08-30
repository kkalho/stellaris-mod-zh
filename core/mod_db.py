"""核心层：统一数据访问（游戏隔离的 SQLite）

所有功能模块通过 ModDB 读写数据，ModDB 内部按游戏隔离：
- data/<game>/mods.db        MOD 主库（元数据/翻译/兼容性/评分/DLC依赖）
- data/<game>/local.db       本地已安装 MOD 库

表结构统一，跨游戏复用同一套 schema，只是数据文件不同。
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

from core.game_config import GameConfig


class ModDB:
    """MOD 主库访问（游戏隔离）"""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS mods (
        id            INTEGER PRIMARY KEY,
        game_id       TEXT NOT NULL,          -- 游戏标识（隔离）
        steam_id      TEXT UNIQUE,
        title         TEXT,                   -- 显示名（优先中文）
        title_en      TEXT,                   -- 英文原名
        author        TEXT,
        author_name   TEXT,
        version       TEXT,
        subscriptions INTEGER DEFAULT 0,
        favorites     INTEGER DEFAULT 0,
        views         INTEGER DEFAULT 0,
        time_created  INTEGER,
        time_updated  INTEGER,
        tags          TEXT,
        url           TEXT,
        preview_url   TEXT,                   -- 封面图
        description   TEXT,
        description_clean TEXT,
        required_dlcs TEXT,                   -- JSON 数组: 必需 DLC app_id
        optional_dlcs TEXT,                   -- JSON 数组: 可选 DLC app_id
        localization_id TEXT,                 -- 关联的汉化包 ID
        score         REAL DEFAULT 0,         -- 综合评分
        like_ratio    REAL DEFAULT 0,         -- 收藏率（favorites/subscriptions，非 Steam 好评率）
        community_score REAL DEFAULT 0,       -- 社区评分
        status        TEXT,                   -- deprecated/outdated/abandoned
        pinyin_idx    TEXT,                   -- 拼音搜索索引
        translated    INTEGER DEFAULT 0,
        fetched_at    TEXT
    );
    CREATE TABLE IF NOT EXISTS translations (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        mod_id     INTEGER NOT NULL REFERENCES mods(id),
        field      TEXT NOT NULL DEFAULT 'description',
        zh_text    TEXT,
        quality    TEXT DEFAULT 'ai',
        updated_at TEXT,
        UNIQUE(mod_id, field)
    );
    CREATE TABLE IF NOT EXISTS compat (
        mod_id    INTEGER PRIMARY KEY REFERENCES mods(id),
        conflicts TEXT,   -- JSON
        requires  TEXT,   -- JSON
        best_with TEXT,   -- JSON
        notes     TEXT,
        has_patches TEXT  -- JSON
    );
    CREATE TABLE IF NOT EXISTS community (
        mod_id      INTEGER PRIMARY KEY REFERENCES mods(id),
        platform    TEXT,      -- tieba/bilibili/nga
        score       REAL,
        comment_summary TEXT,
        recommend   TEXT,
        source_url  TEXT,
        updated_at  TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_mods_game ON mods(game_id);
    CREATE INDEX IF NOT EXISTS idx_mods_subs ON mods(subscriptions DESC);
    """

    def __init__(self, game: GameConfig):
        self.game = game
        self.conn = sqlite3.connect(game.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(self.SCHEMA)
        self.conn.commit()

    # ------------------------------------------------------------------
    # MOD 增删改查
    # ------------------------------------------------------------------

    def upsert_mod(self, data: Dict[str, Any]) -> int:
        """插入或更新一个 MOD，返回 mod_id。

        更新已有记录时只写 data 中显式提供的字段：version / optional_dlcs /
        status / translated 等派生字段未提供则保持原值。
        这是「重建后标注归零」（交接文档坑 #1）的根因修复——任何脚本对
        已有 MOD 重新 upsert 都不会再清掉标注字段。
        """
        now = time.strftime("%Y-%m-%d")
        c = self.conn.cursor()
        steam_id = str(data.get("steam_id", ""))
        existing = None
        if steam_id:
            existing = c.execute(
                "SELECT id FROM mods WHERE game_id=? AND steam_id=?",
                (self.game.game_id, steam_id)).fetchone()
        mod_id = existing[0] if existing else None

        fields = {
            "game_id": self.game.game_id,
            "steam_id": steam_id or None,
            "title": data.get("title", ""),
            "title_en": data.get("title_en", ""),
            "author": data.get("author", ""),
            "author_name": data.get("author_name", ""),
            "version": data.get("version", ""),
            "subscriptions": int(data.get("subscriptions", 0) or 0),
            "favorites": int(data.get("favorites", 0) or 0),
            "views": int(data.get("views", 0) or 0),
            "time_created": int(data.get("time_created", 0) or 0),
            "time_updated": int(data.get("time_updated", 0) or 0),
            "tags": data.get("tags", ""),
            "url": data.get("url", ""),
            "preview_url": data.get("preview_url", ""),
            "description": data.get("description", ""),
            "description_clean": data.get("description_clean", ""),
            "required_dlcs": json.dumps(data.get("required_dlcs", []), ensure_ascii=False),
            "optional_dlcs": json.dumps(data.get("optional_dlcs", []), ensure_ascii=False),
            "localization_id": data.get("localization_id", ""),
            "score": float(data.get("score", 0) or 0),
            "like_ratio": float(data.get("like_ratio", 0) or 0),
            "community_score": float(data.get("community_score", 0) or 0),
            "status": data.get("status", ""),
            "translated": 1 if data.get("translated") else 0,
            "fetched_at": now,
        }
        if mod_id:
            # 只更新 data 中显式提供的字段；fetched_at 是写入时间戳，总是刷新
            update = {k: v for k, v in fields.items() if k in data or k in ("game_id", "fetched_at")}
            cols = ", ".join(f"{k}=?" for k in update)
            c.execute(f"UPDATE mods SET {cols} WHERE id=?", (*update.values(), mod_id))
        else:
            cols = ", ".join(fields.keys())
            placeholders = ", ".join("?" * len(fields))
            c.execute(f"INSERT INTO mods ({cols}) VALUES ({placeholders})", tuple(fields.values()))
            mod_id = c.lastrowid
        self.conn.commit()
        return mod_id

    def get_mod(self, mod_id: int) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM mods WHERE id=?", (mod_id,)).fetchone()
        return dict(row) if row else None

    def get_mod_by_steam_id(self, steam_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM mods WHERE game_id=? AND steam_id=?",
            (self.game.game_id, str(steam_id))).fetchone()
        return dict(row) if row else None

    def list_mods(self, keyword: str = "", limit: int = 200, sort: str = "subs") -> List[Dict]:
        order = {"subs": "subscriptions DESC", "updated": "time_updated DESC",
                 "name": "title_en ASC"}.get(sort, "subscriptions DESC")
        if keyword:
            kw = f"%{keyword}%"
            sql = """
                SELECT m.* FROM mods m
                LEFT JOIN translations t ON t.mod_id = m.id AND t.field = 'title'
                WHERE m.game_id=? AND (m.title_en LIKE ? OR m.title LIKE ?
                      OR m.pinyin_idx LIKE ? OR t.zh_text LIKE ?)
                ORDER BY """ + order + " LIMIT ?"
            rows = self.conn.execute(sql, (self.game.game_id, kw, kw, kw, kw, limit)).fetchall()
        else:
            sql = "SELECT * FROM mods WHERE game_id=? ORDER BY " + order + " LIMIT ?"
            rows = self.conn.execute(sql, (self.game.game_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM mods WHERE game_id=?", (self.game.game_id,)).fetchone()[0]

    # ------------------------------------------------------------------
    # 翻译 / 兼容性 / 社区 数据
    # ------------------------------------------------------------------

    def set_translation(self, mod_id: int, field: str, zh_text: str, quality: str = "ai"):
        now = time.strftime("%Y-%m-%d")
        self.conn.execute("""
            INSERT INTO translations (mod_id, field, zh_text, quality, updated_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(mod_id, field) DO UPDATE SET
                zh_text=excluded.zh_text, updated_at=excluded.updated_at
        """, (mod_id, field, zh_text, quality, now))
        self.conn.commit()

    def get_translations(self, mod_id: int) -> Dict[str, str]:
        rows = self.conn.execute(
            "SELECT field, zh_text FROM translations WHERE mod_id=?", (mod_id,)).fetchall()
        return {r["field"]: r["zh_text"] for r in rows}

    def set_compat(self, mod_id: int, compat: Dict[str, Any]):
        self.conn.execute("""
            INSERT INTO compat (mod_id, conflicts, requires, best_with, notes, has_patches)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(mod_id) DO UPDATE SET
                conflicts=excluded.conflicts, requires=excluded.requires,
                best_with=excluded.best_with, notes=excluded.notes,
                has_patches=excluded.has_patches
        """, (mod_id,
              json.dumps(compat.get("conflicts", []), ensure_ascii=False),
              json.dumps(compat.get("requires", []), ensure_ascii=False),
              json.dumps(compat.get("best_with", []), ensure_ascii=False),
              compat.get("notes", ""),
              json.dumps(compat.get("has_patches", []), ensure_ascii=False)))
        self.conn.commit()

    def get_compat(self, mod_id: int) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM compat WHERE mod_id=?", (mod_id,)).fetchone()
        if not row:
            return None
        return {
            "conflicts": json.loads(row["conflicts"] or "[]"),
            "requires": json.loads(row["requires"] or "[]"),
            "best_with": json.loads(row["best_with"] or "[]"),
            "notes": row["notes"],
            "has_patches": json.loads(row["has_patches"] or "[]"),
        }

    def set_community(self, mod_id: int, data: Dict[str, Any]):
        now = time.strftime("%Y-%m-%d")
        self.conn.execute("""
            INSERT INTO community (mod_id, platform, score, comment_summary, recommend, source_url, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(mod_id) DO UPDATE SET
                platform=excluded.platform, score=excluded.score,
                comment_summary=excluded.comment_summary, recommend=excluded.recommend,
                source_url=excluded.source_url, updated_at=excluded.updated_at
        """, (mod_id, data.get("platform", ""), data.get("score", 0),
              data.get("comment_summary", ""), data.get("recommend", ""),
              data.get("source_url", ""), now))
        self.conn.commit()

    def get_community(self, mod_id: int) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM community WHERE mod_id=?", (mod_id,)).fetchone()
        return dict(row) if row else None

    def close(self):
        self.conn.close()
