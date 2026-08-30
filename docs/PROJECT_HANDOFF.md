# 项目说明书：Paradox 中文 MOD 查询工具（stellaris-mod-zh）

> **本文档是自包含交接说明书**——新会话/另一 AI 仅凭本文即可完整接手项目。
> 最后更新：2026-08-30（两轮维护，实测数据核对）
> **维护轮 1**：坑 #1 根因已修复（`upsert_mod` 改部分更新）；新增 `rebuild_all.py` 收敛流水线 /
> `verify_db.py` 数据体检 / `fetch_batch.py` 参数化抓取 / `export_trend.py` 趋势备份；
> 服务端加限流与 `/versions` 接口；前端版本下拉动态化；`build_db.py` 加 `--force` 防呆。
> **维护轮 2**：progress.json 由 `import_new_batch` 自动更新（迁移至 `data/stellaris/`）；
> DLC 标注并入中文翻译（81→107）；旧链路 15 个文件删除（见 `scripts/README.md`）；
> 云端经全量行存档与本地完全收敛（TAT 实测公网 577/577，见 §8 云同步机制）。
> **维护轮 3**：`calc_score` 收敛到 core（去双实现）；前端错误友好提示/ID 净化/URL 转义/
> 版本徽章动态化；新增场景卡入口与「复制清单」；新增 tests/ 与 GitHub Actions CI
> （push 即验证「从 git 源文件可重建健康库」）。

---

## ⚡ 一分钟速览（四个问题一次看清）

**1. 干了什么？**
一个面向 Paradox 游戏（群星 / CK3 / HOI4）的**中文 MOD 知识库与网页查询工具**：抓取 Steam 创意工坊公开数据 → 整理成结构化知识库（翻译/玩法/评价/DLC/版本/兼容性/汉化包/社区口碑）→ 提供网页查询（中英文+拼音搜索、版本筛选、MOD 详情、DLC 缺失检测等）→ 已部署到腾讯云公网。

**2. 干到哪了？（2026-08-30 实测快照）**

| 游戏 | MOD 数 | 已翻译 | 六字段覆盖 | 说明 |
|---|---|---|---|---|
| **群星** | **677**（目标 1020） | 677/677 | **100%** ✅ | batch17（#628-677）已完成，下一批 #678 |
| CK3 | 300 | 300/300 | Top30 完整 | 版本标注 300/300 ✅（1.13-1.19，Wiki 核实） |
| HOI4 | 0 | - | - | 空框架，未抓取 |

群星**六字段**（title / summary / description / gameplay / reviews / features）**100% 全覆盖**，每个 MOD 详情页都有：中文标题+简介+详细介绍+具体玩法+玩家评价+特色列表。

| 其他数据 | 群星现状 |
|---|---|
| 版本兼容标注 | 群星 577/577（280 显式 + 297 推断）；CK3 300/300（1.13-1.19，Wiki 核实） |
| DLC 依赖标注 | 107 个（英文+中文描述双轨检测，均标"可选"级） |
| 订阅热度趋势 | 577/577（云端已积累 6 天连续快照） |
| 汉化包 | 9 条（鸽组等，含目标版本） |
| 兼容性矩阵 | 16 条（冲突/依赖/最佳搭配/补丁） |
| 社区口碑 | 6 条（贴吧/B站/NGA，附来源 URL） |
| 废弃标注 | 42 个 deprecated |

**3. 要干什么？**
① 群星继续扩容到 Top 1020（剩余 443 个，脚本全自动化）② P2 新手引导/场景化入口 ③ HOI4 抓取 ④ CK3 深度字段精做与兼容性/口碑补全 ⑤ 社区口碑扩充（现仅 6 条）

**4. 用什么干？**
`Python 3.13（本地）/ 3.11.6（云端）+ SQLite + 无框架纯 JS 前端`；数据源 `Steam 官方 API（GetPublishedFileDetails，无需 Key）+ 创意工坊页面内嵌 JSON`；代码托管 `GitHub（kkalho/stellaris-mod-zh，master）`；云端 `腾讯云轻量服务器 + TAT 自动化助手（免 SSH 远程执行）+ tccli CLI`；服务器下载 GitHub 用 **jsDelivr CDN**（gh-proxy 有缓存问题，见技术坑）。

---

## 1. 项目是什么

