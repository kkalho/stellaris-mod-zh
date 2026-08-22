"""自动抓取 CK3 创意工坊热门 Mod 详情（官方 API，无需 Key，支持断点续抓）

输入: data/ck3/workshop_top.json（榜单，含 publishedfileid）
输出: data/ck3/details.jsonl（官方 API 完整详情，逐行 JSON）

用法: python fetch_ck3_details.py [--limit N] [--sleep 15] [--batch 5]
"""
import sys, io, json, time, argparse, os, re
import urllib3

urllib3.disable_warnings()  # 本机 venv 缺根证书，verify=False（与榜单脚本一致）
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

API_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"


def fetch_batch(ids, session):
    payload = {"itemcount": len(ids)}
    for i, fid in enumerate(ids):
        payload[f"publishedfileids[{i}]"] = str(fid)
    r = session.post(API_URL, data=payload, timeout=30, verify=False)
    r.raise_for_status()
    return r.json()["response"]["publishedfiledetails"]


def clean_bbcode(text):
    if not text:
        return ""
    text = re.sub(r"\[/?[a-zA-Z0-9=#\"' ]*\]", "", text)
    return text.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=15, help="批次间等待秒数（Steam 匿名 API 限流严，建议 >=12）")
    ap.add_argument("--batch", type=int, default=5, help="每批数量（建议 5，避免触发限流）")
    args = ap.parse_args()
    BATCH = args.batch

    import requests
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    })

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "data", "ck3", "workshop_top.json"), encoding="utf-8") as f:
        mods = json.load(f)["mods"]
    ids = [str(m["publishedfileid"]) for m in mods]
    if args.limit:
        ids = ids[: args.limit]

    out_path = os.path.join(base, "data", "ck3", "details.jsonl")
    done = set()
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["publishedfileid"])
                except Exception:
                    pass

    pending = [i for i in ids if i not in done]
    print(f"总数 {len(ids)}，已完成 {len(done)}，待抓 {len(pending)}", flush=True)

    fail_count = 0
    with open(out_path, "a", encoding="utf-8") as out:
        for b in range(0, len(pending), BATCH):
            batch = pending[b : b + BATCH]
            try:
                items = fetch_batch(batch, session)
                for it in items:
                    if it.get("result") == 1:
                        it["description_clean"] = clean_bbcode(it.get("description", ""))
                        out.write(json.dumps(it, ensure_ascii=False) + "\n")
                out.flush()
                print(f"批次完成 {min(b + len(batch), len(pending))}/{len(pending)}", flush=True)
                fail_count = 0
            except Exception as e:
                fail_count += 1
                print(f"批次失败({b}): {type(e).__name__} {e}，累计失败 {fail_count} 次", flush=True)
                if fail_count >= 5:
                    print("连续失败 5 次，停止（稍后重新运行即可续抓）")
                    break
                time.sleep(args.sleep * 5)
            time.sleep(args.sleep)

    print("抓取结束")


if __name__ == "__main__":
    main()
