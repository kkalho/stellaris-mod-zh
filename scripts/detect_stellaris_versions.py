"""群星 MOD 版本兼容标注脚本

双轨检测：
1. 显式声明：描述/标签中的 "For 4.4" / "Compatible with 3.14" 等
2. 参考推断：无声明时用 time_updated 反推"最近更新于哪个版本时期"

版本时间线（官方 Wiki + SteamDB 核实，2026-08）：
  3.14: 2024-10-29 Circinus
  4.0:  2025-05-05 Phoenix
  4.1:  2025-09-22 Lyra
  4.2:  2025-12-10 Corvus
  4.3:  2026-03-12 Cetus
  4.4:  2026-06-15 Pegasus

用法：python scripts/detect_stellaris_versions.py
"""
import os
import re
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DB = os.path.join(os.path.dirname(__file__), "..", "data", "stellaris", "mods.db")

# 显式版本声明 → 标准化版本
VERSION_PATTERNS = [
    (r"\b4\.4\.\d+\b", "4.4"), (r"\b4\.4\b", "4.4"),
    (r"\b4\.3\.\d+\b", "4.3"), (r"\b4\.3\b", "4.3"),
    (r"\b4\.2\.\d+\b", "4.2"), (r"\b4\.2\b", "4.2"),
    (r"\b4\.1\.\d+\b", "4.1"), (r"\b4\.1\b", "4.1"),
    (r"\b4\.0\.\d+\b", "4.0"), (r"\b4\.0\b", "4.0"),
    (r"\b3\.14\.\d+\b", "3.14"), (r"\b3\.14\b", "3.14"),
    (r"\b3\.13\.\d+\b", "3.13"), (r"\b3\.13\b", "3.13"),
    (r"\b3\.12\.\d+\b", "3.12"), (r"\b3\.12\b", "3.12"),
    (r"\b3\.11\.\d+\b", "3.11"), (r"\b3\.11\b", "3.11"),
    (r"\b3\.10\.\d+\b", "3.10"), (r"\b3\.10\b", "3.10"),
    (r"\b3\.9\.\d+\b", "3.9"), (r"\b3\.9\b", "3.9"),
    (r"\b3\.8\.\d+\b", "3.8"), (r"\b3\.8\b", "3.8"),
    (r"\b3\.7\.\d+\b", "3.7"), (r"\b3\.7\b", "3.7"),
    (r"\b3\.6\.\d+\b", "3.6"), (r"\b3\.6\b", "3.6"),
    (r"\b3\.5\.\d+\b", "3.5"), (r"\b3\.5\b", "3.5"),
    (r"\b3\.4\.\d+\b", "3.4"), (r"\b3\.4\b", "3.4"),
    (r"\b3\.3\.\d+\b", "3.3"), (r"\b3\.3\b", "3.3"),
    (r"\b3\.2\.\d+\b", "3.2"), (r"\b3\.2\b", "3.2"),
    (r"\b3\.1\.\d+\b", "3.1"), (r"\b3\.1\b", "3.1"),
    (r"\b3\.0\.\d+\b", "3.0"), (r"\b3\.0\b", "3.0"),
    (r"\b2\.\d\b", "2.x"),
]

# 版本发布时间线（时间戳：官方发布时间 UTC → 秒）
VERSION_RELEASE = [
    ("4.4", datetime(2026, 6, 15).timestamp()),
    ("4.3", datetime(2026, 3, 12).timestamp()),
    ("4.2", datetime(2025, 12, 10).timestamp()),
    ("4.1", datetime(2025, 9, 22).timestamp()),
    ("4.0", datetime(2025, 5, 5).timestamp()),
    ("3.14", datetime(2024, 10, 29).timestamp()),
    ("3.13", datetime(2024, 9, 10).timestamp()),
    ("3.12", datetime(2024, 5, 7).timestamp()),
    ("3.11", datetime(2024, 1, 1).timestamp()),
    ("3.10", datetime(2023, 11, 1).timestamp()),
    ("3.9", datetime(2023, 10, 1).timestamp()),
    ("3.8", datetime(2023, 5, 1).timestamp()),
    ("3.7", datetime(2023, 3, 1).timestamp()),
    ("3.6", datetime(2022, 12, 1).timestamp()),
    ("3.5", datetime(2022, 10, 1).timestamp()),
    ("3.4", datetime(2022, 7, 1).timestamp()),
    ("3.3", datetime(2022, 3, 1).timestamp()),
    ("3.2", datetime(2021, 11, 1).timestamp()),
    ("3.1", datetime(2021, 9, 1).timestamp()),
    ("3.0", datetime(2021, 4, 1).timestamp()),
]

# 显式声明上下文词（避免把"需要 4.0"当成"适配 4.0"的反义情况——这里保守处理，
# 只要描述明确提及版本号就标注为"提及版本"，配合时间推断给出最终结论）
CONTEXT_WORDS = ["for", "compatible", "support", "version", "updated", "适配", "兼容", "支持", "版本"]


def detect_explicit(text):
    """从文本提取显式版本声明，返回最高版本号或 None"""
    if not text:
        return None
    text_lower = text.lower()
    found = []
    for pat, ver in VERSION_PATTERNS:
        if re.search(pat, text_lower):
            found.append(ver)
    if not found:
        return None
    # 取最高版本（数值比较，"2.x" 视为 2.99 兜底）
    def ver_key(v):
        if v == "2.x":
            return (2, 99)
        parts = v.split(".")
        nums = []
        for p in parts[:2]:
            try:
                nums.append(int(p))
            except ValueError:
                nums.append(0)
        return tuple(nums) + (0,) * (2 - len(nums))
    return max(found, key=ver_key)


def infer_from_time(time_updated):
    """根据更新时间反推版本时期"""
    if not time_updated:
        return None
    for ver, ts in VERSION_RELEASE:
        if time_updated >= ts:
            return ver
    return "2.x"


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute(
        "SELECT id, title, description_clean, tags, time_updated FROM mods"
    ).fetchall()

    stats = {"explicit": 0, "inferred": 0, "none": 0}
    for r in rows:
        text = " ".join(filter(None, [r["description_clean"], r["tags"]]))
        explicit = detect_explicit(text)
        inferred = infer_from_time(r["time_updated"])

        if explicit:
            version_compat = f"适配 {explicit}"
            stats["explicit"] += 1
        elif inferred:
            version_compat = f"更新于 {inferred} 时期"
            stats["inferred"] += 1
        else:
            version_compat = ""
            stats["none"] += 1

        cur.execute(
            "UPDATE mods SET version=? WHERE id=?",
            (version_compat, r["id"]),
        )

    conn.commit()

    print(f"标注完成：{len(rows)} 个 MOD")
    print(f"  显式声明: {stats['explicit']} 个（描述/标签明确写版本）")
    print(f"  时间推断: {stats['inferred']} 个（无声明，按最近更新时间）")
    print(f"  无信息:   {stats['none']} 个")

    # 抽查
    print("\n抽查（显式声明）:")
    for r in cur.execute(
        "SELECT title, version FROM mods WHERE version LIKE '适配%' ORDER BY subscriptions DESC LIMIT 5"
    ).fetchall():
        print(f"  {r['title'][:40]:<42} → {r['version']}")
    print("\n抽查（时间推断）:")
    for r in cur.execute(
        "SELECT title, version FROM mods WHERE version LIKE '更新于%' ORDER BY subscriptions DESC LIMIT 5"
    ).fetchall():
        print(f"  {r['title'][:40]:<42} → {r['version']}")

    conn.close()


if __name__ == "__main__":
    main()
