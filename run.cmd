@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PY_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PY_EXE%" (
  echo [ERROR] 未找到虚拟环境：%~dp0.venv
  echo 请先运行：.\setup.cmd
  exit /b 1
)

"%PY_EXE%" cli.py
endlocal

