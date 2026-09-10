---
feature: sci-fi-ui
status: delivered
updated: 2026-09-11
branch: feature/sci-fi-ui
commits: b3675b5..2b16fda
---

# 群星图鉴 · 星舰终端 UI 重写

## Report

**What was built** — 前端 `web/index_multigame.html` 彻底重写为单一「星舰作战终端」设计系统：深空底色、冰青主色、切角数据卡、终端搜索前缀 `❯`、Orbitron/Rajdhani 自托管字体（`web/fonts/` + 服务端白名单路由）。曲速全屏过场增强为目标星域文案 + 点击跳过 + `prefers-reduced-motion` 短过场；`switchGame` 真正触发曲速（基线里 `opts.warp` 从未被 `enterGame` 消费）。API 契约与全部功能（星图/筛选/详情/面板/URL/快捷键）等价保留。

**Verification** — `verify_db.py` exit 0（1020/1020 六字段）；`pytest tests -q` 12 passed；本地 :8099 stats total=1020；`/fonts/*.woff2` 200 + `font/woff2`；路径穿越 404；搜索「巨构」与详情六字段非空；独立审查 Spec/Correctness/Consistency 均 PASS、无 critical。

**Journey log**
1. 基线虽已有「深空舰桥皮肤 v2」覆盖层，但是双层 CSS（SaaS 底 + 覆盖）——重写收敛为单一令牌。
2. 基线 `switchGame` 传了 `{warp:true}` 但 `enterGame` 从不读它，切游戏曲速实际是死的；本次修好。
3. worktree 默认无 `data/`（gitignore），自检需从主仓库 robocopy 数据后再起 8099。
4. 审查指出布局未做左侧折叠栏（spec 草图有写）；验收按 HUD 视觉达标，视为可接受偏差。

## [S1] Problem

现网 `web/index_multigame.html` 是深色圆角卡片站(微软雅黑 + 大 border-radius + SaaS 工具栏),虽有 three.js 星图,但整体不像科幻/科技产品。用户已放弃 Steam 工坊发布、主站聚焦群星,希望界面达到「星舰作战终端」气质,并加入曲速全屏过场。

## [S2] Design

### 视觉方向(已拍板:方向 A 星舰作战终端)

| Token | 值 |
|---|---|
| 背景 | `#05080f` 深空黑蓝 |
| 主色 | `#5ce1e6` 冰青 |
| 辅色 | `#3d7ea6` 钢青(描边/次级) |
| 强调 | `#f0c160` 警示金(遗珠/精选) |
| 危险 | `#ff4d6a` |
| 成功 | `#4ade80` |
| 危险面板底 | `rgba(8,16,28,.88)` |
| 描边 | `1px solid rgba(92,225,230,.18)` |
| 圆角 | 0 或 2px(禁止 8-12px 大圆角) |

- **字体**:英文/数字 `Orbitron`(标题/数字)+ `Rajdhani`(次级英文),中文 `"PingFang SC","Microsoft YaHei",sans-serif`。woff2 **本地自托管**,放 `web/fonts/`。
- **形状**:卡片直角 + `clip-path` 四角切角(约 10px);面板顶栏像舰船状态条(左侧 `//` 或 `[SYS]` 前缀 + 标题 + 右侧状态点)。
- **背景层**:固定星点(保留)+ 极淡 CSS 网格 + 顶部/底部扫描线(低透明度,`prefers-reduced-motion` 时关闭)。
- **搜索框**:终端样式,前缀 `❯` 或 `>_`,聚焦时边框冰青脉冲。
- **MOD 卡片**:数据面板感——顶栏(短 ID/状态)+ 主体(标题/摘要)+ 底栏(订阅/收藏数字,Rajdhani/Orbitron 等宽感)。
- **主题变量**:保留 `data-theme` 的 ck3 金 / hoi4 钢灰 / bridge 紫,只替换 `--ac` 等色板 token,形状语言全局统一。

### 布局(彻底重写 DOM/CSS,功能等价迁移)

```
[启动页 launcher]
  全屏星域之门 + 三张切角门卡 + 曲速过场 → 进入游戏库

[游戏库]
  左侧窄栏(可折叠):导航图标/入口(搜索/精选/遗珠/冲突/DLC/汉化/趋势/数据说明)
  主区:
    顶栏:游戏名 + 版本下拉 + 统计条(total/translated,等宽数字)
    星图 hero(保留 three.js 银河,失败降级 2D)
    终端搜索条
    场景卡(新手/美化/剧情/玩法)
    标签条 + 筛选工具条(直角 select)
    MOD 卡片墙(桌面 ≥2 列,移动 1 列)
    分页
  详情:从右侧滑入全高面板(或全屏替换),保留返回
  各功能面板:模态/抽屉统一「数据舱」样式
```

