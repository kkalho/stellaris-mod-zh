# Steam 创意工坊发布套件（群星离线快照版）

> 对应 ROADMAP「Steam 发表」三阶段第①步：**创意工坊先行**（零成本、零审核，物品=离线 HTML 工具书，非游戏内 MOD）。
> 构建工具：`scripts/export_workshop_snapshot.py`。更新日期：2026-09-05。

## 1. 物品形态与合规底线

- **物品内容**：单个自包含 `index.html`（数据 gzip+base64 内嵌，浏览器解压渲染），订阅者在订阅目录双击打开。
- **合规四条**（每次发布前自查）：
  1. 数据全部来自 Steam 公开 API / 创意工坊公开页面（本站自抓），不打包任何游戏本体素材、不打包他人 MOD 内容；
  2. AI 翻译在物品描述与页面内**显著标注**（模板已含）；
  3. 描述第一行即声明「这不是游戏内 MOD，是离线查询手册」（模板已含）；
  4. 页面内保留 Steam 原页跳转与 GitHub 勘误入口（模板已含）。

## 2. 构建（每次更新都要重跑）

```bash
python scripts/export_workshop_snapshot.py            # 全量
python scripts/export_workshop_snapshot.py --limit 50 # 试水版（首次发布建议先试水）
```

产物：
| 文件 | 去向 |
|---|---|
| `dist/workshop/index.html` | steamcmd contentfolder（不进 git，已 gitignore） |
| `dist/workshop/description.txt` | 发布时粘贴进物品描述 / vdf 的 description 字段 |
| `data/stellaris/workshop_version.json` | **进 git**：离线页「检查更新」经 jsDelivr 读取对比 `exported_at` |

生成后自检：
- [ ] 体积合理（全量约 0.7-1.2MB；明显异常先查数据是否为空）
- [ ] 本地双击打开：搜索「巨构」「jugou」、版本筛选、卡片→详情、Esc 关闭
- [ ] 断网状态打开仍可用（「检查更新」静默失败属正常）

## 3. 首次发布（steamcmd）

1. 安装 steamcmd（Windows: 解压版即可；不要装在本项目目录）。
2. 写 `steamcmd_workshop.vdf`（UTF-8，无 BOM）：

```
"workshopitem"
{
  "appid"                "281990"
  "publishedfileid"      ""
  "contentfolder"        "C:/Users/wangf/Documents/新建文件夹/stellaris-mod-zh/dist/workshop"
  "previewfile"          "C:/Users/wangf/Documents/新建文件夹/stellaris-mod-zh/web/og_card.png"
  "visibility"           "0"
  "title"                "群星 MOD 中文图鉴（离线查询手册 · 持续更新）"
  "description"          "<粘贴 dist/workshop/description.txt 全文，内部引号需转义为 \">"
  "changenote"           "首个公开版本：Top 1020 中文数据快照"
}
```

3. 上传（会触发 Steam 手机令牌确认）：

```bash
steamcmd +login <Steam账号> +workshop_build_item <vdf路径> +quit
```

4. **记下日志中的 publishedfileid**，回填进 vdf（以后每次更新必须带），并在本文件登记物品 ID。
5. 订阅自己的物品 → 到 `Steam/steamapps/workshop/content/281990/<物品ID>/` 双击 index.html 完成端到端验证。

## 4. 日常更新（订阅者自动收推送）

```bash
python scripts/export_workshop_snapshot.py && git add data/stellaris/workshop_version.json
git commit -m "workshop: 数据快照 <日期>" && git push   # version.json 上 jsDelivr，离线页「检查更新」才准
steamcmd +login <账号> +workshop_build_item <vdf> +quit   # vdf 里 publishedfileid 已填、changenote 换成新内容
```

## 5. 可选：CI 自动上传

GitHub Marketplace 的 **steam-workshop-upload** Action 支持 Steam Guard 2FA（refresh token 方式），可把第 4 节做成 push tag 触发的 workflow。接入前把 token 放仓库 Secret，且先用试水版演练。本项目已有 `uptime.yml`，同类写法。

## 6. 发布检查清单（DoD）

- [ ] validate 门禁绿、verify_db 健康（数据本身先过关）
- [ ] 快照 `--limit 50` 本地人工验证 → 全量重跑 → 体积/回读校验
- [ ] description.txt 与实际 mod_count、日期一致
- [ ] steamcmd 上传成功 + 工坊页面可见
- [ ] 订阅路径打开 index.html 端到端验证
- [ ] 「检查更新」按钮：改动 version.json 并推送后 10 分钟（jsDelivr 缓存）应提示新快照
- [ ] 本文件登记物品 ID 与发布历史

## 7. 发布历史

| 日期 | 物品ID | 内容 |
|---|---|---|
| （待首次发布后登记） | | |
