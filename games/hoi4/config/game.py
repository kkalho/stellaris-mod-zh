"""Hearts of Iron IV 游戏配置（框架就绪）

HOI4 特点：
- 本地 MOD 目录：Documents/Paradox Interactive/Hearts of Iron IV/mod
- 支持 Steam 创意工坊（app_id 394360）
- 描述文件同样是 Clausewitz 格式，但依赖标签是 dependencies={ "xxx" }
- DLC 依赖常见：Together for Victory / Waking the Tiger / Man the Guns 等
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List

from core.game_config import DLCInfo, GameConfig, register_game


@register_game
class HOI4Config(GameConfig):
    game_id = "hoi4"
    game_name = "钢铁雄心 4"
    steam_app_id = "394360"

    TAG_ZH = {
        "Graphics": "画面美化", "Gameplay": "玩法内容", "National Focus": "国策",
        "Events": "事件", "Map": "地图", "Units": "单位",
        "Sound": "音效", "UI": "界面", "Translation": "翻译汉化",
        "Historical": "历史", "Alternative History": "架空历史",
    }

    def local_mod_dirs(self) -> List[str]:
        user_home = os.path.expanduser("~")
        dirs = []
        pdx_mods = os.path.join(user_home, "Documents", "Paradox Interactive",
                                "Hearts of Iron IV", "mod")
        if os.path.isdir(pdx_mods):
            dirs.append(pdx_mods)
        steam_ws = os.path.join(user_home, "Documents", "Paradox Interactive",
                                "Hearts of Iron IV", "workshop", "content", "394360")
        if os.path.isdir(steam_ws):
            dirs.append(steam_ws)
        for candidate in [
            r"C:\Program Files (x86)\Steam\steamapps\workshop\content\394360",
        ]:
            if os.path.isdir(candidate):
                dirs.append(candidate)
        return dirs

    def parse_descriptor(self, descriptor_text: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for m in re.finditer(r'([a-zA-Z_]+)\s*=\s*"([^"]*)"', descriptor_text):
            result[m.group(1)] = m.group(2)
        tm = re.search(r'tags\s*=\s*\{([^}]*)\}', descriptor_text)
        if tm:
            result["tags"] = re.findall(r'"([^"]+)"', tm.group(1))
        dm = re.search(r'dependencies\s*=\s*\{([^}]*)\}', descriptor_text)
        if dm:
            result["dependencies"] = re.findall(r'"([^"]+)"', dm.group(1))
        return result

    def load_dlcs(self) -> List[DLCInfo]:
        """HOI4 官方 DLC（节选）"""
        return [
            DLCInfo("394360", "Hearts of Iron IV", "钢铁雄心 4 本体", []),
            DLCInfo("394361", "Together for Victory", "为胜利团结", []),
            DLCInfo("394362", "Death or Dishonor", "死或辱", []),
            DLCInfo("537880", "Waking the Tiger", "唤醒猛虎", []),
            DLCInfo("702030", "Man the Guns", "炮手就位", []),
            DLCInfo("841680", "La Résistance", "抵抗运动", []),
            DLCInfo("1146830", "Battle for the Bosporus", "博斯普鲁斯之战", []),
            DLCInfo("1288181", "No Step Back", "绝不后退", []),
            DLCInfo("1455210", "By Blood Alone", "仅凭血统", []),
            DLCInfo("1615730", "Arms Against Tyranny", "反抗暴政之臂", []),
            DLCInfo("1864750", "Trial of Allegiance", "忠诚的考验", []),
            DLCInfo("1864751", "Götterdämmerung", "诸神黄昏", []),
        ]

    def detect_required_dlcs(self, mod: Dict[str, Any]) -> List[str]:
        text = (mod.get("description_clean") or mod.get("description") or "").lower()
        detected: List[str] = []
        keywords = [
            ("together for victory", "394361"), ("为胜利团结", "394361"),
            ("waking the tiger", "537880"), ("唤醒猛虎", "537880"),
            ("man the guns", "702030"), ("炮手就位", "702030"),
            ("la résistance", "841680"), ("抵抗运动", "841680"),
            ("no step back", "1288181"), ("绝不后退", "1288181"),
        ]
        for kw, app_id in keywords:
            if kw.lower() in text:
                detected.append(app_id)
        return list(dict.fromkeys(detected))
