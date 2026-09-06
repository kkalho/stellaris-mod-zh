"""云端趋势表备份拉取：TAT 分片回传（实测外层输出上限 ~32KB，分 14KB 压缩块）

流程：生成第 i 片服务端脚本（lzma 压缩 trend 表 → base64 → 切片）→ tat_sync 推送并轮询
→ 本地拼接解压 → 存 data/stellaris/trend_backup_<日期>.csv。空片即停。
提交由调用方执行（本脚本不做任何 git 操作）。

用法:
    python scripts/pull_trend_backup.py            # 拉取并保存
注意：依赖系统 Python 3.15 的 tccli（见 HANDOFF §8）；临时分片脚本用完即删。
"""
from __future__ import annotations

import base64
import io
import json
import lzma
import re
import subprocess
import time
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SYS_PY = r"C:\Users\wangf\AppData\Local\Programs\Python\Python315\python.exe"
CHUNK = 14000          # 每片压缩字节数（b64 后 ~18.7KB，外层 ~25KB < 32KB 实测上限）
MAX_PARTS = 8
TMP = BASE / "cloud_bak_tmp.txt"

PART_SCRIPT = """cd /opt/stellaris-mod-zh
/usr/bin/python3 - <<'PY'
import sqlite3, lzma, base64, io, csv
conn = sqlite3.connect('/opt/stellaris-mod-zh/data/stellaris/mods.db')
cur = conn.execute("SELECT steam_id, date, subs FROM trend ORDER BY date, steam_id")
buf = io.StringIO()
w = csv.writer(buf)
w.writerows(cur)
conn.close()
comp = lzma.compress(buf.getvalue().encode(), format=lzma.FORMAT_XZ)
i = {i}
chunk = comp[(i - 1) * {CHUNK}: i * {CHUNK}]
print(f"PART={{i}} LEN={{len(chunk)}}")
print(base64.b64encode(chunk).decode())
PY
"""


def run_tat(script_text: str) -> str:
    TMP.write_text(script_text, encoding="utf-8")
    out = subprocess.run([SYS_PY, str(BASE / "scripts" / "tat_sync.py"), "--script", TMP.name],
                         cwd=str(BASE), capture_output=True, text=True, encoding="utf-8").stdout
    m = re.search(r"inv-[a-z0-9]+", out)
    if not m:
        raise SystemExit(f"✗ TAT 推送失败: {out[:200]}")
    inv = m.group(0)
    for _ in range(12):
        time.sleep(15)
        poll = subprocess.run([SYS_PY, str(BASE / "scripts" / "tat_sync.py"), "--poll-inv", inv],
                              cwd=str(BASE), capture_output=True, text=True, encoding="utf-8").stdout
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
        raise SystemExit("✗ 未收到任何数据")
    data = lzma.decompress(b"".join(parts[k] for k in sorted(parts))).decode("utf-8")
    rows = data.strip().split("\n")
    out = BASE / "data" / "stellaris" / f"trend_backup_{date.today().isoformat()}.csv"
    out.write_text(data, encoding="utf-8")
    print(f"✓ 回传 {len(rows)} 行 → {out.name}（{out.stat().st_size // 1024}KB）")
    TMP.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
