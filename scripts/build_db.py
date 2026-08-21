"""构建知识库 SQLite 数据库：导入抓取的详情数据
用法: python build_db.py
输出: data/stellaris_mods.db
表:
  mods       - Mod 元数据（名称/作者/订阅数/标签/更新时间）
  translations - 中英对照翻译（mod_id + field + zh_text）
"""
import sys, io, json, os, sqlite3, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(base, "data", "stellaris_mods.db")


def init_db(conn):
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS mods (
        id            INTEGER PRIMARY KEY,
        steam_id      TEXT UNIQUE NOT NULL,
        title         TEXT NOT NULL,
        author        TEXT,
        author_name   TEXT,
        subscriptions INTEGER DEFAULT 0,
        favorites     INTEGER DEFAULT 0,
        time_created  INTEGER,
        time_updated  INTEGER,
        tags          TEXT,
        url           TEXT,
        description   TEXT,
        description_clean TEXT,
        translated    INTEGER DEFAULT 0,
        fetched_at    TEXT
    );
    CREATE TABLE IF NOT EXISTS translations (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        mod_id    INTEGER NOT NULL REFERENCES mods(id),
        field     TEXT NOT NULL DEFAULT 'description',
        zh_text   TEXT,
        quality   TEXT DEFAULT 'ai',
        updated_at TEXT,
        UNIQUE(mod_id, field)
    );
    CREATE INDEX IF NOT EXISTS idx_mods_title ON mods(title);
    CREATE INDEX IF NOT EXISTS idx_mods_subs ON mods(subscriptions DESC);
    """)
    conn.commit()


def main():
    with open(os.path.join(base, "data", "details.jsonl"), encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    c = conn.cursor()
    now = time.strftime("%Y-%m-%d")

    inserted = 0
    for r in rows:
        if r.get("result") != 1:
            continue
        steam_id = str(r.get("publishedfileid", ""))
        tags = ",".join(t.get("tag", "") for t in r.get("tags", []))
        url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={steam_id}"
        c.execute("""
            INSERT OR REPLACE INTO mods
            (steam_id, title, author, subscriptions, favorites,
             time_created, time_updated, tags, url, description, description_clean, fetched_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            steam_id, r.get("title", ""), r.get("creator", ""),
            r.get("subscriptions", 0), r.get("favorited", 0),
            r.get("time_created", 0), r.get("time_updated", 0),
            tags, url, r.get("description", ""), r.get("description_clean", ""), now,
        ))
        inserted += 1

    conn.commit()
    total = c.execute("SELECT COUNT(*) FROM mods").fetchone()[0]
    print(f"导入完成：{inserted} 条，库中共 {total} 个 Mod")
    conn.close()


if __name__ == "__main__":
    main()
