"""功能模块：本地 MOD 检测

职责：
1. 扫描本地 MOD 目录（Paradox Launcher mod 目录 + Steam 创意工坊目录）
2. 解析 descriptor.mod，识别名称/版本/标签/来源平台（steam/local）
3. 建立本地 MOD 数据库（data/<game>/local.db）
4. 与云端知识库匹配，标注「有中文介绍/无」

数据流：
    本地目录 → scan() → local.db → 与 mods.db 匹配 → 界面展示
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional

from core.game_config import GameConfig, LocalModInfo
from core.mod_db import ModDB


class LocalScanner:
    """本地 MOD 扫描器"""

    LOCAL_SCHEMA = """
    CREATE TABLE IF NOT EXISTS local_mods (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id      TEXT NOT NULL,
        name         TEXT,              -- 内部名（文件名）
        display_name TEXT,              -- 游戏内显示名
        version      TEXT,
        path         TEXT,              -- 目录/文件绝对路径
        source       TEXT,              -- steam / local / paradox_mods
        steam_id     TEXT,              -- 创意工坊 ID
        remote_id    INTEGER,           -- Paradox Mods ID
        tags         TEXT,
        required_dlcs TEXT,
        size_mb      REAL,
        in_knowledge INTEGER DEFAULT 0, -- 知识库中有无此 MOD
        scanned_at   TEXT
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_local_unique
        ON local_mods(game_id, name);
    """

    def __init__(self, game: GameConfig, db: Optional[ModDB] = None):
        self.game = game
        self.db = db or ModDB(game)
        self._init_local_db()

    def _init_local_db(self):
        self.conn = sqlite3.connect(self.game.local_db_path)
        self.conn.executescript(self.LOCAL_SCHEMA)

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------

    def scan(self, verbose: bool = False) -> List[LocalModInfo]:
        """扫描所有本地 MOD 目录，返回发现的 MOD 列表（并写入 local.db）"""
        found: List[LocalModInfo] = []
        for mod_dir in self.game.local_mod_dirs():
            if verbose:
                print(f"  扫描目录: {mod_dir}")
            found.extend(self._scan_dir(mod_dir))
        # 去重（按 name）
        seen = set()
        unique = []
        for m in found:
            if m.name not in seen:
                seen.add(m.name)
                unique.append(m)
        self._save_to_db(unique)
        return unique

    def _scan_dir(self, mod_dir: str) -> List[LocalModInfo]:
        """扫描单个 MOD 目录"""
        results: List[LocalModInfo] = []
        if not os.path.isdir(mod_dir):
            return results

        # 判断是否 Steam 创意工坊目录（目录名是纯数字 ID）
        is_steam_ws = re.fullmatch(r"\d+", os.path.basename(mod_dir)) is not None

        for entry in os.listdir(mod_dir):
            full = os.path.join(mod_dir, entry)
            try:
                if os.path.isdir(full):
                    info = self._scan_mod_dir(full, entry, is_steam_ws)
                elif entry.endswith(".mod"):
                    info = self._scan_mod_file(full, entry, is_steam_ws)
                else:
                    continue
                if info:
                    results.append(info)
            except Exception as e:
                if "verbose" in globals():
                    print(f"  跳过 {entry}: {e}")
        return results

    def _scan_mod_dir(self, dir_path: str, entry: str,
                      is_steam_ws: bool) -> Optional[LocalModInfo]:
        """扫描一个 MOD 文件夹（找 descriptor.mod）"""
        descriptor = None
        for candidate in ("descriptor.mod", f"{entry}.mod"):
            p = os.path.join(dir_path, candidate)
            if os.path.isfile(p):
                descriptor = p
                break
        if not descriptor:
            return None
        with open(descriptor, encoding="utf-8", errors="replace") as f:
            meta = self.game.parse_descriptor(f.read())
        steam_id = None
        if is_steam_ws:
            steam_id = os.path.basename(dir_path)
        elif meta.get("remote_file_id"):
            steam_id = meta["remote_file_id"]
        source = "steam" if steam_id else "local"
        return LocalModInfo(
            name=meta.get("name", entry),
            display_name=meta.get("display_name", meta.get("name", entry)),
            version=meta.get("version", meta.get("supported_version", "")),
            path=dir_path,
            source=source,
            steam_id=steam_id,
            tags=meta.get("tags", []),
            size_mb=self._dir_size_mb(dir_path),
        )

    def _scan_mod_file(self, file_path: str, entry: str,
                       is_steam_ws: bool) -> Optional[LocalModInfo]:
        """扫描单个 .mod 文件（Launcher 使用，指向实际 MOD 路径）"""
        with open(file_path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        meta = self.game.parse_descriptor(content)
        # 找到实际路径（path="..." 或 archive="..."）
        target = None
        m = re.search(r'(?:path|archive)\s*=\s*"([^"]+)"', content)
        if m:
            target = m.group(1)
            if not os.path.isabs(target):
                target = os.path.join(os.path.dirname(file_path), target)
        steam_id = meta.get("remote_file_id") or (
            os.path.basename(os.path.dirname(file_path))
            if is_steam_ws else None)
        return LocalModInfo(
            name=meta.get("name", entry),
            display_name=meta.get("display_name", meta.get("name", entry)),
            version=meta.get("version", meta.get("supported_version", "")),
            path=target or file_path,
            source="steam" if steam_id else "local",
            steam_id=steam_id,
            tags=meta.get("tags", []),
            size_mb=self._dir_size_mb(target) if target and os.path.isdir(target) else 0,
        )

    @staticmethod
    def _dir_size_mb(path: str) -> float:
        """估算目录大小（MB）"""
        if not os.path.isdir(path):
            return 0.0
        total = 0
        try:
            for root, _, files in os.walk(path):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
        except OSError:
            pass
        return round(total / (1024 * 1024), 1)

    # ------------------------------------------------------------------
    # 数据库写入与查询
    # ------------------------------------------------------------------

    def _save_to_db(self, mods: List[LocalModInfo]):
        """写入 local.db，并标记知识库匹配状态"""
        now = time.strftime("%Y-%m-%d")
        c = self.conn.cursor()
        for m in mods:
            # 是否在知识库中
            in_knowledge = 0
            if m.steam_id:
                in_knowledge = 1 if self.db.get_mod_by_steam_id(m.steam_id) else 0
            c.execute("""
                INSERT OR REPLACE INTO local_mods
                (game_id, name, display_name, version, path, source, steam_id,
                 tags, required_dlcs, size_mb, in_knowledge, scanned_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (self.game.game_id, m.name, m.display_name, m.version, m.path,
                  m.source, m.steam_id, ",".join(m.tags), "", m.size_mb,
                  in_knowledge, now))
        self.conn.commit()

    def list_local(self, only_unknown: bool = False) -> List[Dict[str, Any]]:
        """列出本地 MOD"""
        sql = "SELECT * FROM local_mods WHERE game_id=?"
        if only_unknown:
            sql += " AND in_knowledge=0"
        rows = self.conn.execute(sql, (self.game.game_id,)).fetchall()
        return [dict(zip([d[0] for d in self.conn.description], r)) for r in rows]

    def stats(self) -> Dict[str, int]:
        total = self.conn.execute(
            "SELECT COUNT(*) FROM local_mods WHERE game_id=?",
            (self.game.game_id,)).fetchone()[0]
        in_kb = self.conn.execute(
            "SELECT COUNT(*) FROM local_mods WHERE game_id=? AND in_knowledge=1",
            (self.game.game_id,)).fetchone()[0]
        return {"total": total, "in_knowledge": in_kb, "unknown": total - in_kb}

    def close(self):
        self.conn.close()
        self.db.close()
