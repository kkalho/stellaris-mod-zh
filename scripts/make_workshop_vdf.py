"""生成 Steam 创意工坊一键发布套件（在 export_workshop_snapshot.py 之后运行）

产物（dist/ 不进 git）：
  dist/workshop/workshop.vdf   steamcmd workshop_build_item 配置（描述从 description.txt 注入）
  dist/workshop/publish.bat    Windows 一键发布：备料 → 装 steamcmd（如缺）→ 上传（提示 2FA）
  dist/workshop/og_card.png    预览图副本（与 vdf/bat 同目录，自包含）

物品 ID 持久化：首次发布后把日志里的 published file id 写入
data/stellaris/workshop_item_id.json（进 git），之后本脚本自动带上，更新发布不再新建物品。

用法：
  python scripts/make_workshop_vdf.py                 # 生成 vdf + bat
  python scripts/make_workshop_vdf.py --set-id 12345  # 首发后回填物品 ID
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DIST = BASE_DIR / "dist" / "workshop"
ID_FILE = BASE_DIR / "data" / "stellaris" / "workshop_item_id.json"
STAGING = Path((Path.home() / "AppData" / "Local") if sys.platform == "win32" else Path.home()) \
    / "stellaris-snapshot-workshop"

TITLE = "群星 MOD 中文图鉴（离线查询手册 · 持续更新）"


def vdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def load_item_id() -> str:
    if ID_FILE.exists():
        try:
            return str(json.loads(ID_FILE.read_text(encoding="utf-8")).get("publishedfileid", ""))
        except (ValueError, OSError):
            return ""
    return ""


def build_vdf(mod_count: int) -> str:
    description = (DIST / "description.txt").read_text(encoding="utf-8")
    exported = date.today().isoformat()
    item_id = load_item_id()
    return f'''"workshopitem"
{{
    "appid"             "281990"
    "publishedfileid"   "{vdf_escape(item_id)}"
    "contentfolder"     "{vdf_escape(str(STAGING).replace(chr(92), '/'))}"
    "previewfile"       "{vdf_escape(str((STAGING / 'og_card.png')).replace(chr(92), '/'))}"
    "visibility"        "0"
    "title"             "{vdf_escape(TITLE)}"
    "description"       "{vdf_escape(description)}"
    "changenote"        "数据快照 {exported}：Top {mod_count} 中文数据"
}}
'''


BAT_TEMPLATE = r"""@echo off
chcp 65001 >nul
setlocal
set STAGING=%LOCALAPPDATA%\stellaris-snapshot-workshop
set STEAMCMD=%LOCALAPPDATA%\steamcmd\steamcmd.exe
echo [1/3] 准备上传内容...
if not exist "%STAGING%" mkdir "%STAGING%"
copy /Y "%~dp0index.html" "%STAGING%\" >nul
copy /Y "%~dp0og_card.png" "%STAGING%\" >nul
echo [2/3] 检查 steamcmd...
if exist "%STEAMCMD%" goto run
echo     未找到 steamcmd，从官方源下载安装...
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip' -OutFile \"$env:TEMP\steamcmd.zip\""
powershell -NoProfile -Command "Expand-Archive -Force \"$env:TEMP\steamcmd.zip\" \"$env:LOCALAPPDATA\steamcmd\""
if not exist "%STEAMCMD%" (
    echo [x] steamcmd 下载失败。请手动下载 https://developer.valvesoftware.com/wiki/SteamCMD
    echo     并解压 steamcmd.exe 到 %LOCALAPPDATA%\steamcmd\ 后重试。
    pause
    exit /b 1
)
:run
echo [3/3] 上传创意工坊物品（首次运行需输入 Steam 账号密码，并完成手机令牌/邮件确认）...
echo     用法：双击直接运行（会提示输入账号）；或命令行 publish.bat 你的Steam账号名
"%STEAMCMD%" +login %* +workshop_build_item "%~dp0workshop.vdf" +quit
echo.
echo 完成。首次发布请在输出中找到 published file id，回填给 AI 持久化，
echo 之后每次更新只需重新生成快照后再次运行本脚本，订阅者自动收更新。
pause
"""


def main():
    ap = argparse.ArgumentParser(description="生成工坊一键发布套件（vdf + bat）")
    ap.add_argument("--set-id", type=str, default=None, help="回填 publishedfileid（首发后运行一次）")
    args = ap.parse_args()

    if args.set_id:
        ID_FILE.write_text(json.dumps({"publishedfileid": args.set_id}, ensure_ascii=False) + "\n",
                           encoding="utf-8")
        print(f"publishedfileid={args.set_id} 已写入 {ID_FILE}（记得 git 提交该文件）")
        return

    if not (DIST / "index.html").exists():
        raise SystemExit("dist/workshop/index.html 不存在——先跑 scripts/export_workshop_snapshot.py")

    html_kb = round((DIST / "index.html").stat().st_size / 1024)
    mod_count = json.loads((BASE_DIR / "data" / "stellaris" / "workshop_version.json")
                           .read_text(encoding="utf-8"))["mod_count"]

    shutil.copyfile(BASE_DIR / "web" / "og_card.png", DIST / "og_card.png")
    (DIST / "workshop.vdf").write_text(build_vdf(mod_count), encoding="utf-8")
    (DIST / "publish.bat").write_text(BAT_TEMPLATE, encoding="utf-8")

    item_id = load_item_id()
    print(f"vdf          : {DIST / 'workshop.vdf'} (物品ID: {item_id or '空=首次发布会新建物品'})")
    print(f"publish.bat  : {DIST / 'publish.bat'}（双击运行，按提示登录+2FA）")
    print(f"暂存目录     : {STAGING}")
    print(f"快照         : index.html {html_kb}KB / {mod_count} MOD")
    if not item_id:
        print("⚠ 首次发布：运行后把输出里的 published file id 交给 AI，或自己跑 "
              "python scripts/make_workshop_vdf.py --set-id <ID>")


if __name__ == "__main__":
    main()