**核心价值**：让中文玩家**秒查**一个 MOD 是什么、怎么玩、好不好玩、和谁冲突/搭配、缺不缺 DLC、适配哪个版本、有没有汉化包。

| 项 | 值 |
|---|---|
| 本地仓库 | `D:/Projects/walong/stellaris-mod-zh/` |
| GitHub | `https://github.com/kkalho/stellaris-mod-zh`（用户 kkalho，master 分支） |
| 云端公网 | `http://150.158.24.195:8080`（2026-08-30 已与本地收敛，公网实测 577/577） |
| 云端目录 | `/opt/stellaris-mod-zh`（systemd 服务 `stellaris-mod`） |

## 2. 架构（数据流全景）

```
展示层    web_server_multigame.py（HTTP 服务，默认 127.0.0.1:8080，云端 --host 0.0.0.0）
          web/index_multigame.html（前端，纯 JS 单文件，761 行）
功能层    core/ 下：
            dlc_checker.py      DLC 缺失检测
            localization_matcher.py  汉化包匹配
            local_scanner.py    本地 MOD 扫描（读 Paradox 目录）
            community_rating.py 社区口碑
            updater.py / steam_fetch.py  Steam 增量同步（订阅量）
            cli.py             命令行入口（update / community / trend_snapshot）
            game_config.py / mod_db.py   游戏抽象与 SQLite 封装
游戏层    games/{stellaris,ck3,hoi4}/config/game.py（继承 GameConfig，@register_game 注册）
数据层    data/<game>/{mods.db, local.db, localization.json, community_seed.json, update_state.json}
原始数据  data/details.jsonl（Steam 详情流水，607 行 / 4.1MB）
          data/workshop_top1000.json（官方榜单 1020 条）
          data/stellaris/progress.json（扩容进度，import_new_batch 自动更新）
          data/stellaris/mods_full_sync.json（云端全量行存档，export_cloud_sync 生成）
存档      translations/（翻译 JSON）+ translations/deep/（深度精做存档 + 数据库行存档）
```

**数据流**：Steam 榜单/详情（官方 API）→ 抓取脚本 → `data/details.jsonl` → 增量入库 `mods.db` → 翻译 JSON 导入 → 网页查询（`/api/<game>/...`）→ TAT 云端同步。

## 3. 数据库字段说明（群星 mods.db）

| 字段 | 说明 | 覆盖 |
|---|---|---|
| `title` / `title_en` | 中文显示名（优先）/ 英文原名 | 577 |
| `summary` | 一句话简介（translations 表） | 577 |
| `description` | 详细介绍（300-600 字精做） | 577 |
| `gameplay` | 具体玩法（要点式） | 577 |
| `reviews` | 玩家评价（好评/差评结构化） | 577 |
| `features` | 特色标签列表（JSON 数组，3-6 个） | 577 |
| `version` | 版本兼容：`适配 4.4` / `更新于 3.4 时期` | 577 |
| `optional_dlcs` | DLC 提及（JSON 数组，均标"可选"；英文+中文双轨检测） | 107 |
| `pinyin_idx` | 拼音搜索索引（英文+中文译名全拼+首字母） | 577 |
| `status` | `deprecated`（42 个）/ 其他废弃态 | 42 |
| `score` / `like_ratio` | 综合评分（订阅+收藏启发式）/ 好评率 | 577 |
| `subscriptions` / `favorites` | 订阅量 / 收藏数（Steam 同步） | 577 |
| `tags` | Steam 原始标签（逗号分隔，已配 188 条中文映射） | 577 |

**translations 表结构**：`(id, mod_id, field, zh_text, quality, updated_at)`，`field` 取值即上表六个翻译字段。
**trend 表结构**：`(steam_id, date, subs)`，每日一行，主键 `(steam_id, date)`。

## 4. 已实现功能（前端网页版）

