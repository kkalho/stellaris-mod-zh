"""导入翻译 JSON 到知识库
用法: python import_translations.py [翻译文件路径...]
每个翻译 JSON 结构见 translations/hot_top6_zh.json
"""
import sys, io, json, os, sqlite3, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(base, "data", "stellaris_mods.db")


def import_file(conn, path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    c = conn.cursor()
    now = time.strftime("%Y-%m-%d")
    count = 0
    for t in data.get("translations", []):
        sid = t["steam_id"]
        row = c.execute("SELECT id FROM mods WHERE steam_id=?", (sid,)).fetchone()
        if not row:
            print(f"  跳过（库中无此 Mod）: {sid}")
            continue
        mod_id = row[0]
        # 保留英文原名 title_en（搜索用），中文标题写入 translations 表
        # 写入翻译：标题、摘要、详细描述、玩法、玩家评价
        for field, key in [("title", "title_zh"), ("summary", "summary_zh"),
                           ("description", "description_zh"),
                           ("gameplay", "gameplay_zh"), ("reviews", "reviews_zh")]:
            if key in t and t[key]:
                c.execute("""
                    INSERT INTO translations (mod_id, field, zh_text, quality, updated_at)
                    VALUES (?,?,?,?,?)
                    ON CONFLICT(mod_id, field) DO UPDATE SET zh_text=excluded.zh_text, updated_at=excluded.updated_at
                """, (mod_id, field, t[key], "ai_reviewed", now))
        # 写入特性列表
        if "features_zh" in t:
            c.execute("""
                INSERT INTO translations (mod_id, field, zh_text, quality, updated_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT(mod_id, field) DO UPDATE SET zh_text=excluded.zh_text, updated_at=excluded.updated_at
            """, (mod_id, "features", json.dumps(t["features_zh"], ensure_ascii=False), "ai_reviewed", now))
        # 标记已翻译
        c.execute("UPDATE mods SET translated=1 WHERE id=?", (mod_id,))
        count += 1
    conn.commit()
    print(f"  {os.path.basename(path)}: 导入 {count} 条")


def main():
    conn = sqlite3.connect(DB_PATH)
    files = sys.argv[1:]
    if not files:
        files = [os.path.join(base, "translations", f)
                 for f in os.listdir(os.path.join(base, "translations"))
                 if f.endswith(".json")]
    for f in files:
        import_file(conn, f)
    c = conn.cursor()
    n = c.execute("SELECT COUNT(DISTINCT mod_id) FROM translations").fetchone()[0]
    print(f"知识库已翻译 Mod 数: {n}")
    conn.close()


if __name__ == "__main__":
    main()
