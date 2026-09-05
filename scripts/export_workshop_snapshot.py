"""工坊离线快照版导出：把群星知识库打包成单文件 HTML（创意工坊「工具书」物品）

产物（dist/ 不进 git，其余进 git）：
  dist/workshop/index.html        自包含离线页：数据 gzip+base64 内嵌，浏览器 DecompressionStream 解压
  dist/workshop/description.txt   创意工坊物品描述（BBCode，发布时整段粘贴）
  data/stellaris/workshop_version.json  版本探针（进 git；离线页「检查更新」ping jsDelivr 此文件）

用法：
  python scripts/export_workshop_snapshot.py               # 全量（1020）
  python scripts/export_workshop_snapshot.py --limit 50    # 试水版（按订阅量取前 N）

发布流程见 docs/WORKSHOP_PUBLISH.md。预览图复用 web/og_card.png。
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

import games.stellaris.config.game  # noqa: F401,E402
from core.game_config import get_game  # noqa: E402

DIST_DIR = BASE_DIR / "dist" / "workshop"
VERSION_JSON = BASE_DIR / "data" / "stellaris" / "workshop_version.json"
ONLINE_URL = "http://150.158.24.195:8080/?game=stellaris"
ISSUE_URL = ("https://github.com/kkalho/stellaris-mod-zh/issues/new?title="
             "%E5%8B%98%E8%AF%AF%E6%8A%A5%E5%91%8A%EF%BC%88MOD+steam_id%3A+")
VERSION_CDN = ("https://cdn.jsdelivr.net/gh/kkalho/stellaris-mod-zh@master/"
               "data/stellaris/workshop_version.json")


def load_records(limit: int | None) -> list[dict]:
    cfg = get_game("stellaris", str(BASE_DIR))
    tag_zh = getattr(cfg, "TAG_ZH", {}) or {}
    conn = sqlite3.connect(str(BASE_DIR / "data" / "stellaris" / "mods.db"))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT m.id, m.steam_id, m.title, m.title_en, m.version, m.subscriptions, m.favorites,
                  m.tags, m.score, m.like_ratio, m.time_updated, m.status, m.optional_dlcs,
                  m.preview_url, m.pinyin_idx, m.translated
           FROM mods m WHERE m.game_id='stellaris' ORDER BY m.subscriptions DESC"""
    ).fetchall()
    tr: dict[int, dict[str, str]] = {}
    for r in conn.execute(
        "SELECT t.mod_id, t.field, t.zh_text FROM translations t "
        "JOIN mods m ON m.id=t.mod_id WHERE m.game_id='stellaris'"
    ):
        tr.setdefault(r[0], {})[r[1]] = r[2]
    conn.close()

    out = []
    for m in rows:
        t = tr.get(m["id"], {})
        if not (m["translated"] and t.get("description") and t.get("gameplay")):
            continue
        upd = ""
        if m["time_updated"]:
            upd = datetime.fromtimestamp(m["time_updated"]).strftime("%Y-%m-%d")
        tags = [tag_zh.get(x.strip(), x.strip()) for x in (m["tags"] or "").split(",") if x.strip()]
        try:
            dlc = json.loads(m["optional_dlcs"]) if m["optional_dlcs"] else []
        except ValueError:
            dlc = []
        try:
            feats = json.loads(t.get("features") or "[]") or []
        except ValueError:
            feats = []
        q = " ".join(filter(None, [m["title"] or "", m["title_en"] or "", m["pinyin_idx"] or ""])).lower()
        out.append({
            "sid": m["steam_id"], "t": m["title"] or m["title_en"], "te": m["title_en"] or "",
            "s": t.get("summary", ""), "d": t.get("description", ""), "g": t.get("gameplay", ""),
            "r": t.get("reviews", ""), "f": feats,
            "subs": m["subscriptions"] or 0, "favs": m["favorites"] or 0,
            "ver": m["version"] or "", "tg": tags, "sc": round(m["score"] or 0, 2),
            "lr": round(m["like_ratio"] or 0, 3), "upd": upd,
            "dep": 1 if (m["status"] or "") == "deprecated" else 0,
            "dlc": dlc if isinstance(dlc, list) else [], "pv": m["preview_url"] or "", "q": q,
        })
    if limit:
        out = out[:limit]
    return out


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>群星 MOD 中文图鉴 · 离线快照</title>
<style>
:root{--bg:#0b0f1a;--card:#131a2b;--line:#232c44;--fg:#dbe4f5;--dim:#8b96b5;--acc:#4fc3f7;--gold:#ffd54f}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--fg);font:15px/1.65 "Segoe UI","Microsoft YaHei",sans-serif;padding:0 16px 60px}
header{padding:22px 4px 14px;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:10px;align-items:baseline}
header h1{font-size:22px;color:var(--acc);margin-right:8px}
.meta{color:var(--dim);font-size:13px}
.bar{display:flex;flex-wrap:wrap;gap:8px;padding:14px 4px;position:sticky;top:0;background:var(--bg);z-index:5;border-bottom:1px solid var(--line)}
input,select,button{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:8px 10px;font-size:14px}
input[type=search]{flex:1;min-width:220px}
button{cursor:pointer}button:hover{border-color:var(--acc)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;padding:16px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;cursor:pointer;transition:border-color .15s}
.card:hover{border-color:var(--acc)}
.card img{width:100%;height:150px;object-fit:cover;border-radius:6px;background:#0e1424}
.card h3{font-size:15px;margin:8px 0 2px}.card .en{color:var(--dim);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.chip{font-size:12px;color:var(--dim);border:1px solid var(--line);border-radius:10px;padding:1px 8px}
.row{display:flex;justify-content:space-between;align-items:center;margin-top:8px;font-size:12.5px;color:var(--dim)}
.b{border-radius:4px;padding:1px 7px;font-size:12px}
.b.g{background:#12351f;color:#7ddb9a}.b.o{background:#3a2c12;color:#e8c268}.b.r{background:#3a1519;color:#ef8b96}
.overlay{position:fixed;inset:0;background:rgba(4,7,15,.72);display:none;overflow:auto;padding:30px 12px;z-index:9}
.sheet{max-width:820px;margin:0 auto;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:26px}
.sheet h2{color:var(--acc);font-size:20px}.sheet .en{color:var(--dim);margin-bottom:12px}
.sheet section{margin-top:16px}.sheet h4{color:var(--gold);font-size:14px;margin-bottom:4px}
.sheet p{white-space:pre-wrap}
.acts{display:flex;gap:10px;flex-wrap:wrap;margin-top:20px}
.acts a{color:var(--acc);text-decoration:none;border:1px solid var(--line);border-radius:6px;padding:7px 12px;font-size:13px}
.note{color:var(--dim);font-size:12.5px;padding:10px 4px}
#upd{display:none;margin:10px 4px 0;border:1px solid #3a2c12;background:#241d0d;color:#e8c268;border-radius:8px;padding:9px 12px;font-size:13.5px}
#err{max-width:640px;margin:60px auto;text-align:center;color:var(--dim)}
</style>
</head>
<body>
<header>
  <h1>🛰 群星 MOD 中文图鉴</h1>
  <span class="meta" id="meta"></span>
</header>
<div id="upd"></div>
<div class="bar">
  <input id="q" type="search" placeholder="搜索：中文 / 英文 / 拼音（如 jugou）  按 / 聚焦" autofocus>
  <select id="tag"><option value="">全部标签</option></select>
  <select id="ver"><option value="">全部版本</option></select>
  <select id="sort">
    <option value="subs">按订阅量</option>
    <option value="upd">按最近更新</option>
    <option value="name">按名称</option>
  </select>
</div>
<div class="note">📌 本页为<b>离线快照</b>（非游戏内 MOD）：数据抓取自 Steam 公开接口，中文说明为 AI 翻译整理，仅供参考；以工坊原页为准。依赖 DLC 均为描述提及级「可选」。</div>
<div id="err" style="display:none"><p>⚠ 当前浏览器不支持 DecompressionStream，无法解压数据。<br>请使用较新的 Chrome / Edge / Firefox，或访问在线版：<a style="color:var(--acc)" href="__ONLINE__">在线版入口</a></p></div>
<div class="grid" id="grid"></div>
<div class="overlay" id="ov"><div class="sheet" id="sheet"></div></div>
<footer class="note">数据说明：来源 Steam 官方 API/创意工坊公开数据 · AI 翻译由本项目整理，点击详情内「报告勘误」可到 GitHub 反馈 · 在线版（功能更全：DLC 检测/冲突检测/星图）：<a style="color:var(--acc)" href="__ONLINE__">__ONLINE__</a></footer>
<script>
const DATA_B64="__DATA__";
const EXPORTED_AT="__DATE__";
const VERSION_CDN="__CDN__";
const ONLINE_URL="__ONLINE__";
const ISSUE_URL="__ISSUE__";
let MODS=[];
const $=s=>document.querySelector(s);
const esc=s=>(s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmt=n=>n>=10000?(n/10000).toFixed(1)+"万":String(n||0);
function verBadge(v){const m=(v||"").match(/(\d+\.\d+)/);if(!m)return "";const cur=m[1].startsWith("4.");return `<span class="b ${cur?"g":"o"}">${esc(v||"未标注")}</span>`}
function card(m){const tags=m.tg.slice(0,3).map(x=>`<span class="chip">${esc(x)}</span>`).join("");
return `<div class="card" data-sid="${m.sid}">${m.pv?`<img loading="lazy" src="${esc(m.pv)}" onerror="this.style.display='none'">`:""}
<h3>${esc(m.t)}</h3><div class="en">${esc(m.te)}</div>
<div class="chips">${m.dep?'<span class="b r">⚠ 已废弃</span>':""}${verBadge(m.ver)}${tags}</div>
<div class="row"><span>👥 ${fmt(m.subs)} · ⭐ ${fmt(m.favs)}</span><span>${m.upd?"更新 "+m.upd:""}</span></div></div>`}
function filtered(){const q=$("#q").value.trim().toLowerCase(),tag=$("#tag").value,ver=$("#ver").value,sort=$("#sort").value;
let a=MODS.filter(m=>(!q||m.q.includes(q))&&(!tag||m.tg.includes(tag))&&(!ver||(m.ver||"").includes(ver)));
if(sort==="subs")a.sort((x,y)=>y.subs-x.subs);else if(sort==="upd")a.sort((x,y)=>(y.upd||"").localeCompare(x.upd||""));else a.sort((x,y)=>x.t.localeCompare(y.t,"zh"));return a}
function render(){const a=filtered();$("#grid").innerHTML=a.map(card).join("");
$("#meta").textContent=`快照 ${EXPORTED_AT} · ${MODS.length} 个 MOD · 当前显示 ${a.length} 个`}
function detail(m){const dl=m.dlc.length?`<section><h4>涉及 DLC（可选）</h4><p>${esc(m.dlc.join("、"))}</p></section>`:"";
$("#sheet").innerHTML=`<h2>${esc(m.t)}</h2><div class="en">${esc(m.te)}</div>
<div class="chips">${m.dep?'<span class="b r">⚠ 已废弃</span>':""}${verBadge(m.ver)}${m.tg.map(x=>`<span class="chip">${esc(x)}</span>`).join("")}</div>
<p class="row" style="margin-top:10px">👥 订阅 ${fmt(m.subs)} · ⭐ 收藏 ${fmt(m.favs)} · 评分 ${m.sc} · 好评率 ${(m.lr*100).toFixed(0)}% · 数据更新 ${m.upd||"-"}</p>
<section><h4>简介</h4><p>${esc(m.s)}</p></section>
<section><h4>详细介绍</h4><p>${esc(m.d)}</p></section>
<section><h4>具体玩法</h4><p>${esc(m.g)}</p></section>
<section><h4>玩家评价（作者自述整理）</h4><p>${esc(m.r)}</p></section>
${m.f.length?`<section><h4>特色</h4><div class="chips">${m.f.map(x=>`<span class="chip">${esc(x)}</span>`).join("")}</div></section>`:""}
${dl}<div class="acts">
<a target="_blank" rel="noopener" href="https://steamcommunity.com/sharedfiles/filedetails/?id=${m.sid}">↗ Steam 工坊页</a>
<a target="_blank" rel="noopener" href="${ONLINE_URL}">🌐 在线版（DLC/冲突检测）</a>
<a target="_blank" rel="noopener" href="${ISSUE_URL}${m.sid})">报告勘误 ↗</a></div>`;
$("#ov").style.display="block";document.body.style.overflow="hidden"}
$("#grid").addEventListener("click",e=>{const c=e.target.closest(".card");if(!c)return;
detail(MODS.find(m=>m.sid===c.dataset.sid))});
$("#ov").addEventListener("click",e=>{if(e.target.id==="ov"){$("#ov").style.display="none";document.body.style.overflow=""}});
$("#q").addEventListener("input",render);$("#tag").addEventListener("change",render);
$("#ver").addEventListener("change",render);$("#sort").addEventListener("change",render);
document.addEventListener("keydown",e=>{if(e.key==="/"&&document.activeElement!==$("#q")){e.preventDefault();$("#q").focus()}
if(e.key==="Escape"){$("#ov").style.display="none";document.body.style.overflow=""}});
function initFilters(){const tags=[...new Set(MODS.flatMap(m=>m.tg))].sort();
const vers=[...new Set(MODS.map(m=>(m.ver.match(/(\d+\.\d+)/)||[])[1]).filter(Boolean))].sort().reverse();
$("#tag").innerHTML='<option value="">全部标签</option>'+tags.map(t=>`<option>${esc(t)}</option>`).join("");
$("#ver").innerHTML='<option value="">全部版本</option>'+vers.map(v=>`<option>${v}</option>`).join("")}
async function decompress(b64){const bytes=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));
const ds=new DecompressionStream("gzip");const stream=new Response(bytes.stream().pipeThrough(ds));
return stream.json()}
(async()=>{if(!("DecompressionStream" in window)){$("#err").style.display="block";return}
MODS=await decompress(DATA_B64);initFilters();render();
try{const r=await fetch(VERSION_CDN,{cache:"no-store"});const v=await r.json();
if(v.exported_at&&v.exported_at!==EXPORTED_AT){const u=$("#upd");u.style.display="block";
u.innerHTML=`🚀 已有新数据快照（${esc(v.exported_at)}），本页为 ${EXPORTED_AT}。更新方法见工坊页面说明，或先看 <a style="color:var(--acc)" href="${ONLINE_URL}">在线版</a>。`}}catch(e){/* 离线环境无网络，静默 */}})();
</script>
</body>
</html>
"""


def build_description(mod_count: int, exported: str) -> str:
    return f"""[b]群星 MOD 中文图鉴 —— 离线查询手册（Steam 创意工坊版）[/b]

[list]
[*]📚 收录创意工坊 Top {mod_count} 群星 MOD：中英文/拼音搜索、版本筛选、标签筛选、订阅排序
[*]📖 每个 MOD 附中文简介、详细介绍、具体玩法、玩家评价整理、特色标签
[*]🏷 版本兼容徽章、废弃标注、涉及 DLC（描述提及级）、数据更新日期
[*]🌐 配套在线版功能更全：DLC 缺失检测、清单冲突检测、银河星图、遗珠榜（见页面内链接）
[/list]

[b]⚠ 这不是游戏内 MOD[/b]：订阅后不会改变游戏内容。它是一份[b]离线数据快照（单个 HTML 文件）[/b]，双击用浏览器打开即可查询。

[b]使用方法[/b]：订阅本物品后，文件位于
Steam\\steamapps\\workshop\\content\\281990\\<本物品ID>\\index.html
（Steam 客户端中：库 → 群星 → 创意工坊 → 本物品 → 打开文件夹）。双击 index.html 即可，无需联网。

[b]数据说明[/b]：数据抓取自 Steam 官方 API 与创意工坊公开页面（快照日期 {exported}）；中文说明为 AI 翻译整理并经质量门禁校验，仅供参考，以工坊原页为准；发现错漏欢迎在工坊评论区或 GitHub 仓库（kkalho/stellaris-mod-zh）反馈勘误。

[b]更新机制[/b]：本物品定期重新构建上传（数据快照刷新），Steam 会自动向订阅者推送更新；页面顶部也可核对数据日期并与在线版对照。"""


def main():
    ap = argparse.ArgumentParser(description="导出创意工坊离线快照版（单 HTML + 描述 + 版本探针）")
    ap.add_argument("--limit", type=int, default=None, help="试水版：按订阅量取前 N 个")
    args = ap.parse_args()

    records = load_records(args.limit)
    exported = date.today().isoformat()
    payload = json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    b64 = base64.b64encode(gzip.compress(payload, mtime=0)).decode("ascii")

    html = (HTML_TEMPLATE
            .replace("__DATA__", b64)
            .replace("__DATE__", exported)
            .replace("__CDN__", VERSION_CDN)
            .replace("__ONLINE__", ONLINE_URL)
            .replace("__ISSUE__", ISSUE_URL))
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    html_path = DIST_DIR / "index.html"
    html_path.write_bytes(html.encode("utf-8"))

    desc_path = DIST_DIR / "description.txt"
    desc_path.write_bytes(build_description(len(records), exported).encode("utf-8"))

    version = {
        "game": "stellaris",
        "exported_at": exported,
        "mod_count": len(records),
        "html_kb": round(html_path.stat().st_size / 1024, 1),
        "note": "工坊离线快照版版本探针：离线页「检查更新」对比 exported_at",
    }
    VERSION_JSON.write_bytes(json.dumps(version, ensure_ascii=False, indent=1).encode("utf-8"))

    print(f"MOD 记录      : {len(records)}")
    print(f"数据明文      : {len(payload)/1024:.0f} KB")
    print(f"index.html    : {html_path.stat().st_size/1024:.0f} KB -> {html_path}")
    print(f"description   : {desc_path}")
    print(f"version.json  : {VERSION_JSON} (exported_at={exported})")


if __name__ == "__main__":
    main()
