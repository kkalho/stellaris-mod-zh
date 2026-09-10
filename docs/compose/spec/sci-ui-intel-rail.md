---
feature: sci-ui-intel-rail
status: designed
updated: 2026-09-11
branch: feature/sci-fi-ui
commits: 
---

# 群星图鉴 · 右侧情报栏

## Report

## [S1] Problem

超宽屏上主内容 `max-width:1100px` 居中后,左轨右侧之外仍有大片空白(截图可见)。用户要求加右侧情报栏,常驻「热度 + 遗珠」混合信息。

## [S2] Design

### 显示条件

- `min-width: 1500px` 且 `body[data-view="game"]` 时显示 `aside.intel-rail`
- 窄屏隐藏;launcher 不显示
- 详情视图仍显示(不遮挡操作,宽屏有空间)

### 布局

- `position: fixed; right: 0; top: 0; bottom: 0; width: 300px; z-index: 40`
- 左边框 `1px solid var(--line)`,背景与左轨同系
- 主区:在已有 `has-rail` 基础上,`has-intel` 时 `.game-shell`/`footer` 增加 `margin-right: 300px`
- `body.has-intel` 由 `setRailChrome()` 在游戏视图设置(与左轨同步)

### 内容(自上而下)

1. **头部**:`// INTEL` + 当前星域名
2. **筛选读数**:当前列表条数(随 `allResults.length` 更新)、当前版本/标签摘要(有则显示)
3. **热度 TOP**:
   - 标题「热度 TOP」+ 完整趋势面板入口按钮(调 `openTrendPanel`)
   - 从 `trendCache` 或懒加载 `/api/<game>/trend` 取上涨前 5
   - 每行:名次、短标题(截断)、Δ 订阅(+绿/-红)、点击 `showDetail`
   - 无趋势数据时显示占位文案
4. **遗珠雷达**:
   - 标题「遗珠雷达」+ 打开完整遗珠榜按钮(`openGemsPanel`)
   - 从 `gemsCache` 或 `/gems` 取前 6
   - 每行:💎 名、收藏率 %、点击 `showDetail`
   - 无数据时占位

### 数据契约

- **不新增 API**;复用 `/trend`、`/gems`
- 与面板共用 `trendCache` / `gemsCache`;`enterGame` 重置缓存后调用 `loadIntelRail()`
- `loadTop` / `applyFilters` 后更新筛选读数
- 遗珠星标 `loadGemMarkers` 可与 intel 共用 gemsCache,避免重复请求

### 行为

- 点击情报行 → `showDetail(sid)`
- 「完整趋势」「完整遗珠」→ 打开主区对应面板(与左轨一致)
- 加载失败:栏内显示一行 dim 文案,不阻塞主列表
- `prefers-reduced-motion`:无额外动画要求

### 不变

- API、左轨、星图折叠、曲速、字体令牌、面板 id

## [S3] Out of Scope

- 新后端接口
- 可拖拽/可折叠右栏宽度
- 图表库(纯文本/条形即可)
- launcher 改版

## Tasks

- [ ] T1: CSS+DOM 右侧情报栏与 has-intel 边距 — acceptance: ≥1500px 游戏视图出现 300px 右栏;主内容不与右栏重叠;launcher/窄屏无右栏(covers: S2 布局)
- [ ] T2: 情报数据加载与交互 — acceptance: 进入游戏后右栏显示筛选读数+热度TOP+遗珠;点击行进详情;完整入口打开对应面板;与 trendCache/gemsCache 不重复拉取(covers: S2 数据; depends: T1)
- [ ] T3: 自检 — acceptance: pytest 仍绿;8099 宽屏 HTML 含 intel-rail;stats/搜索正常(covers: S2; depends: T2)
