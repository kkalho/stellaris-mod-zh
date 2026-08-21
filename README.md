# 群星 Mod 中文手册 (Stellaris Mod ZH)

> 为《群星》(Stellaris) 创意工坊热门 Mod 建立的**中文知识库与查询工具**。输入 Mod 名称（中英文均可），秒出该 Mod 的中文介绍、特色和详细内容。

![GitHub stars](https://img.shields.io/badge/收录-227%2F1000%20Mod-blue)
![中文覆盖](https://img.shields.io/badge/中文覆盖-100%25-brightgreen)
![数据来源](https://img.shields.io/badge/数据来源-Steam%20Workshop-orange)

## 为什么做这个？

群星创意工坊有数以万计的 Mod，绝大多数由国外作者用英文撰写。对于中文玩家，想快速了解一个 Mod 是干什么的、值不值得订阅，往往要逐词翻译。本项目把**热门 Mod 预翻译成中文知识库**——一次翻译，无限复用，离线秒查。

## 功能特性

- 🔍 **中英文混合搜索**：输入「巨构」「giga」「星球多样性」都能搜到（中英文标题并存）
- 📚 **预翻译知识库**：177 个热门 Mod 已收录，中文覆盖率 100%
- 🖥️ **命令行 + 网页双界面**
- 🔀 **排序筛选**：按订阅量/更新时间/名称排序，按标签分类浏览
- 🖼️ **截图预览**：每个 Mod 带 Steam 官方封面图（列表缩略图 + 详情大图）
- 🔗 **兼容性矩阵**：冲突 / 依赖 / 最佳搭配 / 兼容补丁 / 加载顺序（Top 16）
- 📄 **玩法真相溯源**：玩法内容标注信息来源（Steam 原文 / Paradox 官方 Wiki）
- 💬 **玩家评价**：好评 + 差评（基于订阅量、点赞率与社区共识）
- ⚡ **本地离线查询**：毫秒级响应，无需联网
- 🆓 **无需 API Key**：数据来自 Steam 官方公开 API
- 🔄 **断点续抓**：自动抓取脚本支持中断后继续

## 快速开始

### 方式一：网页版（推荐）

**Windows 用户**：双击 `启动-群星Mod手册.bat`，浏览器自动打开界面。

**手动启动**：
```bash
python scripts/web_server.py 8080
# 浏览器打开 http://localhost:8080
```

### 方式二：命令行

```bash
python scripts/modlookup.py 巨构          # 关键词搜索（中英文均可）
python scripts/modlookup.py giga          # 英文关键词
python scripts/modlookup.py --top 20      # 订阅量 Top 20
python scripts/modlookup.py --id 1121692237  # 按 ID 查详情
python scripts/modlookup.py --full 巨构   # 显示完整翻译
```

## 查询示例

```
$ python scripts/modlookup.py 巨构
      订阅数 | Mod 名称
--------------------------------------------------------------
   568,668 | Gigastructural Engineering & More（巨构工程与更多）
             | 摘要: 群星最著名的巨型建筑扩展模组，新增 45 种巨型建筑和 4 个可选天灾危机。
```

## 项目结构

```
stellaris-mod-zh/
├── scripts/
│   ├── auto_fetch.py         # 自动抓取 Mod 详情（断点续抓、限速防封）
│   ├── build_db.py           # 构建 SQLite 知识库
│   ├── import_translations.py# 导入翻译 JSON
│   ├── modlookup.py          # 命令行查询工具
│   └── web_server.py         # 本地网页服务（零依赖）
├── web/
│   └── index.html            # 网页查询界面（星空主题）
├── translations/
│   ├── hot_top6_zh.json      # Top6 完整翻译
│   └── hot_rest_zh.json      # 其余 Mod 标题+摘要翻译
├── data/
│   ├── hot_mods.json         # 热门 Mod 清单（Top 210）
│   ├── details.jsonl         # 原始详情数据
│   └── stellaris_mods.db     # SQLite 知识库
└── 启动-群星Mod手册.bat        # Windows 一键启动
```

## 数据更新

知识库数据来自 Steam 创意工坊**订阅量排行**（官方页面内嵌数据，截至 2026-08-22 已收录前 227 名，自动化任务每日扩充 50 个，目标前 1000 名）。

数据管道：`scripts/fetch_workshop_top.py`（抓官方榜单）→ `scripts/build_db.py`（建库）→ `scripts/import_translations.py`（导翻译）。如需更新数据：

```bash
# 1. 更新热门清单（data/hot_mods.json，可通过创意工坊浏览页分页获取）
# 2. 自动抓取详情（支持断点续抓，限速防封）
python scripts/auto_fetch.py --sleep 15 --batch 5
# 3. 重建数据库
python scripts/build_db.py
# 4. 补充翻译后导入
python scripts/import_translations.py translations/你的翻译.json
```

> 说明：Steam 对匿名 API 请求限流较严，抓取脚本默认每批 5 个、间隔 15 秒。中断后重新运行会自动跳过已抓取的 Mod。

## 翻译贡献

欢迎通过 PR 补充翻译！翻译文件格式见 `translations/hot_top6_zh.json`：

```json
{
  "steam_id": "1121692237",
  "title_zh": "巨构工程与更多",
  "summary_zh": "一句话简介",
  "description_zh": "详细翻译",
  "features_zh": ["特色1", "特色2"]
}
```

## 路线图

- [x] 120+ 热门 Mod 中文知识库（目标 210，随抓取续补）
- [x] 命令行 + 网页双查询界面
- [x] Windows 一键启动
- [x] 订阅量/更新时间排序、标签分类浏览
- [x] 自动抓取脚本（断点续抓 + 限速防封）
- [ ] 扩展到 Top 500 / 1000 Mod
- [ ] 更多 Mod 的完整描述翻译
- [ ] 游戏内 Mod 列表导入（本地 MOD 检测）

## 许可

本项目仅包含 Mod 的元数据与 AI 翻译内容，用于学习交流。Mod 版权归原作者所有，请通过创意工坊订阅支持作者。

**数据来源**：Steam 创意工坊公开页面与官方 Web API。
