"""功能模块：中文社区口碑

职责：
1. 整合中文 MOD 社区（贴吧 / B站 / NGA / 知乎）的评价信息
2. 为每个 MOD 提供：社区评分、评论摘要、推荐指数
3. 缓存到本地（community 表），支持手动录入与 API 更新

数据流：
    Web 检索/人工整理 → community_rating.set() → community 表 → 界面展示

推荐指数计算（综合）：
    0.4 * 社区评分 + 0.3 * 好评率 + 0.3 * 订阅热度归一化
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.game_config import GameConfig
from core.mod_db import ModDB


class CommunityRating:
    """中文社区口碑聚合器"""

    PLATFORMS = ("tieba", "bilibili", "nga", "zhihu", "steam_zh")

    def __init__(self, game: GameConfig, db: Optional[ModDB] = None):
        self.game = game
        self.db = db or ModDB(game)

    # ------------------------------------------------------------------
    # 数据写入
    # ------------------------------------------------------------------

    def set_rating(self, mod_id: int, platform: str, score: float,
                   comment_summary: str = "", recommend: str = "",
                   source_url: str = "") -> None:
        """设置某平台的口碑数据（覆盖该 MOD 该平台）"""
        if platform not in self.PLATFORMS:
            platform = "steam_zh"
        self.db.set_community(mod_id, {
            "platform": platform,
            "score": max(0, min(10, score)),
            "comment_summary": comment_summary,
            "recommend": recommend,
            "source_url": source_url,
        })

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def get(self, mod_id: int) -> Optional[Dict[str, Any]]:
        return self.db.get_community(mod_id)

    def get_by_steam_id(self, steam_id: str) -> Optional[Dict[str, Any]]:
        mod = self.db.get_mod_by_steam_id(str(steam_id))
        return self.db.get_community(mod["id"]) if mod else None

    # ------------------------------------------------------------------
    # 推荐指数计算
    # ------------------------------------------------------------------

    def recommend_index(self, mod_id: int) -> float:
        """综合推荐指数 0-10

        公式：0.5*社区评分 + 0.2*好评率(0-10) + 0.3*订阅热度(0-10)
        社区评分权重最高（真实口碑），热度只作参考
        """
        mod = self.db.get_mod(mod_id)
        if not mod:
            return 0.0
        community = self.db.get_community(mod_id)
        community_score = (community["score"] if community else 0) or 0
        like_ratio = (mod.get("like_ratio") or 0) * 10  # 0-10 分
        # 订阅热度：>=100万=10分, 对数归一化
        subs = mod.get("subscriptions") or 0
        import math
        heat = min(10.0, math.log10(max(subs, 1)) / 6 * 10)
        idx = 0.5 * community_score + 0.2 * like_ratio + 0.3 * heat
        return round(min(10.0, idx), 1)

    # ------------------------------------------------------------------
    # 批量计算（更新所有 MOD 的 community_score）
    # ------------------------------------------------------------------

    def recompute_all(self) -> int:
        """为所有有口碑数据的 MOD 重算推荐指数"""
        count = 0
        for mod in self.db.list_mods(limit=2000):
            community = self.db.get_community(mod["id"])
            if not community or not community.get("score"):
                continue
            idx = self.recommend_index(mod["id"])
            self.db.conn.execute(
                "UPDATE mods SET community_score=? WHERE id=?",
                (idx, mod["id"]))
            count += 1
        self.db.conn.commit()
        return count

    # ------------------------------------------------------------------
    # 批量导入（从 JSON 文件）
    # ------------------------------------------------------------------

    def import_json(self, data: List[Dict[str, Any]]) -> int:
        """从 JSON 批量导入口碑数据

        data 格式: [{"steam_id", "platform", "score", "comment_summary", ...}]
        """
        count = 0
        for item in data:
            mod = self.db.get_mod_by_steam_id(str(item["steam_id"]))
            if not mod:
                continue
            self.set_rating(
                mod_id=mod["id"],
                platform=item.get("platform", "steam_zh"),
                score=item.get("score", 0),
                comment_summary=item.get("comment_summary", ""),
                recommend=item.get("recommend", ""),
                source_url=item.get("source_url", ""))
            count += 1
        return count
