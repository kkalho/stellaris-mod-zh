#!/bin/bash
# 云端：刷库 + 标 stale + 导出重译任务包
set -e
cd /opt/stellaris-mod-zh
SHA="b3b3754db3d462adb8106a07245edf5d3260f252"
JSDEL="https://cdn.jsdelivr.net/gh/kkalho/stellaris-mod-zh@$SHA"
GHPROXY="https://gh-proxy.com/https://github.com/kkalho/stellaris-mod-zh/raw/$SHA"

fetch() {
  dest="$1"; min="$2"
  for src in "$JSDEL" "$GHPROXY" "$JSDEL"; do
    if curl -fsSL -m 40 -o "$dest.tmp" "$src/$dest"; then
      sz=$(stat -c%s "$dest.tmp" 2>/dev/null || echo 0)
      if [ "$sz" -ge "$min" ]; then mv "$dest.tmp" "$dest"; echo "OK   $dest ($sz B)"; return 0; fi
      echo "too small: $sz (< $min)"
    else
      echo "curl failed (rc=$?)"
    fi
  done
  rm -f "$dest.tmp"
  echo "FAIL $dest"; exit 1
}

echo "=== fetch ==="
fetch scripts/scan_steam_diff.py 8000

echo "=== backup ==="
cp data/stellaris/mods.db "data/stellaris/mods.db.bak-$(date +%Y%m%d%H%M%S)"
ls -1t data/stellaris/mods.db.bak-* 2>/dev/null | tail -n +4 | xargs -r rm -f

echo "=== scan write+mark+pack ==="
mkdir -p translations/stale_wave
# 退出码 1=发现腐化，属预期；不要被 set -e 打断
python3 scripts/scan_steam_diff.py --game stellaris --batch 50 --sleep 1.5 --top 5 \
  --write --mark-stale --export-pack || true

echo "=== after ==="
python3 - <<'PY'
import sqlite3, os, glob, json
c = sqlite3.connect("data/stellaris/mods.db")
stale = c.execute("SELECT COUNT(*) FROM mods WHERE game_id='stellaris' AND translation_stale=1").fetchone()[0]
total = c.execute("SELECT COUNT(*) FROM mods WHERE game_id='stellaris'").fetchone()[0]
print(f"AFTER total={total} translation_stale=1 => {stale}")
c.close()
packs = sorted(glob.glob("translations/stale_wave/stale_task_scan_*.json"))
print("PACKS", len(packs))
if packs:
    p = packs[-1]
    data = json.load(open(p, encoding="utf-8"))
    print("LATEST", p, "count=", data.get("stale_count_total"))
    ids = [t["steam_id"] for t in data.get("translations", [])][:30]
    print("TOP_IDS", ",".join(ids))
    print("PACK_SIZE", os.path.getsize(p))
PY
echo "WRITE_PACK_DONE"
