# 域名 + HTTPS 接入清单（Runbook）

> 2026-09-05 维护轮 15：服务器侧已完成「80 端口 nginx 反代」（**http://150.158.24.195/ 不带端口即可访问**，
> 旧 8080 入口保持兼容）；443 TLS 配置模板已预置在服务器，等域名+证书到位后 5 分钟启用。
> 服务器：腾讯云轻量 lhins-ca3ol8ju（2C/1.9G，上海）——内存实测余 1.4G，nginx 占用 ~20MB，无压力。

## 0. 已完成（服务器侧，2026-09-05）

- ✅ nginx 1.29.8（dnf 安装，systemd 自启），`/etc/nginx/conf.d/stellaris.conf`：80 → proxy 127.0.0.1:8080，gzip 开启
- ✅ `/etc/nginx/conf.d/stellaris-ssl.conf.disabled`：443 TLS 模板预置（启用步骤见 §3）
- ✅ 公网实测：80 入口 200（首页+API），8080 兼容保留
- 证书目录已建：`/etc/nginx/certs/`

## 1. 你需要做的三步（只有这三步需要人）

1. **买/确认域名**：腾讯云控制台 → 域名注册（.com/.cn 都行，首次注册常有优惠）。若已有域名，确认在腾讯云或可改 DNS 解析。
2. **ICP 备案（大陆服务器硬性要求）**：域名指向大陆服务器开 80/443 必须备案，否则腾讯云会拦截 web 访问。控制台搜索「网站备案」→ 个人备案（免费，需身份证+服务器备案服务码，轻量服务器已购满足条件）→ 通常 1-2 周下发。**备案期间不影响现在用 IP:80 访问。**
3. **DNS 解析**：备案通过后，域名解析添加 A 记录 `@` 和 `www` → `150.158.24.195`。

## 2. 证书（两条路线，推荐 A）

- **A. acme.sh 自动续期（推荐，一劳永逸）**：备案后 DNS 已生效时，在服务器执行 Let's Encrypt HTTP-01 签发，90 天有效期但 crontab 自动续：
  ```bash
  # 服务器上（GitHub 不通，走 jsDelivr 取脚本）
  curl -fsSL -m 40 -o /tmp/acme_sh.sh "https://cdn.jsdelivr.net/gh/acmesh-official/acme.sh@master/acme.sh"  # 备选: gh-proxy 前缀
  # 或本地下载 acme.sh 安装包后按 §8 打包上传
  ```
  ⚠️ 服务器对 GitHub 直连不通；若 jsDelivr 取脚本受阻，改走路线 B 或本地下载后经 GitHub Release + TAT 上传（见 HANDOFF §8 打包通道）。
- **B. 腾讯云 SSL 免费证书（最快首发）**：控制台 → SSL 证书 → 申请免费 DV 证书（TrustAsia，**90 天有效期**，DNS 验证无需改服务器）→ 签发后下载 nginx 格式 → 上传 `/etc/nginx/certs/fullchain.pem + privkey.pem`（上传通道：GitHub Release 打包 + TAT 下载，或控制台 OrcaTerm 粘贴）。**每 90 天需手动换证**——到时候提醒 AI 执行 §3 即可。

## 3. 启用 HTTPS（证书文件就位后 5 分钟，TAT 一条命令可代劳）

```bash
# 服务器上：
mv /etc/nginx/conf.d/stellaris-ssl.conf.disabled /etc/nginx/conf.d/stellaris-ssl.conf
# 编辑 stellaris-ssl.conf：server_name 改成实际域名（模板里证书路径 /etc/nginx/certs/ 已对齐）
nginx -t && systemctl reload nginx
curl -sI https://你的域名/api/stellaris/stats   # 验证
```

## 4. 域名生效后的 URL 迁移清单（AI 执行，勿遗漏）

| 位置 | 现值 | 改为 |
|---|---|---|
| `web_server_multigame.py` og:image 硬编码 | `http://150.158.24.195:8080/og_card.png` | `https://域名/og_card.png` |
| `HANDOFF` §1 云端公网 / §6 / §8 | IP:8080 | 域名（保留 IP 备注） |
| `scripts/export_workshop_snapshot.py` ONLINE_URL | IP:8080 | 域名 |
| `docs/WORKSHOP_PUBLISH.md` / `docs/PROMOTION.md` 宣传入口 | IP | 域名 |
| `.github/workflows/uptime.yml` 拨测目标 | IP:8080 | 域名（或双目标） |
| cloud_sync 模板自验 curl | IP:8080 | 127.0.0.1 或域名 |

改完必须走完整 DoD：本地 py_compile → pytest → push → CI → TAT 同步 → 公网复验 og 标签（浏览器查看源码）。

## 5. 风险与边界

- 备案前**不要**把域名解析到本服务器开 80/443（会被拦截且影响备案审核）；备案前网站继续用 IP:80 分享。
- nginx 已设 systemd 自启；重启服务器后 8080(python) 与 80(nginx) 都会自动拉起。
- 2G 内存余量充足（应用+nginx 合计 <650MB used）；若未来上 Steam 流量，优先考虑换域名 CDN 而非加配。
