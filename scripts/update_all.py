"""一键重建知识库：抓取详情 → 建库 → 导入翻译
用法: python update_all.py [--no-fetch] [--sleep 20]
  --no-fetch  跳过抓取（只重建数据库和导入翻译）
"""
import sys, io, os, subprocess, argparse, json, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def run(script, *args):
    cmd = [PY, os.path.join(base, "scripts", script), *args]
    print(f"\n>>> 运行 {os.path.basename(script)} {' '.join(args)}")
    r = subprocess.run(cmd, cwd=base)
    if r.returncode != 0:
        print(f"!! {script} 失败（退出码 {r.returncode}）")
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true", help="跳过抓取详情")
    ap.add_argument("--sleep", type=float, default=20, help="抓取批次间隔秒数")
    args = ap.parse_args()

    if not args.no_fetch:
        run("auto_fetch.py", "--sleep", str(args.sleep), "--batch", "3")
    run("build_db.py")
    # 导入所有 translations/*.json
    tdir = os.path.join(base, "translations")
    files = [os.path.join(tdir, f) for f in sorted(os.listdir(tdir)) if f.endswith(".json")]
    if files:
        run("import_translations.py", *files)
    print("\n✅ 全部完成！数据库已重建并导入翻译。")


if __name__ == "__main__":
    main()
