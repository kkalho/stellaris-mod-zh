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


def search(keyword, limit=30):
    conn = get_db()
    kw = f"%{keyword}%"
    rows = conn.execute("""
        SELECT m.steam_id, m.title, m.subscriptions, m.url, m.author,
               COALESCE(t.zh_text, '') as summary
        FROM mods m
        LEFT JOIN translations t ON t.mod_id = m.id AND t.field = 'summary'
        WHERE m.title LIKE ? OR m.steam_id LIKE ?
        ORDER BY m.subscriptions DESC LIMIT ?
    """, (kw, kw, limit)).fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1].split(" (")[0], "subs": r[2],
             "url": r[3], "author": r[4], "summary": r[5]} for r in rows]


def get_detail(steam_id):
    conn = get_db()
    row = conn.execute("""
        SELECT m.steam_id, m.title, m.author, m.subscriptions, m.favorites,
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
    ts = int(row[7]) if row[7] else 0
    updated = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "未知"
    features = []
    if "features" in trans:
        try:
            features = json.loads(trans["features"])
        except Exception:
            pass
    return {
        "id": row[0],
        "title": row[1].split(" (")[0],
        "author": row[2],
        "subs": row[3],
        "fav": row[4],
        "tags": row[5],
        "url": row[6],
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
        if path == "/api/search":
            q = parse_qs(parsed.query).get("q", [""])[0]
            self._send_json({"results": search(unquote(q))})
        elif path == "/api/mod":
            sid = parse_qs(parsed.query).get("id", [""])[0]
            d = get_detail(sid)
            if d:
                self._send_json(d)
            else:
                self._send_json({"error": "not found"})
        elif path == "/api/top":
            n = int(parse_qs(parsed.query).get("n", ["30"])[0])
            self._send_json({"results": search("", limit=n)})
        else:
            # 静态文件
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
    print(f"群星 Mod 中文手册已启动: http://localhost:{PORT}")
    print("按 Ctrl+C 停止服务")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
