"""翻译质量校验脚本：导入前的数据真实性门禁

背景：reviews 铁律 = 只能总结作者自述 + 客观订阅/收藏数据。Steam 创意工坊
**没有星级评分、没有投票数**（details.jsonl 只有 subscriptions/favorited），
因此「5 星好评」「X 次投票」「官方数据显示…是标杆/头部/经典之作」这类表述
全部属于编造。本脚本在导入前拦截这些编造词，并做 steam_id 基础校验。

用法:
    python scripts/validate_translations.py [文件...]      # 校验指定文件
    python scripts/validate_translations.py                # 扫 translations/ 全部
    python scripts/validate_translations.py f.json --db    # 额外校验 steam_id 关联
    python scripts/validate_translations.py f.json --json  # 机器可读输出
    python scripts/validate_translations.py f.json --dump out.json  # 导出待修复清单

校验项:
- 结构：顶层 dict.translations 为列表，每条含 steam_id
- steam_id 格式：必须为纯数字（拦截「写成 mod_id」类错误）
- 编造词扫描（分字段，见下方词表）
- steam_id 同文件内重复（告警）
- 可选 --db：steam_id 能否查到对应 MOD（张冠李戴第一道防线）

退出码: 0 = 通过；1 = 命中硬阻断词（导入门禁应拒绝）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# 六个逻辑字段。翻译存档有两种命名：主 batch 用 `xxx_zh`，deep 目录用裸 `xxx`；
# 取值时两者都兼容。reviews 字段应用最严的 reviews 专属词表。
LOGICAL_FIELDS = ["title", "summary", "description", "gameplay", "reviews", "features"]

# 非翻译文件标志（用于跳过混入 translations/ 的趋势数据 / MOD 详情）
_TREND_KEYS = {"date", "subs"}
_DETAIL_KEYS = {"game_id", "title_en", "fetched_at", "score", "like_ratio", "subscriptions"}

# ---------------------------------------------------------------------------
# 编造词表
# ---------------------------------------------------------------------------
# 全局硬阻断（任何字段出现即判编造）：只保留**无歧义**的编造强特征。
# 「好评/差评/投票」这类词在 description 里可能是合法（作者"喜欢请好评收藏"、
# 群星游戏机制"投票会议/月度投票"），故放到 HARD_REVIEWS 仅在 reviews 字段拦截。
HARD_GLOBAL = [
    r"官方数据显示?",         # 伪装"官方数据"的编造模板（作者原文不会出现）
    r"(?:\d+|[一二三四五两])\s*星\s*(?=好评|差评|评价|推荐|口碑)",  # 星级评分语境
    r"\d+\s*次\s*投票",       # 编造投票数（details.jsonl 无 votes 字段）
]

# reviews 专属硬阻断（只查 reviews_zh）：reviews 铁律最严——只能作者自述 + 客观订阅/收藏。
# 这里包含：评价/投票数据词（reviews 里出现即编造）+ 主观拔高词（编造赞誉）。
HARD_REVIEWS = [
    r"好评", r"差评", r"中评", r"投票数", r"票数", r"好评如潮",
    r"标杆", r"头部", r"名列前茅", r"经典之作", r"代表作", r"代表作品",
    r"天花板", r"神作", r"现象级", r"镇站", r"最受欢迎",
    r"口碑", r"收藏比高", r"第一梯队", r"人气第一", r"热度第一",
    r"必装", r"必下", r"最强", r"顶级", r"顶尖", r"主流选择",
]

_GLOBAL_RE = re.compile("|".join(HARD_GLOBAL))
_REVIEWS_RE = re.compile("|".join(HARD_REVIEWS))
_SID_RE = re.compile(r"^\d+$")


def _flatten(txt) -> str:
    """features_zh 是字符串列表，转成单一文本供扫描。"""
    if txt is None:
        return ""
    if isinstance(txt, list):
        return " ".join(str(x) for x in txt)
    return str(txt)


def scan_entry(t: dict) -> list[dict]:
    """扫描单条翻译，返回命中列表（每条含 field/word/context）。

    字段名兼容两种命名：`xxx_zh`（主 batch）与裸 `xxx`（deep 目录）。
    """
    hits = []
    sid = str(t.get("steam_id", ""))
    for field in LOGICAL_FIELDS:
        text = _flatten(t.get(field + "_zh") or t.get(field))
        if not text:
            continue
        # 全局词表：所有字段
        for m in _GLOBAL_RE.finditer(text):
            hits.append(_mk_hit(sid, field, m, text))
        # reviews 专属词表
        if field == "reviews":
            for m in _REVIEWS_RE.finditer(text):
                hits.append(_mk_hit(sid, field, m, text))
    return hits


def _mk_hit(sid: str, field: str, m, text: str) -> dict:
    s, e = m.start(), m.end()
    ctx = text[max(0, s - 24):e + 24].replace("\n", " ")
    return {"steam_id": sid, "field": field, "word": m.group(), "context": ctx}


def validate_file(path: str, db=None) -> dict:
    """校验单个 JSON 文件，返回报告 dict。"""
    res = {"file": path, "ok": True, "errors": [], "hits": [], "warnings": [],
           "entries": 0}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        res["ok"] = False
        res["errors"].append(f"无法解析 JSON: {e}")
        return res

    trs = data.get("translations", []) if isinstance(data, dict) else data
    if not isinstance(trs, list):
        res["ok"] = False
        res["errors"].append("顶层缺少 translations 列表")
        return res

    # 跳过非翻译文件：趋势数据（date/subs）、MOD 详情（game_id/title_en 等）
    if trs and isinstance(trs[0], dict):
        keys = set(trs[0].keys())
        if _TREND_KEYS <= keys or _DETAIL_KEYS & keys:
            res["skipped"] = True
            res["note"] = "非翻译文件（趋势/MOD 详情），跳过"
            return res

    res["entries"] = len(trs)
    seen_sid = {}
    for t in trs:
        if not isinstance(t, dict):
            res["errors"].append("translations 中存在非对象条目")
            res["ok"] = False
            continue
        sid = str(t.get("steam_id", ""))
        if not sid:
            res["ok"] = False
            res["errors"].append("存在缺 steam_id 的条目")
            continue
        if not _SID_RE.match(sid):
            res["ok"] = False
            res["errors"].append(f"steam_id 非纯数字: {sid}")
        if sid in seen_sid:
            res["warnings"].append(f"steam_id 重复: {sid}（出现 {seen_sid[sid] + 1} 次）")
        seen_sid[sid] = seen_sid.get(sid, 0) + 1

        res["hits"].extend(scan_entry(t))

        if db is not None:
            mod = db.get_mod_by_steam_id(sid)
            if not mod:
                res["warnings"].append(f"库中无此 MOD（steam_id 可能写错或未入库）: {sid}")

    if res["hits"]:
        res["ok"] = False
    return res


def _iter_files(paths):
    if paths:
        for p in paths:
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for fn in sorted(files):
                        if fn.endswith(".json"):
                            yield os.path.join(root, fn)
            elif os.path.exists(p):
                yield p
            else:
                print(f"[跳过] 文件不存在: {p}", file=sys.stderr)
    else:
        tdir = os.path.join(BASE_DIR, "translations")
        for root, _, files in os.walk(tdir):
            for fn in sorted(files):
                if fn.endswith(".json"):
                    yield os.path.join(root, fn)


def print_report(reports: list[dict]):
    total_hits = sum(len(r["hits"]) for r in reports)
    total_errors = sum(len(r["errors"]) for r in reports)
    total_warn = sum(len(r["warnings"]) for r in reports)
    print(f"\n===== 翻译质量校验：{len(reports)} 个文件 =====")
    for r in reports:
        if r.get("skipped"):
            continue
        mark = "✅" if r["ok"] else "🔴"
        if r["hits"]:
            print(f"\n{mark} {r['file']}  ({r['entries']} 条，命中 {len(r['hits'])} 处)")
            for h in r["hits"]:
                print(f"    [{h['field']}] sid={h['steam_id']}  「{h['word']}」")
                print(f"        …{h['context']}…")
        elif r["errors"]:
            print(f"\n{mark} {r['file']}  结构错误 {len(r['errors'])} 处")
            for e in r["errors"]:
                print(f"    ✗ {e}")
        for w in r["warnings"]:
            print(f"    🟡 {w}")
    print(f"\n--- 合计：命中 {total_hits} 处，结构错误 {total_errors}，告警 {total_warn} ---")
    verdict = "🔴 不通过（有硬阻断词，导入门禁应拒绝）" if (total_hits or total_errors) else "✅ 通过"
    print(f"结论: {verdict}")


def main():
    ap = argparse.ArgumentParser(description="翻译质量校验（数据真实性门禁）")
    ap.add_argument("files", nargs="*", help="待校验的 JSON 文件或目录；默认扫 translations/ 全部")
    ap.add_argument("--db", action="store_true", help="额外校验 steam_id 能否查到对应 MOD")
    ap.add_argument("--game", default="stellaris", help="--db 时使用的游戏（默认 stellaris）")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--dump", metavar="OUT", help="把命中清单导出为 JSON（含 steam_id/字段/词/上下文）")
    args = ap.parse_args()

    db = None
    if args.db:
        import games.stellaris.config.game  # noqa: F401
        import games.ck3.config.game  # noqa: F401
        import games.hoi4.config.game  # noqa: F401
        from core.game_config import get_game
        from core.mod_db import ModDB
        db = ModDB(get_game(args.game, BASE_DIR))

    reports = [validate_file(p, db) for p in _iter_files(args.files)]

    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
    else:
        print_report(reports)

    if args.dump:
        hits = [h for r in reports for h in r["hits"]]
        with open(args.dump, "w", encoding="utf-8") as f:
            json.dump(hits, f, ensure_ascii=False, indent=2)
        print(f"已导出 {len(hits)} 条命中 → {args.dump}")

    if db is not None:
        db.close()

    bad = any(not r["ok"] for r in reports)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
