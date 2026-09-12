"""多游戏版网页服务（展示层）

用法:
    python web_server.py [端口] [--game stellaris]
默认 game=stellaris，端口 8080

API（带游戏上下文）:
    GET /                      → 网页界面（多游戏选择器）
    GET /api/games              → 可用游戏列表
    GET /api/<game>/stats       → 统计
    GET /api/<game>/top?n=      → Top 列表
    GET /api/<game>/search?q=&sort=&tag=&n=   → 搜索
    GET /api/<game>/mod?id=     → MOD 详情（含翻译/DLC/兼容性/社区）
    GET /api/<game>/categories  → 标签分类
    GET /api/<game>/versions    → 版本筛选选项（从数据生成，附代号/计数）
    GET /api/<game>/picks       → 新手精选推荐（beginner_picks.json + 库内联表）
    GET /api/<game>/gems        → 遗珠榜（收藏率显著高于大盘的低订阅 MOD，纯计算）
    GET /api/<game>/conflict-check?ids= → 清单冲突/缺失依赖检测（P7）
    GET /api/<game>/local       → 本地 MOD 列表
    GET /api/<game>/localizations → 汉化包数据库
    GET /api/<game>/trend       → 订阅热度趋势（每日快照涨跌）
    GET /api/<game>/dlcs        → DLC 清单
    GET /api/<game>/comments?id= → 访客留言列表
    POST /api/<game>/comments   → 提交匿名留言（JSON）
    GET /api/site/version       → 站点数据版本指纹（前端自动更新感知）
"""
from __future__ import annotations

import datetime
import hashlib
import io
import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import games.stellaris.config.game  # noqa: F401
import games.ck3.config.game  # noqa: F401
import games.hoi4.config.game  # noqa: F401
from core.game_config import get_game, list_games
from core.mod_db import ModDB, calc_score

# 游戏配置缓存（轻量，无连接）
_CFG_CACHE = {}

# ---------------------------------------------------------------------------
# 简单限流（公网部署防刷；2核1.9G 的轻量机扛不住恶意高频请求）
# ---------------------------------------------------------------------------
RATE_LIMIT = 120        # 每 IP 每窗口最大请求数
RATE_WINDOW = 60.0      # 窗口长度（秒）
_rate_lock = threading.Lock()
_rate_bucket = {}       # ip -> [window_start, count]


