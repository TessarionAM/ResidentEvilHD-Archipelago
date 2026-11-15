@echo off
REM Boss watch (read-only): boss kill / story flags live, for the Boss Rush goal.
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_boss_watch.py
echo.
pause
