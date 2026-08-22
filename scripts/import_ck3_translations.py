"""导入 CK3 翻译 JSON 到知识库（新多游戏架构）

用法: python import_ck3_translations.py [翻译文件路径...]
翻译 JSON 格式见 translations/ck3_top30_zh.json:
  {"translations": [{"steam_id": "...", "title_zh": "...", "summary_zh": "...",
                     "description_zh": "...", "gameplay_zh": "...",
                     "features_zh": [...], "reviews_zh": "..."}]}
"""
import sys, io, json, os, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import games.ck3.config.game  # noqa: F401  触发注册
from core.game_config import get_game
from core.mod_db import ModDB


def import_file(db: ModDB, path: str):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    count = 0
    for t in data.get("translations", []):
        sid = str(t["steam_id"])
        mod = db.get_mod_by_steam_id(sid)
        if not mod:
            print(f"  跳过（库中无此 Mod）: {sid}")
            continue
        mod_id = mod["id"]
        # 中文标题写入 translations 表（title 字段，前端优先展示）；英文原名保留在 mods.title_en
        for field, key in [("title", "title_zh"), ("summary", "summary_zh"),
                           ("description", "description_zh"),
                           ("gameplay", "gameplay_zh"), ("reviews", "reviews_zh")]:
            if t.get(key):
                db.set_translation(mod_id, field, t[key], "ai_reviewed")
        if t.get("features_zh"):
            db.set_translation(mod_id, "features", json.dumps(t["features_zh"], ensure_ascii=False), "ai_reviewed")
        # 标记已翻译 + 中文标题覆盖显示名
        db.conn.execute("UPDATE mods SET translated=1, title=? WHERE id=?",
                        (t.get("title_zh") or mod["title"], mod_id))
        count += 1
    db.conn.commit()
    print(f"  {os.path.basename(path)}: 导入 {count} 条")


def main():
    cfg = get_game("ck3", BASE_DIR)
    db = ModDB(cfg)
    files = sys.argv[1:]
    if not files:
        files = [os.path.join(BASE_DIR, "translations", f)
                 for f in os.listdir(os.path.join(BASE_DIR, "translations"))
                 if f.endswith(".json") and "ck3" in f]
    for f in files:
        if os.path.exists(f):
            import_file(db, f)
    n = db.conn.execute("SELECT COUNT(DISTINCT mod_id) FROM translations").fetchone()[0]
    trans_mods = db.conn.execute(
        "SELECT COUNT(*) FROM mods WHERE game_id='ck3' AND translated=1").fetchone()[0]
    print(f"CK3 知识库翻译记录: {n} 条，已翻译 Mod: {trans_mods} 个")
    db.close()


if __name__ == "__main__":
    main()
