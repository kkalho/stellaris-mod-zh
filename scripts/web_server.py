"""群星 Mod 查询工具 - 本地网页服务
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

# Steam 创意工坊标签英文 → 中文映射
TAG_ZH = {
    "Graphics": "画面美化",
    "Gameplay": "玩法内容",
    "Spaceships": "舰船模型",
    "Overhaul": "全面改造",
    "Events": "事件剧情",
    "Technologies": "科技研究",
    "Fixes": "Bug 修复",
    "Balance": "平衡性",
    "Galaxy Generation": "星系生成",
    "Species": "种族特质",
    "Military": "军事战斗",
    "Buildings": "建筑设施",
    "UI": "界面美化",
    "Translation": "翻译汉化",
    "Story": "故事剧情",
    "Flags": "旗帜徽章",
    "Sound": "音效音乐",
    "Utilities": "实用工具",
    "Performance": "性能优化",
    "Origins": "起源",
    "Traditions": "传统",
    "Ethics": "伦理国策",
    "Civics": "国策",
    "Ascension": "飞升",
    "Traits": "特质",
    "Portraits": "肖像立绘",
    "Shipsets": "舰船模型",
    "Map": "地图",
    "Skybox": "天空盒",
    "Name Lists": "命名表",
    "Music": "音乐",
    "Achievements": "成就",
    "Modding": "模组工具",
    "Diplomacy": "外交",
    "Economy": "经济",
    "War": "战争",
    "Crisis": "天灾危机",
    "Empire": "帝国",
    "Leader": "领袖",
    "Planet": "星球",
    "System": "星系",
    "Resource": "资源",
    "Federation": "联邦",
    "Edicts": "法令",
    "Policies": "政策",
    "Combat": "战斗",
    "Fleet": "舰队",
}


def get_db():
    return sqlite3.connect(DB_PATH)


def tags_to_zh(tags_str):
    """把 'Graphics,Gameplay' 转成 'Graphics（画面美化）, Gameplay（玩法内容）'"""
    if not tags_str:
        return ""
    out = []
    for t in tags_str.split(","):
        t = t.strip()
        if not t:
            continue
        zh = TAG_ZH.get(t)
        out.append(f"{t}（{zh}）" if zh else t)
    return ", ".join(out)


def search(keyword, limit=60, sort="subs", tag=None):
    """搜索 + 排序 + 标签过滤（同时匹配英文原名与中文字段，支持多词拆词搜索）"""
    conn = get_db()
    order_map = {
        "subs": "m.subscriptions DESC",
        "subs_asc": "m.subscriptions ASC",
        "updated": "m.time_updated DESC",
        "name": "m.title_en ASC",
    }
    order = order_map.get(sort, order_map["subs"])

    # 按空格拆词，每个词都必须匹配（AND 逻辑）
    words = [w for w in keyword.split() if w.strip()]
    sql = """
        SELECT m.steam_id, m.title, m.title_en, m.subscriptions, m.url, m.author,
               COALESCE(tsum.zh_text, '') as summary, m.tags,
               COALESCE(ttitle.zh_text, m.title_en) as display_title, m.preview_url, m.status
        FROM mods m
        LEFT JOIN translations tsum ON tsum.mod_id = m.id AND tsum.field = 'summary'
        LEFT JOIN translations ttitle ON ttitle.mod_id = m.id AND ttitle.field = 'title'
    """
    conditions, params = [], []
    for w in words:
        kw = f"%{w}%"
        conditions.append(
            "(m.title_en LIKE ? OR m.title LIKE ? OR m.steam_id LIKE ? "
            "OR ttitle.zh_text LIKE ? OR tsum.zh_text LIKE ?)")
        params.extend([kw, kw, kw, kw, kw])
    if not conditions:
        conditions.append("(m.title_en != '' OR m.title != '')")
    sql += " WHERE " + " AND ".join(conditions)
    if tag:
        sql += " AND m.tags LIKE ?"
        params.append(f"%{tag}%")
    sql += f" ORDER BY {order}"
    if limit and limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [{"id": r[0], "title": r[8], "title_en": r[2], "subs": r[3],
             "url": r[4], "author": r[5], "summary": r[6],
             "tags": r[7], "tags_zh": tags_to_zh(r[7]), "preview": r[9],
             "status": r[10] if len(r) > 10 else None} for r in rows]


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
    # 按数量排序，每个标签附带中文名
    return [{"tag": k, "tag_zh": TAG_ZH.get(k, ""), "count": v}
            for k, v in sorted(counter.items(), key=lambda x: -x[1])]


def get_stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM mods").fetchone()[0]
    subs = conn.execute("SELECT COALESCE(SUM(subscriptions),0) FROM mods").fetchone()[0]
    translated = conn.execute("SELECT COUNT(*) FROM mods WHERE translated=1").fetchone()[0]
    conn.close()
    return {"total": total, "subs": subs, "translated": translated}


def parse_compat(json_str):
    """解析 compat_json 字段为结构化数据"""
    if not json_str:
        return None
    try:
        return json.loads(json_str)
    except Exception:
        return None


def get_detail(steam_id):
    conn = get_db()
    row = conn.execute("""
        SELECT m.steam_id, m.title, m.title_en, m.author, m.subscriptions, m.favorites,
               m.tags, m.url, m.time_updated, m.preview_url, m.compat_json, m.status
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
        "tags_zh": tags_to_zh(row[6]),
        "url": row[7],
        "updated": updated,
        "preview": row[9] if len(row) > 9 else "",
        "summary": trans.get("summary", ""),
        "description": trans.get("description", ""),
        "features": features,
        "gameplay": trans.get("gameplay", ""),
        "reviews": trans.get("reviews", ""),
        "compat": parse_compat(row[10]) if len(row) > 10 else None,
        "status": row[11] if len(row) > 11 else None,
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
    print(f"群星 Mod 查询工具已启动: http://localhost:{port}")
    print("按 Ctrl+C 停止服务")
    if not no_browser:
        import threading, webbrowser
        threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
