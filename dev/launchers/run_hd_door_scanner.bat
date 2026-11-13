@echo off
REM Door scanner: logs every door's lock in each room you enter. READ-ONLY.
cd /d "%~dp0.."
set "PY=python"
if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" hd_door_scanner.py
echo.
pause
