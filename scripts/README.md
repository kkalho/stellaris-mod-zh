# scripts/ 工具说明

## 群星现役工具链（按用途）

| 用途 | 命令 | 说明 |
|---|---|---|
| ⭐ 数据体检 | `python scripts/verify_db.py` | 一条命令验健康度；退出码 1 = 有归零类问题 |
| ⭐ 收敛重建 | `python scripts/rebuild_all.py` | 万能修复（字段归零/漏导入/改坏库），全幂等；`--dry-run` 只看步骤 |
| 抓取详情 | `python scripts/fetch_batch.py --start N --end M` | 参数化，断点续抓 |
| 增量入库 | `python scripts/import_new_batch.py N M` | upsert 新 MOD + 自动更新 progress.json |
| 翻译导入 | `python scripts/import_stellaris_translations.py translations/batchN_zh.json` | 批次格式 |
| 版本标注 | `python scripts/detect_stellaris_versions.py` | 双轨：显式声明 + 时间推断 |
| DLC 标注 | `python scripts/detect_stellaris_dlcs.py` | 英文描述 + 中文翻译双轨，命中全标「可选」 |
| 拼音索引 | `python scripts/rebuild_pinyin_idx.py` | 含中文译名拼音 |
| 趋势快照 | `python scripts/snapshot_trend.py --game stellaris` | 每日一行 |
| 趋势导出 | `python scripts/export_trend.py` | 云端备份用 |
| 抓取榜单 | `python scripts/fetch_workshop_top.py` | 创意工坊页面前 N |

日常大部分场景只需 **verify_db / rebuild_all / fetch_batch** 三个。

## CK3 工具链（P3 深度精做时使用）

`fetch_ck3_workshop_top.py` · `fetch_ck3_details.py` · `build_ck3_db.py` ·
`import_ck3_translations.py` · `patch_ck3_missing.py`

## 部署

`deploy_lighthouse.sh`（首次部署打包；日常同步走 TAT，见交接文档 §8）

## 已移除的旧链路脚本（2026-08-30）

以下脚本已被现役工具取代并删除（git 历史可找回，`git log --diff-filter=D --name-only`）：

- `fetch_batch9~16.py` × 8 → 用 `fetch_batch.py --start/--end` 取代
- `update_all.py`（旧版重建流水线，坑 #1 事故触发链）→ 用 `rebuild_all.py` 取代
- `build_db.py` 的旧搭档 `import_translations.py`（连旧库，坑 #10）→ 用 `import_stellaris_translations.py`
- `web_server.py`（旧单游戏服务）→ 用 `web_server_multigame.py`
- `migrate_to_multigame.py`（一次性迁移，已完成）
- `auto_fetch.py` / `modlookup.py` / `import_compat.py`（早期一次性脚本）
- `data/stellaris_mods.db`（4.9MB 旧版单游戏库，可由 build_db --force 从 git 源文件重新生成）

**新会话注意**：不要再寻找或重建以上脚本；一切数据修复从 `rebuild_all.py` 出发。
