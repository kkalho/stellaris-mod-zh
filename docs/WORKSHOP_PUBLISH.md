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
- [ ] 体积合理（全量约 1.3MB；明显异常先查数据是否为空）
- [ ] 本地双击打开：搜索「巨构」「jugou」、版本筛选、卡片→详情、Esc 关闭
- [ ] 断网状态打开仍可用（「检查更新」静默失败属正常）

> ✅ 2026-09-06 已完成一轮浏览器端到端验证（本地 8123 静态服务 + IAB）：渲染 1020 卡、中文/拼音搜索、
> 详情五段与三个跳转、Esc、版本筛选（4.4→250）全部通过；期间修复 decompress 用 Blob.stream()（Uint8Array
> 无 .stream()）并为初始化加 try/catch 错误面板。

## 2.5 一键发布套件（2026-09-06 新增，推荐）

```bash
python scripts/make_workshop_vdf.py    # 生成 dist/workshop/workshop.vdf + publish.bat + og_card 副本
```

- **发布**：双击 `dist/workshop/publish.bat`（首次自动下载 steamcmd 到 %LOCALAPPDATA%\steamcmd）→ 输入账号密码 → 手机令牌确认。
- **首发回填**：日志里找 `published file id`，然后 `python scripts/make_workshop_vdf.py --set-id <ID>` 并把 `data/stellaris/workshop_item_id.json` 一起 git 提交——之后每次更新都会指向同一物品，订阅者自动收推送。
- vdf 描述自动从 description.txt 注入（Valve KeyValue 多行转义已处理）；上传内容走 ASCII 暂存目录 `%LOCALAPPDATA%\stellaris-snapshot-workshop`（规避中文路径风险）。
- 等价命令行：`steamcmd +login 账号 +workshop_build_item dist/workshop/workshop.vdf +quit`。

## 3. 发布路线（2026-09-06 更新：**主路线 = GitHub Actions**，本地 steamcmd 已判死）

> 本机实测：steamcdn 的 Akamai/Valve 更新主机 TLS 全部不可达（curl/steamcmd 双双失败，仅
> cloudflare.steamstatic 镜像可达），steamcmd 引导器自更新无法完成（HTTPS 断言 + 借用客户端
> DLL 均无效）——**本地 steamcmd 路线在本机网络下不可行**，已弃用；publish.bat 与 vdf 模板保留
> 作未来网络恢复时的备选。

### 主路线：GitHub Actions（仓库自带 workflow）

1. **配置凭据（只做一次，凭据不经过任何对话）**：GitHub 仓库页 → Settings → Secrets and
   variables → Actions → New repository secret，添加两条：
   - `STEAM_USERNAME`：你的 Steam 账号名
   - `STEAM_PASSWORD`：你的 Steam 密码
   （或本机 gh CLI：`gh secret set STEAM_USERNAME` / `gh secret set STEAM_PASSWORD`，回车后粘贴）
2. **发布（每次两跑）**：仓库 Actions 页 → 「工坊发布（workshop-upload）」→ Run workflow：
   - 第 1 次：验证码保持默认 `00000` → 运行会在登录步骤失败并**触发 Valve 发码**（邮箱/手机收 5 位码）
   - 第 2 次：用收到的码作为输入再运行 → 上传成功，日志里找 **published file id**
3. **回填 ID**：把 ID 告诉 AI 或自己跑 `python scripts/make_workshop_vdf.py --set-id <ID>`，
   提交 `data/stellaris/workshop_item_id.json`——之后每次发布自动指向同一物品，订阅者自动收更新。
4. 工作流细节：重建知识库（rebuild_all + verify）→ 生成快照 → vdf → docker cm2network/steamcmd
   上传；凭据全走仓库 Secrets，令牌码经 workflow 输入传入（短时一次性，不上日志明文以外的位置）。

### 订阅目录说明（不变）

物品发布后订阅者在 `Steam\steamapps\workshop\content\281990\<物品ID>\index.html` 打开离线页。

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
