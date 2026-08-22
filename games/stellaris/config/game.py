"""Stellaris 游戏配置（第一个完整实现）

覆盖：
- 本地 MOD 目录（Steam 创意工坊 + Paradox 本地 MOD 目录）
- descriptor.mod 解析（Clausewitz 脚本格式）
- DLC 清单（群星官方 DLC，含中文名）
- 从 MOD 描述中检测 DLC 依赖关键词
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List

from core.game_config import DLCInfo, GameConfig, register_game


@register_game
class StellarisConfig(GameConfig):
    game_id = "stellaris"
    game_name = "群星"
    steam_app_id = "281990"

    TAG_ZH = {
        "Graphics": "画面美化", "Gameplay": "玩法内容", "Spaceships": "舰船模型",
        "Overhaul": "全面改造", "Events": "事件剧情", "Technologies": "科技研究",
        "Fixes": "Bug 修复", "Balance": "平衡性", "Galaxy Generation": "星系生成",
        "Species": "种族特质", "Military": "军事战斗", "Buildings": "建筑设施",
        "UI": "界面美化", "Translation": "翻译汉化", "Story": "故事剧情",
    }

    # ------------------------------------------------------------------
    # 本地 MOD 目录
    # ------------------------------------------------------------------

    def local_mod_dirs(self) -> List[str]:
        """群星本地 MOD 目录（按优先级）：
        1. Paradox Launcher 的 mod 目录（Windows）
        2. Steam 创意工坊下载目录
        """
        user_home = os.path.expanduser("~")
        dirs = []
        # Paradox Launcher 统一目录（Windows）
        pdx_mods = os.path.join(user_home, "Documents", "Paradox Interactive",
                                "Stellaris", "mod")
        if os.path.isdir(pdx_mods):
            dirs.append(pdx_mods)
        # Steam 创意工坊
        steam_ws = os.path.join(user_home, "Documents", "Paradox Interactive",
                                "Stellaris", "workshop", "content", "281990")
        if os.path.isdir(steam_ws):
            dirs.append(steam_ws)
        # 常见 Steam 安装路径
        for candidate in [
            r"C:\Program Files (x86)\Steam\steamapps\workshop\content\281990",
            r"D:\Steam\steamapps\workshop\content\281990",
            r"E:\Steam\steamapps\workshop\content\281990",
        ]:
            if os.path.isdir(candidate):
                dirs.append(candidate)
        return dirs

    # ------------------------------------------------------------------
    # descriptor.mod 解析（Clausewitz 脚本）
    # ------------------------------------------------------------------

    def parse_descriptor(self, descriptor_text: str) -> Dict[str, Any]:
        """解析 Clausewitz 脚本格式的 descriptor.mod：
        name="xxx"
        version="3.4.1"
        tags={ "Graphics" "Gameplay" }
        supported_version="3.*"
        remote_file_id="1121692237"
        """
        result: Dict[str, Any] = {}
        # 键值对（name="..." / version="..." / supported_version="..."）
        for m in re.finditer(r'([a-zA-Z_]+)\s*=\s*"([^"]*)"', descriptor_text):
            result[m.group(1)] = m.group(2)
        # tags={ "A" "B" }
        tm = re.search(r'tags\s*=\s*\{([^}]*)\}', descriptor_text)
        if tm:
            result["tags"] = re.findall(r'"([^"]+)"', tm.group(1))
        # dependencies={ "..." } 或 dependencies={ "id" }
        dm = re.search(r'dependencies\s*=\s*\{([^}]*)\}', descriptor_text)
        if dm:
            result["dependencies"] = re.findall(r'"([^"]+)"', dm.group(1))
        return result

    # ------------------------------------------------------------------
    # DLC 清单
    # ------------------------------------------------------------------

    def load_dlcs(self) -> List[DLCInfo]:
        """群星官方 DLC 清单（app_id / 中英文名）"""
        return [
            DLCInfo("281990", "Stellaris", "群星本体", []),
            DLCInfo("281991", "Leviathans Story Pack", "利维坦故事包", []),
            DLCInfo("281992", "Utopia", "乌托邦", ["飞升天赋", "巨型建筑"]),
            DLCInfo("392450", "Synthetic Dawn", "机械黎明", ["机械种族"]),
            DLCInfo("477880", "Apocalypse", "天启", ["泰坦", "巨像", "掠夺者"]),
            DLCInfo("496240", "Distant Stars", "远星", ["L 星门", "独特星系"]),
            DLCInfo("544870", "MegaCorp", "巨型企业", ["巨型企业政体", "生态园都市"]),
            DLCInfo("581980", "Ancient Relics", "远古遗迹", ["考古", "遗珍"]),
            DLCInfo("616200", "Lithoids", "石质种族", ["石质种族"]),
            DLCInfo("675890", "Federations", "联邦", ["起源系统", "联邦", "银河议会"]),
            DLCInfo("700250", "Necroids", "亡灵种族", ["亡灵种族"]),
            DLCInfo("701010", "Nemesis", "复仇女神", ["天灾机制", "间谍"]),
            DLCInfo("716150", "Aquatics", "水生种族", ["水生种族"]),
            DLCInfo("1238430", "Overlord", "霸主", ["附庸契约", "轨道环"]),
            DLCInfo("1891030", "Toxoids", "毒物种族", ["毒物种族"]),
            DLCInfo("2121800", "First Contact", "首次接触", ["首次接触机制"]),
            DLCInfo("2277550", "Galactic Paragons", "银河典范", ["领袖特质"]),
            DLCInfo("2316221", "Astral Planes", "星界领域", ["星界裂缝"]),
            DLCInfo("2316220", "Machine Age", "机械时代", ["虚拟/模组化进化"]),
            DLCInfo("3163400", "Cosmogenesis", "宇宙发生论", ["后期巨构"]),
        ]

    # ------------------------------------------------------------------
    # DLC 依赖检测
    # ------------------------------------------------------------------

    def detect_required_dlcs(self, mod: Dict[str, Any]) -> List[str]:
        """从 MOD 描述文本中检测 DLC 依赖。

        策略：扫描描述中的 DLC 关键词（中英文），命中即标记为依赖。
        这是启发式检测，返回 app_id 列表。
        """
        text = (mod.get("description_clean") or mod.get("description") or "")
        text_lower = text.lower()
        detected: List[str] = []
        # 关键词 -> (app_id, 是否必需)
        keywords = [
            ("utopia", "281992"), ("乌托邦", "281992"),
            ("synthetic dawn", "392450"), ("机械黎明", "392450"),
            ("apocalypse", "477880"), ("天启", "477880"),
            ("megacorp", "544870"), ("巨型企业", "544870"),
            ("ancient relics", "581980"), ("远古遗迹", "581980"),
            ("federations", "675890"), ("联邦", "675890"),
            ("nemesis", "701010"), ("复仇女神", "701010"),
            ("overlord", "1238430"), ("霸主", "1238430"),
            ("aquatics", "716150"), ("水生种族", "716150"),
            ("first contact", "2121800"), ("首次接触", "2121800"),
            ("machine age", "2316220"), ("机械时代", "2316220"),
            ("astral planes", "2316221"), ("星界领域", "2316221"),
        ]
        for kw, app_id in keywords:
            if kw.lower() in text_lower:
                detected.append(app_id)
        # 去重保序
        return list(dict.fromkeys(detected))


# 便于其他模块 import
def get_config(base_dir: str) -> StellarisConfig:
    return StellarisConfig(base_dir)
