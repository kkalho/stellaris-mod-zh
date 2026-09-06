"""译名一致性检查（advisory，不阻断导入）

读取 games/stellaris/term_list.json，统计 canonical 与 aliases 在译文中的出现频次，
报告仍在使用变体译名的词条。设计为**建议级**输出（退出码恒为 0）——术语误判率高于
编造词铁律，不做硬门禁；接入 run_wave.py import 阶段作展示，供人工决定是否修。

用法:
    python scripts/check_terminology.py                    # 全库（translations 表）
    python scripts/check_terminology.py --files a.json b.json   # 批次/补丁文件
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
TERM_LIST = BASE_DIR / "games" / "stellaris" / "term_list.json"


def load_terms() -> list[dict]:
    data = json.loads(TERM_LIST.read_text(encoding="utf-8"))
    return data["terms"]


def scan(blob: str, terms: list[dict]) -> list[tuple[dict, int]]:
    """返回 [(词条, 变体频次), ...]，仅保留有变体命中的词条。"""
    hits = []
    for term in terms:
        alias_count = sum(blob.count(a) for a in term.get("aliases", []))
        if alias_count:
            hits.append((term, alias_count))
    hits.sort(key=lambda x: -x[1])
    return hits


def main():
    args = sys.argv[1:]
    terms = load_terms()
    if "--files" in args:
        paths = [a for a in args if not a.startswith("--")]
        blobs = []
        for p in paths:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
            for t in d.get("translations", []):
                for k, v in t.items():
                    if k.endswith("_zh") and isinstance(v, str):
                        blobs.append(v)
                    elif k == "features_zh" and isinstance(v, list):
                        blobs.extend(str(x) for x in v)
        blob = " ".join(blobs)
        source = f"文件 {len(paths)} 个（{len(blobs)} 字段）"
    else:
        conn = sqlite3.connect(str(BASE_DIR / "data" / "stellaris" / "mods.db"))
        rows = conn.execute(
            "SELECT t.zh_text FROM translations t JOIN mods m ON m.id=t.mod_id WHERE m.game_id='stellaris'"
        ).fetchall()
        conn.close()
        blob = " ".join(r[0] or "" for r in rows)
        source = "全库 translations 表"

    hits = scan(blob, terms)
    print(f"=== 译名一致性检查（advisory）：{source}，术语 {len(terms)} 条 ===")
    if not hits:
        print("✅ 未发现变体译名，全部与术语表一致")
        return
    total = sum(c for _, c in hits)
    for term, count in hits:
        print(f"  「{term['canonical']}」变体命中 {count} 处: {'、'.join(term.get('aliases', []))}"
              + (f"  [{term['note']}]" if term.get("note") else ""))
    print(f"合计变体 {total} 处（advisory，不阻断）。改译文前先核对 term_list.json 的 canonical。")


if __name__ == "__main__":
    main()
