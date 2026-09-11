---
feature: auto-update-comments
status: delivered
updated: 2026-09-11
branch: feature/auto-update-comments
commits: 4eddadf..cf3356b
---

# 自动更新感知 + 用户评论

## Report

**What was built** — `GET /api/site/version` 返回站点数据指纹(各游戏 total/translated/max_fetched + 留言数哈希);前端 60s 可见轮询,指纹变化后顶部提示条可刷新/关闭。MOD 详情页新增「访客留言」:匿名昵称+内容写入独立 `data/site/comments.db`(gitignore),GET/POST API 带蜜罐、POST 每 IP 10 分钟 5 次限流、参数化 SQL、前端 esc。

**Verification** — py_compile / node SYNTAX OK;pytest 12 passed;node UTF-8 评论入库可读回;蜜堡不入库且 total 不变;指纹随留言数变化;非法 steam_id 400;独立审查无 critical。

**Journey log**
1. POST 路径曾误写成 4 段(`/api/g/comments` 应为 3 段),导致 404。
2. 站点 translated 口径对齐 `mods.translated=1`(与 stats 一致),不用 translations 表 COUNT。
3. PowerShell `Invoke-RestMethod` 中文易乱码,应用 node fetch 验 UTF-8 评论。
4. POST 全局限流 + 评论专用限流是叠加防御,不是重复 bug。

## [S1] Problem

知识库已有云端每日 Steam 订阅同步,但**打开中的页面不会感知数据已更新**;MOD 详情页也没有访客留言交流。用户要求添加「自动更新」与「用户评论」。

默认落地(问题未问完时按推荐):  
- 自动更新 = **前端感知数据版本并提示刷新**(不重做后端 cron)  
- 评论 = **匿名写入本地 SQLite**,公开可读,带基础防刷

## [S2] Design

### A 站点版本 / 自动更新感知

- 新增 `GET /api/site/version`
  - 返回 `{ ok: true, fingerprint: string, updated_at: string, games: { stellaris: { total, translated, max_fetched }, ... }, comments: n }`
  - fingerprint = 各游戏 `total|translated|max_fetched|comments` 的稳定哈希(短 sha1/hex)
  - 只读 mods.db 与 comments.db,不改数据
- 前端:游戏视图下每 60s(页面可见时)拉一次 version;fingerprint 变化 → 顶部固定提示条「数据已更新 · 点击刷新」;点击 `location.reload()`;不可见时暂停轮询

### B 用户评论

- 存储:`data/site/comments.db`(独立 SQLite,**不进 git**;与 mods.db 分离)
  - 表 `comments(id, game_id, steam_id, name, content, ip, created_at)`
  - 索引 `(game_id, steam_id, created_at)`
- API:
  - `GET /api/<game>/comments?id=<steam_id>&n=50` → `{ comments: [...], total }` 按时间倒序,最多 50
  - `POST /api/<game>/comments` JSON body:
    `{ steam_id, name, content, website? }`
    - `website` 蜜罐字段,非空直接 200 假成功(不入库)
    - name 默认「匿名」,≤24 字;content 2–500 字;steam_id 仅数字
    - 成功 `{ ok: true, id }`;失败 `{ error }` 400/429/500
- 防刷:
  - POST 专用限流:每 IP 每 10 分钟最多 5 次
  - 全局 GET 限流不变
  - 参数化 SQL,禁止拼接
  - 内容纯文本存储与输出(前端 esc)
- 前端详情页:在「玩家评价」下增加「访客留言」区块——列表 + 表单(昵称/内容/蜜罐);提交成功后本地 prepend 一条;失败 toast

### C 部署注意

- `data/site/` 加入 `.gitignore`
- 云端若需评论持久化,后续可把 comments.db 纳入备份;**本次不做 TAT 上云**(用户未确认)

## [S3] Out of Scope

- 登录/账号体系
- 评论审核后台
- 后端 cron 重写
- 本次 TAT 云端同步

## Tasks

- [x] T1: 后端 site/version + comments 读写 API + do_POST + 蜜罐/限流 — acceptance: curl GET version 有 fingerprint;GET comments 空列表;POST 合法评论入库且可读回;蜜罐不入库;超频 429(covers: A,B)
- [x] T2: 前端版本轮询提示条 + 详情评论区 — acceptance: 手动改库后 60s 内出现刷新条;详情可发/看评论;XSS 经 esc 不执行(covers: A,B; depends: T1)
- [x] T3: 自检 — acceptance: pytest 仍绿;本地 8099 走通评论与 version;语法检查通过(covers: A,B; depends: T1,T2)
