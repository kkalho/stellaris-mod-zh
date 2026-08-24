"""抓取排名 #328-#377 的 50 个 MOD 详情（官方 API，带重试与限速）
输出: data/details.jsonl（追加）
"""
import sys, io, json, time, os, re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

API_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 读取榜单，取排名 #278-#327 的 publishedfileid
with open(os.path.join(BASE, "data", "workshop_top1000.json"), encoding="utf-8") as f:
    mods = json.load(f)["mods"]

target = []
for i, m in enumerate(mods, start=1):
    if 378 <= i <= 427:
        target.append(str(m["publishedfileid"]))
print(f"目标 {len(target)} 个: 排名 #378~#427")

import requests
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
})

def clean_bbcode(text):
    if not text:
        return ""
    text = re.sub(r"\[/?[a-zA-Z0-9=#\"' ]*\]", "", text)
    return text.strip()

def fetch_batch(ids):
    payload = {"itemcount": len(ids)}
    for i, fid in enumerate(ids):
        payload[f"publishedfileids[{i}]"] = str(fid)
    r = session.post(API_URL, data=payload, timeout=40, verify=False)
    r.raise_for_status()
    return r.json()["response"]["publishedfiledetails"]

out_path = os.path.join(BASE, "data", "details.jsonl")
done = set()
if os.path.exists(out_path):
    with open(out_path, encoding="utf-8") as f:
        for line in f:
            try:
                done.add(json.loads(line)["publishedfileid"])
            except Exception:
                pass

pending = [t for t in target if t not in done]
print(f"待抓 {len(pending)}（已存在 {len(target)-len(pending)}）")

BATCH = 5
SLEEP = 12
fail_count = 0
with open(out_path, "a", encoding="utf-8") as out:
    for b in range(0, len(pending), BATCH):
        batch = pending[b : b + BATCH]
        try:
            items = fetch_batch(batch)
            got = 0
            for it in items:
                if it.get("result") == 1:
                    it["description_clean"] = clean_bbcode(it.get("description", ""))
                    out.write(json.dumps(it, ensure_ascii=False) + "\n")
                    got += 1
            out.flush()
            print(f"批次 {min(b+BATCH, len(pending))}/{len(pending)} 成功 {got} 个", flush=True)
            fail_count = 0
        except Exception as e:
            fail_count += 1
            print(f"批次失败({b}): {type(e).__name__} {e}，累计失败 {fail_count}", flush=True)
            if fail_count >= 5:
                print("连续失败 5 次，停止")
                break
            time.sleep(SLEEP * 5)
        time.sleep(SLEEP)

print("抓取结束")
