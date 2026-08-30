"""兼容性数据批量挖掘（规则法，确定性，可进 rebuild_all 流水线）

用法:
    python scripts/mine_compat.py [--dry-run]

从 777 个 MOD 的描述（英文 description_clean + 中文翻译）中挖掘四类结构化关系：
  1. conflicts    冲突：incompatible / conflict / 不兼容 / 冲突 / don't use with
  2. requires     依赖前置：requires / needs / 前置 / 需要主模组 / must subscribe
  3. has_patches  补丁：compatibility patch / 兼容补丁 / patch for
  4. notes        继任替代（弃坑条目）：successor / moved to / 已弃坑 / 替代 / 续作

引用解析（两种信号，按精度排序）：
  a. 描述中的 Steam 直链  filedetails/?id=NNN  → 直接解析 steam_id
  b. 句子中出现其他已知 MOD 的规范化标题（英文 ≥8 字符或中文 ≥4 字符）

数据真实原则护栏：
- 引用必须能解析到库内已知 steam_id，否则丢弃
- notes 记录证据句（截断 120 字符），可审计
- 排除自引用；每类关系每 MOD 上限 10 条（噪声护栏）
- 关系写入 compat 表（ON CONFLICT 更新），前端详情页「兼容性」版块自动展示
"""
from __future__ import annotations

import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import games.stellaris.config.game  # noqa: F401
from core.game_config import get_game
from core.mod_db import ModDB

DRY = "--dry-run" in sys.argv

REL_KEYWORDS = {
    "conflicts": [r"incompatible", r"conflict", r"don'?t use .{0,20}with", r"不兼容", r"冲突", r"冲突的"],
    "requires": [r"requires?\b", r"\bneeds?\b", r"prerequisite", r"must (?:subscribe|have|install)",
                 r"require[sd]? .{0,10}(?:main|base) mod", r"前置", r"需要主", r"必须先", r"依赖"],
    "has_patches": [r"compatibility patch", r"patch for", r"兼容补丁", r"平衡补丁"],
    "successor": [r"successor", r"moved to", r"replaced by", r"continuation", r"superseded",
                  r"已弃坑", r"弃坑", r"替代品", r"继任", r"转生", r"移步", r"新版.*链接", r"续作"],
}
REL_RE = {k: [re.compile(p, re.I) for p in v] for k, v in REL_KEYWORDS.items()}

STEAM_LINK = re.compile(r"filedetails/\?id=(\d{6,12})")


def norm_title(t: str) -> str:
    """规范化标题：小写、去版本号/标点/多余空白。中文标题保留原字符。"""
    t = (t or "").lower()
    t = re.sub(r"\d+\.\d+(\.\d+)*", " ", t)              # 版本号
    t = re.sub(r"[^\w\u4e00-\u9fff]+", " ", t)           # 标点→空格
    return re.sub(r"\s+", " ", t).strip()


def detect_relations(sentence: str) -> list:
    return [rel for rel, res in REL_RE.items() if any(r.search(sentence) for r in res)]


