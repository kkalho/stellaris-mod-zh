"""抓取群星创意工坊热门 Mod 的完整详情（Steam 官方公开 API，无需 Key）
用法: python fetch_details.py [--limit N]
输出: data/details.jsonl （每行一个 Mod 的详情 JSON）
"""
import sys, io, json, time, argparse, os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

API_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
BATCH = 100  # 官方 API 单次最多 100 个


def fetch_batch(ids):
    payload = {"itemcount": len(ids)}
    for i, fid in enumerate(ids):
        payload[f"publishedfileids[{i}]"] = str(fid)
    r = requests.post(API_URL, data=payload, timeout=30)
    r.raise_for_status()
    return r.json()["response"]["publishedfiledetails"]


def clean_bbcode(text):
    """清理 Steam 创意工坊描述的 BBCode 标记"""
    if not text:
        return ""
    import re
    text = re.sub(r"\[/?[a-zA-Z0-9=#\"' ]*\]", "", text)
    return text.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个（0=全部）")
    ap.add_argument("--start", type=int, default=0, help="从第几个开始（断点续抓）")
    args = ap.parse_args()

    import requests
    global requests

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "data", "hot_mods.json"), encoding="utf-8") as f:
        mods = json.load(f)["mods"]

    ids = [m["id"] for m in mods]
    if args.limit:
        ids = ids[: args.limit]
    if args.start:
        ids = ids[args.start:]

    out_path = os.path.join(base, "data", "details.jsonl")
    # 断点续抓：跳过已存在的
    done = set()
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["publishedfileid"])
                except Exception:
                    pass

    pending = [i for i in ids if i not in done]
    print(f"总数 {len(ids)}，已完成 {len(done)}，待抓 {len(pending)}")

    with open(out_path, "a", encoding="utf-8") as out:
        for b in range(0, len(pending), BATCH):
            batch = pending[b : b + BATCH]
            try:
                items = fetch_batch(batch)
                for it in items:
                    if it.get("result") == 1:
                        it["description_clean"] = clean_bbcode(it.get("description", ""))
                        out.write(json.dumps(it, ensure_ascii=False) + "\n")
                out.flush()
                print(f"批次完成 {b + len(batch)}/{len(pending)}")
            except Exception as e:
                print(f"批次失败({b}): {e}，稍后重试")
                time.sleep(3)
            time.sleep(1)  # 限速

    print("抓取结束")


if __name__ == "__main__":
    main()
