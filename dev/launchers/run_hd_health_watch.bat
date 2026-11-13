@echo off
REM Health watch: shows Jill's health live and records poison / death. READ-ONLY.
REM Home = poisoned   Page Up = poison cured   Page Down = note
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_health_watch.py
echo.
pause
