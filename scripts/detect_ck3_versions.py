"""CK3 MOD 版本兼容标注脚本

双轨检测（与 detect_stellaris_versions.py 同构）：
1. 显式声明：描述/标签中的 "for 1.16" / "1.15 compatible" 等
2. 参考推断：无声明时用 time_updated 反推"最近更新于哪个版本时期"

版本时间线（官方 Wiki 核实，2026-08-30）：
  1.13 Basileus   2024-09-24 (Roads to Power)
  1.14 Traverse   2024-11-04 (Wandering Nobles)
  1.15 Crown      2025-03-12 (Crowns of the World)
  1.16 Chamfron   2025-04-08 (Khans of the Steppe)
  1.17 Ascendant  2025-09-09 (Coronations)
  1.18 Crane      2025-10-28 (All Under Heaven)
  1.19 Scribe     2026-04-20 (Symbols of Authority，现役)
  更早更新的统一标注为「更新于 1.12 及更早」

用法：python scripts/detect_ck3_versions.py
"""
import os
import re
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DB = os.path.join(os.path.dirname(__file__), "..", "data", "ck3", "mods.db")

# 显式版本声明 → 标准化版本
VERSION_PATTERNS = [
    (r"\b1\.19(\.\d+)*\b", "1.19"), (r"\b1\.18(\.\d+)*\b", "1.18"),
    (r"\b1\.17(\.\d+)*\b", "1.17"), (r"\b1\.16(\.\d+)*\b", "1.16"),
    (r"\b1\.15(\.\d+)*\b", "1.15"), (r"\b1\.14(\.\d+)*\b", "1.14"),
    (r"\b1\.13(\.\d+)*\b", "1.13"), (r"\b1\.12(\.\d+)*\b", "1.12"),
    (r"\b1\.11(\.\d+)*\b", "1.11"), (r"\b1\.10(\.\d+)*\b", "1.10"),
    (r"\b1\.9(\.\d+)*\b", "1.9"),
]

# 版本发布时间线（推断用；仅收录 Wiki 核实过的日期）
VERSION_RELEASE = [
    ("1.19", datetime(2026, 4, 20).timestamp()),
    ("1.18", datetime(2025, 10, 28).timestamp()),
    ("1.17", datetime(2025, 9, 9).timestamp()),
    ("1.16", datetime(2025, 4, 8).timestamp()),
    ("1.15", datetime(2025, 3, 12).timestamp()),
    ("1.14", datetime(2024, 11, 4).timestamp()),
    ("1.13", datetime(2024, 9, 24).timestamp()),
]
FALLBACK = "1.12 及更早"


def _ver_key(v):
    major, minor = v.split(".")
    return (int(major), int(minor))


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
    return max(found, key=_ver_key)


def infer_from_time(time_updated):
    """根据更新时间反推版本时期（早于 1.13 归入「1.12 及更早」）"""
    if not time_updated:
        return None
    for ver, ts in VERSION_RELEASE:
        if time_updated >= ts:
            return ver
    return FALLBACK


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

    print("\n抽查（显式声明）:")
    for r in cur.execute(
        "SELECT title, version FROM mods WHERE version LIKE '适配%' "
        "ORDER BY subscriptions DESC LIMIT 5"
    ).fetchall():
        print(f"  {(r['title'] or '')[:40]:<42} → {r['version']}")
    print("\n抽查（时间推断）:")
    for r in cur.execute(
        "SELECT title, version FROM mods WHERE version LIKE '更新于%' "
        "ORDER BY subscriptions DESC LIMIT 5"
    ).fetchall():
        print(f"  {(r['title'] or '')[:40]:<42} → {r['version']}")

    conn.close()


if __name__ == "__main__":
    main()
