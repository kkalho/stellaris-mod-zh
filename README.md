# Paradox 中文 MOD 管理工具 (Paradox MOD ZH)

> 面向 Paradox 游戏（群星 / 十字军之王 3 / 钢铁雄心 4）的**中文 MOD 知识库与查询工具**。
> 输入 Mod 名称（中英文/拼音均可），秒出该 Mod 的中文介绍、玩法、评分、兼容性与社区口碑。

![收录](https://img.shields.io/badge/收录-227%2B%20Mod-blue)
![中文覆盖](https://img.shields.io/badge/中文覆盖-100%25-brightgreen)
![多游戏](https://img.shields.io/badge/支持游戏-3-orange)
![数据来源](https://img.shields.io/badge/数据来源-Steam%20Workshop-brightgreen)

## 为什么做这个？

Paradox 游戏创意工坊有海量 Mod，绝大多数由国外作者用英文撰写。对于中文玩家，想快速了解一个 Mod 是干什么的、值不值得订阅、和哪些 Mod 冲突/搭配，往往要逐词翻译、反复查论坛。本项目把**热门 Mod 预翻译成中文知识库**，并整合 DLC 依赖、汉化包、社区口碑等决策信息——一次整理，无限复用，离线秒查。

## 功能特性

- 🎮 **多游戏支持**：群星（完整 227 MOD）/ 十字军之王 3 / 钢铁雄心 4（框架就绪）
- 🔍 **智能搜索**：中文 / 英文 / **拼音**（`jugou`→巨构）/ 同义词（`巨型建筑`→巨构）
- 📚 **预翻译知识库**：群星 227 个热门 Mod，中文覆盖率 100%
- 🖼️ **截图预览**：每个 Mod 带 Steam 官方封面图（列表缩略图 + 详情大图）
- 🔗 **兼容性矩阵**：冲突 / 依赖 / 最佳搭配 / 兼容补丁 / 加载顺序（Top 16）
- 📄 **玩法真相溯源**：玩法内容标注信息来源（Steam 原文 / Paradox 官方 Wiki）
- 💬 **玩家评价**：好评 + 差评（基于订阅量、点赞率与社区共识）
- ⭐ **综合评分**：好评率 + 订阅热度 → 0-10 分（列表徽章 + 详情展示）
- ⚠️ **废弃警告**：Outdated / Deprecated / Abandoned Mod 红色标记
- 📥 **一键订阅**：详情页直达 Steam 订阅页 + 复制 Mod ID
- 🧩 **DLC 依赖检测**：自动识别必需/可选 DLC，缺失时警告
- 🌏 **汉化包匹配**：自动匹配对应汉化包，版本兼容性校验
- 💽 **本地 MOD 检测**：扫描本机已装 MOD（Steam/自制），标注知识库覆盖情况
- 🏙️ **中文社区口碑**：贴吧 / B站 / NGA 评分与评论摘要
- 🔄 **数据自动更新**：定时 / 手动 / 增量同步机制
- ⚡ **本地离线查询**：毫秒级响应，无需联网
- 🆓 **无需 API Key**：数据来自 Steam 官方公开 API

## 快速开始

### 方式一：网页版（推荐）

**Windows 用户**：双击 `启动-MOD管理工具.bat`，浏览器自动打开界面。

**手动启动（多游戏版）**：
```bash
python web_server_multigame.py 8080
# 浏览器打开 http://localhost:8080（顶部可切换游戏）
```

### 方式二：命令行（多游戏 CLI）

```bash
python -m core.cli list-games                          # 列出支持的游戏
python -m core.cli search 巨构 --game stellaris        # 中英文/拼音搜索
python -m core.cli scan --game stellaris               # 扫描本地 MOD
python -m core.cli dlc-check --owned 281992,392450     # DLC 缺失检测
python -m core.cli localize --game stellaris           # 汉化包列表
python -m core.cli community --import-file data/stellaris/community_seed.json  # 导入社区口碑
python -m core.cli update --force --game stellaris     # 数据更新
```

### 方式三：旧版单游戏（群星专用，保留兼容）

```bash
python scripts/web_server.py 8080     # 旧版网页
python scripts/modlookup.py 巨构      # 旧版命令行
```

## 项目结构

```
stellaris-mod-zh/
├── core/                     # 核心层（游戏无关）
│   ├── game_config.py        #   GameConfig 抽象 + 游戏注册表
│   ├── mod_db.py             #   统一数据访问（游戏隔离 SQLite）
│   ├── dlc_checker.py        #   DLC 依赖检测
│   ├── localization_matcher.py#  汉化包匹配
│   ├── local_scanner.py      #   本地 MOD 扫描
│   ├── community_rating.py   #   中文社区口碑
│   ├── updater.py            #   数据自动更新
│   └── cli.py                #   统一命令行入口
├── games/                    # 游戏配置层（可插拔）
│   ├── stellaris/config/game.py  # 群星（完整）
│   ├── ck3/config/game.py        # 十字军之王 3（框架就绪）
│   └── hoi4/config/game.py       # 钢铁雄心 4（框架就绪）
├── web/
│   ├── index_multigame.html  # 多游戏版网页界面
│   └── index.html            # 单游戏版网页界面（旧）
├── scripts/                  # 抓取/建库/迁移脚本
│   ├── migrate_to_multigame.py   # 旧库 → 多游戏架构迁移
│   ├── auto_fetch.py             # 自动抓取详情
│   └── ...
├── data/
│   └── <game>/               # 各游戏独立数据
│       ├── mods.db           # MOD 主库（元数据/翻译/兼容性/口碑）
│       ├── dlc.json          # DLC 清单
│       ├── localization.json # 汉化包数据库
│       └── community_seed.json # 社区口碑种子数据
├── web_server_multigame.py   # 多游戏版网页服务
└── 启动-MOD管理工具.bat        # Windows 一键启动（多游戏版）
```

## 新增游戏（扩展指南）

只需 3 步，约 30 分钟：
1. 复制 `games/stellaris/config/game.py` 到 `games/<新游戏>/config/game.py`
2. 修改 `game_id` / `game_name` / `steam_app_id` / 本地目录 / DLC 清单 / 标签映射
3. 在 `core/cli.py` 与 `web_server_multigame.py` 顶部各加一行 import

详细架构说明见 [docs/MULTI_GAME_ARCHITECTURE.md](docs/MULTI_GAME_ARCHITECTURE.md)。

## 数据更新

知识库数据来自 Steam 创意工坊**订阅量排行**（官方页面内嵌数据，截至 2026-08-22 群星已收录前 227 名）。

数据管道：抓取榜单 → 拉取详情（Steam 官方 API）→ 构建 SQLite → 导入翻译 → （可选）导入社区口碑/DLC/汉化包。

> 说明：Steam 对匿名 API 请求限流较严，抓取脚本默认每批 5 个、间隔 15 秒，支持断点续抓。

## 路线图

- [x] 群星 227 个热门 Mod 中文知识库（玩法溯源 + 玩家评价）
- [x] 网页 + 命令行双界面 + 多游戏架构
- [x] 兼容性矩阵 / 评分 / 废弃警告 / 智能搜索（拼音/同义词）
- [x] DLC 依赖检测 / 汉化包匹配 / 本地 MOD 检测 / 社区口碑 / 数据更新框架
- [x] 多游戏框架（群星完整，CK3/HOI4 就绪）
- [ ] 抓取 CK3 / HOI4 热门 Mod 数据
- [ ] 网页版展示 DLC 警告 / 汉化包 / 本地 MOD 版块
- [ ] 一键启动脚本整合多游戏版
- [ ] 扩展到 Top 500 / 1000 Mod

## 许可

本项目仅包含 Mod 的元数据与 AI 翻译内容，用于学习交流。Mod 版权归原作者所有，请通过创意工坊订阅支持作者。

**数据来源**：Steam 创意工坊公开页面与官方 Web API。
