"""抓取《十字军之王 3》创意工坊订阅量排行（官方页面内嵌数据，无需 API Key）

数据源: steamcommunity.com/workshop/browse （Steam 官方页面）
页面内嵌 window.SSR.renderContext → queryData → queries[].state.data.results
包含: 标题/作者/订阅数/收藏/星级/投票数/标签/简介/更新时间/预览图

与 fetch_workshop_top.py（群星版）的唯一区别：appid=1158310，输出到 data/ck3/。

用法: python fetch_ck3_workshop_top.py [--pages 10] [--sleep 8] [--start 1]
输出: data/ck3/workshop_top.json  (完整字段)
"""
import sys, io, json, time, re, os, argparse
import requests
import urllib3

urllib3.disable_warnings()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = "https://steamcommunity.com/workshop/browse/"
APPID = 1158310  # Crusader Kings III
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_page(session, page):
    """抓取一页，返回 results 列表（30 条）"""
    params = {
        "appid": APPID,
        "browsesort": "totaluniquesubscribers",
        "section": "readytouseitems",
        "p": page,
    }
    for attempt in range(6):
        try:
            r = session.get(BASE, params=params, timeout=40, verify=False)
            r.raise_for_status()
            html = r.text
            m = re.search(
                r'window\.SSR\.renderContext\s*=\s*JSON\.parse\("(.*?)"\);?\s*</script>',
                html,
                re.S,
            )
            if not m:
                raise ValueError("未找到 renderContext")
            raw = m.group(1)
            # 两层解码: JS 字符串 -> JSON 文本 -> dict
            s1 = json.loads('"' + raw + '"')
            data = json.loads(s1)
            qdata = json.loads(data["queryData"])
            for q in qdata.get("queries", []):
                d = q.get("state", {}).get("data")
                if isinstance(d, dict) and "results" in d and d["results"]:
                    res = d["results"]
                    if isinstance(res[0], dict) and "publishedfileid" in res[0]:
                        return res
            raise ValueError("未找到 results")
        except Exception as e:
            if attempt >= 5:
                print(f"  第 {page} 页失败: {type(e).__name__} {str(e)[:80]}", flush=True)
                return None
            print(f"  第 {page} 页尝试{attempt+1}失败: {type(e).__name__} {str(e)[:60]}", flush=True)
            time.sleep(6 * (attempt + 1))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=10, help="抓取页数（每页 30 条）")
    ap.add_argument("--sleep", type=float, default=8, help="页间等待秒数")
    ap.add_argument("--start", type=int, default=1, help="起始页")
    args = ap.parse_args()

    session = requests.Session()
    session.headers.update(HEADERS)

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(base, "data", "ck3", "workshop_top.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    all_mods = []
    seen = set()
    for page in range(args.start, args.start + args.pages):
        res = fetch_page(session, page)
        if res is None:
            print(f"第 {page} 页无法获取，跳过", flush=True)
            time.sleep(args.sleep * 2)
            continue
        for it in res:
            fid = it.get("publishedfileid")
            if fid and fid not in seen:
                seen.add(fid)
                all_mods.append(it)
        print(f"第 {page} 页完成，累计 {len(all_mods)} 条", flush=True)
        time.sleep(args.sleep)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"appid": APPID, "game": "ck3", "fetched_at": time.strftime("%Y-%m-%d %H:%M"),
                   "source": "steamcommunity.com/workshop/browse (totaluniquesubscribers)",
                   "total": len(all_mods), "mods": all_mods}, f, ensure_ascii=False, indent=1)
    print(f"\n完成！共 {len(all_mods)} 条，已保存到 {out_path}")


if __name__ == "__main__":
    main()
