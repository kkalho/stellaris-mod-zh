"""每周增量维护入口：一次跑完「体检 → 腐化检测 → 新入榜/薄字段报告」。

用法:
    python scripts/weekly_maintenance.py
    python scripts/weekly_maintenance.py --json          # 机器可读摘要
    python scripts/weekly_maintenance.py --mark-stale    # 同时写入 translation_stale

配合 docs/ops/stale-retranslate-checklist.md 使用：
本脚本只做「发现缺口」；翻译与上云仍按清单 C–G 人工/子智能体执行。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_py(script: str, *args: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, os.path.join(BASE_DIR, "scripts", script), *args]
    return subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="每周增量维护：体检 + 腐化 + 扩充缺口报告")
    ap.add_argument("--json", action="store_true", help="输出 JSON 摘要（供自动化）")
    ap.add_argument("--mark-stale", action="store_true", help="检测时写入 translation_stale")
    args = ap.parse_args()

    summary = {
        "ran_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ok": True,
        "steps": {},
        "actions": [],
    }

    # 1) 库体检
    v = run_py("verify_db.py")
    healthy = v.returncode == 0
    summary["steps"]["verify_db"] = {
        "ok": healthy,
        "tail": (v.stdout or "").strip().splitlines()[-8:],
    }
    if not healthy:
        summary["ok"] = False
        summary["actions"].append("verify_db 失败：先跑 python scripts/rebuild_all.py，勿直接翻译")

    # 2) 腐化检测
    stale_args = ["detect_stale_translations.py", "--json"]
    if args.mark_stale:
        stale_args.append("--mark-stale")
    s = run_py(*stale_args)
    stale_info: dict = {}
    if s.stdout.strip():
        try:
            stale_info = json.loads(s.stdout)
        except json.JSONDecodeError:
            stale_info = {"raw": s.stdout[-500:]}
    summary["steps"]["stale"] = {
        "ok": s.returncode in (0, 1),
        "returncode": s.returncode,
        "content_stale": stale_info.get("content_stale_count"),
        "time_suspect": stale_info.get("time_suspect_count"),
        "auto_refreshable": stale_info.get("refreshable_count"),
        "data": stale_info if args.json else None,
    }
    content_stale = int(stale_info.get("content_stale_count") or 0)
    if content_stale:
        summary["actions"].append(
            f"腐化 {content_stale} 条 → export_stale_tasks.py 导出后重译，再 confirm_stale_translations"
        )

    # 3) 扩充/薄字段报告
    e = run_py("export_expand_tasks.py", "--report")
    expand_ok = e.returncode == 0
    # 该脚本把缺口摘要打到 stderr（便于 cron 日志），stdout 可能为空
    report_txt = ((e.stdout or "") + "\n" + (e.stderr or "")).strip()
    summary["steps"]["expand_report"] = {
        "ok": expand_ok,
        "report": report_txt[-2000:] if report_txt else "",
    }
    if "未译=" in report_txt or "薄字段=" in report_txt or "新进榜" in report_txt:
        import re
        m_un = re.search(r"未译=(\d+)", report_txt)
        m_th = re.search(r"薄字段=(\d+)", report_txt)
        m_new = re.search(r"新进榜未入库=(\d+)", report_txt)
        n_un = int(m_un.group(1)) if m_un else 0
        n_th = int(m_th.group(1)) if m_th else 0
        n_new = int(m_new.group(1)) if m_new else 0
        summary["steps"]["expand_counts"] = {
            "untranslated": n_un, "thin": n_th, "not_in_db": n_new
        }
        if n_new:
            summary["actions"].append(
                f"新进榜未入库 {n_new} 个 → 先 fetch_batch + import_new_batch 再译"
            )
        if n_un:
            summary["actions"].append(f"未译 {n_un} 个 → export_expand_tasks --export 分批翻译")
        if n_th:
            summary["actions"].append(
                f"薄字段 {n_th} 个（阈值 desc<150/gameplay<100）→ 可用 --only thin 分批加固"
            )

    if not summary["actions"]:
        summary["actions"].append("本周无缺口，可跳过翻译批；保持云端每日重抓即可")

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("===== 每周增量维护 =====")
        print(f"时间: {summary['ran_at']}")
        print(f"体检: {'✅ 健康' if healthy else '🔴 异常'}")
        print(f"腐化 content_stale={content_stale}  time_suspect={stale_info.get('time_suspect_count')}")
        print("扩充报告:")
        for line in report_txt.splitlines()[:24]:
            print(f"  {line}")
        print("建议动作:")
        for a in summary["actions"]:
            print(f"  - {a}")
        print("详细流程: docs/ops/stale-retranslate-checklist.md")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
