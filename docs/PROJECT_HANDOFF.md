# 项目说明书：Paradox 中文 MOD 查询工具（stellaris-mod-zh）

> **本文档是自包含交接说明书**——新会话/另一 AI 仅凭本文即可完整接手项目。
> 最后更新：2026-08-24 21:15（与 git `3d2c10b` 一致）

---

## ⚡ 一分钟速览（四个问题一次看清）

**1. 干了什么？**
一个面向 Paradox 游戏（群星 / CK3 / HOI4）的**中文 MOD 知识库与网页查询工具**：抓取 Steam 创意工坊公开数据 → 整理成结构化知识库（翻译/评分/DLC/兼容性/汉化包/社区口碑）→ 提供网页查询（支持中英文搜索、MOD 详情、DLC 缺失检测等）→ 已部署到腾讯云公网。

**2. 干到哪了？（2026-08-24 数据快照）**
| 游戏 | MOD 数 | 已翻译 | 说明 |
|---|---|---|---|
| 群星 | **477**（目标 1000） | 477/477 | 扩容进行中，下一批 #478 |
| CK3 | 300 | 300/300 | 全部完成 |
| HOI4 | 0 | - | 空框架，未抓取 |
| 功能 | 汉化包 9 条 / 社区口碑 6 条 / DLC 标注 65 个 / 兼容性 16 条 | | 云端已部署、每日自动更新 |

**3. 要干什么？**
① 群星继续扩容到 Top 1000（剩余 543 个，脚本全自动化）② HOI4 抓取 ③ CK3 兼容性/口碑/汉化包 ④ updater 云端每日真实同步（Steam API 已恢复验证）

**4. 用什么干？**
`Python 3.13 + SQLite + 无框架纯 JS 前端`；数据源 `Steam 官方 API（GetPublishedFileDetails，无需 Key）+ 创意工坊页面内嵌 JSON`；代码托管 `GitHub（kkalho/stellaris-mod-zh）`；云端 `腾讯云轻量服务器 + TAT 自动化助手（免 SSH 远程执行）+ tccli CLI`；服务器下载 GitHub 用 `gh-proxy.com` 镜像。

---

## 1. 项目是什么

**核心价值**：让中文玩家**秒查**一个 MOD 是什么、怎么玩、好不好玩、和谁冲突/搭配、缺不缺 DLC、有没有汉化包。

- 本地仓库：`D:/Projects/walong/stellaris-mod-zh/`
- GitHub：`https://github.com/kkalho/stellaris-mod-zh`（用户 kkalho，master 分支）
- 云端：`http://150.158.24.195:8080`（腾讯云轻量服务器，公网可用）

## 2. 架构（数据流全景）

```
展示层    web_server_multigame.py（HTTP 服务，--host 参数控制监听）+ web/index_multigame.html（前端，纯 JS）
功能层    core/ 下：dlc_checker.py · localization_matcher.py · local_scanner.py · community_rating.py · updater.py · steam_fetch.py · cli.py
游戏层    games/{stellaris,ck3,hoi4}/config/game.py（继承 GameConfig，@register_game 注册）
核心层    core/game_config.py（抽象+注册表）· core/mod_db.py（ModDB：游戏隔离 SQLite）
数据层    data/<game>/{mods.db, local.db, dlc.json, localization.json, community_seed.json, update_state.json}
原始数据  data/details.jsonl（Steam 详情流水）· data/workshop_top1000.json（官方榜单 1020 条）· data/progress.json（翻译进度）
```

**数据流**：Steam 榜单/详情（官方 API）→ 抓取脚本 → mods.db（SQLite）→ 翻译 JSON → 导入 → 前端查询（/api/<game>/...）→ 云端部署（TAT 同步）

## 3. 数据现状（2026-08-24 实测）

| 数据维度 | 群星 | CK3 | HOI4 |
|---|---|---|---|
| MOD 总数 | 477（扩容中） | 300 | 0 |
| 中文翻译 | 477/477 | 300/300 | - |
| DLC 依赖标注 | 65 个（可选级启发式） | 启发式 | - |
| 汉化包 | 9 条 | - | - |
| 社区口碑 | 6 条（贴吧/B站/NGA） | - | - |
| 兼容性矩阵 | 16 个热门 | - | - |
| 封面图 | 100% | 100% | - |

**数据真实原则**：所有数据必须来自 Steam 官方/公开渠道核实，禁止编造。DLC 依赖无明确 require 依据一律标「可选」。

