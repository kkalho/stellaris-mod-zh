---
feature: sci-ui-density
status: delivered
updated: 2026-09-11
branch: feature/sci-fi-ui
commits: f44871d..88ae463
---

# 群星图鉴 · 主区拉满与密度收紧

## Report

**What was built** — 游戏视图下主区/搜索/游戏条放开 `max-width`（保持 block `width:auto`，由左右轨 margin 收进通道，避免 `width:100%` 溢出）；场景卡/统计/工具条/列表间距收紧；场景卡·统计·工具条·列表卡加克制 L 角标（内缩避开 clip-path）；左轨 logo 慢呼吸，`prefers-reduced-motion` 关闭。

**Verification** — node SYNTAX OK；pytest 12 passed；线上 density 规则无 `width:100%`；`max-width:none` 生效。

**Journey log**
1. `game-shell` 是并列兄弟节点各自吃 rail margin，绝不能写 `width:100%`（会叠在 margin 外侧溢出 64+300px）。
2. L 角标画在 `inset:0` 会被 `--cut` 切角裁掉，需 `inset:3–4px`。
3. 用户反馈「空隙大/别扭」根因是主列 `max-width:1100` 居中，不是情报栏本身。

## [S1] Problem

用户截图反馈:左右轨之间空隙过大、元素偏稀、整体观感别扭。根因是主区/搜索/游戏条仍有 `max-width:1100~1280` 且居中,在 ≥1500px 双栏布局下两侧大片留白。

## [S2] Design

已拍板:**主区拉满+提密度** + **克制科技感特效**(不过度闪)。

### D1 宽度拉满

- 游戏视图下 `.search-box`、`main`、`.game-bar`、`.stats`、`.scene-cards` 去掉窄 `max-width` 居中,改为 `max-width: none; width: 100%`,由 `has-rail`/`has-intel` 的 margin 撑开可用区
- 桌面内边距:左右 `20–24px`,顶部收紧
- 情报栏/左轨布局保持不变

### D2 密度收紧

- `main` 顶部 padding 减小;场景卡与统计、标签、工具条、列表之间 `gap/margin` 收紧约 20–30%
- 场景卡改为 4 列均分(已有 grid),卡片 padding 略减
- 统计条与场景卡同行感:统计块更矮、数字略小
- 列表标题与首卡间距减小;`mod-grid` gap 8px

### D3 克制特效

- 主面板/卡片/场景卡:**四角 L 形角标**(伪元素,主色低透明度)
- 状态点(左轨 logo、统计若有):慢速呼吸 opacity
- 搜索框已有 focus 脉冲,保留;卡片 hover 已有辉光,略增强边框亮度即可
- 列表标题 `//` 前保留;`footer` 系统条保留
- **不做**:全屏粒子、边框流光跑马、卡片入场波次
- `prefers-reduced-motion`:关闭呼吸与新增动画

### 不变

- API、左轨、右情报栏逻辑、星图、曲速、字体

## [S3] Out of Scope

- 新功能模块
- 更炫特效包
- 改 launcher

## Tasks

- [x] T1: 拉满主区宽度并收紧间距 — acceptance: ≥1500px 双栏下主内容贴满左右轨之间的可用宽,无大片居中留白;场景卡/统计/列表间距更紧(covers: D1,D2)
- [x] T2: 克制角标与呼吸态 — acceptance: 主要卡片有四角角标;logo/状态点慢呼吸;reduced-motion 无动画(covers: D3; depends: T1)
- [x] T3: 自检 — acceptance: pytest 绿;8099 无语法错误;布局标记仍在(covers: D1-D3; depends: T1,T2)
