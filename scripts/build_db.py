"""构建知识库 SQLite 数据库：导入抓取的详情数据
用法: python build_db.py --force   （必须显式 --force 才会重建）
输出: data/stellaris_mods.db  ⚠️ 这是旧版单游戏库（坑 #10）！
表:
  mods       - Mod 元数据（名称/作者/订阅数/标签/更新时间/预览图）
  translations - 中英对照翻译（mod_id + field + zh_text）

数据源:
  1. data/details.jsonl          - 官方 API 完整详情（描述等）
  2. data/workshop_top1000.json  - 官方页面榜单数据（订阅数/评分/预览图，最新）

⚠️ 注意：
- 本脚本会 DROP 重建整库。现役数据库是 data/stellaris/mods.db（多游戏架构），
  日常维护请用 scripts/rebuild_all.py（收敛式重建，不丢标注）。
- 直接跑本脚本 + migrate_to_multigame.py 迁移，正是历史上
  「重建后 version/DLC 标注归零」事故（坑 #1）的触发链。
"""
import sys, io, json, os, sqlite3, time, re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(base, "data", "stellaris_mods.db")
DATA_DIR = os.path.join(base, "data")


def init_db(conn):
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS mods (
        id            INTEGER PRIMARY KEY,
        steam_id      TEXT UNIQUE NOT NULL,
        title         TEXT NOT NULL,
        title_en      TEXT,          -- 英文原名（搜索用）
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
        fetched_at    TEXT,
        preview_url   TEXT,
        compat_json   TEXT,
        status        TEXT,
        pinyin_idx    TEXT
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
    CREATE INDEX IF NOT EXISTS idx_mods_title_en ON mods(title_en);
    CREATE INDEX IF NOT EXISTS idx_mods_subs ON mods(subscriptions DESC);
    """)
    conn.commit()


def clean_bbcode(text):
    if not text:
        return ""
    text = re.sub(r"\[/?[a-zA-Z0-9=#\"' ]*\]", "", text)
    return text.strip()


def main():
    # 重建保护：本脚本 DROP 重建旧版整库，必须显式 --force
    if "--force" not in sys.argv:
        print("⛔ 拒绝执行：本脚本会 DROP 重建旧版单游戏库 data/stellaris_mods.db。\n"
              "   - 日常维护/数据修复请用: python scripts/rebuild_all.py（收敛式，不丢标注）\n"
              "   - 确实要重建旧库: python scripts/build_db.py --force")
        sys.exit(1)

    # 读取详情（官方 API 数据）
    details_path = os.path.join(DATA_DIR, "details.jsonl")
    rows = []
    if os.path.exists(details_path):
        with open(details_path, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]

    # 读取榜单（官方页面数据，含订阅数/评分/预览图）
    top_mods = {}
    top_path = os.path.join(DATA_DIR, "workshop_top1000.json")
    if os.path.exists(top_path):
        with open(top_path, encoding="utf-8") as f:
            for m in json.load(f).get("mods", []):
                top_mods[str(m.get("publishedfileid", ""))] = m

    # 保存已有翻译状态（避免重建丢失）
    old_translated = {}
    if os.path.exists(DB_PATH):
        try:
            conn_old = sqlite3.connect(DB_PATH)
            old_translated = {r[0]: 1 for r in conn_old.execute(
                "SELECT steam_id FROM mods WHERE translated=1")}
            conn_old.close()
        except Exception:
            pass

    conn = sqlite3.connect(DB_PATH)
    c0 = conn.cursor()
    c0.execute("DROP TABLE IF EXISTS mods")
    c0.execute("DROP TABLE IF EXISTS translations")
    conn.commit()
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
        title_en = r.get("title", "")
        # 从榜单补充订阅数/预览图（榜单数据更新）
        top = top_mods.get(steam_id, {})
        subs = top.get("subscriptions") or r.get("subscriptions", 0)
        fav = top.get("favorited") or r.get("favorited", 0)
        preview = top.get("preview_url") or r.get("preview_url", "")
        # 状态标记：deprecated/outdated 等
        status = None
        t_low = title_en.lower()
        if any(k in t_low for k in ("deprecated", "outdated", "do not use", "legacy",
                                     "on hold", "discontinued", "abandoned", "hiatus")):
            status = "deprecated"
        elif any(k in t_low for k in ("depricated", "old version", "2.x", "3.14 legacy")):
            status = "deprecated"
        c.execute("""
            INSERT OR REPLACE INTO mods
            (steam_id, title, title_en, author, subscriptions, favorites,
             time_created, time_updated, tags, url, description, description_clean,
             translated, fetched_at, preview_url, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            steam_id, title_en, title_en, r.get("creator", ""),
            subs, fav,
            r.get("time_created", 0), r.get("time_updated", 0),
            tags, url, r.get("description", ""), r.get("description_clean", ""),
            1 if steam_id in old_translated else 0, now, preview, status,
        ))
        inserted += 1

    conn.commit()
    total = c.execute("SELECT COUNT(*) FROM mods").fetchone()[0]
    trans = c.execute("SELECT COUNT(*) FROM mods WHERE translated=1").fetchone()[0]
    print(f"导入完成：{inserted} 条，库中共 {total} 个 Mod，已翻译标记 {trans}")
    conn.close()


if __name__ == "__main__":
    main()
