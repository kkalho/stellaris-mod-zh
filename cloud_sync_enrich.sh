#!/bin/bash
set -e
cd /opt/stellaris-mod-zh
mkdir -p translations/fix
SHA=fc15c2dbbb1cab41143ae318cb47599cfe190737
# 拉取 reviews 补全存档（jsDelivr 主 + gh-proxy 回退，带超时防挂起）
curl -sL -m 40 -o translations/fix/fix_review_enrich_20260901.json "https://cdn.jsdelivr.net/gh/kkalho/stellaris-mod-zh@${SHA}/translations/fix/fix_review_enrich_20260901.json" || curl -sL -m 60 -o translations/fix/fix_review_enrich_20260901.json "https://gh-proxy.com/https://raw.githubusercontent.com/kkalho/stellaris-mod-zh/${SHA}/translations/fix/fix_review_enrich_20260901.json"
# 字节数校验（防截断；阈值 = 实际 161769 × 0.9）
python3 -c "import os; a=os.path.getsize('translations/fix/fix_review_enrich_20260901.json'); print('bytes', a); assert a>140000, 'fix_review_enrich 太小'"
# 导入（reviews-only，translations 表，不需要行存档 apply）
python3 scripts/import_stellaris_translations.py translations/fix/fix_review_enrich_20260901.json
# 重启服务
(systemctl restart stellaris-mod 2>/dev/null || sudo systemctl restart stellaris-mod)
sleep 4
# 自验：stats + 锚点 MOD 的 reviews 已补自述
curl -s http://127.0.0.1:8080/api/stellaris/stats
echo
curl -s "http://127.0.0.1:8080/api/stellaris/mod?id=2614472081" | python3 -c "import sys,json; d=json.load(sys.stdin); print('anchor reviews:', (d.get('reviews') or '')[:90])"
