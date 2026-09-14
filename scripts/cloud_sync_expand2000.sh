#!/bin/bash
# 云端同步：Top 2000 扩容（2008 行存档 + 全量翻译 + 兼容性重挖）
# SHA 固定 5d5c4e4（2026-09-13 维护轮 24）
set -e
cd /opt/stellaris-mod-zh
SHA="5d5c4e4dc4d536ee5588597c945606da35c63096"
JSDEL="https://cdn.jsdelivr.net/gh/kkalho/stellaris-mod-zh@$SHA"
GHPROXY="https://gh-proxy.com/https://github.com/kkalho/stellaris-mod-zh/raw/$SHA"

fetch() {
  dest="$1"; min="$2"; tmo="${3:-40}"
  for src in "$JSDEL" "$GHPROXY" "$JSDEL"; do
    echo "try $dest <- $src"
    if curl -fsSL -m "$tmo" -o "$dest.tmp" "$src/$dest"; then
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

mkdir -p web data/stellaris scripts games/stellaris/config core
echo "=== fetch files (pinned SHA $SHA) ==="
fetch scripts/apply_cloud_sync.py 3000
fetch scripts/import_stellaris_translations.py 3000
fetch scripts/migrate_translation_baseline.py 5000
fetch scripts/mine_compat.py 7000
fetch scripts/rebuild_all.py 8000
fetch data/stellaris/mods_full_sync.json.gz 2300000 90
fetch data/stellaris/translations_full_sync.json.gz 1300000 90

echo "=== ensure baseline columns ==="
python3 scripts/migrate_translation_baseline.py || echo "migrate rc=$? (columns may already exist)"

echo "=== backup db ==="
cp data/stellaris/mods.db "data/stellaris/mods.db.bak-$(date +%Y%m%d%H%M%S)"
ls -1t data/stellaris/mods.db.bak-* 2>/dev/null | tail -n +4 | xargs -r rm -f

echo "=== decompress archives (python gzip, sanity-checked) ==="
python3 - <<'PY'
import gzip, json, os, shutil
for name, expect in [("mods_full_sync.json", 2000), ("translations_full_sync.json", 2000)]:
    src = f"data/stellaris/{name}.gz"
    dst = f"data/stellaris/{name}"
    with gzip.open(src, "rb") as fin, open(dst, "wb") as fout:
        shutil.copyfileobj(fin, fout)
    with open(dst, encoding="utf-8") as f:
        data = json.load(f)
    count = data.get("count", 0)
    print(f"{name}: {os.path.getsize(dst)} B, count={count}")
    if count < expect:
        raise SystemExit(f"SANITY FAIL {name}: count {count} < {expect}")
print("archives OK")
PY

echo "=== apply mods rows ==="
python3 scripts/apply_cloud_sync.py --game stellaris

echo "=== import translations ==="
python3 scripts/import_stellaris_translations.py data/stellaris/translations_full_sync.json

echo "=== mine compat ==="
python3 scripts/mine_compat.py

echo "=== restart & verify ==="
sudo systemctl restart stellaris-mod
sleep 4
echo -n "stats: "; curl -s -m 20 http://127.0.0.1:8080/api/stellaris/stats; echo
echo -n "sample: "; curl -s -m 15 "http://127.0.0.1:8080/api/stellaris/mod?id=1121692237" | python3 -c "import sys,json; d=json.load(sys.stdin); m=d.get('mod',d); print(m.get('steam_id'), (m.get('title') or '')[:40], 'desc_len', len(m.get('description') or ''))"
echo "SYNC_DONE"
