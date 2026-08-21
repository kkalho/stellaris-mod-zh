"""群星 Mod 中文手册 - 本地网页服务
用法: python web_server.py [端口]
默认端口 8080，浏览器打开 http://localhost:8080
"""
import sys, io, os, json, sqlite3, datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(base, "data", "stellaris_mods.db")
WEB_DIR = os.path.join(base, "web")

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080


def get_db():
    return sqlite3.connect(DB_PATH)


def search(keyword, limit=60, sort="subs", tag=None):
    """搜索 + 排序 + 标签过滤（同时匹配英文原名与中文字段）"""
    conn = get_db()
    kw = f"%{keyword}%"
    order_map = {
        "subs": "m.subscriptions DESC",
        "subs_asc": "m.subscriptions ASC",
        "updated": "m.time_updated DESC",
        "name": "m.title_en ASC",
    }
    order = order_map.get(sort, order_map["subs"])
    sql = """
        SELECT m.steam_id, m.title, m.title_en, m.subscriptions, m.url, m.author,
               COALESCE(tsum.zh_text, '') as summary, m.tags,
               COALESCE(ttitle.zh_text, m.title_en) as display_title
        FROM mods m
        LEFT JOIN translations tsum ON tsum.mod_id = m.id AND tsum.field = 'summary'
        LEFT JOIN translations ttitle ON ttitle.mod_id = m.id AND ttitle.field = 'title'
        WHERE (m.title_en LIKE ? OR m.title LIKE ?
               OR ttitle.zh_text LIKE ? OR tsum.zh_text LIKE ?
               OR m.steam_id LIKE ?)
    """
    params = [kw, kw, kw, kw, kw]
    if tag:
        sql += " AND m.tags LIKE ?"
        params.append(f"%{tag}%")
    sql += f" ORDER BY {order} LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [{"id": r[0], "title": r[8], "title_en": r[2], "subs": r[3],
             "url": r[4], "author": r[5], "summary": r[6], "tags": r[7]} for r in rows]


def get_categories():
    """统计各标签的 Mod 数量"""
    conn = get_db()
    rows = conn.execute("SELECT tags FROM mods").fetchall()
    conn.close()
    counter = {}
    for (tags,) in rows:
        if not tags:
            continue
        for t in tags.split(","):
            t = t.strip()
            if t:
                counter[t] = counter.get(t, 0) + 1
    # 按数量排序
    return [{"tag": k, "count": v} for k, v in sorted(counter.items(), key=lambda x: -x[1])]


def get_stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM mods").fetchone()[0]
    subs = conn.execute("SELECT COALESCE(SUM(subscriptions),0) FROM mods").fetchone()[0]
    translated = conn.execute("SELECT COUNT(*) FROM mods WHERE translated=1").fetchone()[0]
    conn.close()
    return {"total": total, "subs": subs, "translated": translated}


def get_detail(steam_id):
    conn = get_db()
    row = conn.execute("""
        SELECT m.steam_id, m.title, m.title_en, m.author, m.subscriptions, m.favorites,
               m.tags, m.url, m.time_updated
        FROM mods m WHERE m.steam_id = ?
    """, (str(steam_id),)).fetchone()
    if not row:
        conn.close()
        return None
    trans = {f: t for f, t in conn.execute(
        "SELECT field, zh_text FROM translations WHERE mod_id = (SELECT id FROM mods WHERE steam_id=?)",
        (str(steam_id),)).fetchall()}
    conn.close()
    ts = int(row[8]) if row[8] else 0
    updated = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "未知"
    features = []
    if "features" in trans:
        try:
            features = json.loads(trans["features"])
        except Exception:
            pass
    return {
        "id": row[0],
        "title": trans.get("title", row[2] if row[2] else row[1]),
        "title_en": row[2] if row[2] else row[1],
        "author": row[3],
        "subs": row[4],
        "fav": row[5],
        "tags": row[6],
        "url": row[7],
        "updated": updated,
        "summary": trans.get("summary", ""),
        "description": trans.get("description", ""),
        "features": features,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send_json(self, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        q = parse_qs(parsed.query)
        if path == "/api/search":
            kw = q.get("q", [""])[0]
            sort = q.get("sort", ["subs"])[0]
            tag = q.get("tag", [None])[0]
            limit = int(q.get("n", ["60"])[0])
            self._send_json({"results": search(unquote(kw), limit=limit, sort=sort, tag=tag)})
        elif path == "/api/mod":
            sid = q.get("id", [""])[0]
            d = get_detail(sid)
            if d:
                self._send_json(d)
            else:
                self._send_json({"error": "not found"})
        elif path == "/api/top":
            n = int(q.get("n", ["30"])[0])
            self._send_json({"results": search("", limit=n)})
        elif path == "/api/categories":
            self._send_json({"categories": get_categories()})
        elif path == "/api/stats":
            self._send_json(get_stats())
        else:
            if path == "/":
                path = "/index.html"
            fpath = os.path.join(WEB_DIR, path.lstrip("/"))
            if os.path.isfile(fpath):
                ctype = "text/html; charset=utf-8"
                if fpath.endswith(".css"):
                    ctype = "text/css; charset=utf-8"
                elif fpath.endswith(".js"):
                    ctype = "application/javascript; charset=utf-8"
                with open(fpath, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not Found")


if __name__ == "__main__":
    port = PORT
    # 支持 --no-browser 参数：不自动打开浏览器（供测试用）
    if "--no-browser" in sys.argv:
        no_browser = True
    else:
        no_browser = False
    print(f"群星 Mod 中文手册已启动: http://localhost:{port}")
    print("按 Ctrl+C 停止服务")
    if not no_browser:
        import threading, webbrowser
        threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
