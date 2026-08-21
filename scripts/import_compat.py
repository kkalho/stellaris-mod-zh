"""导入兼容性数据到数据库
用法: python import_compat.py translations/compat_top15.json
"""
import sys, io, json, os, sqlite3

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(base, "data", "stellaris_mods.db")


def main():
    files = sys.argv[1:]
    if not files:
        files = [os.path.join(base, "translations", f)
                 for f in os.listdir(os.path.join(base, "translations"))
                 if f.startswith("compat_") and f.endswith(".json")]
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for path in files:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for item in data.get("compat", []):
            sid = str(item["steam_id"])
            # 只保留需要的字段，序列化存储
            compat = {
                "requires": item.get("requires", []),
                "conflicts": item.get("conflicts", []),
                "best_with": item.get("best_with", []),
                "notes": item.get("notes", ""),
                "has_patches": item.get("has_patches", []),
            }
            r = c.execute("UPDATE mods SET compat_json=? WHERE steam_id=?", (json.dumps(compat, ensure_ascii=False), sid))
            print(f"  {sid}: {'✓' if r.rowcount else '✗ 未找到'}")
    conn.commit()
    n = c.execute("SELECT COUNT(*) FROM mods WHERE compat_json IS NOT NULL AND compat_json != ''").fetchone()[0]
    print(f"已导入兼容性数据的 Mod: {n}")
    conn.close()


if __name__ == "__main__":
    main()
