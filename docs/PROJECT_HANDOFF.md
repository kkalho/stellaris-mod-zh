# 项目说明书：Paradox 中文 MOD 管理工具

> 本文档是**自包含交接文档**——新会话（新任务）仅凭本文即可完整接手项目。
> 最后更新：2026-08-22 18:20（与 git 待提交 一致）

---

## 1. 项目是什么

面向 Paradox 游戏（群星 Stellaris / 十字军之王 3 CK3 / 钢铁雄心 4 HOI4）的**中文 MOD 知识库与查询工具**。核心价值：让中文玩家**秒查**一个 Mod 是什么、怎么玩、好不好玩、和谁冲突/搭配、缺不缺 DLC、有没有汉化包。

- **仓库**：`D:/Projects/walong/stellaris-mod-zh/`（本地）
- **GitHub**：`https://github.com/kkalho/stellaris-mod-zh`（用户 kkalho，master 分支）
- **最新提交**：`8f954ad`（本次 CK3 数据提交后更新）

## 2. 当前状态（已实现）

### 2.1 数据现状（群星 / CK3）
| 数据 | 群星 | CK3 | 说明 |
|---|---|---|---|
| MOD 总数 | 227 | **300** | 创意工坊订阅量 Top（CK3 为新抓取） |
| 中文翻译 | 1020 条 | **100 条** | title/summary/description/gameplay/reviews（CK3 为 Top 100） |
| 玩法溯源 | 100% | 部分 | 每条玩法标注「信息来源：Steam 原文核实」 |
| 兼容性矩阵 | 16 个热门 | - | CK3 待做 |
| DLC 依赖 | 18 个 MOD | 启发式 | 均为「可选」（描述提及），无虚假必需 |
| 社区口碑 | 3 个热门 | - | 贴吧/B站/NGA，CK3 待做 |
| 封面图 | 100% | **100%** | Steam 官方图床 preview_url |
| 总分 | 227 | 300 | 订阅量合计 2064 万（CK3） |

### 2.2 已实现功能（16 项改进中完成 12 项）
✅ 截图预览 ✅ 兼容性矩阵 ✅ 玩法溯源(177/177) ✅ 废弃警告 ✅ 综合评分
✅ 智能搜索(拼音/同义词) ✅ 一键订阅 ✅ DLC 依赖标注 ✅ 汉化包匹配
✅ 本地 MOD 检测 ✅ 社区口碑 ✅ 数据自动更新框架 ✅ 多游戏架构
✅ 网页版 DLC 缺失检测面板

### 2.3 待办（未完成）
- [x] **抓取 CK3 热门 MOD 数据**（300 条已入库，Top 100 已翻译）← 2026-08-22 完成
- [ ] 抓取 HOI4 热门 MOD 数据（框架就绪，库为空）
- [ ] CK3 剩余 200 条翻译（101-300，下批从 rank 101 开始）
- [ ] 网页版汉化包展示版块（数据有，前端未渲染）
- [ ] 网页版本地 MOD 检测版块（API 有 /local，前端未渲染）
- [ ] updater 接入真实 Steam API fetch 函数（当前是占位）
- [ ] 订阅热度趋势（每日快照）
- [ ] 扩展到 Top 500/1000
- [ ] CK3/HOI4 的社区口碑、汉化包数据

## 3. 架构（务必先读这个）

### 3.1 分层结构
```
展示层    web_server_multigame.py（HTTP 服务）+ web/index_multigame.html（前端）
功能层    core/dlc_checker.py · localization_matcher.py · local_scanner.py
          core/community_rating.py · updater.py · cli.py
游戏层    games/{stellaris,ck3,hoi4}/config/game.py（继承 GameConfig）
核心层    core/game_config.py（抽象+注册表）· core/mod_db.py（数据访问）
数据层    data/<game>/{mods.db, local.db, dlc.json, localization.json, community.json}
```

### 3.2 核心接口
- `GameConfig`（core/game_config.py）：抽象基类，子类实现 4 个方法
  - `local_mod_dirs()` / `parse_descriptor()` / `load_dlcs()` / `detect_required_dlcs()`
  - 注册：`@register_game` 装饰器 → GAME_REGISTRY
- `ModDB`（core/mod_db.py）：游戏隔离 SQLite，表：mods / translations / compat / community
- 新增游戏 = 复制 `games/stellaris/config/game.py` 改配置 + 两处 import（cli.py 和 web_server_multigame.py）

### 3.3 启动方式
```bash
# 网页版（推荐）
python web_server_multigame.py 8080        # 自动开浏览器 http://127.0.0.1:8080
# 或双击「启动-MOD管理工具.bat」

# 命令行
python -m core.cli list-games
python -m core.cli search 巨构 --game stellaris
python -m core.cli scan --game stellaris            # 扫描本地 MOD
python -m core.cli dlc-check --owned 281992 --game stellaris
python -m core.cli localize --game stellaris
python -m core.cli update --force --game stellaris
```

