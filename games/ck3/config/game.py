"""Crusader Kings III 游戏配置（框架就绪）

CK3 与群星的区别：
- MOD 描述文件是 descriptor.mod（同样的 Clausewitz 格式，但字段略有不同）
- 本地 MOD 在 Paradox Launcher 统一管理（Documents/Paradox Interactive/Crusader Kings III/mod）
- DLC 列表不同
- 无 Steam 创意工坊标签体系（CK3 使用 Paradox Mods 平台，也有 Steam 创意工坊）
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List

from core.game_config import DLCInfo, GameConfig, register_game


@register_game
class CK3Config(GameConfig):
    game_id = "ck3"
    game_name = "十字军之王 3"
    steam_app_id = "1158310"

    TAG_ZH = {
        "Graphics": "画面美化", "Gameplay": "玩法内容", "Portraits": "肖像",
        "Events": "事件", "Cultures": "文化", "Religion": "宗教",
        "Dynasty": "家族", "Succession": "继承", "Balance": "平衡性",
        "UI": "界面", "Translation": "翻译汉化", "Performance": "性能",
    }

    def local_mod_dirs(self) -> List[str]:
        user_home = os.path.expanduser("~")
        dirs = []
        pdx_mods = os.path.join(user_home, "Documents", "Paradox Interactive",
                                "Crusader Kings III", "mod")
        if os.path.isdir(pdx_mods):
            dirs.append(pdx_mods)
        steam_ws = os.path.join(user_home, "Documents", "Paradox Interactive",
                                "Crusader Kings III", "workshop", "content", "1158310")
        if os.path.isdir(steam_ws):
            dirs.append(steam_ws)
        for candidate in [
            r"C:\Program Files (x86)\Steam\steamapps\workshop\content\1158310",
        ]:
            if os.path.isdir(candidate):
                dirs.append(candidate)
        return dirs

    def parse_descriptor(self, descriptor_text: str) -> Dict[str, Any]:
        """CK3 descriptor.mod：name/version/tags/replace_path/supported_version 等"""
        result: Dict[str, Any] = {}
        for m in re.finditer(r'([a-zA-Z_]+)\s*=\s*"([^"]*)"', descriptor_text):
            result[m.group(1)] = m.group(2)
        tm = re.search(r'tags\s*=\s*\{([^}]*)\}', descriptor_text)
        if tm:
            result["tags"] = re.findall(r'"([^"]+)"', tm.group(1))
        return result

    def load_dlcs(self) -> List[DLCInfo]:
        """CK3 官方 DLC（节选）"""
        return [
            DLCInfo("1158310", "Crusader Kings III", "十字军之王 3 本体", []),
            DLCInfo("1158330", "Royal Court", "皇家宫廷", []),
            DLCInfo("1158331", "Northern Lords", "北方领主", []),
            DLCInfo("1158332", "Fate of Iberia", "伊比利亚的命运", []),
            DLCInfo("1891033", "Friends & Foes", "朋友与敌人", []),
            DLCInfo("2192860", "Tours & Tournaments", "巡游与比武大会", []),
            DLCInfo("2192861", "Wards & Wardens", "被监护人与监护人", []),
            DLCInfo("2192862", "Legacy of Persia", "波斯的遗产", []),
            DLCInfo("2415840", "Legends of the Dead", "亡者传说", []),
            DLCInfo("2415841", "Roads to Power", "权力之路", []),
            DLCInfo("2415842", "Wandering Nobles", "流浪贵族", []),
            DLCInfo("2415843", "Land of the Rus", "罗斯之地", []),
        ]

    def detect_required_dlcs(self, mod: Dict[str, Any]) -> List[str]:
        text = (mod.get("description_clean") or mod.get("description") or "").lower()
        detected: List[str] = []
        keywords = [
            ("royal court", "1158330"), ("皇家宫廷", "1158330"),
            ("northern lords", "1158331"), ("北方领主", "1158331"),
            ("tours & tournaments", "2192860"), ("巡游", "2192860"),
            ("legacy of persia", "2192862"), ("波斯的遗产", "2192862"),
            ("roads to power", "2415841"), ("权力之路", "2415841"),
        ]
        for kw, app_id in keywords:
            if kw.lower() in text:
                detected.append(app_id)
        return list(dict.fromkeys(detected))
