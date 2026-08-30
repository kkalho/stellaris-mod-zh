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
        # 核心分类（高频，Top 14 全覆盖）
        "Gameplay": "玩法内容", "Graphics": "画面美化", "Events": "事件剧情",
        "Spaceships": "舰船模型", "Overhaul": "全面改造", "Technologies": "科技研究",
        "Species": "种族特质", "Fixes": "Bug 修复", "Military": "军事战斗",
        "Balance": "平衡性", "Economy": "经济系统", "Buildings": "建筑设施",
        "Galaxy Generation": "星系生成", "Leaders": "领袖角色",
        # 次要分类
        "UI": "界面美化", "Translation": "翻译汉化", "Story": "故事剧情",
        "Sound": "音效音乐", "Music": "音乐", "Diplomacy": "外交系统",
        "Utilities": "实用组件", "Ships": "舰船", "Ship Set": "船模包",
        "Shipset": "船模包", "Shipsets": "船模包", "Total Conversion": "全面转换",
        "Interface": "界面", "Loading Screen": "载入画面", "Font": "字体",
        "Compatibility": "兼容性", "Empire": "帝国", "Origins": "起源",
        "Crisis": "天灾", "AI": "AI 智能", "Mod Menu": "MOD 菜单",
        "Option": "选项", "Modifiers": "修正", "Flags": "旗帜",
        "Megastructure": "巨型建筑", "Megastructures": "巨型建筑",
        "Starbase": "恒星基地", "Starbases": "恒星基地",
        "Names": "命名", "Namelists": "命名表", "Variety": "多样化",
        "Flavor": "风味", "Anime": "动漫", "Space Battles": "太空战斗",
        "Anomalies": "异常", "Anomaly": "异常", "Civics": "政体", "Civic": "政体",
        "Traits": "特质", "Traditions": "传统",
        "Planets": "星球", "Fallen Empire": "堕落帝国", "Guardians": "守护者",
        "Leviathans": "利维坦", "Marauders": "掠夺者", "Federations": "联邦",
        # 主题标签
        "Star Wars": "星球大战", "Star Trek": "星际迷航", "Warhammer": "战锤",
        "WH40k": "战锤40K", "40k": "战锤40K", "Halo": "光环",
        "Mass Effect": "质量效应", "Real Space": "真实星空",
        "Galactic Empire": "银河帝国", "Clone Wars": "克隆人战争",
        "Rebel Alliance": "义军同盟", "Sith": "西斯", "Republic": "共和国",
        "Stargate": "星门", "Eve": "EVE", "Elite Dangerous": "精英危险",
        "KOTOR": "旧共和国武士", "SWTOR": "旧共和国", "Magic the Gathering": "万智牌",
        "MtG": "万智牌", "TouhouProject": "东方", "Celtic": "凯尔特",
        "Greek": "希腊", "Rome": "罗马", "roman": "罗马", "SPQR": "罗马",
        "Egyptian": "埃及", "Tocharians": "吐火罗", "Athens": "雅典",
        "Mandalorian": "曼达洛人", "Drow": "卓尔", "Dark Elf": "暗精灵",
        "Elven": "精灵", "Elves": "精灵", "Human": "人类", "Humanoid": "人形",
        "Machine": "机械", "Psionic": "灵能", "Nanites": "纳米",
        "Arthropoid": "节肢", "Mammalian": "哺乳", "Molluscoid": "软体",
        "Plantoid": "植物", "Reptilian": "爬行",
        "Binary": "联星", "Stars": "恒星", "Camera": "视角",
        "Customization": "自定义", "Development": "开发", "Pirates": "海盗",
        "War": "战争", "Combat": "战斗", "Homeworld": "家园星系",
        "Nomads": "游牧", "L-Cluster": "L 星团", "L-Gates": "L 门",
        "Gray Tempest": "灰风暴", "Horizonsignal": "地平线信号",
        "ISB": "ISB", "ISBS": "ISBS", "NSC": "NSC", "NSC2": "NSC2",
        "NSC3": "NSC3", "ACOT": "ACOT", "ZoFE": "堕落帝国之巅",
        "Kurogane": "黑钢", "Silfae": "Silfae", "Improved Space Battles": "太空战斗改进",
        "Merged": "合集", "Backgrounds": "背景", "Emblems": "徽章",
        "Icons": "图标", "Battlestar": "战斗星舰", "Combine": "联合军",
        "Scrin": "思金", "Tiberium": "泰伯利亚", "C&C": "命令与征服",
        "half-life": "半条命", "CoFH": "CoFH", "PR": "公关", "PSE": "PSE",
        "RLS": "RLS", "QUENTOPOLIS": "昆特城", "Stellar Expansion": "群星扩展",
        "Stellaris: Utopia": "乌托邦 DLC", "Red Rising": "红色崛起",
        "Old Republic": "旧共和国", "Sith Empire": "西斯帝国",
        "Starfleet": "星联舰队", "Klingon": "克林贡", "Romulan": "罗慕伦",
        "Cardassian": "卡达西", "Borg": "博格", "Forerunner": "先行者",
        "Sentinel": "哨兵", "Promethean": "普罗米修斯", "AI Personalities": "AI 人格",
        "Aliens": "外星人", "AnimationGirls": "动漫少女", "Bundeswehr": "联邦国防军",
        "Deutsch": "德语", "german": "德语", "cybrxkhan": "cybrxkhan",
        "jasonpepe": "jasonpepe", "Mod Pharaoh": "MOD 法老",
        "Get your 6-6-6-6 Admiral today!": "6-6-6-6 上将",
        "Exploit your capitalism empire": "资本主义帝国",
        "Suffer not the alien to live": "灭绝异形",
        "The CIA created the Prethoryn": "CIA 制造了虫群",
        "The Death Star was an inside job.": "死星是内鬼干的",
        "The Unbidden was an inside job": "虚空之敌是内鬼",
        "Crush the Rebellion. Destroy their dream.": "粉碎义军",
        "You have to rename your prison planets Australia": "监狱星球改叫澳大利亚",
        "Don't comment before read!!!": "先读描述再评论",
        "Read description first": "先读描述",
        "I'm a tag": "标签",
        "Stolen from EU4": "取自 EU4",
        "ZroCola(TM)": "Zro 可乐",
        # 补漏（单复数变体/常见）
        "Origin": "起源", "Spaceship": "舰船", "Name lists": "命名表",
        "Techology": "科技", "Galaxy Generaion": "星系生成",
        "Rebel": "义军", "OST": "原声", "LCARS": "LCARS 界面",
        "Imperium of Man": "人类帝国", "Human Fallen Empires": "人类堕落帝国",
        "Economy Categories Only": "纯经济分类", "random AI": "随机 AI",
        "4-in-1": "四合一套装", "A Galaxy Divided": "分裂的银河",
        "star": "恒星", "!-Starbase - Extended-!": "星垒扩展",
        "!-Starbase - Extended-! 2.0": "星垒扩展 2.0",
        # 版本标签
        "3.*": "适配 3.x", "3.0.*": "适配 3.0", "3.14": "适配 3.14",
        "3.14.*": "适配 3.14", "4.2.*": "适配 4.2", "4.4.*": "适配 4.4",
    }

    # 版本代号（官方版本名，中文；前端版本筛选展示用。仅列已核实的）
    VERSION_NAMES = {
        "4.4": "飞马",      # Pegasus, 2026-06-15
        "4.3": "鲸鱼座",    # Cetus, 2026-03-12
        "4.2": "乌鸦座",    # Corvus, 2025-12-10
        "4.1": "天琴座",    # Lyra, 2025-09-22
        "4.0": "凤凰",      # Phoenix, 2025-05-05
        "3.14": "圆规座",   # Circinus, 2024-10-29
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
