#!/bin/bash
set -e
cd /opt/stellaris-mod-zh
SHA=1afe20f9751210f451d235179ba361ded476bfbf
JSDEL="https://cdn.jsdelivr.net/gh/kkalho/stellaris-mod-zh@$SHA"
GHPROXY="https://gh-proxy.com/https://github.com/kkalho/stellaris-mod-zh/raw/$SHA"

fetch() {
  dest="$1"; min="$2"
  for src in "$JSDEL" "$GHPROXY" "$JSDEL"; do
    if curl -fsSL -m 60 -o "$dest.tmp" "$src/$dest"; then
      sz=$(stat -c%s "$dest.tmp" 2>/dev/null || echo 0)
      if [ "$sz" -ge "$min" ]; then mv "$dest.tmp" "$dest"; echo "OK   $dest ($sz B)"; return 0; fi
      echo "too small: $sz (< $min)"
    else
      echo "curl failed (rc=$?)"
    fi
  done
  rm -f "$dest.tmp"; echo "FAIL $dest"; exit 1
}

mkdir -p data/stellaris
echo "=== fetch 存档 (.gz) ==="
fetch data/stellaris/mods_full_sync.json.gz 1200000
fetch data/stellaris/translations_full_sync.json.gz 520000

echo "=== 解压 + 校验 count（python 解压，防 busybox gunzip 方言）==="
python3 - <<'EOF'
import gzip, json
for name, expect in [('mods_full_sync', 977), ('translations_full_sync', 977)]:
    gz = f'data/stellaris/{name}.json.gz'
    raw = gzip.open(gz, 'rb').read()
    open(f'data/stellaris/{name}.json', 'wb').write(raw)
    d = json.loads(raw.decode('utf-8'))
    n = d.get('count') or len(d.get('rows', d.get('translations', [])))
    print(name, 'count', n, 'bytes', len(raw))
    assert n >= expect, f'{name} count 不足 {n}'
EOF

echo "=== backup db ==="
cp data/stellaris/mods.db "data/stellaris/mods.db.bak-$(date +%Y%m%d%H%M%S)"
ls -1t data/stellaris/mods.db.bak-* 2>/dev/null | tail -n +4 | xargs -r rm -f

echo "=== apply mods 表 ==="
python3 scripts/apply_cloud_sync.py

echo "=== import translations ==="
python3 scripts/import_stellaris_translations.py data/stellaris/translations_full_sync.json

echo "=== restart & verify ==="
(systemctl restart stellaris-mod 2>/dev/null || sudo systemctl restart stellaris-mod)
sleep 4
curl -s -m 15 http://127.0.0.1:8080/api/stellaris/stats
echo
curl -s -m 15 "http://127.0.0.1:8080/api/stellaris/mod?id=2938897848" | python3 -c "import sys,json; d=json.load(sys.stdin); print('新MOD title:', d.get('title')); print('新MOD reviews:', (d.get('reviews') or '')[:60])"
echo "SYNC_DONE"