- ✅ **场景卡入口**（首页四卡：🚀新手入门=精选推荐面板 / 🎨画面美化 / 📖剧情事件 / 🧩玩法扩展）
- ✅ **新手精选推荐面板**（`/api/<game>/picks` + `data/stellaris/beginner_picks.json`：贴吧汉化为社区共识附核实链接，其余按分类订阅量自动选出，非人工评测）
- ✅ **一键复制清单**（工具栏「📋 复制清单」：把当前筛选结果连同 Steam 链接整组复制，装机清单即得）
- ✅ **中英文 + 拼音搜索**（pinyin_idx 索引；如 `jugou`→巨构、`nvpu`→美味女仆）
- ✅ **版本兼容筛选**（下拉从 `/versions` 接口动态生成：全部 / 4.x / 4.4 / 4.3 …，附代号与计数）+ 卡片版本徽章（绿=当前大版本/灰=旧版，随数据走）
- ✅ **标签筛选**（Top 14 高频标签，已全部中文化，悬停显示英文原名）
- ✅ **排序**：订阅量升降 / 最近更新 / 名称
- ✅ MOD 详情（标题/简介/详细介绍/具体玩法/玩家评价/特色/评分/封面/废弃警告）
- ✅ DLC 缺失检测面板（勾选已购 DLC → 检测缺依赖 MOD）
- ✅ 汉化包版块（数据库 + 详情页展示 + 总览面板）
- ✅ 本地 MOD 检测版块（读取 local.db，标记已收录/未收录）
- ✅ 订阅热度趋势（每日快照 + 涨跌榜，577/577 全覆盖）
- ✅ 兼容性矩阵（冲突/依赖/最佳搭配/补丁）、社区口碑（评分+摘要+来源）
- ✅ 游戏切换（群星/CK3/HOI4 左上角下拉）
- ✅ **URL 状态同步**（q/tag/version/sort/n/page/详情 id 全部入 URL：查询可分享、刷新不丢、浏览器前进后退可用）
- ✅ **详情直达定位**（点卡片平滑滚到详情主体，返回恢复列表滚动位置）
- ✅ **作者主页外链**（Steam 数字 ID 不再直出，点击跳转 steamcommunity 作者页）
- ✅ 请求错误友好提示（限流/异常时面板显示后端 error 文案，不白屏）
- ✅ **CI**（GitHub Actions：编译检查 + pytest + 从 git 源文件重建库 + verify_db 体检，push 即验证「数据库可从 git 完整重建」）

## 5. 待办（按优先级）

> **完整路线图见 `docs/ROADMAP.md`**（含短/中/长期规划与已知工程债）。下表为当前快照：

| 优先级 | 事项 | 说明 |
|---|---|---|
| **P1** | **群星扩容** | 已到 #627+，流程全自动（fetch_batch → import_new_batch → 子智能体翻译 → rebuild_all），见 §7 |
| **P2** | 新手引导深化 | 🌟精选推荐面板已上线；"第一局推荐"类人工评测内容需 WebSearch/社区核实后扩充，禁止编造 |
| **P2** | 老批次 reviews 回检 | batch2/8/9 的「官方数据显示 5 星好评」类表述超出作者自述，见 ROADMAP 短期 #3 |
| **P3** | CK3 专属界面 + 云同步泛化 | 版本链已完成；界面与多游戏云同步见 ROADMAP |
| **P3** | HOI4 抓取 | 复用 CK3 脚本链改 app_id（394360）；启动页已有"建设中"占位 |

## 6. 工具链（用什么干——全部实测可用）

| 工具 | 用途 | 关键点 |
|---|---|---|
| **Steam 官方 API** | GetPublishedFileDetails（POST，无需 Key）抓详情 | 单批 ≤50 个 ID；本机/云端均有时段性封锁，脚本需快速失败 |
| **Steam 页面内嵌 JSON** | 创意工坊榜单（`window.SSR.renderContext`） | `fetch_workshop_top.py` 抓前 1020 |
| **GitHub** | 代码托管 + Release | `kkalho/stellaris-mod-zh`；服务器下载走 **jsDelivr CDN**（推荐）或 gh-proxy |
| **腾讯云 TAT 自动化助手** | **免 SSH 远程执行命令**（云端运维核心） | `tccli tat RunCommand`（Content base64 ≤64KB）+ `DescribeInvocationTasks --Filters '[{"Name":"invocation-id","Values":["inv-xxx"]}]' --HideOutput false`（输出 base64） |
| **tccli（腾讯云 CLI）** | 查资源/执行 TAT | 已登录 profile default，地域 `ap-shanghai`，实例 `lhins-ca3ol8ju` |
| **jsDelivr CDN** | 服务器拉 GitHub 文件（推荐方案） | `https://cdn.jsdelivr.net/gh/kkalho/stellaris-mod-zh@master/<path>`，比 gh-proxy 缓存更新快 |
| **gh-proxy.com** | 备选镜像 | ⚠️ 有缓存问题（曾反复拉到旧版），大文件（>1MB）易截断 |
| **WebSearch** | 社区口碑/汉化包核实 | 交叉验证，禁止编造 |
| **本地 Python venv** | 开发/抓取环境 | `C:/Users/wangf/.workbuddy/binaries/python/envs/default/Scripts/python.exe`（已装 pypinyin） |

