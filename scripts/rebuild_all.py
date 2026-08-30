"""一键收敛重建知识库（canonical rebuild pipeline）

用法:
    python scripts/rebuild_all.py             # 全流程收敛（幂等，可随时中断重跑）
    python scripts/rebuild_all.py --dry-run   # 只列出将执行的步骤与文件，不改动
    python scripts/rebuild_all.py --skip-fetch-check ...（暂无）

原理：mods.db 是派生物，全部数据都能从 git 内的源文件重建——
    data/details.jsonl + data/workshop_top1000.json   → mods 表元数据
    translations/*_zh.json + translations/deep/*.json → 六字段翻译
    data/stellaris/community_seed.json                → 社区口碑
    detect_* / rebuild_pinyin_idx                     → version / DLC / 拼音标注
    snapshot_trend                                    → 趋势快照（追加，不清历史）

每一步都是幂等 upsert/重算：无论库处于什么状态（字段归零、漏导入、
并行会话改坏），跑完本脚本即收敛到正确状态。替代已停用的 update_all.py。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))

import games.stellaris.config.game  # noqa: F401
import games.ck3.config.game  # noqa: F401
import games.hoi4.config.game  # noqa: F401
from core.game_config import get_game
from core.mod_db import ModDB

TRANSLATIONS_DIR = os.path.join(BASE_DIR, "translations")
DEEP_DIR = os.path.join(TRANSLATIONS_DIR, "deep")


def load_batch_files() -> list:
    """translations/ 下的批次翻译文件（排除 ck3 / compat 等非群星批次格式）。"""
    out = []
    for f in sorted(os.listdir(TRANSLATIONS_DIR)):
        if not f.endswith(".json") or f.startswith(("ck3", "compat")):
            continue
        path = os.path.join(TRANSLATIONS_DIR, f)
        try:
            with open(path, encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, dict) and isinstance(data.get("translations"), list):
                out.append(path)
        except Exception as e:
            print(f"  ⚠ 跳过无法解析的文件 {f}: {e}")
    return out


def load_deep_files() -> list:
    """translations/deep/ 下的深度精做存档（数组格式，含 description 字段）。

    排除 mods 行存档（*mods*.json）与趋势存档（*trend*.json）——它们不是翻译。
    """
    out = []
    for f in sorted(os.listdir(DEEP_DIR)):
        if not f.endswith(".json") or "mods" in f or "trend" in f:
            continue
        path = os.path.join(DEEP_DIR, f)
        try:
            with open(path, encoding="utf-8") as fp:
                data = json.load(fp)
            if (isinstance(data, list) and data
                    and isinstance(data[0], dict)
                    and "steam_id" in data[0]
                    and ("description" in data[0] or "gameplay" in data[0])):
                out.append(path)
        except Exception as e:
            print(f"  ⚠ 跳过无法解析的文件 {f}: {e}")
    return out


def run_step(title: str, fn, dry: bool):
    print(f"\n>>> {title}")
    if dry:
        print("    (dry-run 跳过)")
        return None
    t0 = time.time()
    result = fn()
    print(f"    完成，耗时 {time.time() - t0:.1f}s")
    return result


def main():
    ap = argparse.ArgumentParser(description="一键收敛重建知识库（幂等流水线）")
    ap.add_argument("--game", default="stellaris", help="目前仅支持 stellaris")
    ap.add_argument("--dry-run", action="store_true", help="只列出步骤，不执行")
    args = ap.parse_args()

    if args.game != "stellaris":
        print("⛔ rebuild_all 目前仅支持 --game stellaris"
              "（CK3/HOI4 的抓取链不同，见交接文档 §5 P3）")
        sys.exit(1)

    batches = load_batch_files()
    deeps = load_deep_files()
    print("===== rebuild_all 收敛流水线（幂等，可随时中断重跑）=====")
    print(f"  翻译批次文件: {len(batches)} 个")
    print(f"  深度精做存档: {len(deeps)} 个")
    if args.dry_run:
        for p in batches:
            print(f"    batch: {os.path.relpath(p, BASE_DIR)}")
        for p in deeps:
            print(f"    deep:  {os.path.relpath(p, BASE_DIR)}")

    cfg = get_game("stellaris", BASE_DIR)

    # ---- 1) MOD 元数据收敛（details.jsonl + workshop_top1000.json，增量 upsert）----
    def step_import_mods():
        import import_new_batch
        with open(os.path.join(BASE_DIR, "data", "workshop_top1000.json"), encoding="utf-8") as f:
            top_total = len(json.load(f)["mods"])
        return import_new_batch.import_range("stellaris", 1, top_total, verbose=False)
    r = run_step("1/9 导入 MOD 元数据（details.jsonl + workshop_top1000.json）",
                 step_import_mods, args.dry_run)
    if r:
        print(f"    新增 {r['added']}，跳过已存在 {r['skipped']}，库中共 {r['total']}")

    # ---- 2) 翻译批次导入 ----
    def step_import_batches():
        import import_stellaris_translations
        db = ModDB(cfg)
        for path in batches:
            import_stellaris_translations.import_file(db, path)
        db.close()
    run_step(f"2/9 导入翻译批次（{len(batches)} 个文件）", step_import_batches, args.dry_run)

    # ---- 3) 深度精做存档导入（覆盖批次翻译的 description/gameplay/reviews/features）----
    def step_import_deep():
        db = ModDB(cfg)
        n = 0
        for path in deeps:
            with open(path, encoding="utf-8") as f:
                items = json.load(f)
            for it in items:
                mod = db.get_mod_by_steam_id(str(it["steam_id"]))
                if not mod:
                    continue
                for field in ("description", "gameplay", "reviews"):
                    if it.get(field):
                        db.set_translation(mod["id"], field, it[field], "ai_reviewed")
                if it.get("features"):
                    val = (json.dumps(it["features"], ensure_ascii=False)
                           if isinstance(it["features"], list) else str(it["features"]))
                    db.set_translation(mod["id"], "features", val, "ai_reviewed")
                n += 1
        db.conn.commit()
        db.close()
        print(f"    深度精做覆盖 {n} 个 MOD")
    run_step(f"3/9 导入深度精做存档（{len(deeps)} 个文件）", step_import_deep, args.dry_run)

    # ---- 4) 社区口碑 ----
    def step_import_community():
        from core.community_rating import CommunityRating
        seed = os.path.join(BASE_DIR, "data", "stellaris", "community_seed.json")
        if not os.path.exists(seed):
            print("    无 community_seed.json，跳过")
            return
        with open(seed, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = data.get("community", [])
        cr = CommunityRating(cfg)
        n = cr.import_json(data)
        n2 = cr.recompute_all()
        cr.close() if hasattr(cr, "close") else None
        print(f"    口碑 {n} 条，重算推荐指数 {n2} 个 MOD")
    run_step("4/9 导入社区口碑（community_seed.json）", step_import_community, args.dry_run)

    # ---- 5-7) 派生标注（各自管理连接）----
    def step_detect_versions():
        import detect_stellaris_versions
        detect_stellaris_versions.main()
    run_step("5/9 版本兼容标注", step_detect_versions, args.dry_run)

    def step_detect_dlcs():
        import detect_stellaris_dlcs
        detect_stellaris_dlcs.main()
    run_step("6/9 DLC 依赖标注", step_detect_dlcs, args.dry_run)

    def step_pinyin():
        import rebuild_pinyin_idx
        rebuild_pinyin_idx.main()
    run_step("7/9 拼音索引重建", step_pinyin, args.dry_run)

    # ---- 8) 趋势快照 ----
    def step_snapshot():
        import snapshot_trend
        return snapshot_trend.snapshot("stellaris", verbose=False)
    r = run_step("8/9 订阅热度趋势快照", step_snapshot, args.dry_run)
    if r is not None:
        print(f"    快照结果: {r if not isinstance(r, dict) else r}")

    # ---- 9) 体检 ----
    def step_verify():
        import verify_db
        result = verify_db.verify("stellaris")
        verify_db.print_report(result)
        if not result["ok"]:
            raise SystemExit(1)
    run_step("9/9 数据体检（verify_db）", step_verify, args.dry_run)

    print("\n✅ 收敛完成。下一步：git 提交 → 云端同步（交接文档 §8）→ 公网复验。")


if __name__ == "__main__":
    main()
