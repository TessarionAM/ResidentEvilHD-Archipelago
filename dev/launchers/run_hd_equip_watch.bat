@echo off
REM Equip watch: finds where the game remembers the weapon Jill holds. READ-ONLY.
REM Home = equipped Handgun   Page Up = equipped Knife   Page Down = other
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_equip_watch.py
echo.
pause
