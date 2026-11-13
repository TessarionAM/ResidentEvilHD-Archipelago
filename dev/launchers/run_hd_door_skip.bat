@echo off
REM Door skip without BhdTool (same patches as BhdTool v1.6) + a check of why BhdTool is not running.
REM Leave it open while you play.
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_door_skip.py
echo.
pause
