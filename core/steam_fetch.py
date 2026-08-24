"""Steam API 封装：GetPublishedFileDetails 批量查询（无需 Key）

用途：
- 增量同步 MOD 订阅量/更新时间/点赞数（updater 真实数据源）
- 复用 fetch_ck3_details.py 已验证的抓取方式（verify=False 处理本机 SSL）

接口：
- fetch_details(ids)                → {steam_id: detail_dict}  批量查详情
- sync_subscriptions(game, db)      → 增量同步库中 MOD 的订阅数据，返回统计
"""
from __future__ import annotations

import datetime
import re
import time
from typing import Any, Dict, List, Optional

import requests
import urllib3

urllib3.disable_warnings()  # 本机 venv 缺根证书，verify=False（与抓取脚本一致）

API_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
BATCH = 50          # 每批查询数量（API 宽松限制，50 稳妥）
SLEEP = 10          # 批次间隔（秒），避免限流


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    })
    return s


def clean_bbcode(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\[/?[a-zA-Z0-9=#\"' ]*\]", "", text)
    return text.strip()


def fetch_details(ids: List[str], session: Optional[requests.Session] = None,
                  batch: int = BATCH, sleep: float = SLEEP,
                  verbose: bool = False) -> Dict[str, Dict[str, Any]]:
    """批量查询创意工坊物品详情。

    Args:
        ids: publishedfileid 列表（str/int 均可）
    Returns:
        {str(publishedfileid): detail_dict}，result!=1 的条目不包含
    """
    session = session or _session()
    ids = [str(i) for i in ids]
    out: Dict[str, Dict[str, Any]] = {}
    net_down = False  # 网络不可达标志：一旦出现连接失败，后续批次直接跳过
    for b in range(0, len(ids), batch):
        if net_down:
            break
        chunk = ids[b:b + batch]
        payload = {"itemcount": len(chunk)}
        for i, fid in enumerate(chunk):
            payload[f"publishedfileids[{i}]"] = fid
        for attempt in range(5):
            try:
                r = session.post(API_URL, data=payload, timeout=30, verify=False)
                r.raise_for_status()
                items = r.json()["response"]["publishedfiledetails"]
                for it in items:
                    if it.get("result") == 1:
                        it["description_clean"] = clean_bbcode(it.get("description", ""))
                        out[str(it["publishedfileid"])] = it
                if verbose:
                    print(f"  批次 {min(b + len(chunk), len(ids))}/{len(ids)}，"
                          f"累计成功 {len(out)}", flush=True)
                break
            except requests.exceptions.ConnectionError as e:
                # 连接建立失败（如网络不可达/域名被限制）：重试无意义，快速失败
                net_down = True
                if verbose:
                    print(f"  连接失败（网络不可达）：{str(e)[:60]}", flush=True)
                break
            except Exception as e:
                if attempt >= 4:
                    print(f"  批次失败: {type(e).__name__} {str(e)[:80]}", flush=True)
                else:
                    print(f"  批次重试{attempt + 1}: {str(e)[:60]}", flush=True)
                time.sleep(6 * (attempt + 1))
        time.sleep(sleep)
    return out


def sync_subscriptions(game, db, stale_days: int = 3, verbose: bool = False) -> Dict[str, Any]:
    """增量同步库中 MOD 的订阅数据（订阅量/点赞/更新时间/描述）。

    - 只更新 fetched_at 早于 cutoff（默认 3 天前）的 MOD
    - 用 GetPublishedFileDetails 批量查最新数据并 upsert

    Args:
        game: GameConfig 实例
        db: ModDB 实例
        stale_days: 超过 N 天未抓取的视为待更新
    Returns:
        {"updated": n, "note": "..."}
    """
    cutoff = (datetime.date.today() - datetime.timedelta(days=stale_days)).strftime("%Y-%m-%d")
    mods = db.list_mods(limit=2000)
    pending = [m for m in mods
               if (m.get("fetched_at") or "") < cutoff or not m.get("fetched_at")]
    ids = [str(m["steam_id"]) for m in pending if m.get("steam_id")]
    if not ids:
        return {"updated": 0, "note": f"{len(mods)} 个 MOD 数据均较新（{stale_days} 天内），无需更新"}

    if verbose:
        print(f"待更新 {len(ids)} 个 MOD（cutoff={cutoff}），开始批量查询...")
    details = fetch_details(ids, verbose=verbose)
    if not details:
        return {"updated": 0, "note": "Steam API 查询失败（可能限流），请稍后重试"}

    updated = 0
    for m in pending:
        d = details.get(str(m["steam_id"]))
        if not d:
            continue
        db.upsert_mod({
            **m,
            "subscriptions": d.get("subscriptions", m.get("subscriptions") or 0),
            "favorites": d.get("favorited", m.get("favorites") or 0),
            "views": d.get("views", m.get("views") or 0),
            "time_updated": d.get("time_updated", m.get("time_updated") or 0),
            "description": d.get("description", m.get("description") or ""),
            "description_clean": d.get("description_clean", m.get("description_clean") or ""),
            "preview_url": d.get("preview_url", m.get("preview_url") or ""),
        })
        updated += 1
        if verbose:
            subs = d.get("subscriptions", 0)
            print(f"  更新 {m.get('title_en', '')[:32]} → {subs:,} 订阅", flush=True)
    return {"updated": updated, "note": f"查询 {len(ids)} 个，成功 {len(details)} 个"}
