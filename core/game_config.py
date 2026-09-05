"""核心层：游戏配置抽象（游戏无关）

GameConfig 是每个 Paradox 游戏配置的基类。新增游戏只需：
1. 在 games/<game>/config/game.py 中继承 GameConfig 并实现抽象方法
2. 注册到 GAME_REGISTRY

所有功能模块（dlc_checker / local_scanner / updater 等）只依赖此抽象，
不感知具体游戏差异，从而实现「一套核心，多游戏扩展」。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 基础数据结构
# ---------------------------------------------------------------------------


@dataclass
class DLCInfo:
    """单个 DLC 信息"""
    app_id: str            # Steam App ID，如 281990
    name: str              # DLC 名称（英文）
    name_zh: str           # DLC 中文名
    required_for: List[str] = field(default_factory=list)  # 依赖此 DLC 的常见功能


@dataclass
class LocalModInfo:
    """本地已安装 MOD 信息"""
    name: str
    display_name: str      # 显示名（游戏内）
    version: str
    path: str              # 绝对路径
    source: str            # steam / local / paradox_mods
    steam_id: Optional[str] = None  # Steam 创意工坊 ID（若来自工坊）
    tags: List[str] = field(default_factory=list)
    required_dlcs: List[str] = field(default_factory=list)
    remote_id: Optional[int] = None  # Paradox Mods 平台 ID
    size_mb: float = 0.0   # 目录大小（MB）


# ---------------------------------------------------------------------------
# 游戏配置抽象基类
# ---------------------------------------------------------------------------


class GameConfig:
    """Paradox 游戏配置基类。

    子类必须实现：
    - game_id: 唯一标识（stellaris / ck3 / hoi4 ...）
    - game_name: 游戏显示名
    - steam_app_id: Steam App ID
    - local_mod_dirs(): 本地 MOD 目录列表
    - parse_descriptor(): 解析 MOD 描述文件（.mod / descriptor.mod）
    - load_dlcs(): 加载 DLC 清单
    """

    game_id: str = "abstract"
    game_name: str = "Abstract Game"
    steam_app_id: str = ""
    data_dir: str = ""          # data/<game_id>

    # 标签英文 -> 中文映射（展示用）
    TAG_ZH: Dict[str, str] = {}

    def __init__(self, base_dir: str):
        """base_dir: 项目根目录"""
        self.base_dir = base_dir
        self.data_dir = os.path.join(base_dir, "data", self.game_id)
        os.makedirs(self.data_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 抽象方法（子类实现）
    # ------------------------------------------------------------------

    def local_mod_dirs(self) -> List[str]:
        """返回本地 MOD 可能存在的目录列表（按优先级排序）"""
        raise NotImplementedError

    def parse_descriptor(self, descriptor_text: str) -> Dict[str, Any]:
        """解析 MOD 描述文件内容，返回结构化字典"""
        raise NotImplementedError

    def load_dlcs(self) -> List[DLCInfo]:
        """加载游戏 DLC 清单（从 data/<game>/dlc.json）"""
        raise NotImplementedError

    def detect_required_dlcs(self, mod: Dict[str, Any]) -> List[str]:
        """从 MOD 元数据/描述中检测其依赖的 DLC（返回 DLC app_id 列表）"""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # 通用方法（基类提供）
    # ------------------------------------------------------------------

    @property
    def db_path(self) -> str:
        """MOD 主库路径（游戏隔离）"""
        return os.path.join(self.data_dir, "mods.db")

    @property
    def local_db_path(self) -> str:
        """本地已安装 MOD 库路径"""
        return os.path.join(self.data_dir, "local.db")

    @property
    def dlc_path(self) -> str:
        return os.path.join(self.data_dir, "dlc.json")

    @property
    def localization_path(self) -> str:
        return os.path.join(self.data_dir, "localization.json")

    @property
    def community_path(self) -> str:
        return os.path.join(self.data_dir, "community.json")

    def tag_zh(self, tag: str) -> str:
        """标签英文转中文"""
        return self.TAG_ZH.get(tag, tag)

    def ensure_dirs(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)

    def save_json(self, filename: str, data: Any) -> None:
        """保存 JSON 到 data/<game>/<filename>"""
        path = Path(self.data_dir, filename)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_json(self, filename: str, default: Any = None) -> Any:
        """从 data/<game>/<filename> 读取 JSON"""
        path = os.path.join(self.data_dir, filename)
        if not os.path.exists(path):
            return default
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def __repr__(self) -> str:
        return f"<GameConfig {self.game_id}: {self.game_name}>"


# ---------------------------------------------------------------------------
# 游戏注册表
# ---------------------------------------------------------------------------

GAME_REGISTRY: Dict[str, GameConfig] = {}


def register_game(config_cls):
    """类装饰器：注册游戏配置"""
    GAME_REGISTRY[config_cls.game_id] = config_cls
    return config_cls


def get_game(game_id: str, base_dir: str) -> GameConfig:
    """获取游戏配置实例"""
    if game_id not in GAME_REGISTRY:
        raise KeyError(f"未注册的游戏: {game_id}，可用: {list(GAME_REGISTRY)}")
    return GAME_REGISTRY[game_id](base_dir)


def list_games() -> List[str]:
    """列出所有已注册游戏"""
    return sorted(GAME_REGISTRY)
