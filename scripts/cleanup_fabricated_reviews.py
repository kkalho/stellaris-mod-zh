"""批量清理源翻译存档中的编造评价（P0 止血）

把 reviews 字段里的编造内容（「5 星好评」「X 次投票」「官方数据显示」及
标杆/头部/经典之作等主观拔高词）重写为客观「订阅 X、收藏 Y」。
- 订阅/收藏取自 details.jsonl 的真实 subscriptions/favorited 字段（Steam 工坊
  无星级/无投票，故旧文本里的投票数、星级均为编造）。
- 已在 fix_reviews_debunk.json 中有正确自述的 sid 直接复用其 reviews_zh。

用法:
    python scripts/cleanup_fabricated_reviews.py --dry-run   # 只预览，不改任何文件
    python scripts/cleanup_fabricated_reviews.py             # 实际重写源文件 + 生成 fix 存档

安全：默认只处理含编造词的 reviews；生成 fix 存档
translations/fix/fix_reviews_cleanup_<日期>.json 记录每次重写（sid → 旧 → 新），
便于审计与 git 审查。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import validate_translations as VT


def load_fix_map() -> dict[str, str]:
    """fix_reviews_debunk.json → {steam_id: reviews_zh}。"""
    p = os.path.join(BASE_DIR, "translations", "fix", "fix_reviews_debunk.json")
    m = {}
    if os.path.exists(p):
        d = json.load(open(p, encoding="utf-8"))
        for t in d.get("translations", []):
            m[str(t["steam_id"])] = t.get("reviews_zh", "")
    return m


def load_details() -> dict[str, tuple]:
    """details.jsonl → {publishedfileid: (subscriptions, favorited)}。"""
    p = os.path.join(BASE_DIR, "data", "details.jsonl")
    m = {}
    if not os.path.exists(p):
        return m
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            pid = str(d.get("publishedfileid", ""))
            if pid:
                m[pid] = (d.get("subscriptions"), d.get("favorited"))
    return m


def fmt_subs(subs) -> str:
    """订阅数格式化：≥1 万 → 「X 万」（去尾 0），否则原数字。"""
    if subs is None:
        return "暂无数据"
    subs = int(subs)
    if subs >= 10000:
        v = f"{subs / 10000:.2f}".rstrip("0").rstrip(".")
        return f"{v} 万"
    return str(subs)


def build_review(sid: str, fix_map: dict, details: dict) -> str:
    """生成客观 reviews：优先复用 fix 自述，否则「订阅 X、收藏 Y」。"""
    if sid in fix_map:
        return fix_map[sid]
    subs, fav = details.get(sid, (None, None))
    parts = [f"订阅 {fmt_subs(subs)}"]
    if fav is not None:
        parts.append(f"收藏 {int(fav)}")
    else:
        parts.append("收藏 暂无数据")
    return "、".join(parts) + "。"


def _reviews_key(t: dict) -> str | None:
    """返回该条目实际使用的 reviews 字段名（reviews_zh 优先，其次裸 reviews）。"""
    for k in ("reviews_zh", "reviews"):
        if k in t:
            return k
    return None


def _is_fabricated(text: str) -> bool:
    """判断 reviews 文本是否含编造词（全局强特征 + reviews 专属词表）。"""
    return bool(VT._GLOBAL_RE.search(text) or VT._REVIEWS_RE.search(text))


def process_file(path: str, fix_map: dict, details: dict, dry_run: bool) -> list[dict]:
    """处理单个文件，返回重写记录列表 [{steam_id, old, new, field}]。"""
    records = []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    is_dict = isinstance(data, dict)
    trs = data.get("translations", []) if is_dict else data
    if not isinstance(trs, list):
        return records

    # 跳过非翻译文件（趋势/MOD 详情）
    if trs and isinstance(trs[0], dict):
        keys = set(trs[0].keys())
        if VT._TREND_KEYS <= keys or VT._DETAIL_KEYS & keys:
            return records

    changed = False
    for t in trs:
        if not isinstance(t, dict):
            continue
        sid = str(t.get("steam_id", ""))
        rk = _reviews_key(t)
        if not rk:
            continue
        text = VT._flatten(t.get(rk))
        if not text or not _is_fabricated(text):
            continue
        new = build_review(sid, fix_map, details)
        if new and new != text:
            records.append({"steam_id": sid, "old": text, "new": new, "field": rk})
            t[rk] = new
            changed = True

    if changed and not dry_run:
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return records


def main():
    ap = argparse.ArgumentParser(description="批量清理源存档中的编造评价")
    ap.add_argument("--dry-run", action="store_true", help="只预览，不写任何文件")
    args = ap.parse_args()

    fix_map = load_fix_map()
    details = load_details()
    print(f"fix 复用映射: {len(fix_map)} 条；details 订阅/收藏: {len(details)} 条")

    all_records = []
    touched_files = []
    for path in VT._iter_files([]):
        recs = process_file(path, fix_map, details, args.dry_run)
        if recs:
            touched_files.append(path)
            all_records.extend(recs)
            if args.dry_run:
                print(f"[dry-run] {path}: 将重写 {len(recs)} 条")

    n_reuse = sum(1 for r in all_records if r["steam_id"] in fix_map)
    n_new = len(all_records) - n_reuse
    print(f"\n=== {'预览' if args.dry_run else '完成'} ===")
    print(f"涉及文件 {len(touched_files)} 个，重写 {len(all_records)} 条 "
          f"（复用 fix {n_reuse} 条 / 新生成 {n_new} 条）")

    if all_records and not args.dry_run:
        import datetime
        d = datetime.date.today().strftime("%Y%m%d")
        out = os.path.join(BASE_DIR, "translations", "fix",
                           f"fix_reviews_cleanup_{d}.json")
        payload = {"game": "stellaris",
                   "translations": [{"steam_id": r["steam_id"], "reviews_zh": r["new"]}
                                    for r in all_records]}
        # 按 steam_id 去重（同一 sid 可能在多个源文件出现，只保留一条最终 reviews）
        dedup = {}
        for t in payload["translations"]:
            dedup.setdefault(t["steam_id"], t["reviews_zh"])
        payload["translations"] = [{"steam_id": k, "reviews_zh": v}
                                   for k, v in dedup.items()]
        Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"fix 存档已生成: {out}（去重后 {len(dedup)} 条）")


if __name__ == "__main__":
    main()
