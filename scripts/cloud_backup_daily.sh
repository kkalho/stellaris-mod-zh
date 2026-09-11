#!/bin/bash
# 云端每日数据备份（cron 05:00）
# 备份 mods.db + comments.db + 进度元数据 → /opt/stellaris-mod-zh/backups/，保留 14 份
set -euo pipefail
APP=/opt/stellaris-mod-zh
BAK="$APP/backups"
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$BAK"
cd "$APP"

echo "=== backup $STAMP ==="
# comments 可能不存在（老环境）
FILES=()
[ -f data/stellaris/mods.db ] && FILES+=(data/stellaris/mods.db)
[ -f data/site/comments.db ] && FILES+=(data/site/comments.db)
[ -f data/stellaris/progress.json ] && FILES+=(data/stellaris/progress.json)
if [ ${#FILES[@]} -eq 0 ]; then
  echo "nothing to backup"
  exit 0
fi

OUT="$BAK/stellaris-data-$STAMP.tar.gz"
tar -czf "$OUT" "${FILES[@]}"
# 清单
{
  echo "created_at=$STAMP"
  echo "host=$(hostname)"
  for f in "${FILES[@]}"; do
    echo "file=$f bytes=$(stat -c%s "$f")"
  done
  echo "archive_bytes=$(stat -c%s "$OUT")"
  echo "md5=$(md5sum "$OUT" | awk '{print $1}')"
} > "$BAK/stellaris-data-$STAMP.manifest"

# comments 单独导出 JSON（便于小文件拉取）
if [ -f data/site/comments.db ]; then
  /usr/bin/python3 - <<'PY'
import json, sqlite3, time
from pathlib import Path
src = Path("/opt/stellaris-mod-zh/data/site/comments.db")
dst = Path("/opt/stellaris-mod-zh/backups/comments_export.json")
conn = sqlite3.connect(src)
conn.row_factory = sqlite3.Row
rows = [dict(r) for r in conn.execute(
    "SELECT id, game_id, steam_id, name, content, created_at FROM comments ORDER BY id"
)]
conn.close()
payload = {"exported_at": time.strftime("%Y-%m-%d %H:%M:%S"), "count": len(rows), "comments": rows}
dst.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"comments_export count={len(rows)} bytes={dst.stat().st_size}")
PY
fi

# 轮转：保留最近 14 份 tar
cd "$BAK"
ls -1t stellaris-data-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
ls -1t stellaris-data-*.manifest 2>/dev/null | tail -n +15 | xargs -r rm -f
# 保留最近 1 份 comments_export（每次覆盖）

echo "=== backups dir ==="
ls -lah "$BAK" | tail -20
echo "BACKUP_DONE"