## 7. 群星扩容标准流程（每批 50 个，约 10 分钟）

**已跑到 #677，下一批 #678-727。用参数化的 `fetch_batch.py`（不要再复制 batch 脚本）。**

```bash
# 1) 抓详情（参数化，无需改代码）
python scripts/fetch_batch.py --start 678 --end 727     # → 追加到 data/details.jsonl
#  ⚠️ 等抓取完成：wc -l data/details.jsonl 两次一致再继续

# 2) 增量入库（不动已有数据，upsert；自动更新 data/stellaris/progress.json）
python scripts/import_new_batch.py 578 627

# 3) 精做翻译（六字段：title/summary/description/gameplay/reviews/features）
#    建议用子智能体并行：每批 50 个拆 1-3 个子 Agent，各自输出 JSON
#    格式见 §9；中文 MOD 保留原名；reviews 只写作者自述，禁编造

# 4) 导入翻译
python scripts/import_stellaris_translations.py translations/batchN_zh.json

# 5) 重跑标注脚本（或直接跑第 5.5 步一键收敛，代替 5~6 全部步骤）
python scripts/detect_stellaris_versions.py      # 版本兼容标注
python scripts/detect_stellaris_dlcs.py          # DLC 依赖标注
python scripts/rebuild_pinyin_idx.py             # 拼音索引（含中文译名拼音）

# 5.5) 推荐替代 5~6：python scripts/rebuild_all.py
#      （收敛式流水线：元数据/翻译/口碑导入 + 标注 + 拼音 + 快照 + 体检，全幂等）

# 6) 趋势快照
python scripts/snapshot_trend.py --game stellaris

# 7) 提交 + 云端同步（见 §8）
git add -A && git commit -m "..." && git push origin master
```

**翻译质量基准**（参照前 10 个精做 MOD）：
- `description` 300-600 字，要点式「•」排版
- `gameplay` 300-600 字，讲清楚怎么玩
- `reviews` 150-300 字，好评/差评结构化
- `features` 3-6 个 4-12 字短标签

## 8. 云端部署（完整方法）

**服务器**：腾讯云轻量应用服务器「DeepSeek TUI-ODDY」
- 实例 ID `lhins-ca3ol8ju`｜上海 ap-shanghai｜**2核 / 1.9G 内存 / 36G 磁盘**｜OpenCloudOS 9.6
- 公网 **150.158.24.195**｜防火墙已放行 8080 / 8000 / 18789 / 22 / 80 / 443
- Python 3.11.6｜git 2.43.7｜vim 9.0｜**tmux 未安装**
- 网络：**GitHub 直连不通**，Steam API 连通正常

**首次部署**（免 SSH，全程 API）：
1. 本地打包：代码 + data/ 各 mods.db + `deploy_lighthouse.sh` → `tar -czf`
2. 上传：`gh release create deploy-XXXX <包> --repo kkalho/stellaris-mod-zh`
3. 服务器执行：TAT RunCommand 推命令 → `curl -L` 从镜像下载 → `tar -xzf` → `bash deploy_lighthouse.sh`（装依赖 → 拷到 `/opt/stellaris-mod-zh` → 建 systemd 服务 `stellaris-mod`）
4. 验证：`curl http://150.158.24.195:8080/api/stellaris/stats`

**日常同步（代码/翻译）**：
```bash
# 本地生成 TAT 脚本（jsDelivr 拉取 → 导入 → 重启 → 验证），例：
#   curl -sL -o <文件> "https://cdn.jsdelivr.net/gh/kkalho/stellaris-mod-zh@master/<路径>"
#   /usr/bin/python3 scripts/import_stellaris_translations.py translations/xxx.json
#   sudo systemctl restart stellaris-mod
B64=$(base64 -w0 cloud_sync.sh)
tccli tat RunCommand --region ap-shanghai --Content "$B64" \
  --InstanceIds '["lhins-ca3ol8ju"]' --CommandType SHELL --Timeout 300
```

