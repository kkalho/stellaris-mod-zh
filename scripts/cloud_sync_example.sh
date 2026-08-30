#!/bin/bash
# 云端全量同步脚本模板（2026-08-30 实战版，TAT 执行成功：更新 527 + 插入 50）
#
# 用法：本地改 SHA 与文件清单后：
#   B64=$(base64 -w0 scripts/cloud_sync_example.sh)
#   tccli tat RunCommand --region ap-shanghai --Content "$B64" \
#     --InstanceIds '["lhins-ca3ol8ju"]' --CommandType SHELL --Timeout 600
#   # 轮询取输出（输出为 base64）：
#   tccli tat DescribeInvocationTasks --region ap-shanghai \
#     --Filters '[{"Name":"invocation-id","Values":["inv-xxx"]}]' --HideOutput false
#
# 要点：
# - jsDelivr 用「固定 commit SHA」而非 @master，免缓存陈旧（gh-proxy 才有此坑）
# - 每个文件校验最小字节数，防截断（坑 #3）
# - curl 必须带 -m 超时（r12 教训 2026-08-30：jsDelivr 偶发连接挂起 0 字节，
#   无 -m 会把整段 TAT 拖到 300s TIMEOUT 且输出全丢）；jsDelivr 失败回退
#   gh-proxy（固定 SHA 无缓存坑，r12b 实测救场）
# - apply_cloud_sync.py 为 UPDATE 保主键 / INSERT 分流，外键安全
# - 改库前先备份 mods.db
set -e
cd /opt/stellaris-mod-zh
SHA="<替换为 git rev-parse HEAD 的完整 SHA>"
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

mkdir -p web data/stellaris scripts games/stellaris/config core
echo "=== fetch files (pinned SHA) ==="
fetch web_server_multigame.py 18000
fetch core/mod_db.py 9000
fetch games/stellaris/config/game.py 10000
fetch web/index_multigame.html 30000
fetch scripts/apply_cloud_sync.py 2500
fetch scripts/import_stellaris_translations.py 2000
# ↓ 数据文件按本轮实际需要增删；行存档最小字节数 = 本地实际大小 × 0.9
fetch data/stellaris/mods_full_sync.json 4000000

echo "=== backup db ==="
cp data/stellaris/mods.db "data/stellaris/mods.db.bak-$(date +%Y%m%d%H%M%S)"

echo "=== apply rows ==="
python3 scripts/apply_cloud_sync.py

echo "=== import translations (如有新批次) ==="
# python3 scripts/import_stellaris_translations.py translations/batchN_zh.json

echo "=== restart & verify ==="
sudo systemctl restart stellaris-mod
sleep 3
curl -s -m 15 http://127.0.0.1:8080/api/stellaris/stats
echo
echo "SYNC_DONE"
