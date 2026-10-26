@echo off
setlocal
chcp 65001 >nul
REM One-command bootstrap for Windows (pure CMD, no PowerShell).
cd /d "%~dp0"

set "VENV_DIR=%~dp0.venv"
set "PY_EXE=%VENV_DIR%\Scripts\python.exe"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] 未找到 python，请先安装 Python 3.10+ 并加入 PATH。
  exit /b 1
)

if not exist "%PY_EXE%" (
  echo 创建虚拟环境: %VENV_DIR%
  python -m venv "%VENV_DIR%"
)

echo 升级 pip/setuptools/wheel
"%PY_EXE%" -m pip install -U pip setuptools wheel

echo 安装 Python 依赖: requirements.txt
"%PY_EXE%" -m pip install -r "%~dp0requirements.txt"

echo 安装 Playwright Chromium（首次可能较慢）
"%PY_EXE%" -m playwright install chromium

echo.
echo 完成。
echo 运行命令行: %PY_EXE% cli.py
endlocal

