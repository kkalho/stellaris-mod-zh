"""合并「补作者自述」的提炼结果，写回源文件（P1）

读 data/stellaris/review_tasks/batch_*_out.json（子智能体提炼的 narr），把
「订阅 X、收藏 Y。」后面追加 narr，写回源翻译文件的 reviews 字段，并生成
fix 存档供本地导入 + 云端同步。

用法:
    python scripts/merge_review_enrich.py --dry-run   # 只预览
    python scripts/merge_review_enrich.py             # 实际写回 + 生成 fix 存档
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import validate_translations as VT

# 当前 reviews 是「订阅 X、收藏 Y。」（无自述，以句号结尾）
_NO_NARR = re.compile(r"^订阅[^。]*、收藏[^。]*。$")


def load_narr_map() -> dict[str, str]:
    m = {}
    outdir = os.path.join(BASE_DIR, "data", "stellaris", "review_tasks")
    for fp in sorted(glob.glob(os.path.join(outdir, "batch_*_out.json"))):
        d = json.load(Path(fp).read_text(encoding="utf-8"))
        for t in d:
            sid = str(t.get("steam_id"))
            narr = (t.get("narr") or "").strip()
            if sid and narr:
                m[sid] = narr
    return m


def _reviews_key(t: dict) -> str | None:
    for k in ("reviews_zh", "reviews"):
        if k in t:
            return k
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    narr_map = load_narr_map()
    print(f"合并 narr: {len(narr_map)} 条")

    records = []
    touched = 0
    for fp in glob.glob(os.path.join(BASE_DIR, "translations", "**", "*.json"),
                        recursive=True):
        # 跳过 fix 存档（历史快照，不应被后续操作改动）
        if os.path.join("translations", "fix") in fp.replace("\\", "/"):
            continue
        try:
            data = json.load(Path(fp).read_text(encoding="utf-8"))
        except Exception:
            continue
        is_dict = isinstance(data, dict)
        trs = data.get("translations", []) if is_dict else data
        if not isinstance(trs, list):
            continue
        if trs and isinstance(trs[0], dict):
            keys = set(trs[0].keys())
            if VT._TREND_KEYS <= keys or VT._DETAIL_KEYS & keys:
                continue

        changed = False
        for t in trs:
            if not isinstance(t, dict):
                continue
            sid = str(t.get("steam_id", ""))
            narr = narr_map.get(sid)
            if not narr:
                continue
            rk = _reviews_key(t)
            if not rk:
                continue
            old = VT._flatten(t.get(rk))
            # 仅对「订阅 X、收藏 Y。」无自述的条目追加
            if not _NO_NARR.match(old.strip()):
                continue
            new = old.rstrip() + narr
            records.append({"steam_id": sid, "old": old, "new": new, "field": rk})
            t[rk] = new
            changed = True

        if changed:
            touched += 1
            if not args.dry_run:
                Path(fp).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"追加 {len(records)} 条（涉及 {touched} 个文件）")
    if args.dry_run:
        return

    if records:
        import datetime
        out = os.path.join(BASE_DIR, "translations", "fix",
                           f"fix_review_enrich_{datetime.date.today():%Y%m%d}.json")
        dedup = {}
        for r in records:
            dedup.setdefault(r["steam_id"], r["new"])
        payload = {"game": "stellaris",
                   "translations": [{"steam_id": k, "reviews_zh": v}
                                    for k, v in dedup.items()]}
        Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"fix 存档已生成: {out}（{len(dedup)} 条）")


if __name__ == "__main__":
    main()
