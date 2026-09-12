# 翻译腐化 / 扩充 · 每周例行清单

> 目标：作者更新后中文不掉队；新进榜/变薄字段能补上。  
> 频率：建议每周一次（约 10–20 分钟操作 + 子智能体批译时间）。  
> 工作目录：`C:\Users\wangf\Desktop\群星工具\stellaris-mod-zh`  
> 依赖：云端每日 04:00 重抓、04:30 `detect_stale --mark-stale` 已在跑。

## A. 开工前（1 分钟）

```powershell
cd C:\Users\wangf\Desktop\群星工具\stellaris-mod-zh
python scripts\verify_db.py          # 应 ✅ 健康
```

## B. 发现缺口（2 分钟）

```powershell
# 1) 作者更新导致的旧译
python scripts\detect_stale_translations.py --json --mark-stale

# 2) 新进榜 / 未译 / 复薄
python scripts\export_expand_tasks.py --report
```

**判定**

| 结果 | 动作 |
|---|---|
| 两边都是 0 | 本周跳过，结束 |
| 只有 stale | 只走 C→E |
| 只有 expand 未译/薄 | 只走 D→E |
| 都有 | 先 stale 再 expand |

## C. 导出腐化任务包（stale）

```powershell
mkdir translations\stale_wave -ErrorAction SilentlyContinue
python scripts\export_stale_tasks.py --start 1 --end 25 > translations\stale_wave\stale_task_001.json
```

- 超过 25 条：`--start 26 --end 50` 再导一份。
- 子智能体 prompt 要点（与 deep 相同）：
  - 只重写 `description_zh` / `gameplay_zh`
  - `title/summary/reviews/features` **原样照抄** `*_zh_current`
  - 发现串扰只上报不改写
  - 禁止编造评分/玩家言论

## D. 导出扩充任务包（expand）

```powershell
mkdir translations\expand_wave -ErrorAction SilentlyContinue
python scripts\export_expand_tasks.py --export --only all --start 1 --end 50 > translations\expand_wave\expand_task_001.json
```

- 报告里的「新进榜未入库」**先不要译**，需先 `fetch_batch` + `import_new_batch` 抓进库。

## E. 导入与确认（5 分钟）

```powershell
# 合并子智能体产出后（merged JSON）：
python scripts\validate_translations.py <merged.json>     # 必须 0 命中
python scripts\import_stellaris_translations.py <merged.json>
python scripts\confirm_stale_translations.py --from-file <merged.json>   # 清 stale / 刷基线
python scripts\detect_stale_translations.py                                  # 应 content_stale=0
python scripts\verify_db.py
```

## F. 上云（仅当改了 mods 表/翻译且要公网一致）

```powershell
# 轻量：翻译变更走翻译 import + 重启（见 HANDOFF §8）
# 全量行变更：export_cloud_sync → 提交推送 → TAT 两步同步
```

若只改了本地、云端仍靠每日 04:00 重抓，可等下一次云端 detect。

## G. 收尾

- [ ] `git status` 只含本批产物  
- [ ] 提交推送（fix/import 存档）  
- [ ] 需要的话 `git pull` 云端 TAT  

## 命令速查

| 用途 | 命令 |
|---|---|
| 腐化检测 | `python scripts/detect_stale_translations.py --json --mark-stale` |
| 导出腐化包 | `python scripts/export_stale_tasks.py --start 1 --end 25` |
| 导出扩充包 | `python scripts/export_expand_tasks.py --export --limit 50` |
| 扩充报告 | `python scripts/export_expand_tasks.py --report` |
| 确认基线 | `python scripts/confirm_stale_translations.py --from-file <merged.json>` |
| 危险：批量销账 | `python scripts/confirm_stale_translations.py --all-content-stale`（**确认译文已更新后再用**） |

## 铁律

1. **confirm 前必须已 import 成功译文**——否则等于没译先销账。  
2. 新批次翻译必须过 `validate_translations.py`。  
3. 子智能体报错 ≠ 没做——先查磁盘产物。  
