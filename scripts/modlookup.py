"""群星 Mod 中文手册 - 命令行查询工具
用法:
  python modlookup.py 巨构          # 按关键词搜索（中英文均可）
  python modlookup.py giga          # 英文关键词也行
  python modlookup.py --top 20      # 查看订阅量 Top 20
  python modlookup.py --id 1121692237  # 按 Steam ID 精确查询
  python modlookup.py --full giga   # 显示完整翻译（含全部描述）
"""
import sys, io, os, sqlite3, argparse, json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(base, "data", "stellaris_mods.db")


def get_db():
    return sqlite3.connect(DB_PATH)


def search(keyword, limit=10):
    conn = get_db()
    # 按空格拆词，每个词都必须匹配
    words = [w for w in keyword.split() if w.strip()]
    conditions, params = [], []
    for w in words:
        kw = f"%{w}%"
        conditions.append(
            "(m.title_en LIKE ? OR m.title LIKE ? OR m.steam_id LIKE ? "
            "OR ttitle.zh_text LIKE ? OR tsum.zh_text LIKE ?)")
        params.extend([kw, kw, kw, kw, kw])
    if not conditions:
        conditions.append("(m.title_en != '' OR m.title != '')")
    sql = """
        SELECT m.steam_id, m.title_en, m.subscriptions, m.url,
               COALESCE(tsum.zh_text, '') as summary,
               COALESCE(ttitle.zh_text, m.title_en) as display_title
        FROM mods m
        LEFT JOIN translations tsum ON tsum.mod_id = m.id AND tsum.field = 'summary'
        LEFT JOIN translations ttitle ON ttitle.mod_id = m.id AND ttitle.field = 'title'
        WHERE """ + " AND ".join(conditions) + """
        ORDER BY m.subscriptions DESC LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def get_by_id(steam_id):
    conn = get_db()
    row = conn.execute("""
        SELECT m.steam_id, m.title_en, m.author, m.subscriptions, m.favorites,
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
    # 显示标题：优先中文翻译标题，否则英文原名
    row = list(row)
    row[1] = trans.get("title", row[1])
    return {"meta": tuple(row), "trans": trans}


def fmt_time(ts):
    import datetime
    try:
        return datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
    except Exception:
        return "未知"


def show_list(rows):
    if not rows:
        print("未找到匹配的 Mod")
        return
    print(f"{'订阅数':>10} | Mod 名称")
    print("-" * 70)
    for sid, title_en, subs, url, summary, display_title in rows:
        print(f"{subs:>10,} | {display_title}")
        if summary:
            print(f"{'':>12} | 摘要: {summary[:80]}")
    print()
    print(f"共 {len(rows)} 条。用 --id <steam_id> 查看详情，--full <关键词> 查看完整翻译。")


def show_detail(sid, full=False):
    d = get_by_id(sid)
    if not d:
        print(f"未找到 ID 为 {sid} 的 Mod")
        return
    sid, title, author, subs, fav, tags, url, updated = d["meta"]
    t = d["trans"]
    print("=" * 70)
    print(f"📦 {title}")
    print(f"ID: {sid}")
    print(f"作者: {author}")
    print(f"订阅: {subs:,}  |  点赞: {fav:,}  |  更新: {fmt_time(updated)}")
    print(f"标签: {tags}")
    print(f"链接: {url}")
    print("=" * 70)
    if "summary" in t:
        print(f"\n【简介】{t['summary']}")
    if "features" in t:
        try:
            feats = json.loads(t["features"])
            print("\n【特色】")
            for f in feats:
                print(f"  • {f}")
        except Exception:
            pass
    if full and "description" in t:
        print(f"\n【详细介绍】\n{t['description']}")
    print()


def main():
    ap = argparse.ArgumentParser(description="群星 Mod 中文手册查询工具")
    ap.add_argument("keyword", nargs="?", help="搜索关键词（中英文均可）")
    ap.add_argument("--top", type=int, help="显示订阅量前 N 名")
    ap.add_argument("--id", help="按 Steam ID 查询详情")
    ap.add_argument("--full", nargs="?", const="__ALL__", help="显示完整翻译（含全部描述）")
    args = ap.parse_args()

    if args.id:
        show_detail(args.id, full=True)
    elif args.top:
        show_list(search("", limit=args.top))
    elif args.full and args.full != "__ALL__":
        rows = search(args.full, limit=5)
        if rows:
            show_detail(rows[0][0], full=True)
        else:
            print("未找到匹配的 Mod")
    elif args.keyword:
        show_list(search(args.keyword))
    else:
        ap.print_help()
        print("\n示例:")
        print("  python modlookup.py 巨构")
        print("  python modlookup.py giga")
        print("  python modlookup.py --top 20")
        print("  python modlookup.py --id 1121692237")


if __name__ == "__main__":
    main()