**数据库不同步 git（.gitignore）**，云端更新方式（按推荐顺序）：
1. ⭐ **全量行存档（现役机制，2026-08-30 起实测跑通）**：
   - 本地 `python scripts/export_cloud_sync.py` → git 提交推送（data/stellaris/mods_full_sync.json）
   - TAT 执行同步脚本：curl 从 jsDelivr 拉**固定 commit SHA** 的代码与存档（逐文件字节数校验，防截断/防缓存陈旧）→ `apply_cloud_sync.py`（UPDATE 保云端主键 + INSERT 分流，不破坏 translations/trend 外键）→ 导入新批次翻译 → 重启服务 → curl 自验
   - 2026-08-30 实战记录：更新 527 + 插入 50 = 577，公网复验 stats/DLC/版本接口与本地逐位一致；脚本模板见 `scripts/cloud_sync_example.sh`
2. 同款脚本重新生成（import_new_batch / import_stellaris_translations / detect_*）——适合只差翻译/标注的场景
3. 大文件（如 4.5MB 的 details.jsonl / mods_full_sync.json）**不要用 curl 拉旧镜像**，会截断（坑 #3）；必须拉时用 jsDelivr 固定 SHA + 字节数校验。**大存档建议同时提交 .gz 副本**（约 1/4 体积）：2026-08-30 r7 实测 4.7MB 明文两次 TAT 超时，1.07MB .gz 一次成功（云端 `gunzip -f` 解压后校验字节数）

**每日自动更新**：服务器 crontab `0 4 * * *` 跑 `core.cli update --game stellaris --force`（Steam 同步订阅量 + 趋势快照）。云端已积累 6 天连续快照。
**趋势备份（推荐加到同一 cron）**：cron 追加 `python scripts/export_trend.py`，把 trend 表导出成 `data/stellaris/trend_export.json`；需要回传本地时用 TAT 执行 `gzip -k trend_export.json && base64 trend_export.json.gz`（gzip 后约 20-40KB，满足 TAT 64KB 输出上限）。

## 9. 常用命令速查

```bash
# 本地启动服务（默认 127.0.0.1:8080；云端 --host 0.0.0.0）
python web_server_multigame.py 8080 --no-browser [--host 0.0.0.0]

# 数据更新（Steam 真实同步 + 趋势快照）
python -m core.cli update --game stellaris --force --stale-days 1

# ⭐ 数据体检（一条命令验健康度；接手/改库后先跑这个）
python scripts/verify_db.py                # 退出码 1 = 有「标注归零」类问题

# 单元测试（CI 同款：编译 + 测试 + 重建 + 体检四连）
python -m pytest tests -q

# ⭐ 收敛式重建（字段归零/漏导入/改坏库的万能修复，全幂等）
python scripts/rebuild_all.py              # --dry-run 只看步骤

# 重跑单项标注（一般用 rebuild_all 即可，单项脚本用于快速修补）
python scripts/detect_stellaris_versions.py
python scripts/detect_stellaris_dlcs.py
python scripts/rebuild_pinyin_idx.py
python scripts/snapshot_trend.py --game stellaris

# 抓取（参数化，替代 fetch_batch9~16）
python scripts/fetch_batch.py --start 578 --end 627 [--dry-run]

# 趋势导出（云端备份用）
python scripts/export_trend.py

# 翻译导入
python scripts/import_stellaris_translations.py translations/batchN_zh.json   # 群星
python scripts/import_ck3_translations.py translations/ck3_batchN_zh.json     # CK3

# 社区口碑导入
python -m core.cli community --game stellaris --import-file data/stellaris/community_seed.json

# 云端远程执行（TAT）
tccli tat RunCommand --region ap-shanghai --Content <base64命令> \
  --InstanceIds '["lhins-ca3ol8ju"]' --CommandType SHELL --Timeout 300
tccli tat DescribeInvocationTasks --region ap-shanghai \
  --Filters '[{"Name":"invocation-id","Values":["inv-xxx"]}]' --HideOutput false

# 查 API 覆盖
curl "http://127.0.0.1:8080/api/stellaris/stats"          # 统计
curl "http://127.0.0.1:8080/api/stellaris/search?q=巨构&sort=subs&tag=Gameplay&version=4.4&n=10"
curl "http://127.0.0.1:8080/api/stellaris/mod?id=1121692237"  # 详情
curl "http://127.0.0.1:8080/api/stellaris/categories"     # 标签（含 tag_zh）
curl "http://127.0.0.1:8080/api/stellaris/trend"          # 涨跌榜
```

