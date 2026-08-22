# Paradox 中文 MOD 管理工具 — 架构设计文档

## 1. 设计目标

面向 Paradox 游戏（Stellaris / CK3 / HOI4 等）的中文 MOD 管理工具，核心目标：
- **一套核心，多游戏扩展**：新增游戏只写配置文件，不改核心代码
- **真实数据优先**：DLC 依赖、汉化包、社区口碑均基于真实来源
- **可维护**：模块职责单一，数据流清晰

## 2. 分层架构

```
┌─────────────────────────────────────────────┐
│ 展示层      web_server / modlookup / CLI     │
├─────────────────────────────────────────────┤
│ 功能模块层   dlc_checker  localization_matcher│
│             local_scanner community_rating   │
│             updater  search_engine           │
├─────────────────────────────────────────────┤
│ 游戏配置层   games/stellaris  games/ck3       │
│             games/hoi4（可插拔）              │
├─────────────────────────────────────────────┤
│ 核心层      game_config（抽象） mod_db（数据） │
├─────────────────────────────────────────────┤
│ 数据层      data/<game>/*.db  *.json          │
└─────────────────────────────────────────────┘
```

## 3. 模块职责与交互

### 3.1 核心层
| 模块 | 职责 |
|---|---|
| `game_config.GameConfig` | 游戏抽象基类：本地目录 / DLC 清单 / 描述解析 / 标签映射 |
| `game_config.GAME_REGISTRY` | 游戏注册表，装饰器 `@register_game` 自动注册 |
| `mod_db.ModDB` | 统一数据访问，游戏隔离的 SQLite（mods/translations/compat/community 表） |

### 3.2 游戏配置层
每个游戏一个包，继承 GameConfig：
```
games/stellaris/config/game.py   # 已实现（177+ MOD 数据）
games/ck3/config/game.py         # 框架就绪（DLC/路径/解析已配）
games/hoi4/config/game.py        # 框架就绪
```
新增游戏步骤：复制任一游戏配置 → 改 game_id/app_id/路径/DLC/解析 → 注册。

### 3.3 功能模块层
| 模块 | 输入 | 输出 | 依赖 |
|---|---|---|---|
| `dlc_checker` | MOD 数据 + 用户 DLC 清单 | 必需/可选 DLC、缺失警告 | game.detect_required_dlcs |
| `localization_matcher` | 汉化包数据库 + MOD 版本 | 匹配汉化包、兼容性校验、下载 | game.localization.json |
| `local_scanner` | 本地 MOD 目录 | local.db（名称/版本/来源/大小） | game.local_mod_dirs / parse_descriptor |
| `community_rating` | 社区口碑 JSON | community 表 + 推荐指数 | mod_db |
| `updater` | 任务注册 + 状态 | 定时/手动/增量更新记录 | 各模块 |

### 3.4 数据流

```
抓取/录入
  Steam API → dlc_checker.detect → mods.required_dlcs → web 界面
  社区爬虫 → community_rating.import → community 表 → 推荐指数
  本地扫描 → local_scanner.scan → local.db → 界面「我的 MOD」

查询
  用户搜索 → mod_db.list_mods（中英/拼音）→ 结果 + score/status/compat
  用户点详情 → get_detail → 翻译 + DLC 警告 + 汉化包 + 社区口碑

更新
  updater.run → 各任务 → 增量同步订阅量 → update_state.json
```

## 4. 数据结构

### mods 表（核心，游戏隔离）
```
id / game_id / steam_id / title / title_en / author / version
subscriptions / favorites / views / time_created / time_updated
tags / url / preview_url / description / description_clean
required_dlcs(JSON) / optional_dlcs(JSON) / localization_id
score / like_ratio / community_score / status / pinyin_idx / translated
```

### 关联表
- `translations(mod_id, field, zh_text)` — title/summary/description/gameplay/reviews
- `compat(mod_id, conflicts, requires, best_with, notes, has_patches)` — 兼容性矩阵
- `community(mod_id, platform, score, comment_summary, recommend, source_url)`

### JSON 配置文件（data/<game>/）
- `dlc.json` — DLC 清单（app_id/中英文名）
- `localization.json` — 汉化包数据库（版本/来源/状态）
- `community.json` — 社区口碑缓存
- `update_state.json` — 更新状态（上次全量/增量/历史）

## 5. 扩展机制

### 新增游戏（约 30 分钟）
```python
@register_game
class CK3Config(GameConfig):
    game_id = "ck3"
    game_name = "十字军之王 3"
    steam_app_id = "1158310"
    # 实现 4 个抽象方法即可
```
然后在 `core/cli.py` 加一行 import。

### 新增功能模块
实现一个类，依赖 `GameConfig` + `ModDB` 两个接口即可接入，如 `community_rating`。

## 6. 已实现功能清单

| 功能 | 模块 | 状态 |
|---|---|---|
| DLC 依赖标注 | dlc_checker | ✅ 25 个 MOD 已检测，缺失警告可用 |
| 汉化包匹配 | localization_matcher | ✅ 匹配/版本校验/下载框架 |
| 本地 MOD 检测 | local_scanner | ✅ Steam/自制识别，知识库匹配 |
| 中文社区口碑 | community_rating | ✅ 评分/摘要/推荐指数 |
| 数据自动更新 | updater | ✅ 定时/手动/增量 + 状态持久化 |
| 多游戏扩展 | games/{stellaris,ck3,hoi4} | ✅ 3 游戏注册，架构就绪 |
| 智能搜索 | mod_db.list_mods | ✅ 中英/拼音 |

## 7. CLI 用法

```bash
python -m core.cli list-games
python -m core.cli search 巨构 --game stellaris
python -m core.cli scan --game stellaris
python -m core.cli dlc-check --owned 281992,392450 --game stellaris
python -m core.cli localize --game stellaris
python -m core.cli community --import-file data/stellaris/community_seed.json
python -m core.cli update --force --game stellaris
```
