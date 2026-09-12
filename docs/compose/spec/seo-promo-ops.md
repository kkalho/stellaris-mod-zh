---
feature: seo-promo-ops
status: designed
updated: 2026-09-11
branch: feature/seo-promo-ops
commits: 
---

# 传播 + 详情 SEO + 腐化例行

## Report

## [S1] Problem

站点已公网可访问,但:①详情仅 SPA,搜索引擎难收录;②PROMOTION 仍写工坊发布(已放弃);③腐化重译脚本无固定 checklist。

## [S2] Design

### S SEO 服务端详情壳

- 新增 `GET /mod/<steam_id>` 与 `GET /mod/<game>/<steam_id>`(默认 stellaris)
- 返回**服务端渲染 HTML 壳**(非完整 SPA):title/meta description/og/twitter/canonical + JSON-LD(`SoftwareApplication` 或 `CreativeWork`)含 name/description/作者/订阅数/日期;正文摘要 + 深链到 SPA `/?game=&id=`
- 不改现有 `/` SPA 与 `/api`
- 爬虫可抓;用户点进壳页有可读摘要与「打开完整档案」按钮

### P 传播最小闭环(文档)

- 重写 `docs/PROMOTION.md`:去掉工坊前置,入口改为 `http://150.158.24.195/`;给出贴吧/B站可复制短文草稿;数据真实铁律保留

### O 腐化例行 checklist

- `docs/ops/stale-retranslate-checklist.md`:每周 10 分钟流程(expand report → stale export → 译 → import → confirm → detect)

### 不变

- API 契约、限流、备份 cron

## [S3] Out of Scope

- 全站 SSR、sitemap.xml 大批页、自动发帖

## Tasks

- [ ] T1: /mod/<id> HTML 壳 + JSON-LD — acceptance: curl /mod/1121692237 含 title/json-ld/深链;未知 id 404(covers: S)
- [ ] T2: PROMOTION 更新 + checklist 文档 — acceptance: PROMOTION 无工坊前置强依赖;checklist 含可复制命令(covers: P,O)
- [ ] T3: 自检 — acceptance: pytest 绿;本地 8099 壳页与 API 正常(covers: S,P,O; depends: T1,T2)