**翻译 JSON 格式**（`translations/batchN_zh.json`）：
```json
{
  "game": "stellaris",
  "source": "Steam 原文核实 + AI 翻译（第 N 批：榜单 X-Y）",
  "translations": [
    {"steam_id": "1726290528", "title_zh": "...", "summary_zh": "...",
     "description_zh": "...", "gameplay_zh": "...", "reviews_zh": "...",
     "features_zh": ["特色1", "特色2"]}
  ]
}
```
**深度精做存档**（`translations/deep/deep_*.json`）是数组格式，字段为 `steam_id` / `description` / `gameplay` / `reviews` / `features`，需用自定义脚本导入（`on conflict do update`）。

## 10. 关键技术坑（血泪教训，勿重蹈）

1. **并行会话重建清数据**（⚠️ 曾最高频，2026-08-30 已根治）：根因是 `ModDB.upsert_mod` 更新已有 MOD 时会把未提供的字段整体清空，任何「重建+重灌」链路（`update_all.py` → `build_db.py` → 迁移）都会触发。**已修复三道防线**：① `upsert_mod` 改为部分更新（未提供的字段保持原值，单测覆盖）；② `build_db.py` 必须显式 `--force` 才肯重建、`update_all.py` 已硬停用；③ 新增 `scripts/verify_db.py` 一条命令体检（字段归零立即报出）。**若体检仍报归零（如旧库或新场景），跑 `python scripts/rebuild_all.py` 即可收敛恢复**，或手动重跑 `detect_stellaris_versions.py` + `detect_stellaris_dlcs.py`。
2. **gh-proxy 缓存旧版**：反复拉取都拿到旧文件。解决：改用 **jsDelivr CDN**；或在脚本里校验文件字节数，小于预期就重试。
3. **大文件 curl 截断**：服务器拉 4.1MB 的 `details.jsonl` 只传下 474KB，导致 JSON 解析失败、导入 0 条。解决：数据库变更导出成小 JSON 存档直插，别拉大文件。
4. **云端缺目录**：`curl -o translations/deep/xxx.json` 若目录不存在会静默失败。脚本里先 `mkdir -p`。
5. **多实例抢占 8080**：旧进程没杀干净，新服务起不来或 curl 连到旧代码。解决：`Get-Process python | Stop-Process -Force`（PowerShell），确认 `netstat` 只有一个监听。
6. **git bash 下 taskkill 语法**：`taskkill //F //PID` 在 Git Bash 报错，必须用 PowerShell 工具。
7. **版本通配误匹配**：`LIKE '%3.%'` 会误中 `4.3`。正确做法：通配 `3.x` 用 `LIKE '%3.%'` 配合"适配/更新于"前缀语义，并实测验证 0 误匹配。
8. **Steam 域名时段性封锁**：抓取脚本必须 ConnectionError 快速失败，不傻等重试。
9. **本机 venv 缺根证书**：requests 访问 https 报 CERTIFICATE_VERIFY_FAILED。**2026-08-30 已正确修复**：fetch_batch / core.steam_fetch 优先用 truststore 走 Windows 系统证书库（`pip install truststore`），TLS 校验保持开启；verify=False 已全部移除。极罕见情况才需要 fetch_batch 的 --insecure 兜底。
10. **旧库/新库路径**：旧单游戏库 `data/stellaris_mods.db`（已于 2026-08-30 删除，git 历史可查，build_db --force 可再生）；新架构 `data/stellaris/mods.db`。旧脚本 `import_translations.py` 已删除——群星用 `import_stellaris_translations.py`。
11. **抓取未完成就导入**：增量导入前确认 `wc -l data/details.jsonl` 两次一致。
12. **TAT 细节**：参数是 `--Filters`/`--InvocationTaskIds`；输出默认隐藏需 `--HideOutput false`；输出是 base64；Content base64 ≤64KB。
13. **Keep-Alive 挂起**：web 服务必须 `protocol_version="HTTP/1.0"` + ThreadingHTTPServer；访问用 127.0.0.1 而非 localhost。
14. **SQLite 锁**：web 服务每请求独立连接，`PRAGMA busy_timeout=8000`；外部脚本改库后旧连接可能挂死。
15. **CRLF 警告**：git 提交时 LF/CRLF 转换警告属正常，不影响功能。