窄屏(<900px):侧栏收成顶栏图标行,卡片单列,不破坏现有交互。

### 曲速全屏过场(仅此项动效已拍板)

- **触发**:`switchGame()` 换游戏、launcher 进入游戏、详情内「切换游戏」——凡跨游戏域切换必过场。
- **表现**:全屏覆盖层 `#warpOverlay`(原 `#warp` 增强):星隧道拉伸 + 冰青/主题色闪白 + 短促音效可选(默认静音) + 文案「曲速引擎启动 / 进入 <游戏名>」。
- **时长**:0.7–1.2s,可点击跳过;`prefers-reduced-motion: reduce` 时直接淡入淡出 150ms。
- **实现**:Canvas 2D 或沿用现有 warp 逻辑强化;不依赖 three.js。
- **不做**(用户未选):进场开机自检打字机、视图微过场、卡片入场波次。

### 技术契约

- **入口仍是单文件** `web/index_multigame.html`(服务端已按此路径服务);字体除外链。
- **字体文件**:`web/fonts/orbitron-latin-700.woff2`、`web/fonts/rajdhani-latin-500.woff2`、`web/fonts/rajdhani-latin-600.woff2`(或合并为最少文件集,单文件 <150KB)。
- **服务端**:`web_server_multigame.py` 白名单静态路由增加 `/fonts/<name>.woff2`(固定文件名,防路径穿越),`Content-Type: font/woff2`。
- **API 契约零变更**:全部沿用 `/api/<game>/...` 现有 query 参数与响应;前端函数可重写但行为等价。
- **必须保留的功能清单**:
  - 游戏切换(stellaris/ck3/hoi4)+ 主题色
  - 星图 hero(悬停/点击/遗珠金标/2D 降级/`window.GALAXY_INFO`)
  - 搜索/标签/版本/排序/分页 + URL 状态同步
  - 场景卡、新手精选 picks、遗珠 gems
  - 详情六字段 + 废弃/版本风险/活跃徽章/勘误链接/数据更新
  - DLC 缺失、汉化包、本地 MOD、趋势涨跌、冲突检测、复制清单
  - 数据说明面板、反馈链接、键盘 `/` 与 `Esc`
  - og/favicon 元数据不变
- **降级**:无 WebGL、无 three.js CDN 时功能完整可用。
- **无障碍/减动效**:`prefers-reduced-motion` 关闭装饰动画与曲速长过场。

### 部署路径

- 仅改 `web/` 与 `web_server_multigame.py` 静态字体路由;不改数据/API 业务逻辑。
- 本地预览:`python web_server_multigame.py 8099`;公网同步时按 §8 轻量同步改动文件 + 重启。

## [S3] Out of Scope

- Steam 工坊发布 / workshop-upload CI
- 后端 API 语义变更、数据库、翻译流水线
- EU4/VIC3 扩展、HOI4 抓取
- 进场开机打字机自检、卡片雷达波入场(用户未选)
- 域名/HTTPS
- 音效资源包(曲速默认静音)

## Tasks

- [x] T1: 下载并放置 Orbitron/Rajdhani woff2 到 `web/fonts/` — acceptance: 字体文件存在且 <300KB 合计,`@font-face` 路径指向 `/fonts/...`(covers: S2 字体)
- [x] T2: 服务端增加 fonts 白名单路由 — acceptance: `GET /fonts/orbitron-*.woff2` 返回 200 与正确 Content-Type,非法路径 404(covers: S2 技术契约; depends: T1)
- [x] T3: 重写 `index_multigame.html` 设计系统与布局(DOM+CSS+主题 token+切角卡片+侧栏+终端搜索) — acceptance: 本地 8099 打开后视觉为直角冰青 HUD,无 10px+ 大圆角主卡片;窄屏单列可用(covers: S2 视觉/布局)
- [x] T4: 迁移全部前端功能 JS(API/筛选/详情/面板/星图/URL/快捷键) — acceptance: 功能清单逐项可操作;`GALAXY_INFO` 钩子仍在;无 three.js 时列表与搜索可用(covers: S2 功能契约; depends: T3)
- [x] T5: 曲速全屏过场接入切换游戏路径 — acceptance: 切换游戏出现 0.7–1.2s 曲速覆盖层并进入目标游戏;reduced-motion 下变为短淡入(covers: S2 过场; depends: T4)
- [x] T6: 端到端自检 — acceptance: 本地服务加载 stats total/translated 正常;搜索「巨构」有结果;打开详情六字段非空;pytest 相关无新增失败(covers: S2; depends: T4,T5)
