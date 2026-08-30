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
    GET /api/<game>/local       → 本地 MOD 列表
    GET /api/<game>/localizations → 汉化包数据库
    GET /api/<game>/trend       → 订阅热度趋势（每日快照涨跌）
    GET /api/<game>/dlcs        → DLC 清单
"""
from __future__ import annotations

import datetime
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
        kw = f"%{w}%"
        conds.append("(m.title_en LIKE ? OR m.title LIKE ? OR m.steam_id LIKE ? "
                     "OR ttitle.zh_text LIKE ? OR tsum.zh_text LIKE ? OR m.pinyin_idx LIKE ?)")
        params.extend([kw] * 6)
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
        "preview": m.get("preview_url") or "",
        "score": calc_score(m.get("subscriptions"), m.get("favorites")),
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
        # 游戏列表
        if path == "/api/games":
            games = [{"id": g, "name": get_cfg(g).game_name, "app_id": get_cfg(g).steam_app_id}
                     for g in list_games()]
            self._send_json({"games": games})
            return

        # 带游戏前缀的 API: /api/<game>/xxx
        parts = path.strip("/").split("/")
        if len(parts) >= 3 and parts[0] == "api" and parts[1] in list_games():
            game_id = parts[1]
            api_name = parts[2]
            db = None
            try:
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
