---
feature: stale-retranslate
status: designed
updated: 2026-09-11
branch: feature/stale-retranslate
commits: 
---

# 增量重译流水线（翻译腐化闭环）

## Report

## [S1] Problem

云端已能自动发现「作者更新后翻译过期」（`detect_stale --mark-stale`），但**没有**把腐化名单变成可重译任务包、以及重译导入后**归零基线**的闭环。ROADMAP P2 待做。

## [S2] Design

### E 导出 `scripts/export_stale_tasks.py`

- 输入：内容维度腐化（`description_clean` SHA256 ≠ `desc_hash_baseline`）为主；可选 `--include-marked` 额外并入 `translation_stale=1`；可选 `--include-time-suspect` 并入时间粗筛（默认关）
- 输出：与 `export_deep_tasks.py` 同构 JSON → stdout（`game` / `source` / `translations[]`）
- 每条自包含：`steam_id` / `title_en` / `description_clean`（≤6000）/ `tags` / `subscriptions` / `time_updated` / `stale_type` / 六字段 `*_zh_current`
- 分片：`--start N --end M`（1-based，对排序后名单切片）或 `--limit K`（前 K 条）
- 排序：subscriptions 降序
- 空名单：stderr 提示 + stdout 仍输出合法空 `translations: []`
- 用法示例：
  `python scripts/export_stale_tasks.py --start 1 --end 25 > translations/stale_wave/stale_task_001.json`

### C 确认 `scripts/confirm_stale_translations.py`

导入重译后必须有人确认基线（当前 **import 不写基线**，是缺口）：

- `--ids 111,222` 或 `--from-file path.json`（读任务包 steam_id 列表）
- 或 `--all-content-stale`：对仍内容腐化的全部 MOD，把基线刷成**当前** `description_clean` hash
- 写入：`desc_hash_baseline = sha256(description_clean)`，`translation_confirmed_at = today`，`translation_stale = 0`
- 参数化 SQL；退出码 0=成功写入 n 条，1=参数/库错误

### 工作流（给运维/子智能体）

1. 云端或本地：`detect_stale_translations.py --mark-stale`（已有）
2. `export_stale_tasks.py` 导出任务包
3. 子智能体按 deep 规则重写 description_zh/gameplay_zh（其余字段照抄）
4. `validate_translations.py` 门禁 → `import_stellaris_translations.py`
5. `confirm_stale_translations.py --from-file <merged.json>`
6. 复跑 `detect_stale` 应 content_stale=0；verify_db 健康

### 不变

- 不改 detect_stale 语义、不改 import 写库范围、不自动 AI 上线

## [S3] Out of Scope

- 全自动无人审重译
- 云端 cron 自动跑导出（可后续挂）
- CK3 专用入口（脚本用 --game 参数预留，默认 stellaris）

## Tasks

- [ ] T1: export_stale_tasks.py — acceptance: 对空腐化库输出空列表 exit 0；人为改一行 description 后能导出该 MOD 且含 description_clean 与 *_zh_current(covers: E)
- [ ] T2: confirm_stale_translations.py — acceptance: 对已改 description 的条目 confirm 后 detect_stale 内容腐化清零、stale=0(covers: C; depends: T1)
- [ ] T3: 自检 — acceptance: py_compile；pytest 12 仍绿；端到端模拟「改原文→导出→confirm」闭环(covers: E,C; depends: T1,T2)
