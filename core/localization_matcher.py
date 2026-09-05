"""功能模块：汉化包匹配

职责：
1. 汉化包数据库：记录每个 MOD 对应的汉化包（名称/作者/版本/下载源）
2. 兼容性校验：汉化包版本 vs MOD 版本是否匹配
3. 自动下载/更新：从配置的下载源拉取汉化包（占位实现，可接 Steam/网盘）

数据：
- data/<game>/localization.json  汉化包数据库
  {
    "localizations": [
      {
        "mod_steam_id": "1121692237",
        "loc_id": "giga_zh",
        "name": "巨构工程汉化包",
        "author": "鸽组",
        "target_version": "4.4.*",
        "source": "steam",           # steam / url / local
        "source_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=3772088387",
        "local_path": "",            # 已下载到的本地路径
        "status": "not_downloaded",  # not_downloaded / downloaded / outdated
        "updated_at": ""
      }
    ]
  }
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.game_config import GameConfig
from core.mod_db import ModDB


class LocalizationMatcher:
    """汉化包匹配器"""

    def __init__(self, game: GameConfig, db: Optional[ModDB] = None):
        self.game = game
        self.db = db or ModDB(game)
        self._data = self._load()

    # ------------------------------------------------------------------
    # 数据加载/保存
    # ------------------------------------------------------------------

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.game.localization_path):
            with open(self.game.localization_path, encoding="utf-8") as f:
                return json.load(f)
        return {"localizations": []}

    def _save(self):
        Path(self.game.localization_path).write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def all(self) -> List[Dict[str, Any]]:
        return self._data.get("localizations", [])

    # ------------------------------------------------------------------
    # 汉化包增删改查
    # ------------------------------------------------------------------

    def add(self, loc: Dict[str, Any]) -> Dict[str, Any]:
        """添加/更新一个汉化包记录（按 mod_steam_id 去重）"""
        locs = self._data.setdefault("localizations", [])
        for i, existing in enumerate(locs):
            if (existing.get("mod_steam_id") == loc.get("mod_steam_id")
                    and existing.get("name") == loc.get("name")):
                locs[i] = {**existing, **loc}
                self._save()
                return locs[i]
        loc.setdefault("status", "not_downloaded")
        locs.append(loc)
        self._save()
        # 关联到 mods 表
        mod = self.db.get_mod_by_steam_id(str(loc.get("mod_steam_id", "")))
        if mod:
            self.db.conn.execute(
                "UPDATE mods SET localization_id=? WHERE id=?",
                (loc.get("loc_id", ""), mod["id"]))
            self.db.conn.commit()
        return loc

    def remove(self, mod_steam_id: str, name: str = "") -> bool:
        locs = self._data.get("localizations", [])
        before = len(locs)
        if name:
            self._data["localizations"] = [
                l for l in locs
                if not (l.get("mod_steam_id") == mod_steam_id and l.get("name") == name)]
        else:
            self._data["localizations"] = [
                l for l in locs if l.get("mod_steam_id") != mod_steam_id]
        if len(locs) != before:
            self._save()
            return True
        return False

    # ------------------------------------------------------------------
    # 匹配查询
    # ------------------------------------------------------------------

    def find_for_mod(self, mod_steam_id: str) -> List[Dict[str, Any]]:
        """查找某 MOD 的所有汉化包"""
        return [l for l in self.all() if l.get("mod_steam_id") == mod_steam_id]

    def find_by_name(self, keyword: str) -> List[Dict[str, Any]]:
        """按关键词搜索汉化包"""
        kw = keyword.lower()
        return [l for l in self.all()
                if kw in (l.get("name") or "").lower()
                or kw in (l.get("author") or "").lower()]

    # ------------------------------------------------------------------
    # 版本兼容性校验
    # ------------------------------------------------------------------

    def check_compatibility(self, loc: Dict[str, Any],
                            mod_version: str = "") -> Dict[str, Any]:
        """校验汉化包与 MOD 版本的兼容性。

        loc.target_version 支持通配：'4.4.*' / '3.*' / '>=3.4'
        mod_version: MOD 的目标游戏版本（如 '4.4.2'）
        """
        target = loc.get("target_version", "")
        if not target or not mod_version:
            return {"compatible": True, "reason": "版本信息不足，默认兼容"}
        if _version_match(mod_version, target):
            return {"compatible": True, "reason": f"目标版本 {target} 匹配"}
        return {
            "compatible": False,
            "reason": f"汉化包目标版本 {target} 与当前版本 {mod_version} 不匹配",
        }

    # ------------------------------------------------------------------
    # 下载 / 更新（占位实现）
    # ------------------------------------------------------------------

    def download(self, loc: Dict[str, Any], dest_dir: str) -> Dict[str, Any]:
        """下载汉化包到本地。

        source 类型：
        - steam: 仅记录 steam 链接，需用户在 Steam 中订阅（避免版权问题）
        - url: 直接下载压缩包（需要实现解压）
        - local: 本地文件路径
        """
        source = loc.get("source", "")
        if source == "local":
            return {"ok": True, "path": loc.get("source_url", "")}
        if source == "steam":
            # 创意工坊汉化包需在 Steam 内订阅，这里给出提示
            return {
                "ok": False,
                "reason": "创意工坊汉化包请在 Steam 中订阅",
                "steam_url": loc.get("source_url", ""),
            }
        if source == "url":
            return self._download_url(loc, dest_dir)
        return {"ok": False, "reason": f"未知来源: {source}"}

    def _download_url(self, loc: Dict[str, Any], dest_dir: str) -> Dict[str, Any]:
        url = loc.get("source_url", "")
        if not url:
            return {"ok": False, "reason": "缺少下载地址"}
        os.makedirs(dest_dir, exist_ok=True)
        filename = os.path.join(dest_dir, f"{loc.get('loc_id', 'loc')}.zip")
        try:
            urllib.request.urlretrieve(url, filename)
            loc["local_path"] = filename
            loc["status"] = "downloaded"
            loc["updated_at"] = __import__("time").strftime("%Y-%m-%d")
            self._save()
            return {"ok": True, "path": filename}
        except Exception as e:
            return {"ok": False, "reason": f"下载失败: {e}"}

    def check_updates(self) -> List[Dict[str, Any]]:
        """检查所有已下载汉化包是否有更新（占位）"""
        updates = []
        for loc in self.all():
            if loc.get("status") == "downloaded":
                # TODO: 对比远程版本（需要远程元数据接口）
                updates.append({**loc, "has_update": False})
        return updates


def _version_match(version: str, pattern: str) -> bool:
    """简单版本匹配：支持通配 * 和 >= 前缀"""
    version = version.strip()
    pattern = pattern.strip()
    if pattern.startswith(">="):
        try:
            return [int(x) for x in version.split(".")] >= \
                   [int(x) for x in pattern[2:].split(".")]
        except Exception:
            return True
    return fnmatch.fnmatch(version, pattern)
