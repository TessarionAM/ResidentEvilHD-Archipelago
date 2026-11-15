@echo off
REM Load menu watch (read-only; F10 writes only when Claude asks): the save/load menu's state, for autoload.
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_load_menu_watch.py
echo.
pause