## 11. 数据真实原则（铁律）

- 所有 MOD 数据必须来自 **Steam 官方 API / 创意工坊页面 / 官方 Wiki** 核实，**禁止编造**
- DLC 依赖：无明确 require 依据的一律标「**可选**」（描述提及级），不谎称必需
- 玩家评价 `reviews`：只写**作者自述**的定位/适用人群/已知问题，**禁止编造订阅量、评分、玩家言论**
- 已废弃/过时的 MOD **必须如实标注**（前端有 `⚠ 已废弃` 徽章）
- 社区口碑需 **WebSearch 交叉验证**并附来源 URL

## 12. 文件清单

| 路径 | 说明 |
|---|---|
| `web_server_multigame.py` | HTTP 服务（多游戏 API，10 个路由；含限流/错误脱敏） |
| `web/index_multigame.html` | 前端单文件（纯 JS；版本下拉从 `/versions` 接口动态生成） |
| `core/` | 功能层：DLC 检测/汉化包/本地扫描/口碑/updater/steam_fetch/cli（`mod_db.upsert_mod` 已改部分更新） |
| `games/{stellaris,ck3,hoi4}/config/game.py` | 游戏配置（TAG_ZH 标签映射、VERSION_NAMES 版本代号、DLC 清单、本地目录） |
| `scripts/` | **见 scripts/README.md（工具分工总览）**：rebuild_all（收敛重建）/ verify_db（体检）/ fetch_batch（参数化抓取）/ export_trend / export_cloud_sync + apply_cloud_sync（云端全量同步对）/ import_new_batch（含 progress.json 自动更新）/ 导入与标注脚本；CK3 工具链（P3 用） |
| `translations/` | 翻译存档（batchN_zh.json + deep/ 深度精做存档） |
| `data/` | details.jsonl / workshop_top1000.json / <game>/mods.db / stellaris/progress.json / stellaris/mods_full_sync.json |
| `docs/` | PROJECT_HANDOFF.md（本文）、MULTI_GAME_ARCHITECTURE.md |
| `tests/` | 最小测试集（`python -m pytest tests -q`：upsert 部分更新/评分/版本筛选回归） |
| `.github/workflows/ci.yml` | CI：编译检查 + 测试 + **从 git 源文件重建库 + verify_db**（可复现性验证） |

**已删除/防呆**：旧链路 15 个文件已于 2026-08-30 删除（清单与去向见 `scripts/README.md`，git 历史可查）；`build_db.py` 保留但需显式 `--force`（面向旧库）。

**群星翻译批次**：batch2/8/9（#1-277）· batch10-14（#278-527）· batch15（#528-577）· batch16（#578-627）· batch17（#628-677）· 下一批 #678（`fetch_batch.py --start 678 --end 727`）
**深度精做存档**：`translations/deep/deep_old_batch{0-3}`（原库段 171 个补译）· `deep_batch{10,12,13}`（扩容段）· `deep_new50`（50 个精做升级）· `deep_new50_mods`（数据库行存档）· `deep_trend`（趋势存档）

## 13. 接手检查清单（新 AI 开工前必做）

1. `cd D:/Projects/walong/stellaris-mod-zh && git log --oneline -5` —— 确认最新提交
2. `python scripts/verify_db.py` —— 数据体检（退出码 0 = 健康；报归零先跑 `rebuild_all.py`）
3. `curl http://127.0.0.1:8080/api/stellaris/stats` —— 本地服务是否正常（未启动则起服务）
4. `curl http://150.158.24.195:8080/api/stellaris/stats` —— 云端公网是否可达
5. 读 `data/stellaris/progress.json` —— 确认扩容进度（import_new_batch 自动维护）
6. **改任何数据后**：跑 `python scripts/verify_db.py` 确认健康 → git 提交 → TAT 云端同步 → 公网复验
