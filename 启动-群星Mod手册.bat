@echo off
chcp 65001 >nul
title 群星 Mod 查询工具
echo ========================================
echo   群星 Mod 查询工具 - 一键启动
echo ========================================
echo.

cd /d "%~dp0"

REM 查找 Python
set PYTHON=
where python >nul 2>nul && set PYTHON=python
if not defined PYTHON (
  where py >nul 2>nul && set PYTHON=py
)

if not defined PYTHON (
  echo [错误] 未找到 Python，请先安装 Python 3.8+
  pause
  exit /b 1
)

echo [1/3] 正在启动数据服务...
echo [2/3] 服务启动后自动打开浏览器: http://localhost:8080
echo [3/3] 关闭本窗口即停止服务
echo.
%PYTHON% scripts\web_server.py 8080

pause
