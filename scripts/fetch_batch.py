"""抓取创意工坊 MOD 详情（参数化版，替代 fetch_batch9~16 系列复制脚本）

用法:
    python scripts/fetch_batch.py --start 578 --end 627     # 抓排名 578-627
    python scripts/fetch_batch.py --start 578 --end 627 --dry-run
                                                            # 只列出目标 ID，不请求
    python scripts/fetch_batch.py --start 578 --end 627 --sleep 20

行为与旧脚本一致：
- 从 data/workshop_top1000.json 按枚举序（= 榜单排名）取 ID
- 调 Steam 官方 API GetPublishedFileDetails（无需 Key），追加写入 data/details.jsonl
- 断点续抓：已存在的 publishedfileid 自动跳过
- 连接失败快速放弃（时段性封锁时不傻等），连续失败 5 批终止

TLS 校验：默认使用 certifi 证书包正常校验；仅当本机 venv 缺根证书
（交接文档坑 #9，CERTIFICATE_VERIFY_FAILED）时，加 --insecure 显式降级。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
OUT_PATH = os.path.join(BASE, "data", "details.jsonl")
TOP_PATH = os.path.join(BASE, "data", "workshop_top1000.json")


def clean_bbcode(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\[/?[a-zA-Z0-9=#\"' ]*\]", "", text).strip()


def target_ids(start: int, end: int) -> list:
    with open(TOP_PATH, encoding="utf-8") as f:
        mods = json.load(f)["mods"]
    out = []
    for i, m in enumerate(mods, start=1):
        if start <= i <= end:
            fid = str(m.get("publishedfileid", ""))
            if fid:
                out.append(fid)
    return out


def existing_ids() -> set:
    done = set()
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["publishedfileid"])
                except Exception:
                    pass
    return done


def fetch(session, ids: list, verify_arg) -> list:
    payload = {"itemcount": len(ids)}
    for i, fid in enumerate(ids):
        payload[f"publishedfileids[{i}]"] = str(fid)
    r = session.post(API_URL, data=payload, timeout=40, verify=verify_arg)
    r.raise_for_status()
    return r.json()["response"]["publishedfiledetails"]


def main():
    ap = argparse.ArgumentParser(description="按榜单排名区间抓取 MOD 详情")
    ap.add_argument("--start", type=int, required=True, help="起始排名（含）")
    ap.add_argument("--end", type=int, required=True, help="结束排名（含）")
    ap.add_argument("--batch", type=int, default=5, help="每批请求数")
    ap.add_argument("--sleep", type=float, default=12, help="批次间隔秒")
    ap.add_argument("--dry-run", action="store_true", help="只列出目标，不请求")
    ap.add_argument("--insecure", action="store_true",
                    help="禁用 TLS 校验（仅本机 venv 缺根证书时用，坑 #9）")
    args = ap.parse_args()

    if args.end < args.start:
        print("⛔ --end 不能小于 --start")
        sys.exit(1)

    target = target_ids(args.start, args.end)
    done = existing_ids()
    pending = [t for t in target if t not in done]
    print(f"目标 {len(target)} 个（排名 #{args.start}~#{args.end}），"
          f"已存在 {len(target) - len(pending)}，待抓 {len(pending)}")
    if args.dry_run:
        for fid in pending:
            print(f"  {fid}")
        return
    if not pending:
        print("全部已抓取，无需请求")
        return

    import requests
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    })
    # 默认 certifi 正常校验；仅 --insecure 显式降级（坑 #9 的本机旧环境）
    verify_arg = True
    try:
        import certifi
        verify_arg = certifi.where()
    except ImportError:
        pass
    if args.insecure:
        import urllib3
        urllib3.disable_warnings()
        verify_arg = False
        print("⚠ 已按 --insecure 禁用 TLS 校验（坑 #9 环境才需要）")

    fail_count = 0
    with open(OUT_PATH, "a", encoding="utf-8") as out:
        for b in range(0, len(pending), args.batch):
            chunk = pending[b:b + args.batch]
            try:
                items = fetch(session, chunk, verify_arg)
                got = 0
                for it in items:
                    if it.get("result") == 1:
                        it["description_clean"] = clean_bbcode(it.get("description", ""))
                        out.write(json.dumps(it, ensure_ascii=False) + "\n")
                        got += 1
                out.flush()
                print(f"批次 {min(b + args.batch, len(pending))}/{len(pending)} 成功 {got} 个",
                      flush=True)
                fail_count = 0
            except Exception as e:
                fail_count += 1
                print(f"批次失败({b}): {type(e).__name__} {e}，累计失败 {fail_count}", flush=True)
                if fail_count >= 5:
                    print("连续失败 5 次，停止（Steam 可能时段性封锁，稍后重跑即可续抓）")
                    break
                time.sleep(args.sleep * 5)
            time.sleep(args.sleep)

    # 提示：抓取完成后用两次 wc -l 确认行数稳定，再增量入库（坑 #11）
    print("\n下一步:")
    print("  1. 确认抓完: 两次运行 wc -l data/details.jsonl 行数一致")
    print(f"  2. 增量入库: python scripts/import_new_batch.py {args.start} {args.end}")
    print("  3. 翻译导入后重跑标注，或直接: python scripts/rebuild_all.py")


if __name__ == "__main__":
    main()
