"""深度精做 wave 一键流水线（阶段化，每步内置对账，防跳步）

把 HANDOFF §5.2 的手动六步收敛为四个阶段命令，子智能体派工仍是 AI 会话行为、不在此脚本内：

    python scripts/run_wave.py export --start 401    # ① 导出任务包 + 串扰预扫 + 打印 A/B/C 分组
    （派 3 个子智能体写 partA/partB/partC；通道故障时主会话按补丁格式直做 partC1/partC2）
    python scripts/run_wave.py merge  --wave 9       # ② 校验分片 → 合并（兼容补丁格式）→ 门禁
    python scripts/run_wave.py import --wave 9       # ③ 门禁复核 → 导入 → 体检 → 厚度 → 译名报告
    python scripts/run_wave.py sync   --wave 9       # ④ 生成 cloud_sync_waveN.sh（真实 SHA+对账门槛）
    python scripts/run_wave.py archive --wave 9      # ⑤ 分片归档（公网复验通过后）

wave 编号 = (start-1)//50 + 1；文件名 deep_task_%03d.json。所有阶段「先对账再动手」，对不上即退出非 0。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DW = BASE_DIR / "translations" / "deep_wave"
GATE = BASE_DIR / "scripts" / "validate_translations.py"
VERIFIY = BASE_DIR / "scripts" / "verify_db.py"
TERMCHK = BASE_DIR / "scripts" / "check_terminology.py"
FIELDS = ("title_zh", "summary_zh", "description_zh", "gameplay_zh", "reviews_zh")


def run(py: str, *argv: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run([py, *argv], cwd=str(BASE_DIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr.rstrip(), file=sys.stderr)
        if check:
            raise SystemExit(f"✗ 子命令失败（exit {proc.returncode}）: {' '.join(argv)}")
    return proc


def wave_no(start: int) -> int:
    return (start - 1) // 50 + 1


def paths(wave: int) -> dict:
    n = f"{wave:03d}"
    return {
        "task": DW / f"deep_task_{n}.json",
        "merged": DW / f"deep_task_{n}_merged.json",
        "fix": DW / f"fix_crosstalk_{n}.json",
    }


def load_translations(p: Path) -> list[dict]:
    return json.loads(p.read_text(encoding="utf-8"))["translations"]


def cmd_export(args):
    start, end = args.start, args.start + 49
    wave = wave_no(start)
    tp = paths(wave)["task"]
    if tp.exists() and not args.force:
        raise SystemExit(f"✗ {tp.name} 已存在（--force 覆盖）。若为重跑请先确认旧包用途。")
    proc = subprocess.run([sys.executable, str(BASE_DIR / "scripts" / "export_deep_tasks.py"),
                           "--start", str(start), "--end", str(end)],
                          cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0 or not proc.stdout.strip():
        raise SystemExit(f"✗ 导出失败: {proc.stderr.strip()[:300]}")
    tp.write_text(proc.stdout, encoding="utf-8")
    ts = load_translations(tp)
    print(f"① 任务包 {tp.name}: {len(ts)} 条（目标 #{start}-{end}），{tp.stat().st_size//1024}KB")
    if len(ts) != 50:
        print(f"  ⚠ 实得 {len(ts)} ≠ 50（库中缺条的 MOD 已在 stderr 注明），派工前先看原因")

    sus = [(ts[i]["steam_id"], ts[i + 1]["steam_id"]) for i in range(len(ts) - 1)
           if ts[i].get("features_zh_current") and ts[i]["features_zh_current"] == ts[i + 1].get("features_zh_current")]
    print(f"  串扰预扫（相邻 features 相同）: {sus if sus else '无'}")

    bounds = [(0, 17, "A"), (17, 34, "B"), (34, len(ts), "C")]
    print("  分组（派工用，prompt 模板见 HANDOFF §5.2 / 历史提交）:")
    for lo, hi, name in bounds:
        seg = ts[lo:hi]
        print(f"    part{name}: 切片[{lo}:{hi}] {len(seg)} 条 = 目标 #{start+lo}-#{start+hi-1}"
              f"（首 {seg[0]['steam_id']} 末 {seg[-1]['steam_id']}）")
    for sid_pair in sus:
        print(f"  ⚠ 串扰嫌疑 {sid_pair}: 先核实原文并写 fix_crosstalk_{wave:03d}.json，再派工")


def _part_files(wave: int) -> list[Path]:
    n = f"{wave:03d}"
    found = sorted(DW.glob(f"deep_task_{n}_part*.json"))
    if not found:
        raise SystemExit(f"✗ 找不到 deep_task_{n}_part*.json——分片还没写")
    return found


def _assemble(wave: int) -> list[dict]:
    """合并：标准分片直接用；补丁分片（无 title_zh）按任务包拼装照抄字段。"""
    tp = paths(wave)["task"]
    task = load_translations(tp)
    by_id = {t["steam_id"]: t for t in task}
    out: dict[str, dict] = {}
    for pf in _part_files(wave):
        for t in load_translations(pf):
            sid = str(t["steam_id"])
            if sid not in by_id:
                raise SystemExit(f"✗ {pf.name} 含任务包之外的 steam_id: {sid}")
            if "title_zh" in t:  # 标准分片：整条采用
                out[sid] = {**t, "steam_id": sid}
            else:  # 补丁分片：只带重写字段，其余照抄任务包
                if out.get(sid, {}).get("title_zh"):
                    raise SystemExit(f"✗ {sid} 同时出现标准分片与补丁分片，先二选一")
                base = by_id[sid]
                merged = {"steam_id": sid}
                for f in FIELDS:
                    merged[f] = t[f] if f in t else base.get(f + "_current", "")
                feats = base.get("features_zh_current", "[]")
                merged["features_zh"] = json.loads(feats) if isinstance(feats, str) else feats
                out[sid] = merged
    ordered = [out[tk["steam_id"]] for tk in task if tk["steam_id"] in out]
    missing = [tk["steam_id"] for tk in task if tk["steam_id"] not in out]
    if missing:
        raise SystemExit(f"✗ 缺 {len(missing)} 条（分片没写全）: {missing[:5]}{'...' if len(missing) > 5 else ''}")
    if len(ordered) != len(task):
        raise SystemExit(f"✗ 合并 {len(ordered)} ≠ 任务包 {len(task)}")
    return ordered


def cmd_merge(args):
    wave = args.wave
    pp = paths(wave)
    ordered = _assemble(wave)
    bad = [t["steam_id"] for t in ordered if len(t.get("description_zh", "")) < 300 or len(t.get("gameplay_zh", "")) < 300]
    if bad:
        raise SystemExit(f"✗ {len(bad)} 条 description/gameplay 未达 300 字基准: {bad}")
    payload = {"game": "stellaris",
               "source": f"深度精做 wave{wave} 合并件（run_wave.py 生成）",
               "translations": ordered}
    pp["merged"].write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    gate_files = [str(p) for p in _part_files(wave)]
    if pp["fix"].exists():
        gate_files.append(str(pp["fix"]))
    print(f"② 合并件 {pp['merged'].name}: {len(ordered)} 条 → 门禁（含分片与修复文件）:")
    run(sys.executable, str(GATE), *gate_files)
    print("② 串扰检测（精确重复）:")
    run(sys.executable, str(BASE_DIR / "scripts" / "detect_crosstalk.py"),
        "--files", str(pp["merged"]))
    print(f"✓ merge 完成: {pp['merged'].stat().st_size//1024}KB")


def cmd_import(args):
    wave = args.wave
    pp = paths(wave)
    if not pp["merged"].exists():
        raise SystemExit("✗ 先跑 merge")
    merged_now = load_translations(pp["merged"])
    gate_files = [str(p) for p in _part_files(wave)]
    if pp["fix"].exists():
        gate_files.append(str(pp["fix"]))
    run(sys.executable, str(GATE), *gate_files)
    import_files = [str(p) for p in _part_files(wave)]
    if pp["fix"].exists():
        import_files.append(str(pp["fix"]))
    print(f"③ 导入（{len(import_files)} 个文件，门禁复核已过）:")
    run(sys.executable, str(BASE_DIR / "scripts" / "import_stellaris_translations.py"), *import_files)
    run(sys.executable, str(VERIFIY))
    run(sys.executable, str(TERMCHK), "--files", *[str(p) for p in _part_files(wave)])
    import sqlite3
    conn = sqlite3.connect(str(BASE_DIR / "data" / "stellaris" / "mods.db"))
    g = conn.execute("SELECT COUNT(*) FROM translations t JOIN mods m ON m.id=t.mod_id "
                     "WHERE m.game_id='stellaris' AND t.field='gameplay' AND length(t.zh_text)<100").fetchone()[0]
    d = conn.execute("SELECT COUNT(*) FROM translations t JOIN mods m ON m.id=t.mod_id "
                     "WHERE m.game_id='stellaris' AND t.field='description' AND length(t.zh_text)<150").fetchone()[0]
    conn.close()
    print(f"③ 厚度复测: gameplay<100字 全库余 {g}（本批前见 HANDOFF）；description<150字 余 {d}")
    print(f"✓ import 完成（合并件 {len(merged_now)} 条已与分片一致）。下一步: commit+push → sync → TAT → 公网复验 → archive")


def cmd_sync(args):
    wave = args.wave
    pp = paths(wave)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(BASE_DIR),
                         capture_output=True, text=True).stdout.strip()
    if not sha:
        raise SystemExit("✗ 不是 git 仓库？")
    dirty = subprocess.run(["git", "status", "--short"], cwd=str(BASE_DIR),
                           capture_output=True, text=True).stdout.strip()
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(pp["merged"].relative_to(BASE_DIR))],
                             cwd=str(BASE_DIR), capture_output=True, text=True).returncode == 0
    if not tracked:
        raise SystemExit("✗ 合并件还没提交（git add + commit + push 后再 sync）")
    if dirty:
        print(f"⚠ 工作区有未提交改动（不影响本同步，但请确认来源）:\n{dirty[:300]}")

    def minsize(p: Path) -> int:
        return max(400, p.stat().st_size // 2)

    fetches = [(pp["merged"], minsize(pp["merged"]))]
    if pp["fix"].exists():
        fetches.append((pp["fix"], minsize(pp["fix"])))
    lines = ["#!/bin/bash", f"# cloud_sync_wave{wave}.sh — 由 run_wave.py sync 生成（翻译轻量同步）",
             "set -e", "cd /opt/stellaris-mod-zh", f'SHA="{sha}"',
             "mkdir -p translations/deep_wave", "",
             "fetch() {", '  local rel="$1" min="$2"',
             '  for src in \\',
             f'    "https://cdn.jsdelivr.net/gh/kkalho/stellaris-mod-zh@${{SHA}}/${{rel}}" \\',
             '    "https://gh-proxy.com/https://raw.githubusercontent.com/kkalho/stellaris-mod-zh/${SHA}/${rel}" \\',
             f'    "https://cdn.jsdelivr.net/gh/kkalho/stellaris-mod-zh@${{SHA}}/${{rel}}"; do',
             '    echo "try: $src"',
             '    if curl -fsSL -m 40 -o "$rel" "$src"; then',
             '      size=$(stat -c%s "$rel" 2>/dev/null || echo 0)',
             '      if [ "$size" -ge "$min" ]; then echo "OK $rel=$size"; return 0; fi',
             '      echo "too small: $size < $min"',
             "    fi",
             "    sleep 2",
             "  done",
             '  echo "FETCH FAIL: $rel"; exit 1', "}", ""]
    for p, mn in fetches:
        rel = p.relative_to(BASE_DIR).as_posix()
        lines += [f'fetch "{rel}" {mn}', ""]
    check_py = " + ".join(f'len(json.load(open("{p.relative_to(BASE_DIR).as_posix()}", encoding="utf-8"))["translations"])'
                          for p, _ in fetches)
    expect = "50" if not pp["fix"].exists() else "52"
    lines += ["python3 - <<'PY'", "import json", f"assert {check_py} == {expect}, '条数对账失败'", 'print("sanity OK")', "PY", "",
              "/usr/bin/python3 scripts/import_stellaris_translations.py \\",
              "  " + " \\\n  ".join(f'"{p.relative_to(BASE_DIR).as_posix()}"' for p, _ in fetches), "",
              "sudo systemctl restart stellaris-mod", "sleep 3",
              'echo "=== stats ==="', 'curl -s -m 15 "http://127.0.0.1:8080/api/stellaris/stats"', "echo"]
    out = BASE_DIR / f"cloud_sync_wave{wave}.sh"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"④ 已生成 {out.name}（SHA={sha[:9]}…，门槛={[(p.name, mn) for p, mn in fetches]}）")
    print("  下一步（Git Bash）:")
    print(f'  SYS_PY="/c/Users/wangf/AppData/Local/Programs/Python/Python315/python.exe"')
    print(f'  "$SYS_PY" scripts/tat_sync.py --script cloud_sync_wave{wave}.sh   # 取 InvocationId')
    print(f'  "$SYS_PY" scripts/tat_sync.py --poll-inv <inv-xxx>                # 轮询结果')
    print("  公网复验后: git rm cloud_sync_wave*.sh && git commit（临时脚本用完即删），并跑 run_wave.py archive")


def cmd_archive(args):
    wave = args.wave
    files = _part_files(wave)
    (DW / "archive").mkdir(exist_ok=True)
    for p in files:
        subprocess.run(["git", "mv", str(p), str(DW / "archive" / p.name)], cwd=str(BASE_DIR), check=True)
    print(f"⑤ 已归档 {len(files)} 个分片到 deep_wave/archive/（保留任务包/合并件/修复件）")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="① 导出任务包+预扫+分组")
    e.add_argument("--start", type=int, required=True)
    e.add_argument("--force", action="store_true")
    m = sub.add_parser("merge", help="② 合并+门禁")
    m.add_argument("--wave", type=int, required=True)
    i = sub.add_parser("import", help="③ 导入+体检+厚度+译名")
    i.add_argument("--wave", type=int, required=True)
    s = sub.add_parser("sync", help="④ 生成云同步脚本")
    s.add_argument("--wave", type=int, required=True)
    a = sub.add_parser("archive", help="⑤ 分片归档")
    a.add_argument("--wave", type=int, required=True)
    args = ap.parse_args()
    {"export": cmd_export, "merge": cmd_merge, "import": cmd_import,
     "sync": cmd_sync, "archive": cmd_archive}[args.cmd](args)


if __name__ == "__main__":
    main()