def _rate_allow(ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        win, cnt = _rate_bucket.get(ip, (now, 0))
        if now - win >= RATE_WINDOW:
            win, cnt = now, 0
        cnt += 1
        _rate_bucket[ip] = (win, cnt)
        if len(_rate_bucket) > 4096:  # 防字典无限膨胀
            for k in [k for k, (w, _) in _rate_bucket.items() if now - w >= RATE_WINDOW]:
                del _rate_bucket[k]
        return cnt <= RATE_LIMIT


# POST 评论专用限流：每 IP 每 10 分钟最多 5 次
POST_RATE_LIMIT = 5
POST_RATE_WINDOW = 600.0
_post_bucket = {}


def _post_rate_allow(ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        win, cnt = _post_bucket.get(ip, (now, 0))
        if now - win >= POST_RATE_WINDOW:
            win, cnt = now, 0
        cnt += 1
        _post_bucket[ip] = (win, cnt)
        if len(_post_bucket) > 4096:
            for k in [k for k, (w, _) in _post_bucket.items() if now - w >= POST_RATE_WINDOW]:
                del _post_bucket[k]
        return cnt <= POST_RATE_LIMIT


# ---------------------------------------------------------------------------
# 访客留言（独立 SQLite，不写 mods.db；参数化 SQL）
# ---------------------------------------------------------------------------
COMMENTS_DB_DIR = os.path.join(BASE, "data", "site")
COMMENTS_DB_PATH = os.path.join(COMMENTS_DB_DIR, "comments.db")
_comments_lock = threading.Lock()


def _comments_conn():
    import sqlite3

    os.makedirs(COMMENTS_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(COMMENTS_DB_PATH, timeout=8)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 8000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT NOT NULL,
            steam_id TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '匿名',
            content TEXT NOT NULL,
            ip TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_comments_mod ON comments(game_id, steam_id, created_at)"
    )
    conn.commit()
    return conn


def list_comments(game_id: str, steam_id: str, limit: int = 50):
    steam_id = re.sub(r"[^0-9]", "", str(steam_id or ""))
    if not steam_id:
        return {"comments": [], "total": 0}
    limit = max(1, min(int(limit or 50), 50))
    with _comments_lock:
        conn = _comments_conn()
        try:
            rows = conn.execute(
                "SELECT id, name, content, created_at FROM comments "
                "WHERE game_id = ? AND steam_id = ? ORDER BY id DESC LIMIT ?",
                (game_id, steam_id, limit),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) AS n FROM comments WHERE game_id = ? AND steam_id = ?",
                (game_id, steam_id),
            ).fetchone()["n"]
        finally:
            conn.close()
    return {
        "comments": [
            {
                "id": r["id"],
                "name": r["name"],
                "content": r["content"],
                "created_at": r["created_at"],
            }
            for r in rows
        ],
        "total": total,
    }


def add_comment(game_id: str, steam_id: str, name: str, content: str, ip: str = ""):
    steam_id = re.sub(r"[^0-9]", "", str(steam_id or ""))
    if not steam_id or len(steam_id) < 6:
        raise ValueError("无效的 Steam ID")
    name = (name or "匿名").strip()[:24] or "匿名"
    content = (content or "").strip()
    if len(content) < 2 or len(content) > 500:
        raise ValueError("留言长度需在 2–500 字之间")
    # 去掉控制字符，保留换行
    content = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", content)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _comments_lock:
        conn = _comments_conn()
        try:
            cur = conn.execute(
                "INSERT INTO comments (game_id, steam_id, name, content, ip, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (game_id, steam_id, name, content, ip[:64], now),
            )
            conn.commit()
            cid = cur.lastrowid
        finally:
            conn.close()
    return {"id": cid, "name": name, "content": content, "created_at": now}


def _count_comments():
    try:
        with _comments_lock:
            conn = _comments_conn()
            try:
                return int(conn.execute("SELECT COUNT(*) AS n FROM comments").fetchone()["n"])
            finally:
                conn.close()
    except Exception:
        return 0


def get_site_version():
    """站点数据指纹：任一游戏统计/抓取日期/留言数变化 → fingerprint 变 → 前端提示刷新。"""
    games = {}
    parts = []
    for g in list_games():
        try:
            db = get_db(g)
            try:
                row = db.conn.execute(
                    "SELECT COUNT(*) AS total, MAX(fetched_at) AS max_fetched "
                    "FROM mods WHERE game_id = ?",
                    (g,),
                ).fetchone()
                total = int(row[0] or 0)
                max_fetched = row[1] or ""
                trow = db.conn.execute(
                    "SELECT COUNT(*) FROM mods WHERE game_id = ? AND translated = 1",
                    (g,),
                ).fetchone()
                translated = int(trow[0] or 0)
            finally:
                db.close()
            games[g] = {
                "total": total,
                "translated": translated,
                "max_fetched": max_fetched or "",
            }
            parts.append(f"{g}:{total}:{translated}:{max_fetched}")
        except Exception:
            games[g] = {"total": 0, "translated": 0, "max_fetched": ""}
            parts.append(f"{g}:err")
    n_comments = _count_comments()
    parts.append(f"c:{n_comments}")
    fp = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
    updated = max((v.get("max_fetched") or "" for v in games.values()), default="")
    return {
        "ok": True,
        "fingerprint": fp,
        "updated_at": updated,
        "comments": n_comments,
        "games": games,
    }


def get_cfg(game_id: str):
    if game_id not in _CFG_CACHE:
        _CFG_CACHE[game_id] = get_game(game_id, BASE)
    return _CFG_CACHE[game_id]


def get_db(game_id: str) -> ModDB:
    """获取游戏数据库连接（每个请求新建，避免共享连接锁死）。"""
    cfg = get_cfg(game_id)
    db = ModDB(cfg)
    # 只设置 busy_timeout（连接级），WAL 由首次连接持久化
    db.conn.execute("PRAGMA busy_timeout = 8000")
    return db


def search(game_id, keyword, limit=60, sort="subs", tag=None, version=None, db=None):
    if db is None:
        db = get_db(game_id)
    conn = db.conn
    order_map = {
        "subs": "m.subscriptions DESC",
        "subs_asc": "m.subscriptions ASC",
        "updated": "m.time_updated DESC",
        "name": "m.title_en ASC",
    }
    order = order_map.get(sort, order_map["subs"])
    words = [w for w in keyword.split() if w.strip()]
    sql = """
        SELECT m.*, COALESCE(tsum.zh_text, '') as summary,
               COALESCE(ttitle.zh_text, m.title_en) as display_title
        FROM mods m
        LEFT JOIN translations tsum ON tsum.mod_id = m.id AND tsum.field = 'summary'
        LEFT JOIN translations ttitle ON ttitle.mod_id = m.id AND ttitle.field = 'title'
    """
    conds, params = [], []
    for w in words:
        variant_conds, variant_params = [], []
        for v in term_variants(game_id, w):
            kw = f"%{v}%"
            variant_conds.append("(m.title_en LIKE ? OR m.title LIKE ? OR m.steam_id LIKE ? "
                                 "OR ttitle.zh_text LIKE ? OR tsum.zh_text LIKE ? OR m.pinyin_idx LIKE ?)")
            variant_params.extend([kw] * 6)
        conds.append("(" + " OR ".join(variant_conds) + ")")
        params.extend(variant_params)
    if not conds:
        conds.append("(m.title_en != '' OR m.title != '')")
    sql += " WHERE m.game_id=? AND " + " AND ".join(conds)
    params.insert(0, game_id)
    if tag:
        sql += " AND m.tags LIKE ?"
        params.append(f"%{tag}%")
    if version:
        # 版本筛选：匹配「适配 4.4」或「更新于 4.4 时期」
        # 精确版本如 "4.4"：匹配含 "4.4" 的（"适配 4.4"、"更新于 4.4 时期"）
        # 通配如 "3.x"：匹配 "3."（"适配 3.14"、"更新于 3.11 时期"，不会误中 "4.3"）
        if version.endswith(".x"):
            prefix = version[:-2]
            sql += " AND m.version LIKE ?"
            params.append(f"%{prefix}.%")
        else:
            # 精确版本：version 字段由 detect_stellaris_versions 生成，只有
            # 「适配 X」/「更新于 X 时期」两种格式。等值匹配避免
            # LIKE '%3.1%' 误中 3.10~3.14（动态下拉暴露细粒度版本后必须精确）。
            sql += " AND (m.version = ? OR m.version = ? OR m.version = ?)"
            params.extend([f"适配 {version}", f"更新于 {version} 时期", version])
    sql += f" ORDER BY {order}"
    if limit and limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        results.append({
            "id": d.get("steam_id") or d.get("id"),
            "title": d.get("display_title") or d.get("title"),
            "title_en": d.get("title_en") or d.get("title"),
            "subs": d.get("subscriptions") or 0,
            "url": d.get("url") or "",
            "author": d.get("author") or "",
            "summary": d.get("summary") or "",
            "tags": d.get("tags") or "",
            "preview": d.get("preview_url") or "",
            "status": d.get("status"),
            "version": d.get("version") or "",
            "score": calc_score(d.get("subscriptions"), d.get("favorites")),
            "act": activity_of(d.get("time_updated")),
        })
    return results


def get_detail(game_id, steam_id, db=None):
    if db is None:
        db = get_db(game_id)
    conn = db.conn
    row = conn.execute(
        "SELECT * FROM mods WHERE game_id=? AND steam_id=?",
        (game_id, str(steam_id))).fetchone()
    if not row:
        return None
    m = dict(row)
    trans = {f: t for f, t in conn.execute(
        "SELECT field, zh_text FROM translations WHERE mod_id=?", (m["id"],)).fetchall()}
    compat_row = conn.execute(
        "SELECT * FROM compat WHERE mod_id=?", (m["id"],)).fetchone()
    compat = dict(compat_row) if compat_row else None
    community = conn.execute(
        "SELECT * FROM community WHERE mod_id=?", (m["id"],)).fetchone()
    features = []
    if "features" in trans:
        try:
            features = json.loads(trans["features"])
        except Exception:
            pass
    ts = int(m.get("time_updated") or 0)
    updated = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "未知"
    fetched = str(m.get("fetched_at") or "")[:10]   # 库里已是 YYYY-MM-DD 日期串
    cfg = get_cfg(game_id)
    required = json.loads(m.get("required_dlcs") or "[]")
    optional = json.loads(m.get("optional_dlcs") or "[]")
    dlc_map = {d.app_id: d for d in cfg.load_dlcs()}
    # 汉化包（该 MOD 对应的汉化包记录）
    from core.localization_matcher import LocalizationMatcher
    matcher = LocalizationMatcher(cfg)
    localizations = [{
        "loc_id": l.get("loc_id", ""),
        "name": l.get("name", ""),
        "author": l.get("author", ""),
        "target_version": l.get("target_version", ""),
        "source": l.get("source", ""),
        "source_url": l.get("source_url", ""),
        "status": l.get("status", "not_downloaded"),
    } for l in matcher.find_for_mod(str(m.get("steam_id", "")))]
    return {
        "id": m.get("steam_id"),
        "title": trans.get("title", m.get("title_en") or m.get("title")),
        "title_en": m.get("title_en") or m.get("title"),
        "author": m.get("author") or "",
        "subs": m.get("subscriptions") or 0,
        "fav": m.get("favorites") or 0,
        "tags": m.get("tags") or "",
        "url": m.get("url") or "",
        "updated": updated,
        "fetched": fetched,
        "preview": m.get("preview_url") or "",
        "score": calc_score(m.get("subscriptions"), m.get("favorites")),
        "act": activity_of(m.get("time_updated")),
        "stale_notice": stale_notice_of(m),
        "like_ratio": round((m.get("favorites") or 0) / (m.get("subscriptions") or 1) * 100, 1)
                      if m.get("subscriptions") else 0,
        "status": m.get("status"),
        "version": m.get("version") or "",
        "summary": trans.get("summary", ""),
        "description": trans.get("description", ""),
        "features": features,
        "gameplay": trans.get("gameplay", ""),
        "reviews": trans.get("reviews", ""),
        "required_dlcs": [{"app_id": d, "name": dlc_map.get(d).name_zh if dlc_map.get(d) else d}
                          for d in required],
        "optional_dlcs": [{"app_id": d, "name": dlc_map.get(d).name_zh if dlc_map.get(d) else d}
                          for d in optional],
        "localizations": localizations,
        "compat": {
            "conflicts": json.loads(compat["conflicts"]) if compat and compat.get("conflicts") else [],
            "requires": json.loads(compat["requires"]) if compat and compat.get("requires") else [],
            "best_with": json.loads(compat["best_with"]) if compat and compat.get("best_with") else [],
            "notes": compat["notes"] if compat else "",
            "has_patches": json.loads(compat["has_patches"]) if compat and compat.get("has_patches") else [],
        } if compat else None,
        "community": dict(community) if community else None,
    }


def get_categories(game_id, db=None):
    if db is None:
        db = get_db(game_id)
    cfg = get_cfg(game_id)
    rows = db.conn.execute(
        "SELECT tags FROM mods WHERE game_id=? AND tags != ''", (game_id,)).fetchall()
    counter = {}
    for (tags,) in rows:
        for t in tags.split(","):
            t = t.strip()
            if t:
                counter[t] = counter.get(t, 0) + 1
    return [{"tag": k, "tag_zh": cfg.tag_zh(k), "count": v}
            for k, v in sorted(counter.items(), key=lambda x: -x[1])]


def get_versions(game_id, db=None):
    """版本筛选选项：从库中 version 字段提取去重版本号（避免前端硬编码）。

    version 存储形如「适配 4.4」/「更新于 3.4 时期」，此处提取纯版本号
    并按数值降序返回，附带代号名（来自游戏配置 VERSION_NAMES）与计数。
    """
    if db is None:
        db = get_db(game_id)
    cfg = get_cfg(game_id)
    names = getattr(cfg, "VERSION_NAMES", {}) or {}
    rows = db.conn.execute(
        "SELECT version, COUNT(*) AS n FROM mods "
        "WHERE game_id=? AND version IS NOT NULL AND version != '' "
        "GROUP BY version", (game_id,)).fetchall()
    buckets = {}
    for r in rows:
        m = re.match(r"^(?:适配|更新于)\s*(\d+(?:\.\d+)*(?:\.x)?)", r["version"])
        if not m:
            continue
        v = m.group(1)
        buckets[v] = buckets.get(v, 0) + r["n"]

    def vkey(v):
        parts = []
        for p in v.split("."):
            parts.append(99 if p == "x" else int(p))
        return tuple(parts)

    out = [{"v": v,
            "label": f"{v} {names[v]}" if v in names else v,
            "count": n}
           for v, n in sorted(buckets.items(), key=lambda x: (-vkey(x[0])[0], -vkey(x[0])[1]))]
    return {"versions": out}


def get_picks(game_id, db=None):
    """新手精选推荐：读 data/<game>/beginner_picks.json（人工/社区核实清单），
    与库内 MOD 信息联表返回（缺库的条目跳过，保证不留死链）。"""
    if db is None:
        db = get_db(game_id)
    cfg = get_cfg(game_id)
    data = cfg.load_json("beginner_picks.json", {}) or {}
    out = []
    for p in data.get("picks", []):
        m = db.get_mod_by_steam_id(str(p.get("steam_id", "")))
        if not m:
            continue
        t = db.get_translations(m["id"])
        out.append({
            "steam_id": m.get("steam_id"),
            "title": t.get("title") or m.get("title_en") or m.get("title"),
            "summary": t.get("summary", ""),
            "subs": m.get("subscriptions") or 0,
            "version": m.get("version") or "",
            "preview": m.get("preview_url") or "",
            "reason": p.get("reason", ""),
            "source": p.get("source", ""),
            "source_url": p.get("source_url", ""),
        })
    return {"note": data.get("note", ""), "picks": out}


def activity_of(ts):
    """P6 活跃徽章：按最近一次更新距今天数分三档。
    只陈述「作者最近有没有动作」，不推断兼容性（那是 versionRisk 的职责）。"""
    ts = int(ts or 0)
    if not ts:
        return None
    days = max(0, int((time.time() - ts) / 86400))
    if days <= 180:
        return {"lvl": "active", "days": days}
    if days <= 540:
        return {"lvl": "slow", "days": days}
    return {"lvl": "stale", "days": days}


def stale_notice_of(m):
    """内容时效提示（数据真实原则）：翻译确认后 MOD 又更新，或原文 hash 已变（stale 标记）→
    中文内容可能滞后于最新版本。"""
    conf = str(m.get("translation_confirmed_at") or "")
    tu = int(m.get("time_updated") or 0)
    if int(m.get("translation_stale") or 0) == 1:
        return {"reason": "stale", "confirmed_at": conf, "updated": ""}
    if not conf or not tu:
        return None
    try:
        update_day = time.strftime("%Y-%m-%d", time.localtime(tu))
        if update_day <= conf:  # 按日粒度比较，同日更新不误报
            return None
        return {"reason": "updated", "confirmed_at": conf, "updated": update_day}
    except (ValueError, OSError):
        return None


_TERM_CACHE = {}


def term_variants(game_id, word):
    """term_list 驱动的同义词扩展：查询词全等命中某术语的 canonical/别名 → 返回整组变体。"""
    if game_id not in _TERM_CACHE:
        cache = {}
        p = os.path.join(BASE, "games", game_id, "term_list.json")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    for t in json.load(f).get("terms", []):
                        group = [t["canonical"]] + list(t.get("aliases", []))
                        for v in group:
                            cache[v] = group
            except (ValueError, OSError):
                pass
        _TERM_CACHE[game_id] = cache
    return _TERM_CACHE[game_id].get(word, [word])


def get_gems(game_id, db=None):
    """P5 遗珠榜：纯库内数据计算，无人工编辑。
    遴选逻辑——收藏是玩家玩过之后的主动认可，收藏率（收藏/订阅）显著高于
    大盘而订阅量进不了头部，大概率是曝光不足而非质量不足。
    条件：300 < 订阅 < 30000，收藏率 ≥ 15%，近 18 个月仍有更新（排除弃坑）。"""
    if db is None:
        db = get_db(game_id)
    conn = db.conn
    cutoff = int(time.time()) - 540 * 86400
    rows = conn.execute("""
        SELECT m.*, COALESCE(tsum.zh_text, '') as summary,
               COALESCE(ttitle.zh_text, m.title_en) as display_title
        FROM mods m
        LEFT JOIN translations tsum ON tsum.mod_id = m.id AND tsum.field = 'summary'
        LEFT JOIN translations ttitle ON ttitle.mod_id = m.id AND ttitle.field = 'title'
        WHERE m.game_id=? AND m.subscriptions > 300 AND m.subscriptions < 30000
              AND m.favorites * 1.0 / m.subscriptions >= 0.15
              AND m.time_updated > ?
        ORDER BY m.favorites DESC LIMIT 24
    """, (game_id, cutoff)).fetchall()
    gems = []
    for r in rows:
        d = dict(r)
        subs = max(d.get("subscriptions") or 0, 1)
        ratio = (d.get("favorites") or 0) * 1.0 / subs
        gems.append({
            "id": d.get("steam_id"),
            "title": d.get("display_title") or d.get("title_en") or d.get("title"),
            "summary": d.get("summary") or "",
            "subs": d.get("subscriptions") or 0,
            "favs": d.get("favorites") or 0,
            "ratio": round(ratio, 3),
            "version": d.get("version") or "",
            "preview": d.get("preview_url") or "",
            "act": activity_of(d.get("time_updated")),
            "score": calc_score(d.get("subscriptions"), d.get("favorites")),
        })
    return {"count": len(gems), "gems": gems}


def _norm_name(t: str) -> str:
    """与 mine_compat.py 同源的标题规范化（用于兼容条目 ↔ MOD 匹配）"""
    t = (t or "").lower()
    t = re.sub(r"\d+\.\d+(\.\d+)*", " ", t)
    t = re.sub(r"[^\w\u4e00-\u9fff]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def conflict_check(game_id, ids, db=None):
    """清单冲突检测（P7）：给定 steam_id 列表，输出
    1) 清单内两两冲突（compat.conflicts 条目解析到清单内另一成员）
    2) 缺失依赖（compat.requires 指向的 MOD 不在清单中）
    兼容数据来自描述挖掘 + 手工整理，覆盖有限——响应中如实提示。"""
    if db is None:
        db = get_db(game_id)
    ids = list(dict.fromkeys(str(i).strip() for i in ids if str(i).strip().isdigit()))
    mods = {}
    for sid in ids:
        m = db.get_mod_by_steam_id(sid)
        if m:
            mods[sid] = m

    def brief(m):
        t = db.get_translations(m["id"])
        return {"id": m.get("steam_id"),
                "title": t.get("title") or m.get("title_en") or m.get("title"),
                "subs": m.get("subscriptions") or 0}

    # 名字 → steam_id（用于把 compat 条目解析到清单成员）
    name_map = {}
    for sid, m in mods.items():
        for t in filter(None, [m.get("title_en"), m.get("title")]):
            nn = _norm_name(t)
            if nn:
                name_map.setdefault(nn, sid)

    def resolve_target(entry, self_sid):
        """compat 条目 → 清单内目标 sid；解析不到返回 None"""
        if not isinstance(entry, dict):
            return None
        eid = str(entry.get("id") or "").strip()
        if eid.isdigit() and eid in mods and eid != self_sid:
            return eid
        name = str(entry.get("name") or "")
        nn = _norm_name(name)
        if nn in name_map and name_map[nn] != self_sid:
            return name_map[nn]
        if len(nn) >= 10:                      # 长名模糊包含（≥10 字符防误配）
            for k, v in name_map.items():
                if v != self_sid and (nn in k or k in nn):
                    return v
        return None

    conflicts, seen_pairs = [], set()
    missing_requires = []
    known = 0
    for sid, m in mods.items():
        c = db.get_compat(m["id"])
        if not c:
            continue
        known += 1
        for entry in (c.get("conflicts") or []):
            tgt = resolve_target(entry, sid)
            if not tgt:
                continue
            name = entry.get("name") if isinstance(entry, dict) else str(entry)
            note = (entry.get("note") if isinstance(entry, dict) else "") or name
            pair = tuple(sorted([sid, tgt]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            conflicts.append({"a": brief(mods[pair[0]]), "b": brief(mods[pair[1]]), "note": note})
        for entry in (c.get("requires") or []):
            name = str(entry.get("name") or "") if isinstance(entry, dict) else str(entry)
            if not name:
                continue
            tgt = resolve_target(entry, sid)
            if tgt is None:                     # 依赖的 MOD 不在清单中
                missing_requires.append({"mod": brief(m), "require": name})

    conflicts.sort(key=lambda x: -(x["a"]["subs"] + x["b"]["subs"]))
    return {
        "checked": len(mods),
        "known_compat": known,
        "conflicts": conflicts,
        "missing_requires": missing_requires[:20],
        "coverage_note": "兼容数据来自 MOD 描述挖掘与人工整理，覆盖有限——无警告不代表实际无冲突，装后请进游戏验证。",
    }


def get_stats(game_id, db=None):
    if db is None:
        db = get_db(game_id)
    conn = db.conn
    total = conn.execute("SELECT COUNT(*) FROM mods WHERE game_id=?", (game_id,)).fetchone()[0]
    subs = conn.execute(
        "SELECT COALESCE(SUM(subscriptions),0) FROM mods WHERE game_id=?",
        (game_id,)).fetchone()[0]
    translated = conn.execute(
        "SELECT COUNT(*) FROM mods WHERE game_id=? AND translated=1",
        (game_id,)).fetchone()[0]
    return {"total": total, "subs": subs, "translated": translated}


def get_local(game_id):
    """本地 MOD 列表（调用扫描器读 local.db）"""
    from core.local_scanner import LocalScanner
    cfg = get_cfg(game_id)
    scanner = LocalScanner(cfg)
    mods = scanner.list_local()
    scanner.close()
    return mods


def get_localizations(game_id, db=None):
    """汉化包数据库（localization.json + 关联 MOD 信息）"""
    from core.localization_matcher import LocalizationMatcher
    cfg = get_cfg(game_id)
    matcher = LocalizationMatcher(cfg)
    if db is None:
        db = get_db(game_id)
    locs = []
    for loc in matcher.all():
        mod = db.get_mod_by_steam_id(str(loc.get("mod_steam_id", "")))
        locs.append({
            "mod_steam_id": loc.get("mod_steam_id", ""),
            "loc_id": loc.get("loc_id", ""),
            "name": loc.get("name", ""),
            "author": loc.get("author", ""),
            "target_version": loc.get("target_version", ""),
            "source": loc.get("source", ""),
            "source_url": loc.get("source_url", ""),
            "status": loc.get("status", "not_downloaded"),
            "mod_title": mod.get("title_en") if mod else "",
            "mod_subs": mod.get("subscriptions") or 0 if mod else 0,
            "mod_status": mod.get("status") if mod else "",
        })
    # 按 MOD 订阅量降序
    locs.sort(key=lambda x: x["mod_subs"], reverse=True)
    return locs


def get_trend(game_id, db=None):
    """订阅热度趋势：首末快照对比，返回各 MOD 涨跌（按涨跌排序）"""
    if db is None:
        db = get_db(game_id)
    conn = db.conn
    # 确保 trend 表存在（可能还没快照过）
    conn.execute("""CREATE TABLE IF NOT EXISTS trend (
        steam_id TEXT NOT NULL, date TEXT NOT NULL, subs INTEGER DEFAULT 0,
        PRIMARY KEY (steam_id, date))""")
    dates = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM trend ORDER BY date").fetchall()]
    if len(dates) < 2:
        return {"dates": dates, "mods": [],
                "note": "暂无趋势数据（需至少 2 天快照）。请运行 python -m core.cli update 每日生成，"
                        "或手动执行 scripts/snapshot_trend.py"}
    first, last = dates[0], dates[-1]
    rows = conn.execute("""
        SELECT t.steam_id, t.subs AS first_subs, t2.subs AS last_subs,
               COALESCE(NULLIF(m.title, ''), m.title_en, t.steam_id) AS title
        FROM trend t
        JOIN trend t2 ON t2.steam_id = t.steam_id AND t2.date = ?
        LEFT JOIN mods m ON m.steam_id = t.steam_id AND m.game_id = ?
        WHERE t.date = ?
    """, (last, game_id, first)).fetchall()
    out = []
    for sid, first_subs, last_subs, title in rows:
        f, l = first_subs or 0, last_subs or 0
        out.append({
            "steam_id": str(sid),
            "title": title or str(sid),
            "first_subs": f,
            "last_subs": l,
            "diff": l - f,
            "pct": round((l - f) / f * 100, 2) if f else 0.0,
        })
    out.sort(key=lambda x: x["diff"], reverse=True)
    return {"dates": dates, "mods": out, "note": ""}


def get_dlc_missing(game_id, owned_app_ids, db=None):
    """根据用户已拥有的 DLC，检测哪些 MOD 缺 DLC。

    Args:
        game_id: 游戏标识
        owned_app_ids: 用户拥有的 DLC app_id 列表（str）
        db: 可选数据库连接

    Returns:
        {"warnings": [...], "total_mods": n, "missing_mods": n}
        warning: {"mod": {id,title,title_en,subs}, "missing": [{app_id,name,name_zh}]}
    """
    if db is None:
        db = get_db(game_id)
    conn = db.conn
    cfg = get_cfg(game_id)
    dlc_map = {d.app_id: d for d in cfg.load_dlcs()}
    owned = set(str(x) for x in (owned_app_ids or []))

    rows = conn.execute(
        "SELECT id, steam_id, title_en, subscriptions, optional_dlcs, required_dlcs "
        "FROM mods WHERE game_id=? AND (optional_dlcs != '[]' OR required_dlcs != '[]')",
        (game_id,)).fetchall()

    warnings = []
    for r in rows:
        m = dict(zip(["id", "steam_id", "title_en", "subscriptions", "optional_dlcs", "required_dlcs"], r))
        missing = []
        for app_id in json.loads(m["optional_dlcs"] or "[]") + json.loads(m["required_dlcs"] or "[]"):
            if str(app_id) not in owned:
                dlc = dlc_map.get(str(app_id))
                missing.append({
                    "app_id": str(app_id),
                    "name": dlc.name if dlc else str(app_id),
                    "name_zh": dlc.name_zh if dlc else str(app_id),
                })
        if missing:
            warnings.append({
                "mod": {
                    "id": m["steam_id"],
                    "title": m["title_en"],
                    "subs": m["subscriptions"] or 0,
                },
                "missing": missing,
            })
    warnings.sort(key=lambda w: -w["mod"]["subs"])
    return {"warnings": warnings, "total_mods": len(rows), "missing_mods": len(warnings)}


def _seo_escape(s) -> str:
    t = "" if s is None else str(s)
    return (
        t.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _seo_clip(s, n: int) -> str:
    t = "" if s is None else str(s).strip()
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


def render_mod_seo_html(game_id: str, d: dict, host: str) -> str:
    """服务端详情壳：meta + JSON-LD + 可读摘要 + 深链 SPA（SEO/分享用）。"""
    title = _seo_clip(d.get("title") or d.get("title_en") or "MOD", 60)
    summary = _seo_clip(d.get("summary") or d.get("description") or "", 160)
    desc = _seo_clip(
        d.get("summary") or d.get("gameplay") or d.get("description") or summary, 300
    )
    sid = re.sub(r"[^0-9]", "", str(d.get("id") or ""))
    author = _seo_clip(d.get("author_name") or d.get("author") or "", 80)
    subs = int(d.get("subscriptions") or 0)
    favs = int(d.get("fav") or d.get("favorites") or 0)
    updated = _seo_clip(d.get("updated") or "", 20)
    game_name = get_cfg(game_id).game_name if game_id in list_games() else game_id
    scheme = "https" if (self_host_https(host)) else "http"
    # host 可能带端口；规范 URL 用当前 Host
    base = f"{scheme}://{host}" if host else "http://150.158.24.195"
    page_url = f"{base}/mod/{game_id}/{sid}"
    spa_url = f"{base}/?game={game_id}&id={sid}"
    steam_url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={sid}"

    features = d.get("features") or []
    if isinstance(features, str):
        try:
            features = json.loads(features)
        except Exception:
            features = [features]
    feat_txt = "、".join(_seo_clip(f, 20) for f in features[:8])

    ld = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": d.get("title") or title,
        "alternateName": d.get("title_en") or "",
        "description": desc,
        "applicationCategory": "GameApplication",
        "operatingSystem": "PC",
        "url": page_url,
        "sameAs": steam_url,
        "author": {"@type": "Person", "name": author} if author else None,
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
    }
    if not ld.get("author"):
        ld.pop("author", None)
    # interactionStatistic 订阅量（近似热度）
    if subs:
        ld["interactionStatistic"] = {
            "@type": "InteractionCounter",
            "interactionType": "https://schema.org/SubscribeAction",
            "userInteractionCount": subs,
        }
    ld_json = json.dumps(ld, ensure_ascii=False)

    body_summary = _seo_escape(_seo_clip(d.get("summary") or "", 400))
    body_gameplay = _seo_escape(_seo_clip(d.get("gameplay") or "", 500))
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_seo_escape(title)} · {game_name} MOD 中文档案</title>
<meta name="description" content="{_seo_escape(summary)}">
<link rel="canonical" href="{_seo_escape(page_url)}">
<meta property="og:type" content="article">
<meta property="og:title" content="{_seo_escape(title)} · {game_name} MOD 中文档案">
<meta property="og:description" content="{_seo_escape(summary)}">
<meta property="og:url" content="{_seo_escape(page_url)}">
<meta property="og:site_name" content="Paradox MOD 中文知识库">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{_seo_escape(title)}">
<meta name="twitter:description" content="{_seo_escape(summary)}">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<script type="application/ld+json">{ld_json}</script>
<style>
:root {{ --bg:#05080f; --ink:#d7e6f5; --dim:#8aa0b8; --ac:#5ce1e6; }}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:"PingFang SC","Microsoft YaHei",sans-serif; background:var(--bg); color:var(--ink); line-height:1.7; padding:32px 18px 64px; }}
.wrap {{ max-width:720px; margin:0 auto; }}
.eyebrow {{ font-family:ui-monospace,Consolas,monospace; font-size:11px; letter-spacing:3px; color:var(--ac); margin-bottom:10px; }}
h1 {{ font-size:22px; letter-spacing:1px; margin-bottom:8px; color:#eaf6ff; }}
.meta {{ color:var(--dim); font-size:13px; margin-bottom:18px; }}
.panel {{ border:1px solid rgba(92,225,230,.2); background:rgba(8,18,32,.7); padding:16px 18px; margin-bottom:14px; }}
.panel h2 {{ font-size:13px; letter-spacing:2px; color:var(--ac); margin-bottom:8px; }}
.panel p {{ color:#b5c4d6; font-size:14px; white-space:pre-wrap; }}
.btns {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:20px; }}
.btns a {{ display:inline-block; padding:10px 16px; text-decoration:none; font-size:13px; border:1px solid rgba(92,225,230,.4); color:var(--ac); }}
.btns a.primary {{ background:rgba(92,225,230,.18); }}
.foot {{ margin-top:28px; font-size:12px; color:var(--faint,#5a6e88); }}
.foot a {{ color:var(--dim); }}
</style>
</head>
<body>
<div class="wrap">
  <div class="eyebrow">// {game_name} · MOD ARCHIVE</div>
  <h1>{_seo_escape(d.get("title") or title)}</h1>
  <div class="meta">
    {f"Steam ID {sid}" if sid else ""}
    {f" · 作者 {_seo_escape(author)}" if author else ""}
    {f" · 订阅 {subs:,}" if subs else ""}
    {f" · 收藏 {favs:,}" if favs else ""}
    {f" · 更新 {_seo_escape(updated)}" if updated else ""}
  </div>
  <div class="panel"><h2>简介</h2><p>{body_summary or "（暂无中文简介）"}</p></div>
  {"<div class=\"panel\"><h2>具体玩法</h2><p>" + body_gameplay + "</p></div>" if body_gameplay else ""}
  {"<div class=\"panel\"><h2>特色</h2><p>" + _seo_escape(feat_txt) + "</p></div>" if feat_txt else ""}
  <div class="btns">
    <a class="primary" href="{_seo_escape(spa_url)}">打开完整档案（搜索/星图/留言）</a>
    <a href="{_seo_escape(steam_url)}" rel="noopener">Steam 创意工坊</a>
  </div>
  <div class="foot">
    数据来自 Steam 创意工坊公开信息 · 中文由 AI 整理 ·
    <a href="/">返回知识库首页</a>
  </div>
</div>
</body>
</html>
"""


def self_host_https(host: str) -> bool:
    return False  # 当前公网仅 HTTP；域名+TLS 后可改


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"  # 禁用 keep-alive，避免连接复用挂起

    def log_message(self, fmt, *args):
        pass

    def _send_json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html):
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _mod_seo_not_found(self, game_id: str, sid: str) -> str:
        return (
            "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"UTF-8\">"
            "<title>未找到 MOD</title>"
            "<meta name=\"robots\" content=\"noindex\">"
            "</head><body style=\"font-family:sans-serif;background:#05080f;color:#d7e6f5;padding:40px\">"
            f"<h1>未找到 Steam ID {sid}</h1>"
            f"<p><a style=\"color:#5ce1e6\" href=\"/\">返回首页</a></p>"
            "</body></html>"
        )

    def do_GET(self):
        # 限流（公网防刷；本地使用不会触达 120 次/分钟）
        if not _rate_allow(self.client_address[0]):
            self._send_json({"error": "请求过于频繁，请稍后再试"}, 429)
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        q = urllib.parse.parse_qs(parsed.query)

        # 网页界面
        if path == "/":
            self._send_html(self._load_index())
            return
        # SEO 详情壳：/mod/<id> 或 /mod/<game>/<id>（可被搜索引擎抓取）
        seo_m = re.match(r"^/mod(?:/([a-z0-9_-]+))?/([0-9]{6,20})/?$", path)
        if seo_m:
            game_id = seo_m.group(1) or "stellaris"
            sid = seo_m.group(2)
            if game_id not in list_games():
                self._send_json({"error": "unknown game"}, 404)
                return
            db = None
            try:
                db = get_db(game_id)
                d = get_detail(game_id, sid, db)
                if not d:
                    html = self._mod_seo_not_found(game_id, sid)
                    data = html.encode("utf-8")
                    self.send_response(404)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("X-Robots-Tag", "noindex")
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self._send_html(render_mod_seo_html(game_id, d, self.headers.get("Host") or "150.158.24.195"))
            except Exception:
                traceback.print_exc()
                self._send_json({"error": "服务器内部错误"}, 500)
            finally:
                if db:
                    db.close()
            return
        # 白名单静态资源（favicon / OG 分享图 / 自托管字体）：固定文件名，防路径穿越
        _static_font = {
            "/fonts/orbitron-latin-700-normal.woff2": "font/woff2",
            "/fonts/rajdhani-latin-500-normal.woff2": "font/woff2",
            "/fonts/rajdhani-latin-600-normal.woff2": "font/woff2",
        }
        if path in ("/favicon.svg", "/og_card.png") or path in _static_font:
            rel = path.lstrip("/")
            fp = os.path.join(BASE, "web", rel)
            if os.path.exists(fp):
                if path in _static_font:
                    ctype = _static_font[path]
                elif path.endswith(".svg"):
                    ctype = "image/svg+xml"
                else:
                    ctype = "image/png"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(os.path.getsize(fp)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                with open(fp, "rb") as f:
                    self.wfile.write(f.read())
                return
            self._send_json({"error": "not found"}, 404)
            return
        # 游戏列表
        if path == "/api/games":
            games = [{"id": g, "name": get_cfg(g).game_name, "app_id": get_cfg(g).steam_app_id}
                     for g in list_games()]
            self._send_json({"games": games})
            return
        # 站点版本指纹（前端自动更新感知）
        if path == "/api/site/version":
            self._send_json(get_site_version())
            return

        # 带游戏前缀的 API: /api/<game>/xxx
        parts = path.strip("/").split("/")
        if len(parts) >= 3 and parts[0] == "api" and parts[1] in list_games():
            game_id = parts[1]
            api_name = parts[2]
            db = None
            try:
                if api_name == "comments":
                    # 读留言不依赖 mods 连接
                    sid = q.get("id", [""])[0]
                    n = int(q.get("n", ["50"])[0] or 50)
                    self._send_json(list_comments(game_id, sid, n))
                    return
                db = get_db(game_id)
                if api_name == "stats":
                    self._send_json(get_stats(game_id, db))
                elif api_name == "top":
                    n = int(q.get("n", ["0"])[0])
                    self._send_json({"results": search(game_id, "", limit=n, db=db)})
                elif api_name == "search":
                    kw = q.get("q", [""])[0]
                    sort = q.get("sort", ["subs"])[0]
                    n = int(q.get("n", ["0"])[0])
                    tag = q.get("tag", [""])[0]
                    version = q.get("version", [""])[0]
                    self._send_json({"results": search(game_id, kw, n, sort, tag, version, db=db)})
                elif api_name == "mod":
                    sid = q.get("id", [""])[0]
                    d = get_detail(game_id, sid, db)
                    if d:
                        self._send_json(d)
                    else:
                        self._send_json({"error": "not found"}, 404)
                elif api_name == "categories":
                    self._send_json({"categories": get_categories(game_id, db)})
                elif api_name == "versions":
                    self._send_json(get_versions(game_id, db))
                elif api_name == "picks":
                    self._send_json(get_picks(game_id, db))
                elif api_name == "gems":
                    self._send_json(get_gems(game_id, db))
                elif api_name == "conflict-check":
                    ids = q.get("ids", [""])[0].split(",")
                    self._send_json(conflict_check(game_id, ids, db))
                elif api_name == "local":
                    self._send_json({"local": get_local(game_id)})
                elif api_name == "localizations":
                    self._send_json({"localizations": get_localizations(game_id, db)})
                elif api_name == "trend":
                    self._send_json(get_trend(game_id, db))
                elif api_name == "dlcs":
                    cfg = get_cfg(game_id)
                    dlcs = [{"app_id": d.app_id, "name": d.name, "name_zh": d.name_zh}
                            for d in cfg.load_dlcs()]
                    self._send_json({"dlcs": dlcs})
                elif api_name == "dlc-missing":
                    owned = q.get("owned", [""])[0].split(",") if q.get("owned") else []
                    self._send_json(get_dlc_missing(game_id, owned, db=db))
                else:
                    self._send_json({"error": f"unknown api: {api_name}"}, 404)
            except Exception:
                # 详情只进服务端日志，不回传客户端（公网部署防内部信息泄漏）
                traceback.print_exc()
                self._send_json({"error": "服务器内部错误"}, 500)
            finally:
                if db:
                    db.close()
            return

        self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        if not _rate_allow(self.client_address[0]):
            self._send_json({"error": "请求过于频繁，请稍后再试"}, 429)
            return
        if not _post_rate_allow(self.client_address[0]):
            self._send_json({"error": "提交过于频繁，请稍后再试"}, 429)
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        parts = path.strip("/").split("/")
        # /api/<game>/comments → 3 段
        if not (len(parts) == 3 and parts[0] == "api" and parts[1] in list_games()
                and parts[2] == "comments"):
            self._send_json({"error": "not found"}, 404)
            return
        game_id = parts[1]
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > 8192:
            self._send_json({"error": "请求体过大或为空"}, 400)
            return
        try:
            raw = self.rfile.read(length)
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send_json({"error": "JSON 解析失败"}, 400)
            return
        # 蜜罐：机器人填了 website 则假成功，不入库
        if str(body.get("website") or "").strip():
            self._send_json({"ok": True, "id": 0})
            return
        try:
            result = add_comment(
                game_id,
                body.get("steam_id"),
                body.get("name"),
                body.get("content"),
                self.client_address[0],
            )
            self._send_json({"ok": True, **result})
        except ValueError as e:
            self._send_json({"error": str(e)}, 400)
        except Exception:
            traceback.print_exc()
            self._send_json({"error": "服务器内部错误"}, 500)

    def _load_index(self):
        idx = os.path.join(BASE, "web", "index_multigame.html")
        if os.path.exists(idx):
            with open(idx, encoding="utf-8") as f:
                return f.read()
        # 回退到单游戏版
        idx = os.path.join(BASE, "web", "index.html")
        with open(idx, encoding="utf-8") as f:
            return f.read()


def main():
    # 参数：python web_server_multigame.py [端口] [--no-browser] [--host 0.0.0.0]
    args_list = sys.argv[1:]
    host = "127.0.0.1"  # 默认仅本机（安全）；部署到云服务器用 --host 0.0.0.0
    if "--host" in args_list:
        i = args_list.index("--host")
        if i + 1 < len(args_list):
            host = args_list[i + 1]
            del args_list[i:i + 2]
    port = int(args_list[0]) if args_list and args_list[0].isdigit() else 8080
    auto_open = "--no-browser" not in args_list
    print(f"Paradox MOD 管理工具已启动: http://{host}:{port}")
    print(f"支持游戏: {list_games()}")
    # 绑定 host（默认 127.0.0.1 仅本机；云服务器用 0.0.0.0 对外开放）
    server = ThreadingHTTPServer((host, port), Handler)
    if auto_open:
        import threading
        import webbrowser

        def _open():
            import time
            time.sleep(1.2)
            try:
                webbrowser.open(f"http://127.0.0.1:{port}")
            except Exception:
                pass

        threading.Thread(target=_open, daemon=True).start()
        print("已尝试打开浏览器（如未自动打开，请手动访问 http://127.0.0.1:{port}）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
