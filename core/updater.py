"""功能模块：数据自动更新

职责：
1. 定时更新 MOD 数据（Steam API 增量同步订阅量/更新时间）
2. 更新汉化包信息、社区口碑缓存
3. 支持手动触发 / 定时触发 / 增量更新
4. 更新状态记录（供界面展示）

实现策略：
- 增量更新：只更新 time_updated 或 fetched_at 超过阈值的 MOD
- 全量更新：重建整个游戏知识库
- 更新状态持久化在 data/<game>/update_state.json
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class DataUpdater:
    """数据更新器"""

    def __init__(self, game, db, state_file: Optional[str] = None):
        """
        Args:
            game: GameConfig 实例
            db: ModDB 实例
            state_file: 状态文件路径（默认 data/<game>/update_state.json）
        """
        self.game = game
        self.db = db
        self.state_file = state_file or os.path.join(game.data_dir, "update_state.json")
        self.state = self._load_state()
        # 任务注册表
        self._tasks: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 状态管理
    # ------------------------------------------------------------------

    def _load_state(self) -> Dict[str, Any]:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"last_full_update": None, "last_incremental": None, "history": []}

    def _save_state(self):
        os.makedirs(self.game.data_dir, exist_ok=True)
        Path(self.state_file).write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # 任务注册
    # ------------------------------------------------------------------

    def register_task(self, name: str, fn: Callable, schedule_hours: int = 24,
                      kind: str = "incremental"):
        """注册更新任务：
        - name: 任务名
        - fn: 执行函数，返回 {updated: n, ...}
        - schedule_hours: 距上次执行多少小时后才需要跑
        - kind: incremental / full
        """
        self._tasks.append({
            "name": name, "fn": fn, "schedule_hours": schedule_hours, "kind": kind,
        })

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    def run(self, force: bool = False, verbose: bool = False) -> List[Dict]:
        """执行所有到期的更新任务。force=True 时忽略计划时间全部执行。"""
        results = []
        now = time.time()
        for task in self._tasks:
            last = self.state.get(f"last_{task['name']}")
            due = (last is None) or (now - last >= task["schedule_hours"] * 3600)
            if force or due:
                if verbose:
                    print(f"  更新任务: {task['name']}")
                try:
                    result = task["fn"]()
                    self.state[f"last_{task['name']}"] = now
                    self.state.setdefault("history", []).append({
                        "task": task["name"], "time": time.strftime("%Y-%m-%d %H:%M"),
                        "result": result,
                    })
                    self.state["history"] = self.state["history"][-50:]
                    results.append({"task": task["name"], "ok": True, "result": result})
                except Exception as e:
                    results.append({"task": task["name"], "ok": False, "error": str(e)})
        self._save_state()
        return results

    # ------------------------------------------------------------------
    # 增量 / 全量
    # ------------------------------------------------------------------

    def incremental_sync(self, fetch_fn: Callable[[str], Dict[str, Any]],
                         stale_days: int = 1, verbose: bool = False) -> int:
        """增量同步：只更新近期有变化的 MOD。

        Args:
            fetch_fn: 给定 steam_id 返回最新数据的函数
            stale_days: 超过 N 天未抓取的视为需要刷新
        """
        import datetime
        cutoff = datetime.date.today() - datetime.timedelta(days=stale_days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        mods = self.db.list_mods(limit=2000)
        updated = 0
        for mod in mods:
            fetched = mod.get("fetched_at") or ""
            if fetched >= cutoff_str:
                continue  # 新鲜数据跳过
            steam_id = mod.get("steam_id")
            if not steam_id:
                continue
            try:
                fresh = fetch_fn(steam_id)
                if fresh:
                    merged = {**mod, **fresh}
                    self.db.upsert_mod(merged)
                    updated += 1
                    if verbose:
                        print(f"  更新 {mod['title_en'][:30]} ({steam_id})")
            except Exception:
                continue
        self.state["last_incremental"] = time.time()
        self._save_state()
        return updated

    def full_rebuild(self, build_fn: Callable[[], int], verbose: bool = False) -> int:
        """全量重建：清空并重建 MOD 库。

        build_fn 应返回重建的 MOD 数量。
        """
        # 备份旧库
        db_path = self.game.db_path
        if os.path.exists(db_path):
            backup = db_path + f".bak.{int(time.time())}"
            os.replace(db_path, backup)
            if verbose:
                print(f"  已备份旧库 -> {backup}")
        count = build_fn()
        self.state["last_full_update"] = time.time()
        self._save_state()
        return count

    def status(self) -> Dict[str, Any]:
        """当前更新状态"""
        return {
            "last_full_update": self.state.get("last_full_update"),
            "last_incremental": self.state.get("last_incremental"),
            "history": self.state.get("history", [])[-5:],
            "tasks": [t["name"] for t in self._tasks],
        }
