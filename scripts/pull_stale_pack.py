"""从云端分片拉回 translations/stale_wave/stale_task_scan_*.json（lzma+base64）。

用法:
    python scripts/pull_stale_pack.py
    python scripts/pull_stale_pack.py --remote translations/stale_wave/stale_task_scan_20260923_195030.json
"""
from __future__ import annotations

import argparse
import base64
import json
import lzma
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNK = 14000
SYS_PY = r"C:\Users\wangf\AppData\Local\Programs\Python\Python315\python.exe"
TAT = os.path.join(BASE_DIR, "scripts", "tat_sync.py")


def run_tat(script_body: str) -> str:
    path = os.path.join(BASE_DIR, "scripts", "_pull_pack_tmp.sh")
    with open(path, "w", encoding="utf-8") as f:
        f.write(script_body)
    try:
        r = subprocess.run(
            [SYS_PY, TAT, "--script", path],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=BASE_DIR, timeout=120,
        )
        out = r.stdout or ""
        start = out.find("{")
        if start < 0:
            raise SystemExit(f"RunCommand 失败: {out[-400:]} {r.stderr[-200:]}")
        inv = json.loads(out[start:])["InvocationId"]
        # 轮询
        import time
        for _ in range(30):
            time.sleep(3)
            r2 = subprocess.run(
                [SYS_PY, TAT, "--poll-inv", inv],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                cwd=BASE_DIR, timeout=60,
            )
            raw = r2.stdout or ""
            s = raw.find("{")
            if s < 0:
                continue
            data = json.loads(raw[s:])
            task = data["InvocationTaskSet"][0]
            if task["TaskStatus"] in ("RUNNING", "PENDING"):
                continue
            b64 = task["TaskResult"].get("Output") or ""
            return base64.b64decode(b64).decode("utf-8", "replace")
        raise SystemExit("轮询超时")
    finally:
        if os.path.exists(path):
            os.remove(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--remote", default="translations/stale_wave/stale_task_scan_20260923_195030.json")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    remote = args.remote
    out_path = args.out or os.path.join(BASE_DIR, "translations", "stale_wave", os.path.basename(remote))

    # 1) 元信息
    meta_script = f"""#!/bin/bash
set -e
cd /opt/stellaris-mod-zh
python3 - <<'PY'
import lzma, os
p = {remote!r}
raw = open(p, "rb").read()
comp = lzma.compress(raw, format=lzma.FORMAT_XZ)
print(f"RAW={{len(raw)}} COMP={{len(comp)}}")
open("/tmp/pack.lzma", "wb").write(comp)
PY
"""
    meta = run_tat(meta_script).strip()
    print("[meta]", meta)
    # RAW=500201 COMP=xxxx
    comp_len = 0
    for tok in meta.split():
        if tok.startswith("COMP="):
            comp_len = int(tok.split("=", 1)[1])
    if not comp_len:
        raise SystemExit("拿不到 COMP 长度")
    n_chunks = (comp_len + CHUNK - 1) // CHUNK
    print(f"[pull] {n_chunks} 片 × {CHUNK}B")

    parts: dict[int, bytes] = {}
    for i in range(1, n_chunks + 1):
        script = f"""#!/bin/bash
set -e
cd /opt/stellaris-mod-zh
python3 - <<'PY'
import base64
comp = open("/tmp/pack.lzma", "rb").read()
chunk = comp[{(i - 1) * CHUNK}: {i * CHUNK}]
print("PART={i} LEN={{len(chunk)}}")
print(base64.b64encode(chunk).decode())
PY
"""
        text = run_tat(script)
        lines = [ln for ln in text.strip().splitlines() if ln.strip()]
        # 找 PART= 行与后续 b64
        header = ""
        payload = ""
        for ln in lines:
            if ln.startswith("PART="):
                header = ln
            elif ln and not ln.startswith("PART=") and not ln.startswith("RAW"):
                payload = ln
                break
        if not payload:
            # 整段当 b64
            payload = lines[-1] if lines else ""
        chunk = base64.b64decode(payload)
        expect = min(CHUNK, comp_len - (i - 1) * CHUNK)
        if len(chunk) != expect:
            print(f"  ⚠ 片 {i} 长度 {len(chunk)} != {expect}，重试")
            text = run_tat(script)
            lines = [ln for ln in text.strip().splitlines() if ln.strip()]
            payload = lines[-1] if lines else ""
            chunk = base64.b64decode(payload)
            if len(chunk) != expect:
                raise SystemExit(f"✗ 片 {i} 不完整")
        parts[i] = chunk
        print(f"  ok 片 {i}/{n_chunks} ({len(chunk)}B)")

    blob = b"".join(parts[k] for k in range(1, n_chunks + 1))
    data = lzma.decompress(blob)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(data)
    obj = json.loads(data.decode("utf-8"))
    print(f"✓ 写入 {out_path} ({len(data)} B, {obj.get('stale_count_total')} 条)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
