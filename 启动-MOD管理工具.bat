@echo off
chcp 65001 >nul
title Paradox MOD 管理工具
echo ============================================
echo   Paradox MOD 管理工具 - 一键启动
echo   支持: 群星 / 十字军之王3 / 钢铁雄心4
echo ============================================
echo.

cd /d "%~dp0"

REM 查找 Python（优先用项目 venv，其次系统 Python）
set PYTHON=
if exist ".venv\Scripts\python.exe" (
  set PYTHON=.venv\Scripts\python.exe
) else (
  where python >nul 2>nul && set PYTHON=python
)
if not defined PYTHON (
  where py >nul 2>nul && set PYTHON=py
)

if not defined PYTHON (
  echo [错误] 未找到 Python，请先安装 Python 3.8+
  pause
  exit /b 1
)

REM 检查 pypinyin（智能拼音搜索依赖）
%PYTHON% -c "import pypinyin" >nul 2>nul
if errorlevel 1 (
  echo [提示] 安装拼音搜索依赖...
  %PYTHON% -m pip install pypinyin -q
)

echo [1/3] 正在启动多游戏数据服务...
echo [2/3] 服务就绪后自动打开浏览器: http://127.0.0.1:8080
echo [3/3] 关闭本窗口即停止服务
echo.
%PYTHON% web_server_multigame.py 8080

pause