### 3.4 数据流
- **抓取**：Steam 榜单 → `scripts/auto_fetch.py`（详情）→ `build_db.py`（建库）→ `import_translations.py`（翻译）
- **CK3 版抓取链**：`scripts/fetch_ck3_workshop_top.py`（榜单→data/ck3/workshop_top.json）→ `scripts/fetch_ck3_details.py`（详情→data/ck3/details.jsonl）→ `scripts/build_ck3_db.py`（直接写新架构 ModDB）→ `scripts/patch_ck3_missing.py`（榜单有/详情缺的兜底补录）→ `scripts/import_ck3_translations.py`（翻译导入）
- **迁移**：`scripts/migrate_to_multigame.py`（旧单游戏库 → 新多游戏架构）
- **查询**：前端 → `/api/<game>/search|mod|dlcs|dlc-missing|local` → ModDB

## 4. 关键技术坑（血泪教训，勿重蹈）

1. **服务器 Keep-Alive 挂起**：必须 `protocol_version = "HTTP/1.0"` + `ThreadingHTTPServer`。HTTP/1.1 keep-alive 在 Windows 连接复用会挂死（表现为第二个请求超时）。已修复于 `c7e0d66`。
2. **SQLite 连接锁死**：web 服务每请求**独立连接**（勿缓存共享），`PRAGMA busy_timeout = 8000`。外部脚本改库后旧连接会挂死。
3. **访问用 127.0.0.1 而非 localhost**：Windows 下 localhost 优先解析 IPv6 (::1)，服务只监听 IPv4 会白等 2 秒。
4. **前端 API 路径必须带游戏前缀**：`api('/api/' + GAME + '/...')`。`applyFilters` 曾漏加导致分类 404（`7ea1538` 修复）。
5. **Steam 限流**：`steamcommunity.com` 直连（requests/curl）会被重置连接；但 `api.steampowered.com` 的 `GetPublishedFileDetails` 无需 Key 可批量查详情；WebSearch/WebFetch 独立通道稳定。
6. **本机 venv SSL 证书缺失**：`requests` 访问 https 会 `CERTIFICATE_VERIFY_FAILED`（本机 Python venv 缺根证书）。**所有抓取脚本必须 `verify=False` + `urllib3.disable_warnings()`**（榜单与详情脚本均已处理）。
7. **数据真实原则**：DLC 依赖启发式检测有误报，**无明确 require 依据不标「必需」**，一律标「可选」。
8. **迁移脚本**：`ModDB.upsert_mod` 必须含 steam_id 字段；`LocalModInfo` 需含 size_mb 字段（曾漏）。
9. **旧库 schema 兼容**：`data/ck3/mods.db` 等旧建库缺少 `pinyin_idx` 列，写库前需 `PRAGMA table_info` 检查并 `ALTER TABLE ADD COLUMN`（见 build_ck3_db.py）。

## 5. 常用命令速查

```bash
# 服务
python web_server_multigame.py 8080 --no-browser   # 不自动开浏览器
# 测试接口
curl "http://127.0.0.1:8080/api/stellaris/search?q=巨构&n=5"
curl "http://127.0.0.1:8080/api/stellaris/dlc-missing?owned=281992"
# 数据库
python -c "import sqlite3; c=sqlite3.connect('data/stellaris/mods.db'); ..."
python -c "import sqlite3; c=sqlite3.connect('data/ck3/mods.db'); ..."
# CK3 抓取链（按序执行）
python scripts/fetch_ck3_workshop_top.py --pages 10   # 榜单 300 条
python scripts/fetch_ck3_details.py --sleep 12        # 详情（断点续抓）
python scripts/build_ck3_db.py                        # 建库
python scripts/patch_ck3_missing.py                   # 兜底补录
python scripts/import_ck3_translations.py             # 翻译导入
# 提交推送（GitHub 偶发网络波动需重试）
git add -A && git commit -m "..." && git push origin master
```

## 6. 开发约定

- Python 环境：`C:/Users/wangf/.workbuddy/binaries/python/envs/default/Scripts/python.exe`（venv，已装 pypinyin）
- 依赖：pypinyin（拼音搜索，必须）
- 网页前端：单文件 `web/index_multigame.html`（星空主题深色 UI，无框架纯 JS）
- 翻译文件格式：`translations/*.json`，含 `translations[].{steam_id, gameplay_zh, reviews_zh}` 等
- 社区口碑导入：`data/stellaris/community_seed.json`（格式见 `core/community_rating.import_json`）
- 提交信息用中文，说明改动内容

## 7. 项目质量现状

- **诚实说明**：CK3 数据已抓取入库（300 条），翻译完成 Top 100；HOI4 仍是空框架；社区口碑仅群星 3 个样例；DLC 依赖是可选级启发式；updater 的 Steam fetch 是占位
- **性能**：服务并发已优化，6 并发 0.13s；SQLite 毫秒级
- **测试**：无自动化测试脚本，靠 curl/CLI 手工验证

## 8. 下一步建议（按优先级）

1. **CK3 剩余翻译**：101-300 条中文标题/简介翻译（脚本已就绪，续写 translations/ck3_batchN_zh.json 即可）
2. **抓 HOI4 数据**：复用 CK3 脚本链，改 app_id（HOI4=394360）抓热门 Mod
3. **网页版汉化包 + 本地 MOD 版块**：后端数据/API 已就绪，只需前端渲染
4. **updater 接真实 Steam API**：实现增量同步订阅量
5. **数据自动化**：定时任务每日更新
