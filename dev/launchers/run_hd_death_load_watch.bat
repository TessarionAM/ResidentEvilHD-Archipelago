@echo off
REM Death & load watch: records the game's screens after Jill dies and while a save loads. READ-ONLY.
REM Home = Jill died   Page Up = new screen   Page Down = loading starts   End = back in control
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_death_load_watch.py
echo.
pause
