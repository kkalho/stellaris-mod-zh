#!/bin/bash
# 云端导入 77 条重译并确认基线（SHA: be97a5bdbf75255ac4cd1b38ea77738d99d3cecc）
set -e
cd /opt/stellaris-mod-zh
SHA="be97a5bdbf75255ac4cd1b38ea77738d99d3cecc"
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
fetch scripts/import_stellaris_translations.py 2000
fetch scripts/confirm_stale_translations.py 2000
fetch translations/stale_wave/stale_scan_merged_all.json 50000

echo "=== before ==="
python3 - <<'PY'
import sqlite3
c = sqlite3.connect("data/stellaris/mods.db")
print("stale_before", c.execute("SELECT COUNT(*) FROM mods WHERE game_id='stellaris' AND translation_stale=1").fetchone()[0])
c.close()
PY

echo "=== import ==="
python3 scripts/import_stellaris_translations.py translations/stale_wave/stale_scan_merged_all.json

echo "=== confirm ==="
python3 scripts/confirm_stale_translations.py --from-file translations/stale_wave/stale_scan_merged_all.json

echo "=== detect ==="
python3 scripts/detect_stale_translations.py || true

echo "=== after ==="
python3 - <<'PY'
import sqlite3
c = sqlite3.connect("data/stellaris/mods.db")
print("stale_after", c.execute("SELECT COUNT(*) FROM mods WHERE game_id='stellaris' AND translation_stale=1").fetchone()[0])
c.close()
PY

echo "=== restart ==="
sudo systemctl restart stellaris-mod
sleep 3
curl -s -m 15 http://127.0.0.1:8080/api/stellaris/stats
echo
echo "IMPORT_CONFIRM_DONE"
