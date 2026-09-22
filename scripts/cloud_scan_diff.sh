#!/bin/bash
# 云端跑 scan_steam_diff 全库 Steam 差分（只读，不写库）
# 输出精简文本报告，适配 TAT ~32KB 输出上限
set -e
cd /opt/stellaris-mod-zh
SHA="b3b3754db3d462adb8106a07245edf5d3260f252"
JSDEL="https://cdn.jsdelivr.net/gh/kkalho/stellaris-mod-zh@$SHA"
GHPROXY="https://gh-proxy.com/https://github.com/kkalho/stellaris-mod-zh/raw/$SHA"

fetch() {
  dest="$1"; min="$2"
  for src in "$JSDEL" "$GHPROXY" "$JSDEL"; do
    echo "try $dest <- $src"
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

echo "=== fetch scan_steam_diff.py ==="
fetch scripts/scan_steam_diff.py 8000

echo "=== db stale snapshot ==="
python3 - <<'PY'
import sqlite3
c = sqlite3.connect("data/stellaris/mods.db")
n = c.execute("SELECT COUNT(*) FROM mods WHERE game_id='stellaris' AND translation_stale=1").fetchone()[0]
t = c.execute("SELECT COUNT(*) FROM mods WHERE game_id='stellaris'").fetchone()[0]
print(f"BEFORE total={t} translation_stale=1 => {n}")
c.close()
PY

echo "=== scan (read-only) ==="
# 全库 ~2010，batch50 sleep1.5 约 60-90s；--top 18 控制输出体积
python3 scripts/scan_steam_diff.py --game stellaris --batch 50 --sleep 1.5 --top 18
echo "SCAN_DONE rc=$?"
