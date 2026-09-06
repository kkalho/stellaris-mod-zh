"""串扰自动检测：跨 MOD 字段完全重复 = 历史串扰的直接症状

已知串扰模式是 A 的 gameplay/features 被整体复制到 B（wave6-8 修复的 14 处大多如此）。
本脚本检测三类**精确重复**（跨不同 steam_id）：
  1. features_zh 列表完全相同
  2. gameplay_zh 全文相同（≥50 字，排除「无介绍」类占位）
  3. summary_zh 相同（≥10 字）
语义级串扰（内容独特但张冠李戴，如 wave7 的 Real Space 条）检不出——那类靠任务包
子智能体上报 + 邻条 features 相同预扫，本脚本是第三道网。

用法:
    python scripts/detect_crosstalk.py                 # 全库（体检用）
    python scripts/detect_crosstalk.py --files a.json  # 波次分片/合并件（run_wave merge 阶段接入）
退出码: 0 = 无重复；1 = 有重复（merge 阶段应处理后再导入）
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

# 全库已知合法重复（同作者系列共用文案/模板简介，2026-09-06 维护轮 19 人工核实）
KNOWN_LEGIT = {
    frozenset({"2938897848", "2932557948", "2930813098"}),  # 无尽空间2 舰船系列
    frozenset({"2851692297", "2833499231"}),                # 星际迷航 舰船系列
    frozenset({"1609801017", "1653043481", "1613766846"}),  # 同作者同简介系列
    frozenset({"2466511041", "2458655721", "2783854641"}),  # 传统槽系列（15+16/63+64/23+24）
}


def _is_known_legit(sids: list[str]) -> bool:
    s = set(sids)
    return any(s == k or s <= k for k in KNOWN_LEGIT)


def dup_groups(pairs: list[tuple[str, str]], min_len: int) -> list[tuple[str, list[str]]]:
    """pairs = [(steam_id, 文本)] → 返回出现 ≥2 次的文本及其 sid 列表。"""
    seen: dict[str, list[str]] = {}
    for sid, text in pairs:
        t = (text or "").strip()
        if len(t) >= min_len:
            seen.setdefault(t, []).append(sid)
    return [(t, sids) for t, sids in seen.items() if len(sids) > 1]


def scan(rows: dict[str, dict[str, str]]) -> list[str]:
    problems = []
    feats: dict[str, list[str]] = {}
    for sid, f in rows.items():
        try:
            fl = json.loads(f.get("features") or "[]")
        except ValueError:
            continue
        if isinstance(fl, list) and fl:
            feats.setdefault(json.dumps(fl, ensure_ascii=False), []).append(sid)
    for key, sids in feats.items():
        if len(sids) > 1:
            problems.append(f"features 完全相同 ×{len(sids)}: {sids[:6]} → {key[:80]}")
    for field, minlen, label in (("gameplay", 50, "gameplay 全文"), ("summary", 10, "summary")):
        groups = dup_groups([(sid, f.get(field, "")) for sid, f in rows.items()], minlen)
        for _, sids in groups:
            problems.append(f"{label}完全相同 ×{len(sids)}: {sids[:6]}")
    return problems


def main():
    args = sys.argv[1:]
    if "--files" in args:
        rows: dict[str, dict[str, str]] = {}
        for p in args[1:]:
            for t in json.loads(Path(p).read_text(encoding="utf-8")).get("translations", []):
                sid = str(t["steam_id"])
                rows[sid] = {
                    "features": json.dumps(t["features_zh"], ensure_ascii=False) if isinstance(t.get("features_zh"), list) else "",
                    "gameplay": t.get("gameplay_zh", ""), "summary": t.get("summary_zh", ""),
                }
        src = f"文件 {len(args[1:])} 个"
    else:
        conn = sqlite3.connect(str(BASE_DIR / "data" / "stellaris" / "mods.db"))
        raw = conn.execute(
            "SELECT m.steam_id, t.field, t.zh_text FROM translations t JOIN mods m ON m.id=t.mod_id "
            "WHERE m.game_id='stellaris' AND t.field IN ('features','gameplay','summary')"
        ).fetchall()
        conn.close()
        rows = {}
        for sid, field, text in raw:
            rows.setdefault(str(sid), {})[field] = text or ""
        src = "全库"
    problems = scan(rows)
    if src.startswith("全库"):
        problems = [x for x in problems
                    if not _is_known_legit(re.findall(r"\d{6,}", x.split(": ", 1)[-1]))]
    print(f"=== 串扰检测（精确重复）：{src}，{len(rows)} 条 ===")
    if not problems:
        print("✅ 无跨 MOD 字段重复")
        return
    for p in problems:
        print(f"  ⚠ {p}")
    print(f"共 {len(problems)} 组重复——波次内命中请先核实是否串扰，全库命中请评估是否历史遗留")
    sys.exit(1)


if __name__ == "__main__":
    main()
