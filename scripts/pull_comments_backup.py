"""拉取云端访客留言库 comments.db（二进制，TAT 分片回传）

云端每日 05:00 由 scripts/cloud_backup_daily.sh 备份；comments 体积小（~16KB），
lzma 后通常 1–2 片即可。流程与 pull_trend_backup.py 相同。

用法:
    python scripts/pull_comments_backup.py
    python scripts/pull_comments_backup.py --out data/site/comments_local.db

产出:
    data/site/comments_local.db

依赖系统 Python 3.15 的 tccli（HANDOFF §8）。
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import time
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SYS_PY = r"C:\Users\wangf\AppData\Local\Programs\Python\Python315\python.exe"
CHUNK = 14000
MAX_PARTS = 8
TMP = BASE / "cloud_bak_tmp.txt"

PART_SCRIPT = """#!/bin/bash
/usr/bin/python3 - <<'PY'
import lzma, base64
from pathlib import Path
p = Path('/opt/stellaris-mod-zh/data/site/comments.db')
if not p.exists():
    print('PART={i} LEN=0')
    print('')
else:
    comp = lzma.compress(p.read_bytes(), format=lzma.FORMAT_XZ)
    chunk = comp[({i}-1)*{CHUNK}: {i}*{CHUNK}]
    print(f'PART={i} LEN={{len(chunk)}}')
    print(base64.b64encode(chunk).decode() if chunk else '')
PY
"""


def run_tat(script_text: str) -> str:
    TMP.write_text(script_text, encoding="utf-8")
    try:
        out = subprocess.run(
            [SYS_PY, str(BASE / "scripts" / "tat_sync.py"), "--script", TMP.name],
            cwd=str(BASE),
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout
    finally:
        TMP.unlink(missing_ok=True)
    m = re.search(r"inv-[a-z0-9]+", out)
    if not m:
        raise SystemExit(f"✗ TAT 推送失败: {out[:200]}")
    inv = m.group(0)
    for _ in range(12):
        time.sleep(12)
        poll = subprocess.run(
            [SYS_PY, str(BASE / "scripts" / "tat_sync.py"), "--poll-inv", inv],
            cwd=str(BASE),
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout
        try:
            d = json.loads(poll)
        except ValueError:
            continue
        for t in d.get("InvocationTaskSet", []):
            status = (t.get("TaskStatus") or "").upper()
            if status == "SUCCESS":
                out_b64 = t.get("TaskResult", {}).get("Output", "")
                return base64.b64decode(out_b64).decode("utf-8", "replace")
            if status in ("FAILED", "CANCELLED", "TIMEOUT"):
                raise SystemExit(f"✗ TAT 执行失败: {status}")
    raise SystemExit(f"✗ TAT 轮询超时: {inv}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(BASE / "data" / "site" / "comments_local.db"))
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    parts: dict[int, bytes] = {}
    for i in range(1, MAX_PARTS + 1):
        text = run_tat(PART_SCRIPT.format(i=i, CHUNK=CHUNK))
        lines = text.strip().split("\n")
        meta = lines[0].strip()
        m = re.search(r"LEN=(\d+)", meta)
        if not m:
            raise SystemExit(f"✗ 第 {i} 片输出异常: {meta[:80]}")
        length = int(m.group(1))
        if length == 0:
            print(f"  片 {i}: 空 → 传输完成")
            break
        payload = re.sub(r"\s+", "", "".join(lines[1:]))
        chunk = base64.b64decode(payload)
        if len(chunk) != length:
            raise SystemExit(f"✗ 第 {i} 片不完整: 应 {length} 实 {len(chunk)}")
        parts[i] = chunk
        print(f"  片 {i}: {length} B ✓")
        if length < CHUNK:
            break
    if not parts:
        raise SystemExit("✗ 未收到数据（云端 comments.db 可能不存在）")
    import lzma

    data = lzma.decompress(b"".join(parts[k] for k in sorted(parts)))
    out.write_bytes(data)
    print(f"✓ 回传 {len(data)} B → {out}（{date.today().isoformat()}）")


if __name__ == "__main__":
    main()
