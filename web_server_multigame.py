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
    GET /api/<game>/local       → 本地 MOD 列表
    GET /api/<game>/dlcs        → DLC 清单
"""
from __future__ import annotations

import datetime
import io
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import games.stellaris.config.game  # noqa: F401
import games.ck3.config.game  # noqa: F401
import games.hoi4.config.game  # noqa: F401
from core.game_config import get_game, list_games
from core.mod_db import ModDB

# 各游戏缓存（避免每次请求重建连接）
_DB_CACHE = {}


def get_db(game_id: str) -> ModDB:
    if game_id not in _DB_CACHE:
        cfg = get_game(game_id, BASE)
        _DB_CACHE[game_id] = ModDB(cfg)
    return _DB_CACHE[game_id]


def get_cfg(game_id: str):
    return get_game(game_id, BASE)


def calc_score(subs, fav):
    try:
        subs = int(subs or 0)
        fav = int(fav or 0)
        if subs <= 0:
            return 0.0
        ratio = fav / subs
        s = 4.0 + (min(ratio, 0.15) / 0.15) * 5.5
        if subs >= 100000:
            s += 0.5
        elif subs >= 50000:
            s += 0.3
        return round(min(s, 10.0), 1)
    except Exception:
        return 0.0


def search(game_id, keyword, limit=60, sort="subs", tag=None):
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
            "score": calc_score(d.get("subscriptions"), d.get("favorites")),
        })
    return results


def get_detail(game_id, steam_id):
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
        "summary": trans.get("summary", ""),
        "description": trans.get("description", ""),
        "features": features,
        "gameplay": trans.get("gameplay", ""),
        "reviews": trans.get("reviews", ""),
        "required_dlcs": [{"app_id": d, "name": dlc_map.get(d).name_zh if dlc_map.get(d) else d}
                          for d in required],
        "optional_dlcs": [{"app_id": d, "name": dlc_map.get(d).name_zh if dlc_map.get(d) else d}
                          for d in optional],
        "compat": {
            "conflicts": json.loads(compat["conflicts"]) if compat and compat.get("conflicts") else [],
            "requires": json.loads(compat["requires"]) if compat and compat.get("requires") else [],
            "best_with": json.loads(compat["best_with"]) if compat and compat.get("best_with") else [],
            "notes": compat["notes"] if compat else "",
            "has_patches": json.loads(compat["has_patches"]) if compat and compat.get("has_patches") else [],
        } if compat else None,
        "community": dict(community) if community else None,
    }


def get_categories(game_id):
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


def get_stats(game_id):
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


class Handler(BaseHTTPRequestHandler):
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
            try:
                if api_name == "stats":
                    self._send_json(get_stats(game_id))
                elif api_name == "top":
                    n = int(q.get("n", ["0"])[0])
                    self._send_json({"results": search(game_id, "", limit=n)})
                elif api_name == "search":
                    kw = q.get("q", [""])[0]
                    sort = q.get("sort", ["subs"])[0]
                    n = int(q.get("n", ["0"])[0])
                    tag = q.get("tag", [""])[0]
                    self._send_json({"results": search(game_id, kw, n, sort, tag)})
                elif api_name == "mod":
                    sid = q.get("id", [""])[0]
                    d = get_detail(game_id, sid)
                    if d:
                        self._send_json(d)
                    else:
                        self._send_json({"error": "not found"}, 404)
                elif api_name == "categories":
                    self._send_json({"categories": get_categories(game_id)})
                elif api_name == "local":
                    self._send_json({"local": get_local(game_id)})
                elif api_name == "dlcs":
                    cfg = get_cfg(game_id)
                    dlcs = [{"app_id": d.app_id, "name": d.name, "name_zh": d.name_zh}
                            for d in cfg.load_dlcs()]
                    self._send_json({"dlcs": dlcs})
                else:
                    self._send_json({"error": f"unknown api: {api_name}"}, 404)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
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
    port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8080
    print(f"Paradox MOD 管理工具已启动: http://localhost:{port}")
    print(f"支持游戏: {list_games()}")
    server = HTTPServer(("127.0.0.1", port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