## 4. 已实现功能（前端网页版）

- ✅ 中英文搜索（拼音索引 pinyin_idx + 翻译参与匹配）
- ✅ MOD 详情（翻译描述/玩法/特性/评分/封面/废弃警告）
- ✅ DLC 缺失检测面板（勾选已购 DLC → 检测缺依赖 MOD）
- ✅ 汉化包版块（数据库 + 详情页展示 + 总览面板）
- ✅ 本地 MOD 检测版块（读取 local.db，标记已收录/未收录）
- ✅ 订阅热度趋势（每日快照 trend 表 + 涨跌榜）
- ✅ 兼容性矩阵（冲突/依赖/最佳搭配/补丁）、社区口碑（评分+摘要+来源）
- ✅ 游戏切换（群星/CK3/HOI4 左上角下拉）

## 5. 待办（按优先级）

1. **群星扩容**：#478 起，剩余 543 个到 Top 1000（脚本全自动化，每批：fetch_batchN 抓详情 → import_new_batch 增量入库 → batchN_zh.json 翻译 → import_stellaris_translations 导入 → git 提交 → TAT 云端同步）
2. **HOI4 抓取**：复用 CK3 脚本链改 app_id（394360）
3. **CK3 补充**：兼容性矩阵/社区口碑/汉化包
4. **updater 实跑确认**：Steam API 已恢复（2026-08-24 本机 277 个同步成功）；云端 crontab 每天 04:00 自动跑

## 6. 工具链（用什么干——全部实测可用）

| 工具 | 用途 | 关键点 |
|---|---|---|
| **Steam 官方 API** | GetPublishedFileDetails（POST，无需 Key）抓详情 | 单批 ≤50 个 ID；本机/云端均有时段性封锁，脚本需快速失败（ConnectionError 不重试） |
| **Steam 页面内嵌 JSON** | 创意工坊榜单（window.SSR.renderContext → queryData） | fetch_workshop_top.py 抓前 1000 |
| **GitHub** | 代码托管 + Release 放部署包 | kkalho/stellaris-mod-zh；服务器下载走 gh-proxy.com 镜像（直连会被限） |
| **腾讯云 TAT 自动化助手** | **免 SSH 远程执行命令**（云端运维核心） | `tccli tat RunCommand`（Content base64 ≤64KB）+ `DescribeInvocationTasks --Filters '[{"Name":"invocation-id","Values":["inv-xxx"]}]' --HideOutput false`（输出 base64） |
| **tccli（腾讯云 CLI）** | 查资源/执行 TAT | 已登录 profile default（UIN 100049338267 Root，地域 ap-guangzhou）；lighthouse DescribeInstances 查轻量服务器 |
| **gh CLI** | 创建 GitHub Release 上传部署包 | 已认证 kkalho |
| **WebSearch/WebFetch** | 社区口碑/汉化包核实（Steam 封锁时唯一核实通道） | 交叉验证避免编造 |
| **本地 Python venv** | 开发/抓取环境 | `C:/Users/wangf/.workbuddy/binaries/python/envs/default/Scripts/python.exe`（已装 pypinyin） |

## 7. 云端部署（完整方法）

**服务器**：腾讯云轻量应用服务器「DeepSeek TUI-ODDY」
- 实例 ID `lhins-ca3ol8ju`｜上海 ap-shanghai-5｜2C2G / 40GB SSD｜OpenCloudOS 9｜公网 **150.158.24.195**｜包年包月 2027-05-30 到期
- 防火墙已放行 8080（MOD 工具）/ 8000 / 18789(OpenClaw) / 22 / 80 / 443

**部署方式（免 SSH，全程 API）**：
1. 本地打包：`D:/Projects/temp/stellaris-mod-zh-deploy/`（代码 + data/ 各 mods.db + deploy_lighthouse.sh），`tar -czf` 产出部署包
2. 上传：`gh release create deploy-XXXX stellaris-mod-zh-deploy.tar.gz --repo kkalho/stellaris-mod-zh`
3. 服务器执行：TAT RunCommand 推命令 → 服务器 `curl -L` 从 gh-proxy 镜像下载 → `tar -xzf` → `bash deploy_lighthouse.sh`（装依赖→拷到 /opt/stellaris-mod-zh→systemd 服务 stellaris-mod→防火墙）
4. 验证：`curl http://150.158.24.195:8080/api/stellaris/stats`

