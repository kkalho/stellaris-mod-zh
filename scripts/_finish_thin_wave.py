"""薄字段波次收尾：合并 A/B/C → 门禁 → 导入 → 报告 → 可选云同步。

用法:
    python scripts/_finish_thin_wave.py 3
    python scripts/_finish_thin_wave.py 3 --cloud
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd[:6]), "...")
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit(f"failed rc={r.returncode}: {cmd[0]}")


def merge(n: int) -> Path:
    base = ROOT / "translations" / "expand_wave"
    parts = []
    for p in "ABC":
        path = base / f"thin_task_{n:03d}_part{p}.json"
        if not path.exists():
            raise SystemExit(f"missing {path}")
        d = json.loads(path.read_text(encoding="utf-8"))
        for t in d.get("translations", []):
            if "description_zh_current" in t or "gameplay_zh" not in t:
                raise SystemExit(f"{path.name} steam_id={t.get('steam_id')} 不是输出格式（缺 *_zh 或含 *_zh_current）")
        parts.extend(d["translations"])
        print(path.name, len(d["translations"]))
    ids = [t["steam_id"] for t in parts]
    if len(parts) != 25 or len(set(ids)) != 25:
        raise SystemExit(f"count/unique mismatch: {len(parts)}/{len(set(ids))}")
    merged = {
        "game": "stellaris",
        "source": f"thin wave{n} merged (25)",
        "translations": parts,
    }
    out = base / f"thin_task_{n:03d}_merged.json"
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", out.name, "items", len(parts))
    return out


def cloud_sync(n: int, merged: Path) -> None:
    data = json.loads(merged.read_text(encoding="utf-8"))
    b64 = base64.b64encode(
        gzip.compress(json.dumps(data, ensure_ascii=False).encode("utf-8"), compresslevel=9)
    ).decode()
    script = f"""#!/bin/bash
# 薄字段 wave{n} 上云
set -e
cd /opt/stellaris-mod-zh
python3 - <<'PY'
import base64, gzip, json, sqlite3, time, re
data = json.loads(gzip.decompress(base64.b64decode({b64!r})))
META_BRACKETS = re.compile(r"^(?:\\s*【[^】]{{0,24}}】)+\\s*")
META_PAREN = re.compile(r"^（已[^）]{{0,30}}核实）\\s*")
def clean_meta(t):
    if not t: return t
    t = META_BRACKETS.sub("", t.strip())
    t = META_PAREN.sub("", t).strip()
    return t
FIELD_MAP = {{"title":"title_zh","summary":"summary_zh","description":"description_zh",
             "gameplay":"gameplay_zh","reviews":"reviews_zh","features":"features_zh"}}
conn = sqlite3.connect("data/stellaris/mods.db")
conn.execute("PRAGMA busy_timeout=8000")
cur = conn.cursor()
n = 0
for t in data["translations"]:
    sid = str(t.get("steam_id"))
    mid = cur.execute("SELECT id FROM mods WHERE game_id='stellaris' AND steam_id=?", (sid,)).fetchone()
    if not mid:
        print("skip", sid); continue
    mid = mid[0]
    for field, key in FIELD_MAP.items():
        val = t.get(key)
        if not val: continue
        if field == "features" and isinstance(val, list):
            val = json.dumps(val, ensure_ascii=False)
        if field in ("description", "gameplay", "reviews"):
            val = clean_meta(val)
        cur.execute("DELETE FROM translations WHERE mod_id=? AND field=?", (mid, field))
        cur.execute("INSERT INTO translations (mod_id, field, zh_text, quality, updated_at) VALUES (?,?,?,?,?)",
                    (mid, field, val, "ai_reviewed", time.strftime("%Y-%m-%d %H:%M:%S")))
    n += 1
conn.commit()
print("imported", n)
conn.close()
PY
sudo systemctl restart stellaris-mod
sleep 3
echo -n "stats: "; curl -s -m 15 http://127.0.0.1:8080/api/stellaris/stats; echo
echo THIN{n}_DONE
"""
    sh = ROOT / "scripts" / f"cloud_sync_thin{n}.sh"
    sh.write_text(script, encoding="utf-8", newline="\n")
    print("tat script", sh.name, "bytes", len(script))
    run([sys.executable, "scripts/tat_sync.py", "--script", str(sh.relative_to(ROOT))])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("wave", type=int)
    ap.add_argument("--cloud", action="store_true")
    args = ap.parse_args()
    n = args.wave
    merged = merge(n)
    run([sys.executable, "scripts/validate_translations.py", str(merged.relative_to(ROOT))])
    run([sys.executable, "scripts/import_stellaris_translations.py", str(merged.relative_to(ROOT))])
    run([sys.executable, "scripts/export_expand_tasks.py", "--report"])
    run([sys.executable, "scripts/verify_db.py"])
    if args.cloud:
        cloud_sync(n, merged)
    print(f"WAVE{n}_FINISH_OK")


if __name__ == "__main__":
    main()
