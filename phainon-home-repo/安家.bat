@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if exist "%~dp0_python\python.exe" (
  set "PY=%~dp0_python\python.exe"
) else (
  set "PY=python"
  where python >nul 2>nul || set "PY=py"
)
"%PY%" -X utf8 "%~dp0_bin\install.py"
echo.
pause