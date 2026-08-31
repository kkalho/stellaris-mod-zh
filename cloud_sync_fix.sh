#!/bin/bash
set -e
cd /opt/stellaris-mod-zh
mkdir -p translations/fix
SHA=0a8f4d0a0bd6715e73f4d1571455046a772c03a6
# 拉取两个修复存档（jsDelivr 主 + gh-proxy 回退，带超时防挂起）
curl -sL -m 40 -o translations/fix/fix_15_misaligned.json "https://cdn.jsdelivr.net/gh/kkalho/stellaris-mod-zh@${SHA}/translations/fix/fix_15_misaligned.json" || curl -sL -m 60 -o translations/fix/fix_15_misaligned.json "https://gh-proxy.com/https://raw.githubusercontent.com/kkalho/stellaris-mod-zh/${SHA}/translations/fix/fix_15_misaligned.json"
curl -sL -m 40 -o translations/fix/fix_reviews_debunk.json "https://cdn.jsdelivr.net/gh/kkalho/stellaris-mod-zh@${SHA}/translations/fix/fix_reviews_debunk.json" || curl -sL -m 60 -o translations/fix/fix_reviews_debunk.json "https://gh-proxy.com/https://raw.githubusercontent.com/kkalho/stellaris-mod-zh/${SHA}/translations/fix/fix_reviews_debunk.json"
# 字节数校验（防截断；阈值 = 实际大小 × 0.9 左右）
python3 -c "import os; a=os.path.getsize('translations/fix/fix_15_misaligned.json'); b=os.path.getsize('translations/fix/fix_reviews_debunk.json'); print('bytes', a, b); assert a>22000, 'fix_15 太小'; assert b>66000, 'fix_reviews 太小'"
# 导入翻译（translations 表，不需要行存档 apply）
python3 scripts/import_stellaris_translations.py translations/fix/fix_15_misaligned.json
python3 scripts/import_stellaris_translations.py translations/fix/fix_reviews_debunk.json
# 重启服务（TAT 以 root 运行；必要时回退 sudo）
(systemctl restart stellaris-mod 2>/dev/null || sudo systemctl restart stellaris-mod)
sleep 4
# 自验：stats + 锚点 MOD 的 gameplay 已更新
curl -s http://127.0.0.1:8080/api/stellaris/stats
echo
curl -s "http://127.0.0.1:8080/api/stellaris/mod?id=1631985204" | python3 -c "import sys,json; d=json.load(sys.stdin); g=(d.get('gameplay') or d.get('gameplay_zh') or ''); print('anchor gameplay head:', g[:80])"