**日常更新（数据同步到云端）**：
- 代码/翻译 JSON 走 git 提交 → TAT 命令 `curl` 拉取 raw（gh-proxy 镜像）→ 跑导入脚本 → `systemctl restart stellaris-mod`
- 数据库（mods.db 被 .gitignore）不直接传，云端用同款脚本（import_new_batch / import_stellaris_translations / detect_stellaris_dlcs）重新生成
- **每日自动更新**：服务器 crontab `0 4 * * * cd /opt/stellaris-mod-zh && /usr/bin/python3 -m core.cli update --game stellaris --force`（Steam 同步订阅量 + 趋势快照）

## 8. 常用命令速查

```bash
# 本地启动服务（默认 127.0.0.1；云端用 --host 0.0.0.0）
python web_server_multigame.py 8080 --no-browser [--host 0.0.0.0]
# 数据更新（Steam 真实同步 + 趋势快照）
python -m core.cli update --game stellaris --force --stale-days 1
# 群星扩容一批（例：#478-527）
python scripts/fetch_batch14.py            # 抓详情（改 rank 范围生成）
python scripts/import_new_batch.py 478 527 # 增量入库
python scripts/import_stellaris_translations.py translations/batch14_zh.json
# DLC 标注重检 / 社区口碑导入
python scripts/detect_stellaris_dlcs.py
python -m core.cli community --game stellaris --import-file data/stellaris/community_seed.json
# 云端远程执行（TAT）
tccli tat RunCommand --region ap-shanghai --Content <base64命令> --InstanceIds '["lhins-ca3ol8ju"]' --CommandType SHELL --Timeout 300
# git 提交推送
git add -A && git commit -m "..." && git push origin master
```

## 9. 关键技术坑（血泪教训，勿重蹈）

1. **Steam 域名时段性封锁**：steamcommunity.com / api.steampowered.com 在国内网络**有时段性全拒**（baidu 正常、WinError 10061）。抓取/更新脚本必须 ConnectionError 快速失败（见 steam_fetch.py 的 net_down 标志），不傻等重试。
2. **本机 venv 缺根证书**：requests 访问 https 报 CERTIFICATE_VERIFY_FAILED。**所有抓取脚本必须 verify=False + urllib3.disable_warnings()**。
3. **旧库/新库路径**：旧单游戏库 `data/stellaris_mods.db`，新架构 `data/stellaris/mods.db`。`import_translations.py` 连旧库——群星翻译用 `import_stellaris_translations.py`（新架构），CK3 用 `import_ck3_translations.py`。
4. **并行会话重建清数据**：`build_db.py` 全量重建会清 DLC 标注等字段。多会话协作时重跑 detect_stellaris_dlcs 等修复脚本。
5. **抓取未完成就导入**：增量导入前确认 `data/details.jsonl` 行数稳定（wc -l 两次一致）。
6. **TAT 细节**：DescribeInvocationTasks 参数是 `--Filters`/`--InvocationTaskIds`（不是 InvocationIds）；输出默认隐藏需 `--HideOutput false`；输出是 base64；命令 Content base64 ≤64KB；云端 curl 拉取必须校验文件字节数（曾静默失败）。
7. **服务器访问 GitHub 慢**：用 gh-proxy.com 镜像（`https://gh-proxy.com/https://raw.githubusercontent.com/...`），直连/ghproxy.net 都卡。
8. **Keep-Alive 挂起**：web 服务必须 `protocol_version="HTTP/1.0"` + ThreadingHTTPServer；访问用 127.0.0.1 而非 localhost（IPv6 解析延迟）。
9. **SQLite 连接锁死**：web 服务每请求独立连接，`PRAGMA busy_timeout=8000`；外部脚本改库后旧连接会挂死。
10. **翻译文件格式**：`translations/batchN_zh.json` → `{"translations":[{"steam_id","title_zh","summary_zh",...}]}`；中文 MOD 保留原名不翻译。

## 10. 翻译文件清单（群星批次）

- batch2/batch8/batch9：旧批次（#1-277）
- batch10（#278-327）、batch11（#328-377）、batch12（#378-427）、batch13（#428-477）
- CK3：ck3_top30_zh（#1-30 完整）、ck3_batch2_zh（#31-100）、ck3_batch3-6_zh（#101-300）
- progress.json 记录进度（下一批 #478）
