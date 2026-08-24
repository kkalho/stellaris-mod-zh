"""重建群星 pinyin_idx 拼音搜索索引

问题：原索引只含英文标题拼音，中文译名（如「巨构工程」）的拼音（jugou）
没有进去，导致拼音搜索 jujgong/jugou 无结果。

修复：合并 英文标题 + 中文译名 + 首字母缩写 生成索引。
用法：python scripts/rebuild_pinyin_idx.py
"""
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pypinyin import lazy_pinyin, Style

DB = os.path.join(os.path.dirname(__file__), "..", "data", "stellaris", "mods.db")


def build_index(title_en: str, title_zh: str) -> str:
    """生成拼音索引：英文拼音 + 中文译名拼音（全拼 + 首字母）。"""
    parts = []
    if title_en:
        parts.append("".join(lazy_pinyin(title_en)).lower())
    if title_zh:
        parts.append("".join(lazy_pinyin(title_zh)).lower())
        parts.append("".join(lazy_pinyin(title_zh, style=Style.FIRST_LETTER)).lower())
    return " ".join(p for p in parts if p)


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute(
        """SELECT m.id, m.title AS title_en,
                  (SELECT zh_text FROM translations t
                   WHERE t.mod_id = m.id AND t.field = 'title' LIMIT 1) AS title_zh
           FROM mods m"""
    ).fetchall()

    updated = 0
    for r in rows:
        idx = build_index(r["title_en"] or "", r["title_zh"] or "")
        cur.execute("UPDATE mods SET pinyin_idx=? WHERE id=?", (idx, r["id"]))
        updated += 1

    conn.commit()

    # 验证
    for q in ["jujgong", "jugou", "giga", "nsc", "nvpu"]:
        cnt = cur.execute(
            "SELECT COUNT(*) FROM mods WHERE pinyin_idx LIKE ?", (f"%{q}%",)
        ).fetchone()[0]
        print(f"  拼音「{q}」命中 {cnt} 个")

    # 抽查巨构
    row = cur.execute(
        "SELECT title, pinyin_idx FROM mods WHERE title LIKE '%Gigastructural%' LIMIT 1"
    ).fetchone()
    print(f"  抽查: {row['title'][:30]} → {row['pinyin_idx'][:80]}...")
    conn.close()
    print(f"重建完成: {updated} 个 MOD")


if __name__ == "__main__":
    main()