def main():
    cfg = get_game("stellaris", BASE_DIR)
    db = ModDB(cfg)
    mods = db.list_mods(limit=5000)
    zh_desc = dict(db.conn.execute(
        "SELECT t.mod_id, t.zh_text FROM translations t "
        "JOIN mods m ON m.id = t.mod_id WHERE m.game_id='stellaris' AND t.field='description'"
    ).fetchall())

    # 标题索引：规范化标题 → steam_id（长标题才入索引，防常见词误配）
    title_index = []
    for m in mods:
        for t in filter(None, [m.get("title_en"), m.get("title")]):
            nt = norm_title(t)
            has_cjk = any("\u4e00" <= c <= "\u9fff" for c in nt)
            if (has_cjk and len(nt) >= 4) or (not has_cjk and len(nt) >= 8):
                title_index.append((nt, m["steam_id"]))

    stats = {"sentences": 0, "refs": 0, "relations": 0}
    found = {}   # (self_sid, other_sid, rel) -> evidence
    for m in mods:
        self_sid = str(m.get("steam_id") or "")
        text = " ".join(filter(None, [m.get("description_clean"), zh_desc.get(m["id"]) or ""]))
        if len(text) < 20:
            continue
        # 句切分：换行 / 。 / 句号
        for sent in re.split(r"[\n。]+|(?<=[.!?])\s+", text):
            sent = sent.strip()
            if len(sent) < 12:
                continue
            stats["sentences"] += 1
            rels = detect_relations(sent)
            if not rels:
                continue
            norm_sent = norm_title(sent)
            targets = set()
            # a) Steam 直链（最高精度）
            for sid in STEAM_LINK.findall(sent):
                targets.add(("link", sid))
            # b) 标题匹配
            for nt, sid in title_index:
                if sid != self_sid and nt in norm_sent:
                    targets.add(("title", sid))
            for src, sid in targets:
                sid = str(sid)
                if sid == self_sid or not sid:
                    continue
                for rel in rels:
                    if rel == "successor" and (m.get("status") or "") != "deprecated":
                        continue   # 非弃坑条目提 successor 多为「我是继任者」，方向不定，不记录
                    key = (self_sid, sid, rel)
                    if key not in found:
                        found[key] = (src, sent[:120])
                        stats["refs"] += 1

    # 按 MOD 聚合（每类上限 10 条，噪声护栏）
    per_mod = {}
    for (self_sid, other_sid, rel), (src, ev) in found.items():
        other = next((m for m in mods if str(m["steam_id"]) == other_sid), None)
        if not other:
            continue
        bucket = per_mod.setdefault(self_sid, {"conflicts": {}, "requires": {}, "has_patches": [], "successor": []})
        name = other.get("title_en") or other.get("title") or other_sid
        if rel in ("conflicts", "requires"):
            bucket[rel][other_sid] = {"name": name, "evidence": ev}
        elif rel == "successor":
            bucket["successor"].append({"steam_id": other_sid, "name": name, "evidence": ev})
        elif rel == "has_patches":
            bucket["has_patches"].append(name)

    stats["relations"] = len(per_mod)
    print(f"扫描句子 {stats['sentences']}，命中关系 MOD {stats['relations']} 个"
          f"（引用对 {stats['refs']}）")

    if DRY:
        for sid, b in list(per_mod.items())[:8]:
            m = next((x for x in mods if str(x["steam_id"]) == sid), {})
            print(f"  [{(m.get('title_en') or '')[:34]}] "
                  f"冲突{len(b['conflicts'])} 依赖{len(b['requires'])} 补丁{len(b['has_patches'])} 继任{len(b['successor'])}")
        db.close()
        return per_mod

    # 写库：手工存档（compat_top15.json）为种子优先保留，挖掘数据按名去重追加；
    # notes 记录继任与证据句（可审计）
    seed_path = os.path.join(BASE_DIR, "translations", "compat_top15.json")
    seed_map = {}
    if os.path.exists(seed_path):
        with open(seed_path, encoding="utf-8") as f:
            seed_rows = json.load(f).get("compat", [])
        for row in seed_rows:
            seed_map[str(row.get("steam_id"))] = row

    def _names(items):
        out = []
        for x in items or []:
            out.append(x.get("name") if isinstance(x, dict) else str(x))
        return out

    def _merge(old_items, new_items, cap=10):
        merged = list(old_items or [])
        seen = set(_names(merged))
        for info in new_items:
            if info["name"] not in seen:
                merged.append({"name": info["name"], "note": info["evidence"]})
                seen.add(info["name"])
        return merged[:cap]

    n = 0
    all_sids = set(seed_map) | set(per_mod)
    for sid in sorted(all_sids):
        m = next((x for x in mods if str(x["steam_id"]) == sid), None)
        if not m:
            continue
        seed = seed_map.get(sid, {})
        mined = per_mod.get(sid, {"conflicts": {}, "requires": {}, "has_patches": [], "successor": []})

        conflicts = _merge(seed.get("conflicts"), list(mined["conflicts"].values()))
        requires = _merge(seed.get("requires"), list(mined["requires"].values()))
        has_patches = list(dict.fromkeys(_names(seed.get("has_patches")) + mined["has_patches"]))[:10]
        best_with = seed.get("best_with") or []

        notes_parts = []
        for rel in ("conflicts", "requires"):
            for info in list(mined[rel].values())[:10]:
                notes_parts.append(f"{'⚠ 不兼容' if rel == 'conflicts' else '🔒 依赖前置'}：{info['name']}（{info['evidence']}…）")
        if mined["successor"]:
            notes_parts.append(f"🔗 继任/替代：{mined['successor'][0]['name']}")
        seed_notes = (seed.get("notes") or "").strip()
        mined_notes = " ｜ ".join(notes_parts)[:900]
        notes = (seed_notes + (" ｜ " if seed_notes and mined_notes else "") + mined_notes).strip(" ｜")[:1200]

        db.set_compat(m["id"], {
            "conflicts": conflicts,
            "requires": requires,
            "best_with": best_with,
            "notes": notes,
            "has_patches": has_patches,
        })
        n += 1
    db.conn.commit()
    total = db.conn.execute("SELECT COUNT(*) FROM compat").fetchone()[0]
    print(f"写入/合并 {n} 个 MOD 的兼容数据（手工种子 {len(seed_map)} 优先）；compat 表共 {total} 行")
    db.close()
    return per_mod


if __name__ == "__main__":
    main()
