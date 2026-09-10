---
feature: sci-ui-layout
status: delivered
updated: 2026-09-11
branch: feature/sci-fi-ui
commits: 92d63f5..81705eb
---

# 群星图鉴 · 星舰终端布局强化

## Report

**What was built** — 在方向 A 视觉基线上完成三刀布局：≥960px 固定 64px 左侧 HUD 轨（DLC/冲突/精选/遗珠/汉化/本地/趋势/清单/说明/舰桥），主内容 margin-left 64px；星图默认收起为 88px 横幅，点击展开完整交互并在 height transitionend 后同步 three.js；主列表 `#content.mod-grid` 按断点 1/2/3 栏，详情页去掉网格恢复全宽。窄屏隐藏左轨并恢复工具栏完整入口。

**Verification** — 内联脚本 node SYNTAX OK；`pytest tests -q` 12 passed；`verify_db` 健康（此前同 worktree）；本地 :8099 stats total=1020；HTML 含 side-rail / toggleGalaxy / mod-grid / narrow-only。独立复审确认 C1–C3、H1–H2 已修，Spec/Correctness/Consistency 均 PASS。

**Journey log**
1. 首版左轨 `setRailChrome` 写在 `enterGame` 之前，`data-view` 仍是 launcher → 轨永不显示；必须在原函数设完 view/GAME 之后再刷 chrome。
2. `#content.mod-grid` 会粘在详情节点上，详情被挤成半栏；`showDetail` 必须 `remove('mod-grid')`。
3. hero 高度有 0.28s CSS transition，rAF 里 resize 会读到旧高度；应用 `transitionend`（+360ms 兜底）。
4. 窄屏若只藏左轨不恢复工具按钮，会丢精选/汉化/本地/趋势/清单入口。

## [S1] Problem

视觉皮肤(方向 A)已交付,但布局仍是「垂直堆叠工具站」:首屏滚太快、工具按钮墙、单列宽卡浪费横向空间,离「星舰作战终端」的信息架构还差半口气。

## [S2] Design

在 `feature/sci-fi-ui` 基线上做三刀布局(不改 API、不改数据):

### B1 桌面左侧 HUD 导航轨

- **断点**: `min-width: 960px` 显示;更窄改为顶部横向工具条(或隐藏进现有 toolbar)。
- **位置**: `position: fixed; left: 0; top: 0; bottom: 0; width: 64px`。
- **内容**(自上而下): 游戏域徽标(`✦` 或当前 glyph) → DLC → 冲突 → 精选 → 遗珠 → 汉化 → 本地 → 趋势 → 复制清单 → 数据说明 → 底部「舰桥」返回启动页。
- **样式**: 图标 18–20px + 下方 10px 短标签;hover 出提示;激活面板时对应项高亮(`aria-current` / class `active`)。
- **主内容**: `body[data-view="game"]` 时 `main / .search-box / .game-bar / .hero / footer` 整体 `margin-left: 64px`(或包一层 `.shell`)。
- **启动页**: `data-view="launcher"` 隐藏导航轨。
- **功能**: 点击项调用既有 `open*Panel` / `copyList` / `openMetaPanel` / `showLauncher`,**不重复实现面板逻辑**。

### B2 可折叠星图横幅

- **默认**: 收起——高度约 `72–96px` 的横幅:左侧游戏名 + `heroCount` 徽章 + 「展开星图」按钮;星图 canvas 仍存在但 `opacity` 低或仅显示窄条背景。
- **展开**: 点击横幅或按钮 → `height: clamp(300px, 42vh, 440px)`,显示完整交互星图(拖拽/悬停/点击);再点收起。
- **状态**: `body.dataset.galaxy = 'open' | 'closed'`;会话内记住(可选 localStorage `galaxyOpen`)。
- **收起时** 不销毁 three.js 渲染器,仅调整 canvas 容器高度并 `renderer.setSize`;展开后 resize。
- **reduced-motion**: 高度过渡改为瞬时。

### B3 双栏紧凑 MOD 卡片墙

- **桌面** (`min-width: 900px`): `#content` 列表改 `display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px`。
- **超宽** (`min-width: 1400px`): 可 `repeat(3, 1fr)`。
- **移动**: 保持单列。
- **卡片**: 保留现有 `.mod-card` 结构;双栏下缩略图宽度约 `110–120px`,摘要 `line-clamp: 2`;徽章可换行不撑破。
- **详情/面板内嵌列表**: gems/picks 等面板内列表仍单列(避免面板内网格过挤);仅主 `#content` 用网格。

### 不变

- API、星图逻辑、URL 同步、曲速过场、启动页三卡、字体与设计令牌。
- 面板 DOM id 与 `open*` 函数签名。

## [S3] Out of Scope

- 新功能/新接口
- 彻底改成 SPA 路由
- 左侧栏可折叠宽度调节/拖拽
- 改 launcher 布局

## Tasks

- [x] T1: CSS+DOM 增加左侧 HUD 轨与 shell 边距 — acceptance: ≥960px 出现 64px 固定左轨,点击 DLC/遗珠等打开既有面板;launcher 下隐藏轨(covers: B1)
- [x] T2: 星图默认收起横幅 + 展开/收起切换与 resize — acceptance: 首屏星图为矮横幅;点击展开后可拖拽;收起再展开不崩(covers: B2; depends: T1)
- [x] T3: 主列表改双栏/三栏 grid,卡片双栏自适应 — acceptance: ≥900px 两列、≥1400px 三列、&lt;900px 单列;详情仍正常(covers: B3; depends: T1)
- [x] T4: 本地 8099 自检 — acceptance: stats/search/详情/面板/导航轨点击均可用;pytest 仍绿(covers: B1-B3; depends: T1,T2,T3)
