"""功能模块：DLC 依赖标注

职责：
1. 从 MOD 元数据/描述检测其依赖的 DLC（必需/可选）
2. 对比用户已拥有的 DLC，给出缺失警告
3. 提供 DLC 依赖的增删改查 API（供界面层使用）

数据流：
    Steam API / 描述解析 → game.detect_required_dlcs() → mods.required_dlcs
    用户 DLC 清单（Steam 库）→ dlc_checker.check_missing() → 警告列表
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.game_config import DLCInfo, GameConfig
from core.mod_db import ModDB


class DLCChecker:
    """DLC 依赖检测器"""

    def __init__(self, game: GameConfig, db: Optional[ModDB] = None):
        self.game = game
        self.db = db or ModDB(game)
        self._dlc_map = {d.app_id: d for d in game.load_dlcs()}

    # ------------------------------------------------------------------
    # DLC 清单查询
    # ------------------------------------------------------------------

    def all_dlcs(self) -> List[DLCInfo]:
        return list(self._dlc_map.values())

    def get_dlc(self, app_id: str) -> Optional[DLCInfo]:
        return self._dlc_map.get(app_id)

    # ------------------------------------------------------------------
    # MOD 依赖检测与写入
    # ------------------------------------------------------------------

    def detect_and_save(self, mod_id: int, mod_data: Dict[str, Any]) -> Dict[str, List[str]]:
        """检测 MOD 的 DLC 依赖并写入数据库。

        策略（避免误报）：
        - 描述关键词检测 = 启发式，标记为「可选」（可能只是提及）
        - 明确写 "requires"/"需要" 的 = 标记为「必需」（可人工确认后升级）
        返回 {"required": [...], "optional": [...]}
        """
        detected = self.game.detect_required_dlcs(mod_data)
        required: List[str] = []
        optional: List[str] = []
        text = ((mod_data.get("description_clean") or mod_data.get("description") or "")
                .lower())
        for app_id in detected:
            # 描述中含 "requires <dlc>" / "需要 <dlc>" 等强依赖词的算必需
            dlc = self._dlc_map.get(app_id)
            strong_kw = ["requires", "required", "需要", "必需", "依赖"]
            if dlc and any(k in text for k in [dlc.name.lower(), dlc.name_zh]):
                # 提及了 DLC 名，再看有没有强依赖词
                if any(sk in text for sk in strong_kw):
                    required.append(app_id)
                else:
                    optional.append(app_id)
            else:
                optional.append(app_id)
        mod = self.db.get_mod(mod_id)
        if mod:
            self.db.conn.execute(
                "UPDATE mods SET required_dlcs=?, optional_dlcs=? WHERE id=?",
                (_json(required), _json(optional), mod_id))
            self.db.conn.commit()
        return {"required": required, "optional": optional}

    def set_dlc_dependency(self, mod_id: int, required: List[str],
                           optional: List[str]) -> None:
        """手动设置 MOD 的 DLC 依赖（覆盖）"""
        self.db.conn.execute(
            "UPDATE mods SET required_dlcs=?, optional_dlcs=? WHERE id=?",
            (_json(required), _json(optional), mod_id))
        self.db.conn.commit()

    def get_dependencies(self, mod_id: int) -> Dict[str, List[str]]:
        """读取 MOD 的 DLC 依赖"""
        mod = self.db.get_mod(mod_id)
        if not mod:
            return {"required": [], "optional": []}
        return {
            "required": _parse(mod.get("required_dlcs")),
            "optional": _parse(mod.get("optional_dlcs")),
        }

    # ------------------------------------------------------------------
    # 缺失检测
    # ------------------------------------------------------------------

    def check_missing(self, mod_id: int,
                      owned_dlcs: List[str]) -> List[Dict[str, Any]]:
        """检查 MOD 依赖中用户缺失的 DLC。

        Args:
            mod_id: MOD 内部 ID
            owned_dlcs: 用户已拥有的 DLC app_id 列表

        Returns:
            [{"app_id", "name", "name_zh", "required": bool}, ...]
        """
        deps = self.get_dependencies(mod_id)
        missing: List[Dict[str, Any]] = []
        owned = set(owned_dlcs)
        for app_id in deps["required"]:
            if app_id not in owned:
                dlc = self._dlc_map.get(app_id)
                missing.append({
                    "app_id": app_id,
                    "name": dlc.name if dlc else app_id,
                    "name_zh": dlc.name_zh if dlc else app_id,
                    "required": True,
                })
        for app_id in deps["optional"]:
            if app_id not in owned:
                dlc = self._dlc_map.get(app_id)
                missing.append({
                    "app_id": app_id,
                    "name": dlc.name if dlc else app_id,
                    "name_zh": dlc.name_zh if dlc else app_id,
                    "required": False,
                })
        return missing

    # ------------------------------------------------------------------
    # 批量：为整个数据库检测缺失
    # ------------------------------------------------------------------

    def scan_all(self, owned_dlcs: List[str],
                 limit: int = 500) -> List[Dict[str, Any]]:
        """扫描所有 MOD，返回有缺失 DLC 依赖的警告列表"""
        warnings = []
        for mod in self.db.list_mods(limit=limit):
            missing = self.check_missing(mod["id"], owned_dlcs)
            if missing:
                warnings.append({"mod": mod, "missing": missing})
        return warnings

    def close(self):
        self.db.close()


def _json(lst: List[str]) -> str:
    import json
    return json.dumps(lst)


def _parse(s: Optional[str]) -> List[str]:
    import json
    if not s:
        return []
    try:
        return json.loads(s)
    except Exception:
        return []
